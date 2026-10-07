"""Validate the complete shell-class CSV independently, without graph reruns.

Run with the v2 Python environment and a classes CSV positional argument.
An optional --summary accepts the scanner's CSV summary or retained JSON
manifest; --output preserves the validation report as JSON.
"""

import argparse
import csv
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path

import bce_v2 as c

EXPECTED_CLASSES = 7_073
EXPECTED_GEOMETRIC_CLASSES = 13_016_719
EXPECTED_SEEDS = 312_238_908

# Construct geometry and all determinant-positive signed permutations here,
# independently of the Rust rotation tables and optimized bond layout.
BONDS = [(cell, cell + stride) for stride in (9, 3, 1)
         for cell in range(27) if (cell // stride) % 3 < 2]
assert len(BONDS) == 54
NEIGHBORS = [[] for _ in range(27)]
for a, b in BONDS:
    NEIGHBORS[a].append(b)
    NEIGHBORS[b].append(a)

ROTATIONS = []
for axes in itertools.permutations(range(3)):
    parity = (-1) ** sum(axes[a] > axes[b]
                         for a in range(3) for b in range(a + 1, 3))
    for signs in itertools.product((-1, 1), repeat=3):
        if parity * signs[0] * signs[1] * signs[2] != 1:
            continue
        destinations = []
        for cell in range(27):
            point = (cell % 3 - 1, 1 - ((cell // 3) % 3), 1 - cell // 9)
            x, y, z = (point[axes[i]] * signs[i] for i in range(3))
            destinations.append((1 - z) * 9 + (1 - y) * 3 + x + 1)
        ROTATIONS.append(destinations)
assert len({tuple(rotation) for rotation in ROTATIONS}) == 24

CUT_MASKS = [sum(1 << cell for cell in range(27)
                 if (cell // stride) % 3 < level)
             for stride in (9, 3, 1) for level in (1, 2)]


def bond_word(labels):
    return sum(1 << i for i, (a, b) in enumerate(BONDS)
               if labels[a] == labels[b])


def independent_rotation_minimum(labels):
    words = []
    for destinations in ROTATIONS:
        rotated = [0] * 27
        for source, target in enumerate(destinations):
            rotated[target] = labels[source]
        words.append(bond_word(rotated))
    return min(words)


def validate_partition(labels):
    shape = c.Shape(labels)
    assert shape.labels == labels, "labels must be normalized"
    assert labels.count(labels[13]) == 1, "the core must remain independent"
    blocks = {}
    for cell, label in enumerate(labels):
        blocks.setdefault(label, set()).add(cell)
    for cells in blocks.values():
        reached = {next(iter(cells))}
        pending = list(reached)
        while pending:
            for neighbor in NEIGHBORS[pending.pop()]:
                if neighbor in cells and neighbor not in reached:
                    reached.add(neighbor)
                    pending.append(neighbor)
        assert reached == cells, "each block must be connected"
        if cells == {13}:
            continue
        bounds = [(min((cell // stride) % 3 for cell in cells),
                   max((cell // stride) % 3 for cell in cells))
                  for stride in (9, 3, 1)]
        expected = {z * 9 + y * 3 + x
                    for z in range(bounds[0][0], bounds[0][1] + 1)
                    for y in range(bounds[1][0], bounds[1][1] + 1)
                    for x in range(bounds[2][0], bounds[2][1] + 1)} - {13}
        assert cells == expected, "each shell block must fill its projected box"
    return shape


def is_guillotine(labels):
    """Find a recursive full-plane slicing after discarding the ghost core."""
    blocks = {}
    for cell, label in enumerate(labels):
        if cell != 13:
            blocks[label] = blocks.get(label, 0) | (1 << cell)
    footprints = tuple(blocks.values())

    @lru_cache(None)
    def slice_region(region):
        contained = [block for block in footprints if block & region]
        if len(contained) <= 1:
            return True
        for cut in CUT_MASKS:
            left, right = region & cut, region & ~cut
            if not left or not right:
                continue
            if any(block & left and block & right for block in contained):
                continue
            if slice_region(left) and slice_region(right):
                return True
        return False

    return slice_region(((1 << 27) - 1) & ~(1 << 13))


def read_summary(path):
    if path.suffix == ".json":
        result = json.loads(path.read_text())
        assert result["schema"] == "bandaged-cube-enumeration-summary-v1"
        # Normalize the retained manifest's descriptive names to scanner fields.
        for destination, source in (
            ("seeds_scanned", "spatial_partitions"),
            ("raw_rotation_keys", "geometric_rotation_classes"),
            ("classes", "behavioral_motion_rotation_classes"),
            ("largest_component", "largest_raw_fixed_frame_component"),
        ):
            result[destination] = result[source]
        return result
    with path.open() as stream:
        result, = csv.DictReader(stream)
    return result


def validate(classes_path, summary_path=None):
    if not __debug__:
        raise RuntimeError("validation requires Python assertions; run without -O")
    with classes_path.open() as stream:
        first_line = stream.readline().strip()
        assert first_line.startswith("# bandaged-cube-enumeration-v1 ")
        metadata = dict(token.split("=", 1) for token in first_line.split()[2:])
        assert metadata["model"] == "shell-cuboids"
        assert metadata["core_bonds"] == "false"
        assert metadata["symmetry"] == "proper-rotations"
        assert metadata["motion"] == "outer-face-turns"
        assert metadata["implicit_bonds"] == metadata["complete"] == "true"
        assert not metadata["stop_reason"]
        assert int(metadata["seeds_scanned"]) == EXPECTED_SEEDS
        rows = list(csv.DictReader(stream))
    assert len(rows) == EXPECTED_CLASSES
    checks = ["exact seed-count certificate", "normalized labels", "independent core",
              "connected shell footprints", "projected cuboid footprints",
              "independent proper-rotation minimum", "canonical bond identifier",
              "valid seed footprints", "positive component sizes",
              "sorted unique identifiers", "whole-block guillotine decomposition on physical shell"]
    largest_component = None
    if summary_path is not None:
        summary = read_summary(summary_path)
        assert summary["model"] == "shell-cuboids"
        assert str(summary["implicit_bonds"]).lower() == "true"
        assert str(summary["complete"]).lower() == "true"
        assert not summary["stop_reason"]
        assert int(summary["seeds_scanned"]) == EXPECTED_SEEDS
        assert int(summary["raw_rotation_keys"]) == EXPECTED_GEOMETRIC_CLASSES
        assert len(rows) == int(summary["classes"])
        largest_component = int(summary["largest_component"])
        checks.insert(1, "exact Burnside orbit-count certificate")
        if "schema" in summary:
            assert summary["core_bonds"] is False
            assert summary["reflections"] is False
            assert summary["dead_end_filter"] == "none"
            assert summary["symmetry"] == "proper-rotations"
            assert summary["moves"] == "outer-face-turns"
            assert summary["representatives_file"] == classes_path.name
            checksum = hashlib.sha256(classes_path.read_bytes()).hexdigest()
            assert summary["representatives_sha256"] == checksum
            checks.append("retained manifest model and SHA-256 checksum")
    keys = []
    frozen = 0
    for row in rows:
        key = row["representative_axis_major"]
        assert len(key) == 14 and key == f"{int(key, 16):014x}"
        labels = list(map(int, row["representative_labels"].split()))
        shape = validate_partition(labels)
        assert int(key, 16) == bond_word(labels)
        assert int(key, 16) == independent_rotation_minimum(labels)
        assert key == shape.rotation_key
        assert is_guillotine(labels), f"closed representative {key} must admit guillotine cuts"
        validate_partition(list(map(int, row["seed_labels"].split())))
        component_size = int(row["raw_component_vertices"])
        assert component_size >= 1
        if largest_component is not None:
            assert component_size <= largest_component
        frozen += not shape.legal_moves
        keys.append(key)
    assert keys == sorted(set(keys)), "identifiers must be unique and sorted"
    assert frozen == 1, "the complete behavioral quotient must retain one frozen class"
    return {
        "complete": True,
        "representatives_checked": len(rows),
        "frozen_representatives": frozen,
        "guillotine_representatives": len(rows),
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classes", type=Path, help="complete shell-class CSV")
    parser.add_argument("--summary", type=Path, help="scanner CSV summary or retained JSON manifest")
    parser.add_argument("--output", type=Path, help="write the validation report as JSON")
    args = parser.parse_args()
    summary_path = args.summary
    if summary_path is None:
        candidate = args.classes.with_name(args.classes.stem.replace("-puzzles", "-summary") + ".json")
        if candidate.is_file():
            summary_path = candidate
    report = validate(args.classes, summary_path)
    text = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
