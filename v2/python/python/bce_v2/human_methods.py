"""Complete finite case policies compiled from reference-shape loops.

This is a computational baseline. It deliberately keeps the exact policy
separate from later searches for shorter, easier-to-remember algorithms.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

from . import Shape, State
from ._moves import _simplified_moves
from .block_actions import BlockInventory
from .computation import checkpoint
from .human_chains import (BlockFeature, _check_alignment_membership, _check_slot_invariance, _feature_name,
                           _feature_successor, _observation, _resolve_feature,
                           plan_human_stages)
from .isotropy import LoopGenerator, LoopGenerators
from .loop_algorithms import LoopAlgorithm, LoopExpression


_IDENTITY = tuple(range(48))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _then(first, second):
    return tuple(second[p] for p in first)


def _inverse(permutation):
    result = [0] * 48
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


def _observe(action, block, kind):
    return _observation(action, block, kind)


def _recognition_spec(inventory, stage):
    """Resolve independent observers; the goal remains an explicit projection.

    Requiring the goal among the observers is a deliberately sufficient
    recovery rule. It avoids treating a lucky representative as evidence
    that every state with the same recognition pattern has the same goal.
    """
    _require(isinstance(stage.recognition_features, tuple),
             "recognition features must be a tuple of block features")
    features = stage.recognition_features or (stage.feature,)
    _require(features and
             all(isinstance(feature, BlockFeature) for feature in features),
             "recognition features must be a nonempty tuple of block features")
    _require(len(set(features)) == len(features) and stage.feature in features,
             "recognition features must be distinct and explicitly include the stage goal")
    return tuple((feature, _resolve_feature(inventory, feature)) for feature in features)


def _recognition_observation(action, spec):
    return tuple(value for feature, block in spec
                 for value in _observe(action, block, feature.kind))


def _stage_observation(action, stage, inventory):
    """Read a case pattern, independently of the stage's committed goal."""
    return _recognition_observation(action, _recognition_spec(inventory, stage))


def _goal_observation(observation, inventory, stage):
    """Project a recognition pattern onto its explicitly included goal."""
    identity, offset = inventory.action(_IDENTITY), 0
    for feature, block in _recognition_spec(inventory, stage):
        size = len(_observe(identity, block, feature.kind))
        if feature == stage.feature:
            return observation[offset:offset + size]
        offset += size
    raise ValueError("recognition does not recover the stage goal")


def _recognition_inputs(plan, recognition):
    if recognition is None:
        return {}
    if not isinstance(recognition, Mapping):
        raise TypeError("recognition must map stage numbers to feature sequences")
    result = {}
    for number, features in recognition.items():
        if type(number) is not int or not 1 <= number <= len(plan.stages):
            raise ValueError("recognition stage number is outside the compiled plan")
        features = (features,) if isinstance(features, BlockFeature) else tuple(features)
        _require(bool(features), "recognition features must explicitly include the stage goal")
        # Skeleton stages intentionally commit only a goal. Resolve using a
        # method-stage view, without changing the planner's subgroup chain.
        stage = SimpleNamespace(feature=plan.stages[number - 1].feature,
                                recognition_features=features)
        _recognition_spec(plan.inventory, stage)
        result[number] = features
    return result


def _require_goal_only_recognition(method, operation):
    """Keep older policy optimizers from silently interpreting finer patterns."""
    _require(all(not stage.recognition_features or stage.recognition_features == (stage.feature,)
                 for stage in method.stages),
             f"{operation} does not yet support independent recognition features")


def _recognition_orbit(inventory, certified, stage):
    """Enumerate only the joint observation orbit, retaining physical members.

    Every observer has a well-defined action, so orbit closure covers all
    reachable patterns even when the preceding group itself is enormous.
    """
    spec = _recognition_spec(inventory, stage)
    identity = inventory.action(_IDENTITY)
    sizes = tuple(len(_observe(identity, block, feature.kind)) for feature, block in spec)
    actions = tuple((generator.permutation, inventory.action(generator.permutation))
                    for generator in certified.group_before.strong_generators)
    for feature, block in spec:
        _check_alignment_membership(feature, certified.group_before.contains)
        if feature.kind == "orient_slots":
            _check_slot_invariance((action for _, action in actions), block)
    solved = _recognition_observation(identity, spec)
    representatives, queue = {solved: _IDENTITY}, deque([solved])
    while queue:
        checkpoint("independent_recognition_orbit", stage=stage.number,
                   observations=len(representatives))
        observation = queue.popleft()
        for permutation, action in actions:
            offset, successor = 0, []
            for (feature, block), size in zip(spec, sizes):
                successor.extend(_feature_successor(observation[offset:offset + size],
                                                   action, inventory, block, feature.kind))
                offset += size
            successor = tuple(successor)
            if successor not in representatives:
                representatives[successor] = _then(representatives[observation], permutation)
                queue.append(successor)
    return representatives


