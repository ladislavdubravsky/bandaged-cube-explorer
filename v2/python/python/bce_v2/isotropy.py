"""Witnessed shape loops and optional exact GAP analysis.

Extraction runs in Rust. GAP receives only faithful sticker permutations;
retained generators continue to reference their original legal move witnesses.
"""

from dataclasses import dataclass, field
from functools import cached_property
import json
from pathlib import Path
from types import MappingProxyType

from . import Shape, State, explore
from ._moves import _simplified_moves
from .graph import ShapeGraph


@dataclass(frozen=True)
class LoopGenerator:
    """A nonidentity root loop, identified by its original graph arc ID.

    permutation maps source sticker positions to destinations, numbered 0..47
    in URFDLB facelet order with the six centers omitted. moves expands the
    shared tree paths lazily; qtm_length is its unsimplified quarter-turn cost.
    turn_sequence combines adjacent same-face turns for human display, and
    htm_length counts its face turns, including half turns as one.
    """

    id: int
    source: int
    target: int
    permutation: tuple[int, ...]
    qtm_length: int
    _owner: object = field(repr=False, compare=False)
    _inventory: object = field(default=None, repr=False, compare=False)
    _library: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "permutation", tuple(self.permutation))

    @cached_property
    def moves(self):
        return self._owner.generator_moves(self.id)

    @cached_property
    def turn_sequence(self):
        """Replayable display word with adjacent same-face turns combined."""
        return _simplified_moves(self.moves.split())

    @cached_property
    def htm_length(self):
        """HTM cost of turn_sequence; no shortest-word guarantee is made."""
        return len(self.turn_sequence.split())

    @cached_property
    def block_action(self):
        """Exact effect on the loop root's physical reference blocks."""
        from .block_actions import BlockInventory

        inventory = self._inventory
        if inventory is None:
            inventory = BlockInventory(Shape(self._owner.root_shape))
        return inventory.action(self.permutation)

    def to_dict(self, *, include_moves=True):
        record = {
            "id": self.id, "source": self.source, "target": self.target,
            "permutation": list(self.permutation), "qtm_length": self.qtm_length,
        }
        record["block_action"] = self.block_action.to_dict()
        if include_moves:
            record["moves"] = self.moves
            record["turn_sequence"] = self.turn_sequence
            record["htm_length"] = self.htm_length
        return record


