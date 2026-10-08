"""Python research interface for the Rust bandaged-cube engine.

Cell indices use the legacy 27-cell grid. Moves use standard Singmaster
notation; shapes forget colors, while State retains cubie identities and
orientations. All moves return new values.
"""

from collections.abc import Sequence

from . import _native

BlockedMoveError = _native.BlockedMoveError

CELL_NAMES = (
    "UBL", "UB", "UBR", "UL", "U", "UR", "UFL", "UF", "UFR",
    "BL", "B", "BR", "L", "C", "R", "FL", "F", "FR",
    "DBL", "DB", "DBR", "DL", "D", "DR", "DFL", "DF", "DFR",
)
globals().update({name: index for index, name in enumerate(CELL_NAMES)})


def _labels(values):
    """Normalize arbitrary nonnegative labels before entering the u8 API."""
    values = list(values)
    if len(values) != 27:
        raise ValueError("a shape requires exactly 27 cell labels")
    mapping = {}
    result = []
    next_label = 1
    for label in values:
        if isinstance(label, bool) or not isinstance(label, int):
            raise TypeError("cell labels must be nonnegative integers")
        if label < 0:
            raise ValueError("cell labels must be nonnegative integers")
        if label == 0:
            result.append(next_label)
            next_label += 1
        else:
            if label not in mapping:
                mapping[label] = next_label
                next_label += 1
            result.append(mapping[label])
    return result


class Shape(Sequence):
    """An immutable connected partition, indexed by named cell constants.

    Every input zero denotes a different unbandaged cubie. Other labels name
    fused blocks and are normalized by first occurrence. The virtual core is
    cell C. A missing input constructs the unbandaged cube.
    """

    __slots__ = ("_native", "_labels")

    def __init__(self, labels=None):
        if isinstance(labels, Shape):
            native = labels._native
        elif isinstance(labels, _native.Shape):
            native = labels
        else:
            native = _native.Shape(_labels([0] * 27 if labels is None else labels))
        object.__setattr__(self, "_native", native)
        object.__setattr__(self, "_labels", tuple(native.labels))

    def __setattr__(self, name, value):
        raise AttributeError("Shape is immutable")

    def __delattr__(self, name):
        raise AttributeError("Shape is immutable")

    @property
    def labels(self):
        """A copy of the normalized 27-cell labels."""
        return list(self._labels)

    @property
    def legal_moves(self):
        return self._native.legal_moves

    def is_turnable(self, face):
        return self._native.is_turnable(face)

    def apply(self, moves):
        """Apply a checked sequence in standard notation, returning a Shape."""
        return Shape(self._native.apply(moves))

    @property
    def rotation_key(self):
        """Stable hexadecimal key identifying the 24 proper rotation variants."""
        return self._native.rotation_key

    def canonical(self):
        """Return the least bond encoding among the 24 proper rotations."""
        return Shape(self._native.canonical())

    def rotated(self, rotation):
        """Return one of the 24 proper spatial rotations; index 0 is identity."""
        if isinstance(rotation, bool) or not isinstance(rotation, int):
            raise TypeError("rotation must be an integer in 0..24")
        if rotation < 0 or rotation >= 24:
            raise ValueError("rotation must be an integer in 0..24")
        return Shape(self._native.rotated(rotation))

    def __len__(self):
        return 27

    def __getitem__(self, index):
        value = self._labels[index]
        return list(value) if isinstance(index, slice) else value

    def __iter__(self):
        return iter(self._labels)

    def __eq__(self, other):
        return isinstance(other, Shape) and self._labels == other._labels

    def __hash__(self):
        return hash(self._labels)

    def __repr__(self):
        return f"Shape({self.labels!r})"


