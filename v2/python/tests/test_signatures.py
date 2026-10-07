"""Physical inventories, invariance, and queries on the complete class atlas."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import unittest

import bce_v2 as c


RESULTS = Path(__file__).resolve().parents[2] / "enumeration-results"
DATABASE = RESULTS / "2026-10-07-shell-signatures.sqlite3"


def fused(cells):
    labels = [0] * 27
    for cell in cells:
        labels[cell] = 1
    return c.Shape(labels)


def inventory(shape):
    return Counter((b.type, b.cubies, b.corners, b.edges, b.centers, b.core_hole)
                   for b in c.classify_blocks(shape))


class SignatureTests(unittest.TestCase):
    def test_types_format_and_physical_singletons(self):
        self.assertEqual(len(c.BLOCK_TYPES), 11)
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

    def test_core_holes_refine_the_same_dimensional_type(self):
        outer = fused([0, 1, 3, 4])
        middle = fused([9, 10, 12])
        self.assertEqual(c.block_signature(outer), {"221": 1})
        self.assertEqual(c.block_signature(middle), {"221": 1})
        for shape, cubies, centers, hole, singletons in (
                (outer, 4, 1, False, 22), (middle, 3, 2, True, 23)):
            block = next(b for b in c.classify_blocks(shape) if b.type == "221")
            self.assertEqual((block.cubies, block.centers, block.core_hole),
                             (cubies, centers, hole))
            self.assertEqual(c.block_signature(shape, include_singletons=True)["111"], singletons)
        corner = fused([0, 1, 3, 4, 9, 10, 12])
        block = next(b for b in c.classify_blocks(corner) if b.type == "222")
        self.assertEqual((block.cubies, block.corners, block.edges, block.centers), (7, 1, 3, 3))

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
        shapes = c.cuboid_partitions(limit=24) + [fused([9, 10, 12])]
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
                ("all", 7_073, 339, 931, 2), ("mirror", 4_860, 238, 931, 1),
                ("mobile", 7_070, 339, 928, 2), ("filtered", 4_857, 238, 928, 1)):
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
                self.assertTrue(any(row["singletons_min"] != row["singletons_max"]
                                    for row in groups))
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


if __name__ == "__main__":
    unittest.main()
