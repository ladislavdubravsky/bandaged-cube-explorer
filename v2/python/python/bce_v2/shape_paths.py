"""Checked open paths in the fixed-frame shape groupoid.

An open path is not an isotropy generator: it has two exact shape endpoints.
Its 48-sticker action describes physical turns in the fixed world axes, and
``frame`` records only how to display those turns.  No move is transformed a
second time when a path is constructed, composed, or deserialized.

Regripping by rho transforms *both* physical endpoints by inverse rho, just
like ``rotate_moves`` transforms face normals.  This permits a path to be
reused at a different oriented shape without asserting a symmetry of either
endpoint.  Closing and transporting a local loop still does not establish an
original-generator certificate; lowering to LoopExpression requires one.
"""

from dataclasses import dataclass
import json
from numbers import Integral
from pathlib import Path
import re

from . import BlockedMoveError, Shape, State, shape
from ._moves import _simplified_moves
from .block_actions import _ROTATIONS
from .loop_rotations import (
    inverse_rotation, normalize_rotation, rotate_moves, rotate_permutation,
    rotation_tuple,
)


_IDENTITY = tuple(range(48))
_MOVE = re.compile(r"[URFDLB](?:2|')?")
_METADATA = {
    "format": "bce-v2-shape-path", "version": 1,
    "model": "full-grid-27-fixed-centers", "notation": "Singmaster",
    "permutation_degree": 48, "permutation_index_base": 0,
    "permutation_point_order": "URFDLB-without-centers",
    "permutation_action": "source-to-destination",
    "permutation_composition": "execution-order",
    "frame_convention": "presentation-only; physical moves and endpoints",
}


def _word(moves):
    if not isinstance(moves, str):
        raise TypeError("path moves must be a face-turn string")
    if any(_MOVE.fullmatch(move) is None for move in moves.split()):
        raise ValueError("path moves must use outer-face Singmaster notation")
    return " ".join(moves.split())


def _permutation(images):
    try:
        images = tuple(images)
    except TypeError:
        raise TypeError("path permutation must contain 48 integer images") from None
    if (len(images) != 48 or any(isinstance(image, bool) or
                               not isinstance(image, Integral) for image in images)
            or set(images) != set(range(48))):
        raise ValueError("path permutation must be a bijection of 0..47")
    return tuple(map(int, images))


def _inverse_word(moves):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(moves.split()))


def _inverse_action(images):
    result = [0] * len(images)
    for source, target in enumerate(images):
        result[target] = source
    return tuple(result)


def _reference(generators):
    # Preserve an existing nonzero graph root.  An open path has no authority
    # to silently explore another root or invent original-loop witnesses.
    from .loop_algorithms import _loops_from_records

    return _loops_from_records(generators)


