"""Large-group method coverage, physical execution and portable certificates."""

from copy import deepcopy
from fractions import Fraction
import math
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_method_io import _fingerprint


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                              edges=state.edges, flips=state.flips)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for symbolic preparation")
class SymbolicHumanMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([0] * 27)
        cls.methods = {}
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no full enumeration")):
            for strategy in ("fully_solve_each_block", "placement_then_orientation"):
                cls.methods[strategy] = c.synthesize_human_method(
                    cls.shape, strategy=strategy, backend="symbolic", timeout=90)

    def test_classic_cube_has_small_complete_case_tables(self):
        for strategy, stages, cases, largest in (("fully_solve_each_block", 18, 257, 24),
                                               ("placement_then_orientation", 35, 153, 12)):
            method = self.methods[strategy]
            self.assertEqual(method.group_order, 43_252_003_274_489_856_000)
            self.assertEqual(method.backend, "symbolic")
            self.assertEqual(method.coverage, "certified")
            self.assertEqual(method.terminal_order, 1)
            self.assertEqual(len(method.stages), stages)
            self.assertEqual(sum(s.case_count for s in method.stages), cases)
            self.assertEqual(max(s.case_count for s in method.stages), largest)
            self.assertEqual(math.prod(s.index for s in method.stages), method.group_order)
            self.assertIn("symbolic", method.write_guide())

    def test_imported_scrambles_and_every_case_example_solve_offline(self):
        with patch("subprocess.run", side_effect=AssertionError("no GAP when applying a method")):
            for method in self.methods.values():
                sources = [imported(c.State(self.shape).apply(word)) for word in (
                    "", "B", "R U R' U'", "R U2 F' L D2 B R2 U' F2 D L2 B'")]
                sources.extend(method.example_state(stage.number, case.observation)
                               for stage in method.stages for case in stage.cases)
                for source in sources:
                    self.assertIsNone(source.scramble)
                    result = method.apply(source)
                    self.assertEqual(result.status, "solved")
                    self.assertTrue(result.state.is_solved)
                    self.assertEqual(source.apply(result.turn_sequence), result.state)

    def test_symbolic_artifact_loads_without_external_tools(self):
        for method in self.methods.values():
            record = method.to_dict()
            self.assertEqual(record["version"], 2)
            with patch("subprocess.run", side_effect=AssertionError("no GAP when loading")):
                loaded = c.HumanMethod.from_dict(record)
            self.assertEqual(loaded.to_dict(), record)
            source = imported(c.State(self.shape).apply("B R U2 F'"))
            self.assertTrue(loaded.apply(source).state.is_solved)

    def test_corrupt_stage_and_correction_rejected_with_valid_fingerprint(self):
        original = self.methods["fully_solve_each_block"].to_dict()
        broken = deepcopy(original)
        broken["stages"][0]["order_after"] = "1"
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaises(ValueError):
            c.HumanMethod.from_dict(broken)
        broken = deepcopy(original)
        cases = [case for case in broken["stages"][0]["cases"] if case["algorithm_id"]]
        cases[0]["algorithm_id"] = cases[1]["algorithm_id"]
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaises(ValueError):
            c.HumanMethod.from_dict(broken)

        broken = deepcopy(original)
        broken["gap_version"] = "0.0.0"
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaises(ValueError):
            c.HumanMethod.from_dict(broken)

    def test_cost_scope_is_exact_additive_before_boundary_cancellation(self):
        method = self.methods["fully_solve_each_block"]
        costs = method.additive_costs()
        self.assertTrue(costs["exact"])
        self.assertIn("before_boundary_cancellation", costs["scope"])
        algorithms = {a.id: a for a in method.algorithms}
        expected = sum((Fraction(sum(algorithms[c.algorithm_id].htm_length
                                    for c in s.cases if c.algorithm_id), s.case_count)
                        for s in method.stages), Fraction())
        self.assertEqual(Fraction(costs["htm"]["mean_numerator"], costs["htm"]["mean_denominator"]),
                         expected)

    def test_small_fixture_matches_explicit_chain_and_solves_every_element(self):
        shape = c.fixture("Shark Fin Soup")
        explicit = c.plan_human_stages(shape, timeout=30)
        method = c.synthesize_human_method(shape, backend="symbolic", timeout=60)
        self.assertEqual([(s.feature, s.order_before, s.order_after, s.observations)
                          for s in method.stages],
                         [(s.feature, s.order_before, s.order_after, s.observations)
                          for s in explicit.stages])
        for permutation in explicit.group.permutations:
            word = explicit.group.witness(permutation).expanded_moves(explicit.group.generators)
            self.assertTrue(method.apply(imported(c.State(shape).apply(word))).state.is_solved)

    def test_singleton_rich_bandage_has_complete_large_group_method(self):
        labels = [0] * 27
        labels[c.UFR] = labels[c.UR] = 1
        shape = c.Shape(labels)
        method = c.synthesize_human_method(shape, backend="symbolic",
                                           strategy="fully_solve_each_block", timeout=90)
        self.assertEqual(method.group_order, 75_090_283_462_656_000)
        self.assertEqual(method.terminal_order, 1)
        self.assertEqual(math.prod(stage.index for stage in method.stages), method.group_order)
        for generator in method.generators[:8]:
            self.assertTrue(method.apply(imported(c.State(shape).apply(generator.turn_sequence))).state.is_solved)

    def test_symbolic_backend_rejects_enumeration_budget(self):
        with self.assertRaisesRegex(ValueError, "only applies"):
            c.synthesize_human_method(self.shape, backend="symbolic", max_group_elements=100)


if __name__ == "__main__":
    unittest.main()
