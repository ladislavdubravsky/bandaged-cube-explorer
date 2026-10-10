"""Portable, exact membership certificates for witnessed permutation groups.

A certificate stores a base and strong generators, rather than every group
element.  The words of its strong generators use an ambient original generator
library.  Checking those words proves ambient containment; orbit closure and
Schreier generators independently certify the represented group's exact order.

Subgroup certificates need a separate check that they are the desired feature
stabilizer: ambient containment, fixed features and the orbit--stabilizer order
identity provide that check.  ``input_generators`` certify containment of the
requested subgroup inputs, not equality with those inputs on their own.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from numbers import Integral
from types import MappingProxyType
from typing import Mapping


_SCHEMA = "bce.permutation_group_certificate.v1"


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{label} must be an integer")
    return int(value)


def _permutation(value, degree, label):
    try:
        permutation = tuple(_integer(point, label) for point in value)
    except TypeError as error:
        raise TypeError(f"{label} must be an integer sequence") from error
    if len(permutation) != degree or set(permutation) != set(range(degree)):
        raise ValueError(f"{label} must be a bijection of 0..{degree - 1}")
    return permutation


def _compose(first, second):
    """Execute first, then second, matching the puzzle and GAP conventions."""
    return tuple(second[image] for image in first)


def _inverse(permutation):
    inverse = [0] * len(permutation)
    for point, image in enumerate(permutation):
        inverse[image] = point
    return tuple(inverse)


def _power(permutation, exponent):
    if exponent < 0:
        permutation, exponent = _inverse(permutation), -exponent
    result = tuple(range(len(permutation)))
    while exponent:
        if exponent & 1:
            result = _compose(result, permutation)
        exponent >>= 1
        if exponent:
            permutation = _compose(permutation, permutation)
    return result


@dataclass(frozen=True)
class StrongGenerator:
    """A permutation and a word in the ambient original generator library."""

    permutation: tuple[int, ...]
    syllables: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class StabilizerLevel:
    """One base point, with all strong generators fixing earlier base points."""

    base_point: int
    generator_indices: tuple[int, ...]


@dataclass(frozen=True)
class _OrbitLevel:
    base_point: int
    transversals: Mapping[int, tuple[int, ...]]
    inverses: Mapping[int, tuple[int, ...]]


@dataclass(frozen=True, init=False)
class PermutationGroupCertificate:
    """An independently checked BSGS certificate with offline membership.

    Every level contains *all* pool generators fixing its earlier base points.
    This prevents an alleged deeper stabilizer from silently adding elements to
    its parent.  Point orbits and transversals are reconstructed by breadth-first
    traversal of those generators.  No operation enumerates group elements.

    For a full-group certificate, leave ``input_generators`` unspecified: every
    ambient original generator must sift to identity, proving equality with the
    witnessed strong-generator group.  For a subgroup, supply that subgroup's
    input permutations, and certify its feature-stabilizer identity separately.
    """

    root_generators: tuple[tuple[int, ...], ...]
    strong_generators: tuple[StrongGenerator, ...]
    levels: tuple[StabilizerLevel, ...]
    input_generators: tuple[tuple[int, ...], ...]
    degree: int
    order: int
    _orbit_levels: tuple[_OrbitLevel, ...]

    def __init__(self, root_generators, strong_generators, levels, *,
                 input_generators=None, degree=None):
        roots, generators, supplied_levels = (
            tuple(root_generators), tuple(strong_generators), tuple(levels)
        )
        if degree is None:
            degree = len(roots[0]) if roots else (
                len(generators[0].permutation) if generators else 48
            )
        degree = _integer(degree, "certificate degree")
        if degree < 1:
            raise ValueError("certificate degree must be positive")
        identity = tuple(range(degree))
        roots = tuple(_permutation(value, degree, f"root generator {index}")
                      for index, value in enumerate(roots))
        inputs = roots if input_generators is None else tuple(
            _permutation(value, degree, f"input generator {index}")
            for index, value in enumerate(input_generators)
        )
        witnessed = []
        powers = {}
        for index, generator in enumerate(generators):
            if not isinstance(generator, StrongGenerator):
                raise TypeError("strong generators must be StrongGenerator records")
            permutation = _permutation(generator.permutation, degree,
                                       f"strong generator {index}")
            syllables, value = [], identity
            for syllable in generator.syllables:
                if len(syllable) != 2:
                    raise ValueError("generator witness syllables need index and exponent")
                root_index = _integer(syllable[0], "witness generator index")
                exponent = _integer(syllable[1], "witness exponent")
                if not 0 <= root_index < len(roots):
                    raise ValueError("generator witness index is out of range")
                if exponent == 0:
                    raise ValueError("generator witness exponents must be nonzero")
                key = root_index, exponent
                if key not in powers:
                    powers[key] = _power(roots[root_index], exponent)
                value = _compose(value, powers[key])
                syllables.append(key)
            if value != permutation:
                raise ValueError(f"strong generator {index} witness has the wrong effect")
            witnessed.append(StrongGenerator(permutation, tuple(syllables)))
        generators = tuple(witnessed)
        normalized_levels, orbit_levels, previous = [], [], []
        for number, level in enumerate(supplied_levels):
            if not isinstance(level, StabilizerLevel):
                raise TypeError("levels must be StabilizerLevel records")
            base = _integer(level.base_point, "base point")
            if not 0 <= base < degree or base in previous:
                raise ValueError("base points must be distinct points in the action")
            indices = tuple(_integer(index, "strong generator index")
                            for index in level.generator_indices)
            if len(set(indices)) != len(indices):
                raise ValueError("level strong generator indices must be distinct")
            expected = {index for index, generator in enumerate(generators)
                        if all(generator.permutation[point] == point
                               for point in previous)}
            if set(indices) != expected:
                raise ValueError(f"level {number} must contain all strong generators "
                                 "fixing the previous base points")
            level_generators = tuple(generators[index].permutation for index in indices)
            transversals = {base: identity}
            queue = deque([base])
            while queue:
                point = queue.popleft()
                representative = transversals[point]
                for generator in level_generators:
                    image = generator[point]
                    if image not in transversals:
                        transversals[image] = _compose(representative, generator)
                        queue.append(image)
            if len(transversals) == 1:
                raise ValueError("certificate base levels must have nontrivial orbits")
            normalized_levels.append(StabilizerLevel(base, indices))
            orbit_levels.append(_OrbitLevel(
                base, MappingProxyType(transversals),
                MappingProxyType({point: _inverse(value)
                                  for point, value in transversals.items()}),
            ))
            previous.append(base)
        if any(generator.permutation != identity
               and all(generator.permutation[point] == point for point in previous)
               for generator in generators):
            raise ValueError("certificate terminal stabilizer is not trivial")
        object.__setattr__(self, "root_generators", roots)
        object.__setattr__(self, "strong_generators", generators)
        object.__setattr__(self, "levels", tuple(normalized_levels))
        object.__setattr__(self, "input_generators", inputs)
        object.__setattr__(self, "degree", degree)
        object.__setattr__(self, "_orbit_levels", tuple(orbit_levels))
        order = 1
        for orbit_level in orbit_levels:
            order *= len(orbit_level.transversals)
        object.__setattr__(self, "order", order)
        # Schreier's lemma proves every reconstructed orbit stabilizer equals
        # the next represented subgroup.  Inverses need not be additional
        # generators: these are finite permutation groups.
        for number, (level, orbit_level) in enumerate(zip(self.levels, orbit_levels)):
            seen = set()
            for point, representative in orbit_level.transversals.items():
                for index in level.generator_indices:
                    generator = generators[index].permutation
                    schreier = _compose(
                        _compose(representative, generator),
                        orbit_level.inverses[generator[point]],
                    )
                    if schreier == identity or schreier in seen:
                        continue
                    seen.add(schreier)
                    if self._sift(schreier, number + 1) != identity:
                        raise ValueError(f"level {number} Schreier generator is absent "
                                         "from the next stabilizer")
        for generator in inputs:
            if self._sift(generator) != identity:
                raise ValueError("input generator is absent from the certified group")

    @property
    def base(self):
        return tuple(level.base_point for level in self.levels)

    @property
    def orbit_sizes(self):
        return tuple(len(level.transversals) for level in self._orbit_levels)

    def _sift(self, permutation, start=0):
        remainder = permutation
        for level in self._orbit_levels[start:]:
            image = remainder[level.base_point]
            if image == level.base_point:
                continue
            inverse = level.inverses.get(image)
            if inverse is None:
                return remainder
            remainder = _compose(remainder, inverse)
        return remainder

    def sift(self, permutation):
        """Return a residual permutation; identity means membership."""
        return self._sift(_permutation(permutation, self.degree, "target permutation"))

    def contains(self, permutation):
        return self.sift(permutation) == tuple(range(self.degree))

    def __contains__(self, permutation):
        return self.contains(permutation)

    def to_dict(self):
        """Save only the compact certificate; orbits are derived when loaded."""
        return {
            "schema": _SCHEMA,
            "degree": self.degree,
            "order": str(self.order),
            "root_generators": [list(generator) for generator in self.root_generators],
            "input_generators": [list(generator) for generator in self.input_generators],
            "strong_generators": [
                {"permutation": list(generator.permutation),
                 "syllables": [list(syllable) for syllable in generator.syllables]}
                for generator in self.strong_generators
            ],
            "levels": [
                {"base_point": level.base_point,
                 "generator_indices": list(level.generator_indices)}
                for level in self.levels
            ],
        }

    @classmethod
    def from_dict(cls, data):
        """Independently validate a saved certificate without GAP."""
        if not isinstance(data, Mapping) or data.get("schema") != _SCHEMA:
            raise ValueError("unsupported permutation group certificate schema")
        required = {"schema", "degree", "order", "root_generators",
                    "input_generators", "strong_generators", "levels"}
        if set(data) != required:
            raise ValueError("permutation group certificate fields do not match the schema")
        try:
            generators = tuple(StrongGenerator(
                tuple(record["permutation"]),
                tuple(tuple(syllable) for syllable in record["syllables"]),
            ) for record in data["strong_generators"])
            levels = tuple(StabilizerLevel(record["base_point"],
                                           tuple(record["generator_indices"]))
                           for record in data["levels"])
            result = cls(data["root_generators"], generators, levels,
                         input_generators=data["input_generators"], degree=data["degree"])
        except (KeyError, IndexError) as error:
            raise ValueError("malformed permutation group certificate") from error
        if not isinstance(data["order"], str) or data["order"] != str(result.order):
            raise ValueError("saved group order disagrees with the certificate")
        return result
