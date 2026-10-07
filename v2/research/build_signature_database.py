"""Build a queryable block-signature database from the certified shell atlases.

Run with v2/.venv/bin/python from the repository root. The source atlases remain
unchanged. SQLite, a complete signature-count CSV, and a provenance manifest
are produced together. No third-party data-analysis package is required.
"""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

import bce_v2 as c


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE block_types (
    code TEXT PRIMARY KEY, dimensions TEXT NOT NULL, box_volume INTEGER NOT NULL,
    name TEXT NOT NULL, description TEXT NOT NULL, display_order INTEGER NOT NULL
);
CREATE TABLE puzzles (
    id TEXT PRIMARY KEY, mirror_id TEXT NOT NULL,
    mirror_representative INTEGER NOT NULL CHECK(mirror_representative IN (0, 1)),
    ever_axes INTEGER NOT NULL CHECK(ever_axes BETWEEN 0 AND 3),
    ever_faces TEXT NOT NULL, fixed_frame_vertices INTEGER NOT NULL,
    raw_component_vertices INTEGER NOT NULL,
    signature TEXT NOT NULL, signature_counts TEXT NOT NULL,
    detailed_signature TEXT NOT NULL, singletons INTEGER NOT NULL,
    labels TEXT NOT NULL, seed_labels TEXT NOT NULL
);
CREATE TABLE blocks (
    puzzle_id TEXT NOT NULL REFERENCES puzzles(id), label INTEGER NOT NULL,
    block_type TEXT NOT NULL REFERENCES block_types(code), cubies INTEGER NOT NULL,
    corners INTEGER NOT NULL, edges INTEGER NOT NULL, centers INTEGER NOT NULL,
    core_hole INTEGER NOT NULL CHECK(core_hole IN (0, 1)),
    PRIMARY KEY(puzzle_id, label)
);
CREATE INDEX puzzles_signature ON puzzles(signature);
CREATE INDEX blocks_type ON blocks(block_type, puzzle_id);
CREATE VIEW puzzles_all AS SELECT * FROM puzzles;
CREATE VIEW puzzles_mirror AS SELECT * FROM puzzles WHERE mirror_representative = 1;
CREATE VIEW puzzles_mobile AS SELECT * FROM puzzles WHERE ever_axes >= 2;
CREATE VIEW puzzles_filtered AS SELECT * FROM puzzles
    WHERE mirror_representative = 1 AND ever_axes >= 2;
CREATE VIEW block_inventory AS
    SELECT b.*, t.dimensions, t.box_volume, t.name FROM blocks b
    JOIN block_types t ON t.code = b.block_type;
CREATE VIEW signature_totals AS
    SELECT signature, signature_counts, COUNT(*) AS all_puzzles,
        SUM(mirror_representative) AS mirror_puzzles,
        SUM(ever_axes >= 2) AS mobile_puzzles,
        SUM(mirror_representative AND ever_axes >= 2) AS filtered_puzzles,
        MIN(singletons) AS singletons_min_all, MAX(singletons) AS singletons_max_all,
        MIN(CASE WHEN mirror_representative AND ever_axes >= 2 THEN singletons END)
            AS singletons_min_filtered,
        MAX(CASE WHEN mirror_representative AND ever_axes >= 2 THEN singletons END)
            AS singletons_max_filtered
    FROM puzzles GROUP BY signature ORDER BY signature;
