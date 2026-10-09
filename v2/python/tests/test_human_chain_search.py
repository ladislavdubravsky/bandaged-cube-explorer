"""Algorithm-aware chain choices remain complete, witnessed, and bounded."""

import json
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c


IDENTITY = tuple(range(48))
ZERO_DISCOVERY = {"max_candidates": 0, "max_states": 0}
SMALL_DISCOVERY = {"mode": "original", "max_candidates": 48, "max_states": 0}
PARETO = ("mean_htm", "worst_htm", "max_case_count", "case_count_sum",
          "original_leaf_count", "original_leaf_htm", "definition_htm", "stage_count")
PREFERENCES = {
    "execution": ("mean_htm", "worst_htm", "max_case_count", "case_count_sum",
                  "original_leaf_count", "original_leaf_htm", "definition_htm", "stage_count"),
    "recognition": ("max_case_count", "case_count_sum", "mean_htm", "worst_htm",
                    "original_leaf_count", "original_leaf_htm", "definition_htm", "stage_count"),
}


def then(first, second):
    return tuple(second[point] for point in first)


def observe(action, stage):
    return ((action.destinations[stage.block_index],) if stage.feature.kind == "place_block" else
            (action.destinations[stage.block_index], action.phases[stage.block_index]))


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                             edges=state.edges, flips=state.flips)


def physical_metrics(method, states):
    costs, additive = [], 0
    for state in states:
        application = method.apply(state)
        if application.status != "solved" or not application.state.is_solved:
            raise AssertionError("the selected chain does not solve its complete reference group")
        moves = application.turn_sequence.split()
        costs.append((len(moves), sum(2 if move.endswith("2") else 1 for move in moves)))
        additive += sum(step.htm_length for step in application.steps)
    return {"states": len(states), "mean_htm": sum(pair[0] for pair in costs) / len(states),
            "worst_htm": max(pair[0] for pair in costs),
            "mean_qtm": sum(pair[1] for pair in costs) / len(states),
            "worst_qtm": max(pair[1] for pair in costs), "additive_mean_htm": additive / len(states)}