class State:
    """An immutable colored cube with fixed reference bandage membership.

    Construct solved and apply legal turns, or import validated cubies/facelets.
    Imported states satisfy ordinary cube and rigid-block constraints; legal
    reachability from solved is a separate question for solve_colored().
    """

    __slots__ = ("_native", "_moves")

    def __init__(self, specification=None):
        if isinstance(specification, State):
            object.__setattr__(self, "_native", specification._native)
            object.__setattr__(self, "_moves", specification._moves)
            return
        initial = shape(Shape() if specification is None else specification)
        object.__setattr__(self, "_native", _native.State(initial.labels))
        object.__setattr__(self, "_moves", ())

    def __setattr__(self, name, value):
        raise AttributeError("State is immutable")

    def __delattr__(self, name):
        raise AttributeError("State is immutable")

    @classmethod
    def _from_native(cls, native, moves):
        result = object.__new__(cls)
        object.__setattr__(result, "_native", native)
        object.__setattr__(result, "_moves", moves)
        return result

    @classmethod
    def from_cubies(cls, specification=None, *, corners, twists, edges, flips):
        """Import Kociemba-ordered cubies, checking cube and rigid-block validity.

        This does not establish reachability under the bandaging. The imported
        state has no replay witness, so scramble is None.
        """
        def entries(values, name, length, bound):
            values = list(values)
            if len(values) != length:
                raise ValueError(f"{name} requires {length} entries")
            for value in values:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{name} entries must be integers")
                if not 0 <= value < bound:
                    raise ValueError(f"{name} entry out of range")
            return values
        if isinstance(specification, State):
            specification = specification.specification
        initial = shape(Shape() if specification is None else specification)
        native = _native.State.from_cubies(
            initial.labels, entries(corners, "corners", 8, 8),
            entries(twists, "twists", 8, 3), entries(edges, "edges", 12, 12),
            entries(flips, "flips", 12, 2))
        return cls._from_native(native, None)

    @classmethod
    def from_facelets(cls, facelets, specification=None):
        """Import 54 URFDLB facelets (nine per face, read row by row).

        Face letters name colors relative to fixed matching centers. Check
        ordinary-cube and rigid-block validity, independently of reachability.
        """
        if not isinstance(facelets, str):
            raise TypeError("facelets must be a 54-character string")
        if isinstance(specification, State):
            specification = specification.specification
        initial = shape(Shape() if specification is None else specification)
        return cls._from_native(_native.State.from_facelets(initial.labels, facelets), None)

    @property
    def facelets(self):
        """54 face letters in standard URFDLB order with fixed centers."""
        return self._native.facelets

    @property
    def sticker_permutation(self):
        """Source-to-destination images of 48 stickers, omitting fixed centers.

        Points are zero-based in URFDLB facelet order with centers omitted.
        Unlike cubie positions alone, this faithfully retains orientations.
        """
        return tuple(self._native.sticker_permutation)

    @property
    def shape(self):
        return Shape(self._native.shape)

    @property
    def specification(self):
        return Shape(self._native.specification)

    @property
    def hex_id(self):
        """Stable, collision-free ID for reference bandages and colored cubies.

        Uses the fixed URFDLB center frame and ignores replay history. Format
        v1 has 54 lowercase hex digits: 14 for the reference AxisMajor bonds,
        then eight corner bytes (3*identity + twist) and twelve edge bytes
        (2*identity + flip), both in Kociemba order.
        """
        return self._native.hex_id

    @property
    def scramble(self):
        """Validated solved-to-state witness, or None for an imported state."""
        return None if self._moves is None else " ".join(self._moves)

    @property
    def corners(self):
        return self._native.corners

    @property
    def twists(self):
        return self._native.twists

    @property
    def edges(self):
        return self._native.edges

    @property
    def flips(self):
        return self._native.flips

    @property
    def is_solved(self):
        return self._native.is_solved

    @property
    def legal_moves(self):
        return self._native.legal_moves

    def is_turnable(self, face):
        return self.shape.is_turnable(face)

    def apply(self, moves):
        native = self._native.apply(moves)
        witness = None if self._moves is None else self._moves + tuple(moves.split())
        return self._from_native(native, witness)

    def _key(self):
        return (self.specification, tuple(self.corners), tuple(self.twists),
                tuple(self.edges), tuple(self.flips))

    def __eq__(self, other):
        return isinstance(other, State) and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        if self._moves is None:
            return (f"State.from_cubies({self.specification.labels!r}, "
                    f"corners={self.corners!r}, twists={self.twists!r}, "
                    f"edges={self.edges!r}, flips={self.flips!r})")
        return f"State({self.specification.labels!r}).apply({self.scramble!r})"


