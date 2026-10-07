#!/usr/bin/env python3
"""Independently reproduce the spatial cuboid-partition counts.

Run with Python 3.10+ and no third-party packages:

    python3 v2/research/check_partition_counts.py
    python3 v2/research/check_partition_counts.py --rotations
    python3 v2/research/check_partition_counts.py --mobility

The layer-transfer calculation is independent of the engine's exact-cover DP.
The small-grid check filters every set partition, without generating cuboids.
Counts precede legal-turn equivalence and complete implicit-bond closure.

The published planar 3x3 count, 322, appears in Blanco et al. (2026):
https://sites.math.rutgers.edu/~zeilberg/mamarim/mamarimPDF/recto.pdf
The three-dimensional results below are derived here, rather than quoted.
"""

from argparse import ArgumentParser
from functools import cache
from itertools import permutations, product
import json


CORE = 1 << 13
FULL_GRID = (1 << 27) - 1
SHELL = FULL_GRID ^ CORE
EXPECTED = {
    "full": (216, 701_898_882, 29_255_694),
    "core-singleton": (153, 170_204_427, 7_095_461),
    "shell": (206, 312_238_908, 13_016_719),
}
EXPECTED_MOBILITY = {
    "full": [154_100_675, 325_473_186, 190_613_799, 30_543_852, 1_164_303, 3_066, 1],
    "core-singleton": [33_044_260, 79_157_334, 49_364_379, 8_300_524, 336_399, 1_530, 1],
    "shell": [64_056_605, 146_026_794, 88_406_271, 13_362_156, 385_551, 1_530, 1],
}
EXPECTED_FROZEN_ROTATIONS = {
    "full": 6_423_921,
    "core-singleton": 1_378_011,
    "shell": 2_671_527,
}


def box_masks(nx: int, ny: int, nz: int) -> list[int]:
    """All spatial boxes; bit index is x + nx * (y + ny * z)."""
    def intervals(size: int) -> list[tuple[int, int]]:
        return [(low, high) for low in range(size) for high in range(low, size)]

    boxes = []
    for (x0, x1), (y0, y1), (z0, z1) in product(
        intervals(nx), intervals(ny), intervals(nz)
    ):
        mask = 0
        for x, y, z in product(
            range(x0, x1 + 1), range(y0, y1 + 1), range(z0, z1 + 1)
        ):
            mask |= 1 << (x + nx * (y + ny * z))
        boxes.append(mask)
    return boxes


