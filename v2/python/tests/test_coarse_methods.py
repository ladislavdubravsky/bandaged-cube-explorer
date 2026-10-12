"""Strict supplied-palette policies over independently certified start domains."""

from copy import deepcopy
from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette
from bce_v2.coarse_methods import CoarseMethod, compile_coarse_method
from bce_v2.human_method_io import _fingerprint
from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression


BODIES = {
    "EO": "F R U R' U' F'",
    "Sune": "R U R' U R U2 R'",
    "Tperm": "R U R' U' R' F R2 U' R' U' R U R' F'",
    "Ua": "R U' R U R U R U' R' U' R2",
}


def last_layer_inputs():
    analysis = c.analyze_isotropy(c.Shape(), timeout=90)
    builder = AlgorithmLibrary(analysis.loops, (), (), ())
    by_face = {generator.turn_sequence: generator for generator in analysis.loops.generators}

    def algorithm(identifier, word):
        proof = LoopExpression.sequence(*(LoopExpression.power(
            LoopExpression.loop(by_face[token[0]].id),
            2 if token.endswith("2") else -1 if token.endswith("'") else 1)
            for token in word.split()))
        return replace(builder.build_algorithm(LoopExpression.turns(word, proof)), id=identifier)

    adjustments = tuple(algorithm(word, word) for word in ("U", "U2", "U'"))
    palette = AlgorithmPalette.from_algorithms(
        tuple(algorithm(identifier, word) for identifier, word in BODIES.items()),
        setups=adjustments, adjustments=adjustments, allow_inverse=False)
    edges, corners = (c.UR, c.UF, c.UL, c.UB), (c.UFR, c.UFL, c.UBL, c.UBR)
    domain = tuple(cell for block in analysis.block_inventory.blocks
                   if block.orientation_order > 1 and not set(block.cells).intersection((*edges, *corners))
                   for cell in block.cells)
    features = (c.BlockFeature("orient_slots", edges), c.BlockFeature("orient_slots", corners),
                c.BlockFeature("place_blocks", corners), c.BlockFeature("place_blocks", edges))
    return analysis, palette, features, (c.BlockFeature("solve_blocks", domain),)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for symbolic preparation")
class CoarseMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis, cls.palette, cls.features, cls.domain = last_layer_inputs()
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no full enumeration")):
            cls.method = compile_coarse_method(cls.analysis, features=cls.features,
                                               palette=cls.palette, domain_features=cls.domain,
                                               timeout=90)

    def test_exact_domain_and_complete_four_stage_ladder(self):
        method = self.method
        self.assertEqual(method.group_order, 62_208)
        self.assertEqual(method.ambient_group_order, 43_252_003_274_489_856_000)
        self.assertEqual([stage.case_count for stage in method.stages], [8, 27, 24, 12])
        self.assertEqual([stage.feature for stage in method.stages], list(self.features))
        self.assertEqual([stage.number for stage in method.stages], [1, 2, 3, 4])
        self.assertEqual(method.taught_body_ids, tuple(sorted(BODIES)))
        self.assertEqual(method.coverage, "certified")
        self.assertIn("domain_features", method.coverage_scope)

    def test_every_case_example_solves_without_history_or_external_tools(self):
        with patch("subprocess.run", side_effect=AssertionError("offline execution")):
            for stage in self.method.stages:
                for case in stage.cases:
                    state = self.method.example_state(stage.number, case.observation)
                    self.assertIsNone(state.scramble)
                    result = self.method.apply(state)
                    self.assertEqual(result.status, "solved")
                    self.assertTrue(result.state.is_solved)
                    self.assertEqual(state.apply(result.turn_sequence), result.state)
                    self.assertTrue(all(1 <= step.stage_number <= 4 for step in result.steps))

    def test_unrestored_domain_is_rejected_before_any_entry_correction(self):
        state = c.State().apply("R")
        self.assertEqual(self.method.recognize(state).status, "outside_domain")
        result = self.method.apply(state)
        self.assertEqual(result.status, "outside_domain")
        self.assertEqual(result.steps, ())
        self.assertEqual(result.state, state)

    def test_palette_failure_does_not_fall_back_to_computational_transversals(self):
        missing = AlgorithmPalette(self.palette.bodies[:-1], self.palette.setups,
                                    self.palette.adjustments)
        with patch("bce_v2.coarse_methods._entry_correction",
                   side_effect=AssertionError("baseline expansion must follow strict coverage check")):
            with self.assertRaisesRegex(ValueError, "supplied palette does not cover"):
                compile_coarse_method(self.analysis, features=self.features, palette=missing,
                                      domain_features=self.domain, timeout=90)

    def test_portable_artifact_loads_offline_and_rejects_tampering(self):
        record = self.method.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("offline loading")):
            loaded = CoarseMethod.from_dict(record)
        self.assertEqual(loaded.to_dict(), record)
        state = c.State().apply(" ".join(BODIES.values()))
        self.assertTrue(loaded.apply(state).state.is_solved)
        broken = deepcopy(record)
        nonempty = next(row for row in broken["case_recipes"] if row["recipe"])
        nonempty["recipe"] = []
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaisesRegex(ValueError, "differs from its declared palette recipe"):
            CoarseMethod.from_dict(broken)
        broken = deepcopy(record)
        broken["prefix_stage_count"] -= 1
        broken["fingerprint"] = _fingerprint(broken)
        with self.assertRaises(ValueError):
            CoarseMethod.from_dict(broken)

    def test_costs_exclude_entry_scaffolding_and_taught_body_count_excludes_setups(self):
        costs = self.method.additive_costs()
        self.assertTrue(costs["exact"])
        self.assertLess(costs["htm"]["mean"], 70)
        self.assertEqual(len(self.method.taught_body_ids), 4)
        self.assertLess(len(self.method.algorithms), len(self.method.ambient_method.algorithms))

    def test_same_compiler_covers_a_bandaged_fixture_with_an_unrestricted_domain(self):
        shape = c.Shape([1] * 9 + [2] * 18)
        analysis = c.analyze_isotropy(shape, timeout=30)
        builder = AlgorithmLibrary(analysis.loops, (), (), ())
        bodies = tuple(replace(builder.build_algorithm(LoopExpression.loop(g.id)),
                               id=f"native-{g.id}") for g in analysis.loops.generators)
        palette = AlgorithmPalette.from_algorithms(bodies)
        method = compile_coarse_method(analysis, palette=palette,
                    features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        self.assertEqual(method.prefix_stage_count, 0)
        self.assertEqual(method.group_order, analysis.group_order)
        for stage in method.stages:
            for case in stage.cases:
                state = method.example_state(stage.number, case.observation)
                self.assertTrue(method.apply(state).state.is_solved)


if __name__ == "__main__":
    unittest.main()