def shape(value):
    """Accept a Shape, State, or ordinary 27-cell Python sequence."""
    if isinstance(value, Shape):
        return value
    if isinstance(value, State):
        return value.shape
    return Shape(value)


def normalize(labels):
    return shape(labels).labels


def do(value, moves):
    """Replay moves on a Shape/list or State, preserving the kind of state."""
    return value.apply(moves) if isinstance(value, State) else shape(value).apply(moves)


def fixture_names():
    return _native.fixture_names()


def fixture(name):
    return Shape(_native.fixture(name))


def explore(initial, *, metric="QTM", max_vertices=None):
    """Explore a whole shape component unless an explicit limit is supplied.

    Distances and paths in an incomplete result describe the retained graph
    and do not establish optimality or unreachability in the full component.
    """
    if max_vertices is not None:
        if isinstance(max_vertices, bool) or not isinstance(max_vertices, int):
            raise TypeError("max_vertices must be a positive integer or None")
        if max_vertices <= 0:
            raise ValueError("max_vertices must be positive")
    from .graph import ShapeGraph
    return ShapeGraph(_native.explore(shape(initial)._native, metric=metric,
                                     max_vertices=max_vertices))


def explore_colored(initial, *, metric="QTM", max_states=None):
    """Explore full colored states by exact BFS in a fixed frame.

    No implicit cap. An explicit cap returns a partial graph with complete=False;
    retained paths alone do not prove global optimality or unreachability.
    """
    if not isinstance(initial, State):
        raise TypeError("colored exploration requires a State")
    _positive_limit(max_states, "max_states")
    from .colored import ColoredGraph
    return ColoredGraph(_native.explore_colored(initial._native, metric=metric,
                                                max_states=max_states))


def solve_colored(initial, *, target=None, metric="QTM", algorithm="bidirectional",
                  max_states=None, max_depth=None):
    """Return an exact shortest colored solution, unreachability, or a cutoff.

    The default target is solved with the same reference bandage specification.
    QTM uses quarter/inverse turns, HTM also uses unit-cost half turns. Algorithm
    is 'bfs' or 'bidirectional'. max_depth bounds total solution cost, including
    zero; max_states bounds stored search records (both sides for bidirectional).
    There are no implicit limits. A cutoff never establishes unreachability.
    """
    if not isinstance(initial, State) or (target is not None and not isinstance(target, State)):
        raise TypeError("colored solving requires State inputs")
    _positive_limit(max_states, "max_states")
    if max_depth is not None:
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            raise TypeError("max_depth must be a nonnegative integer or None")
        if max_depth < 0:
            raise ValueError("max_depth must be nonnegative")
    from .colored import SearchResult
    return SearchResult(**_native.solve_colored(
        initial._native, target=None if target is None else target._native,
        metric=metric, algorithm=algorithm, max_states=max_states, max_depth=max_depth))


def _positive_limit(value, name):
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be a positive integer or None")
        if value <= 0:
            raise ValueError(f"{name} must be positive")


def _boolean(value, name):
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")


def _enumeration_options(core_bonds, strict_core_singleton):
    _boolean(core_bonds, "core_bonds")
    _boolean(strict_core_singleton, "strict_core_singleton")
    if core_bonds and strict_core_singleton:
        raise ValueError("core_bonds and strict_core_singleton cannot both be true")


def count_partitions(*, core_bonds=False, strict_core_singleton=False):
    """Count all cuboid partitions and proper-rotation classes exactly.

    By default a cuboid occupies its shell cells and leaves the virtual core
    independent. Set core_bonds=True for cuboids of the full 27-cell grid, or
    strict_core_singleton=True to require full cuboids avoiding the core.
    The returned dictionary includes the 24 Burnside fixed-point counts.
    """
    _enumeration_options(core_bonds, strict_core_singleton)
    return _native.count_partitions(core_bonds=core_bonds,
                                    strict_core_singleton=strict_core_singleton)


