"""Independently check mirror pair certificates and filtered shell atlases.

Run using the v2 Python environment. All 7,073 source IDs, mirror involutions,
orbit counts, mobility filters, and retained rows are checked. A deterministic
sample also reruns complete original and reflected shape components, using an
independently constructed spatial reflection and proper-rotation minimum.

Example:
    v2/.venv/bin/python v2/research/validate_mirror_analysis.py \
        v2/enumeration-results/2026-10-06-shell-mirror-analysis.json
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import bce_v2 as c
from validate_enumeration import bond_word, independent_rotation_minimum


ATLAS_FIELDS = (
    "representative_axis_major", "raw_component_vertices",
    "representative_labels", "seed_labels",
)
PAIR_FIELDS = (
    "class_id", "mirror_class_id", "fixed_frame_vertices",
    "proper_rotation_shape_keys", "ever_faces", "ever_axes",
)
AXES = {face: axis for axis, faces in enumerate(("RL", "UD", "FB"))
        for face in faces}
FILTERS = {
    "none": lambda row: True,
    "frozen": lambda row: bool(row["faces"]),
    "one-axis": lambda row: row["axes"] >= 2,
    "unchanging-shape": lambda row: row["vertices"] > 1,
}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read_atlas(path):
    with path.open() as stream:
        declaration = stream.readline().strip()
        check(declaration.startswith("# bandaged-cube-enumeration-v1 "),
              f"invalid atlas declaration: {path}")
        metadata = dict(token.split("=", 1)
                        for token in declaration.split()[2:])
        reader = csv.DictReader(stream)
        check(tuple(reader.fieldnames or ()) == ATLAS_FIELDS,
              f"unexpected atlas columns: {path}")
        rows = list(reader)
    keys = [row["representative_axis_major"] for row in rows]
    check(keys == sorted(set(keys)), f"atlas IDs must be unique and sorted: {path}")
    for key in keys:
        check(len(key) == 14 and key == f"{int(key, 16):014x}",
              f"invalid stable ID: {key}")
    for field, expected in {
        "model": "shell-cuboids", "core_bonds": "false",
        "implicit_bonds": "true", "complete": "true",
        "motion": "outer-face-turns",
    }.items():
        check(metadata.get(field) == expected,
              f"atlas requires {field}={expected}: {path}")
    return metadata, {row["representative_axis_major"]: row for row in rows}


def reflect_labels(labels):
    """Reflect the x coordinate, independently of the native geometry tables."""
    reflected = [0] * 27
    for source, label in enumerate(labels):
        target = source - source % 3 + 2 - source % 3
        reflected[target] = label
    return reflected


def graph_samples(measurements, requested, maximum_vertices):
    """Cover both chirality cases and several component sizes deterministically."""
    if not requested:
        return []
    eligible = [row for row in measurements.values()
                if row["vertices"] <= maximum_vertices]
    candidates = []
    requiring_motion = [row for row in eligible if row["reflection_requires_motion"]]
    if requiring_motion:
        candidates.append(min(requiring_motion, key=lambda row: (
            row["vertices"], row["key"])))
    for upper in (1, 4, 16, 64, 256, 1_024, 4_096, maximum_vertices):
        for chiral in (False, True):
            choices = [row for row in eligible
                       if row["vertices"] <= upper
                       and (row["key"] != row["mirror"]) == chiral]
            if choices:
                candidates.append(max(choices, key=lambda row: (
                    row["vertices"], -int(row["key"], 16))))
    candidates.extend(sorted(eligible, key=lambda row: (
        row["vertices"], row["key"])))
    result = []
    seen = set()
    for row in candidates:
        if row["key"] not in seen:
            result.append(row)
            seen.add(row["key"])
            if len(result) == requested:
                break
    return result


def check_component(record, atlas):
    shape = c.Shape(list(map(int, atlas[record["key"]]["representative_labels"].split())))
    graph = c.explore(shape)
    check(graph.complete, "sample component must be complete")
    check(len(graph) == record["vertices"],
          f"incorrect component size: {record['key']}")
    faces = {movement[0] for _, _, movement in graph.arcs}
    check(faces == record["faces"], f"incorrect ever-faces: {record['key']}")
    original_keys = {independent_rotation_minimum(vertex.labels)
                     for vertex in graph}
    check(min(original_keys) == int(record["key"], 16),
          f"original component does not minimize to its ID: {record['key']}")
    check(len(original_keys) == record["rotation_keys"],
          f"incorrect proper-rotation shape count: {record['key']}")
    mirror_minimum = min(independent_rotation_minimum(reflect_labels(vertex.labels))
                         for vertex in graph)
    check(mirror_minimum == int(record["mirror"], 16),
          f"incorrect whole-component mirror ID: {record['key']}")
    reflected_graph = c.explore(c.Shape(reflect_labels(shape.labels)))
    check(reflected_graph.complete and len(reflected_graph) == len(graph),
          f"reflected component size mismatch: {record['key']}")
    reflected_minimum = min(independent_rotation_minimum(vertex.labels)
                           for vertex in reflected_graph)
    check(reflected_minimum == mirror_minimum,
          f"independent reflected exploration mismatch: {record['key']}")
    return {
        "class_id": record["key"], "mirror_class_id": record["mirror"],
        "fixed_frame_vertices": len(graph),
    }


def validate(source_path, summary_path, pairs_path, filtered_path,
             graph_checks=12, max_graph_vertices=1_024):
    source_metadata, atlas = read_atlas(source_path)
    check(source_metadata.get("symmetry") == "proper-rotations",
          "source atlas must retain mirror images")
    check(source_metadata.get("dead_end_filter", "none") == "none",
          "source atlas must retain all mobility classes")
    summary = json.loads(summary_path.read_text())
    check(summary.get("schema") == "bandaged-cube-atlas-analysis-v1",
          "invalid analysis schema")
    for field, expected in {"model": "shell-cuboids", "core_bonds": False,
                            "implicit_bonds": True, "complete": True}.items():
        check(summary.get(field) == expected, f"invalid summary {field}")
    check(summary["source_classes"] == len(atlas), "source count mismatch")
    checksum_checks = []
    for prefix, path in (("source", source_path), ("pairs", pairs_path),
                         ("representatives", filtered_path)):
        if f"{prefix}_sha256" in summary:
            check(summary.get(f"{prefix}_file") == path.name,
                  f"manifest filename mismatch: {prefix}")
            check(summary[f"{prefix}_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest(),
                  f"manifest SHA-256 mismatch: {prefix}")
            checksum_checks.append(f"{prefix} manifest filename and SHA-256 checksum")
    for key, row in atlas.items():
        labels = list(map(int, row["representative_labels"].split()))
        shape = c.Shape(labels)
        check(shape.labels == labels, f"unnormalized source labels: {key}")
        check(labels.count(labels[13]) == 1, f"source core must be independent: {key}")
        check(bond_word(labels) == int(key, 16) and shape.rotation_key == key,
              f"source label/key mismatch: {key}")

    with pairs_path.open() as stream:
        reader = csv.DictReader(stream)
        check(tuple(reader.fieldnames or ()) == PAIR_FIELDS, "unexpected pair columns")
        pairs = list(reader)
    pair_keys = [row["class_id"] for row in pairs]
    check(pair_keys == sorted(atlas), "pair map must cover every source ID exactly once")
    measurements = {}
    for row in pairs:
        key, mirror = row["class_id"], row["mirror_class_id"]
        check(mirror in atlas, f"mirror class missing: {key} -> {mirror}")
        faces_list = row["ever_faces"].split()
        faces = set(faces_list)
        check(len(faces) == len(faces_list) and faces <= set(AXES),
              f"invalid face set: {key}")
        axes = len({AXES[face] for face in faces})
        vertices = int(row["fixed_frame_vertices"])
        rotation_keys = int(row["proper_rotation_shape_keys"])
        check(axes == int(row["ever_axes"]), f"axis count mismatch: {key}")
        check(1 <= rotation_keys <= vertices, f"invalid vertex/orbit counts: {key}")
        check(faces or vertices == 1, f"frozen component must be singleton: {key}")
        reflected = c.Shape(reflect_labels(list(map(
            int, atlas[key]["representative_labels"].split()))))
        reflected_pose_key = reflected.rotation_key
        check(reflected_pose_key >= mirror,
              f"mirror component minimum exceeds reflected representative: {key}")
        measurements[key] = {
            "key": key, "mirror": mirror, "vertices": vertices,
            "rotation_keys": rotation_keys, "faces": faces, "axes": axes,
            "reflection_requires_motion": reflected_pose_key != mirror,
        }
    for key, row in measurements.items():
        partner = measurements[row["mirror"]]
        check(partner["mirror"] == key, f"mirror map is not involutive: {key}")
        for field in ("vertices", "rotation_keys", "axes"):
            check(row[field] == partner[field], f"mirror partners differ in {field}: {key}")
        check(len(row["faces"]) == len(partner["faces"]),
              f"mirror partners differ in legal-face counts: {key}")
    achiral = sum(row["key"] == row["mirror"] for row in measurements.values())
    chiral_pairs = sum(row["key"] < row["mirror"] for row in measurements.values())
    check(achiral + 2 * chiral_pairs == len(atlas), "invalid mirror orbit partition")
    check(summary["achiral_classes"] == achiral, "achiral count mismatch")
    check(summary["chiral_pairs"] == chiral_pairs, "chiral-pair count mismatch")
    check(summary["expanded_closed_vertices"] == sum(row["vertices"]
                                                     for row in measurements.values()),
          "expanded vertex total mismatch")

    derived_counts = {}
    retained_ids = {}
    for policy, retains in FILTERS.items():
        proper = {key for key, row in measurements.items() if retains(row)}
        for key, row in measurements.items():
            check(retains(row) == retains(measurements[row["mirror"]]),
                  f"filter must respect mirror pairing: {policy}, {key}")
        mirrored = {min(key, measurements[key]["mirror"]) for key in proper}
        derived_counts[policy] = {
            "proper_rotations": len(proper),
            "rotations_and_reflections": len(mirrored),
        }
        retained_ids[policy] = mirrored
    check(summary["counts"] == derived_counts, "filter count table mismatch")
    policy = summary["dead_end_filter"]
    check(policy in FILTERS, "unknown selected dead-end filter")
    check(summary["filtered_mirror_classes"] == len(retained_ids[policy]),
          "selected count mismatch")

    output_metadata, filtered = read_atlas(filtered_path)
    for field, expected in {
        "symmetry": "rotations-and-reflections", "dead_end_filter": policy,
        "source_classes": str(len(atlas)), "classes": str(len(filtered)),
    }.items():
        check(output_metadata.get(field) == expected, f"invalid filtered metadata {field}")
    check(set(filtered) == retained_ids[policy],
          "filtered atlas does not contain exactly the retained mirror orbit minima")
    for key, row in filtered.items():
        check(row == atlas[key], f"filtered row differs from original atlas: {key}")

    sampled = graph_samples(measurements, graph_checks, max_graph_vertices)
    graph_results = [check_component(row, atlas) for row in sampled]
    return {
        "source_classes_checked": len(atlas), "mirror_pairs_checked": chiral_pairs,
        "achiral_classes_checked": achiral, "derived_counts": derived_counts,
        "selected_dead_end_filter": policy, "filtered_rows_checked": len(filtered),
        "representative_reflections_requiring_motion_canonicalization": sum(
            row["reflection_requires_motion"] for row in measurements.values()),
        "complete_component_graph_checks": graph_results,
        "checks": [
            "source identifiers and normalized labels", "pair-map exact coverage",
            "mirror involution", "mirror-invariant mobility and component sizes",
            "achiral and chiral orbit totals", "all four exact mobility filters",
            "filtered orbit minima and unchanged source rows",
            "sampled independent geometric reflection and complete component exploration",
        ] + checksum_checks,
    }


def main():
    results = Path(__file__).resolve().parents[1] / "enumeration-results"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path, nargs="?",
                        default=results / "2026-10-06-shell-mirror-analysis.json",
                        help="analysis JSON manifest; artifact paths resolve beside it")
    parser.add_argument("--source", type=Path, help="override the source atlas path")
    parser.add_argument("--pairs", type=Path, help="override the mirror-pair CSV path")
    parser.add_argument("--filtered", type=Path, help="override the filtered atlas path")
    parser.add_argument("--check-components", "--graph-checks", dest="graph_checks", type=int, default=12,
                        help="number of deterministic complete-component spot checks (default: 12)")
    parser.add_argument("--max-graph-vertices", type=int, default=1_024,
                        help="component-size cap for graph spot checks (default: 1024)")
    parser.add_argument("--output", type=Path, help="save the independent validation report")
    args = parser.parse_args()
    if args.graph_checks < 0 or args.max_graph_vertices <= 0:
        parser.error("graph-checks must be nonnegative and max-graph-vertices must be positive")
    manifest = json.loads(args.analysis.read_text())
    directory = args.analysis.parent
    source = args.source or directory / manifest["source_file"]
    pairs = args.pairs or directory / manifest["pairs_file"]
    filtered = args.filtered or directory / manifest["representatives_file"]
    report = validate(source, args.analysis, pairs, filtered,
                      args.graph_checks, args.max_graph_vertices)
    result = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()
