"""Small observation-orbit searches preserve symbolic coverage and budgets."""

from dataclasses import replace
import json
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_methods import _observe, _then
from bce_v2.symbolic_human_algorithms import _orbit_edges, _successor


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                              edges=state.edges, flips=state.flips)


class SymbolicOrbitEdgeTests(unittest.TestCase):
    def test_small_edge_budget_keeps_coverage_when_cheap_actions_fix_the_target(self):
        inventory = SimpleNamespace(action=lambda permutation: SimpleNamespace(
            destinations=permutation, phases=(0, 0, 0)))
        stage = SimpleNamespace(observations=((0,), (1,), (2,)), solved_observation=(0,))
        cheap_noop = SimpleNamespace(algorithm=SimpleNamespace(permutation=(0, 1, 2)), key=(1,))
        cheap_partial = SimpleNamespace(algorithm=SimpleNamespace(permutation=(1, 0, 2)), key=(2,))
        covering = SimpleNamespace(algorithm=SimpleNamespace(permutation=(1, 2, 0)), key=(16,))
        self.assertEqual(_orbit_edges((cheap_noop, cheap_partial, covering), stage, inventory, 1),
                         [covering])
        self.assertEqual(_orbit_edges((covering,), stage, inventory, 0), [])


@unittest.skipUnless(shutil.which("gap"), "GAP is required for symbolic preparation")
class SymbolicHumanAlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.fixture("Shark Fin Soup")
        cls.explicit = c.plan_human_stages(cls.shape, timeout=30)
        cls.baseline = c.synthesize_human_method(cls.shape, backend="symbolic", timeout=60)
        with patch("subprocess.run", side_effect=AssertionError("symbolic improvement must run offline")):
            cls.search = c.improve_human_method(cls.baseline, max_candidates=600, rounds=2,
                                                max_states=150, max_word_length=3)

    def test_improved_and_loaded_methods_solve_all_small_fixture_states_offline(self):
        with patch("subprocess.run", side_effect=AssertionError("no GAP during loading or execution")):
            loaded = c.HumanMethod.from_dict(self.search.method.to_dict())
            for permutation in self.explicit.group.permutations:
                expression = self.explicit.group.witness(permutation)
                word = expression.expanded_moves(self.explicit.group.generators)
                source = imported(c.State(self.shape).apply(word))
                for method in (self.search.method, loaded):
                    result = method.apply(source)
                    self.assertEqual(result.status, "solved")
                    self.assertEqual(source.apply(result.turn_sequence), result.state)
                    self.assertTrue(result.state.is_solved)

    def test_retained_alternatives_have_legal_stage_preserving_corrections(self):
        self.assertTrue(self.search.alternatives)
        for alternative in self.search.alternatives:
            certified = self.baseline._symbolic_chain.stages[alternative.stage_number - 1]
            stage = self.baseline.stages[alternative.stage_number - 1]
            representative = next(case.representative for case in stage.cases
                                  if case.observation == alternative.observation)
            algorithm = alternative.algorithm
            self.assertIn(algorithm.permutation, certified.group_before)
            self.assertIn(_then(representative, algorithm.permutation), certified.group_after)
            replay = c.State(self.shape).apply(algorithm.turn_sequence)
            self.assertEqual(replay.shape, self.shape)
            self.assertEqual(replay.sticker_permutation, algorithm.permutation)
            self.assertEqual(algorithm.expression.evaluate(self.baseline.generators), algorithm.permutation)

    def test_search_metrics_declare_additive_scope_and_limits(self):
        metadata = self.search.metadata
        self.assertEqual(metadata["preparation_group_elements"], 0)
        self.assertLessEqual(metadata["candidates_examined"], 600)
        self.assertLessEqual(metadata["states_expanded"], 150)
        self.assertTrue(metadata["fallback_policy_retained"])
        self.assertEqual(metadata["coverage"], "certified")
        for name in ("baseline_metrics", "improved_metrics"):
            metrics = metadata[name]
            self.assertTrue(metrics["exact"])
            self.assertFalse(metrics["boundary_cancellation_included"])
            self.assertIn("before_boundary_cancellation", metrics["scope"])
        self.assertEqual(metadata["improved_metrics"]["additive_costs"],
                         self.search.method.additive_costs())
        self.assertLessEqual(metadata["improved_metrics"]["total_htm"],
                             metadata["baseline_metrics"]["total_htm"])
        self.assertLessEqual(metadata["improved_metrics"]["worst_htm"],
                             metadata["baseline_metrics"]["worst_htm"])

    def test_zero_work_returns_the_unchanged_complete_policy(self):
        with patch("subprocess.run", side_effect=AssertionError("fallback must run offline")):
            for mode in ("original", "shallow", "structured"):
                for limits in ({"max_candidates": 0}, {"max_expanded_moves": 0},
                               {"max_seed_loops": 0}, {"max_htm_length": 0}):
                    with self.subTest(mode=mode, limits=limits):
                        search = c.improve_human_method(self.baseline, mode=mode, **limits)
                        self.assertEqual(search.method.to_dict(), self.baseline.to_dict())
                        self.assertEqual(search.method.coverage, "certified")
                        self.assertEqual(search.metadata["candidates_examined"], 0)

    def test_portable_witness_library_and_restrictive_budgets(self):
        with patch("subprocess.run", side_effect=AssertionError("loaded search must run offline")):
            loaded = c.HumanMethod.from_dict(self.baseline.to_dict())
            search = c.improve_human_method(loaded, max_candidates=32, max_states=4,
                                            max_word_length=2, max_htm_length=10)
        self.assertEqual(search.method.coverage, "certified")
        self.assertLessEqual(search.metadata["candidates_examined"], 32)
        self.assertLessEqual(search.metadata["states_expanded"], 4)
        self.assertEqual(search.method.generators, loaded.generators)

    def test_shared_dictionary_is_reused_offline_without_running_discovery(self):
        dictionary = c.discover_symbolic_dictionary(
            self.baseline._symbolic_chain.analysis, max_candidates=64, rounds=1,
            max_algorithms=64, max_setup_depth=1, max_setup_words=16, max_conjugates=32)
        with patch("subprocess.run", side_effect=AssertionError("shared dictionary is used offline")), patch(
                "bce_v2.symbolic_human_algorithms.discover_loop_algorithms",
                side_effect=AssertionError("shared dictionary must not be rediscovered")):
            search = c.improve_human_method(self.baseline, dictionary=dictionary,
                                            max_candidates=256, max_states=128,
                                            max_stage_generators=48, max_word_length=4)
            loaded = c.HumanMethod.from_dict(search.method.to_dict())
        self.assertEqual(search.metadata["dictionary_metadata"], dictionary.metadata)
        self.assertEqual(search.metadata["attempted_by_source"]["shared_dictionary"],
                         len(dictionary.algorithms))
        self.assertLessEqual(search.method.additive_costs()["htm"]["mean"],
                             self.baseline.additive_costs()["htm"]["mean"])
        for permutation in self.explicit.group.permutations:
            word = self.explicit.group.witness(permutation).expanded_moves(self.explicit.group.generators)
            source = imported(c.State(self.shape).apply(word))
            self.assertTrue(loaded.apply(source).state.is_solved)
        forged_metadata = dictionary.metadata
        forged_metadata["group_order"] *= 2
        forged_metadata["orientation_target_order"] *= 2
        forged_metadata["orientation_complete"] = (
            forged_metadata["orientation_span_order"] == forged_metadata["orientation_target_order"])
        forged = replace(dictionary, _metadata_json=json.dumps(forged_metadata))
        with self.assertRaisesRegex(ValueError, "certified reference group"):
            c.improve_human_method(self.baseline, dictionary=forged)

    def test_zero_depth_shallow_mode_uses_direct_candidates_without_orbit_expansion(self):
        with patch("subprocess.run", side_effect=AssertionError("shallow search must run offline")):
            search = c.improve_human_method(self.baseline, mode="shallow", rounds=0,
                                            max_word_length=0, max_candidates=32)
        self.assertEqual(search.method.coverage, "certified")
        self.assertEqual(search.metadata["states_expanded"], 0)
        self.assertLessEqual(search.metadata["candidates_examined"], 32)

    def test_observation_action_matches_full_physical_composition(self):
        algorithms = {a.id: a for a in self.baseline.algorithms}
        for stage in self.baseline.stages:
            algorithm = next(algorithms[case.algorithm_id] for case in stage.cases if case.algorithm_id)
            action = self.baseline.inventory.action(algorithm.permutation)
            for case in stage.cases:
                expected = _observe(self.baseline.inventory.action(
                    _then(case.representative, algorithm.permutation)), stage.block_index,
                    stage.feature.kind)
                self.assertEqual(_successor(case.observation, action, self.baseline.inventory), expected)


if __name__ == "__main__":
    unittest.main()
