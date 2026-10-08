"""Optional, exact permutation-group analysis in a separate GAP process.

The backend needs only GAP's core permutation-group library. It never asks GAP
to enumerate the group or to synthesize generators: every returned index refers
to an input permutation, so its original executable loop remains the witness.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral, Real
import os
import re
import subprocess
from typing import Sequence


class GapError(RuntimeError):
    """GAP failed to produce a complete, valid exact analysis."""


class GapUnavailableError(GapError):
    """The requested GAP executable could not be found or started."""


class GapTimeoutError(GapError):
    """The GAP subprocess exceeded the requested time limit."""


@dataclass(frozen=True)
class GapAnalysis:
    """Exact group order and an input-order subset generating that group."""

    group_order: int
    generator_indices: tuple[int, ...]
    gap_version: str


@dataclass(frozen=True)
class GapFactorization:
    """Exact membership and a witnessed product of original input generators.

    Syllables are ``(zero_based_input_index, signed_exponent)`` pairs in
    execution order. ``group_order`` concerns the full input group, even if
    the word uses only a proper subgroup. An unreachable target has no word.
    """

    group_order: int
    reachable: bool
    syllables: tuple[tuple[int, int], ...]
    gap_version: str


_BEGIN = "__BCE_GAP_V1_BEGIN__"
_END = "__BCE_GAP_V1_END__"
_FACTOR_BEGIN = "__BCE_GAP_FACTOR_V1_BEGIN__"
_FACTOR_END = "__BCE_GAP_FACTOR_V1_END__"

# Only validated integer lists and a literal boolean are appended to this
# constant program. In particular, filenames and user text never become GAP
# source. random=1000 requests a certified stabilizer chain (not a Monte Carlo
# estimate); constructing it before membership and Size keeps both exact.
_PROGRAM = r'''
SetPrintFormattingStatus("*stdout*", false);;
BCEAnalyze := function(images, prune)
    local permutations, makeGroup, kept, group, candidate, others, i, order;
    permutations := List(images, PermList);
    makeGroup := function(indices)
        local result;
        # Including the identity also handles an empty generator list.
        result := Group(Concatenation([()], permutations{indices}));
        StabChain(result, rec(random := 1000));
        return result;
    end;
    kept := [];
    group := makeGroup(kept);
    for i in [1..Length(permutations)] do
        if not (permutations[i] in group) then
            Add(kept, i);
            group := makeGroup(kept);
        fi;
    od;
    if prune then
        # Later generators can make earlier accepted generators redundant.
        # A single deletion pass is enough: subsequent deletions only shrink
        # the subgroup against which an indispensable generator was tested.
        for i in ShallowCopy(kept) do
            others := Filtered(kept, j -> j <> i);
            candidate := makeGroup(others);
            if permutations[i] in candidate then
                kept := others;
                group := candidate;
            fi;
        od;
    fi;
    order := Size(group);
    # Refuse to report a result after any startup or parse error, even if GAP
    # happened to continue reading stdin. --quitonbreak handles runtime errors.
    if ErrorCount() <> 0 then
        QuitGap(1);
    fi;
    Print("__BCE_GAP_V1_BEGIN__\n");
    Print("version=", GAPInfo.Version, "\n");
    Print("order=", order, "\n");
    Print("indices=", JoinStringsWithSeparator(List(kept, i -> String(i-1)), ","), "\n");
    Print("__BCE_GAP_V1_END__\n");
end;;
'''


_FACTOR_PROGRAM = r'''
SetPrintFormattingStatus("*stdout*", false);;
BCEFactor := function(images, targetImages)
    local permutations, target, makeGroup, fullGroup, group, order, reachable,
          kept, others, candidate, i, epi, word, external, syllables, orders,
          appendPower, exponent, index, value;
    permutations := List(images, PermList);
    target := PermList(targetImages);
    makeGroup := function(indices)
        local result;
        # Preserve the exact input order for the eventual free-group map.
        result := GroupWithGenerators(permutations{indices}, ());
        StabChain(result, rec(random := 1000));
        return result;
    end;
    kept := [1..Length(permutations)];
    fullGroup := makeGroup(kept);
    order := Size(fullGroup);
    reachable := target in fullGroup;
    syllables := [];
    if reachable and target <> () then
        group := fullGroup;
        # A singleton can beat the subset obtained by greedy deletions. Prefer
        # the earliest supplied generator when several cyclic groups suffice.
        for i in kept do
            candidate := makeGroup([i]);
            if target in candidate then
                kept := [i];
                group := candidate;
                break;
            fi;
        od;
        if Length(kept) > 1 then
            # This is inclusion-minimal for this target, not necessarily a
            # subset of globally minimum size. Prefer earlier input witnesses.
            for i in Reversed(kept) do
                others := Filtered(kept, j -> j <> i);
                candidate := makeGroup(others);
                if target in candidate then
                    kept := others;
                    group := candidate;
                fi;
            od;
        fi;
        epi := EpimorphismFromFreeGroup(group);
        if MappingGeneratorsImages(epi)[2] <> permutations{kept} then
            Error("free-group map changed the requested generator order");
        fi;
        word := PreImagesRepresentative(epi, target);
        if word = fail or Image(epi, word) <> target then
            Error("free-group preimage failed verification");
        fi;
        external := ExtRepOfObj(word);
        orders := List(permutations, Order);
        appendPower := function(index, exponent)
            # Reduce powers using the generator's finite permutation order,
            # and merge adjacent equal generators without expanding repeats.
            if Length(syllables) > 0 and Last(syllables)[1] = index then
                exponent := exponent + Remove(syllables)[2];
            fi;
            exponent := exponent mod orders[index];
            if 2 * exponent > orders[index] then
                exponent := exponent - orders[index];
            fi;
            if exponent <> 0 then
                Add(syllables, [index, exponent]);
            fi;
        end;
        for i in [1,3..Length(external)-1] do
            appendPower(kept[external[i]], external[i+1]);
        od;
        value := ();
        for word in syllables do
            value := value * permutations[word[1]]^word[2];
        od;
        if value <> target then
            Error("normalized generator word failed verification");
        fi;
    fi;
    if ErrorCount() <> 0 then
        QuitGap(1);
    fi;
    Print("__BCE_GAP_FACTOR_V1_BEGIN__\n");
    Print("version=", GAPInfo.Version, "\n");
    Print("order=", order, "\n");
    Print("reachable=", reachable, "\n");
    Print("syllables=", JoinStringsWithSeparator(List(syllables,
        pair -> Concatenation(String(pair[1]-1), ":", String(pair[2]))), ","), "\n");
    Print("__BCE_GAP_FACTOR_V1_END__\n");
end;;
'''


def _validated_images(permutations: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    images = []
    for index, permutation in enumerate(permutations):
        try:
            values = tuple(permutation)
        except TypeError as error:
            raise TypeError(f"permutation {index} must be a sequence of 48 integers") from error
        if len(values) != 48:
            raise ValueError(f"permutation {index} must contain exactly 48 images")
        if any(isinstance(value, bool) or not isinstance(value, Integral) for value in values):
            raise TypeError(f"permutation {index} must contain integer images")
        values = tuple(int(value) for value in values)
        if set(values) != set(range(48)):
            raise ValueError(f"permutation {index} must be a bijection of 0..47")
        images.append(values)
    return tuple(images)


def _parse_result(output: str, generator_count: int) -> GapAnalysis:
    lines = output.splitlines()
    if lines.count(_BEGIN) != 1 or lines.count(_END) != 1:
        raise GapError("GAP returned missing or duplicate result markers")
    begin, end = lines.index(_BEGIN), lines.index(_END)
    payload = lines[begin + 1:end]
    if end <= begin or len(payload) != 3:
        raise GapError("GAP returned a malformed result block")
    version_match = re.fullmatch(r"version=([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)", payload[0])
    order_match = re.fullmatch(r"order=([1-9][0-9]*)", payload[1])
    indices_match = re.fullmatch(r"indices=((?:0|[1-9][0-9]*)(?:,(?:0|[1-9][0-9]*))*)?", payload[2])
    if not version_match or not order_match or not indices_match:
        raise GapError("GAP returned malformed version, order, or generator indices")
    try:
        order = int(order_match.group(1))
        indices = tuple(int(value) for value in indices_match.group(1).split(",")) if indices_match.group(1) else ()
    except ValueError as error:
        raise GapError("GAP returned oversized numeric values") from error
    if indices != tuple(sorted(set(indices))) or any(index >= generator_count for index in indices):
        raise GapError("GAP returned invalid generator indices")
    if (order == 1) != (not indices) or order > math.factorial(48):
        raise GapError("GAP returned an inconsistent group order")
    return GapAnalysis(order, indices, version_match.group(1))


def _validated_options(gap_executable, timeout):
    executable = os.fspath(gap_executable)
    if not isinstance(executable, str):
        raise TypeError("gap_executable must be a string or text path")
    if not executable or "\x00" in executable:
        raise ValueError("gap_executable must be a nonempty path without NUL characters")
    if timeout is not None:
        if isinstance(timeout, bool) or not isinstance(timeout, Real):
            raise TypeError("timeout must be a positive finite number of seconds")
        try:
            timeout = float(timeout)
        except OverflowError as error:
            raise ValueError("timeout must be positive and finite") from error
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
    return executable, timeout


def _gap_images(images):
    return "[" + ",".join("[" + ",".join(str(value + 1) for value in permutation) + "]"
                           for permutation in images) + "]"


def _run_gap(program, executable, timeout, operation="analysis"):
    try:
        completed = subprocess.run(
            [executable, "-q", "-b", "--quitonbreak", "-r", "-A"],
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise GapTimeoutError(f"GAP {operation} exceeded its {timeout:g}-second timeout") from error
    except OSError as error:
        raise GapUnavailableError(
            f"Could not start GAP executable {executable!r}: {error}. "
            "Install GAP or pass gap_executable pointing to its launcher."
        ) from error
    if completed.returncode != 0:
        diagnostic = (completed.stderr.strip() or completed.stdout.strip())[-2000:]
        suffix = f": {diagnostic}" if diagnostic else ""
        raise GapError(f"GAP exited with status {completed.returncode}{suffix}")
    return completed.stdout


def analyze_generators(
    permutations: Sequence[Sequence[int]],
    *,
    gap_executable: str | os.PathLike[str] = "gap",
    timeout: float | None = None,
    prune: bool = True,
) -> GapAnalysis:
    """Compute an exact order and reduce 48-point, zero-based permutations.

    Candidates are considered in their supplied order. Membership testing first
    retains only generators outside the subgroup accumulated so far. With
    ``prune=True``, a deletion pass additionally makes this subset irredundant;
    minimum cardinality is not promised. Supply candidates in increasing loop
    length to prefer shorter physical witnesses.

    GAP is optional and is launched without a shell. ``gap_executable`` can be
    a command on PATH or a filesystem path. ``timeout`` is a positive finite
    number of seconds, or ``None`` for no time limit. A missing executable,
    timeout, subprocess failure, or incomplete result raises ``GapError``;
    none of these failures returns an approximate order.
    """
    images = _validated_images(permutations)
    executable, timeout = _validated_options(gap_executable, timeout)
    if not isinstance(prune, bool):
        raise TypeError("prune must be a boolean")
    program = _PROGRAM + "BCEAnalyze(" + _gap_images(images) + "," + ("true" if prune else "false") + ");;\nQuitGap(0);\n"
    return _parse_result(_run_gap(program, executable, timeout), len(images))


def _permutation_power(images, exponent):
    """Evaluate a signed power by cycles, without repeating its exponent."""
    result = list(range(48))
    seen = set()
    for source in range(48):
        if source in seen:
            continue
        cycle = []
        point = source
        while point not in seen:
            seen.add(point)
            cycle.append(point)
            point = images[point]
        shift = exponent % len(cycle)
        for index, point in enumerate(cycle):
            result[point] = cycle[(index + shift) % len(cycle)]
    return tuple(result)


def _parse_factor_result(output, images, target):
    lines = output.splitlines()
    if lines.count(_FACTOR_BEGIN) != 1 or lines.count(_FACTOR_END) != 1:
        raise GapError("GAP returned missing or duplicate factorization markers")
    begin, end = lines.index(_FACTOR_BEGIN), lines.index(_FACTOR_END)
    payload = lines[begin + 1:end]
    if end <= begin or len(payload) != 4:
        raise GapError("GAP returned a malformed factorization block")
    version_match = re.fullmatch(r"version=([0-9]+(?:\.[0-9]+)+(?:[-+._A-Za-z0-9]*)?)", payload[0])
    order_match = re.fullmatch(r"order=([1-9][0-9]*)", payload[1])
    reachable_match = re.fullmatch(r"reachable=(true|false)", payload[2])
    syllables_match = re.fullmatch(r"syllables=((?:0|[1-9][0-9]*):-?[1-9][0-9]*(?:,(?:0|[1-9][0-9]*):-?[1-9][0-9]*)*)?", payload[3])
    if not all((version_match, order_match, reachable_match, syllables_match)):
        raise GapError("GAP returned malformed factorization fields")
    try:
        order = int(order_match.group(1))
        syllables = tuple(tuple(int(value) for value in pair.split(":"))
                          for pair in syllables_match.group(1).split(",")) if syllables_match.group(1) else ()
    except ValueError as error:
        raise GapError("GAP returned oversized numeric values") from error
    reachable = reachable_match.group(1) == "true"
    if order > math.factorial(48) or any(index >= len(images) for index, _ in syllables):
        raise GapError("GAP returned invalid group order or generator indices")
    identity = tuple(range(48))
    if not reachable:
        if syllables or target == identity:
            raise GapError("GAP returned inconsistent unreachable factorization")
    else:
        product = identity
        for index, exponent in syllables:
            power = _permutation_power(images[index], exponent)
            product = tuple(power[point] for point in product)
        if product != target or (order == 1 and target != identity):
            raise GapError("GAP factorization failed independent permutation verification")
    return GapFactorization(order, reachable, syllables, version_match.group(1))


def factor_permutation(
    permutations: Sequence[Sequence[int]],
    target: Sequence[int],
    *,
    gap_executable: str | os.PathLike[str] = "gap",
    timeout: float | None = None,
) -> GapFactorization:
    """Factor a target permutation using original generator indices and powers.

    All permutations are zero-based images on 48 stickers. GAP first certifies
    membership and the full input group order. For a nonidentity member, it
    checks single-generator subgroups, then greedily removes high-index
    generators while the remaining subgroup still contains the target. The
    resulting subset is inclusion-minimal; minimum cardinality or a shortest
    word is not promised.

    A free-group preimage supplies a word without enumerating the group.
    Signed powers are reduced by the generator orders, and both GAP and Python
    independently verify that the returned execution-order product equals
    ``target``. Identity and nonmembers return empty syllables, distinguished
    by ``reachable``. The executable, timeout, and errors follow the same
    contract as ``analyze_generators``. Word construction may still be costly
    and the resulting syllable sequence may be long.
    """
    images = _validated_images(permutations)
    target_images = _validated_images([target])[0]
    executable, timeout = _validated_options(gap_executable, timeout)
    gap_target = _gap_images([target_images])[1:-1]
    program = _FACTOR_PROGRAM + "BCEFactor(" + _gap_images(images) + "," + gap_target + ");;\nQuitGap(0);\n"
    output = _run_gap(program, executable, timeout, "factorization")
    return _parse_factor_result(output, images, target_images)