def _fixed_features(inventory, actions, members):
    return tuple(BlockFeature(kind, block.cells)
                 for kind in ("place_block", "solve_block")
                 for i, block in enumerate(inventory.blocks)
                 if all(_observe(actions[p], i, kind) == _observe(actions[_IDENTITY], i, kind)
                        for p in members))


def _state_for_permutation(reference, permutation):
    """Decode a faithful physical action through the public colored importer."""
    facelets = list("".join(face * 9 for face in "URFDLB"))
    solved = tuple(facelets)
    points = tuple(i for i in range(54) if i % 9 != 4)
    for source, destination in enumerate(permutation):
        facelets[points[destination]] = solved[points[source]]
    return State.from_facelets("".join(facelets), reference)


def _expression_bound(expression, records):
    """Bound physical execution; literal provenance has a separate budget."""
    if expression.kind == "loop":
        return records[expression.generator_id].qtm_length
    if expression.kind == "turns":
        return len(expression.moves.split())
    sizes = tuple(_expression_bound(child, records) for child in expression.children)
    if expression.kind == "sequence":
        return sum(sizes)
    if expression.kind == "rotated":
        return sizes[0]
    if expression.kind == "power":
        return max(1, abs(expression.exponent)) * sizes[0]
    return 2 * sizes[0] + (2 if expression.kind == "commutator" else 1) * sizes[1]


@dataclass(frozen=True)
class HumanMethodCase:
    observation: tuple[int, ...]
    algorithm_id: str | None
    representative: tuple[int, ...]


@dataclass(frozen=True)
class HumanMethodStage:
    number: int
    feature: BlockFeature
    block_index: int | tuple[int, ...]
    block_name: str
    order_before: int
    order_after: int
    solved_observation: tuple[int, ...]
    implied_features: tuple[BlockFeature, ...]
    cases: tuple[HumanMethodCase, ...]
    recognition_features: tuple[BlockFeature, ...] = ()

    @property
    def index(self):
        return self.order_before // self.order_after

    @property
    def case_count(self):
        return len(self.cases)

    @property
    def observations(self):
        return tuple(case.observation for case in self.cases)


@dataclass(frozen=True)
class HumanRecognition:
    status: str
    stage_number: int | None = None
    observation: tuple[int, ...] | None = None
    algorithm_id: str | None = None
    reason: str | None = None

    def to_dict(self):
        return {"status": self.status, "stage_number": self.stage_number,
                "observation": None if self.observation is None else list(self.observation),
                "algorithm_id": self.algorithm_id, "reason": self.reason}


@dataclass(frozen=True)
class HumanMethodStep:
    stage_number: int
    feature: BlockFeature
    block_name: str
    observation: tuple[int, ...]
    algorithm_id: str
    expression: LoopExpression
    turn_sequence: str
    before: State
    after: State

    @property
    def qtm_length(self):
        return sum(2 if move.endswith("2") else 1 for move in self.turn_sequence.split())

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())

    def to_dict(self):
        return {"stage_number": self.stage_number, "feature": self.feature.to_dict(),
                "block_name": self.block_name, "observation": list(self.observation),
                "algorithm_id": self.algorithm_id, "expression": self.expression.to_dict(),
                "turn_sequence": self.turn_sequence, "htm_length": self.htm_length,
                "qtm_length": self.qtm_length, "before": self.before.hex_id,
                "after": self.after.hex_id}


@dataclass(frozen=True)
class HumanMethodApplication:
    status: str
    state: State
    steps: tuple[HumanMethodStep, ...]
    reason: str | None = None

    @property
    def turn_sequence(self):
        return _simplified_moves(move for step in self.steps for move in step.turn_sequence.split())

    def to_dict(self):
        return {"status": self.status, "reason": self.reason, "state": self.state.hex_id,
                "turn_sequence": self.turn_sequence, "steps": [step.to_dict() for step in self.steps]}