def dominated(candidate, other):
    return (all(other.metrics[key] <= candidate.metrics[key] for key in PARETO) and
            any(other.metrics[key] < candidate.metrics[key] for key in PARETO))


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare exact reference groups")
class HumanChainSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alcatraz = c.plan_human_stages(c.fixture("Alcatraz"), max_group_elements=324, timeout=45)
        cls.fused = c.plan_human_stages(c.Shape([1] * 9 + [2] * 18), max_group_elements=4, timeout=45)
        cls.trivial = c.plan_human_stages(c.Shape([1] * 27), max_group_elements=1, timeout=45)
        cls.searches = {}
        with patch("subprocess.run", side_effect=AssertionError("prepared chain selection requires no GAP")):
            for preference in PREFERENCES:
                cls.searches[preference] = c.select_human_chain(
                    cls.alcatraz, preference=preference, beam_width=2, max_expansions=8,
                    max_methods=2, discovery_options=SMALL_DISCOVERY)
        initial = c.State(cls.alcatraz.inventory.root_shape)
        cls.states = tuple(imported(initial.apply(cls.alcatraz.group.witness(permutation).expanded_moves(
            cls.alcatraz.group.generators))) for permutation in cls.alcatraz.group.permutations)

    def test_both_known_alcatraz_baselines_are_complete_and_expose_recognition_tradeoff(self):
        for preference, search in self.searches.items():
            with self.subTest(preference=preference):
                self.assertEqual(search.status, "completed")
                by_source = {candidate.source: candidate for candidate in search.candidates}
                placement = by_source["baseline:placement_then_orientation"]
                full = by_source["baseline:fully_solve_each_block"]
                self.assertEqual(tuple(stage.case_count for stage in placement.method.stages),
                                 (2, 3, 3, 2, 3, 3))
                self.assertEqual(tuple(stage.case_count for stage in full.method.stages), (3, 2, 2, 9, 3))
                self.assertEqual((placement.metrics["stage_count"], placement.metrics["max_case_count"]),
                                 (6, 3))
                self.assertEqual((full.metrics["stage_count"], full.metrics["max_case_count"]), (5, 9))
                self.assertEqual(by_source["fallback:placement_then_orientation"].method.to_json(),
                                 search.baseline.to_json())
                self.assertEqual(tuple(stage.case_count for stage in
                                      by_source["fallback:fully_solve_each_block"].method.stages), (3, 2, 2, 9, 3))
                self.assertTrue(all(candidate.method.coverage == "certified" for candidate in search.candidates))
                self.assertTrue(all(candidate.method.terminal_order == 1 for candidate in search.candidates))
        self.assertLessEqual(self.searches["recognition"].method.stages[0].case_count, 3)
        self.assertLessEqual(max(stage.case_count for stage in self.searches["recognition"].method.stages), 3)

    def test_selected_and_portably_reloaded_policies_solve_all_324_imported_states_without_gap(self):
        search = self.searches["execution"]
        with patch("subprocess.run", side_effect=AssertionError("portable application requires no GAP")):
            loaded = c.HumanMethod.from_dict(search.method.to_dict())
            for label, method in (("selected", search.method), ("reloaded", loaded)):
                for index, source in enumerate(self.states):
                    with self.subTest(method=label, element=index):
                        self.assertIsNone(source.scramble)
                        application = method.apply(source)
                        self.assertEqual(application.status, "solved")
                        self.assertTrue(application.state.is_solved)
                        self.assertEqual(source.apply(application.turn_sequence), application.state)
                        current = source
                        for step in application.steps:
                            self.assertEqual(current, step.before)
                            self.assertEqual(current.apply(step.turn_sequence), step.after)
                            action = method.inventory.action(step.after)
                            for earlier in method.stages[:step.stage_number]:
                                self.assertEqual(observe(action, earlier), earlier.solved_observation)
                            current = step.after

    def test_every_candidate_correction_preserves_its_actual_prior_subgroup_and_entire_case(self):
        group = self.alcatraz.group
        permutations = frozenset(group.permutations)
        actions = {permutation: group.inventory.action(permutation) for permutation in permutations}
        initial = c.State(group.inventory.root_shape)
        for candidate in self.searches["execution"].candidates:
            method, current = candidate.method, permutations
            algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
            for stage in method.stages:
                target = frozenset(permutation for permutation in current
                                   if observe(actions[permutation], stage) == stage.solved_observation)
                self.assertEqual((len(current), len(target)), (stage.order_before, stage.order_after))
                for case in stage.cases:
                    fiber = frozenset(permutation for permutation in current
                                      if observe(actions[permutation], stage) == case.observation)
                    self.assertTrue(fiber)
                    if case.algorithm_id is None:
                        self.assertEqual(case.observation, stage.solved_observation)
                        self.assertEqual(fiber, target)
                        continue
                    algorithm = algorithms[case.algorithm_id]
                    with self.subTest(candidate=candidate.id, stage=stage.number, case=case.observation):
                        self.assertIn(algorithm.permutation, current)
                        self.assertEqual(frozenset(then(permutation, algorithm.permutation) for permutation in fiber),
                                         target)
                        replay = initial.apply(algorithm.turn_sequence)
                        self.assertEqual(replay.shape, initial.shape)
                        self.assertEqual(replay.sticker_permutation, algorithm.permutation)
                        self.assertEqual(algorithm.expression.evaluate(algorithm._generators), algorithm.permutation)
                        self.assertEqual(initial.apply(algorithm.expression.expanded_moves(
                            algorithm._generators, max_expanded_moves=100_000)), replay)
                current = target
            self.assertEqual(current, frozenset((IDENTITY,)))

    def test_selected_metrics_match_independent_physical_applications(self):
        with patch("subprocess.run", side_effect=AssertionError("measurement requires no GAP")):
            for preference, search in self.searches.items():
                selected = next(candidate for candidate in search.candidates if candidate.id == search.selected_id)
                for key, expected in physical_metrics(search.method, self.states).items():
                    with self.subTest(preference=preference, metric=key):
                        if key == "additive_mean_htm":
                            self.assertAlmostEqual(selected.metrics[key], expected, places=12)
                        else:
                            self.assertEqual(selected.metrics[key], expected)
                metrics, method = selected.metrics, selected.method
                self.assertEqual(metrics["stage_count"], len(method.stages))
                self.assertEqual(metrics["max_case_count"], max(stage.case_count for stage in method.stages))
                self.assertEqual(metrics["case_count_sum"], sum(stage.case_count for stage in method.stages))
                self.assertEqual(metrics["definition_htm"], sum(algorithm.htm_length for algorithm in method.algorithms))

    def test_frontier_and_selected_preferences_match_independent_complete_method_comparison(self):
        for preference, search in self.searches.items():
            expected_frontier = {candidate.id for candidate in search.candidates
                                 if not any(dominated(candidate, other) for other in search.candidates)}
            self.assertEqual(set(search.frontier), expected_frontier)
            selected = next(candidate for candidate in search.candidates if candidate.id == search.selected_id)
            self.assertIn(selected.id, search.frontier)
            keys = PREFERENCES[preference]
            self.assertEqual(tuple(selected.metrics[key] for key in keys),
                             min(tuple(candidate.metrics[key] for key in keys) for candidate in search.candidates))
            self.assertEqual(search.method.to_json(), selected.method.to_json())
            self.assertFalse(search.metadata["exhaustive_chain_search"])

    def test_quality_caps_bound_shared_discovery_and_additional_complete_methods(self):
        search = self.searches["execution"]
        metadata = search.metadata
        self.assertLessEqual(metadata["nodes_expanded"], 8)
        self.assertLessEqual(metadata["additional_methods_evaluated"], 2)
        self.assertLessEqual(metadata["discovery"]["candidates_examined"], 48)
        self.assertEqual(metadata["discovery"]["states_expanded"], 0)
        self.assertEqual(metadata["coverage"], "certified")
        self.assertEqual(metadata["discovery"]["preparation_group_elements"], 324)
        self.assertGreaterEqual(metadata["stage_edges_evaluated"], 0)
        self.assertGreaterEqual(metadata["stage_cache_hits"], 0)

    def test_zero_chain_and_word_budgets_retain_complete_baselines(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared fallback requires no GAP")):
            search = c.select_human_chain(self.alcatraz, max_expansions=0, max_methods=0,
                                          discovery_options=ZERO_DISCOVERY)
        self.assertEqual({candidate.source for candidate in search.candidates},
                         {"baseline:placement_then_orientation", "baseline:fully_solve_each_block",
                          "fallback:placement_then_orientation", "fallback:fully_solve_each_block"})
        self.assertEqual(search.metadata["nodes_expanded"], 0)
        self.assertEqual(search.metadata["additional_methods_evaluated"], 0)
        self.assertEqual(search.metadata["discovery"]["candidates_examined"], 0)
        self.assertEqual(search.method.coverage, "certified")
        self.assertTrue(search.method.apply(self.states[-1]).state.is_solved)

    def test_supplied_manual_complete_chain_is_compared_even_when_chain_budget_is_zero(self):
        features = tuple(stage.feature for stage in self.alcatraz.stages)
        with patch("subprocess.run", side_effect=AssertionError("manual comparison requires no GAP")):
            search = c.select_human_chain(self.alcatraz, manual_features=features,
                                          max_expansions=0, max_methods=0, discovery_options=ZERO_DISCOVERY)
        manual = next(candidate for candidate in search.candidates if candidate.source == "manual")
        self.assertEqual(tuple(stage.feature for stage in manual.method.stages), features)
        self.assertEqual(manual.method.terminal_order, 1)
        self.assertEqual(manual.method.coverage, "certified")
        self.assertTrue(manual.method.apply(self.states[-1]).state.is_solved)

    def test_orientation_only_and_trivial_groups_finish_at_faithful_identity(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared small groups require no GAP")):
            orientation = c.select_human_chain(self.fused, max_expansions=4, max_methods=2,
                                               discovery_options=SMALL_DISCOVERY)
            trivial = c.select_human_chain(self.trivial, max_expansions=4, max_methods=2,
                                          discovery_options=ZERO_DISCOVERY)
        self.assertEqual((orientation.method.group_order, orientation.method.quotient_order,
                          orientation.method.kernel_order), (4, 1, 4))
        self.assertEqual(len(orientation.method.stages), 1)
        self.assertEqual(orientation.method.stages[0].feature.kind, "solve_block")
        self.assertEqual({phase for _, phase in orientation.method.stages[0].observations}, {0, 1, 2, 3})
        initial = c.State(self.fused.inventory.root_shape)
        for permutation in self.fused.group.permutations:
            state = imported(initial.apply(self.fused.group.witness(permutation).expanded_moves(
                self.fused.group.generators)))
            self.assertTrue(orientation.method.apply(state).state.is_solved)
        self.assertEqual(trivial.method.stages, ())
        self.assertEqual(trivial.method.algorithms, ())
        self.assertEqual(trivial.method.terminal_order, 1)
        self.assertTrue(trivial.method.apply(c.State(self.trivial.inventory.root_shape)).state.is_solved)
        chosen = next(candidate for candidate in trivial.candidates if candidate.id == trivial.selected_id)
        for key in ("mean_htm", "worst_htm", "max_case_count", "case_count_sum", "stage_count"):
            self.assertEqual(chosen.metrics[key], 0)

    def test_explicit_group_cap_produces_no_selected_or_partial_chain_claim(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared cap preflight requires no GAP")):
            search = c.select_human_chain(self.fused, max_group_elements=3)
        self.assertEqual(search.status, "limit_reached")
        self.assertEqual(search.candidates, ())
        self.assertEqual(search.frontier, ())
        self.assertIsNone(search.selected_id)
        self.assertEqual(search.method.to_json(), search.baseline.to_json())
        self.assertEqual(search.method.coverage, "partial")
        self.assertIsNone(search.method.terminal_order)

    def test_reports_are_deterministic_serializable_and_detached_from_mutable_inspection(self):
        options = dict(beam_width=2, max_expansions=4, max_methods=1, discovery_options=ZERO_DISCOVERY)
        with patch("subprocess.run", side_effect=AssertionError("prepared repeat requires no GAP")):
            first = c.select_human_chain(self.alcatraz, **options)
            second = c.select_human_chain(self.alcatraz, **options)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.to_dict(), json.loads(first.to_json()))
        detached = first.metadata
        detached["nodes_expanded"] = -1
        self.assertGreaterEqual(first.metadata["nodes_expanded"], 0)
        candidate = first.candidates[0]
        metrics = candidate.metrics
        metrics["mean_htm"] = -1
        self.assertGreaterEqual(candidate.metrics["mean_htm"], 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chains.json"
            first.save(path)
            self.assertEqual(path.read_text(), first.to_json())

    def test_invalid_options_fail_before_external_work_and_incomplete_manual_chains_are_rejected(self):
        invalid = (({"preference": "unknown"}, ValueError), ({"beam_width": 0}, ValueError),
                   ({"beam_width": True}, TypeError), ({"max_expansions": 1.0}, TypeError),
                   ({"max_methods": -1}, ValueError), ({"discovery_options": {"unknown": 1}}, (TypeError, ValueError)),
                   ({"discovery_options": {"max_candidates": True}}, TypeError))
        with patch("subprocess.run", side_effect=AssertionError("validation must not call GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    c.select_human_chain(self.alcatraz, **options)
            with self.assertRaises(ValueError):
                c.select_human_chain(self.fused, manual_features=(), max_expansions=0, max_methods=0,
                                     discovery_options=ZERO_DISCOVERY)
            cells = self.fused.stages[0].feature.cells
            with self.assertRaises(ValueError):
                c.select_human_chain(self.fused, manual_features=(c.BlockFeature("place_block", cells),),
                                     max_expansions=0, max_methods=0, discovery_options=ZERO_DISCOVERY)

    def test_reused_public_reference_records_are_validated_before_trusting_their_witnesses(self):
        group = self.fused.group
        forged = replace(group, parent_indices=(None, 1, *group.parent_indices[2:]))
        record = replace(self.fused, group=forged)
        with patch("subprocess.run", side_effect=AssertionError("prepared validation requires no GAP")):
            with self.assertRaises((ValueError, c.GapError)):
                c.select_human_chain(record, max_expansions=0, max_methods=0,
                                     discovery_options=ZERO_DISCOVERY)


if __name__ == "__main__":
    unittest.main()
