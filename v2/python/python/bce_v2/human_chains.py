"""Exact, witnessed stage skeletons; correction policies are separate work."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
from math import prod
from pathlib import Path
from types import MappingProxyType

from . import State
from .block_solver import BlockStructure, _permutation_order, analyze_block_structure
from .gap_backend import GapError, _validated_options
from .isotropy import IsotropyAnalysis, analyze_isotropy
from .loop_algorithms import LoopExpression
from .loop_solver import LoopStep


_IDENTITY = tuple(range(48))
_KINDS = ("place_block", "solve_block")
_STRATEGIES = {
    "placement_then_orientation": _KINDS,
    "fully_solve_each_block": ("solve_block",),
}


def _check(condition, message):
    if not condition:
        raise GapError(message)


def _then(first, second):
    return tuple(second[p] for p in first)


def _inverse(permutation):
    result = [0] * 48
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


def _inverse_moves(moves):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(moves.split()))


@dataclass(frozen=True)
class BlockFeature:
    """Place or fully solve one physical block, named by all reference cells."""

    kind: str
    cells: tuple[int, ...]

    def __post_init__(self):
        if self.kind not in _KINDS:
            raise ValueError("feature kind must be place_block or solve_block")
        cells = tuple(self.cells)
        if not cells:
            raise ValueError("a feature must name a nonempty reference block")
        if any(isinstance(cell, bool) or not isinstance(cell, int) for cell in cells):
            raise TypeError("feature cells must be integer reference-cell indices")
        if any(not 0 <= cell < 27 for cell in cells) or len(set(cells)) != len(cells):
            raise ValueError("feature cells must be distinct indices from 0 through 26")
        object.__setattr__(self, "cells", tuple(sorted(cells)))

    def to_dict(self):
        return {"kind": self.kind, "reference_cells": list(self.cells)}


@dataclass(frozen=True)
class _ActionSummary:
    destinations: tuple[int, ...]
    phases: tuple[int, ...]


def _observation(action, block, kind):
    destination = action.destinations[block]
    return (destination,) if kind == "place_block" else (destination, action.phases[block])


@dataclass(frozen=True)
class WitnessedLoopGroup:
    """Complete finite root group with a compact original-loop witness tree.

    Permutations and parent arrays use deterministic BFS discovery order.
    Every parent precedes its child; parent_steps names a legal original loop
    or its inverse. Reconstructing a word never requires another GAP call.
    """

    analysis: IsotropyAnalysis
    permutations: tuple[tuple[int, ...], ...]
    parent_indices: tuple[int | None, ...]
    parent_steps: tuple[LoopStep | None, ...]
    _summaries: tuple[_ActionSummary, ...] = field(repr=False, compare=False)
    _indices: object = field(repr=False, compare=False)

    @property
    def inventory(self):
        return self.analysis.block_inventory

    @property
    def generators(self):
        return self.analysis.generators

    def __len__(self):
        return len(self.permutations)

    def element_index(self, permutation):
        permutation = tuple(permutation)
        if (len(permutation) != 48 or
                any(isinstance(p, bool) or not isinstance(p, int) for p in permutation) or
                set(permutation) != set(range(48))):
            raise ValueError("an element must be a permutation of sticker points 0 through 47")
        try:
            return self._indices[permutation]
        except KeyError:
            raise ValueError("permutation does not belong to this reference loop group") from None

    def witness_for_index(self, index):
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("element index must be an integer")
        if not 0 <= index < len(self):
            raise ValueError("element index is outside the enumerated group")
        expressions = []
        while index:
            step = self.parent_steps[index]
            expressions.append(LoopExpression.power(LoopExpression.loop(step.generator_id), step.exponent))
            index = self.parent_indices[index]
        return LoopExpression.sequence(*reversed(expressions))

    def witness(self, permutation):
        """Return a witnessed LoopExpression for an exact group permutation."""
        return self.witness_for_index(self.element_index(permutation))

    def to_dict(self, *, include_elements=False, include_moves=True):
        record = {"order": str(len(self)),
                  "generator_ids": list(self.analysis.generator_ids),
                  "generators": [g.to_dict(include_moves=include_moves) for g in self.generators],
                  "witness_kind": "original_loop_bfs_tree"}
        if include_elements:
            record["elements"] = [
                {"permutation": list(permutation), "parent": parent,
                 "step": step.to_dict() if step is not None else None}
                for permutation, parent, step in
                zip(self.permutations, self.parent_indices, self.parent_steps)
            ]
        return record


@dataclass(frozen=True)
class HumanStage:
    """A recognizable stabilizer step, without a correction algorithm policy."""

    number: int
    feature: BlockFeature
    block_index: int
    block_name: str
    members_before: tuple[int, ...] = field(repr=False)
    members_after: tuple[int, ...] = field(repr=False)
    observations: tuple[tuple[int, ...], ...]
    solved_observation: tuple[int, ...]
    implied_features: tuple[BlockFeature, ...]

    @property
    def order_before(self):
        return len(self.members_before)

    @property
    def order_after(self):
        return len(self.members_after)

    @property
    def index(self):
        return self.order_before // self.order_after

    @property
    def case_count(self):
        return len(self.observations)

    def to_dict(self, *, include_elements=False):
        record = {"number": self.number, "feature": self.feature.to_dict(),
                  "block_index": self.block_index, "block_name": self.block_name,
                  "order_before": str(self.order_before), "order_after": str(self.order_after),
                  "index": self.index, "observations": [list(o) for o in self.observations],
                  "solved_observation": list(self.solved_observation),
                  "implied_features": [feature.to_dict() for feature in self.implied_features]}
        if include_elements:
            record.update(members_before=list(self.members_before), members_after=list(self.members_after))
        return record


@dataclass(frozen=True)
class HumanStagePlan:
    """A completed chain skeleton or an explicit preflight stop.

    Complete structure does not certify a correction policy or human quality.
    Application/recognition helpers belong to the subsequent method delivery.
    """

    analysis: IsotropyAnalysis
    strategy: str
    status: str
    group: WitnessedLoopGroup | None
    stages: tuple[HumanStage, ...]
    block_structure: BlockStructure | None
    initial_features: tuple[BlockFeature, ...]
    skipped_features: tuple[BlockFeature, ...]
    max_group_elements: int | None
    reason: str | None = None

    @property
    def inventory(self):
        return self.analysis.block_inventory

    @property
    def group_order(self):
        return self.analysis.group_order

    @property
    def quotient_order(self):
        return None if self.block_structure is None else self.block_structure.quotient_order

    @property
    def kernel_order(self):
        return None if self.block_structure is None else self.block_structure.kernel_order

    @property
    def terminal_order(self):
        return 1 if self.status == "completed" else None

    @property
    def coverage_scope(self):
        return "chain_structure_only"

    @property
    def human_method_complete(self):
        return False

    def to_dict(self, *, include_elements=False, include_moves=True):
        return {
            "format": "bce-v2-human-stage-plan", "version": 1,
            "model": "full-grid-27-fixed-centers", "frame": "fixed",
            "permutation_action": "source-to-destination", "permutation_composition": "execution-order",
            "reference_shape": self.inventory.root_shape.labels,
            "root_vertex": self.analysis.loops.root_vertex,
            "block_inventory": self.inventory.to_dict(), "gap_version": self.analysis.gap_version,
            "status": self.status, "reason": self.reason, "strategy": self.strategy,
            "coverage_scope": self.coverage_scope, "human_method_complete": False,
            "preservation": "whole_algorithm_endpoints",
            "max_group_elements": self.max_group_elements,
            "group_order": str(self.group_order),
            "quotient_order": None if self.quotient_order is None else str(self.quotient_order),
            "kernel_order": None if self.kernel_order is None else str(self.kernel_order),
            "terminal_order": None if self.terminal_order is None else str(self.terminal_order),
            "initial_features": [f.to_dict() for f in self.initial_features],
            "skipped_features": [f.to_dict() for f in self.skipped_features],
            "stages": [stage.to_dict(include_elements=include_elements) for stage in self.stages],
            "group": None if self.group is None else self.group.to_dict(
                include_elements=include_elements, include_moves=include_moves),
            "block_structure": None if self.block_structure is None else
                self.block_structure.to_dict(include_moves=include_moves),
        }

    def to_json(self, path=None, *, include_elements=False, include_moves=True):
        text = json.dumps(self.to_dict(include_elements=include_elements, include_moves=include_moves),
                          indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_elements=False, include_moves=True):
        self.to_json(path, include_elements=include_elements, include_moves=include_moves)
        return self.to_dict(include_elements=include_elements, include_moves=include_moves)


def _alphabet(analysis):
    alphabet = {}
    initial = State(analysis.loops.root_shape)
    for generator in analysis.generators:
        for exponent, permutation, moves in (
                (1, generator.permutation, generator.turn_sequence),
                (-1, _inverse(generator.permutation), _inverse_moves(generator.turn_sequence))):
            replay = initial.apply(moves)
            _check(replay.shape == initial.shape and tuple(replay.sticker_permutation) == permutation,
                   "selected loop alphabet fails legal colored replay")
            alphabet.setdefault(permutation, LoopStep(generator.id, exponent))
    return alphabet


def _enumerate(analysis):
    alphabet = _alphabet(analysis)
    permutations = [_IDENTITY]
    indices = {_IDENTITY: 0}
    parents, steps = [None], [None]
    for element in permutations:
        parent = indices[element]
        for generator, step in alphabet.items():
            successor = _then(element, generator)
            if successor not in indices:
                _check(len(permutations) < analysis.group_order,
                       "enumeration exceeds the supplied isotropy order")
                indices[successor] = len(permutations)
                permutations.append(successor)
                parents.append(parent)
                steps.append(step)
    _check(len(permutations) == analysis.group_order, "enumeration disagrees with the supplied isotropy order")
    _check(all(g.permutation in indices for g in analysis.loops.generators),
           "supplied isotropy analysis omits part of the complete root-loop group")
    inventory = analysis.block_inventory
    summaries = []
    for permutation in permutations:
        action = inventory.action(permutation)
        _check(action.to_permutation() == permutation, "block action fails faithful reconstruction")
        summaries.append(_ActionSummary(action.destinations, action.phases))
    moduli = tuple(b.orientation_order for b in inventory.blocks)
    for index, action in enumerate(summaries):
        for generator in alphabet:
            next_action = summaries[indices[generator]]
            composed = summaries[indices[_then(permutations[index], generator)]]
            _check(composed.destinations == tuple(next_action.destinations[d] for d in action.destinations)
                   and composed.phases == tuple((q + next_action.phases[d]) % modulus
                                               for d, q, modulus in
                                               zip(action.destinations, action.phases, moduli)),
                   "oriented-block observations fail equivariance")
    return WitnessedLoopGroup(analysis, tuple(permutations), tuple(parents), tuple(steps),
                              tuple(summaries), MappingProxyType(indices))


def _check_reused_group(group):
    """Recheck retained public records before trusting their witness tree."""
    size = len(group)
    _check(size == group.analysis.group_order and size > 0,
           "retained group size disagrees with its isotropy analysis")
    _check(len(group.parent_indices) == len(group.parent_steps) == len(group._summaries) == size,
           "retained group arrays have inconsistent lengths")
    _check(group.permutations[0] == _IDENTITY and
           group.parent_indices[0] is None and group.parent_steps[0] is None,
           "retained witness tree has an invalid identity root")
    indices = {p: i for i, p in enumerate(group.permutations)}
    _check(len(indices) == size and group._indices == indices,
           "retained group element index is inconsistent")
    alphabet = _alphabet(group.analysis)
    steps = {(step.generator_id, step.exponent): p for p, step in alphabet.items()}
    # Equal actions can have different valid original IDs; retain those too.
    for generator in group.generators:
        steps[generator.id, 1] = generator.permutation
        steps[generator.id, -1] = _inverse(generator.permutation)
    for i in range(1, size):
        parent, step = group.parent_indices[i], group.parent_steps[i]
        _check(isinstance(parent, int) and not isinstance(parent, bool) and 0 <= parent < i,
               "retained witness tree parent must precede its child")
        _check(isinstance(step, LoopStep) and
               isinstance(step.generator_id, int) and not isinstance(step.generator_id, bool) and
               isinstance(step.exponent, int) and not isinstance(step.exponent, bool) and
               (step.generator_id, step.exponent) in steps,
               "retained witness tree step is not in the original loop alphabet")
        _check(_then(group.permutations[parent], steps[step.generator_id, step.exponent]) ==
               group.permutations[i], "retained witness tree edge has the wrong action")
    _check(all(g.permutation in indices for g in group.analysis.loops.generators),
           "retained group omits part of the complete root-loop group")
    for permutation, summary in zip(group.permutations, group._summaries):
        action = group.inventory.action(permutation)
        _check(action.to_permutation() == permutation and
               summary == _ActionSummary(action.destinations, action.phases),
               "retained block-action summary disagrees with its permutation")


def _fixed_features(group, members):
    fixed = []
    identity = group._summaries[0]
    for kind in _KINDS:
        for block, slot in enumerate(group.inventory.blocks):
            solved = _observation(identity, block, kind)
            if all(_observation(group._summaries[i], block, kind) == solved for i in members):
                fixed.append(BlockFeature(kind, slot.cells))
    return tuple(fixed)


def _stage(group, current, feature, block, number, fixed):
    solved = _observation(group._summaries[0], block, feature.kind)
    fibers = defaultdict(list)
    for i in current:
        fibers[_observation(group._summaries[i], block, feature.kind)].append(i)
    target = tuple(fibers[solved])
    _check(len(current) == len(target) * len(fibers), "stage stabilizer index is inconsistent")
    for members in fibers.values():
        representative = group.permutations[members[0]]
        _check({_then(group.permutations[k], representative) for k in target} ==
               {group.permutations[i] for i in members}, "stage observations are not right cosets")
    after_fixed = _fixed_features(group, target)
    implied = tuple(f for f in after_fixed if f not in fixed and f != feature)
    return (HumanStage(number, feature, block, group.inventory.blocks[block].name,
                       current, target, tuple(sorted(fibers)), solved, implied), after_fixed)


def _chains(group, strategy, features):
    current = tuple(range(len(group)))
    fixed = initial = _fixed_features(group, current)
    stages, skipped = [], []
    by_cells = {block.cells: i for i, block in enumerate(group.inventory.blocks)}
    if strategy == "manual":
        choices = features
        for feature in choices:
            block = by_cells[feature.cells]
            solved = _observation(group._summaries[0], block, feature.kind)
            if all(_observation(group._summaries[i], block, feature.kind) == solved for i in current):
                skipped.append(feature)
                continue
            stage, fixed = _stage(group, current, feature, block, len(stages) + 1, fixed)
            stages.append(stage)
            current = stage.members_after
        if current != (0,):
            raise ValueError(f"manual features leave a subgroup of order {len(current)}; add solve_block features")
    else:
        for kind in _STRATEGIES[strategy]:
            while True:
                candidates = []
                for block, slot in enumerate(group.inventory.blocks):
                    solved = _observation(group._summaries[0], block, kind)
                    size = sum(_observation(group._summaries[i], block, kind) == solved for i in current)
                    if size < len(current):
                        _check(size > 0 and len(current) % size == 0, "invalid feature stabilizer order")
                        candidates.append((len(current) // size, block))
                if not candidates:
                    break
                _, block = min(candidates)
                feature = BlockFeature(kind, group.inventory.blocks[block].cells)
                stage, fixed = _stage(group, current, feature, block, len(stages) + 1, fixed)
                stages.append(stage)
                current = stage.members_after
            if kind == "place_block":
                kernel = tuple(i for i, action in enumerate(group._summaries)
                               if action.destinations == group._summaries[0].destinations)
                _check(current == kernel, "placement stages do not reach the exact footprint kernel")
    _check(current == (0,) and prod(stage.index for stage in stages) == len(group),
           "stage chain does not terminate at the faithful identity")
    return tuple(stages), initial, tuple(skipped)


def _check_kernel(group, structure):
    kernel = {p for p, a in zip(group.permutations, group._summaries)
              if a.destinations == group._summaries[0].destinations}
    placements = {a.destinations for a in group._summaries}
    _check(len(kernel) == structure.kernel_order and len(placements) == structure.quotient_order,
           "enumerated placement/kernel counts disagree with GAP")
    _check(prod(a.order for a in structure.basis) == len(kernel) and
           len({a.id for a in structure.basis}) == len(structure.basis),
           "independent kernel basis orders or identifiers are inconsistent")
    generated, queue = {_IDENTITY}, deque([_IDENTITY])
    for algorithm in structure.basis:
        _check(algorithm.permutation in kernel and algorithm.order > 1 and
               _permutation_order(algorithm.permutation) == algorithm.order,
               "kernel basis has an invalid action or declared order")
        _check(algorithm._inventory.root_shape == group.inventory.root_shape and
               algorithm._generators == group.generators,
               "kernel basis witness refers to a different reference library")
        expression = LoopExpression.sequence(*(LoopExpression.power(LoopExpression.loop(s.generator_id), s.exponent)
                                               for s in algorithm.steps))
        _check(expression.evaluate(group.generators) == algorithm.permutation,
               "kernel basis original-loop witness is inconsistent")
        _check(all(_then(algorithm.permutation, other.permutation) ==
                   _then(other.permutation, algorithm.permutation) for other in structure.basis),
               "kernel basis elements do not commute")
    while queue:
        element = queue.popleft()
        for algorithm in structure.basis:
            successor = _then(element, algorithm.permutation)
            _check(successor in kernel, "kernel basis leaves the footprint-fixing kernel")
            if successor not in generated:
                generated.add(successor)
                queue.append(successor)
    _check(generated == kernel, "independent kernel basis does not generate the enumerated kernel")


def plan_human_stages(initial, *, strategy="placement_then_orientation", features=None,
                      max_group_elements=None, gap_executable="gap", timeout=None, root=None,
                      backend="explicit"):
    """Build a complete finite stage skeleton from a reference shape alone.

    Also accepts complete ShapeGraphs, LoopGenerators, IsotropyAnalysis,
    BlockStructure, or a prepared HumanStagePlan. Original roots are retained.
    Manual features must name exact inventory blocks and finish at identity;
    redundant features are recorded and skipped. There is no default resource
    cap. Supply max_group_elements to stop before enumeration of larger H.
    A stop has status=limit_reached, no group/stages, and no terminal claim.

    backend='symbolic' uses exact stabilizers and small feature orbits instead
    of enumerating the colored group. max_group_elements applies only to the
    explicit backend and cannot be supplied for a symbolic plan.

    This explicit backend has been measured through order 10,368. It retains
    original-loop witnesses and exact cases, but no case correction policy,
    shortest-word guarantee, or human-quality claim.
    """
    gap_executable, timeout = _validated_options(gap_executable, timeout)
    if backend not in ("explicit", "symbolic"):
        raise ValueError("backend must be 'explicit' or 'symbolic'")
    if backend == "symbolic" and max_group_elements is not None:
        raise ValueError("max_group_elements only applies to backend='explicit'")
    if root is not None and (isinstance(root, bool) or not isinstance(root, int)):
        raise TypeError("root must be an integer vertex ID")
    from .symbolic_chains import SymbolicStagePlan
    symbolic_previous = initial if isinstance(initial, SymbolicStagePlan) else None
    if symbolic_previous is not None:
        if backend != "symbolic":
            raise ValueError("a prepared symbolic plan requires backend='symbolic'")
        if symbolic_previous.analysis is None:
            raise ValueError("a prepared symbolic plan must retain its reference analysis")
        if root is not None and root != symbolic_previous.analysis.loops.root_vertex:
            raise ValueError("root differs from the supplied reference analysis")
        if strategy == symbolic_previous.strategy and features is None:
            return symbolic_previous.validate(expected_order=symbolic_previous.analysis.group_order)
    if max_group_elements is not None:
        if isinstance(max_group_elements, bool) or not isinstance(max_group_elements, int):
            raise TypeError("max_group_elements must be a positive integer or None")
        if max_group_elements <= 0:
            raise ValueError("max_group_elements must be positive")
    if strategy not in (*_STRATEGIES, "manual"):
        raise ValueError("unknown human stage strategy")
    if strategy == "manual":
        if features is None:
            raise ValueError("manual strategy requires features")
        features = tuple(features)
        if any(not isinstance(f, BlockFeature) for f in features):
            raise TypeError("manual features must be BlockFeature instances")
    elif features is not None:
        raise ValueError("features are only accepted with strategy='manual'")
    previous = initial if isinstance(initial, HumanStagePlan) else None
    structure = previous.block_structure if previous else initial if isinstance(initial, BlockStructure) else None
    analysis = (symbolic_previous.analysis if symbolic_previous else
                previous.analysis if previous else structure.analysis if structure else
                initial if isinstance(initial, IsotropyAnalysis) else None)
    if analysis is None:
        analysis = analyze_isotropy(initial, gap_executable=gap_executable, timeout=timeout, root=root)
    elif root is not None and root != analysis.loops.root_vertex:
        raise ValueError("root differs from the supplied reference analysis")
    if structure is not None:
        _check(structure.analysis == analysis, "prepared kernel structure refers to a different analysis")
    if previous is not None and previous.group is not None:
        _check(previous.group.analysis == analysis, "prepared group refers to a different analysis")
    if features is not None:
        cells = {block.cells for block in analysis.block_inventory.blocks}
        if any(f.cells not in cells for f in features):
            raise ValueError("each feature must name exactly one block in the actual reference inventory")
    if backend == "symbolic":
        from .symbolic_chains import plan_symbolic_stages
        return plan_symbolic_stages(analysis, strategy=strategy, features=features,
                                    gap_executable=gap_executable, timeout=timeout)
    if max_group_elements is not None and analysis.group_order > max_group_elements:
        return HumanStagePlan(analysis, strategy, "limit_reached", None, (), None, (), (),
                              max_group_elements, "group_order_exceeds_limit")
    if previous and previous.group is not None:
        group = previous.group
        _check_reused_group(group)
    else:
        group = _enumerate(analysis)
    structure = structure or analyze_block_structure(analysis, gap_executable=gap_executable, timeout=timeout)
    _check_kernel(group, structure)
    stages, initial_features, skipped = _chains(group, strategy, features)
    return HumanStagePlan(analysis, strategy, "completed", group, stages, structure,
                          initial_features, skipped, max_group_elements)