@dataclass(frozen=True)
class HumanMethod:
    reference_shape: Shape
    strategy: str
    status: str
    group_order: int
    quotient_order: int | None
    kernel_order: int | None
    root_vertex: int
    generators: tuple[LoopGenerator, ...]
    stages: tuple[HumanMethodStage, ...]
    algorithms: tuple[LoopAlgorithm, ...]
    initial_features: tuple[BlockFeature, ...]
    skipped_features: tuple[BlockFeature, ...]
    max_group_elements: int | None
    reason: str | None
    gap_version: str
    _inventory: BlockInventory = field(repr=False, compare=False)
    _permutations: object = field(repr=False, compare=False)
    _symbolic_chain: object | None = field(default=None, repr=False, compare=False)

    @property
    def inventory(self):
        return self._inventory

    @property
    def coverage(self):
        return "certified" if self.status == "completed" else "partial"

    @property
    def coverage_scope(self):
        return "all_reference_group_states" if self.status == "completed" else "none"

    @property
    def quality(self):
        return "computational_baseline"

    @property
    def human_method_complete(self):
        return self.status == "completed"

    @property
    def terminal_order(self):
        return 1 if self.status == "completed" else None

    @property
    def backend(self):
        return "symbolic" if self._symbolic_chain is not None else "explicit"

    def additive_costs(self):
        """Exact uniform-group costs before cancellation between stages.

        Deterministic goal coset tables give independent, uniformly distributed
        stage digits. Refined observers retain this calculation when correction
        effects and costs depend only on the goal coordinate. These are sums of
        stored case-word costs, before simplifying the concatenation.
        """
        from fractions import Fraction
        _require(self.status == "completed", "costs require a complete method")
        algorithms = {a.id: a for a in self.algorithms}
        for stage in self.stages:
            effects = defaultdict(set)
            for case in stage.cases:
                goal = _goal_observation(case.observation, self.inventory, stage)
                algorithm = None if case.algorithm_id is None else algorithms[case.algorithm_id]
                effects[goal].add((_IDENTITY, 0, 0) if algorithm is None else
                                  (algorithm.permutation, algorithm.htm_length,
                                   algorithm.qtm_length))
            _require(all(len(values) == 1 for values in effects.values()),
                     "exact additive costs require one correction effect and cost per goal observation")
        result = {"scope": "uniform_reference_group_before_boundary_cancellation", "exact": True}
        for metric in ("htm", "qtm"):
            means, worst = [], 0
            for stage in self.stages:
                costs = [0 if case.algorithm_id is None else
                         getattr(algorithms[case.algorithm_id], metric + "_length")
                         for case in stage.cases]
                means.append(Fraction(sum(costs), len(costs)))
                worst += max(costs)
            mean = sum(means, Fraction())
            result[metric] = {"mean": float(mean), "mean_numerator": mean.numerator,
                              "mean_denominator": mean.denominator, "worst": worst}
        return result

    def to_dict(self):
        from .human_method_io import method_to_dict
        return method_to_dict(self)

    def to_json(self, path=None):
        from .human_method_io import method_to_json
        return method_to_json(self, path)

    def save(self, path):
        self.to_json(path)
        return self.to_dict()

    @classmethod
    def from_dict(cls, record):
        from .human_method_io import method_from_dict
        return method_from_dict(record)

    def write_guide(self, path=None):
        from .human_render import method_guide
        guide = method_guide(self)
        if path is not None:
            Path(path).write_text(guide, encoding="utf-8")
        return guide

    def example_state(self, stage_number, observation):
        """Return a validated physical example of a compiled recognition case."""
        if isinstance(stage_number, bool) or not isinstance(stage_number, int):
            raise TypeError("stage_number must be an integer")
        if not 1 <= stage_number <= len(self.stages):
            raise ValueError("stage_number is outside the method")
        observation = tuple(observation)
        case = next((c for c in self.stages[stage_number - 1].cases if c.observation == observation), None)
        if case is None:
            raise ValueError("observation is not a case in that stage")
        return _state_for_permutation(self.reference_shape, case.representative)

    def recognize(self, state):
        """Read the first unfinished stage; never factor the supplied scramble."""
        if not isinstance(state, State):
            raise TypeError("recognition requires a colored State")
        if state.specification != self.reference_shape:
            return HumanRecognition("wrong_reference", reason="state has a different reference bandage specification")
        if state.shape != self.reference_shape:
            return HumanRecognition("shape_not_restored", reason="restore the reference shape before applying this method")
        if self.status != "completed":
            return HumanRecognition("method_incomplete", reason=self.reason)
        if state.sticker_permutation not in self._permutations:
            return HumanRecognition("unreachable", reason="colored residual is outside the complete reference-loop group")
        if state.is_solved:
            return HumanRecognition("solved")
        action = self.inventory.action(state.sticker_permutation)
        for stage in self.stages:
            goal = _observe(action, stage.block_index, stage.feature.kind)
            if goal != stage.solved_observation:
                observation = _stage_observation(action, stage, self.inventory)
                case = next((c for c in stage.cases if c.observation == observation), None)
                _require(case is not None and case.algorithm_id is not None,
                         "compiled method is missing a required case correction")
                return HumanRecognition("ready", stage.number, observation, case.algorithm_id)
        raise ValueError("compiled method reaches a nontrivial terminal residual")

    def next_step(self, state):
        """Return one verified correction, or None when already solved.

        Use recognize() or apply() to obtain structured precondition failures.
        """
        recognition = self.recognize(state)
        if recognition.status == "solved":
            return None
        if recognition.status != "ready":
            raise ValueError(f"{recognition.status}: {recognition.reason}")
        stage = self.stages[recognition.stage_number - 1]
        algorithm = next((a for a in self.algorithms if a.id == recognition.algorithm_id), None)
        _require(algorithm is not None, "compiled method refers to a missing algorithm")
        after = state.apply(algorithm.turn_sequence)
        _require(after.shape == self.reference_shape and
                 after.sticker_permutation == _then(state.sticker_permutation, algorithm.permutation),
                 "compiled correction fails physical replay")
        action = self.inventory.action(after.sticker_permutation)
        _require(all(_observe(action, prior.block_index, prior.feature.kind) == prior.solved_observation
                     for prior in self.stages[:stage.number]),
                 "compiled correction fails stage progress or protected features")
        return HumanMethodStep(stage.number, stage.feature, stage.block_name, recognition.observation,
                               algorithm.id, algorithm.expression, algorithm.turn_sequence, state, after)

    def apply(self, state):
        """Execute the precompiled case policy and retain its stage trace."""
        recognition = self.recognize(state)
        if recognition.status not in ("ready", "solved"):
            return HumanMethodApplication(recognition.status, state, (), recognition.reason)
        steps, current = [], state
        for _ in range(len(self.stages) + 1):
            step = self.next_step(current)
            if step is None:
                return HumanMethodApplication("solved", current, tuple(steps))
            _require(not steps or step.stage_number > steps[-1].stage_number,
                     "compiled policy does not make strictly increasing stage progress")
            steps.append(step)
            current = step.after
        raise ValueError("compiled policy did not terminate within its stage count")


