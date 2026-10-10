"""Shared recipes preserve certified whole-fiber policies without GAP or closure."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_method_io import _fingerprint
from bce_v2.symbolic_repertoire_core import build_symbolic_repertoire, validate_symbolic_repertoire


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                              edges=state.edges, flips=state.flips)


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare certified test methods")
class SymbolicHumanRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.fixture("Shark Fin Soup")
        cls.explicit = c.plan_human_stages(cls.shape, timeout=30)
        cls.method = c.synthesize_human_method(cls.shape, backend="symbolic", timeout=45)
        cls.cyclic_method = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
                                                      backend="symbolic", timeout=30)
        with patch("subprocess.run", side_effect=AssertionError("supplied symbolic policies are offline")), \
                patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no reference-group closure")), \
                patch("bce_v2.human_repertoire._stage_groups", side_effect=AssertionError("no explicit fibers")):
            cls.repertoire = c.template_human_repertoire(
                cls.method, allow_symmetry=False, select_chain=False, max_trials=2,
                max_word_candidates=256, max_word_frontier=64, max_applications=4)
            cls.cyclic = c.template_human_repertoire(
                cls.cyclic_method, allow_symmetry=False, select_chain=False, max_trials=2,
                max_word_candidates=128, max_word_frontier=32, max_applications=4)

    def test_every_small_group_state_solves_by_the_same_physical_policy_offline(self):
        with patch("subprocess.run", side_effect=AssertionError("application and loading are offline")):
            loaded = c.HumanRepertoire.from_dict(self.repertoire.to_dict())
            for permutation in self.explicit.group.permutations:
                word = self.explicit.group.witness(permutation).expanded_moves(self.explicit.group.generators)
                source = imported(c.State(self.shape).apply(word))
                self.assertIsNone(source.scramble)
                expected = self.method.apply(source)
                for repertoire in (self.repertoire, loaded):
                    solved = repertoire.apply(source)
                    self.assertEqual(solved.status, "solved")
                    self.assertTrue(solved.state.is_solved)
                    self.assertEqual(source.apply(solved.turn_sequence), solved.state)
                    self.assertEqual(solved.turn_sequence, expected.turn_sequence)

    def test_shared_projection_retains_every_exact_case_correction(self):
        source_algorithms = {algorithm.id: algorithm for algorithm in self.method.algorithms}
        projected = {algorithm.id: algorithm for algorithm in self.repertoire.method.algorithms}
        macros = {macro.id: macro for macro in self.repertoire.macros}
        for original, selected, policy in zip(self.method.stages, self.repertoire.method.stages,
                                              self.repertoire.stages):
            self.assertEqual(original.observations, selected.observations)
            for before, after, case in zip(original.cases, selected.cases, policy.cases):
                if before.algorithm_id is None:
                    self.assertIsNone(after.algorithm_id)
                    continue
                expected, actual = source_algorithms[before.algorithm_id], projected[after.algorithm_id]
                self.assertEqual(actual.turn_sequence, expected.turn_sequence)
                self.assertEqual(actual.permutation, expected.permutation)
                self.assertEqual(case.recipe.loop_expression(macros).evaluate(self.method.generators),
                                 expected.permutation)
        self.assertEqual(self.repertoire.method.additive_costs(), self.method.additive_costs())

    def test_symbolic_wrapper_and_shared_dictionaries_roundtrip_offline(self):
        for repertoire in (self.repertoire, self.cyclic):
            record = repertoire.to_dict()
            self.assertEqual(record["version"], 2)
            self.assertEqual(record["backend"], "symbolic")
            self.assertIn("before_boundary_cancellation", record["cost_scope"])
            self.assertEqual(record["method"]["version"], 2)
            with tempfile.TemporaryDirectory() as directory, \
                    patch("subprocess.run", side_effect=AssertionError("portable reload is offline")):
                path = Path(directory) / "repertoire.json"
                repertoire.save(path)
                loaded = c.load_human_repertoire(path)
                self.assertEqual(loaded.to_dict(), record)
                self.assertIn("Stage 1", loaded.write_guide())
                for stage in loaded.method.stages:
                    for case in stage.cases:
                        source = loaded.method.example_state(stage.number, case.observation)
                        self.assertTrue(loaded.apply(source).state.is_solved)

    def test_rehashed_rule_progress_and_macro_corruption_are_rejected(self):
        original = self.repertoire.to_dict()
        mutations = []
        broken = deepcopy(original)
        broken["cost_scope"] = "sampled_or_enumerated_states"
        mutations.append(broken)
        broken = deepcopy(original)
        nontrivial = next(case for stage in broken["stages"] for case in stage["cases"] if case["instruction"])
        nontrivial["rank"] = 0
        mutations.append(broken)
        broken = deepcopy(original)
        stage = next(stage for stage in broken["stages"] if len(stage["rules"]) > 0)
        stage["rules"] = []
        mutations.append(broken)
        broken = deepcopy(original)
        nontrivial = next(case for stage in broken["stages"] for case in stage["cases"] if case["instruction"])
        nontrivial["instruction"] = {"kind": "sequence", "children": []}
        mutations.append(broken)
        broken = deepcopy(original)
        macro = broken["macros"][0]
        macro["expression"] = {"kind": "power", "children": [macro["expression"]], "exponent": 2}
        mutations.append(broken)
        broken = deepcopy(original)
        broken["metadata"]["selected_metrics"]["mean_htm"] += 1
        mutations.append(broken)
        with patch("subprocess.run", side_effect=AssertionError("tampering checks are offline")):
            for index, broken in enumerate(mutations):
                broken["fingerprint"] = _fingerprint(broken)
                with self.subTest(mutation=index), self.assertRaises(ValueError):
                    c.HumanRepertoire.from_dict(broken)

    def test_core_rejects_missing_cases_and_noninteger_ranks(self):
        stage = self.repertoire.stages[0]
        shortened = replace(self.repertoire, stages=(replace(stage, cases=stage.cases[:-1]),
                                                     *self.repertoire.stages[1:]))
        with self.assertRaisesRegex(ValueError, "cases"):
            validate_symbolic_repertoire(shortened)
        case = next(case for case in stage.cases if case.instruction is not None)
        forged = replace(case, rank=True)
        stages = (replace(stage, cases=tuple(forged if item == case else item for item in stage.cases)),
                  *self.repertoire.stages[1:])
        with self.assertRaisesRegex(ValueError, "rank"):
            validate_symbolic_repertoire(replace(self.repertoire, stages=stages))

    def test_nonportable_master_names_are_rejected_before_projection(self):
        recipes = tuple(tuple(case.recipe for case in stage.cases) for stage in self.repertoire.stages)
        for identifier in ("B", "M0", "M01", "custom"):
            macro = self.repertoire.macros[0]
            forged = replace(macro, id=identifier, algorithm=replace(macro.algorithm, id=identifier))
            definitions = (forged, *self.repertoire.macros[1:])
            with self.subTest(identifier=identifier), self.assertRaisesRegex(ValueError, "macro ID"):
                build_symbolic_repertoire(self.method, definitions, recipes)


if __name__ == "__main__":
    unittest.main()
