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
    """A colored cube with fixed bandage membership and a legal replay witness.

    Construct from the puzzle's solved reference shape, then use apply() to
    scramble it. Arbitrary colored-state import is not supported.
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

    @property
    def shape(self):
        return Shape(self._native.shape)

    @property
    def specification(self):
        return Shape(self._native.specification)

    @property
    def scramble(self):
        """The validated sequence from the solved reference state."""
        return " ".join(self._moves)

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
        return self._from_native(native, self._moves + tuple(moves.split()))

    def _key(self):
        return (self.specification, tuple(self.corners), tuple(self.twists),
                tuple(self.edges), tuple(self.flips))

    def __eq__(self, other):
        return isinstance(other, State) and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
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
    """Draw a shape or gallery with the optional matplotlib extra."""
    from .graphics import draw_cubes as draw
    return draw(cubes, **kwargs)


from .persistence import load_puzzle, save_puzzle, save_graph  # noqa: E402
from .graph import ShapeGraph  # noqa: E402

__all__ = [
    "Shape", "State", "ShapeGraph", "BlockedMoveError", "CELL_NAMES",
    "shape", "normalize", "do", "fixture", "fixture_names", "explore",
    "count_partitions", "cuboid_partitions", "enumerate_puzzles", "close_implicit",
    "draw_cubes", "load_puzzle", "save_puzzle", "save_graph",
] + list(CELL_NAMES)