def _validate_method(method, *, complete_loops=None):
    """Prove portable method coverage from legal leaves and complete native loops.

    The saved order only bounds enumeration; closure and native-loop coverage
    establish the actual group independently of a saved certification claim.
    """
    _require(method.status in ("completed", "limit_reached"), "unsupported method status")
    _require(method.strategy in ("placement_then_orientation", "fully_solve_each_block", "manual"),
             "unsupported method stage strategy")
    _require(method.inventory.root_shape == method.reference_shape, "method inventory has a different reference")
    _require(type(method.group_order) is int and method.group_order > 0, "invalid reference group order")
    if method.status == "limit_reached":
        _require(method.max_group_elements is not None and method.group_order > method.max_group_elements and
                 method.reason == "group_order_exceeds_limit" and not method.stages and not method.algorithms and
                 not method.generators and method.quotient_order is None and method.kernel_order is None and
                 not method.initial_features and not method.skipped_features,
                 "inconsistent method preflight stop")
        return replace(method, _permutations=frozenset())
    _require(method.reason is None and complete_loops is not None and
             complete_loops.root_shape == method.reference_shape, "complete loop provenance is required")
    if method._symbolic_chain is not None:
        return _validate_symbolic_method(method, complete_loops=complete_loops)
    _require(method.max_group_elements is None or method.group_order <= method.max_group_elements,
             "completed method exceeds its declared group-element limit")
    initial = State(method.reference_shape)
    _require(len({g.id for g in method.generators}) == len(method.generators), "duplicate original loop IDs")
    for generator in method.generators:
        _require(type(generator.id) is int and generator.id >= 0, "invalid original loop ID")
        replay = initial.apply(generator.moves)
        _require(replay.shape == method.reference_shape and replay.sticker_permutation == generator.permutation,
                 "original loop witness fails legal replay")
    alphabet = tuple(p for g in method.generators for p in (g.permutation, _inverse(g.permutation)))
    permutations, known = [_IDENTITY], {_IDENTITY}
    for element in permutations:
        for generator in alphabet:
            successor = _then(element, generator)
            if successor not in known:
                _require(len(known) < method.group_order, "closure exceeds the saved group order")
                known.add(successor)
                permutations.append(successor)
    _require(len(known) == method.group_order and
             all(g.permutation in known for g in complete_loops.generators),
             "saved generators do not cover the complete reference-loop group")
    actions = {p: method.inventory.action(p) for p in permutations}
    _require(all(a.to_permutation() == p for p, a in actions.items()), "unfaithful method block action")
    placements = {a.destinations for a in actions.values()}
    kernel = {p for p, a in actions.items() if a.destinations == actions[_IDENTITY].destinations}
    _require((len(placements), len(kernel)) == (method.quotient_order, method.kernel_order),
             "method placement/kernel orders are inconsistent")
    algorithms = {a.id: a for a in method.algorithms}
    records = {g.id: g for g in method.generators}
    _require(len(algorithms) == len(method.algorithms), "duplicate shared algorithm IDs")
    for algorithm in method.algorithms:
        _require(isinstance(algorithm.id, str) and bool(algorithm.id) and algorithm.permutation in known and
                 algorithm.permutation != _IDENTITY, "invalid shared correction algorithm")
        _require(algorithm._inventory.root_shape == method.reference_shape and
                 algorithm._generators == method.generators,
                 "algorithm refers to a different witness library")
        _require(algorithm.expression.evaluate(method.generators) == algorithm.permutation,
                 "algorithm expression disagrees with its full action")
        expression_moves = algorithm.expression.expanded_moves(
            method.generators, max_expanded_moves=max(1, _expression_bound(algorithm.expression, records)))
        _require(initial.apply(expression_moves).sticker_permutation == algorithm.permutation,
                 "algorithm expression fails physical replay")
        replay = initial.apply(algorithm.turn_sequence)
        _require(replay.shape == method.reference_shape and replay.sticker_permutation == algorithm.permutation,
                 "algorithm physical witness disagrees with its full action")
    current, used = known, set()
    fixed = _fixed_features(method.inventory, actions, current)
    _require(method.initial_features == fixed, "initial guaranteed features are inconsistent")
    for number, stage in enumerate(method.stages, 1):
        block = _resolve_feature(method.inventory, stage.feature)
        _check_alignment_membership(stage.feature, current.__contains__)
        if stage.feature.kind == "orient_slots":
            _check_slot_invariance((actions[p] for p in current), block)
        _require(stage.number == number and stage.block_index == block and
                 stage.block_name == _feature_name(method.inventory, block, stage.feature.kind),
                 "stage identity or reference block metadata is inconsistent")
        solved = _observe(actions[_IDENTITY], block, stage.feature.kind)
        spec = _recognition_spec(method.inventory, stage)
        for observed_feature, observed_block in spec:
            _check_alignment_membership(observed_feature, current.__contains__)
            if observed_feature.kind == "orient_slots":
                _check_slot_invariance((actions[p] for p in current), observed_block)
        fibers, goals = defaultdict(set), defaultdict(set)
        for p in current:
            fibers[_recognition_observation(actions[p], spec)].add(p)
            goals[_observe(actions[p], block, stage.feature.kind)].add(p)
        target = goals[solved]
        _require(stage.solved_observation == solved and stage.order_before == len(current) and
                 stage.order_after == len(target) and len(goals) > 1 and
                 len(current) == len(target) * len(goals), "stage order or solved observation is inconsistent")
        _require(stage.observations == tuple(sorted(fibers)), "stage cases omit, duplicate or reorder observations")
        recognition_target = fibers[_recognition_observation(actions[_IDENTITY], spec)]
        for case in stage.cases:
            fiber = fibers[case.observation]
            _require(case.representative in fiber, "case representative is outside its exact observation fiber")
            _require({_then(k, case.representative) for k in recognition_target} == fiber,
                     "case observation is not an exact right coset")
            if _goal_observation(case.observation, method.inventory, stage) == solved:
                _require(case.algorithm_id is None, "already-solved case must require no correction")
            else:
                _require(case.algorithm_id in algorithms, "case refers to a missing correction")
                algorithm = algorithms[case.algorithm_id]
                _require(algorithm.permutation in current and
                         all(_then(p, algorithm.permutation) in target for p in fiber),
                         "case correction fails progress or protected features")
                used.add(algorithm.id)
        after_fixed = _fixed_features(method.inventory, actions, target)
        implied = tuple(f for f in after_fixed if f not in fixed and f != stage.feature)
        _require(stage.implied_features == implied, "stage implied features are inconsistent")
        fixed, current = after_fixed, target
    _require(current == {_IDENTITY}, "method leaves a nontrivial terminal subgroup")
    _require(used == set(algorithms), "method contains unused shared algorithms")
    for feature in method.skipped_features:
        block = _resolve_feature(method.inventory, feature)
        solved = _observe(actions[_IDENTITY], block, feature.kind)
        _require(all(_observe(actions[p], block, feature.kind) == solved for p in current),
                 "skipped feature metadata is inconsistent")
    return replace(method, _permutations=frozenset(known))


