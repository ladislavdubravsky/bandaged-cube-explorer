"""Bounded stage-aware word discovery with a complete method as fallback.

Physical words are compared after adjacent-turn simplification. Dijkstra
labels only guide discovery: their additive macro cost does not prove shortest
physical words, and truncated Schreier candidates are not a certified SGS.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from itertools import islice, product, zip_longest
import json
from pathlib import Path

from ._moves import _simplified_moves
from .computation import checkpoint, report_progress, retain_method
from .human_methods import HumanMethod, _expression_bound, _inverse, _observe, _then, _validate_method
from .human_witnesses import stored_loop_generators
from .loop_algorithms import (
    AlgorithmLibrary, LoopAlgorithm, LoopExpression, _loops_from_records, _mining_expressions,
)
from .preparation import reference_loops


_IDENTITY = tuple(range(48))


@dataclass(frozen=True)
class HumanAlgorithmAlternative:
    stage_number: int
    observation: tuple[int, ...]
    algorithm: LoopAlgorithm
    source: str


@dataclass(frozen=True)
class HumanAlgorithmSearch:
    baseline: HumanMethod
    method: HumanMethod
    alternatives: tuple[HumanAlgorithmAlternative, ...]
    _generators: tuple = field(repr=False, compare=False)
    _metadata_json: str = field(repr=False, compare=False)
    _candidates: tuple[_Candidate, ...] = field(default=(), repr=False, compare=False)

    @property
    def metadata(self):
        """Return a copy of settings, bounded work and exact method metrics."""
        return json.loads(self._metadata_json)

    def to_dict(self):
        return {"format": "bce-v2-human-algorithm-search", "version": 1,
                "metadata": self.metadata, "baseline": self.baseline.to_dict(),
                "method": self.method.to_dict(),
                "candidate_generators": [g.to_dict() for g in self._generators],
                "alternatives": [{"stage_number": a.stage_number, "observation": list(a.observation),
                                  "source": a.source, "algorithm": a.algorithm.to_dict()}
                                 for a in self.alternatives]}

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path):
        self.to_json(path)
        return self.to_dict()


@dataclass(frozen=True)
class _Candidate:
    algorithm: LoopAlgorithm
    source: str
    description_cost: int

    @property
    def key(self):
        a = self.algorithm
        return a.htm_length, a.qtm_length, self.description_cost, a.expression.render()

    @property
    def structured_key(self):
        a = self.algorithm
        return self.description_cost, a.htm_length, a.qtm_length, a.expression.render()


def _merge_seeds(method, complete_loops, maximum):
    records = [g.to_dict() for g in method.generators]
    by_word = {(g.permutation, g.turn_sequence): g.id for g in method.generators}
    identifiers, seed_ids = {g.id for g in method.generators}, []
    next_id = max(identifiers, default=-1) + 1
    for generator in islice(complete_loops.generators, maximum):
        key = generator.permutation, generator.turn_sequence
        if key in by_word:
            identifier = by_word[key]
        else:
            identifier = generator.id
            if identifier in identifiers:
                identifier = next_id
                next_id += 1
            identifiers.add(identifier)
            next_id = max(next_id, identifier + 1)
            record = generator.to_dict()
            record["id"] = identifier
            records.append(record)
            by_word[key] = identifier
        seed_ids.append(identifier)
    generators = stored_loop_generators(records, method.inventory, method.root_vertex, complete_loops)
    return generators, tuple(dict.fromkeys(seed_ids))


def _stage_groups(method, actions):
    current, groups = frozenset(actions), []
    for stage in method.stages:
        checkpoint("algorithm_stages", work=1, stage=stage.number)
        target = frozenset(p for p in current
                           if _observe(actions[p], stage.block_index, stage.feature.kind) == stage.solved_observation)
        groups.append((current, target))
        current = target
    return tuple(groups)


def _metrics(method, actions):
    algorithms = {a.id: a for a in method.algorithms}
    totals, worst = [0, 0], [0, 0]
    for index, original in enumerate(sorted(method._permutations)):
        if index % 128 == 0:
            checkpoint("algorithm_metrics", work=1, states=index)
        current, words = original, []
        for stage in method.stages:
            observation = _observe(actions[current], stage.block_index, stage.feature.kind)
            case = next(c for c in stage.cases if c.observation == observation)
            if case.algorithm_id is not None:
                algorithm = algorithms[case.algorithm_id]
                words.extend(algorithm.turn_sequence.split())
                current = _then(current, algorithm.permutation)
        if current != _IDENTITY:
            raise ValueError("candidate method fails whole-method coverage")
        moves = _simplified_moves(words).split()
        costs = len(moves), sum(2 if move.endswith("2") else 1 for move in moves)
        for i, cost in enumerate(costs):
            totals[i] += cost
            worst[i] = max(worst[i], cost)
    leaves = {identifier for a in method.algorithms for identifier in a.base_ids}
    visible = {key for a in method.algorithms for key in a.expression.memory_keys}
    return {"states": method.group_order,
            "mean_htm": totals[0] / method.group_order, "worst_htm": worst[0], "total_htm": totals[0],
            "mean_qtm": totals[1] / method.group_order, "worst_qtm": worst[1], "total_qtm": totals[1],
            "algorithm_count": len(method.algorithms),
            "definition_htm": sum(a.htm_length for a in method.algorithms),
            "definition_qtm": sum(a.qtm_length for a in method.algorithms),
            "visible_leaf_count": len(visible), "original_leaf_count": len(leaves),
            "original_leaf_htm": sum(g.htm_length for g in method.generators if g.id in leaves)}


class _Search:
    def __init__(self, method, generators, settings):
        self.method, self.generators, self.settings = method, generators, settings
        self.records = {g.id: g for g in generators}
        self.lengths = tuple((generator.id, generator.htm_length) for generator in generators)
        self.library = (AlgorithmLibrary(_loops_from_records(generators), (), (), ())
                        if generators else None)
        self.pool, self.seen = defaultdict(list), set()
        self.counts, self.sources = Counter(), Counter()

    def candidate(self, algorithm, source):
        algorithm = replace(algorithm, _inventory=self.method.inventory, _generators=self.generators,
                            _leaf_htm_lengths=self.lengths, _human_score=())
        return _Candidate(algorithm, source, algorithm.expression.structure_cost(self.generators))

    def add(self, candidate):
        effect = candidate.algorithm.permutation
        choices = self.pool[effect]
        if any(c.algorithm.expression == candidate.algorithm.expression for c in choices):
            return
        choices.append(candidate)
        # Retain a physical and a description representative, then additional
        # physical variants. Baseline case fallbacks are retained separately.
        keep = [min(choices, key=lambda c: c.key), min(choices, key=lambda c: c.structured_key)]
        keep.extend(sorted(choices, key=lambda c: c.key))
        result = []
        for item in keep:
            if item not in result:
                result.append(item)
            if len(result) >= max(2, self.settings["max_alternatives"]):
                break
        self.pool[effect] = result

    def propose(self, expression, source):
        if self.counts["candidates_examined"] >= self.settings["max_candidates"]:
            self.counts["candidate_limit_reached"] = 1
            return False
        checkpoint("algorithm_candidates", work=1, source=source)
        self.counts["candidates_examined"] += 1
        self.sources[source] += 1
        if expression in self.seen:
            self.counts["duplicate_expressions"] += 1
            return True
        self.seen.add(expression)
        if _expression_bound(expression, self.records) > self.settings["max_expanded_moves"]:
            self.counts["expansion_pruned"] += 1
            return True
        effect = expression.evaluate(self.generators)
        if effect == _IDENTITY:
            self.counts["identity_candidates"] += 1
            return True
        if effect not in self.method._permutations:
            raise ValueError("discovered word leaves the complete reference group")
        algorithm = self.library.build_algorithm(expression,
                                                  max_expanded_moves=max(1, self.settings["max_expanded_moves"]))
        if algorithm.htm_length > self.settings["max_htm_length"]:
            self.counts["length_pruned"] += 1
            return True
        self.counts["candidates_built"] += 1
        self.add(self.candidate(algorithm, source))
        return True

    def consume(self, expressions, source, maximum):
        for expression in islice(expressions, max(0, maximum)):
            if not self.propose(expression, source):
                break

    def remaining(self):
        return self.settings["max_candidates"] - self.counts["candidates_examined"]

    def dijkstra(self, edges, allowed, maximum_states, source):
        """Discover bounded macro words, ranking by additive edge HTM."""
        labels, paths = {_IDENTITY: (0, 0)}, {}
        queue, serial = [(0, 0, 0, _IDENTITY, ())], 0
        settled = 0
        while queue and self.remaining() > 0:
            checkpoint("algorithm_states", work=1, source=source,
                       states=self.counts["states_expanded"])
            if settled >= maximum_states or self.counts["states_expanded"] >= self.settings["max_states"]:
                self.counts["state_limit_reached"] = 1
                break
            cost, depth, _, element, expressions = heappop(queue)
            if labels.get(element) != (cost, depth) or element in paths:
                continue
            paths[element] = LoopExpression.sequence(*expressions)
            settled += 1
            self.counts["states_expanded"] += 1
            if element != _IDENTITY:
                self.propose(paths[element], source)
            if depth >= self.settings["max_word_length"]:
                continue
            for edge in edges:
                self.counts["transitions_examined"] += 1
                successor = _then(element, edge.algorithm.permutation)
                if successor not in allowed:
                    raise ValueError("stage search generator fails protected-feature preservation")
                label = cost + edge.algorithm.htm_length, depth + 1
                if successor not in labels or label < labels[successor]:
                    labels[successor] = label
                    serial += 1
                    heappush(queue, (*label, serial, successor, (*expressions, edge.algorithm.expression)))
        return paths


def _shallow_words(alphabet, depth):
    for length in range(2, depth + 1):
        for word in product(alphabet, repeat=length):
            yield LoopExpression.sequence(*word)


def _protected_key(action, previous):
    return tuple(_observe(action, stage.block_index, stage.feature.kind) for stage in previous)


def _schreier_words(method, actions, paths, alphabet):
    def stage_words(previous):
        representatives = {}
        for element, expression in paths.items():
            representatives.setdefault(_protected_key(actions[element], previous), (element, expression))
        for element, expression in representatives.values():
            for generator in alphabet:
                successor = _then(element, generator.algorithm.permutation)
                other = representatives.get(_protected_key(actions[successor], previous))
                if other is not None:
                    yield LoopExpression.sequence(expression, generator.algorithm.expression,
                                                  LoopExpression.power(other[1], -1))
    # Fairly interleave late stabilizers rather than spending the entire budget
    # on the first stage. These need not be complete transversals.
    streams = [stage_words(method.stages[:i]) for i in range(1, len(method.stages))]
    for batch in zip_longest(*streams):
        yield from (expression for expression in batch if expression is not None)


def _collision_words(method, actions, paths, anchors):
    def stage_words(previous):
        buckets = defaultdict(list)
        for element, expression in paths.items():
            key = _protected_key(actions[element], previous)
            for anchor in buckets[key]:
                yield LoopExpression.sequence(expression, LoopExpression.power(anchor, -1))
            if len(buckets[key]) < anchors:
                buckets[key].append(expression)
    for batch in zip_longest(*(stage_words(method.stages[:i]) for i in range(1, len(method.stages)))):
        yield from (expression for expression in batch if expression is not None)


def improve_human_method(method, *, mode="structured", max_seed_loops=32, max_candidates=3000,
                         max_word_length=3, rounds=1, max_states=2000, max_stage_generators=24,
                         max_alternatives=3, max_htm_length=120, max_expanded_moves=480,
                         dictionary=None):
    """Improve a fixed stage policy while retaining certified complete fallbacks.

    No GAP is required. Native root loops supplement the saved generating set;
    saved local IDs retain their actions and words. Original, shallow and
    structured modes share the same explicit bounds. Zero work or restrictive
    quality limits leave the baseline policy available and certified.
    """
    if not isinstance(method, HumanMethod):
        raise TypeError("improvement requires a compiled HumanMethod")
    if method.status != "completed":
        raise ValueError("algorithm improvement requires a complete baseline method")
    if mode not in ("original", "shallow", "structured"):
        raise ValueError("mode must be original, shallow or structured")
    settings = dict(mode=mode, max_seed_loops=max_seed_loops, max_candidates=max_candidates,
                    max_word_length=max_word_length, rounds=rounds, max_states=max_states,
                    max_stage_generators=max_stage_generators, max_alternatives=max_alternatives,
                    max_htm_length=max_htm_length, max_expanded_moves=max_expanded_moves)
    for name, value in settings.items():
        if name == "mode":
            continue
        minimum = 1 if name == "max_alternatives" else 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
    if method.backend == "symbolic":
        from .symbolic_human_algorithms import improve_symbolic_human_method
        return improve_symbolic_human_method(method, dictionary=dictionary, **settings)
    if dictionary is not None:
        raise ValueError("a supplied dictionary currently requires a symbolic method")
    complete_loops = reference_loops(method)
    baseline = _validate_method(method, complete_loops=complete_loops)
    retain_method(baseline, source="algorithm_baseline")
    report_progress("algorithm_improvement", status="started", backend="explicit", mode=mode)
    checkpoint("algorithm_improvement", work=0)
    generators, seed_ids = _merge_seeds(baseline, complete_loops, max_seed_loops)
    search = _Search(baseline, generators, settings)
    baseline_algorithms = {a.id: search.candidate(a, "baseline") for a in baseline.algorithms}
    for candidate in baseline_algorithms.values():
        search.add(candidate)
    actions = {}
    for index, permutation in enumerate(sorted(baseline._permutations)):
        if index % 128 == 0:
            checkpoint("algorithm_actions", work=1, states=index)
        actions[permutation] = baseline.inventory.action(permutation)
    groups = _stage_groups(baseline, actions)
    alphabet = tuple(LoopExpression.power(LoopExpression.loop(identifier), exponent)
                     for identifier in seed_ids for exponent in (1, -1))
    search.consume(alphabet, "original", search.remaining())
    seeds = []
    for expression in alphabet:
        effect = expression.evaluate(generators)
        # A previously improved policy may already contain this same native
        # word. Its source label must not remove the edge on a repeated run.
        choices = [c for c in search.pool.get(effect, ())
                   if c.algorithm.htm_length <= max_htm_length and
                   _expression_bound(c.algorithm.expression, search.records) <= max_expanded_moves]
        if choices:
            candidate = min(choices, key=lambda c: c.key)
            if candidate not in seeds:
                seeds.append(candidate)
    paths = {_IDENTITY: LoopExpression.sequence()}
    if mode != "original" and alphabet and max_word_length > 0:
        search.consume(_shallow_words(alphabet, max_word_length), "shallow",
                       min(search.remaining(), max_candidates // 3))
        state_share = max_states if mode == "shallow" else max_states // 2
        paths.update(search.dijkstra(seeds, baseline._permutations, state_share, "global_words"))
    for iteration in range(rounds if mode == "structured" else 0):
        checkpoint("algorithm_round", work=1, round=iteration + 1)
        if search.remaining() <= 0:
            break
        previous_work = search.counts["candidates_examined"], search.counts["states_expanded"]
        operands = [c.algorithm for c in sorted((min(v, key=lambda c: c.key) for v in search.pool.values()),
                                                key=lambda c: c.key)[:max_stage_generators]]
        families = (_schreier_words(baseline, actions, paths, seeds),
                    _collision_words(baseline, actions, paths, max_alternatives),
                    _mining_expressions(operands))
        budget = search.remaining() // max(1, 2 * (rounds - iteration))
        proposed = 0
        for batch in zip_longest(*families):
            for source, expression in zip(("schreier", "same_coset", "structured"), batch):
                if expression is None:
                    continue
                if proposed >= budget or not search.propose(expression, source):
                    break
                proposed += 1
            if proposed >= budget or search.remaining() <= 0:
                break
        for stage, (current, _) in zip(baseline.stages, groups):
            edges = sorted((c for p, choices in search.pool.items() if p in current for c in choices),
                           key=lambda c: c.key)[:max_stage_generators]
            remaining_states = max_states - search.counts["states_expanded"]
            share = remaining_states // max(1, len(baseline.stages) - stage.number + 1)
            search.dijkstra(edges, current, share, "stage_words")
        search.counts["rounds_completed"] += 1
        if previous_work == (search.counts["candidates_examined"], search.counts["states_expanded"]):
            break
    stages, chosen_algorithms, alternatives, summaries = [], [], [], []
    for stage, (current, _) in zip(baseline.stages, groups):
        checkpoint("algorithm_stages", work=1, stage=stage.number)
        by_observation = defaultdict(list)
        for effect, choices in search.pool.items():
            if effect in current:
                observation = _observe(actions[_inverse(effect)], stage.block_index, stage.feature.kind)
                by_observation[observation].extend(choices)
        cases, changed, fallbacks, improved = [], 0, 0, 0
        for case in stage.cases:
            if case.algorithm_id is None:
                cases.append(case)
                continue
            fallback = baseline_algorithms[case.algorithm_id]
            choices = [fallback, *by_observation[case.observation]]
            best = min(choices, key=lambda c: c.key)
            if best.key[:3] >= fallback.key[:3]:
                best = fallback
            keep = [best, min(choices, key=lambda c: c.structured_key), fallback]
            keep.extend(sorted(choices, key=lambda c: c.key))
            retained = []
            for candidate in keep:
                if candidate not in retained:
                    retained.append(candidate)
                if len(retained) >= max_alternatives:
                    break
            alternatives.extend(HumanAlgorithmAlternative(stage.number, case.observation, c.algorithm, c.source)
                                for c in retained)
            identifier = f"A{len(chosen_algorithms) + 1}"
            chosen_algorithms.append(replace(best.algorithm, id=identifier))
            cases.append(replace(case, algorithm_id=identifier))
            changed += ((best.algorithm.permutation, best.algorithm.turn_sequence) !=
                        (fallback.algorithm.permutation, fallback.algorithm.turn_sequence))
            fallbacks += best.source == "baseline"
            improved += best.key[:2] < fallback.key[:2]
        summaries.append({"stage_number": stage.number, "cases": stage.case_count,
                          "changed_cases": changed, "improved_cases": improved,
                          "fallback_cases": fallbacks,
                          "admissible_effects": sum(p in current for p in search.pool)})
        stages.append(replace(stage, cases=tuple(cases)))
    used_ids = {g.id for g in baseline.generators} | {i for a in chosen_algorithms for i in a.base_ids}
    selected_generators = tuple(g for g in generators if g.id in used_ids)
    selected_algorithms = tuple(replace(a, _generators=selected_generators) for a in chosen_algorithms)
    proposed_method = _validate_method(replace(baseline, generators=selected_generators,
                                              algorithms=selected_algorithms, stages=tuple(stages)),
                                       complete_loops=complete_loops)
    before, proposed_metrics = _metrics(baseline, actions), _metrics(proposed_method, actions)
    # A local case improvement can change later cases and boundary cancellations.
    # Retain the baseline if the complete physical HTM mean or worst regresses.
    accepted = (proposed_metrics["total_htm"] <= before["total_htm"] and
                proposed_metrics["worst_htm"] <= before["worst_htm"])
    result = proposed_method if accepted else baseline
    retain_method(result, source="algorithm_improvement", metrics=proposed_metrics if accepted else before)
    report_progress("algorithm_improvement", status="completed", backend="explicit", accepted=accepted,
                    candidates=search.counts["candidates_examined"], states=search.counts["states_expanded"])
    metadata = {"settings": settings, "exhaustive_word_search": False,
                "selection": "physical HTM, QTM, expression description cost; full-method HTM guard",
                "macro_search_cost": "sum of simplified edge HTM; heuristic for physical words",
                "preparation_group_elements": baseline.group_order,
                "native_loop_count": len(complete_loops), "seed_loop_count": len(seed_ids),
                "seed_action_count": len(seeds),
                "candidates_examined": search.counts["candidates_examined"],
                "candidates_built": search.counts["candidates_built"],
                "states_expanded": search.counts["states_expanded"],
                "transitions_examined": search.counts["transitions_examined"],
                "attempted_by_source": dict(sorted(search.sources.items())),
                "candidate_limit_reached": bool(search.counts["candidate_limit_reached"] or
                                                search.counts["candidates_examined"] == max_candidates),
                "state_limit_reached": bool(search.counts["state_limit_reached"]),
                "identity_candidates": search.counts["identity_candidates"],
                "duplicate_expressions": search.counts["duplicate_expressions"],
                "length_pruned": search.counts["length_pruned"],
                "expansion_pruned": search.counts["expansion_pruned"],
                "rounds_completed": search.counts["rounds_completed"], "proposed_stages": summaries,
                "stages": summaries if accepted else [
                    {**summary, "changed_cases": 0, "improved_cases": 0,
                     "fallback_cases": summary["cases"] - 1} for summary in summaries],
                "accepted": accepted, "baseline_metrics": before, "proposed_metrics": proposed_metrics,
                "improved_metrics": proposed_metrics if accepted else before,
                "fallback_policy_retained": True, "coverage": result.coverage}
    retained = tuple(c for effect in sorted(search.pool)
                     for c in sorted(search.pool[effect], key=lambda c: c.key))
    return HumanAlgorithmSearch(baseline, result, tuple(alternatives), generators,
                                json.dumps(metadata, sort_keys=True, separators=(",", ":")), retained)
