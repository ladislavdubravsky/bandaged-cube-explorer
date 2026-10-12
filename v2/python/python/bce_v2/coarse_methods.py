"""Compile a supplied coarse goal ladder using a strict witnessed palette.

The ambient symbolic chain proves the exact start domain. Its entry stages
are certificate scaffolding: a CoarseMethod executes only the requested
suffix, and every suffix correction must be a declared palette recipe.
No ordinary-cube geometry or cubie-array convention is used here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import cached_property
from heapq import heappop, heappush
import json
from pathlib import Path

from . import State
from .algorithm_palette import AlgorithmPalette, AlgorithmPaletteBody, AlgorithmPaletteSetup
from .computation import checkpoint
from .human_chains import BlockFeature, _feature_successor, _observation, _resolve_feature
from .human_methods import (HumanMethod, HumanMethodApplication, HumanMethodCase,
                            HumanMethodStage, HumanMethodStep, HumanRecognition,
                            _expression_bound, _inverse, _then, _validate_method)
from .loop_algorithms import AlgorithmLibrary, LoopExpression, _loops_from_records
from .preparation import prepare_analysis, reference_loops
from .symbolic_chains import plan_symbolic_stages


_IDENTITY = tuple(range(48))


def _domain_ladder(inventory, features):
    """Split pointwise conjunctions into small exact stabilizer steps.

    This avoids materializing the potentially enormous orbit of a completed
    assembly. Sequentially fixing its members proves the same conjunction.
    Anonymous orientation goals remain one invariant-region feature.
    """
    result = []
    for feature in features:
        block = _resolve_feature(inventory, feature)
        if feature.kind in ("solve_blocks", "place_blocks"):
            kind = "solve_block" if feature.kind == "solve_blocks" else "place_block"
            result.extend(BlockFeature(kind, inventory.blocks[index].cells) for index in block)
        else:
            result.append(feature)
    return tuple(dict.fromkeys(result))


def _palette_paths(stage, inventory, palette):
    """Shortest directed palette paths to the goal on a certified orbit."""
    available = tuple(sorted((algorithm for algorithm in palette.recipes
                              if algorithm.permutation in stage.group_before),
                             key=lambda algorithm: algorithm.id))
    observations = set(stage.observations)
    reverse = defaultdict(list)
    for algorithm in available:
        action = inventory.action(algorithm.permutation)
        for value in stage.observations:
            checkpoint("coarse_palette_transitions", stage=stage.number, work=1)
            image = _feature_successor(value, action, inventory, stage.block_index,
                                       stage.feature.kind)
            if image not in observations:
                raise ValueError("a protected palette action leaves the certified feature orbit")
            if image != value:
                reverse[image].append((value, algorithm.id, algorithm.htm_length))
    # Search reversed edges, without silently granting inverse-body permission.
    goal = stage.solved_observation
    best, paths, queue = {goal: (0, ())}, {goal: ()}, [(0, (), goal)]
    while queue:
        cost, path, destination = heappop(queue)
        if best[destination] != (cost, path):
            continue
        for source, identifier, weight in reverse[destination]:
            candidate = cost + weight, (identifier,) + path
            if source not in best or candidate < best[source]:
                best[source], paths[source] = candidate, candidate[1]
                heappush(queue, (*candidate, source))
    missing = observations - set(paths)
    if missing:
        raise ValueError(f"supplied palette does not cover stage {stage.number} "
                         f"({stage.feature.kind}): {len(missing)} of "
                         f"{len(observations)} observations have no correction")
    return paths


def _entry_correction(builder, representative, roots, identifier):
    expression = LoopExpression.power(representative.expression, -1)
    return replace(builder.build_algorithm(expression, max_expanded_moves=max(
        1, _expression_bound(expression, roots))), id=identifier)


def _algorithm_record(algorithm):
    from .human_method_io import _algorithm_to_dict
    return _algorithm_to_dict(algorithm)


def _palette_record(palette):
    record = {"bodies": [{"id": body.id, "allow_inverse": body.allow_inverse,
                         "algorithm": _algorithm_record(body.algorithm)}
                        for body in palette.bodies],
            "setups": [{"id": setup.id, "algorithm": _algorithm_record(setup.algorithm)}
                       for setup in palette.setups],
            "adjustments": [{"id": adjustment.id,
                             "algorithm": _algorithm_record(adjustment.algorithm)}
                            for adjustment in palette.adjustments]}
    if palette.max_derived_recipes:
        record["derivation"] = palette.derivation_settings
    return record


def _load_palette(record, method):
    from .human_method_io import _expression, _fields, _list, _string
    _fields(record, {"bodies", "setups", "adjustments"} |
            ({"derivation"} if "derivation" in record else set()), "coarse palette")
    if not method.generators:
        if any(record[name] for name in ("bodies", "setups", "adjustments")):
            raise ValueError("a palette without original witnesses must be empty")
        return AlgorithmPalette((), **record.get("derivation", {}))
    loops = _loops_from_records(method.generators)
    builder = AlgorithmLibrary(loops, (), (), ())
    roots = {g.id: g for g in method.generators}

    def algorithm(value):
        _fields(value, {"id", "expression", "permutation", "turn_sequence",
                        "htm_length", "qtm_length"}, "coarse palette algorithm")
        expression = _expression(value["expression"])
        built = replace(builder.build_algorithm(
            expression, max_expanded_moves=max(1, _expression_bound(expression, roots))),
                        id=_string(value["id"], "palette algorithm ID"))
        if _algorithm_record(built) != value:
            raise ValueError("saved palette algorithm disagrees with its physical witness")
        return built

    bodies = []
    for body in _list(record["bodies"], "coarse palette bodies"):
        _fields(body, {"id", "algorithm", "allow_inverse"}, "coarse palette body")
        bodies.append(AlgorithmPaletteBody(body["id"], algorithm(body["algorithm"]),
                                           body["allow_inverse"]))
    def setups(name):
        result = []
        for setup in _list(record[name], "coarse palette " + name):
            _fields(setup, {"id", "algorithm"}, "coarse palette setup")
            result.append(AlgorithmPaletteSetup(setup["id"], algorithm(setup["algorithm"])))
        return tuple(result)
    return AlgorithmPalette(tuple(bodies), setups("setups"), setups("adjustments"),
                            **record.get("derivation", {}))


@dataclass(frozen=True)
class CoarseMethod:
    """A complete palette policy over the exact declared start domain.

    ``ambient_method`` contains entry witnesses for portable certification.
    They are excluded from this method's public execution and taught bodies.
    ``stages`` and physical traces use suffix-local stage numbers.
    """

    ambient_method: HumanMethod = field(repr=False)
    domain_features: tuple[BlockFeature, ...]
    prefix_stage_count: int
    palette: AlgorithmPalette
    case_recipes: tuple[tuple[int, tuple[int, ...], tuple[str, ...]], ...]

    @property
    def reference_shape(self):
        return self.ambient_method.reference_shape

    @property
    def inventory(self):
        return self.ambient_method.inventory

    @property
    def generators(self):
        return self.ambient_method.generators

    @property
    def root_vertex(self):
        return self.ambient_method.root_vertex

    @cached_property
    def stages(self):
        return tuple(replace(stage, number=number) for number, stage in enumerate(
            self.ambient_method.stages[self.prefix_stage_count:], 1))

    @cached_property
    def algorithms(self):
        used = {case.algorithm_id for stage in self.stages for case in stage.cases}
        return tuple(a for a in self.ambient_method.algorithms if a.id in used)

    @cached_property
    def domain_group(self):
        chain = self.ambient_method._symbolic_chain
        return (chain.stages[self.prefix_stage_count - 1].group_after
                if self.prefix_stage_count else chain.group)

    @cached_property
    def _case_table(self):
        return {(stage.number, case.observation): case for stage in self.stages for case in stage.cases}

    @cached_property
    def _algorithm_table(self):
        return {algorithm.id: algorithm for algorithm in self.algorithms}

    @property
    def group_order(self):
        return self.domain_group.order

    @property
    def ambient_group_order(self):
        return self.ambient_method.group_order

    @property
    def status(self):
        return "completed"

    @property
    def coverage(self):
        return "certified"

    @property
    def coverage_scope(self):
        return "all_reference_group_states_satisfying_domain_features"

    @property
    def human_method_complete(self):
        return True

    @property
    def terminal_order(self):
        return 1

    @property
    def taught_body_ids(self):
        return tuple(sorted({body for _, _, recipe in self.case_recipes
                             for identifier in recipe
                             for body in self.palette.recipe_body_ids[identifier]}))

    def validate(self):
        """Recheck exact domain, complete policy and declared palette recipes."""
        _validate_method(self.ambient_method, complete_loops=reference_loops(self.ambient_method))
        return self._validate_domain_and_palette()

    def _validate_domain_and_palette(self):
        method = self.ambient_method
        if method.backend != "symbolic" or method.status != "completed":
            raise ValueError("a coarse method requires a complete symbolic ambient certificate")
        if (type(self.prefix_stage_count) is not int or
                not 0 <= self.prefix_stage_count <= len(method.stages)):
            raise ValueError("invalid coarse-method prefix stage count")
        domain = tuple(self.domain_features)
        if any(not isinstance(f, BlockFeature) for f in domain):
            raise TypeError("domain features must be BlockFeature instances")
        ladder = _domain_ladder(self.inventory, domain)
        prefix = method.stages[:self.prefix_stage_count]
        if any(stage.feature not in ladder for stage in prefix):
            raise ValueError("coarse-method entry prefix does not describe its domain")
        # Prefix constraints are a subset of the declared conjunction. If its
        # exact subgroup fixes every declaration, the two intersections agree,
        # including redundant features skipped or implied by earlier steps.
        identity = self.inventory.action(_IDENTITY)
        actions = tuple(self.inventory.action(g.permutation)
                        for g in self.domain_group.strong_generators)
        for feature in ladder:
            block = _resolve_feature(self.inventory, feature)
            solved = _observation(identity, block, feature.kind)
            if any(_observation(action, block, feature.kind) != solved for action in actions):
                raise ValueError("coarse-method prefix omits a declared domain feature")
        self.palette.validate(inventory=self.inventory, generators=self.generators,
                              group=method._symbolic_chain.group)
        recipes = {a.id: a for a in self.palette.recipes}
        algorithms = {a.id: a for a in self.algorithms}
        rows = {(number, observation): recipe for number, observation, recipe in self.case_recipes}
        expected = {(stage.number, case.observation) for stage in self.stages for case in stage.cases}
        if len(rows) != len(self.case_recipes) or set(rows) != expected:
            raise ValueError("coarse-method recipe declarations omit or duplicate cases")
        for stage in self.stages:
            for case in stage.cases:
                recipe = rows[stage.number, case.observation]
                if any(identifier not in recipes for identifier in recipe):
                    raise ValueError("coarse correction calls a recipe outside the supplied palette")
                expression = LoopExpression.sequence(*(recipes[i].expression for i in recipe))
                if case.algorithm_id is None:
                    if recipe or case.observation != stage.solved_observation:
                        raise ValueError("solved coarse case must use an empty palette recipe")
                elif algorithms[case.algorithm_id].expression != expression:
                    raise ValueError("coarse correction differs from its declared palette recipe")
        return self

    def recognize(self, state):
        if not isinstance(state, State):
            raise TypeError("recognition requires a colored State")
        if state.specification != self.reference_shape:
            return HumanRecognition("wrong_reference", reason="state has another reference specification")
        if state.shape != self.reference_shape:
            return HumanRecognition("shape_not_restored", reason="restore the reference shape first")
        if state.sticker_permutation not in self.domain_group:
            return HumanRecognition("outside_domain", reason="state does not satisfy the certified start domain")
        if state.is_solved:
            return HumanRecognition("solved")
        action = self.inventory.action(state.sticker_permutation)
        for stage in self.stages:
            observation = _observation(action, stage.block_index, stage.feature.kind)
            if observation != stage.solved_observation:
                case = self._case_table[stage.number, observation]
                return HumanRecognition("ready", stage.number, observation, case.algorithm_id)
        raise ValueError("coarse method leaves a nontrivial terminal residual")

    def _step(self, state, stage, observation):
        case = self._case_table[stage.number, observation]
        algorithm = self._algorithm_table[case.algorithm_id]
        after = state.apply(algorithm.turn_sequence)
        certified = self.ambient_method._symbolic_chain.stages[
            self.prefix_stage_count + stage.number - 1]
        if (after.shape != self.reference_shape or
                after.sticker_permutation != _then(state.sticker_permutation, algorithm.permutation) or
                after.sticker_permutation not in certified.group_after):
            raise ValueError("coarse correction fails physical replay or cumulative stage progress")
        return HumanMethodStep(stage.number, stage.feature, stage.block_name, observation,
                               algorithm.id, algorithm.expression, algorithm.turn_sequence, state, after)

    def next_step(self, state):
        recognition = self.recognize(state)
        if recognition.status == "solved":
            return None
        if recognition.status != "ready":
            raise ValueError(f"{recognition.status}: {recognition.reason}")
        return self._step(state, self.stages[recognition.stage_number - 1], recognition.observation)

    def apply(self, state):
        recognition = self.recognize(state)
        if recognition.status not in ("ready", "solved"):
            return HumanMethodApplication(recognition.status, state, (), recognition.reason)
        steps, current = [], state
        for stage in self.stages:
            action = self.inventory.action(current.sticker_permutation)
            observation = _observation(action, stage.block_index, stage.feature.kind)
            if observation != stage.solved_observation:
                step = self._step(current, stage, observation)
                steps.append(step)
                current = step.after
        if not current.is_solved:
            raise ValueError("coarse policy leaves a nontrivial terminal residual")
        return HumanMethodApplication("solved", current, tuple(steps))

    def example_state(self, stage_number, observation):
        if type(stage_number) is not int or not 1 <= stage_number <= len(self.stages):
            raise ValueError("stage_number is outside the coarse method")
        return self.ambient_method.example_state(self.prefix_stage_count + stage_number,
                                                 observation)

    def additive_costs(self):
        algorithms = {a.id: a for a in self.algorithms}
        result = {"scope": "uniform_declared_domain_before_boundary_cancellation", "exact": True}
        for metric in ("htm", "qtm"):
            mean, worst = Fraction(), 0
            for stage in self.stages:
                costs = [0 if case.algorithm_id is None else
                         getattr(algorithms[case.algorithm_id], metric + "_length")
                         for case in stage.cases]
                mean += Fraction(sum(costs), len(costs))
                worst += max(costs)
            result[metric] = {"mean": float(mean), "mean_numerator": mean.numerator,
                              "mean_denominator": mean.denominator, "worst": worst}
        return result

    def write_guide(self, path=None):
        """Render suffix cases with their exact starting-domain contract."""
        from .palette_render import palette_method_guide
        guide = palette_method_guide(self)
        if path is not None:
            Path(path).write_text(guide, encoding="utf-8")
        return guide

    def _write_case_guide(self, path=None):
        """Retain the exact flat policy as a computational audit view."""
        from .human_render import method_guide
        from .palette_render import execution_vocabulary, execution_vocabulary_lines, recipe_structure

        presentation = replace(self.ambient_method, group_order=self.group_order,
                               stages=self.stages, algorithms=self.algorithms,
                               skipped_features=())
        declarations, aliases = execution_vocabulary(
            self.palette, (path for _, _, path in self.case_recipes))
        structures = {}
        for number, observation, recipe_path in self.case_recipes:
            case = self._case_table[number, observation]
            if case.algorithm_id is not None:
                structures.setdefault(case.algorithm_id,
                    recipe_structure(self.palette, recipe_path, aliases))
        guide = method_guide(presentation, domain_features=self.domain_features,
                             algorithm_structures=structures)
        if declarations:
            definitions = execution_vocabulary_lines(declarations)
            guide = guide.replace("## Algorithms\n", "\n".join(definitions) + "\n## Algorithms\n", 1)
        if path is not None:
            Path(path).write_text(guide, encoding="utf-8")
        return guide

    def to_dict(self):
        from .human_method_io import _fingerprint
        record = {"format": "bce-v2-coarse-method", "version": 1,
                  "coverage_scope": self.coverage_scope,
                  "domain_features": [f.to_dict() for f in self.domain_features],
                  "prefix_stage_count": self.prefix_stage_count,
                  "domain_order": str(self.group_order),
                  "ambient_method": self.ambient_method.to_dict(),
                  "palette": _palette_record(self.palette),
                  "case_recipes": [{"stage": n, "observation": list(o), "recipe": list(r)}
                                   for n, o, r in self.case_recipes],
                  "taught_body_ids": list(self.taught_body_ids)}
        record["fingerprint"] = _fingerprint(record)
        return record

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path):
        self.to_json(path)
        return self.to_dict()

    @classmethod
    def from_dict(cls, record):
        from .human_method_io import _feature, _fields, _fingerprint, _integer, _list, _observation
        _fields(record, {"format", "version", "coverage_scope", "domain_features",
                         "prefix_stage_count", "domain_order", "ambient_method", "palette",
                         "case_recipes", "taught_body_ids", "fingerprint"}, "coarse method")
        if (record["format"] != "bce-v2-coarse-method" or type(record["version"]) is not int or
                record["version"] != 1 or record["fingerprint"] != _fingerprint(record)):
            raise ValueError("unsupported or corrupted coarse-method record")
        ambient = HumanMethod.from_dict(record["ambient_method"])
        rows = []
        for row in _list(record["case_recipes"], "coarse case recipes"):
            _fields(row, {"stage", "observation", "recipe"}, "coarse case recipe")
            rows.append((_integer(row["stage"], "coarse stage", 1),
                         _observation(row["observation"]),
                         tuple(_list(row["recipe"], "palette recipe"))))
        result = cls(ambient, tuple(_feature(f) for f in record["domain_features"]),
                     _integer(record["prefix_stage_count"], "prefix stage count"),
                     _load_palette(record["palette"], ambient), tuple(rows))._validate_domain_and_palette()
        if result.to_dict() != record:
            raise ValueError("saved coarse-method claims disagree with certified coverage")
        return result


def compile_coarse_method(initial, *, features, palette, domain_features=(),
                          gap_executable="gap", timeout=None):
    """Compile a generic prescribed ladder before selecting physical corrections.

    ``domain_features`` are entry assumptions, not entry instructions. Coverage
    is the full ambient stabilizer of those assumptions, independently of the
    group generated by the palette. Each requested stage must be completely
    covered by protected palette recipes or compilation fails explicitly.
    """
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    features, domain_features = tuple(features), tuple(domain_features)
    if any(not isinstance(f, BlockFeature) for f in (*features, *domain_features)):
        raise TypeError("features and domain_features must contain BlockFeature instances")
    analysis = prepare_analysis(initial, gap_executable=gap_executable, timeout=timeout)
    prefix_features = _domain_ladder(analysis.block_inventory, domain_features)
    plan = plan_symbolic_stages(analysis, strategy="manual",
                                features=(*prefix_features, *features),
                                gap_executable=gap_executable, timeout=timeout)
    return _compile_coarse_plan(plan, palette, domain_features)


def _compile_coarse_plan(plan, palette, domain_features, *, stage_recipes=None):
    """Compile a certified ladder, optionally retaining budget-selected paths.

    Search supplies complete palette paths rather than having this compiler
    replace them with locally cheapest paths using a larger taught vocabulary.
    The ordinary compiler continues to choose shortest unrestricted palette
    paths. Both routes perform the same endpoint and physical validation.
    """
    analysis = plan.analysis
    prefix_features = _domain_ladder(analysis.block_inventory, domain_features)
    prefix_count = sum(stage.feature in prefix_features for stage in plan.stages)
    if any(stage.feature not in prefix_features for stage in plan.stages[:prefix_count]):
        raise ValueError("symbolic planner reordered the declared start domain")
    palette.validate(inventory=plan.inventory, generators=plan._generators, group=plan.group)
    recipes = {a.id: a for a in palette.recipes}
    # Check strict palette coverage before expanding any computational witnesses.
    suffix = plan.stages[prefix_count:]
    if stage_recipes is None:
        paths = [_palette_paths(stage, plan.inventory, palette) for stage in suffix]
    else:
        paths = tuple(stage_recipes)
        if len(paths) != len(suffix):
            raise ValueError("budgeted policy omits certified stages")
        for stage, table in zip(suffix, paths):
            if set(table) != set(stage.observations):
                raise ValueError("budgeted policy omits certified observations")
            for observation, path in table.items():
                current = observation
                for identifier in path:
                    if identifier not in recipes:
                        raise ValueError("budgeted policy calls a recipe outside the supplied palette")
                    algorithm = recipes[identifier]
                    if algorithm.permutation not in stage.group_before:
                        raise ValueError("budgeted recipe does not preserve preceding goals")
                    current = _feature_successor(current, plan.inventory.action(algorithm.permutation),
                                                 plan.inventory, stage.block_index, stage.feature.kind)
                if current != stage.solved_observation:
                    raise ValueError("budgeted palette path does not reach its certified goal")
    loops = analysis.loops
    builder = AlgorithmLibrary(loops, (), (), ())
    roots = {g.id: g for g in loops.generators}
    stages, entry_algorithms, entry_by_effect = [], [], {}
    # Entry corrections carry the ambient certificate's finite witnesses.
    # Suffix transversals prove fibers but their computational corrections
    # need never be expanded: the palette supplies the executed words.
    for stage in plan.stages[:prefix_count]:
        cases = []
        for representative in stage.representatives:
            identifier = None
            if representative.observation != stage.solved_observation:
                correction = _inverse(representative.permutation)
                if correction not in entry_by_effect:
                    algorithm = _entry_correction(builder, representative, roots,
                                                   f"E{len(entry_algorithms) + 1}")
                    entry_algorithms.append(algorithm)
                    entry_by_effect[correction] = algorithm.id
                identifier = entry_by_effect[correction]
            cases.append(HumanMethodCase(representative.observation, identifier,
                                         representative.permutation))
        stages.append(HumanMethodStage(stage.number, stage.feature, stage.block_index,
                                       stage.block_name, stage.order_before, stage.order_after,
                                       stage.solved_observation, stage.implied_features, tuple(cases)))
    algorithms = []
    case_recipes, by_expression = [], {}
    for local_number, (stage, paths_for_stage) in enumerate(
            zip(plan.stages[prefix_count:], paths), 1):
        cases = []
        for representative in stage.representatives:
            path = paths_for_stage[representative.observation]
            case_recipes.append((local_number, representative.observation, path))
            identifier = None
            if path:
                expression = LoopExpression.sequence(*(recipes[i].expression for i in path))
                if expression not in by_expression:
                    algorithm = replace(builder.build_algorithm(expression, max_expanded_moves=max(
                        1, _expression_bound(expression, roots))), id=f"P{len(algorithms) + 1}")
                    algorithms.append(algorithm)
                    by_expression[expression] = algorithm.id
                identifier = by_expression[expression]
            cases.append(HumanMethodCase(representative.observation, identifier,
                                         representative.permutation))
        stages.append(HumanMethodStage(stage.number, stage.feature, stage.block_index,
                                       stage.block_name, stage.order_before, stage.order_after,
                                       stage.solved_observation, stage.implied_features, tuple(cases)))
    ambient = HumanMethod(plan.inventory.root_shape, plan.strategy, "completed", plan.group_order,
                          plan.quotient_order, plan.kernel_order, loops.root_vertex,
                          loops.generators, tuple(stages), (*entry_algorithms, *algorithms),
                          plan.initial_features, plan.skipped_features, None, None,
                          plan.gap_version, plan.inventory, plan.group, plan)
    return CoarseMethod(ambient, domain_features, prefix_count, palette,
                        tuple(case_recipes)).validate()


def load_coarse_method(path):
    """Load and independently certify a saved method without invoking GAP."""
    return CoarseMethod.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