class LoopGenerators:
    """A complete generating set of the reference shape's isotropy group.

    Identity, duplicate, and inverse-duplicate permutations have been removed.
    This set need not be irredundant. GAP is required only by analyze().
    """

    __slots__ = ("_native", "_generators", "_block_inventory", "_generator_records",
                 "_evaluations", "_algorithm_words", "_verified_turns",
                 "_validated_witness_signature", "_witness_signature", "_generator_htm_lengths")

    def __init__(self, native):
        object.__setattr__(self, "_native", native)
        object.__setattr__(self, "_generators", None)
        object.__setattr__(self, "_block_inventory", None)
        object.__setattr__(self, "_generator_records", None)
        object.__setattr__(self, "_evaluations", {})
        object.__setattr__(self, "_algorithm_words", {})
        object.__setattr__(self, "_verified_turns", set())
        object.__setattr__(self, "_validated_witness_signature", None)
        object.__setattr__(self, "_witness_signature", None)
        object.__setattr__(self, "_generator_htm_lengths", None)

    def __setattr__(self, name, value):
        raise AttributeError("LoopGenerators is immutable")

    def __delattr__(self, name):
        raise AttributeError("LoopGenerators is immutable")

    @property
    def root_shape(self):
        return Shape(self._native.root_shape)

    @property
    def root_vertex(self):
        return self._native.root_vertex

    @property
    def block_inventory(self):
        """Stable identities, names and orientation frames at root_shape."""
        if self._block_inventory is None:
            from .block_actions import BlockInventory

            object.__setattr__(self, "_block_inventory", BlockInventory(self.root_shape))
        return self._block_inventory

    @property
    def shape_count(self):
        return self._native.shape_count

    @property
    def arc_count(self):
        """Clockwise QTM arcs, including parallel actions and self-loops."""
        return self._native.arc_count

    @property
    def candidate_count(self):
        return self._native.candidate_count

    @property
    def nonidentity_count(self):
        return self._native.nonidentity_count

    @property
    def generators(self):
        if self._generators is None:
            records = tuple(LoopGenerator(
                id=record["id"], source=record["source"], target=record["target"],
                permutation=tuple(record["permutation"]),
                qtm_length=record["qtm_length"], _owner=self._native,
                _inventory=self.block_inventory, _library=self,
            ) for record in self._native.generators)
            object.__setattr__(self, "_generators", records)
        return self._generators

    @property
    def generator_records(self):
        """Immutable original-ID index shared by this witness library."""
        if self._generator_records is None:
            object.__setattr__(self, "_generator_records", MappingProxyType(
                {generator.id: generator for generator in self.generators}))
        return self._generator_records

    @property
    def witness_signature(self):
        """Exact immutable alphabet identity, including physical witnesses."""
        if self._witness_signature is None:
            object.__setattr__(self, "_witness_signature", tuple(
                (generator.id, generator.permutation, generator.moves, generator.qtm_length)
                for generator in self.generators))
        return self._witness_signature

    @property
    def generator_htm_lengths(self):
        """Stable immutable length table for this original witness alphabet."""
        if self._generator_htm_lengths is None:
            object.__setattr__(self, "_generator_htm_lengths", tuple(
                (generator.id, generator.htm_length) for generator in self.generators))
        return self._generator_htm_lengths

    def validate_witnesses(self):
        """Independently replay this immutable alphabet once per owner.

        Portable imports receive a fresh owner and therefore a cold certificate.
        The cache records successful physical replay, never a trust flag copied
        from saved data or a claim that the alphabet generates the full group.
        """
        signature = self.witness_signature
        if self._validated_witness_signature == signature:
            return self
        if len({generator.id for generator in self.generators}) != len(self.generators):
            raise ValueError("original loops have duplicate IDs")
        initial = State(self.root_shape)
        for generator in self.generators:
            if (type(generator.id) is not int or generator.id < 0 or
                    generator.qtm_length != sum(2 if move.endswith("2") else 1
                                                for move in generator.moves.split())):
                raise ValueError("original loop has invalid ID or length metadata")
            replay = initial.apply(generator.moves)
            if replay.shape != self.root_shape or replay.sticker_permutation != generator.permutation:
                raise ValueError("original loop fails physical replay")
        object.__setattr__(self, "_validated_witness_signature", signature)
        return self

    def __len__(self):
        return len(self.generators)

    def __iter__(self):
        return iter(self.generators)

    def __getitem__(self, index):
        return self.generators[index]

    def transport(self, vertex):
        """A shortest QTM tree path from the root to a graph vertex ID."""
        if isinstance(vertex, bool) or not isinstance(vertex, int):
            raise TypeError("vertex must be an integer ID")
        if not 0 <= vertex < self.shape_count:
            raise IndexError("vertex ID out of range")
        return self._native.transport(vertex)

    def analyze(self, *, gap_executable="gap", timeout=None):
        """Compute exact order and select original loops through GAP."""
        from .gap_backend import analyze_generators

        result = analyze_generators(
            [generator.permutation for generator in self.generators],
            gap_executable=gap_executable, timeout=timeout,
        )
        return IsotropyAnalysis(
            loops=self, group_order=result.group_order,
            generator_ids=tuple(self.generators[index].id
                                for index in result.generator_indices),
            gap_version=result.gap_version,
        )

    def _metadata(self):
        return {
            "version": 1, "model": "full-grid-27-fixed-centers",
            "notation": "Singmaster", "metric": "QTM", "symmetry": "none",
            "complete": True, "root_shape": self.root_shape.labels,
            "root_vertex": self.root_vertex, "shape_count": self.shape_count,
            "arc_count": self.arc_count, "candidate_count": self.candidate_count,
            "nonidentity_count": self.nonidentity_count,
            "permutation_degree": 48, "permutation_index_base": 0,
            "permutation_point_order": "URFDLB-without-centers",
            "permutation_action": "source-to-destination",
            "permutation_composition": "execution-order",
            "block_inventory": self.block_inventory.to_dict(),
        }

    def to_dict(self, *, include_moves=True):
        """Versioned inspection export; move witnesses are included by default."""
        return {
            **self._metadata(), "format": "bce-v2-isotropy-loops",
            "generator_count": len(self),
            "generators": [generator.to_dict(include_moves=include_moves)
                           for generator in self.generators],
        }

    def to_json(self, path=None, *, include_moves=True):
        text = json.dumps(self.to_dict(include_moves=include_moves),
                          indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_moves=True):
        self.to_json(path, include_moves=include_moves)
        return self.to_dict(include_moves=include_moves)


