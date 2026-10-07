#!/usr/bin/env python3
"""Count positioned guillotine partitions with a small exact recurrence.

This is an exact alternative to the legacy enumerate_analytic() for the
recursive full-plane-cut family. It counts partitions, not cut trees, motion
classes, rotation classes, or dynamically closed bandages. Cuboid partitions
with no recursive full-plane-cut construction are outside this family.

For a box B, let A_p contain its guillotine partitions with no block crossing
the internal plane p. Every nontrivial guillotine partition lies in at least
one A_p. For a nonempty set S of planes, their intersection consists of freely
chosen guillotine partitions of the subboxes cut out by S. Restricting a
guillotine cut tree to any subbox remains a guillotine cut tree. Therefore:

    F(B) = allowed_whole_block(B)
         + sum((-1)**(len(S)+1) * product(F(C) for C in subboxes(B, S))
               for nonempty S of internal planes)

In a 3x3x3 box there are at most six planes and only 216 interval subboxes.
Python integers keep the result exact; the optional small brute-force checks
use sets of actual partitions, independently of the inclusion-exclusion sum.

Run: python3 v2/research/check_guillotine_counts.py --check
"""

from __future__ import annotations

import argparse
from functools import lru_cache
from itertools import combinations, product
from math import prod

Bounds = tuple[tuple[int, int], ...]
Plane = tuple[int, int]
POLICIES = ("include", "exclude_core_pairs", "exclude_core_bars", "core_singleton")


def allowed_whole_block(bounds: Bounds, core: tuple[int, ...], policy: str) -> bool:
    """Core policies affect a block only when it contains the reference core."""
    if not all(low <= coordinate < high for (low, high), coordinate in zip(bounds, core)):
        return True
    lengths = [high - low for low, high in bounds]
    volume = prod(lengths)
    if policy == "include":
        return True
    if policy == "exclude_core_pairs":
        # The stated final family in the old enumerator's README.
        return volume != 2
    if policy == "exclude_core_bars":
        # The old p3c=1 also excludes the three-cell bar through the core.
        return sum(length > 1 for length in lengths) != 1
    if policy == "core_singleton":
        return volume == 1
    raise ValueError(f"unknown core policy: {policy}")


def internal_planes(bounds: Bounds) -> tuple[Plane, ...]:
    return tuple(
        (axis, position)
        for axis, (low, high) in enumerate(bounds)
        for position in range(low + 1, high)
    )


def subboxes(bounds: Bounds, planes: tuple[Plane, ...]):
    intervals = []
    for axis, (low, high) in enumerate(bounds):
        cuts = [low, *(position for candidate, position in planes if candidate == axis), high]
        intervals.append(tuple(zip(cuts, cuts[1:])))
    return product(*intervals)


def guillotine_count(
    dimensions: tuple[int, ...],
    core: tuple[int, ...],
    policy: str = "include",
) -> int:
    if len(dimensions) != len(core) or any(size <= 0 for size in dimensions):
        raise ValueError("positive dimensions and one core coordinate per axis are required")
    if any(not 0 <= coordinate < size for coordinate, size in zip(core, dimensions)):
        raise ValueError("the core must be inside the box")
    if policy not in POLICIES:
        raise ValueError(f"unknown core policy: {policy}")

    @lru_cache(maxsize=None)
    def count(bounds: Bounds) -> int:
        total = int(allowed_whole_block(bounds, core, policy))
        planes = internal_planes(bounds)
        for size in range(1, len(planes) + 1):
            sign = 1 if size % 2 else -1
            for selected in combinations(planes, size):
                total += sign * prod(count(child) for child in subboxes(bounds, selected))
        return total

    return count(tuple((0, size) for size in dimensions))


def brute_guillotine_count(dimensions: tuple[int, ...], core: tuple[int, ...], policy: str) -> int:
    """Independently enumerate all small slicing partitions and deduplicate."""
    @lru_cache(maxsize=None)
    def partitions(bounds: Bounds) -> frozenset[frozenset[Bounds]]:
        found = {frozenset((bounds,))} if allowed_whole_block(bounds, core, policy) else set()
        for plane in internal_planes(bounds):
            first, second = subboxes(bounds, (plane,))
            found.update(a | b for a in partitions(first) for b in partitions(second))
        return frozenset(found)

    return len(partitions(tuple((0, size) for size in dimensions)))


def brute_cuboid_count(dimensions: tuple[int, ...]) -> int:
    """Independent exact cover count, including small non-guillotine tilings."""
    cells = tuple(product(*(range(size) for size in dimensions)))
    positions = {cell: index for index, cell in enumerate(cells)}
    boxes = []
    for lows in product(*(range(size) for size in dimensions)):
        for highs in product(*(range(low + 1, size + 1) for low, size in zip(lows, dimensions))):
            boxes.append(
                sum(
                    1 << positions[cell]
                    for cell in product(*(range(low, high) for low, high in zip(lows, highs)))
                )
            )
    containing = tuple(tuple(box for box in boxes if box >> index & 1) for index in range(len(cells)))

    @lru_cache(maxsize=None)
    def count(remaining: int) -> int:
        if not remaining:
            return 1
        first = (remaining & -remaining).bit_length() - 1
        return sum(count(remaining ^ box) for box in containing[first] if box & remaining == box)

    return count((1 << len(cells)) - 1)


def check_small_instances() -> None:
    for dimensions, core in (((3,), (1,)), ((3, 3), (1, 1)), ((2, 2, 2), (0, 0, 0))):
        for policy in POLICIES:
            analytic = guillotine_count(dimensions, core, policy)
            brute = brute_guillotine_count(dimensions, core, policy)
            assert analytic == brute, (dimensions, policy, analytic, brute)
    assert guillotine_count((3, 3), (1, 1)) == 320
    assert brute_cuboid_count((3, 3)) == 322
    assert guillotine_count((2, 2, 2), (0, 0, 0)) == 146
    assert brute_cuboid_count((2, 2, 2)) == 154
    # Confirm the early legacy core-bar subcounts separately.
    assert guillotine_count((3,), (1,), "exclude_core_bars") == 1
    assert guillotine_count((3, 2), (1, 0), "exclude_core_bars") == 14
    assert guillotine_count((2, 2, 2), (0, 0, 0), "exclude_core_bars") == 74
    assert guillotine_count((3, 2, 2), (1, 0, 0), "exclude_core_bars") == 1384


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="also verify small instances with independent enumeration")
    options = parser.parse_args()
    if options.check:
        check_small_instances()
        print("Small independent checks passed: 3x3 rectangles 322, guillotine 320; 2x2x2 cuboids 154, guillotine 146.")
    for policy in POLICIES:
        result = guillotine_count((3, 3, 3), (1, 1, 1), policy)
        print(f"3x3x3 guillotine partitions ({policy}): {result:,}")


if __name__ == "__main__":
    main()
