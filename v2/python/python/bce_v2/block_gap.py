"""Exact footprint quotient and witnessed abelian orientation kernel in GAP.

The supplied generator lists are paired: index i always names the same legal
loop in the faithful sticker action and in its reference-block projection.
No section, splitting, or independence of physical block coordinates is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral
import os
import re
from typing import Sequence

from .gap_backend import (
    GapError, GapFactorization, _gap_images, _permutation_power, _run_gap,
    _validated_images, _validated_options, factor_permutation,
)


@dataclass(frozen=True)
class GapKernelGenerator:
    """One independent kernel generator, witnessed by original loop indices."""

    permutation: tuple[int, ...]
    order: int
    syllables: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class GapBlockStructure:
    """Certified H -> P structure and an independent cyclic basis of its K."""

    group_order: int
    quotient_order: int
    kernel_order: int
    basis: tuple[GapKernelGenerator, ...]
    gap_version: str


@dataclass(frozen=True)
class GapKernelFactorization:
    """Coordinates in the exact supplied kernel basis; failures are not nonmembers."""

    reachable: bool
    exponents: tuple[int, ...]
    group_order: int
    gap_version: str


_BEGIN = "__BCE_GAP_BLOCK_V1_BEGIN__"
_END = "__BCE_GAP_BLOCK_V1_END__"
_KERNEL_BEGIN = "__BCE_GAP_KERNEL_V1_BEGIN__"
_KERNEL_END = "__BCE_GAP_KERNEL_V1_END__"
_VERSION = r"([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)"
_POSITIVE = r"([1-9][0-9]*)"
_INTEGER_LIST = r"((?:0|[1-9][0-9]*)(?:,(?:0|[1-9][0-9]*))*)?"
_SYLLABLES = r"((?:0|[1-9][0-9]*):-?[1-9][0-9]*(?:,(?:0|[1-9][0-9]*):-?[1-9][0-9]*)*)?"


_STRUCTURE_PROGRAM = r'''
SetPrintFormattingStatus("*stdout*", false);;
BCEBlockStructure := function(images, blockImages)
    local permutations, projections, H, P, map, K, basis, orders, B, epi,
          words, generator, word, external, syllables, appendPower, i, value;
    permutations := List(images, PermList);
    projections := List(blockImages, PermList);
    H := GroupWithGenerators(permutations, ());
    P := GroupWithGenerators(projections, ());
    StabChain(H, rec(random := 1000));
    StabChain(P, rec(random := 1000));
    # The checked constructor proves that the paired actions respect every
    # relation of H, even when supplied loops are redundant or have identities.
    map := GroupHomomorphismByImages(H, P, permutations, projections);
    if map = fail or not IsSurjective(map) then
        Error("paired block actions do not define a surjective homomorphism");
    fi;
    K := Kernel(map);
    StabChain(K, rec(random := 1000));
    if not IsAbelian(K) then
        Error("reference-footprint kernel is not abelian");
    fi;
    if Size(H) <> Size(P) * Size(K) then
        Error("quotient/kernel orders failed verification");
    fi;
    basis := ShallowCopy(IndependentGeneratorsOfAbelianGroup(K));
    Sort(basis, function(a, b)
        if Order(a) <> Order(b) then return Order(a) < Order(b); fi;
        return ListPerm(a, 48) < ListPerm(b, 48);
    end);
    orders := List(permutations, Order);
    B := GroupWithGenerators(basis, ());
    StabChain(B, rec(random := 1000));
    # Commutativity plus this order product proves independence. Equality of
    # subgroups proves span; neither operation enumerates the group.
    if B <> K or Product(List(basis, Order)) <> Size(K) then
        Error("kernel basis failed span or independence verification");
    fi;
    words := [];
    if Length(basis) > 0 then
        epi := EpimorphismFromFreeGroup(H);
        if MappingGeneratorsImages(epi)[2] <> permutations then
            Error("free-group map changed the requested generator order");
        fi;
        for generator in basis do
            word := PreImagesRepresentative(epi, generator);
            if word = fail or Image(epi, word) <> generator then
                Error("kernel witness failed verification");
            fi;
            external := ExtRepOfObj(word);
            syllables := [];
            appendPower := function(index, exponent)
                if Length(syllables) > 0 and Last(syllables)[1] = index then
                    exponent := exponent + Remove(syllables)[2];
                fi;
                # These are full H orders, never the orders of images in P.
                exponent := exponent mod orders[index];
                if 2 * exponent > orders[index] then
                    exponent := exponent - orders[index];
                fi;
                if exponent <> 0 then Add(syllables, [index, exponent]); fi;
            end;
            for i in [1,3..Length(external)-1] do
                appendPower(external[i], external[i+1]);
            od;
            value := ();
            for word in syllables do
                value := value * permutations[word[1]]^word[2];
            od;
            if value <> generator or Image(map, value) <> () then
                Error("normalized kernel witness failed verification");
            fi;
            Add(words, syllables);
        od;
    fi;
    if ErrorCount() <> 0 then QuitGap(1); fi;
    Print("__BCE_GAP_BLOCK_V1_BEGIN__\n");
    Print("version=", GAPInfo.Version, "\n");
    Print("order=", Size(H), "\n");
    Print("quotient_order=", Size(P), "\n");
    Print("kernel_order=", Size(K), "\n");
    Print("basis_count=", Length(basis), "\n");
    for i in [1..Length(basis)] do
        Print("basis=", Order(basis[i]), "|",
              JoinStringsWithSeparator(List(ListPerm(basis[i],48), j -> String(j-1)), ","), "|",
              JoinStringsWithSeparator(List(words[i], pair ->
                  Concatenation(String(pair[1]-1), ":", String(pair[2]))), ","), "\n");
    od;
    Print("__BCE_GAP_BLOCK_V1_END__\n");
end;;
'''


_KERNEL_PROGRAM = r'''
SetPrintFormattingStatus("*stdout*", false);;
BCEKernelFactor := function(images, targetImages)
    local basis, target, K, orders, exponents, reachable, value, i;
    basis := List(images, PermList);
    target := PermList(targetImages);
    K := GroupWithGenerators(basis, ());
    StabChain(K, rec(random := 1000));
    orders := List(basis, Order);
    if not IsAbelian(K) or Product(orders) <> Size(K)
       or ForAny(orders, order -> order = 1 or not IsPrimePowerInt(order)) then
        Error("supplied kernel basis is not an independent prime-power basis");
    fi;
    # Reuse the prepared basis verbatim: recomputing it here could silently
    # attach coefficients to different physical algorithms on each solve.
    SetIndependentGeneratorsOfAbelianGroup(K, basis);
    reachable := target in K;
    exponents := [];
    if reachable then
        if Length(basis) > 0 then
            exponents := IndependentGeneratorExponents(K, target);
        fi;
        value := ();
        for i in [1..Length(basis)] do
            exponents[i] := exponents[i] mod orders[i];
            if 2 * exponents[i] > orders[i] then
                exponents[i] := exponents[i] - orders[i];
            fi;
            value := value * basis[i]^exponents[i];
        od;
        if value <> target then Error("kernel coefficients failed verification"); fi;
    fi;
    if ErrorCount() <> 0 then QuitGap(1); fi;
    Print("__BCE_GAP_KERNEL_V1_BEGIN__\n");
    Print("version=", GAPInfo.Version, "\n");
    Print("order=", Size(K), "\n");
    Print("reachable=", reachable, "\n");
    Print("exponents=", JoinStringsWithSeparator(List(exponents, String), ","), "\n");
    Print("__BCE_GAP_KERNEL_V1_END__\n");
end;;
'''


def _block_images(permutations, *, degree=None):
    """Validate arbitrary finite block permutations, retaining fixed centers."""
    result = []
    for index, permutation in enumerate(permutations):
        try:
            values = tuple(permutation)
        except TypeError as error:
            raise TypeError(f"block permutation {index} must be an integer sequence") from error
        if degree is None:
            degree = len(values)
        if len(values) != degree or degree > 48:
            raise ValueError("block permutations must have the same degree, at most 48")
        if any(isinstance(value, bool) or not isinstance(value, Integral) for value in values):
            raise TypeError(f"block permutation {index} must contain integer images")
        values = tuple(int(value) for value in values)
        if set(values) != set(range(degree)):
            raise ValueError(f"block permutation {index} must be a bijection of 0..{degree-1}")
        result.append(values)
    return tuple(result)


def _order(images):
    order, seen = 1, set()
    for point in range(len(images)):
        if point in seen:
            continue
        length, next_point = 0, point
        while next_point not in seen:
            seen.add(next_point)
            length += 1
            next_point = images[next_point]
        order = math.lcm(order, length)
    return order


def _prime_power(order):
    if order < 2:
        return False
    prime = 2
    while prime * prime <= order and order % prime:
        prime += 1
    if order % prime:
        return True
    while order % prime == 0:
        order //= prime
    return order == 1


def _evaluate(images, syllables, degree=48):
    product = tuple(range(degree))
    for index, exponent in syllables:
        # The shared evaluator is deliberately fixed to 48 points. Padding
        # preserves fixed center/core block indices and the original indices.
        padded = images[index] + tuple(range(len(images[index]), 48))
        power = _permutation_power(padded, exponent)
        product = tuple(power[point] for point in product)
    return product


def _subgroup_order(permutations):
    """Exact order through point orbits and successive Schreier stabilizers.

    Only point orbits are traversed, each of size at most 48. In particular,
    this does not enumerate the potentially large abelian kernel itself.
    """
    identity = tuple(range(48))
    generators = set(permutations) - {identity}
    order = 1
    while generators:
        base = next(point for point in range(48)
                    if any(generator[point] != point for generator in generators))
        transversals = {base: identity}
        orbit = [base]
        for point in orbit:
            for generator in generators:
                image = generator[point]
                if image not in transversals:
                    # Source execution order: transversal, then generator.
                    transversals[image] = tuple(generator[p] for p in transversals[point])
                    orbit.append(image)
        order *= len(orbit)
        inverses = {}
        for point, transversal in transversals.items():
            inverse = [0] * 48
            for source, destination in enumerate(transversal):
                inverse[destination] = source
            inverses[point] = tuple(inverse)
        stabilizers = set()
        for point in orbit:
            for generator in generators:
                inverse = inverses[generator[point]]
                # t_point * generator * t_image^-1 fixes this base point.
                schreier = tuple(inverse[generator[p]] for p in transversals[point])
                if schreier != identity:
                    stabilizers.add(schreier)
        generators = stabilizers
    return order


def _payload(output, begin_marker, end_marker):
    lines = output.splitlines()
    if lines.count(begin_marker) != 1 or lines.count(end_marker) != 1:
        raise GapError("GAP returned missing or duplicate block result markers")
    begin, end = lines.index(begin_marker), lines.index(end_marker)
    if end <= begin:
        raise GapError("GAP returned reversed block result markers")
    return lines[begin + 1:end]


def _field(line, name, pattern):
    match = re.fullmatch(name + "=" + pattern, line)
    if not match:
        raise GapError(f"GAP returned malformed {name}")
    return match.group(1) or ""


def _integer(value):
    try:
        return int(value)
    except ValueError as error:
        raise GapError("GAP returned oversized numeric values") from error


def _parse_structure(output, images, blocks):
    payload = _payload(output, _BEGIN, _END)
    if len(payload) < 5:
        raise GapError("GAP returned a malformed block structure")
    version = _field(payload[0], "version", _VERSION)
    order = _integer(_field(payload[1], "order", _POSITIVE))
    quotient = _integer(_field(payload[2], "quotient_order", _POSITIVE))
    kernel = _integer(_field(payload[3], "kernel_order", _POSITIVE))
    count = _integer(_field(payload[4], "basis_count", r"(0|[1-9][0-9]*)"))
    degree = len(blocks[0]) if blocks else 0
    if (len(payload) != 5 + count or count > 48
            or order > math.factorial(48) or quotient > math.factorial(degree)
            or order != quotient * kernel):
        raise GapError("GAP returned inconsistent quotient/kernel orders or basis count")
    if any(order % _order(p) for p in images) or any(quotient % _order(p) for p in blocks):
        raise GapError("GAP returned orders inconsistent with supplied generators")
    basis = []
    for line in payload[5:]:
        match = re.fullmatch(r"basis=" + _POSITIVE + r"\|" + _INTEGER_LIST + r"\|" + _SYLLABLES, line)
        if not match:
            raise GapError("GAP returned malformed kernel basis fields")
        generator_order = _integer(match.group(1))
        permutation = tuple(_integer(value) for value in match.group(2).split(",")) if match.group(2) else ()
        syllables = tuple(tuple(_integer(value) for value in pair.split(":"))
                          for pair in match.group(3).split(",")) if match.group(3) else ()
        try:
            permutation = _validated_images([permutation])[0]
        except (TypeError, ValueError) as error:
            raise GapError("GAP returned an invalid kernel basis permutation") from error
        if (generator_order != _order(permutation) or not _prime_power(generator_order)
                or any(index >= len(images) for index, _ in syllables)
                or _evaluate(images, syllables) != permutation
                or _evaluate(blocks, syllables, degree) != tuple(range(degree))):
            raise GapError("GAP kernel basis failed independent witness verification")
        basis.append(GapKernelGenerator(permutation, generator_order, syllables))
    if math.prod(generator.order for generator in basis) != kernel:
        raise GapError("GAP kernel basis orders do not multiply to the kernel order")
    for index, first in enumerate(basis):
        for second in basis[index + 1:]:
            if (tuple(second.permutation[p] for p in first.permutation)
                    != tuple(first.permutation[p] for p in second.permutation)):
                raise GapError("GAP returned noncommuting kernel basis elements")
    if _subgroup_order(generator.permutation for generator in basis) != kernel:
        raise GapError("GAP returned a dependent or incomplete kernel basis")
    return GapBlockStructure(order, quotient, kernel, tuple(basis), version)


def analyze_block_structure(
    permutations: Sequence[Sequence[int]],
    block_permutations: Sequence[Sequence[int]],
    *,
    gap_executable: str | os.PathLike[str] = "gap",
    timeout: float | None = None,
) -> GapBlockStructure:
    """Certify H -> P and extract independently witnessed abelian K algorithms.

    The checked homomorphism uses paired supplied generator indices. GAP
    certifies all stabilizer chains, quotient/kernel orders, commutativity,
    basis span and independence. Python independently verifies every original-
    generator word, its sticker order and identity block projection, and the
    generated basis order using Schreier point stabilizers.
    Missing GAP, malformed output and inconclusive computations raise GapError.
    """
    images = _validated_images(permutations)
    blocks = _block_images(block_permutations)
    if len(images) != len(blocks):
        raise ValueError("sticker and block generator lists must be paired")
    executable, timeout = _validated_options(gap_executable, timeout)
    program = (_STRUCTURE_PROGRAM + "BCEBlockStructure(" + _gap_images(images)
               + "," + _gap_images(blocks) + ");;\nQuitGap(0);\n")
    return _parse_structure(_run_gap(program, executable, timeout, "block structure analysis"), images, blocks)


def factor_block_permutation(
    permutations: Sequence[Sequence[int]],
    target: Sequence[int],
    *,
    gap_executable: str | os.PathLike[str] = "gap",
    timeout: float | None = None,
) -> GapFactorization:
    """Factor P using original paired loop indices, ready for a literal H lift.

    Powers here may be reduced using their P orders. Execute the returned
    original-loop word literally in H, then measure and correct its residual;
    never assume those quotient power reductions are identities in H.
    """
    target_images = _block_images([target])[0]
    images = _block_images(permutations, degree=len(target_images))
    pad = lambda permutation: permutation + tuple(range(len(permutation), 48))
    return factor_permutation(tuple(pad(permutation) for permutation in images), pad(target_images),
                              gap_executable=gap_executable, timeout=timeout)


def factor_kernel(
    basis: Sequence[Sequence[int]],
    target: Sequence[int],
    *,
    gap_executable: str | os.PathLike[str] = "gap",
    timeout: float | None = None,
) -> GapKernelFactorization:
    """Find signed coordinates in a prepared, independent prime-power K basis.

    GAP proves the supplied basis is independent and abelian, then uses
    IndependentGeneratorExponents with precisely that basis. Python verifies
    the supplied basis independence and reported coefficient product. A target
    outside this subgroup is an exact nonmember; process errors and invalid
    bases raise GapError.
    """
    images = _validated_images(basis)
    target_images = _validated_images([target])[0]
    executable, timeout = _validated_options(gap_executable, timeout)
    program = (_KERNEL_PROGRAM + "BCEKernelFactor(" + _gap_images(images) + ","
               + _gap_images([target_images])[1:-1] + ");;\nQuitGap(0);\n")
    payload = _payload(_run_gap(program, executable, timeout, "kernel factorization"),
                       _KERNEL_BEGIN, _KERNEL_END)
    if len(payload) != 4:
        raise GapError("GAP returned a malformed kernel factorization")
    version = _field(payload[0], "version", _VERSION)
    order = _integer(_field(payload[1], "order", _POSITIVE))
    reachable = _field(payload[2], "reachable", r"(true|false)") == "true"
    raw = _field(payload[3], "exponents", r"((?:0|-?[1-9][0-9]*)(?:,(?:0|-?[1-9][0-9]*))*)?")
    exponents = tuple(_integer(value) for value in raw.split(",")) if raw else ()
    orders = tuple(_order(permutation) for permutation in images)
    if order != math.prod(orders) or order > math.factorial(48):
        raise GapError("GAP returned an inconsistent kernel order")
    if (any(not _prime_power(modulus) for modulus in orders)
            or any(tuple(second[p] for p in first) != tuple(first[p] for p in second)
                   for index, first in enumerate(images) for second in images[index + 1:])
            or _subgroup_order(images) != order):
        raise GapError("GAP returned a factorization in an invalid independent kernel basis")
    if not reachable:
        if exponents or target_images == tuple(range(48)):
            raise GapError("GAP returned inconsistent unreachable kernel factorization")
    elif (len(exponents) != len(images)
          or any(not (-modulus < exponent < modulus) for exponent, modulus in zip(exponents, orders))
          or _evaluate(images, tuple(enumerate(exponents))) != target_images):
        raise GapError("GAP kernel coefficients failed independent permutation verification")
    return GapKernelFactorization(reachable, exponents, order, version)
