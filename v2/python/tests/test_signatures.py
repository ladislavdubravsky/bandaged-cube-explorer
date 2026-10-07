"""Physical inventories, invariance, and queries on the complete class atlas."""

from collections import Counter, defaultdict
import hashlib
import json
from itertools import product
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest

import bce_v2 as c


RESULTS = Path(__file__).resolve().parents[2] / "enumeration-results"
DATABASE = RESULTS / "2026-10-07-shell-signatures.sqlite3"


def fused(cells):
    labels = [0] * 27
    for cell in cells:
        labels[cell] = 1
    return c.Shape(labels)


def inventory(shape, *, core_bonds=False):
    return Counter((b.type, b.cubies, b.corners, b.edges, b.centers, b.cores, b.core_hole)
                   for b in c.classify_blocks(shape, core_bonds=core_bonds))


class SignatureTests(unittest.TestCase):
    def test_types_format_and_physical_singletons(self):
        self.assertEqual(len(c.BLOCK_TYPES), 17)
        self.assertEqual(c.format_signature({"Pair": 2, "Clock": 1, "221": 2, "111": 12}),
                         "2x221 Clock 2xPair")
        self.assertEqual(c.format_signature({"331": 1, "322": 1, "222": 1}),
                         "322 331 222")
        self.assertEqual(c.block_signature(c.Shape()), {})
        self.assertEqual(c.block_signature(c.Shape(), include_singletons=True), {"111": 26})
        self.assertEqual(c.format_signature({}), "111 only")
        self.assertEqual(c.format_signature({"111": 26}, include_singletons=True), "26x111")
        self.assertEqual(c.block_signature(fused([c.UBL, c.UB])), {"Pair": 1})
        self.assertEqual(c.block_signature(fused([c.UB, c.U])), {"Clock": 1})

    def test_center_and_core_variants_are_different_types(self):
        outer = fused([0, 1, 3, 4])
        middle = fused([9, 10, 12])
        self.assertEqual(c.block_signature(outer), {"221": 1})
        self.assertEqual(c.block_signature(middle), {"221Core": 1})
        for shape, code, cubies, centers, hole, singletons in (
                (outer, "221", 4, 1, False, 22), (middle, "221Core", 3, 2, True, 23)):
            block = next(b for b in c.classify_blocks(shape) if b.type == code)
            self.assertEqual((block.cubies, block.centers, block.core_hole),
                             (cubies, centers, hole))
            self.assertEqual(c.block_signature(shape, include_singletons=True)["111"], singletons)
        for cells, code in (([0, 1, 2], "311"), ([3, 4, 5], "BigClock"),
                            ([0, 1, 2, 3, 4, 5], "321"), ([9, 10, 11, 12, 14], "321Core"),
                            (range(9), "331"), ([cell for cell in range(9, 18) if cell != 13], "331Core")):
            self.assertEqual(c.block_signature(fused(cells)), {code: 1})
        for cells, code, centers in (([13, 14], "211Core", 1), ([12, 13, 14], "311Core", 2)):
            shape = fused(cells)
            self.assertEqual(c.block_signature(shape, core_bonds=True), {code: 1})
            block = next(b for b in c.classify_blocks(shape, core_bonds=True) if b.type == code)
            self.assertEqual((block.cores, block.centers, block.core_hole), (1, centers, False))
        corner = fused([0, 1, 3, 4, 9, 10, 12])
        block = next(b for b in c.classify_blocks(corner) if b.type == "222")
        self.assertEqual((block.cubies, block.corners, block.edges, block.centers), (7, 1, 3, 3))

    def test_every_box_placement_is_covered_by_the_variant_catalogue(self):
        intervals = [range(start, stop + 1) for start in range(3) for stop in range(start, 3)]
        catalogue = {block.code: block for block in c.BLOCK_TYPES}
        full_counts = {"333": 1, "332": 6, "322": 12, "331": 6, "331Core": 3,
                       "222": 8, "321": 24, "321Core": 12, "221": 24, "221Core": 12,
                       "311": 12, "BigClock": 12, "311Core": 3,
                       "Pair": 24, "Clock": 24, "211Core": 6, "111": 27}
        for core_bonds, total in ((False, 206), (True, 216)):
            seen, counts, orbit_keys = set(), Counter(), defaultdict(set)
            for spans in product(intervals, repeat=3):
                cells = tuple(sorted(d * 9 + f * 3 + r for d, f, r in product(*spans)
                                     if core_bonds or (d, f, r) != (1, 1, 1)))
                if not cells or cells in seen:
                    continue
                try:
                    shape = fused(cells)
                except ValueError:
                    self.assertFalse(core_bonds)
                    self.assertEqual(len(cells), 2)  # Disconnected opposite-center shell rods.
                    continue
                seen.add(cells)
                block = next(b for b in c.classify_blocks(shape, core_bonds=core_bonds)
                             if b.cells == cells)
                counts[block.type] += 1
                orbit_keys[block.type].add(shape.rotation_key)
                kind = catalogue[block.type]
                self.assertEqual(kind.dimensions, block.dimensions)
                if block.type != "111":
                    self.assertEqual(kind.centers, block.centers)
                    self.assertEqual(kind.core_position, block.core_hole or bool(block.cores))
            self.assertEqual(len(seen), total)
            expected = dict(full_counts)
            if not core_bonds:
                for code in ("211Core", "311Core"):
                    del expected[code]
                expected["111"] = 26
            self.assertEqual(counts, expected)
            for code, keys in orbit_keys.items():
                if code != "111":
                    self.assertEqual(len(keys), 1, f"{code} must describe one spatial block type")

    def test_rejects_nonboxes_and_undeclared_core_bonds(self):
        with self.assertRaisesRegex(ValueError, "not a cuboid"):
            c.block_signature(fused([0, 1, 3]))
        with self.assertRaisesRegex(ValueError, "independent virtual core"):
            c.block_signature(fused([13, 14]))
        self.assertEqual(c.block_signature(fused(range(27)), core_bonds=True), {"333": 1})
        for bad in (True, 1.5, "2"):
            with self.assertRaises(TypeError):
                c.format_signature({"Pair": bad})
        for bad in (-1,):
            with self.assertRaises(ValueError):
                c.format_signature({"Pair": bad})
        with self.assertRaises(ValueError):
            c.format_signature({"211": 2})

    def test_rigid_inventory_survives_moves_rotations_and_reflection(self):
        rng = random.Random(8371)
        shapes = c.cuboid_partitions(limit=24) + [fused([9, 10, 12]), fused([3, 4, 5]),
                                                 fused([9, 10, 11, 12, 14])]
        for initial in shapes:
            expected = inventory(initial)
            for rotation in range(24):
                self.assertEqual(inventory(initial.rotated(rotation)), expected)
            reflected = [0] * 27
            for cell, label in enumerate(initial):
                reflected[cell // 3 * 3 + 2 - cell % 3] = label
            self.assertEqual(inventory(c.Shape(reflected)), expected)
            current = initial
            for _ in range(24):
                if not current.legal_moves:
                    break
                current = current.apply(rng.choice(current.legal_moves))
                self.assertEqual(inventory(current), expected)


@unittest.skipUnless(DATABASE.is_file(), "the retained signature database is not installed")
class AtlasQueryTests(unittest.TestCase):
    def test_certified_database_and_all_persisted_inventories(self):
        manifest = json.loads(DATABASE.with_suffix(".json").read_text())
        self.assertEqual(hashlib.sha256(DATABASE.read_bytes()).hexdigest(),
                         manifest["database_sha256"])
        counts = RESULTS / manifest["signature_counts_file"]
        self.assertEqual(hashlib.sha256(counts.read_bytes()).hexdigest(),
                         manifest["signature_counts_sha256"])
        with c.PuzzleAtlas(DATABASE, cohort="all") as atlas:
            self.assertEqual(atlas.query("PRAGMA integrity_check"), [{"integrity_check": "ok"}])
            self.assertEqual(atlas.query("PRAGMA foreign_key_check"), [])
            self.assertEqual(atlas.query("SELECT COUNT(*) AS n FROM (SELECT puzzle_id FROM blocks "
                                        "GROUP BY puzzle_id HAVING SUM(cubies) != 26 "
                                        "OR SUM(corners) != 8 OR SUM(edges) != 12 OR SUM(centers) != 6)"),
                             [{"n": 0}])
            counts = {}
            for row in atlas.query("SELECT puzzle_id, block_type, COUNT(*) AS n FROM blocks "
                                   "GROUP BY puzzle_id, block_type"):
                counts.setdefault(row["puzzle_id"], {})[row["block_type"]] = row["n"]
            for row in atlas.select():
                stored = counts[row["id"]]
                self.assertEqual(stored.pop("111", 0), row["singletons"])
                self.assertEqual(stored, json.loads(row["signature_counts"]))
                self.assertEqual(c.format_signature(stored), row["signature"])
            self.assertGreater(manifest["legal_successors_checked"], 0)
            self.assertEqual(manifest["mirror_inventories_checked"], 7_073)
            with self.assertRaises(sqlite3.OperationalError):
                atlas.query("DELETE FROM puzzles")

    def test_complete_cohort_queries_and_maximum_domino_puzzles(self):
        for cohort, classes, containing_222, signatures, maxima in (
                ("all", 7_073, 339, 1_735, 2), ("mirror", 4_860, 238, 1_735, 1),
                ("mobile", 7_070, 339, 1_732, 2), ("filtered", 4_857, 238, 1_732, 1)):
            with self.subTest(cohort=cohort), c.PuzzleAtlas(DATABASE, cohort=cohort) as atlas:
                self.assertEqual(len(atlas), classes)
                self.assertEqual(len(atlas.containing("222")), containing_222)
                groups = atlas.signature_counts()
                self.assertEqual(len(groups), signatures)
                self.assertEqual(sum(row["puzzles"] for row in groups), classes)
                maximum, puzzles = atlas.maximum("211", only=("211",))
                self.assertEqual((maximum, len(puzzles)), (12, maxima))
                for puzzle in puzzles:
                    self.assertEqual(puzzle["signature"], "5xClock 7xPair")
                    self.assertEqual(puzzle["singletons"], 2)
                    shape = atlas.shape(puzzle["id"])
                    self.assertEqual(c.block_signature(shape), {"Clock": 5, "Pair": 7})
                self.assertTrue(all(row["singletons_min"] == row["singletons_max"]
                                    for row in groups))
                self.assertEqual(len(groups), atlas.metadata["cohorts"][cohort]["detailed_signatures"])
                self.assertEqual(atlas.only(), atlas.select(signature="111 only"))

    def test_query_validation_and_combined_constraints(self):
        with c.PuzzleAtlas(DATABASE) as atlas:
            for code in ("Clock", "Pair", "211", "111"):
                rows = atlas.select(contains={code: 2}, only=("211",))
                allowed = {"Clock", "Pair", "111"}
                for row in rows:
                    counts = c.block_signature(atlas.shape(row["id"]), include_singletons=True)
                    self.assertLessEqual(set(counts), allowed)
                    count = counts.get("Clock", 0) + counts.get("Pair", 0) if code == "211" else counts.get(code, 0)
                    self.assertGreaterEqual(count, 2)
            with self.assertRaises(ValueError):
                atlas.containing("999")
            with self.assertRaises(TypeError):
                atlas.containing("Pair", at_least=True)
            with self.assertRaises(ValueError):
                atlas.containing("Pair", at_least=0)
            with self.assertRaises(TypeError):
                atlas.select(only="211")
            with self.assertRaises(KeyError):
                atlas.shape("not-an-id")
        with self.assertRaises(ValueError):
            c.PuzzleAtlas(DATABASE, cohort="invented")

    def test_position_variants_query_independently_and_stale_schema_is_rejected(self):
        with c.PuzzleAtlas(DATABASE) as atlas:
            for code, expected in (("221", 2_511), ("221Core", 1_456),
                                   ("321", 1_003), ("321Core", 871),
                                   ("311", 2_418), ("BigClock", 2_179)):
                rows = atlas.containing(code)
                self.assertEqual(len(rows), expected)
                self.assertTrue(all(json.loads(row["signature_counts"])[code] >= 1 for row in rows))
            self.assertEqual(atlas.containing("211Core"), [])
            self.assertEqual(atlas.containing("311Core"), [])
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "old.sqlite3"
            with sqlite3.connect(stale) as connection:
                connection.execute("PRAGMA user_version = 1")
            with self.assertRaisesRegex(ValueError, "rebuild"):
                c.PuzzleAtlas(stale)


if __name__ == "__main__":
    unittest.main()
