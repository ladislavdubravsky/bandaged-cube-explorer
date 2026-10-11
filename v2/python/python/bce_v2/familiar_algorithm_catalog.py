"""Verified familiar outer-face words and exact bandage obstructions.

This bounded vocabulary contains every adjacent two-face commutator with
quarter, inverse-quarter or half turns and powers 1–3, plus selected nested
commutators, OLLs, PLLs, edge cycles and pure edge flips. Proper rotations
relabel physical words without assuming a symmetry of any bandage. Inverse
words are deduplicated because their *closed* availability is equivalent;
different words with the same ordinary-cube action remain separate.

Obstructions describe raw words, before cancellation. A saturated adjacency
mask includes invisible core bonds. A connected block is split precisely when
one of its original adjacencies is split, so forbidden bonds determine exact
legality and the surviving bond images determine exact endpoint closure.
"""

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations_with_replacement

from . import BlockedMoveError, State, Shape, shape
from ._moves import _simplified_moves
from .computation import checkpoint
from .loop_rotations import bandage_symmetries, normalize_rotation, rotate_moves


# Independent axis-major encoding, rather than the native layout's raw bits.
# All 54 full-grid adjacencies are retained, including the six core bonds.
BONDS = tuple((cell, cell + stride)
              for stride in (9, 3, 1)
              for cell in range(27) if (cell // stride) % 3 < 2)
_ALL_BONDS = (1 << len(BONDS)) - 1


def _word(word):
    if not isinstance(word, str):
        raise TypeError("algorithm word must be a face-turn string")
    tokens = word.split()
    if any(token[0] not in "URFDLB" or token[1:] not in ("", "'", "2")
           for token in tokens):
        raise ValueError("algorithm word must use outer-face Singmaster notation")
    return " ".join(tokens)


def _inverse_word(word):
    return " ".join(token if token.endswith("2") else token[:-1]
                    if token.endswith("'") else token + "'"
                    for token in reversed(word.split()))


def _commutator(first, second):
    return _simplified_moves(" ".join(
        (first, second, _inverse_word(first), _inverse_word(second))).split())


def _bond_mask(bits):
    if type(bits) is not int:
        raise TypeError("bond mask must be an integer")
    if not 0 <= bits <= _ALL_BONDS:
        raise ValueError("bond mask must fit the 54 full-grid adjacencies")
    return bits


def shape_bond_bits(specification):
    """Return saturated axis-major adjacency bits, including core bonds."""
    labels = shape(specification)
    return sum(1 << index for index, (first, second) in enumerate(BONDS)
               if labels[first] == labels[second])


@dataclass(frozen=True)
class OrdinaryAlgorithmEffect:
    """Exact native Kociemba cubies and faithful 48-sticker images."""

    corners: tuple[int, ...]
    twists: tuple[int, ...]
    edges: tuple[int, ...]
    flips: tuple[int, ...]
    sticker_permutation: tuple[int, ...]

    def __post_init__(self):
        for name, length, bound in (("corners", 8, 8), ("twists", 8, 3),
                                    ("edges", 12, 12), ("flips", 12, 2),
                                    ("sticker_permutation", 48, 48)):
            values = tuple(getattr(self, name))
            if (len(values) != length or
                    any(type(value) is not int or not 0 <= value < bound for value in values)):
                raise ValueError(f"invalid ordinary algorithm {name}")
            if name in ("corners", "edges", "sticker_permutation") and len(set(values)) != length:
                raise ValueError(f"ordinary algorithm {name} must be a permutation")
            object.__setattr__(self, name, values)

    @property
    def corner_moved(self):
        return sum(index != value for index, value in enumerate(self.corners))

    @property
    def corner_twisted(self):
        return sum(bool(value) for value in self.twists)

    @property
    def edge_moved(self):
        return sum(index != value for index, value in enumerate(self.edges))

    @property
    def edge_flipped(self):
        return sum(bool(value) for value in self.flips)

    @property
    def is_identity(self):
        return self.sticker_permutation == tuple(range(48))

    def to_dict(self):
        return {"corners": list(self.corners), "twists": list(self.twists),
                "edges": list(self.edges), "flips": list(self.flips),
                "sticker_permutation": list(self.sticker_permutation),
                "corner_moved": self.corner_moved, "corner_twisted": self.corner_twisted,
                "edge_moved": self.edge_moved, "edge_flipped": self.edge_flipped}


@lru_cache(maxsize=2048)
def _ordinary_effect(word):
    state = State().apply(word)
    return OrdinaryAlgorithmEffect(tuple(state.corners), tuple(state.twists),
                                   tuple(state.edges), tuple(state.flips),
                                   state.sticker_permutation)


@dataclass(frozen=True)
class FamiliarAlgorithm:
    """An immutable physical word with independently verified ordinary effect.

    Base templates and their physical forms use the same type. ``rotation``
    and ``inverse`` explain a form's relationship to its ``base_id``; they
    never transform its executable ``word`` a second time. Orientation labels
    belong to this exact form, not to every bandaged conjugate of the form.
    """

    id: str
    base_id: str
    family: str
    rotation: str
    inverse: bool
    word: str
    htm: int
    ordinary_effect: OrdinaryAlgorithmEffect

    def __post_init__(self):
        for name in ("id", "base_id", "family"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"algorithm {name} must be a nonempty string")
        word = _word(self.word)
        if type(self.htm) is not int or self.htm != len(word.split()):
            raise ValueError("algorithm HTM length must match its physical word")
        if type(self.inverse) is not bool:
            raise TypeError("algorithm inverse must be a bool")
        if self.ordinary_effect != _ordinary_effect(word):
            raise ValueError("algorithm ordinary effect must match native replay")
        object.__setattr__(self, "word", word)
        object.__setattr__(self, "rotation", normalize_rotation(self.rotation))

    @classmethod
    def from_word(cls, word, *, id="custom", base_id=None, family="custom",
                  rotation="", inverse=False):
        """Create a verified form for a custom bounded vocabulary."""
        word = _word(word)
        return cls(id, id if base_id is None else base_id, family, rotation, inverse,
                   word, len(word.split()), _ordinary_effect(word))

    @property
    def permutation(self):
        return self.ordinary_effect.sticker_permutation

    @property
    def obstruction(self):
        """Compile once on first use; retain raw physical-word legality."""
        return compile_word_obstruction(self.word)

    def to_dict(self):
        return {"id": self.id, "base_id": self.base_id, "family": self.family,
                "rotation": self.rotation, "inverse": self.inverse,
                "word": self.word, "htm": self.htm,
                "ordinary_cube_effect": self.ordinary_effect.to_dict()}


@dataclass(frozen=True)
class FamiliarAlgorithmCatalog:
    """Verified bases and physical forms, deterministically ordered."""

    base_templates: tuple[FamiliarAlgorithm, ...]
    variants: tuple[FamiliarAlgorithm, ...]
    excluded_identity_bases: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("base_templates", "variants"):
            entries = tuple(getattr(self, name))
            if any(not isinstance(entry, FamiliarAlgorithm) for entry in entries):
                raise TypeError(f"catalog {name} must contain verified FamiliarAlgorithm values")
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError(f"catalog {name} must have unique algorithm IDs")
            object.__setattr__(self, name, entries)
        excluded = tuple(self.excluded_identity_bases)
        if any(not isinstance(identifier, str) for identifier in excluded):
            raise TypeError("excluded catalog IDs must be strings")
        object.__setattr__(self, "excluded_identity_bases", excluded)

    def __iter__(self):
        return iter(self.variants)

    def __len__(self):
        return len(self.variants)

    def to_dict(self):
        return {"base_templates": [entry.to_dict() for entry in self.base_templates],
                "variants": [entry.to_dict() for entry in self.variants],
                "excluded_identity_bases": list(self.excluded_identity_bases)}


@dataclass(frozen=True)
class WordObstruction:
    """Exact forbidden adjacencies and final bond action of one raw word.

    ``destinations[i]`` is the one-bit image of bond i, or zero if that bond
    blocks any prefix. Bits use ``BONDS`` order. Endpoint methods return None
    for illegal inputs and never silently simplify blocked cancellation.
    """

    word: str
    forbidden_bonds: int
    destinations: tuple[int, ...]

    def __post_init__(self):
        word = _word(self.word)
        forbidden = _bond_mask(self.forbidden_bonds)
        destinations = tuple(self.destinations)
        if len(destinations) != len(BONDS):
            raise ValueError("word obstruction requires 54 bond destinations")
        for index, destination in enumerate(destinations):
            _bond_mask(destination)
            if (destination.bit_count() != (0 if forbidden & (1 << index) else 1)):
                raise ValueError("word obstruction destinations must agree with forbidden bonds")
        object.__setattr__(self, "word", word)
        object.__setattr__(self, "destinations", destinations)

    def is_legal_bits(self, bits):
        return not (_bond_mask(bits) & self.forbidden_bonds)

    def endpoint_bits(self, bits):
        bits = _bond_mask(bits)
        if bits & self.forbidden_bonds:
            return None
        endpoint = 0
        while bits:
            lowest = bits & -bits
            endpoint |= self.destinations[lowest.bit_length() - 1]
            bits ^= lowest
        return endpoint

    def is_closed_bits(self, bits):
        return self.endpoint_bits(bits) == bits

    def is_legal(self, specification):
        return self.is_legal_bits(shape_bond_bits(specification))

    def is_closed(self, specification):
        return self.is_closed_bits(shape_bond_bits(specification))


def compile_word_obstruction(word):
    """Compile native single-bond replay, cached by the normalized raw word.

    Whitespace is normalized but physical turns are never cancelled. Each
    replay independently checks one adjacency; native shape validation then
    guarantees its image remains exactly one bond when the word is legal.
    """
    return _compiled_obstruction(_word(word))


@lru_cache(maxsize=2048)
def _compiled_obstruction(word):
    forbidden, destinations = 0, []
    for index, (first, second) in enumerate(BONDS):
        checkpoint("familiar_obstructions", bond=index, bond_count=len(BONDS))
        labels = [0] * 27
        labels[first] = labels[second] = 1
        try:
            endpoint = Shape(labels).apply(word)
        except BlockedMoveError:
            forbidden |= 1 << index
            destinations.append(0)
        else:
            image = shape_bond_bits(endpoint)
            if image.bit_count() != 1:
                raise AssertionError("a legal single bond must remain a single bond")
            destinations.append(image)
    return WordObstruction(word, forbidden, tuple(destinations))


@lru_cache(maxsize=1)
def familiar_algorithm_catalog():
    """Return the shared verified catalog: 27 bases and 552 physical forms.

    Catalog construction verifies every exact ordinary action with the native
    colored engine. Obstructions are compiled lazily, so a bounded discovery
    can stop without preparing unused forms. Cache values are immutable.
    """
    seeds = []
    for first, second in combinations_with_replacement(("", "'", "2"), 2):
        body = _commutator("R" + first, "U" + second)
        for power in (1, 2, 3):
            seeds.append((f"comm_R{first}_U{second}_power{power}",
                          "two_face_commutator",
                          _simplified_moves(" ".join([body] * power).split())))
    for power in (1, 2):
        body = " ".join([_commutator("R", "U")] * power)
        seeds.append((f"nested_comm_power{power}_D", "nested_commutator",
                      _commutator(body, "D")))
    seeds.extend((
        ("edge_3cycle", "edge_cycle", "R2 U R U R' U' R' U' R' U R'"),
        ("edge_orientation_OLL", "OLL", "R U R' U' R' F R F'"),
        ("pure_opposite_edge_flip", "edge_flip",
         "R' L F R' L D R' L B2 L' R D L' R F L' R U2"),
        ("pure_adjacent_edge_flip", "edge_flip",
         "L F R' F' L' R U R U' R' B U' B U B U B U' B' U' B2"),
        ("sune", "OLL", "R U R' U R U2 R'"),
        ("H_corner_OLL", "OLL", "R U R' U R U' R' U R U2 R'"),
        ("T_PLL", "PLL", "R U R' U' R' F R2 U' R' U' R U R' F'"),
        ("Jb_PLL", "PLL", "R U R' F' R U R' U' R' F R2 U' R' U'"),
    ))
    bases, excluded = [], []
    for identifier, family, word in seeds:
        checkpoint("familiar_catalog", base=identifier)
        entry = FamiliarAlgorithm.from_word(word, id=identifier, family=family)
        if entry.ordinary_effect.is_identity:
            excluded.append(identifier)
        else:
            bases.append(entry)
    variants = {}
    rotations = ("", *bandage_symmetries(Shape()))
    for base in bases:
        for rotation in rotations:
            checkpoint("familiar_catalog", base=base.id, rotation=rotation)
            rotated = rotate_moves(base.word, rotation)
            word = min(rotated, _inverse_word(rotated))
            if word not in variants:
                variants[word] = FamiliarAlgorithm.from_word(
                    word, id=f"A{len(variants) + 1}", base_id=base.id,
                    family=base.family, rotation=rotation, inverse=word != rotated)
    return FamiliarAlgorithmCatalog(tuple(bases), tuple(variants.values()), tuple(excluded))


__all__ = ["FamiliarAlgorithm", "FamiliarAlgorithmCatalog", "OrdinaryAlgorithmEffect",
           "WordObstruction", "familiar_algorithm_catalog", "compile_word_obstruction",
           "shape_bond_bits"]