@dataclass(frozen=True)
class ShapePath:
    """Immutable, independently replayed physical path with typed endpoints.

    ``source_shape`` and ``target_shape`` are exact partitions, including core
    bonds; equality up to rotation is not sufficient for composition.  The
    optional canonical ``frame`` changes presentation only.  Directly supplied
    endpoints and permutations are verified, rather than trusted assertions.
    """

    source_shape: Shape
    target_shape: Shape
    moves: str
    permutation: tuple[int, ...]
    frame: str = ""

    def __post_init__(self):
        source, target = shape(self.source_shape), shape(self.target_shape)
        word = _word(self.moves)
        images = _permutation(self.permutation)
        frame = normalize_rotation(self.frame)
        # Check the supplied word before simplifying: an illegal R R' cannot
        # become a valid empty path by cancellation on an immobile bandage.
        try:
            replay = State(source).apply(word)
        except BlockedMoveError as error:
            raise ValueError("path moves are blocked at the source shape") from error
        if replay.shape != target:
            raise ValueError("path moves do not reach the declared target shape")
        if replay.sticker_permutation != images:
            raise ValueError("path moves do not match the declared sticker action")
        object.__setattr__(self, "source_shape", source)
        object.__setattr__(self, "target_shape", target)
        object.__setattr__(self, "moves", _simplified_moves(word.split()))
        object.__setattr__(self, "permutation", images)
        object.__setattr__(self, "frame", frame)

    @classmethod
    def from_moves(cls, source_shape, moves, *, frame=""):
        """Replay physical face turns and infer the target and faithful action."""
        source = shape(source_shape)
        word = _word(moves)
        try:
            replay = State(source).apply(word)
        except BlockedMoveError as error:
            raise ValueError("path moves are blocked at the source shape") from error
        return cls(source, replay.shape, word, replay.sticker_permutation, frame)

    @classmethod
    def identity(cls, reference, *, frame=""):
        return cls(reference, reference, "", _IDENTITY, frame)

    @classmethod
    def local_loop(cls, source_shape, moves, *, frame=""):
        """Build a checked loop at any shape, without claiming root provenance."""
        result = cls.from_moves(source_shape, moves, frame=frame)
        if not result.is_closed:
            raise ValueError("local loop must return to its source shape")
        return result

    @classmethod
    def from_graph(cls, graph, source=0, target=0, *, frame=""):
        """Use a graph's checked shortest transport, retaining exact endpoints."""
        source_id, target_id = graph._vertex(source), graph._vertex(target)
        return cls.from_moves(graph[source_id], graph.shortest_path(source_id, target_id),
                              frame=frame)

    @classmethod
    def from_transport(cls, generators, vertex, *, frame=""):
        """Build a native loop library's tree transport from its actual root.

        Portable original-loop records retain legal loop words but do not
        retain their shape graph or its tree paths.  Use ``from_graph`` with
        an explicit verified graph to construct transport for those records.
        """
        loops = _reference(generators)
        if not callable(getattr(loops._native, "transport", None)):
            raise ValueError("tree transport requires a native loop library; portable loop "
                             "records do not retain graph paths (use from_graph instead)")
        return cls.from_moves(loops.root_shape, loops.transport(vertex), frame=frame)

    @property
    def is_closed(self):
        return self.source_shape == self.target_shape

    @property
    def turn_sequence(self):
        return self.moves

    @property
    def htm_length(self):
        return len(self.moves.split())

    @property
    def qtm_length(self):
        return sum(2 if move.endswith("2") else 1 for move in self.moves.split())

    @property
    def displayed_moves(self):
        """Face spelling in ``frame``; physical execution remains ``moves``."""
        return rotate_moves(self.moves, inverse_rotation(self.frame))

    def then(self, other):
        """Compose in execution order; shape and presentation axes must agree."""
        if not isinstance(other, ShapePath):
            raise TypeError("path composition requires a ShapePath")
        if self.target_shape != other.source_shape:
            raise ValueError("path composition requires identical endpoint shapes")
        if self.frame != other.frame:
            raise ValueError("path composition requires identical presentation frames")
        images = tuple(other.permutation[point] for point in self.permutation)
        return type(self)(self.source_shape, other.target_shape,
                          (self.moves + " " + other.moves).strip(), images, self.frame)

    def inverse(self):
        """Reverse the physical witness, exchanging its exact endpoints."""
        return type(self)(self.target_shape, self.source_shape, _inverse_word(self.moves),
                          _inverse_action(self.permutation), self.frame)

    def reframed(self, frame):
        """Change display axes explicitly, with no physical action or shape change."""
        return type(self)(self.source_shape, self.target_shape, self.moves,
                          self.permutation, frame)

    def rotated(self, rotation):
        """Transfer geometry by a proper regrip, whether or not it is a symmetry.

        In ``rho (displayed word) rho^-1``, a normal is transformed by inverse
        rho.  Endpoint partitions use the same inverse spatial transform.  The
        frame composition is written ``rho old_frame``, whose spatial action
        is old_frame after rho; this also preserves ``displayed_moves`` under
        successive noncommuting regrips.
        """
        rotation = normalize_rotation(rotation)
        spatial = rotation_tuple(inverse_rotation(rotation))
        index = _ROTATIONS.index(spatial)
        return type(self)(self.source_shape.rotated(index), self.target_shape.rotated(index),
                          rotate_moves(self.moves, rotation),
                          rotate_permutation(self.permutation, rotation),
                          normalize_rotation((rotation + " " + self.frame).strip()))

    def transport_loop(self, local_loop):
        """Return setup, local body, setup inverse at this path's source shape.

        Useful action can live at any reachable shape.  The body must be a
        closed typed path at this setup's target, in the same frame.  No loop
        generator certificate is inferred from shape closure alone.
        """
        if not isinstance(local_loop, ShapePath):
            raise TypeError("transported body must be a ShapePath")
        if not local_loop.is_closed:
            raise ValueError("transported body must be a closed local loop")
        return self.then(local_loop).then(self.inverse())

    def to_loop_expression(self, witness, generators, *, max_expanded_moves=100_000):
        """Lower a reference loop to literal turns with a checked certificate.

        A legal local loop or a transported loop supplies a physical witness,
        but an original-loop expression with the same faithful effect is still
        required.  The library's exact root, including a nonzero graph root,
        is retained.  Frame metadata never alters the physical lowered turns.
        """
        from .loop_algorithms import LoopExpression

        if not isinstance(witness, LoopExpression):
            raise TypeError("loop certificate must be a LoopExpression")
        loops = _reference(generators)
        if not self.is_closed or self.source_shape != loops.root_shape:
            raise ValueError("only a closed path at the loop reference root can be lowered")
        certified_moves = witness.expanded_moves(loops, max_expanded_moves=max_expanded_moves)
        certified = State(loops.root_shape).apply(certified_moves)
        if (certified.shape != loops.root_shape or
                certified.sticker_permutation != self.permutation):
            raise ValueError("path does not match its original-loop certificate")
        return LoopExpression.turns(self.moves, witness)

    def to_dict(self):
        """Portable physical witness, with independently checkable declarations."""
        return {**_METADATA, "source_shape": self.source_shape.labels,
                "target_shape": self.target_shape.labels, "moves": self.moves,
                "permutation": list(self.permutation), "frame": self.frame}

    @classmethod
    def from_dict(cls, record):
        """Load only a recognized schema and independently replay its witness."""
        if not isinstance(record, dict):
            raise TypeError("path record must be a dictionary")
        expected = set(_METADATA) | {"source_shape", "target_shape", "moves", "permutation", "frame"}
        if set(record) != expected:
            raise ValueError("path record has missing or unexpected fields")
        for key, value in _METADATA.items():
            if record[key] != value or type(record[key]) is not type(value):
                raise ValueError(f"unsupported path metadata {key!r}")
        return cls(record["source_shape"], record["target_shape"], record["moves"],
                   record["permutation"], record["frame"])

    def to_json(self, path=None):
        result = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(result, encoding="utf-8")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path):
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


__all__ = ["ShapePath"]