def synthesize_human_method(initial, *, strategy="placement_then_orientation", features=None,
                            recognition=None,
                            max_group_elements=None, gap_executable="gap", timeout=None, root=None,
                            backend="explicit", progress=None):
    """Compile a complete reusable case policy from a reference shape alone.

    Uses the stage planner's reference inputs and optional explicit limits.
    backend='symbolic' compiles small feature orbits without enumerating H.
    Corrections invert deterministic BFS coset representatives; this is not
    an algorithm-quality optimizer or a shortest physical word guarantee.
    ``recognition`` optionally maps compiled stage numbers to feature tuples
    that explicitly include the goal and may observe additional pieces.
    """
    from .computation import Computation, current_computation, report_progress, retain_method
    if progress is not None and current_computation() is None:
        with Computation(progress=progress).activate():
            return synthesize_human_method(initial, strategy=strategy, features=features,
                recognition=recognition,
                max_group_elements=max_group_elements, gap_executable=gap_executable,
                timeout=timeout, root=root, backend=backend)
    if backend == "auto":
        from .preparation import route_preparation, validate_stage_inputs
        features = validate_stage_inputs(strategy, features)
        initial, backend = route_preparation(initial, gap_executable=gap_executable,
            timeout=timeout, root=root, max_group_elements=max_group_elements)
    report_progress("planning", "started", backend=backend, strategy=strategy)
    plan = plan_human_stages(initial, strategy=strategy, features=features,
                             max_group_elements=max_group_elements, gap_executable=gap_executable,
                             timeout=timeout, root=root, backend=backend)
    report_progress("policy", "started", backend=backend)
    method = _compile_plan(plan, recognition=recognition)
    retain_method(method)
    report_progress("policy", "completed", backend=backend, coverage=method.coverage)
    return method