"""
COHORTS = ("all", "mirror", "mobile", "filtered")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_atlas(path):
    with path.open() as stream:
        declaration = stream.readline().split()
        require(declaration[:2] == ["#", "bandaged-cube-enumeration-v1"],
                f"unsupported atlas format: {path}")
        metadata = dict(token.split("=", 1) for token in declaration[2:])
        rows = list(csv.DictReader(stream))
    for key, expected in {"model": "shell-cuboids", "core_bonds": "false",
                          "implicit_bonds": "true", "complete": "true",
                          "motion": "outer-face-turns"}.items():
        require(metadata.get(key) == expected, f"atlas requires {key}={expected}")
    keys = [row["representative_axis_major"] for row in rows]
    require(keys == sorted(set(keys)), "atlas IDs must be unique and sorted")
    return metadata, {row["representative_axis_major"]: row for row in rows}


def inventory(blocks):
    counts = Counter(block.type for block in blocks)
    nonsingletons = {block.code: counts[block.code] for block in c.BLOCK_TYPES
                     if block.code != "111" and counts[block.code]}
    details = Counter((block.type, block.cubies, block.corners, block.edges,
                       block.centers, block.core_hole) for block in blocks)
    details = [[*key, count] for key, count in sorted(details.items())]
    return (c.format_signature(nonsingletons),
            json.dumps(nonsingletons, separators=(",", ":")),
            json.dumps(details, separators=(",", ":")), counts["111"])


def summarize(connection, cohort):
    view = f"puzzles_{cohort}"
    classes, signatures, detailed = connection.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT signature), COUNT(DISTINCT detailed_signature) "
        f"FROM {view}").fetchone()
    with_singletons = connection.execute(
        f"SELECT COUNT(*) FROM (SELECT 1 FROM {view} GROUP BY signature, singletons)").fetchone()[0]
    containing_222 = connection.execute(
        f"SELECT COUNT(*) FROM {view} p WHERE EXISTS (SELECT 1 FROM blocks b "
        "WHERE b.puzzle_id = p.id AND b.block_type = '222')").fetchone()[0]
    candidates = connection.execute(
        f"SELECT p.id, p.signature, p.singletons, "
        "SUM(b.block_type IN ('Clock', 'Pair')) AS dominoes "
        f"FROM {view} p JOIN blocks b ON b.puzzle_id = p.id GROUP BY p.id "
        "HAVING SUM(b.block_type NOT IN ('Clock', 'Pair', '111')) = 0 "
        "ORDER BY dominoes DESC, p.id").fetchall()
    maximum = candidates[0][3]
    maximum_puzzles = [dict(zip(("id", "signature", "singletons", "dominoes"), row))
                       for row in candidates if row[3] == maximum]
    return {"puzzles": classes, "signatures": signatures,
            "signatures_with_singletons": with_singletons, "detailed_signatures": detailed,
            "containing_222": containing_222, "maximum_domino_only_blocks": maximum,
            "maximum_domino_only_puzzles": maximum_puzzles}


def build(results, database_path, counts_path, manifest_path, *, check_turns=True):
    original_manifest_path = results / "2026-10-06-shell-summary.json"
    mirror_manifest_path = results / "2026-10-06-shell-mirror-analysis.json"
    original_manifest = json.loads(original_manifest_path.read_text())
    mirror_manifest = json.loads(mirror_manifest_path.read_text())
    source_path = results / mirror_manifest["source_file"]
    filtered_path = results / mirror_manifest["representatives_file"]
    pairs_path = results / mirror_manifest["pairs_file"]
    for prefix, path in (("source", source_path), ("representatives", filtered_path),
                         ("pairs", pairs_path)):
        require(digest(path) == mirror_manifest[prefix + "_sha256"],
                f"source checksum mismatch: {path}")
    require(digest(source_path) == original_manifest["representatives_sha256"],
            "original atlas checksum mismatch")
    source_metadata, source = read_atlas(source_path)
    filtered_metadata, filtered = read_atlas(filtered_path)
    require(source_metadata["symmetry"] == "proper-rotations", "wrong source symmetry")
    require(filtered_metadata["symmetry"] == "rotations-and-reflections"
            and filtered_metadata["dead_end_filter"] == "one-axis", "wrong filtered policy")
    with pairs_path.open() as stream:
        pair_rows = list(csv.DictReader(stream))
    require([row["class_id"] for row in pair_rows] == list(source),
            "pair map must cover the source exactly once in sorted order")
    pairs = {row["class_id"]: row for row in pair_rows}
    require(len(source) == original_manifest["behavioral_motion_rotation_classes"]
            == mirror_manifest["source_classes"], "source count mismatch")
    sources = {"atlas": source_path, "filtered_atlas": filtered_path,
               "mirror_pairs": pairs_path, "atlas_manifest": original_manifest_path,
               "mirror_manifest": mirror_manifest_path}
    outputs = [database_path.resolve(), counts_path.resolve(), manifest_path.resolve()]
    require(len(set(outputs)) == 3 and not set(outputs).intersection(
        path.resolve() for path in sources.values()), "outputs must be distinct from sources")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    counts_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(dir=database_path.parent, suffix=".sqlite3", delete=False)
    temporary.close()
    temporary_path = Path(temporary.name)
    signatures = {}
    checked_turns = 0
    try:
        with sqlite3.connect(temporary_path) as connection:
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA user_version = 1")
            connection.executemany("INSERT INTO block_types VALUES (?, ?, ?, ?, ?, ?)", [
                (block.code, "".join(map(str, block.dimensions)), block.volume,
                 block.name, block.description, order)
                for order, block in enumerate(c.BLOCK_TYPES)])
            for key, row in source.items():
                labels = list(map(int, row["representative_labels"].split()))
                shape = c.Shape(labels)
                require(shape.labels == labels and shape.rotation_key == key,
                        f"invalid representative: {key}")
                blocks = c.classify_blocks(shape)
                require(sum(block.cubies for block in blocks) == 26, "shell cubie count mismatch")
                require(sum(block.corners for block in blocks) == 8
                        and sum(block.edges for block in blocks) == 12
                        and sum(block.centers for block in blocks) == 6, "cubie-kind totals mismatch")
                signature = inventory(blocks)
                signatures[key] = signature
                if check_turns:
                    for face in "URFDLB":
                        if shape.is_turnable(face):
                            require(inventory(c.classify_blocks(shape.apply(face))) == signature,
                                    f"signature changed after {face} in {key}")
                            checked_turns += 1
                pair = pairs[key]
                mirror = pair["mirror_class_id"]
                require(mirror in source and pairs[mirror]["mirror_class_id"] == key,
                        "mirror map must be a complete involution")
                axes = int(pair["ever_axes"])
                selected = key <= mirror and axes >= 2
                require(selected == (key in filtered), "filtered membership mismatch")
                if selected:
                    require(filtered[key] == row, "filtered source row mismatch")
                connection.execute("INSERT INTO puzzles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    key, mirror, int(key <= mirror), axes, pair["ever_faces"],
                    int(pair["fixed_frame_vertices"]), int(row["raw_component_vertices"]),
                    *signature, row["representative_labels"], row["seed_labels"]))
                connection.executemany("INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?)", [
                    (key, block.label, block.type, block.cubies, block.corners,
                     block.edges, block.centers, int(block.core_hole)) for block in blocks])
            require(set(filtered) <= set(source), "filtered atlas contains unknown IDs")
            for key, signature in signatures.items():
                require(signature == signatures[pairs[key]["mirror_class_id"]],
                        f"mirror partners have different inventories: {key}")
            summaries = {cohort: summarize(connection, cohort) for cohort in COHORTS}
            expected_policies = {"all": ("none", "proper_rotations"),
                                 "mirror": ("none", "rotations_and_reflections"),
                                 "mobile": ("one-axis", "proper_rotations"),
                                 "filtered": ("one-axis", "rotations_and_reflections")}
            for cohort, (policy, field) in expected_policies.items():
                require(summaries[cohort]["puzzles"] == mirror_manifest["counts"][policy][field],
                        f"cohort count mismatch: {cohort}")
            metadata = {
                "schema": "bandaged-cube-block-signatures-v1", "core_bonds": False,
                "implicit_bonds": True, "model": "shell-cuboids",
                "signature": "nonsingleton bounding-box types; 211 split into Clock and Pair",
                "singletons": "explicit physical 111 count; ghost core excluded",
                "detailed_signature_fields": ["type", "cubies", "corners", "edges",
                                              "centers", "core_hole", "multiplicity"],
                "source_files": {key: {"file": path.name, "sha256": digest(path)}
                                 for key, path in sources.items()},
                "cohorts": summaries, "legal_successors_checked": checked_turns,
                "mirror_inventories_checked": len(source),
            }
            connection.executemany("INSERT INTO metadata VALUES (?, ?)",
                                   [(key, json.dumps(value, sort_keys=True))
                                    for key, value in metadata.items()])
            require(connection.execute("PRAGMA integrity_check").fetchone() == ("ok",),
                    "SQLite integrity check failed")
            require(not connection.execute("PRAGMA foreign_key_check").fetchall(),
                    "SQLite foreign-key check failed")
            cursor = connection.execute("SELECT * FROM signature_totals")
            with counts_path.open("w", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)
        temporary_path.replace(database_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    metadata["database_file"] = database_path.name
    metadata["database_sha256"] = digest(database_path)
    metadata["signature_counts_file"] = counts_path.name
    metadata["signature_counts_sha256"] = digest(counts_path)
    manifest_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


def main():
    results = Path(__file__).resolve().parents[1] / "enumeration-results"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=results)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--counts", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--skip-turn-checks", action="store_true",
                        help="omit the default checks of legal successors of all representatives")
    args = parser.parse_args()
    database = args.output or args.results / "2026-10-07-shell-signatures.sqlite3"
    counts = args.counts or database.with_suffix(".csv")
    manifest = args.manifest or database.with_suffix(".json")
    metadata = build(args.results, database, counts, manifest,
                     check_turns=not args.skip_turn_checks)
    print(json.dumps({"cohorts": metadata["cohorts"],
                      "legal_successors_checked": metadata["legal_successors_checked"],
                      "database": str(database)}, indent=2))


if __name__ == "__main__":
    main()