@dataclass(frozen=True)
class IsotropyAnalysis:
    """Exact GAP order and a generating subset with original loop witnesses.

    Counts concern the complete reachable component in a fixed center frame,
    with full corner/edge identities and orientations and unmarked centers.
    """

    loops: LoopGenerators
    group_order: int
    generator_ids: tuple[int, ...]
    gap_version: str

    @property
    def colored_state_count(self):
        return self.loops.shape_count * self.group_order

    @property
    def block_inventory(self):
        return self.loops.block_inventory

    @property
    def generators(self):
        by_id = self.loops.generator_records
        return tuple(by_id[identifier] for identifier in self.generator_ids)

    def to_dict(self, *, include_moves=True):
        """Export exact orders as decimal strings to preserve JSON precision."""
        return {
            **self.loops._metadata(), "format": "bce-v2-isotropy-analysis",
            "algebra_backend": "GAP", "gap_version": self.gap_version,
            "group_order": str(self.group_order),
            "colored_state_count": str(self.colored_state_count),
            "extracted_generator_count": len(self.loops),
            "generator_count": len(self.generator_ids),
            "generator_ids": list(self.generator_ids),
            "generators": [generator.to_dict(include_moves=include_moves)
                           for generator in self.generators],
        }

    def to_json(self, path=None, *, include_moves=True):
        text = json.dumps(self.to_dict(include_moves=include_moves),
                          indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_moves=True):
        self.to_json(path, include_moves=include_moves)
        return self.to_dict(include_moves=include_moves)


def isotropy_loops(initial, *, root=None):
    """Extract all necessary shape-loop generators without requiring GAP.

    Accept a complete ShapeGraph or a Shape/list to explore. A State supplies
    its reference specification, independently of scramble or reachability.
    QTM and HTM graphs are accepted; loop construction always uses QTM actions.
    The root is a vertex ID in the resulting fixed-frame graph, defaulting to
    zero. Passing an existing LoopGenerators preserves its root unless an
    explicitly different root is requested, which raises ValueError.
    """
    if root is not None and (isinstance(root, bool) or not isinstance(root, int)):
        raise TypeError("root must be an integer vertex ID")
    if isinstance(initial, LoopGenerators):
        if root is not None and root != initial.root_vertex:
            raise ValueError("root differs from the already extracted loop set")
        return initial
    root = 0 if root is None else root
    if isinstance(initial, State):
        initial = initial.specification
    graph = initial if isinstance(initial, ShapeGraph) else explore(initial)
    if not 0 <= root < len(graph):
        raise IndexError("root vertex ID out of range")
    return LoopGenerators(graph._native.isotropy_loops(root))


def analyze_isotropy(initial, *, gap_executable="gap", timeout=None, root=None):
    """Extract witnessed generators and ask GAP for exact group/component size."""
    loops = isotropy_loops(initial, root=root)
    return loops.analyze(gap_executable=gap_executable, timeout=timeout)
