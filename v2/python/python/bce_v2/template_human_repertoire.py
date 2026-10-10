"""Symmetry-closed learned templates and complete case-target policies.

The exact finite group is a coverage certificate. Search for nicer physical
words, smaller dictionaries and mixed feature chains has explicit budgets;
none of those searches certifies globally shortest or easiest instructions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from heapq import heappop, heappush
import json
from math import isfinite
from types import SimpleNamespace

from . import State
from ._moves import _simplified_moves
from .human_algorithms import _stage_groups
from .human_chains import BlockFeature, _inverse_moves, plan_human_stages
from .human_methods import (HumanMethod, HumanMethodCase, HumanMethodStage,
                            _compile_plan, _expression_bound, _fixed_features,
                            _inverse, _observe, _require, _then, _validate_method)
from .human_repertoire import (
    HumanMacroRecipe, HumanRepertoire, HumanRepertoireCase, HumanRepertoireMacro,
    _baseline_metrics, _build_algorithm, _compile_policies, _same_json,
    _validate_repertoire,
)
from .isotropy import isotropy_loops
from .loop_algorithms import LoopAlgorithm, LoopExpression
from .loop_rotations import bandage_symmetries


_IDENTITY = tuple(range(48))
_DIMENSIONS = ("dictionary_score", "instruction_symbols", "macro_count", "mean_htm",
               "worst_htm", "max_case_count", "case_count_sum")
_PREFERENCES = {
    "memory": _DIMENSIONS,
    "execution": ("mean_htm", "worst_htm", "dictionary_score", "instruction_symbols",
                  "macro_count", "max_case_count", "case_count_sum"),
    "recognition": ("max_case_count", "case_count_sum", "instruction_symbols",
                    "dictionary_score", "macro_count", "mean_htm", "worst_htm"),
}
_BUDGETS = ("max_trials", "max_applications", "max_word_candidates", "max_word_frontier",
            "beam_width", "max_chain_expansions", "max_chain_methods")
_CHUNK_OPTIONS = {"max_chunk_length": 8, "min_chunk_length": 3, "max_chunks": 12,
                  "max_candidates": 256, "max_word_moves": 96}


def _recipe_symbols(recipe):
    # A power or regrip is an instruction as well as its body. Sequences do
    # not contribute a separate symbol; their individual calls do.
    return (1 if recipe.kind != "sequence" else 0) + sum(
        _recipe_symbols(child) for child in recipe.children)


def _dictionary(reference, macros, options):
    from .human_chunks import extract_algorithm_chunks
    return extract_algorithm_chunks(reference,
        {macro.id: macro.algorithm.turn_sequence for macro in macros}, **options)


def _augment_metrics(metrics, method, stages, dictionary):
    result = dict(metrics)
    chunk = dictionary.metrics
    result.update(dictionary_score=chunk["score"],
                  chunk_definition_moves=chunk["dictionary_definition_moves"],
                  chunk_definition_symbols=chunk["dictionary_definition_symbols"],
                  chunk_recipe_symbols=chunk["recipe_symbols"],
                  chunk_regrips=chunk["regrip_count"],
                  instruction_symbols=sum(_recipe_symbols(case.recipe)
                                          for stage in stages for case in stage.cases),
                  stage_count=len(method.stages),
                  max_case_count=max((stage.case_count for stage in method.stages), default=0))
    return result


@dataclass(frozen=True)
class _Word:
    permutation: tuple[int, ...]
    turns: tuple[str, ...]
    factors: tuple[HumanMacroRecipe, ...]

    @property
    def key(self):
        return (len(self.turns), sum(2 if move.endswith("2") else 1 for move in self.turns),
                len(self.factors), tuple(factor.render() for factor in self.factors))

    @property
    def recipe(self):
        # Adjacent calls of the exact same body are learned as powers. This
        # compression changes notation only, never the physical word.
        result = []
        for factor in self.factors:
            body, exponent = ((factor.children[0], factor.exponent)
                              if factor.kind == "power" else (factor, 1))
            if result:
                previous = result[-1]
                old_body, old_exponent = ((previous.children[0], previous.exponent)
                    if previous.kind == "power" else (previous, 1))
                if old_body == body:
                    result.pop()
                    if old_exponent + exponent:
                        result.append(HumanMacroRecipe.power(body, old_exponent + exponent))
                    continue
            result.append(factor)
        return result[0] if len(result) == 1 else HumanMacroRecipe.sequence(*result)


def _extend(word, factor):
    return _Word(_then(word.permutation, factor.permutation),
                 tuple(_simplified_moves((*word.turns, *factor.turns)).split()),
                 (*word.factors, *factor.factors))


class _Context:
    def __init__(self, baseline, loops, settings, templates):
        self.baseline, self.loops, self.settings = baseline, loops, settings
        self.actions = {p: baseline.inventory.action(p) for p in sorted(baseline._permutations)}
        self.rotations = ("", *bandage_symmetries(baseline.reference_shape)) if settings["allow_symmetry"] else ("",)
        self.lengths = tuple((g.id, g.htm_length) for g in baseline.generators)
        self.macros, self.seed_ids, self.baseline_recipes = self._definitions(templates)
        self.by_id = {macro.id: macro for macro in self.macros}
        self.word_pools, self.edges = {}, {}
        self.dictionary_cache = {}
        self.search = defaultdict(int, physical_words_examined=0,
                                  physical_depths_completed=0, physical_word_budget_hits=0)
        self.all_features = tuple(BlockFeature(kind, block.cells)
            for kind in ("place_block", "solve_block") for block in baseline.inventory.blocks)
        self.blocks = {block.cells: i for i, block in enumerate(baseline.inventory.blocks)}

    def _definitions(self, templates):
        macros, by_word, originals = [], {}, {}
        records = {g.id: g for g in self.baseline.generators}

        def add(algorithm):
            _require(algorithm._inventory.root_shape == self.baseline.reference_shape,
                     "template refers to a different reference shape")
            expression = algorithm.expression
            witness = expression.expanded_moves(self.baseline.generators,
                max_expanded_moves=max(1, _expression_bound(expression, records)))
            replay = State(self.baseline.reference_shape).apply(algorithm.turn_sequence)
            _require(expression.evaluate(self.baseline.generators) == algorithm.permutation and
                     replay.shape == self.baseline.reference_shape and
                     replay.sticker_permutation == algorithm.permutation,
                     "template word disagrees with its legal root-loop proof")
            word = _simplified_moves(algorithm.turn_sequence.split())
            if _simplified_moves(witness.split()) != algorithm.turn_sequence:
                expression = LoopExpression.turns(word, expression)
            inverse = _inverse_moves(word)
            canonical, sign = (word, 1) if word <= inverse else (inverse, -1)
            if canonical not in by_word:
                identifier = f"M{len(macros) + 1}"
                by_word[canonical] = identifier
                macros.append(HumanRepertoireMacro(identifier, LoopAlgorithm(identifier,
                    expression if sign == 1 else LoopExpression.power(expression, -1),
                    algorithm.permutation if sign == 1 else _inverse(algorithm.permutation),
                    canonical, self.baseline.inventory, self.lengths, self.baseline.generators)))
            return HumanMacroRecipe.power(HumanMacroRecipe.macro(by_word[canonical]), sign)

        seeds = set()
        for generator in self.baseline.generators:
            recipe = add(LoopAlgorithm("seed", LoopExpression.loop(generator.id),
                generator.permutation, generator.turn_sequence, self.baseline.inventory,
                self.lengths, self.baseline.generators))
            seeds.update(recipe.macro_ids)
        for algorithm in self.baseline.algorithms:
            originals[algorithm.id] = add(algorithm)
        # Baseline names precede optional additions so its shared dictionary
        # is independently reproducible without retaining discarded templates.
        for algorithm in templates:
            _require(algorithm.permutation in self.baseline._permutations and
                     algorithm.permutation != _IDENTITY, "template is outside the complete root group")
            seeds.update(add(algorithm).macro_ids)
        return tuple(macros), frozenset(seeds), originals

    def dictionary(self, macros):
        key = tuple(macro.id for macro in macros)
        if key not in self.dictionary_cache:
            self.dictionary_cache[key] = _dictionary(self.baseline.reference_shape, macros,
                                                     self.settings["chunk_options"])
        return self.dictionary_cache[key]

    def alphabet(self, available):
        alphabet, seen = [], set()
        for identifier in sorted(available):
            body = HumanMacroRecipe.macro(identifier)
            for rotation in self.rotations:
                rotated = HumanMacroRecipe.rotated(rotation, body) if rotation else body
                for exponent in (1, -1):
                    recipe = HumanMacroRecipe.power(rotated, exponent)
                    algorithm = _build_algorithm(recipe, self.macros, self.baseline, "variant")
                    key = algorithm.permutation, algorithm.turn_sequence
                    if key in seen:
                        continue
                    seen.add(key)
                    _require(algorithm.permutation in self.baseline._permutations,
                             "template symmetry leaves the complete root group")
                    alphabet.append(_Word(algorithm.permutation,
                                          tuple(algorithm.turn_sequence.split()), (recipe,)))
        return tuple(alphabet)

    def words(self, available):
        """Complete additive witnesses plus a separately bounded physical beam."""
        from .computation import checkpoint
        available = frozenset(available)
        if available in self.word_pools:
            return self.word_pools[available]
        alphabet = self.alphabet(available)
        identity = _Word(_IDENTITY, (), ())
        # Distances use additive macro HTM. Boundary cancellation therefore
        # cannot invalidate Dijkstra's complete finite coverage fallback.
        best = {_IDENTITY: identity}
        distances = {_IDENTITY: (0, 0, ())}
        queue = [(distances[_IDENTITY], _IDENTITY)]
        expanded = 0
        while queue:
            if expanded % 128 == 0:
                checkpoint("template_vocabulary", vertices=expanded)
            expanded += 1
            distance, permutation = heappop(queue)
            if distance != distances[permutation]:
                continue
            for factor in alphabet:
                successor = _extend(best[permutation], factor)
                following = (distance[0] + len(factor.turns), distance[1] + 1,
                             (*distance[2], factor.factors[0].render()))
                if successor.permutation not in distances or following < distances[successor.permutation]:
                    distances[successor.permutation] = following
                    best[successor.permutation] = successor
                    heappush(queue, (following, successor.permutation))
        if frozenset(best) != self.baseline._permutations:
            self.search["unreachable_vocabularies"] += 1
            self.word_pools[available] = None
            return None
        self.search["complete_vocabularies"] += 1
        physical = dict(best)
        frontier = (identity,)
        examined, depths = 0, 0
        for depth in range(1, self.settings["max_applications"] + 1):
            candidates = {}
            exhausted = False
            for word in frontier:
                checkpoint("template_physical_words", examined=examined)
                for factor in alphabet:
                    if examined >= self.settings["max_word_candidates"]:
                        exhausted = True
                        break
                    examined += 1
                    successor = _extend(word, factor)
                    if successor.key < physical[successor.permutation].key:
                        physical[successor.permutation] = successor
                    # Keep boundary alternatives; selecting only one word per
                    # effect loses useful cancellations with the next call.
                    key = successor.permutation, successor.turns[-1:]
                    previous = candidates.get(key)
                    if previous is None or successor.key < previous.key:
                        candidates[key] = successor
                if exhausted:
                    break
            if not exhausted:
                depths = depth
            frontier = tuple(sorted(candidates.values(), key=lambda word: word.key)
                             [:self.settings["max_word_frontier"]])
            if exhausted or not frontier:
                break
        self.search["physical_words_examined"] += examined
        self.search["physical_depths_completed"] += depths
        self.search["physical_word_budget_hits"] += int(examined >= self.settings["max_word_candidates"])
        result = {"additive": best, "physical": physical}
        self.word_pools[available] = result
        return result

    def edge(self, current, feature):
        key = current, feature
        if key in self.edges:
            return self.edges[key]
        block = self.blocks[feature.cells]
        solved = _observe(self.actions[_IDENTITY], block, feature.kind)
        fibers = defaultdict(list)
        for permutation in sorted(current):
            fibers[_observe(self.actions[permutation], block, feature.kind)].append(permutation)
        if len(fibers) == 1:
            self.edges[key] = None
            return None
        target = frozenset(fibers[solved])
        before = _fixed_features(self.baseline.inventory, self.actions, current)
        after = _fixed_features(self.baseline.inventory, self.actions, target)
        implied = tuple(f for f in after if f not in before and f != feature)
        stage = HumanMethodStage(1, feature, block, self.baseline.inventory.blocks[block].name,
            len(current), len(target), solved, implied,
            tuple(HumanMethodCase(observation, None, members[0])
                  for observation, members in sorted(fibers.items())))
        self.edges[key] = stage, target
        return self.edges[key]

    def chain(self, features, *, complete=False):
        current, stages = self.baseline._permutations, []
        for feature in features:
            edge = self.edge(current, feature)
            if edge is not None:
                stage, current = edge
                stages.append(replace(stage, number=len(stages) + 1))
        if complete:
            while current != frozenset((_IDENTITY,)):
                options = [self.edge(current, feature) for feature in self.all_features
                           if feature.kind == "solve_block"]
                stage, current = min((edge for edge in options if edge is not None),
                                     key=lambda edge: (edge[0].index, edge[0].block_index))
                stages.append(replace(stage, number=len(stages) + 1))
        return tuple(stages), current

    def automatic(self, strategy):
        current, features = self.baseline._permutations, []
        kinds = ("place_block", "solve_block") if strategy == "placement_then_orientation" else ("solve_block",)
        for kind in kinds:
            while True:
                options = [self.edge(current, feature) for feature in self.all_features if feature.kind == kind]
                options = [edge for edge in options if edge is not None]
                if not options:
                    break
                stage, current = min(options, key=lambda edge: (edge[0].index, edge[0].block_index))
                features.append(stage.feature)
        _require(current == frozenset((_IDENTITY,)), "automatic template chain does not terminate")
        return tuple(features)

    def policy(self, available, stages, family):
        pools = self.words(available)
        if pools is None:
            return None
        words = pools[family]
        current, policies = self.baseline._permutations, []
        for stage in stages:
            target = frozenset(p for p in current
                if _observe(self.actions[p], stage.block_index, stage.feature.kind) == stage.solved_observation)
            cases = []
            for original in stage.cases:
                if original.observation == stage.solved_observation:
                    cases.append(HumanRepertoireCase(original.observation, HumanMacroRecipe.sequence(),
                                                     None, stage.solved_observation, 0))
                    continue
                eligible = [word for permutation, word in words.items()
                            if permutation in current and _then(original.representative, permutation) in target]
                _require(bool(eligible), "complete template vocabulary leaves a stage case uncovered")
                selected = min(eligible, key=lambda word: word.key)
                fiber = tuple(p for p in current
                    if _observe(self.actions[p], stage.block_index, stage.feature.kind) == original.observation)
                _require(all(_then(p, selected.permutation) in target for p in fiber),
                         "template correction fails its complete case fiber")
                recipe = selected.recipe
                checked = _build_algorithm(recipe, self.macros, self.baseline, "case")
                _require(checked.turn_sequence == " ".join(selected.turns) and
                         checked.permutation == selected.permutation, "template word/recipe disagreement")
                cases.append(HumanRepertoireCase(original.observation, recipe, recipe,
                                                 stage.solved_observation, len(selected.turns)))
            policies.append(tuple(cases))
            current = target
        _require(current == frozenset((_IDENTITY,)), "template policies leave a terminal subgroup")
        return tuple(policies)

    def fallback(self):
        algorithms = {a.id: a for a in self.baseline.algorithms}
        return tuple(tuple(HumanRepertoireCase(case.observation,
            self.baseline_recipes[case.algorithm_id] if case.algorithm_id else HumanMacroRecipe.sequence(),
            self.baseline_recipes[case.algorithm_id] if case.algorithm_id else None,
            stage.solved_observation, algorithms[case.algorithm_id].htm_length if case.algorithm_id else 0)
            for case in stage.cases) for stage in self.baseline.stages)

    def compile(self, stages, policies, strategy="manual"):
        skeleton = replace(self.baseline, stages=stages, strategy=strategy, skipped_features=())
        method, macros, rules, metrics = _compile_policies(skeleton, self.macros, policies,
            self.actions, _stage_groups(skeleton, self.actions), self.loops)
        dictionary = self.dictionary(macros)
        return method, macros, rules, _augment_metrics(metrics, method, rules, dictionary), dictionary


def _dominates(first, second):
    return (all(first[k] <= second[k] for k in _DIMENSIONS) and
            any(first[k] < second[k] for k in _DIMENSIONS))


def template_human_repertoire(initial, *, strategy="fully_solve_each_block", features=None,
                              preference="memory", allow_symmetry=True, select_chain=None,
                              templates=(), max_trials=16, max_applications=6,
                              max_word_candidates=100000, max_word_frontier=2000,
                              beam_width=3, max_chain_expansions=None, max_chain_methods=8,
                              max_cost_ratio=1.0, chunk_options=None,
                              max_group_elements=None, gap_executable="gap", timeout=None, root=None,
                              backend="explicit", dictionary=None, dictionary_options=None,
                              discovery_options=None, optimization_seconds=None,
                              max_optimization_work=None, progress=None):
    """Build a certified guide with shared optional quality-search limits.

    ``backend='auto'`` routes using exact group order, loop and witness workload.
    Explicit backend selections and supplied method chains are preserved.
    ``optimization_seconds`` and ``max_optimization_work`` apply across all
    optional passes after a complete baseline is certified. A cutoff returns
    the best retained complete policy; mandatory fallback construction and
    validation are outside that allowance. ``timeout`` remains a per-GAP cap.
    ``progress`` receives phase/status dictionaries, including baseline and
    completion events. None preserves the existing unlimited quality budget.
    """
    from .computation import Computation, OptimizationBudgetExceeded, current_computation
    from .preparation import route_preparation
    if backend not in ("explicit", "symbolic", "auto"):
        raise ValueError("backend must be explicit, symbolic or auto")
    if backend == "auto":
        # Automatic routing must not launch analysis before ordinary argument
        # errors have been rejected. Backend-specific checks still follow it.
        if preference not in _PREFERENCES:
            raise ValueError("preference must be memory, execution or recognition")
        if type(allow_symmetry) is not bool or (select_chain is not None and type(select_chain) is not bool):
            raise TypeError("allow_symmetry and select_chain must be booleans (select_chain may be None)")
        budgets = dict(max_trials=max_trials, max_applications=max_applications,
                       max_word_candidates=max_word_candidates, max_word_frontier=max_word_frontier,
                       beam_width=beam_width, max_chain_expansions=max_chain_expansions,
                       max_chain_methods=max_chain_methods)
        for name, value in budgets.items():
            if name == "max_chain_expansions" and value is None:
                continue
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < (1 if name in ("beam_width", "max_word_frontier") else 0):
                raise ValueError(f"invalid template-search budget: {name}")
        if type(max_cost_ratio) not in (int, float) or not isfinite(max_cost_ratio) or max_cost_ratio < 1:
            raise ValueError("max_cost_ratio must be finite and at least one")
        if chunk_options is not None and not isinstance(chunk_options, dict):
            raise TypeError("chunk_options must be a dictionary or None")
        if set(chunk_options or {}) - set(_CHUNK_OPTIONS):
            raise ValueError("unknown chunk option")
        chunks = {**_CHUNK_OPTIONS, **(chunk_options or {})}
        for name, value in chunks.items():
            if type(value) is not int:
                raise TypeError(f"chunk {name} must be an integer")
            if value < (2 if name in ("min_chunk_length", "max_chunk_length") else 0):
                raise ValueError(f"invalid chunk budget: {name}")
        if chunks["min_chunk_length"] > chunks["max_chunk_length"]:
            raise ValueError("minimum chunk length exceeds maximum")
        templates = tuple(templates)
        if any(not isinstance(template, LoopAlgorithm) for template in templates):
            raise TypeError("templates must contain witnessed LoopAlgorithms")
        from .preparation import validate_search_inputs, validate_stage_inputs
        features = validate_stage_inputs(strategy, features)
        validate_search_inputs(discovery_options, dictionary, dictionary_options)
    options = dict(strategy=strategy, features=features, preference=preference,
        allow_symmetry=allow_symmetry, select_chain=select_chain, templates=templates,
        max_trials=max_trials, max_applications=max_applications, max_word_candidates=max_word_candidates,
        max_word_frontier=max_word_frontier, beam_width=beam_width,
        max_chain_expansions=max_chain_expansions, max_chain_methods=max_chain_methods,
        max_cost_ratio=max_cost_ratio, chunk_options=chunk_options, max_group_elements=max_group_elements,
        gap_executable=gap_executable, timeout=timeout, root=root, backend=backend,
        dictionary=dictionary, dictionary_options=dictionary_options, discovery_options=discovery_options)
    # Nested preparation shares the same counters and deadline; it cannot
    # silently buy another allowance for a second chain or template pass.
    if current_computation() is not None:
        if backend == "auto":
            if isinstance(initial, HumanMethod):
                options["backend"] = initial.backend
            else:
                initial, options["backend"] = route_preparation(initial,
                    gap_executable=gap_executable, timeout=timeout, root=root,
                    max_group_elements=max_group_elements)
        return _template_human_repertoire(initial, **options)
    context = Computation(optimization_seconds=optimization_seconds,
                          max_optimization_work=max_optimization_work, progress=progress)
    context.method_preference = "recognition" if preference == "recognition" else "execution"
    with context.activate():
        if backend == "auto":
            if isinstance(initial, HumanMethod):
                options["backend"] = initial.backend
            else:
                initial, options["backend"] = route_preparation(initial,
                    gap_executable=gap_executable, timeout=timeout, root=root,
                    max_group_elements=max_group_elements)
        try:
            result = _template_human_repertoire(initial, **options)
        except OptimizationBudgetExceeded:
            if context.best_repertoire is not None:
                result = context.best_repertoire
            elif context.best_method is not None:
                # Finalize a complete portable guide from the last certified
                # policy without starting fresh dictionary/chain/chunk mining.
                context.event("fallback", "started")
                with context.suspend():
                    result = _template_human_repertoire(context.best_method,
                        preference=preference, allow_symmetry=allow_symmetry,
                        select_chain=False, backend=context.best_method.backend,
                        max_trials=0, max_applications=0, max_word_candidates=0,
                        max_chain_expansions=0, max_chain_methods=0,
                        max_cost_ratio=max_cost_ratio,
                        chunk_options={"max_candidates": 0, "max_chunks": 0, "max_word_moves": 0})
            else:
                # Initial certification is deliberately outside quality search;
                # this branch cannot turn an incomplete proof into a guide.
                raise
        return context.finish(result)


def _template_human_repertoire(initial, *, strategy="fully_solve_each_block", features=None,
                              preference="memory", allow_symmetry=True, select_chain=None,
                              templates=(), max_trials=16, max_applications=6,
                              max_word_candidates=100000, max_word_frontier=2000,
                              beam_width=3, max_chain_expansions=None, max_chain_methods=8,
                              max_cost_ratio=1.0, chunk_options=None,
                              max_group_elements=None, gap_executable="gap", timeout=None, root=None,
                              backend="explicit", dictionary=None, dictionary_options=None,
                              discovery_options=None):
    """Build a complete guide using selected templates, regrips and shared pieces.

    Shape/analysis/plan inputs compare both automatic chains and bounded mixed
    feature chains in the actual taught vocabulary. A complete supplied method
    retains its chain unless ``select_chain=True``. Its exact physical policy
    is always an eligible fallback. ``templates`` adds witnessed LoopAlgorithms
    to the original-loop seeds; their proofs use the same hidden witness library.

    Group closure and every complete observation fiber are checked without
    quality-search caps. Additive Dijkstra supplies complete vocabulary-specific
    corrections; a bounded physical beam then seeks boundary cancellations.
    Whole-method mean and worst HTM may not exceed the exact input fallback by
    ``max_cost_ratio``. The Pareto comparison also scores shared chunk definitions,
    case instructions and recognition counts. No global quality claim is made.
    Physical-word budgets apply separately to each trial vocabulary; the saved
    search counters report totals across all trial vocabularies.

    ``backend="symbolic"`` prepares a dictionary-aware certified chain without
    enumerating its group, then shares repeated witnessed bodies and typed
    physical chunks. A supplied symbolic method follows this path automatically
    and needs no GAP. Its physical case corrections stay unchanged. Here
    ``max_trials`` bounds accepted greedy body rounds, ``max_word_frontier``
    bounds their proposal pool, ``max_word_candidates`` bounds inspected
    expression nodes, and ``max_applications`` bounds eligible body expression
    depth. Complete fallback words are retained independently of these caps.
    The default chain expansion budget is 64 for symbolic and 12 for explicit.
    """
    supplied = isinstance(initial, HumanMethod)
    if backend not in ("explicit", "symbolic"):
        raise ValueError("backend must be explicit or symbolic")
    if backend == "symbolic" or (supplied and initial.backend == "symbolic"):
        from .symbolic_template_repertoire import symbolic_template_human_repertoire
        return symbolic_template_human_repertoire(initial, strategy=strategy, features=features,
            preference=preference, allow_symmetry=allow_symmetry, select_chain=select_chain,
            templates=templates, max_trials=max_trials, max_applications=max_applications,
            max_word_candidates=max_word_candidates, max_word_frontier=max_word_frontier,
            beam_width=beam_width, max_chain_expansions=64 if max_chain_expansions is None else max_chain_expansions,
            max_chain_methods=max_chain_methods, max_cost_ratio=max_cost_ratio,
            chunk_options=chunk_options, max_group_elements=max_group_elements,
            gap_executable=gap_executable, timeout=timeout, root=root, dictionary=dictionary,
            dictionary_options=dictionary_options, discovery_options=discovery_options)
    if dictionary is not None or dictionary_options is not None or discovery_options is not None:
        raise ValueError("dictionary and discovery options require backend='symbolic'")
    if max_chain_expansions is None:
        max_chain_expansions = 12
    if preference not in _PREFERENCES:
        raise ValueError("preference must be memory, execution or recognition")
    if type(allow_symmetry) is not bool:
        raise TypeError("allow_symmetry must be a boolean")
    if select_chain is None:
        select_chain = not supplied
    if type(select_chain) is not bool:
        raise TypeError("select_chain must be a boolean or None")
    settings = dict(preference=preference, allow_symmetry=allow_symmetry, select_chain=select_chain,
                    max_trials=max_trials, max_applications=max_applications,
                    max_word_candidates=max_word_candidates, max_word_frontier=max_word_frontier,
                    beam_width=beam_width, max_chain_expansions=max_chain_expansions,
                    max_chain_methods=max_chain_methods, max_cost_ratio=max_cost_ratio)
    for name in _BUDGETS:
        value = settings[name]
        if type(value) is not int:
            raise TypeError(f"{name} must be an integer")
        if value < (1 if name in ("beam_width", "max_word_frontier") else 0):
            raise ValueError(f"invalid template-search budget: {name}")
    if type(max_cost_ratio) not in (int, float) or not isfinite(max_cost_ratio) or max_cost_ratio < 1:
        raise ValueError("max_cost_ratio must be finite and at least one")
    if chunk_options is not None and not isinstance(chunk_options, dict):
        raise TypeError("chunk_options must be a dictionary or None")
    if set(chunk_options or {}) - set(_CHUNK_OPTIONS):
        raise ValueError("unknown chunk option")
    settings["chunk_options"] = {**_CHUNK_OPTIONS, **(chunk_options or {})}
    for name, value in settings["chunk_options"].items():
        if type(value) is not int:
            raise TypeError(f"chunk {name} must be an integer")
        if value < (2 if name in ("min_chunk_length", "max_chunk_length") else 0):
            raise ValueError(f"invalid chunk budget: {name}")
    if settings["chunk_options"]["min_chunk_length"] > settings["chunk_options"]["max_chunk_length"]:
        raise ValueError("minimum chunk length exceeds maximum")
    templates = tuple(templates)
    if any(not isinstance(template, LoopAlgorithm) for template in templates):
        raise TypeError("templates must contain witnessed LoopAlgorithms")
    if max_group_elements is not None:
        if type(max_group_elements) is not int:
            raise TypeError("max_group_elements must be a positive integer or None")
        if max_group_elements <= 0:
            raise ValueError("max_group_elements must be positive")
    if root is not None and type(root) is not int:
        raise TypeError("root must be an integer vertex ID")
    if supplied:
        if initial.status != "completed":
            raise ValueError("template repertoire requires a complete method")
        if initial.backend == "symbolic":
            raise ValueError("template repertoire optimization currently requires the explicit backend; "
                             "use improve_human_method for a symbolic policy")
        if features is not None or strategy != "fully_solve_each_block":
            raise ValueError("a supplied method retains its own baseline features")
        if root is not None and root != initial.root_vertex:
            raise ValueError("root differs from the supplied method reference")
        if max_group_elements is not None and initial.group_order > max_group_elements:
            raise ValueError("template repertoire group exceeds max_group_elements")
        from .preparation import reference_loops
        loops = reference_loops(initial)
        baseline = _validate_method(initial, complete_loops=loops)
    else:
        plan = plan_human_stages(initial, strategy=strategy, features=features,
            max_group_elements=max_group_elements, gap_executable=gap_executable, timeout=timeout, root=root)
        if plan.status != "completed":
            raise ValueError(f"template repertoire requires a complete plan: {plan.reason}")
        loops, baseline = plan.analysis.loops, _compile_plan(plan)
    from .computation import (checkpoint, retain_method, report_progress,
                              retain_repertoire, current_computation)
    retain_method(baseline)
    report_progress("templates", "started", backend="explicit")
    context = _Context(baseline, loops, settings, templates)
    candidates, seen = [], {}

    def consider(stages, policies, source, method_strategy="manual"):
        if policies is None:
            return None
        signature = (tuple(stage.feature for stage in stages),
                     tuple(tuple(case.recipe for case in stage) for stage in policies))
        if signature in seen:
            return seen[signature]
        result = context.compile(stages, policies, method_strategy)
        candidate = (f"C{len(candidates) + 1}", source, *result)
        candidates.append(candidate)
        seen[signature] = candidate
        return candidate

    fallback = consider(baseline.stages, context.fallback(), "exact_baseline", baseline.strategy)
    before = _augment_metrics(_baseline_metrics(baseline, context.actions), baseline,
                               fallback[4], fallback[6])

    def admissible(candidate):
        metrics = candidate[5]
        return (metrics["total_htm"] <= before["total_htm"] * max_cost_ratio and
                metrics["worst_htm"] <= before["worst_htm"] * max_cost_ratio)

    def rank(candidate):
        return (*[candidate[5][key] for key in _PREFERENCES[preference]], candidate[0])

    def publish():
        eligible = [c for c in candidates if admissible(c)]
        frontier = [c for c in eligible if not any(_dominates(other[5], c[5]) for other in eligible)]
        selected = min(frontier, key=rank)
        metadata = {
            "basis": "templates", "construction": "symmetry_template_search", "settings": settings,
            "coverage": "certified", "human_reviewed": False, "exhaustive_repertoire_search": False,
            "physical_shortest_claim": False, "rotations": list(context.rotations),
            "chunk_dictionary": selected[6].to_dict(),
            "baseline_chunk_dictionary": fallback[6].to_dict(), "baseline_metrics": before,
            "selected_metrics": selected[5], "pareto_dimensions": _DIMENSIONS,
            "preference_orders": _PREFERENCES, "selected_id": selected[0],
            "frontier": [c[0] for c in frontier], "search": dict(context.search),
            "candidates": [{"id": c[0], "source": c[1], "metrics": c[5], "admissible": admissible(c)}
                           for c in candidates],
        }
        repertoire = HumanRepertoire(baseline, selected[2], selected[3], selected[4],
                                     json.dumps(metadata, sort_keys=True, allow_nan=False))
        result = _validate_repertoire(repertoire, complete_loops=loops)
        retain_repertoire(result)
        return result

    computation = current_computation()
    snapshots = (computation is not None and not computation._suspended
                 and (computation.seconds is not None or computation.limit is not None))
    if snapshots:
        publish()

    chains = [("input", baseline.stages, baseline.strategy)]
    if select_chain:
        for name in ("placement_then_orientation", "fully_solve_each_block"):
            stages, _ = context.chain(context.automatic(name))
            if tuple(s.feature for s in stages) not in {tuple(s.feature for s in chain[1]) for chain in chains}:
                chains.append((name, stages, name))
    available = context.seed_ids

    def evaluate(identifiers, source, stage_choices=chains):
        checkpoint("template_trial", source=source)
        if context.words(identifiers) is None:
            return ()
        found = []
        for name, stages, method_strategy in stage_choices:
            for family in ("additive", "physical"):
                candidate = consider(stages, context.policy(identifiers, stages, family),
                                     f"{source}:{name}:{family}", method_strategy)
                if candidate is not None:
                    found.append(candidate)
        if snapshots:
            publish()
        return tuple(found)

    # Legacy zero-search settings still compile the complete vocabulary's
    # additive policies. A budget-cutoff finalizer keeps the exact saved policy.
    if computation is None or not computation._suspended:
        evaluate(available, "initial")
    # Symmetry variants precede every closure and deletion trial. Removing a
    # template therefore removes its entire orbit, not an individual regrip.
    while available and context.search["trials_examined"] < max_trials:
        checkpoint("template_deletion")
        removed = False
        eligible_current = [c for c in candidates if admissible(c)]
        current_rank = rank(min(eligible_current, key=rank))
        for identifier in sorted(available, key=lambda i: (-context.by_id[i].algorithm.htm_length, i)):
            if context.search["trials_examined"] >= max_trials:
                break
            context.search["trials_examined"] += 1
            trial = available - {identifier}
            found = [c for c in evaluate(trial, f"remove:{identifier}") if admissible(c)]
            if found and min(rank(c) for c in found) <= current_rank:
                available = trial
                context.search["accepted_deletions"] += 1
                removed = True
                break
        if not removed:
            break

    # Score complete rollouts in this very dictionary. Mixed-feature search
    # uses no algorithm pool whose words are rebuilt after stage selection.
    if select_chain and context.words(available) is not None:
        beam, complete_seen = [()], {tuple(s.feature for s in chain[1]) for chain in chains}
        expanded = published = 0
        while beam and expanded < max_chain_expansions and published < max_chain_methods:
            checkpoint("template_chain")
            following = []
            for prefix in beam:
                if expanded >= max_chain_expansions or published >= max_chain_methods:
                    break
                _, current = context.chain(prefix)
                if current == frozenset((_IDENTITY,)):
                    continue
                expanded += 1
                for feature in context.all_features:
                    if context.edge(current, feature) is None:
                        continue
                    next_prefix = (*prefix, feature)
                    stages, _ = context.chain(next_prefix, complete=True)
                    features_key = tuple(s.feature for s in stages)
                    found = evaluate(available, "mixed", (("mixed", stages, "manual"),))
                    eligible = [c for c in found if admissible(c)]
                    if eligible:
                        following.append((rank(min(eligible, key=rank)), next_prefix))
                        if features_key not in complete_seen:
                            complete_seen.add(features_key)
                            published += 1
                    if published >= max_chain_methods:
                        break
            following.sort(key=lambda entry: (entry[0], tuple((f.kind, f.cells) for f in entry[1])))
            beam = [prefix for _, prefix in following[:beam_width]]
        context.search["chain_nodes_expanded"] = expanded
        context.search["additional_chains_evaluated"] = published
    result = publish()
    report_progress("templates", "completed", backend="explicit", macros=len(result.macros))
    return result


def _validate_template_metadata(repertoire, actual, before):
    """Recheck executable dictionaries and saved selection without rerunning search."""
    from .human_chunks import ChunkDictionary
    metadata = repertoire.metadata
    fields = {"basis", "construction", "settings", "coverage", "human_reviewed",
              "exhaustive_repertoire_search", "physical_shortest_claim", "rotations",
              "chunk_dictionary", "baseline_chunk_dictionary", "baseline_metrics", "selected_metrics", "pareto_dimensions",
              "preference_orders", "selected_id", "frontier", "search", "candidates"}
    from .computation import validate_computation_metadata
    validate_computation_metadata(metadata)
    _require(set(metadata) - {"computation"} == fields and metadata["basis"] == "templates" and
             metadata["construction"] == "symmetry_template_search" and metadata["coverage"] == "certified"
             and metadata["human_reviewed"] is False and metadata["exhaustive_repertoire_search"] is False
             and metadata["physical_shortest_claim"] is False, "invalid template repertoire metadata")
    settings = metadata["settings"]
    _require(isinstance(settings, dict) and set(settings) ==
             {"preference", "allow_symmetry", "select_chain", "max_cost_ratio", "chunk_options", *_BUDGETS},
             "invalid template settings")
    _require(settings["preference"] in _PREFERENCES and type(settings["allow_symmetry"]) is bool and
             type(settings["select_chain"]) is bool and
             all(type(settings[k]) is int and settings[k] >=
                 (1 if k in ("beam_width", "max_word_frontier") else 0) for k in _BUDGETS),
             "invalid template budgets or preference")
    ratio = settings["max_cost_ratio"]
    _require(type(ratio) in (int, float) and isfinite(ratio) and ratio >= 1, "invalid template cost guard")
    chunk_options = settings["chunk_options"]
    _require(isinstance(chunk_options, dict) and set(chunk_options) == set(_CHUNK_OPTIONS) and
             all(type(value) is int and value >=
                 (2 if key in ("min_chunk_length", "max_chunk_length") else 0)
                 for key, value in chunk_options.items()) and
             chunk_options["min_chunk_length"] <= chunk_options["max_chunk_length"], "invalid chunk budgets")
    expected_rotations = ["", *bandage_symmetries(repertoire.method.reference_shape)] if settings["allow_symmetry"] else [""]
    _require(metadata["rotations"] == expected_rotations, "saved template symmetries disagree with the bandage")
    _require(repertoire.baseline.root_vertex == repertoire.method.root_vertex and
             repertoire.baseline.generators == repertoire.method.generators,
             "template projection changes its reference or hidden witness library")
    if not settings["select_chain"]:
        _require(tuple((s.feature, s.observations) for s in repertoire.baseline.stages) ==
                 tuple((s.feature, s.observations) for s in repertoire.method.stages),
                 "template repertoire changes a fixed stage chain")
    dictionary = ChunkDictionary.from_dict(metadata["chunk_dictionary"])

    def check_dictionary(record, macros):
        _require(record.reference_shape == repertoire.method.reference_shape and
                 dict(record.search_limits) == chunk_options and
                 tuple(identifier for identifier, _ in record.masters) == tuple(sorted(macro.id for macro in macros)),
                 "saved dictionary reference, limits or master IDs disagree with its templates")
        for macro in macros:
            _require(record.expand(macro.id) == macro.algorithm.turn_sequence,
                     "shared pieces do not reconstruct their template")

    # Grammar loading replays every guarded open path, local loop and complete
    # expansion and recalculates costs. Quality mining is deliberately absent:
    # portable certificates survive later improvements to the bounded miner.
    check_dictionary(dictionary, repertoire.macros)
    actual = _augment_metrics(actual, repertoire.method, repertoire.stages, dictionary)
    # Recover the exact input policy's shared inverse-word masters; no search
    # history or GAP execution is needed to remeasure its dictionary.
    context = _Context(repertoire.baseline, None, settings, ())
    used = {i for cases in context.fallback() for case in cases for i in case.recipe.macro_ids}
    baseline_macros = tuple(m for m in context.macros if m.id in used)
    baseline_dictionary = ChunkDictionary.from_dict(metadata["baseline_chunk_dictionary"])
    check_dictionary(baseline_dictionary, baseline_macros)
    baseline_rules = tuple(SimpleNamespace(cases=cases) for cases in context.fallback())
    before = _augment_metrics(before, repertoire.baseline, baseline_rules, baseline_dictionary)
    _require(_same_json(metadata["selected_metrics"], actual) and
             _same_json(metadata["baseline_metrics"], before), "saved template metrics disagree with verified policies")
    _require(_same_json(metadata["pareto_dimensions"], _DIMENSIONS) and
             _same_json(metadata["preference_orders"], _PREFERENCES), "invalid template objectives")
    candidates = metadata["candidates"]
    _require(isinstance(candidates, list) and candidates, "missing template search candidates")
    for index, candidate in enumerate(candidates, 1):
        _require(isinstance(candidate, dict) and set(candidate) == {"id", "source", "metrics", "admissible"}
                 and candidate["id"] == f"C{index}" and isinstance(candidate["source"], str),
                 "invalid template candidate")
        metrics = candidate["metrics"]
        _require(isinstance(metrics, dict) and set(metrics) == set(actual) and
                 all(type(value) in (int, float) and isfinite(value) and value >= 0 for value in metrics.values()),
                 "invalid template candidate metrics")
        admissible = metrics["total_htm"] <= before["total_htm"] * ratio and metrics["worst_htm"] <= before["worst_htm"] * ratio
        _require(type(candidate["admissible"]) is bool and candidate["admissible"] == admissible,
                 "template candidate disagrees with its cost guard")
    fallback_keys = ("states", "mean_htm", "worst_htm", "total_htm", "mean_qtm", "worst_qtm", "total_qtm",
                     "macro_count", "macro_definition_htm", "rule_count", "case_count_sum", "dictionary_score",
                     "chunk_definition_moves", "chunk_definition_symbols", "chunk_recipe_symbols", "chunk_regrips",
                     "instruction_symbols", "stage_count", "max_case_count")
    _require(candidates[0]["source"] == "exact_baseline" and
             _same_json({key: candidates[0]["metrics"][key] for key in fallback_keys},
                        {key: before[key] for key in fallback_keys}), "template fallback disagrees with its baseline")
    eligible = [c for c in candidates if c["admissible"]]
    frontier = [c for c in eligible if not any(_dominates(other["metrics"], c["metrics"]) for other in eligible)]
    _require(metadata["frontier"] == [c["id"] for c in frontier], "invalid template Pareto frontier")
    selected = min(frontier, key=lambda c: (*[c["metrics"][key] for key in _PREFERENCES[settings["preference"]]], c["id"]))
    _require(metadata["selected_id"] == selected["id"] and _same_json(selected["metrics"], actual),
             "template selection disagrees with the verified method")
    search = metadata["search"]
    _require(isinstance(search, dict) and all(type(value) is int and value >= 0 for value in search.values()),
             "invalid template search diagnostics")


__all__ = ["template_human_repertoire"]