def cuboid_partitions(*, limit, core_bonds=False, strict_core_singleton=False):
    """Return an explicitly bounded, deterministic prefix as a list of Shapes."""
    _enumeration_options(core_bonds, strict_core_singleton)
    _positive_limit(limit, "limit")
    if limit is None:
        raise TypeError("limit must be a positive integer")
    return [Shape(value) for value in _native.cuboid_partitions(
        limit, core_bonds=core_bonds, strict_core_singleton=strict_core_singleton)]


def enumerate_puzzles(*, core_bonds=False, implicit_bonds=False, max_seeds=None,
                      max_component_vertices=None, strict_core_singleton=False):
    """Classify cuboid partitions by legal face turns and proper rotations.

    This scans the entire family unless explicit limits are supplied. A limit
    produces complete=False and a stop_reason; partial components do not enter
    the class count. Set implicit_bonds=True to identify behaviorally redundant
    adjacent bonds as well. Representatives are JSON-compatible records with
    labels, seed_labels, a stable hexadecimal id, and raw_component_vertices.
    """
    _enumeration_options(core_bonds, strict_core_singleton)
    _boolean(implicit_bonds, "implicit_bonds")
    _positive_limit(max_seeds, "max_seeds")
    _positive_limit(max_component_vertices, "max_component_vertices")
    return _native.enumerate_puzzles(
        core_bonds=core_bonds, implicit_bonds=implicit_bonds,
        max_seeds=max_seeds, max_component_vertices=max_component_vertices,
        strict_core_singleton=strict_core_singleton)


def close_implicit(initial, *, core_bonds=False, max_vertices=None):
    """Add every admitted implicit adjacency, returning a Shape.

    Exploration must finish before closure can be established. An explicit
    vertex limit that cuts the component short raises ValueError. The default
    model requires the virtual core to be an independent cell.
    """
    _boolean(core_bonds, "core_bonds")
    _positive_limit(max_vertices, "max_vertices")
    return Shape(_native.close_implicit(shape(initial)._native,
                                       core_bonds=core_bonds,
                                       max_vertices=max_vertices))


def draw_cubes(cubes, **kwargs):
    """Draw 3D shapes or colored States, optionally from opposite corners."""
    from .graphics import draw_cubes as draw
    return draw(cubes, **kwargs)


def draw_net(state, **kwargs):
    """Draw all colored stickers and current face bandages as an unfolded net."""
    from .graphics import draw_net as draw
    return draw(state, **kwargs)


from .persistence import load_puzzle, save_puzzle, save_graph  # noqa: E402
from .graph import ShapeGraph  # noqa: E402
from .colored import ColoredGraph, SearchResult  # noqa: E402
from .signatures import (  # noqa: E402
    BLOCK_TYPES, Block, BlockType, block_signature, classify_blocks, format_signature,
)
from .atlas import PuzzleAtlas  # noqa: E402
from .isotropy import (  # noqa: E402
    IsotropyAnalysis, LoopGenerator, LoopGenerators, analyze_isotropy, isotropy_loops,
)
from .gap_backend import GapError  # noqa: E402
from .loop_solver import LoopSolution, LoopSolver, LoopStep, solve_colored_loops  # noqa: E402

__all__ = [
    "Shape", "State", "ShapeGraph", "BlockedMoveError", "CELL_NAMES",
    "shape", "normalize", "do", "fixture", "fixture_names", "explore",
    "count_partitions", "cuboid_partitions", "enumerate_puzzles", "close_implicit",
    "BLOCK_TYPES", "Block", "BlockType", "block_signature", "classify_blocks", "format_signature",
    "PuzzleAtlas",
    "LoopGenerator", "LoopGenerators", "IsotropyAnalysis", "GapError",
    "isotropy_loops", "analyze_isotropy",
    "LoopSolver", "LoopSolution", "LoopStep", "solve_colored_loops",
    "draw_cubes", "load_puzzle", "save_puzzle", "save_graph",
] + list(CELL_NAMES)
