"""Exact relative assemblies and bounded geometry-led runtime choices.

An assembly is a collection of whole physical components whose marked poses
agree with one common rigid cube rotation of their reference arrangement.
It may be away from its home slots. This is a standalone predicate, rather
than a stabilizer-chain feature: the union of rotated targets need not be a
subgroup, and no orbit coverage or entry-policy claim follows from it.

Native State inputs may be off the reference partition. Recognition uses
the faithful sticker permutation and real constituent cells, never replay
history, cubie-type tables, or completed bounding boxes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
from types import MappingProxyType

from . import State
from .block_actions import (BlockAction, BlockInventory, _CELL_IMAGES,
                           _CELL_POINTS, _IDENTITY, _NORMALS,
                           _ROTATIONS, _STICKER_IMAGES, _STICKER_ROTATIONS,
                           _coordinates)


def _cells(values, name):
    values = tuple(values)
    if any(type(cell) is not int for cell in values):
        raise TypeError(f"{name} must contain integer cell indices")
    if any(not 0 <= cell < 27 for cell in values) or len(set(values)) != len(values):
        raise ValueError(f"{name} must contain distinct cells from 0 through 26")
    return tuple(sorted(values))


def _bound(value, name, *, minimum=0):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _inventory(value):
    if not isinstance(value, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    return value


def _indices(inventory, cells):
    region = set(cells)
    result = tuple(index for index, block in enumerate(inventory.blocks)
                   if set(block.cells).issubset(region))
    if set(cell for index in result for cell in inventory.blocks[index].cells) != region:
        raise ValueError("assembly cells must be a union of complete physical components")
    return result


@dataclass(frozen=True)
class RelativeAssemblyGoal:
    """A reference arrangement, matched under explicitly allowed rotations.

    The default contains all 24 proper rotations. A restricted rotation set
    is also an exact standalone predicate; it need not form a group.
    """

    cells: tuple[int, ...]
    allowed_rotations: tuple[tuple[int, int, int], ...] = _ROTATIONS

    def __post_init__(self):
        cells = _cells(self.cells, "assembly cells")
        if not cells:
            raise ValueError("an assembly must contain at least one component")
        rotations = tuple(tuple(rotation) for rotation in self.allowed_rotations)
        if not rotations or any(any(type(axis) is not int for axis in rotation) or
                                rotation not in _ROTATIONS for rotation in rotations):
            raise ValueError("allowed rotations must be proper signed-axis cube rotations")
        if len(set(rotations)) != len(rotations):
            raise ValueError("allowed rotations must be distinct")
        object.__setattr__(self, "cells", cells)
        object.__setattr__(self, "allowed_rotations", tuple(
            rotation for rotation in _ROTATIONS if rotation in rotations))

    @property
    def id(self):
        return "relative-assembly:" + json.dumps(
            [self.cells, self.allowed_rotations], separators=(",", ":"))

    def to_dict(self):
        return {"kind": "relative_assembly", "reference_cells": list(self.cells),
                "allowed_rotations": [list(rotation) for rotation in self.allowed_rotations],
                "subgroup_claim": False}

    @classmethod
    def from_dict(cls, record):
        if not isinstance(record, dict) or record.get("kind") != "relative_assembly":
            raise ValueError("record must describe a relative assembly")
        return cls(tuple(record["reference_cells"]),
                   tuple(tuple(rotation) for rotation in record["allowed_rotations"]))


@dataclass(frozen=True)
class AssemblyObservation:
    """Exact component poses and their agreement with common rotations."""

    goal: RelativeAssemblyGoal
    block_indices: tuple[int, ...]
    destination_cells: tuple[tuple[int, ...], ...]
    rotations: tuple[tuple[int, int, int] | None, ...]
    matching_rotations: tuple[tuple[int, int, int], ...]
    best_rotations: tuple[tuple[int, int, int], ...]
    matched_component_count: int
    anchored_component_count: int

    @property
    def is_assembled(self):
        return bool(self.matching_rotations)

    @property
    def assembled(self):
        """Alias for the exact common-rotation predicate."""
        return self.is_assembled

    @property
    def is_anchored(self):
        return self.anchored_component_count == len(self.block_indices)

    @property
    def missing_component_count(self):
        return len(self.block_indices) - self.matched_component_count

    def to_dict(self):
        return {"goal": self.goal.to_dict(), "block_indices": list(self.block_indices),
                "destination_cells": [list(cells) for cells in self.destination_cells],
                "rotations": [list(rotation) if rotation is not None else None
                              for rotation in self.rotations],
                "matching_rotations": [list(rotation) for rotation in self.matching_rotations],
                "best_rotations": [list(rotation) for rotation in self.best_rotations],
                "matched_component_count": self.matched_component_count,
                "anchored_component_count": self.anchored_component_count,
                "is_assembled": self.is_assembled, "is_anchored": self.is_anchored,
                "subgroup_claim": False}


def _physical_poses(inventory, value):
    if isinstance(value, BlockAction):
        if value.inventory.root_shape != inventory.root_shape:
            raise ValueError("block action has a different reference inventory")
        return (tuple(inventory.blocks[index].cells for index in value.destinations),
                value.rotations)
    if isinstance(value, State):
        if value.specification != inventory.root_shape:
            raise ValueError("state specification differs from the reference inventory")
        permutation = value.sticker_permutation
    else:
        try:
            permutation = tuple(value)
        except TypeError as error:
            raise TypeError("assembly recognition requires a State, BlockAction, or permutation") from error
    if any(type(point) is not int for point in permutation):
        raise TypeError("sticker images must be integers")
    if len(permutation) != 48 or set(permutation) != set(range(48)):
        raise ValueError("sticker images must permute 0 through 47")
    destinations, rotations = [], []
    for block in inventory.blocks:
        points = tuple(point for cell in block.cells for point in _CELL_POINTS[cell])
        if not points:
            destinations.append(block.cells)
            rotations.append(None)
            continue
        rotation = _STICKER_ROTATIONS.get((points[0], permutation[points[0]]))
        if rotation is None or any(_STICKER_IMAGES[rotation][point] != permutation[point]
                                   for point in points):
            raise ValueError("sticker action violates rigid physical component orientation")
        # Face centers and the virtual core have no marked stickers and stay
        # at their physical cells. A fused component must agree with them.
        if any(not _CELL_POINTS[cell] and _CELL_IMAGES[rotation][cell] != cell
               for cell in block.cells):
            raise ValueError("sticker action moves an unmarked fixed constituent cell")
        if not block.movable and rotation != _IDENTITY:
            raise ValueError("sticker action moves a permanently immobile component")
        destinations.append(tuple(sorted(_CELL_IMAGES[rotation][cell] for cell in block.cells)))
        rotations.append(rotation)
    return tuple(destinations), tuple(rotations)


def _observe(inventory, poses, goal):
    if not isinstance(goal, RelativeAssemblyGoal):
        raise TypeError("goal must be a RelativeAssemblyGoal")
    indices = _indices(inventory, goal.cells)
    destinations, rotations = poses

    def matches(index, rotation):
        footprint = tuple(sorted(_CELL_IMAGES[rotation][cell]
                                 for cell in inventory.blocks[index].cells))
        return (destinations[index] == footprint and
                (rotations[index] is None or rotations[index] == rotation))

    counts = tuple(sum(matches(index, rotation) for index in indices)
                   for rotation in goal.allowed_rotations)
    best = max(counts)
    return AssemblyObservation(
        goal, indices, tuple(destinations[index] for index in indices),
        tuple(rotations[index] for index in indices),
        tuple(rotation for rotation, count in zip(goal.allowed_rotations, counts)
              if count == len(indices)),
        tuple(rotation for rotation, count in zip(goal.allowed_rotations, counts) if count == best),
        best, sum(matches(index, _IDENTITY) for index in indices))


def observe_relative_assembly(inventory, value, goal):
    """Recognize a complete common-rotation assembly, including off-root states.

    Permutation inputs are checked for component rigidity but are not proofs
    of physical reachability. State imports similarly do not provide an
    ordinary or bandaged scramble witness; no history is inspected here.
    """
    inventory = _inventory(inventory)
    return _observe(inventory, _physical_poses(inventory, value), goal)


@dataclass(frozen=True)
class AssemblyProposalSet:
    """A bounded, deterministic catalogue of connected whole components."""

    goals: tuple[RelativeAssemblyGoal, ...]
    metadata: object = field(repr=False)

    def to_dict(self):
        metadata = dict(self.metadata)
        metadata["eligible_block_indices"] = list(metadata["eligible_block_indices"])
        return {"format": "bce-v2-relative-assembly-proposals", "version": 1,
                "goals": [goal.to_dict() for goal in self.goals],
                "metadata": metadata, "coverage_claim": False}


def _adjacent(inventory, left, right):
    return any(sum(abs(a - b) for a, b in zip(_coordinates(first), _coordinates(second))) == 1
               for first in inventory.blocks[left].cells for second in inventory.blocks[right].cells)


def propose_relative_assemblies(inventory, *, min_components=2, max_components=2,
                                max_candidates=128, max_expansions=4096,
                                eligible_cells=None, required_cells=()):
    """Grow connected collections using real face-adjacent constituent cells.

    ``eligible_cells`` restricts every proposed collection to that region;
    ``required_cells`` is a compatibility alias for the same restriction.
    Neither asks every collection to contain the entire supplied region.
    Both regions must be unions of complete components. Unmarked or
    permanently immobile components are excluded from temporary assemblies.
    Caps are recorded explicitly; a truncated catalogue is not exhaustive.
    """
    inventory = _inventory(inventory)
    min_components = _bound(min_components, "min_components", minimum=1)
    max_components = _bound(max_components, "max_components", minimum=min_components)
    max_candidates = _bound(max_candidates, "max_candidates")
    max_expansions = _bound(max_expansions, "max_expansions")
    alias = _cells(required_cells, "required_cells")
    if eligible_cells is not None:
        eligible_cells = _cells(eligible_cells, "eligible_cells")
        if alias and alias != eligible_cells:
            raise ValueError("eligible_cells and required_cells name different regions")
        candidates = _indices(inventory, eligible_cells)
    elif alias:
        candidates = _indices(inventory, alias)
    else:
        candidates = tuple(range(len(inventory.blocks)))
    eligible = tuple(index for index in candidates if inventory.blocks[index].movable and
                     any(_CELL_POINTS[cell] for cell in inventory.blocks[index].cells))
    adjacency = {index: frozenset(other for other in eligible
                                if index != other and _adjacent(inventory, index, other))
                 for index in eligible}
    queue = deque((index,) for index in eligible)
    seen = set(queue)
    retained = []
    expanded = 0
    while queue and expanded < max_expansions and len(retained) < max_candidates:
        collection = queue.popleft()
        expanded += 1
        if len(collection) >= min_components:
            retained.append(RelativeAssemblyGoal(tuple(
                cell for index in collection for cell in inventory.blocks[index].cells)))
        if len(collection) >= max_components:
            continue
        neighbors = sorted(set().union(*(adjacency[index] for index in collection)) - set(collection))
        for neighbor in neighbors:
            grown = tuple(sorted((*collection, neighbor)))
            if grown not in seen:
                seen.add(grown)
                queue.append(grown)
    metadata = MappingProxyType({"eligible_block_indices": eligible,
                                "min_components": min_components, "max_components": max_components,
                                "max_candidates": max_candidates, "max_expansions": max_expansions,
                                "expanded_collections": expanded, "queued_collections": len(queue),
                                "candidates_bounded": bool(queue and len(retained) >= max_candidates),
                                "expansions_bounded": bool(queue and expanded >= max_expansions),
                                "coverage_claim": False, "subgroup_claim": False})
    return AssemblyProposalSet(tuple(retained), metadata)


@dataclass(frozen=True)
class AssemblyChoice:
    """A per-state candidate and its exact recognition/workspace facts."""

    goal: RelativeAssemblyGoal
    observation: AssemblyObservation
    free_faces: tuple[str, ...]
    assembly_preserving_faces: tuple[str, ...]
    score: tuple[int, ...]

    def to_dict(self):
        return {"goal": self.goal.to_dict(), "observation": self.observation.to_dict(),
                "free_faces": list(self.free_faces),
                "assembly_preserving_faces": list(self.assembly_preserving_faces),
                "score": list(self.score), "entry_recipe_claim": False}


def rank_relative_assemblies(inventory, state, goals, *, max_choices=32):
    """Rank existing assemblies and partial matches using the actual state.

    The ranking first minimizes missing components, then favors larger
    matched collections and more currently legal faces touching none of
    them. It is a proposal heuristic, not a move-distance estimate. Exact
    searches may compare entry costs before choosing a collection.
    """
    inventory = _inventory(inventory)
    if not isinstance(state, State):
        raise TypeError("runtime assembly ranking requires a State")
    max_choices = _bound(max_choices, "max_choices")
    poses = _physical_poses(inventory, state)
    if isinstance(goals, AssemblyProposalSet):
        goals = goals.goals
    goals = tuple(goals)
    if any(not isinstance(goal, RelativeAssemblyGoal) for goal in goals):
        raise TypeError("goals must contain RelativeAssemblyGoal values")
    if len({goal.id for goal in goals}) != len(goals):
        raise ValueError("runtime assembly goals must be distinct")
    legal_faces = tuple(face for face in _NORMALS if state.is_turnable(face))
    choices = []
    for goal in goals:
        observation = _observe(inventory, poses, goal)
        destination_cells = tuple(cell for footprint in observation.destination_cells for cell in footprint)
        free = tuple(face for face in legal_faces
                     if all(sum(a * b for a, b in zip(_coordinates(cell), _NORMALS[face])) != 1
                            for cell in destination_cells))
        preserving = free
        if observation.is_assembled:
            preserving = tuple(face for face in legal_faces
                               if _observe(inventory, _physical_poses(inventory, state.apply(face)), goal).is_assembled)
        score = (observation.missing_component_count, -observation.matched_component_count,
                 -len(free), -observation.anchored_component_count)
        choices.append(AssemblyChoice(goal, observation, free, preserving, score))
    return tuple(sorted(choices, key=lambda choice: (choice.score, choice.goal.id))[:max_choices])
