"""Independent algebra/edge checks for the Delivery 0 research probe."""

import importlib.util
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c


PROBE_PATH = Path(__file__).resolve().parents[2] / "research" / "probe_human_chains.py"
SPEC = importlib.util.spec_from_file_location("human_chain_probe", PROBE_PATH)
probe_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe_module
SPEC.loader.exec_module(probe_module)


class FeatureActionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = c.BlockInventory(c.Shape())
        self.turn = tuple(c.State().apply("R").sticker_permutation)
        self.elements, self.alphabet = probe_module.enumerate_group((self.turn,), 4)
        self.actions = probe_module.action_summaries(self.inventory, self.elements)

    def test_right_turn_closure_and_transported_phases(self):
        # Ordinary R moves corners between slots with different twist phases;
        # applying it twice has no corner twists. Using the source index for
        # the second phase would fail this independently observed cube fact.
        half = probe_module.then(self.turn, self.turn)
        self.assertEqual(self.inventory.action(half).phases,
                         self.inventory.action(c.State().apply("R2")).phases)
        self.assertTrue(all(phase == 0 for phase in self.actions[half].phases))
        first = self.actions[self.turn]
        self.assertTrue(any(first.phases[i] != first.phases[d]
                            for i, d in enumerate(first.destinations)))
        probe_module.check_feature_actions(
            self.inventory, self.elements, self.alphabet, self.actions)

    def test_balanced_but_wrong_observation_fibers_are_rejected(self):
        half = probe_module.then(self.turn, self.turn)
        inverse = probe_module.inverse(self.turn)
        target = (probe_module.IDENTITY, half)
        fibers = {0: [probe_module.IDENTITY, self.turn], 1: [half, inverse]}
        with self.assertRaisesRegex(ValueError, "right coset"):
            probe_module.validate_cosets(self.elements, target, fibers)

    def test_incorrect_certified_orders_are_not_credited(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            probe_module.enumerate_group((self.turn,), 1)
        with self.assertRaisesRegex(ValueError, "disagrees"):
            probe_module.enumerate_group((self.turn,), 8)

    def test_invalid_limits_are_rejected_before_preparation(self):
        for invalid in (True, 1.5, "4", 0, -1):
            with self.subTest(invalid=invalid):
                with patch.object(c, "isotropy_loops", side_effect=AssertionError("unexpected work")):
                    with self.assertRaises((TypeError, ValueError)):
                        probe_module.probe(c.Shape(), max_group_elements=invalid)

    def test_output_aliases_are_rejected_before_work_and_keep_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            output.write_text("existing result", encoding="utf-8")
            alias = Path(directory) / "alias.json"
            os.link(output, alias)
            for measurements in (output, alias):
                with self.subTest(measurements=measurements):
                    with patch.object(probe_module, "probe", side_effect=AssertionError("unexpected work")):
                        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                            probe_module.main(["--output", str(output),
                                               "--measurements", str(measurements)])
                    self.assertEqual(error.exception.code, 2)
                    self.assertEqual(output.read_text(encoding="utf-8"), "existing result")


@unittest.skipUnless(shutil.which("gap"), "GAP is required for exact probe integration")
class ProbeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fused_face = c.Shape([1] * 9 + [2] * 18)
        cls.record, cls.measurements = probe_module.probe(
            cls.fused_face, max_group_elements=4)

    def test_fixed_footprint_retains_all_four_observable_orientations(self):
        self.assertEqual((self.record["group_order"], self.record["quotient_order"],
                          self.record["kernel_order"]), ("4", "1", "4"))
        self.assertEqual(self.record["status"], "completed")
        self.assertEqual(self.record["enumerated_elements"], 4)
        placement = self.record["chains"]["placement_then_orientation"]
        self.assertEqual(placement["placement_terminal_order"], "4")
        self.assertEqual(len(placement["stages"]), 1)
        stage = placement["stages"][0]
        self.assertEqual(stage["feature"]["kind"], "solve_block")
        self.assertEqual(stage["observations"], [[0, 0], [0, 1], [0, 2], [0, 3]])
        self.assertEqual((stage["index"], stage["order_after"]), (4, "1"))
        self.assertFalse(self.record["human_method_complete"])
        self.assertEqual(self.record["coverage_scope"], "chain_structure_only")

    def test_trivial_group_produces_empty_chains(self):
        record, _ = probe_module.probe(c.Shape([1] * 27))
        self.assertEqual(record["group_order"], "1")
        self.assertEqual(record["enumerated_elements"], 1)
        self.assertEqual(record["reduced_generator_ids"], [])
        for chain in record["chains"].values():
            self.assertEqual(chain["stages"], [])
            self.assertEqual(chain["terminal_order"], "1")

    def test_preflight_limit_never_enumerates_or_emits_a_partial_chain(self):
        with patch.object(probe_module, "enumerate_group", side_effect=AssertionError("unexpected enumeration")):
            record, _ = probe_module.probe(self.fused_face, max_group_elements=3)
        self.assertEqual(record["status"], "limit_reached")
        self.assertEqual(record["reason"], "group_order_exceeds_limit")
        self.assertEqual(record["group_order"], "4")
        self.assertEqual(record["enumerated_elements"], 0)
        self.assertFalse(record["enumeration_complete"])
        self.assertEqual(record["chains"], {})

    def test_repeated_probe_has_identical_results_with_separate_measurements(self):
        repeated, _ = probe_module.probe(self.fused_face, max_group_elements=4)
        self.assertEqual(probe_module.json_text(repeated), probe_module.json_text(self.record))
        self.assertIn("elapsed_seconds", self.measurements)
        self.assertNotIn("elapsed_seconds", self.record)


if __name__ == "__main__":
    unittest.main()
