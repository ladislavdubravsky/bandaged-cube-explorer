"""Automatic vocabularies use actual bandage legality and original witnesses."""

import shutil
import unittest

import bce_v2 as c
from bce_v2.automatic_palette import automatic_algorithm_palette


class AutomaticPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ordinary_loops = c.isotropy_loops(c.Shape())
        cls.fused_shape = c.Shape([1] * 9 + [2] * 18)
        cls.fused_loops = c.isotropy_loops(cls.fused_shape)
        labels = [0] * 27
        labels[c.FR] = labels[c.DFR] = 1
        cls.pair_shape = c.Shape(labels)
        cls.pair_loops = c.isotropy_loops(cls.pair_shape)

    def assert_witnesses(self, palette, loops):
        palette.validate(inventory=loops.block_inventory, generators=loops.generators)
        for declaration in (*palette.bodies, *palette.setups, *palette.adjustments):
            algorithm = declaration.algorithm
            physical = c.State(loops.root_shape).apply(algorithm.turn_sequence)
            self.assertEqual(physical.shape, loops.root_shape)
            self.assertEqual(tuple(physical.sticker_permutation), algorithm.permutation)
            self.assertEqual(algorithm.expression.evaluate(loops), algorithm.permutation)
            self.assertEqual(algorithm._generators, loops.generators)
            self.assertTrue(set(algorithm.base_ids) <= set(loops.generator_records))

    def test_ordinary_catalog_selects_four_coherent_bodies_without_supplied_words(self):
        result = automatic_algorithm_palette(self.ordinary_loops)
        palette = result.palette
        self.assertEqual([body.id for body in palette.bodies], ["EO", "Sune", "Tperm", "Ua"])
        self.assertEqual([body.algorithm.htm_length for body in palette.bodies], [6, 7, 14, 11])
        self.assertFalse(any(body.allow_inverse for body in palette.bodies))
        self.assertEqual([adjustment.id for adjustment in palette.adjustments], ["U", "U2", "U'"])
        self.assertEqual([setup.id for setup in palette.setups], ["U", "U2", "U'"])
        self.assertEqual(len(result.metadata["inferred_shared_fixed_component_indices"]), 12)
        self.assertEqual(result.metadata["selection_kind"], "familiar_preservation_cohort")
        self.assertFalse(result.metadata["coverage_claim"])
        self.assertFalse(result.metadata["goals_seeded"])
        self.assert_witnesses(palette, self.ordinary_loops)
        rejected = [row for row in result.metadata["sources"]
                    if row["source"] == "short_root_adjustment" and row["id"] == "R"]
        self.assertEqual(rejected[0]["reason"], "disrupts_selected_workspace")

    def test_fused_bandage_uses_only_legal_directed_u_adjustments(self):
        result = automatic_algorithm_palette(self.fused_loops)
        self.assertEqual(result.palette.bodies, ())
        self.assertEqual([value.id for value in result.palette.adjustments], ["U", "U2", "U'"])
        self.assertEqual(result.metadata["selection_kind"], "native_root_loops")
        familiar_rows = [row for row in result.metadata["sources"] if row["source"] == "familiar_catalog"]
        self.assertTrue(familiar_rows)
        self.assertTrue(all(row["status"] == "rejected" for row in familiar_rows))
        self.assertIn("blocked_move", {row["reason"] for row in familiar_rows})
        self.assert_witnesses(result.palette, self.fused_loops)

    def test_real_pair_bandage_rejects_nonclosing_and_blocked_catalog_words(self):
        result = automatic_algorithm_palette(self.pair_loops, max_catalog_candidates=32)
        reasons = {row.get("reason") for row in result.metadata["sources"]
                   if row["source"] == "familiar_catalog" and row["status"] == "rejected"}
        self.assertIn("blocked_move", reasons)
        self.assertIn("not_root_closing", reasons)
        self.assertLessEqual(len(result.palette.bodies), 7)
        self.assert_witnesses(result.palette, self.pair_loops)
        for declaration in result.palette._declared_algorithms:
            self.assertEqual(c.State(self.pair_shape).apply(declaration.turn_sequence).shape,
                             self.pair_shape)

    def test_hard_body_limit_including_zero_is_observed(self):
        for bound in (0, 1, 2):
            result = automatic_algorithm_palette(self.ordinary_loops, max_taught_bodies=bound,
                                                 max_catalog_candidates=32)
            self.assertLessEqual(len(result.palette.bodies), bound)
            self.assertEqual(result.metadata["body_count"], len(result.palette.bodies))
        native = automatic_algorithm_palette(self.fused_loops, max_taught_bodies=1,
            max_catalog_candidates=0, max_short_adjustment_htm=0)
        self.assertEqual(len(native.palette.bodies), 1)
        self.assertTrue(native.palette.bodies[0].allow_inverse)
        self.assertEqual(native.palette.adjustments, ())
        self.assert_witnesses(native.palette, self.fused_loops)

    def test_no_palette_can_bypass_original_proof_cap(self):
        result = automatic_algorithm_palette(self.fused_loops, max_proof_moves=0)
        self.assertEqual(result.palette.bodies, ())
        self.assertEqual(result.palette.adjustments, ())
        reasons = {row.get("reason") for row in result.metadata["sources"]}
        self.assertIn("max_proof_moves", reasons)

    def test_limits_and_metadata_are_explicit_and_immutable(self):
        for setting in ("max_taught_bodies", "max_catalog_candidates", "max_body_htm",
                        "max_native_candidates", "max_short_adjustment_htm", "max_proof_moves"):
            with self.assertRaises(TypeError):
                automatic_algorithm_palette(self.fused_loops, **{setting: True})
            with self.assertRaises(ValueError):
                automatic_algorithm_palette(self.fused_loops, **{setting: -1})
        result = automatic_algorithm_palette(self.fused_loops, max_catalog_candidates=1)
        result.metadata["sources"].clear()
        self.assertTrue(result.metadata["sources"])
        self.assertEqual(result.metadata["catalog_candidates_examined"], 1)

    @unittest.skipUnless(shutil.which("gap"), "GAP prepares reduced native generators")
    def test_alcatraz_long_native_basis_remains_replayable_and_bounded(self):
        analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=60)
        result = automatic_algorithm_palette(analysis)
        self.assertEqual(result.metadata["selection_kind"], "native_root_loops")
        self.assertEqual(len(result.palette.bodies), len(analysis.generators))
        self.assertLessEqual(len(result.palette.bodies), 7)
        self.assertTrue(all(body.allow_inverse for body in result.palette.bodies))
        self.assertTrue(all(body.algorithm.htm_length > 2 for body in result.palette.bodies))
        self.assert_witnesses(result.palette, analysis.loops)


if __name__ == "__main__":
    unittest.main()
