"""Complete finite case policies compiled from reference-shape loops.

This is a computational baseline. It deliberately keeps the exact policy
separate from later searches for shorter, easier-to-remember algorithms.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import Shape, State
from ._moves import _simplified_moves
from .block_actions import BlockInventory
from .human_chains import BlockFeature, plan_human_stages
from .isotropy import LoopGenerator
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
    return ((action.destinations[block],) if kind == "place_block" else
            (action.destinations[block], action.phases[block]))


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
    """Bound this finite expression's expansion, including checked subwords."""
    if expression.kind == "loop":
        return records[expression.generator_id].qtm_length
    sizes = tuple(_expression_bound(child, records) for child in expression.children)
    if expression.kind == "sequence":
        return sum(sizes)
    if expression.kind == "turns":
        return max(len(expression.moves.split()), sizes[0])
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
    block_index: int
    block_name: str
    order_before: int
    order_after: int
    solved_observation: tuple[int, ...]
    implied_features: tuple[BlockFeature, ...]
    cases: tuple[HumanMethodCase, ...]

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
    _permutations: frozenset = field(repr=False, compare=False)

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
            observation = _observe(action, stage.block_index, stage.feature.kind)
            if observation != stage.solved_observation:
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
    by_cells = {b.cells: i for i, b in enumerate(method.inventory.blocks)}
    for number, stage in enumerate(method.stages, 1):
        _require(stage.feature.cells in by_cells, "stage feature is not an exact reference block")
        block = by_cells[stage.feature.cells]
        _require(stage.number == number and stage.block_index == block and
                 stage.block_name == method.inventory.blocks[block].name,
                 "stage identity or reference block metadata is inconsistent")
        solved = _observe(actions[_IDENTITY], block, stage.feature.kind)
        fibers = defaultdict(set)
        for p in current:
            fibers[_observe(actions[p], block, stage.feature.kind)].add(p)
        target = fibers[solved]
        _require(stage.solved_observation == solved and stage.order_before == len(current) and
                 stage.order_after == len(target) and len(fibers) > 1 and
                 len(current) == len(target) * len(fibers), "stage order or solved observation is inconsistent")
        _require(stage.observations == tuple(sorted(fibers)), "stage cases omit, duplicate or reorder observations")
        for case in stage.cases:
            fiber = fibers[case.observation]
            _require(case.representative in fiber, "case representative is outside its exact observation fiber")
            _require({_then(k, case.representative) for k in target} == fiber,
                     "case observation is not an exact right coset")
            if case.observation == solved:
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
    _require(all(f.cells in by_cells and f in fixed for f in method.skipped_features),
             "skipped feature metadata is inconsistent")
    return replace(method, _permutations=frozenset(known))


def synthesize_human_method(initial, *, strategy="placement_then_orientation", features=None,
                            max_group_elements=None, gap_executable="gap", timeout=None, root=None):
    """Compile a complete reusable case policy from a reference shape alone.

    Uses the explicit stage planner's reference inputs and optional limits.
    Corrections invert deterministic BFS coset representatives; this is not
    an algorithm-quality optimizer or a shortest physical word guarantee.
    """
    plan = plan_human_stages(initial, strategy=strategy, features=features,
                             max_group_elements=max_group_elements, gap_executable=gap_executable,
                             timeout=timeout, root=root)
    return _compile_plan(plan)


def _compile_plan(plan):
    """Compile an internally prepared plan, retaining the full method proof."""
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
    for stage in plan.stages:
        representatives = {}
        for i in stage.members_before:
            observation = _observe(group._summaries[i], stage.block_index, stage.feature.kind)
            representatives.setdefault(observation, i)
        cases = []
        for observation in stage.observations:
            index = representatives[observation]
            representative = group.permutations[index]
            algorithm_id = None
            if observation != stage.solved_observation:
                permutation = _inverse(representative)
                if permutation not in by_effect:
                    expression = LoopExpression.power(group.witness_for_index(index), -1)
                    # The BFS tree bounds the word length; this is an exact
                    # expansion size, not an implicit synthesis resource cap.
                    steps = expression.loop_steps(max_syllables=len(group))
                    raw_length = sum(abs(e) * by_id[i].qtm_length for i, e in steps)
                    moves = expression.expanded_moves(group.generators, max_expanded_moves=max(1, raw_length))
                    algorithm = LoopAlgorithm(f"A{len(algorithms) + 1}", expression, permutation, moves,
                                              group.inventory, tuple((g.id, g.htm_length) for g in group.generators),
                                              group.generators)
                    algorithms.append(algorithm)
                    by_effect[permutation] = algorithm.id
                algorithm_id = by_effect[permutation]
            cases.append(HumanMethodCase(observation, algorithm_id, representative))
        stages.append(HumanMethodStage(stage.number, stage.feature, stage.block_index, stage.block_name,
                                       stage.order_before, stage.order_after, stage.solved_observation,
                                       stage.implied_features, tuple(cases)))
    return _validate_method(HumanMethod(**base, generators=group.generators, stages=tuple(stages),
                                        algorithms=tuple(algorithms)), complete_loops=plan.analysis.loops)