def _compile_plan(plan, *, recognition=None):
    """Compile an internally prepared plan, retaining the full method proof."""
    from .symbolic_chains import SymbolicStagePlan
    recognition = _recognition_inputs(plan, recognition)
    if isinstance(plan, SymbolicStagePlan):
        return _compile_symbolic_plan(plan, recognition=recognition)
    max_group_elements = plan.max_group_elements
    base = dict(reference_shape=plan.inventory.root_shape, strategy=plan.strategy, status=plan.status,
                group_order=plan.group_order, quotient_order=plan.quotient_order, kernel_order=plan.kernel_order,
                root_vertex=plan.analysis.loops.root_vertex, initial_features=plan.initial_features,
                skipped_features=plan.skipped_features, max_group_elements=max_group_elements,
                reason=plan.reason, gap_version=plan.analysis.gap_version,
                _inventory=plan.inventory, _permutations=frozenset())
    if plan.status != "completed":
        return _validate_method(HumanMethod(**base, generators=(), stages=(), algorithms=()))
    group, stages, algorithms, by_effect = plan.group, [], [], {}
    by_id = {g.id: g for g in group.generators}
    generator_lengths = tuple((g.id, g.htm_length) for g in group.generators)
    for stage in plan.stages:
        features = recognition.get(stage.number, ())
        view = SimpleNamespace(feature=stage.feature, recognition_features=features)
        spec = _recognition_spec(plan.inventory, view)
        representatives, goal_representatives = {}, {}
        for i in stage.members_before:
            observation = _recognition_observation(group._summaries[i], spec)
            representatives.setdefault(observation, i)
            goal = _observe(group._summaries[i], stage.block_index, stage.feature.kind)
            goal_representatives.setdefault(goal, i)
        cases = []
        for observation in sorted(representatives):
            index = representatives[observation]
            representative = group.permutations[index]
            algorithm_id = None
            goal = _observe(group._summaries[index], stage.block_index, stage.feature.kind)
            if goal != stage.solved_observation:
                goal_index = goal_representatives[goal]
                permutation = _inverse(group.permutations[goal_index])
                if permutation not in by_effect:
                    expression = LoopExpression.power(group.witness_for_index(goal_index), -1)
                    # The BFS tree bounds the word length; this is an exact
                    # expansion size, not an implicit synthesis resource cap.
                    steps = expression.loop_steps(max_syllables=len(group))
                    raw_length = sum(abs(e) * by_id[i].qtm_length for i, e in steps)
                    moves = expression.expanded_moves(group.generators, max_expanded_moves=max(1, raw_length))
                    algorithm = LoopAlgorithm(f"A{len(algorithms) + 1}", expression, permutation, moves,
                                              group.inventory, generator_lengths,
                                              group.generators)
                    algorithms.append(algorithm)
                    by_effect[permutation] = algorithm.id
                algorithm_id = by_effect[permutation]
            cases.append(HumanMethodCase(observation, algorithm_id, representative))
        stages.append(HumanMethodStage(stage.number, stage.feature, stage.block_index, stage.block_name,
                                       stage.order_before, stage.order_after, stage.solved_observation,
                                       stage.implied_features, tuple(cases), features))
    return _validate_method(HumanMethod(**base, generators=group.generators, stages=tuple(stages),
                                        algorithms=tuple(algorithms)), complete_loops=plan.analysis.loops)


