"""Exact partition counts, rotation quotients, and explicit scan completeness."""

import json
import unittest

import bce_v2 as c


class EnumerationTests(unittest.TestCase):
    def test_count_models_and_burnside_evidence(self):
        counts = [c.count_partitions(), c.count_partitions(core_bonds=True),
                  c.count_partitions(strict_core_singleton=True)]
        self.assertEqual(len({count["model"] for count in counts}), 3)
        for count in counts:
            with self.subTest(model=count["model"]):
                self.assertEqual(count["symmetry"], "proper-rotations")
                self.assertEqual(len(count["fixed_by_rotation"]), 24)
                self.assertEqual(count["fixed_by_rotation"][0], count["partitions"])
                self.assertEqual(sum(count["fixed_by_rotation"]),
                                 count["rotation_classes"] * 24)
                self.assertGreater(count["placements"], 0)
                self.assertGreater(count["memo_states"], 0)
                self.assertEqual(json.loads(json.dumps(count)), count)
        self.assertGreater(counts[0]["partitions"], counts[2]["partitions"])
        self.assertGreater(counts[1]["partitions"], counts[2]["partitions"])

    def test_partition_prefix_is_deterministic_connected_and_has_no_core_bonds(self):
        prefix = c.cuboid_partitions(limit=50)
        self.assertEqual(prefix, c.cuboid_partitions(limit=50))
        self.assertEqual(len(prefix), 50)
        self.assertEqual(len(set(prefix)), 50)
        self.assertEqual(prefix[0], c.Shape())
        for value in prefix:
            self.assertIsInstance(value, c.Shape)
            self.assertEqual(value.labels.count(value[c.C]), 1)
            self.assertEqual(c.Shape(value.labels), value)

    def test_rotation_keys_and_canonical_shapes(self):
        labels = [0] * 27
        # A corner 2x2x2 occupies seven visible cells with an independent core.
        for cell in (0, 1, 3, 4, 9, 10, 12):
            labels[cell] = 1
        initial = c.Shape(labels)
        variants = {initial.rotated(rotation) for rotation in range(24)}
        self.assertEqual(len(variants), 8)
        self.assertEqual(initial.rotated(0), initial)
        self.assertEqual(len(initial.rotation_key), 14)
        for variant in variants:
            self.assertEqual(variant.rotation_key, initial.rotation_key)
            self.assertEqual(variant.canonical(), initial.canonical())
        for invalid in (-1, 24):
            with self.assertRaises(ValueError):
                initial.rotated(invalid)
        with self.assertRaises(TypeError):
            initial.rotated(True)

    def test_seed_limit_keeps_exact_component_results_and_partial_status(self):
        result = c.enumerate_puzzles(max_seeds=1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["stop_reason"], "seed-limit")
        self.assertEqual(result["progress"]["seeds_scanned"], 1)
        self.assertEqual(result["progress"]["classes"], 1)
        self.assertEqual(result["progress"]["expanded_shape_vertices"], 1)
        record, = result["representatives"]
        self.assertEqual(c.Shape(record["labels"]), c.Shape())
        self.assertEqual(record["id"], c.Shape().rotation_key)
        self.assertEqual(record["raw_component_vertices"], 1)
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertEqual(result, c.enumerate_puzzles(max_seeds=1))

    def test_partial_component_is_not_counted(self):
        result = c.enumerate_puzzles(max_seeds=2, max_component_vertices=1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["stop_reason"], "component-limit")
        self.assertEqual(result["progress"]["seeds_scanned"], 2)
        self.assertEqual(result["progress"]["raw_components_explored"], 1)
        self.assertEqual(result["progress"]["classes"], 1)
        self.assertEqual(len(result["representatives"]), 1)

    def test_implicit_closure_and_core_policy(self):
        initial = c.Shape()
        self.assertEqual(c.close_implicit(initial, max_vertices=1), initial)
        self.assertEqual(c.enumerate_puzzles(implicit_bonds=True, max_seeds=1)
                         ["representatives"][0]["labels"], initial.labels)
        fused = c.Shape([1] * 27)
        self.assertEqual(c.close_implicit(fused, core_bonds=True), fused)
        with self.assertRaises(ValueError):
            c.close_implicit(fused)
        labels = [0] * 27
        labels[c.UBL] = labels[c.UB] = 1
        with self.assertRaises(ValueError):
            c.close_implicit(c.Shape(labels), max_vertices=1)

    def test_flags_and_limits_are_explicit(self):
        for function in (c.count_partitions, c.enumerate_puzzles):
            with self.subTest(function=function.__name__), self.assertRaises(ValueError):
                function(core_bonds=True, strict_core_singleton=True)
            with self.subTest(function=function.__name__), self.assertRaises(TypeError):
                function(core_bonds=1)
        for name in ("max_seeds", "max_component_vertices"):
            for value in (0, -1):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    c.enumerate_puzzles(**{name: value})
            for value in (True, 1.5, "3"):
                with self.subTest(name=name, value=value), self.assertRaises(TypeError):
                    c.enumerate_puzzles(**{name: value})
        with self.assertRaises(TypeError):
            c.cuboid_partitions(limit=None)
        with self.assertRaises(ValueError):
            c.cuboid_partitions(limit=0)
        with self.assertRaises(TypeError):
            c.enumerate_puzzles(implicit_bonds=1)


if __name__ == "__main__":
    unittest.main()
