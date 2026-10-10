"""Bounded algorithm-aware block-feature chains over one witnessed word pool.

Only completed, independently verified policies receive published physical
metrics. Greedy/beam ranking uses complete additive rollouts, not a claimed
lower bound on physical words after cross-stage cancellation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path

from .human_algorithms import _Candidate, _metrics, improve_human_method
from .human_chains import (BlockFeature, HumanStage, _chains, _fixed_features,
                           _observation, _stage, plan_human_stages)
from .human_methods import (HumanMethod, HumanMethodCase, HumanMethodStage, _compile_plan,
                            _expression_bound, _inverse, _validate_method)
from .loop_algorithms import LoopAlgorithm, LoopExpression


_EXECUTION = ("mean_htm", "worst_htm", "max_case_count", "case_count_sum",
              "original_leaf_count", "original_leaf_htm", "definition_htm", "stage_count")
_RECOGNITION = (_EXECUTION[2], _EXECUTION[3], *_EXECUTION[:2], *_EXECUTION[4:])
_PREFERENCES = {"execution": _EXECUTION, "recognition": _RECOGNITION}
_DISCOVERY_DEFAULTS = dict(mode="structured", max_seed_loops=32, max_candidates=3000,
                           max_word_length=3, rounds=1, max_states=2000,
                           max_stage_generators=24, max_alternatives=3,
                           max_htm_length=120, max_expanded_moves=480)


@dataclass(frozen=True)
class HumanChainCandidate:
    id: str
    source: str
    method: HumanMethod
    _metrics_json: str = field(repr=False, compare=False)

    @property
    def metrics(self):
        return json.loads(self._metrics_json)

    def to_dict(self):
        return {"id": self.id, "source": self.source,
                "metrics": self.metrics, "method": self.method.to_dict()}


@dataclass(frozen=True)
class HumanChainSearch:
    baseline: HumanMethod
    method: HumanMethod
    candidates: tuple[HumanChainCandidate, ...]
    frontier: tuple[str, ...]
    selected_id: str | None
    _metadata_json: str = field(repr=False, compare=False)

    @property
    def status(self):
        return self.method.status

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    def to_dict(self):
        return {"format": "bce-v2-human-chain-search", "version": 1,
                "status": self.status, "metadata": self.metadata,
                "baseline": self.baseline.to_dict(), "method": self.method.to_dict(),
                "selected_id": self.selected_id, "frontier": list(self.frontier),
                "candidates": [candidate.to_dict() for candidate in self.candidates]}

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path):
        self.to_json(path)
        return self.to_dict()


@dataclass(frozen=True)
class _Edge:
    stage: HumanStage
    cases: tuple[HumanMethodCase, ...]
    choices: tuple[_Candidate, ...]

    @property
    def additive_mean_htm(self):
        return sum(c.algorithm.htm_length for c in self.choices) / self.stage.case_count


def _signature(features):
    return tuple((feature.kind, feature.cells) for feature in features)


class _Context:
    def __init__(self, plan, baseline, discovery):
        self.plan, self.group, self.baseline = plan, plan.group, baseline
        self.generators = discovery._generators
        self.records = {g.id: g for g in self.generators}
        self.lengths = tuple((g.id, g.htm_length) for g in self.generators)
        self.pool = discovery._candidates
        self.blocks = {b.cells: i for i, b in enumerate(plan.inventory.blocks)}
        self.features = tuple(BlockFeature(kind, b.cells)
                              for kind in ("place_block", "solve_block") for b in plan.inventory.blocks)
        self.actions = dict(zip(self.group.permutations, self.group._summaries))
        self.edges, self.fixed, self.fallbacks, self.rollouts = {}, {}, {}, {}
        self.edge_evaluations, self.cache_hits = 0, 0

    def fallback(self, index):
        if index not in self.fallbacks:
            expression = LoopExpression.power(self.group.witness_for_index(index), -1)
            moves = expression.expanded_moves(
                self.generators, max_expanded_moves=max(1, _expression_bound(expression, self.records)))
            algorithm = LoopAlgorithm("fallback", expression, _inverse(self.group.permutations[index]),
                                      moves, self.plan.inventory, self.lengths, self.generators)
            self.fallbacks[index] = _Candidate(
                algorithm, "fallback", expression.structure_cost(self.generators))
        return self.fallbacks[index]

    def edge(self, members, feature):
        key = members, feature
        if key in self.edges:
            self.cache_hits += 1
            return self.edges[key]
        self.edge_evaluations += 1
        block = self.blocks[feature.cells]
        solved = _observation(self.group._summaries[0], block, feature.kind)
        representatives = {}
        for i in members:
            observation = _observation(self.group._summaries[i], block, feature.kind)
            representatives.setdefault(observation, i)
        if len(representatives) == 1:
            self.edges[key] = None
            return None
        if members not in self.fixed:
            self.fixed[members] = _fixed_features(self.group, members)
        stage, _ = _stage(self.group, members, feature, block, 1, self.fixed[members])
        permitted = {self.group.permutations[i] for i in members}
        by_case = {}
        for candidate in self.pool:
            effect = candidate.algorithm.permutation
            if effect in permitted:
                observation = _observation(self.actions[_inverse(effect)], block, feature.kind)
                if observation not in by_case or candidate.key < by_case[observation].key:
                    by_case[observation] = candidate
        cases, choices = [], []
        for observation in stage.observations:
            index = representatives[observation]
            correction = None
            if observation != solved:
                fallback = self.fallback(index)
                choice = min((fallback, by_case.get(observation, fallback)), key=lambda c: c.key)
                choices.append(choice)
                correction = str(len(choices) - 1)  # local index until complete compilation
            cases.append(HumanMethodCase(observation, correction, self.group.permutations[index]))
        edge = _Edge(stage, tuple(cases), tuple(choices))
        self.edges[key] = edge
        return edge

    def next_edges(self, members):
        return tuple(edge for feature in self.features if (edge := self.edge(members, feature)) is not None)

    def suffix(self, members):
        """Complete minimum-index full-block rollout; no partial-policy claim."""
        if members not in self.rollouts:
            current, result = members, []
            while current != (0,):
                choices = [self.edge(current, feature) for feature in self.features
                           if feature.kind == "solve_block"]
                edge = min((e for e in choices if e is not None),
                           key=lambda e: (e.stage.index, e.stage.block_index))
                result.append(edge)
                current = edge.stage.members_after
            self.rollouts[members] = tuple(result)
        return self.rollouts[members]

    def prefix_edges(self, features):
        current, result = tuple(range(len(self.group))), []
        for feature in features:
            edge = self.edge(current, feature)
            if edge is None:
                raise ValueError("internal chain prefix contains a redundant feature")
            result.append(edge)
            current = edge.stage.members_after
        return tuple(result), current

    def rollout(self, features):
        edges, current = self.prefix_edges(features)
        return (*edges, *self.suffix(current))

    def rank(self, features, preference):
        edges = self.rollout(features)
        # Exact mean for additive stage execution under uniform H, but only a
        # proxy for the full physical solution after boundary cancellation.
        mean = sum(e.additive_mean_htm for e in edges)
        maximum = max((e.stage.case_count for e in edges), default=0)
        total = sum(e.stage.case_count for e in edges)
        leaves = {i for e in edges for c in e.choices for i in c.algorithm.base_ids}
        memory = sum(self.records[i].htm_length for i in leaves)
        costs = ((mean, maximum, total) if preference == "execution" else (maximum, total, mean))
        return (*costs, len(leaves), memory, len(edges), _signature(features))

    def compile(self, features, strategy="manual", skipped=()):
        edges, current = self.prefix_edges(features)
        if current != (0,):
            raise ValueError("cannot publish an unfinished chain")
        stages, algorithms = [], []
        for number, edge in enumerate(edges, 1):
            local_ids, cases = {}, []
            for local, choice in enumerate(edge.choices):
                identifier = f"A{len(algorithms) + 1}"
                local_ids[str(local)] = identifier
                algorithms.append(replace(choice.algorithm, id=identifier))
            for case in edge.cases:
                cases.append(replace(case, algorithm_id=local_ids.get(case.algorithm_id)))
            stage = edge.stage
            stages.append(HumanMethodStage(number, stage.feature, stage.block_index, stage.block_name,
                                           stage.order_before, stage.order_after, stage.solved_observation,
                                           stage.implied_features, tuple(cases)))
        used = {g.id for g in self.group.generators} | {i for a in algorithms for i in a.base_ids}
        generators = tuple(g for g in self.generators if g.id in used)
        algorithms = tuple(replace(a, _generators=generators) for a in algorithms)
        method = _validate_method(replace(self.baseline, strategy=strategy, generators=generators,
                                          stages=tuple(stages), algorithms=algorithms,
                                          skipped_features=tuple(skipped)), complete_loops=self.plan.analysis.loops)
        return method, self.measure(method)

    def measure(self, method):
        metrics = _metrics(method, self.actions)
        algorithms = {a.id: a for a in method.algorithms}
        stages = method.stages
        metrics.update(stage_count=len(stages), max_case_count=max((s.case_count for s in stages), default=0),
                       case_count_sum=sum(s.case_count for s in stages),
                       additive_mean_htm=sum(
                           sum(algorithms[c.algorithm_id].htm_length for c in s.cases
                               if c.algorithm_id is not None) / s.case_count for s in stages))
        return metrics


def _dominates(first, second):
    return (all(first[k] <= second[k] for k in _EXECUTION) and
            any(first[k] < second[k] for k in _EXECUTION))


def select_human_chain(initial, *, strategy="placement_then_orientation", manual_features=None,
                       preference="execution", beam_width=4, max_expansions=64, max_methods=16,
                       discovery_options=None, max_group_elements=None,
                       gap_executable="gap", timeout=None, root=None, backend="explicit",
                       dictionary=None, dictionary_options=None):
    """Compare complete recognizable methods using a shared witnessed word pool.

    Exact preparation has the usual opt-in cap. Chain budgets bound additional
    greedy/beam exploration, never fixed controls or complete fallbacks. Raw BFS
    and shared-pool policies for both automatic chains remain selectable.
    A supplied manual feature list is an additional complete control, not a
    constraint on every search branch. No globally optimal or human-reviewed
    chain is claimed. Selected methods retain the portable version-one schema.
    """
    if backend not in ("explicit", "symbolic"):
        raise ValueError("backend must be explicit or symbolic")
    if backend == "symbolic":
        from .symbolic_chain_search import select_symbolic_human_chain
        return select_symbolic_human_chain(
            initial, strategy=strategy, manual_features=manual_features,
            preference=preference, beam_width=beam_width, max_expansions=max_expansions,
            max_methods=max_methods, discovery_options=discovery_options,
            dictionary=dictionary, dictionary_options=dictionary_options,
            max_group_elements=max_group_elements, gap_executable=gap_executable,
            timeout=timeout, root=root)
    if dictionary is not None or dictionary_options is not None:
        raise ValueError("shared dictionary options currently require backend='symbolic'")
    if strategy not in ("placement_then_orientation", "fully_solve_each_block"):
        raise ValueError("chain search strategy must name an automatic baseline")
    if preference not in _PREFERENCES:
        raise ValueError("preference must be execution or recognition")
    for name, value, minimum in (("beam_width", beam_width, 1),
                                  ("max_expansions", max_expansions, 0), ("max_methods", max_methods, 0)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
    if discovery_options is not None and not isinstance(discovery_options, dict):
        raise TypeError("discovery_options must be a dictionary or None")
    supplied = dict(discovery_options or {})
    if set(supplied) - set(_DISCOVERY_DEFAULTS):
        raise ValueError("unknown discovery option")
    discovery_settings = {**_DISCOVERY_DEFAULTS, **supplied}
    if discovery_settings["mode"] not in ("original", "shallow", "structured"):
        raise ValueError("unknown discovery mode")
    for name, value in discovery_settings.items():
        if name == "mode":
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < (1 if name == "max_alternatives" else 0):
            raise ValueError(f"invalid discovery budget: {name}")
    if manual_features is not None:
        manual_features = tuple(manual_features)
        if any(not isinstance(f, BlockFeature) for f in manual_features):
            raise TypeError("manual_features must contain BlockFeature instances")
    settings = dict(strategy=strategy, preference=preference, beam_width=beam_width,
                    max_expansions=max_expansions, max_methods=max_methods,
                    discovery_options=discovery_settings,
                    manual_features=None if manual_features is None else [f.to_dict() for f in manual_features])
    plan = plan_human_stages(initial, strategy=strategy, max_group_elements=max_group_elements,
                             gap_executable=gap_executable, timeout=timeout, root=root)
    metadata = {"settings": settings, "preference_orders": _PREFERENCES,
                "pareto_dimensions": _EXECUTION, "exhaustive_chain_search": False,
                "human_reviewed": False, "coverage": "partial", "nodes_expanded": 0,
                "additional_methods_evaluated": 0, "stage_edges_evaluated": 0,
                "stage_cache_hits": 0, "discovery": None,
                "rank_scope": "complete additive minimum-index full-block rollout; physical-cost proxy"}
    baseline = _compile_plan(plan)
    if plan.status != "completed":
        return HumanChainSearch(baseline, baseline, (), (), None, json.dumps(metadata, sort_keys=True))
    controls, raw_controls = [], []
    for name in ("placement_then_orientation", "fully_solve_each_block"):
        stages, fixed, skipped = _chains(plan.group, name, None)
        controls.append((f"baseline:{name}", tuple(s.feature for s in stages), name, skipped))
        raw = baseline if name == strategy else _compile_plan(
            replace(plan, strategy=name, stages=stages, initial_features=fixed, skipped_features=skipped))
        raw_controls.append((name, raw))
    if manual_features is not None:
        cells = {b.cells for b in plan.inventory.blocks}
        if any(f.cells not in cells for f in manual_features):
            raise ValueError("each manual feature must name an exact reference inventory block")
        stages, _, skipped = _chains(plan.group, "manual", manual_features)
        controls.append(("manual", tuple(s.feature for s in stages), "manual", skipped))
    discovery = improve_human_method(baseline, **discovery_settings)
    context = _Context(plan, baseline, discovery)
    candidates, seen = [], set()

    def complete(features, source, method_strategy="manual", skipped=()):
        signature = _signature(features)
        if source in ("greedy", "beam"):
            if signature in seen or metadata["additional_methods_evaluated"] >= max_methods:
                return
            metadata["additional_methods_evaluated"] += 1
        method, metrics = context.compile(features, method_strategy, skipped)
        candidates.append(HumanChainCandidate(f"C{len(candidates) + 1}", source, method,
                                              json.dumps(metrics, sort_keys=True)))
        seen.add(signature)

    for source, features, name, skipped in controls:
        if source != "manual":
            complete(features, source, name, skipped)
    # A locally shorter pooled policy can worsen whole-word cancellation or
    # shared memory. Keep the original policies in the actual Pareto comparison.
    for name, raw in raw_controls:
        candidates.append(HumanChainCandidate(f"C{len(candidates) + 1}", f"fallback:{name}", raw,
                                              json.dumps(context.measure(raw), sort_keys=True)))
    for source, features, name, skipped in controls:
        if source == "manual":
            complete(features, source, name, skipped)
    # Greedy lookahead evaluates complete rollout proxies at each decision.
    prefix, current = (), tuple(range(len(plan.group)))
    while (current != (0,) and metadata["nodes_expanded"] < max_expansions and
           metadata["additional_methods_evaluated"] < max_methods):
        metadata["nodes_expanded"] += 1
        edge = min(context.next_edges(current),
                   key=lambda e: context.rank((*prefix, e.stage.feature), preference))
        prefix = (*prefix, edge.stage.feature)
        current = edge.stage.members_after
    if prefix:
        rollout = context.rollout(prefix)
        complete(tuple(e.stage.feature for e in rollout), "greedy")
    # Keep distinct feature prefixes even when they reach an equal subgroup.
    beam = [()]
    while (beam and metadata["nodes_expanded"] < max_expansions and
           metadata["additional_methods_evaluated"] < max_methods):
        successors = []
        for prefix in beam:
            if (metadata["nodes_expanded"] >= max_expansions or
                    metadata["additional_methods_evaluated"] >= max_methods):
                break
            _, current = context.prefix_edges(prefix)
            if current == (0,):
                continue
            metadata["nodes_expanded"] += 1
            for edge in context.next_edges(current):
                next_prefix = (*prefix, edge.stage.feature)
                successors.append(next_prefix)
        beam = sorted(set(successors), key=lambda fs: context.rank(fs, preference))[:beam_width]
        for prefix in beam:
            complete(tuple(e.stage.feature for e in context.rollout(prefix)), "beam")
    metrics = {c.id: c.metrics for c in candidates}
    frontier = tuple(c.id for c in candidates
                     if not any(_dominates(metrics[other.id], metrics[c.id]) for other in candidates))
    by_id = {c.id: c for c in candidates}
    selected = min((by_id[i] for i in frontier),
                   key=lambda c: (*tuple(metrics[c.id][k] for k in _PREFERENCES[preference]), c.id))
    metadata.update(coverage="certified", discovery=discovery.metadata,
                    discovery_origin=strategy, shared_pool_effects=len({c.algorithm.permutation for c in context.pool}),
                    shared_pool_words=len(context.pool), stage_edges_evaluated=context.edge_evaluations,
                    stage_cache_hits=context.cache_hits,
                    node_limit_reached=metadata["nodes_expanded"] >= max_expansions,
                    method_limit_reached=metadata["additional_methods_evaluated"] >= max_methods,
                    selected_source=selected.source)
    return HumanChainSearch(baseline, selected.method, tuple(candidates), frontier, selected.id,
                            json.dumps(metadata, sort_keys=True))