def _compile_symbolic_plan(plan, *, recognition=None):
    """Compile witnessed feature transversals, without listing group elements."""
    generators = tuple(plan.analysis.loops.generators)
    witness_loops = plan.analysis.loops
    records = {g.id: g for g in generators}
    generator_lengths = tuple((g.id, g.htm_length) for g in generators)
    stages, algorithms, by_effect = [], [], {}
    for stage in plan.stages:
        checkpoint("symbolic_case_compilation", stage=stage.number, stages=len(plan.stages))
        features = (recognition or {}).get(stage.number, ())
        view = HumanMethodStage(stage.number, stage.feature, stage.block_index, stage.block_name,
                                stage.order_before, stage.order_after, stage.solved_observation,
                                stage.implied_features, (), features)
        representatives = (_recognition_orbit(plan.inventory, stage, view) if features else
                           {r.observation: r.permutation for r in stage.representatives})
        goal_representatives = {r.observation: r for r in stage.representatives}
        cases = []
        for observation, permutation in sorted(representatives.items()):
            algorithm_id = None
            goal = _goal_observation(observation, plan.inventory, view)
            if goal != stage.solved_observation:
                representative = goal_representatives[goal]
                correction = _inverse(representative.permutation)
                if correction not in by_effect:
                    expression = LoopExpression.power(representative.expression, -1)
                    moves = expression.expanded_moves(
                        witness_loops, max_expanded_moves=max(1, _expression_bound(expression, records)))
                    algorithm = LoopAlgorithm(
                        f"A{len(algorithms) + 1}", expression, correction, moves, plan.inventory,
                        generator_lengths, generators)
                    algorithms.append(algorithm)
                    by_effect[correction] = algorithm.id
                algorithm_id = by_effect[correction]
            cases.append(HumanMethodCase(observation, algorithm_id, permutation))
        stages.append(HumanMethodStage(
            stage.number, stage.feature, stage.block_index, stage.block_name,
            stage.order_before, stage.order_after, stage.solved_observation,
            stage.implied_features, tuple(cases), features))
    method = HumanMethod(
        plan.inventory.root_shape, plan.strategy, "completed", plan.group_order,
        plan.quotient_order, plan.kernel_order, plan.analysis.loops.root_vertex,
        generators, tuple(stages), tuple(algorithms), plan.initial_features,
        plan.skipped_features, None, None, plan.gap_version, plan.inventory,
        plan.group, plan)
    return _validate_method(method, complete_loops=plan.analysis.loops)