def connected_shell(mask: int) -> bool:
    """Check face adjacency, independently of the engine's bond encoding."""
    seen = mask & -mask
    frontier = seen
    while frontier:
        cell_bit = frontier & -frontier
        frontier ^= cell_bit
        cell = cell_bit.bit_length() - 1
        coordinates = (cell % 3, (cell // 3) % 3, cell // 9)
        for coordinate, stride in zip(coordinates, (1, 3, 9)):
            for direction in (-1, 1):
                if 0 <= coordinate + direction < 3:
                    neighbor = 1 << (cell + direction * stride)
                    if neighbor & mask and not neighbor & seen:
                        seen |= neighbor
                        frontier |= neighbor
    return seen == mask


def model_tiles(model: str) -> tuple[int, list[int]]:
    boxes = box_masks(3, 3, 3)
    if model == "full":
        return FULL_GRID, boxes
    if model == "core-singleton":
        return FULL_GRID, [box for box in boxes if not box & CORE or box == CORE]
    if model == "shell":
        footprints = {box & SHELL for box in boxes}
        return SHELL, sorted(mask for mask in footprints if mask and connected_shell(mask))
    raise ValueError(f"Unknown model: {model}")


def exact_cover_count(domain: int, tiles: list[int]) -> tuple[int, int]:
    """A first-unfilled-cell recurrence; repeated tiles retain multiplicity."""
    choices: dict[int, list[int]] = {}
    for tile in tiles:
        choices.setdefault(tile & -tile, []).append(tile)

    @cache
    def count(remaining: int) -> int:
        if not remaining:
            return 1
        first = remaining & -remaining
        return sum(
            count(remaining ^ tile)
            for tile in choices.get(first, ())
            if tile & remaining == tile
        )

    result = count(domain)
    return result, count.cache_info().currsize


def blocked_faces(tiles: list[int]) -> list[int]:
    """A tile blocks a face exactly when it straddles that layer's boundary."""
    layers = [
        sum(1 << cell for cell in range(27) if (cell // stride) % 3 == side)
        for stride in (1, 3, 9)
        for side in (0, 2)
    ]
    return [
        sum(1 << face for face, layer in enumerate(layers) if tile & layer not in (0, tile))
        for tile in tiles
    ]


def legal_face_distribution(
    domain: int, tiles: list[int], blockers: list[int] | None = None
) -> list[int]:
    """Count exact legal-face masks by subset inversion, without shape search.

    First count partitions allowing every face in each prescribed subset.
    Exclude any tile straddling one of those faces. Subset Möbius inversion
    then gives the number of partitions with exactly each legal-face mask.
    This independently checks the 64-bin obstruction-histogram recurrence.
    """
    if blockers is None:
        blockers = blocked_faces(tiles)
    counts = []
    for allowed in range(64):
        permitted = [tile for tile, blocked in zip(tiles, blockers) if not blocked & allowed]
        counts.append(exact_cover_count(domain, permitted)[0])
    for face in range(6):
        for allowed in range(64):
            if not allowed & (1 << face):
                counts[allowed] -= counts[allowed | (1 << face)]
    distribution = [0] * 7
    for allowed, count in enumerate(counts):
        assert count >= 0
        distribution[allowed.bit_count()] += count
    return distribution


def planar_tilings(nx: int, ny: int) -> list[frozenset[int]]:
    """Enumerate planar partitions only, for the independent transfer method."""
    boxes = box_masks(nx, ny, 1)
    covers = [[box for box in boxes if box & (1 << cell)] for cell in range(nx * ny)]
    tilings = []

    def visit(remaining: int, chosen: list[int]) -> None:
        if not remaining:
            tilings.append(frozenset(chosen))
            return
        first = (remaining & -remaining).bit_length() - 1
        for box in covers[first]:
            if box & remaining == box:
                visit(remaining ^ box, chosen + [box])

    visit((1 << (nx * ny)) - 1, [])
    return tilings


def layer_transfer_counts() -> dict[str, int]:
    """Identical rectangles in adjacent layers may independently be joined.

    Thus W(A,B) = 2**len(A & B). For three layers the total is the
    sum over middle tilings B of (sum over A of W(A,B))**2.
    To isolate the core, its middle rectangle must be a singleton and
    that singleton must be excluded from possible joins on both sides.
    """
    tilings = planar_tilings(3, 3)
    center_rectangle = 1 << 4
    full = 0
    isolated = 0
    two_layers = 0
    for middle in tilings:
        row_sum = sum(1 << len(layer & middle) for layer in tilings)
        full += row_sum * row_sum
        two_layers += row_sum
        if center_rectangle in middle:
            isolated_sum = sum(
                1 << len((layer & middle) - {center_rectangle}) for layer in tilings
            )
            isolated += isolated_sum * isolated_sum
    return {
        "3x3": len(tilings),
        "3x3x2": two_layers,
        "3x3x3": full,
        "3x3x3-core-singleton": isolated,
    }


def brute_set_partitions(nx: int, ny: int, nz: int) -> tuple[int, int]:
    """Filter every restricted-growth label string by box-shaped blocks."""
    cells = nx * ny * nz
    labels = [0] * cells
    checked = accepted = 0

    def visit(index: int, largest: int) -> None:
        nonlocal checked, accepted
        if index < cells:
            for label in range(largest + 2):
                labels[index] = label
                visit(index + 1, max(largest, label))
            return
        checked += 1
        groups: list[list[tuple[int, int, int]]] = [[] for _ in range(largest + 1)]
        for cell, label in enumerate(labels):
            groups[label].append((cell % nx, (cell // nx) % ny, cell // (nx * ny)))
        for group in groups:
            volume = 1
            for axis in range(3):
                volume *= max(cell[axis] for cell in group) - min(cell[axis] for cell in group) + 1
            if volume != len(group):
                return
        accepted += 1

    visit(1, 0)
    return checked, accepted


def proper_rotations() -> list[tuple[int, ...]]:
    """Generate the 24 coordinate permutations with determinant +1."""
    rotations = []
    for order in permutations(range(3)):
        inversions = sum(order[i] > order[j] for i in range(3) for j in range(i + 1, 3))
        parity = -1 if inversions % 2 else 1
        for signs in product((-1, 1), repeat=3):
            if parity * signs[0] * signs[1] * signs[2] != 1:
                continue
            mapping = []
            for cell in range(27):
                coordinates = (cell % 3 - 1, (cell // 3) % 3 - 1, cell // 9 - 1)
                x, y, z = (signs[axis] * coordinates[order[axis]] + 1 for axis in range(3))
                mapping.append(x + 3 * y + 9 * z)
            rotations.append(tuple(mapping))
    assert len(set(rotations)) == 24
    return rotations


def rotate_mask(mask: int, mapping: tuple[int, ...]) -> int:
    result = 0
    while mask:
        bit = mask & -mask
        mask ^= bit
        result |= 1 << mapping[bit.bit_length() - 1]
    return result


def rotation_classes(
    domain: int, tiles: list[int], *, mobility: bool = False
) -> tuple[int, list[int], int | None]:
    """Burnside: each invariant partition is an exact cover of tile orbits."""
    fixed_counts = []
    fixed_frozen = []
    tile_blockers = dict(zip(tiles, blocked_faces(tiles)))
    for rotation in proper_rotations():
        visited = set()
        orbit_tiles = []
        orbit_blockers = []
        for seed in tiles:
            if seed in visited:
                continue
            tile = seed
            union = 0
            blocked = 0
            disjoint = True
            while tile not in visited:
                visited.add(tile)
                if union & tile:
                    disjoint = False
                union |= tile
                blocked |= tile_blockers[tile]
                tile = rotate_mask(tile, rotation)
            assert tile == seed
            if disjoint:
                # Distinct orbits can cover the same cells in different ways.
                orbit_tiles.append(union)
                # An orbit is several separate blocks, so use their combined
                # obstructions, rather than those of a single union-shaped block.
                orbit_blockers.append(blocked)
        fixed_counts.append(exact_cover_count(domain, orbit_tiles)[0])
        if mobility:
            fixed_frozen.append(legal_face_distribution(domain, orbit_tiles, orbit_blockers)[0])
    assert sum(fixed_counts) % 24 == 0
    assert sum(fixed_frozen) % 24 == 0
    frozen_classes = sum(fixed_frozen) // 24 if mobility else None
    return sum(fixed_counts) // 24, sorted(fixed_counts), frozen_classes


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotations", action="store_true", help="also count proper-rotation orbits"
    )
    parser.add_argument(
        "--mobility", action="store_true", help="also count partitions by number of legal faces"
    )
    args = parser.parse_args()
    output: dict[str, object] = {}
    brute_results = {}
    small_cases = [
        ((2, 2, 1), (15, 8)),
        ((3, 3, 1), (21_147, 322)),
        ((2, 2, 2), (4_140, 154)),
    ]
    for dimensions, expected in small_cases:
        actual = brute_set_partitions(*dimensions)
        assert actual == expected, (dimensions, actual, expected)
        brute_results["x".join(map(str, dimensions))] = {
            "set_partitions": actual[0], "cuboid_partitions": actual[1]
        }
    output["brute_set_partitions"] = brute_results
    transfer = layer_transfer_counts()
    assert transfer == {
        "3x3": 322,
        "3x3x2": 415_634,
        "3x3x3": 701_898_882,
        "3x3x3-core-singleton": 170_204_427,
    }
    output["layer_transfer"] = transfer
    covers = {}
    for model, (expected_tiles, expected_count, expected_rotations) in EXPECTED.items():
        domain, tiles = model_tiles(model)
        count, memo_states = exact_cover_count(domain, tiles)
        assert (len(tiles), count) == (expected_tiles, expected_count), model
        result = {"piece_placements": len(tiles), "partitions": count, "memo_states": memo_states}
        if args.mobility:
            mobility = legal_face_distribution(domain, tiles)
            assert mobility == EXPECTED_MOBILITY[model], (model, mobility)
            assert sum(mobility) == count
            result["partitions_by_legal_face_count"] = mobility
        if args.rotations:
            classes, fixed_counts, frozen_classes = rotation_classes(
                domain, tiles, mobility=args.mobility
            )
            assert classes == expected_rotations, (model, classes, expected_rotations)
            result.update(rotation_classes=classes, fixed_partition_counts=fixed_counts)
            if args.mobility:
                assert frozen_classes == EXPECTED_FROZEN_ROTATIONS[model]
                result["frozen_rotation_classes"] = frozen_classes
        covers[model] = result
    output["exact_cover"] = covers
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