def _validate_symbolic_method(method, *, complete_loops):
    """Verify exact coset coverage using certified stabilizers and small orbits."""
    _require(method.max_group_elements is None, "symbolic methods cannot declare an enumeration limit")
    chain = method._symbolic_chain
    chain.validate(inventory=method.inventory, generators=method.generators,
                   expected_order=method.group_order)
    _require((method.quotient_order, method.kernel_order) ==
             (chain.quotient_order, chain.kernel_order), "symbolic placement/kernel orders disagree")
    _require(method.strategy == chain.strategy and method.initial_features == chain.initial_features and
             method.skipped_features == chain.skipped_features and method.gap_version == chain.gap_version,
             "symbolic feature metadata is inconsistent")
    _require(len(method.stages) == len(chain.stages), "symbolic method omits certified stages")
    initial = State(method.reference_shape)
    _require(len({g.id for g in method.generators}) == len(method.generators), "duplicate original loop IDs")
    # chain.validate has just checked this exact immutable witness tuple.
    _require(all(type(g.id) is int and g.id >= 0 for g in method.generators),
             "invalid original loop ID")
    complete_roots = tuple(g.permutation for g in complete_loops.generators)
    _require(complete_roots == chain.group.root_generators or
             all(p in chain.group for p in complete_roots),
             "symbolic generators omit part of the complete reference-loop group")
    algorithms = {a.id: a for a in method.algorithms}
    records = {g.id: g for g in method.generators}
    witness_loops = (complete_loops if method.generators is complete_loops.generators else
                     LoopGenerators(method.generators[0]._owner) if method.generators else None)
    _require(len(algorithms) == len(method.algorithms), "duplicate shared algorithm IDs")
    for algorithm in method.algorithms:
        checkpoint("symbolic_method_validation")
        _require(isinstance(algorithm.id, str) and bool(algorithm.id) and
                 algorithm.permutation != _IDENTITY and algorithm.permutation in chain.group,
                 "invalid shared correction algorithm")
        _require(algorithm._inventory.root_shape == method.reference_shape and
                 algorithm._generators == method.generators,
                 "algorithm refers to a different witness library")
        _require(algorithm.expression.evaluate(witness_loops if witness_loops is not None else records)
                 == algorithm.permutation,
                 "algorithm expression disagrees with its full action")
        moves = algorithm.expression.expanded_moves(
            witness_loops, max_expanded_moves=max(1, _expression_bound(algorithm.expression, records)))
        for word in (moves, algorithm.turn_sequence):
            replay = initial.apply(word)
            _require(replay.shape == method.reference_shape and
                     replay.sticker_permutation == algorithm.permutation,
                     "algorithm physical witness disagrees with its full action")
    used = set()
    for stage, certified in zip(method.stages, chain.stages):
        _require((stage.number, stage.feature, stage.block_index, stage.block_name,
                  stage.order_before, stage.order_after, stage.solved_observation, stage.implied_features) ==
                 (certified.number, certified.feature, certified.block_index, certified.block_name,
                  certified.order_before, certified.order_after, certified.solved_observation,
                  certified.implied_features), "symbolic stage metadata disagrees with its certificate")
        observations = (tuple(sorted(_recognition_orbit(method.inventory, certified, stage)))
                        if stage.recognition_features else certified.observations)
        _require(stage.observations == observations,
                 "symbolic stage cases omit or reorder observations")
        for case in stage.cases:
            _require(case.representative in certified.group_before and
                     _stage_observation(method.inventory.action(case.representative), stage,
                                        method.inventory) == case.observation,
                     "case representative is outside its certified observation fiber")
            if _goal_observation(case.observation, method.inventory, stage) == stage.solved_observation:
                _require(case.algorithm_id is None, "already-solved case must require no correction")
            else:
                _require(case.algorithm_id in algorithms, "case refers to a missing correction")
                algorithm = algorithms[case.algorithm_id]
                _require(algorithm.permutation in certified.group_before and
                         _then(case.representative, algorithm.permutation) in certified.group_after,
                         "case correction fails certified progress or protected features")
                # The observer explicitly projects onto the certified goal.
                # Its whole fiber is therefore contained in the goal coset,
                # and endpoint membership certifies the same correction for
                # every member, rather than only for this representative.
                used.add(algorithm.id)
    _require(used == set(algorithms), "method contains unused shared algorithms")
    return replace(method, _permutations=chain.group)
