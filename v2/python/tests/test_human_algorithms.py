"""Bounded stage-aware algorithm search preserves complete reusable policies."""

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c


IDENTITY = tuple(range(48))
REFERENCES = (("Alcatraz", 324), ("Bicube Fuse", 60), ("Shark Fin Soup", 36))


def then(first, second):
    return tuple(second[point] for point in first)


def imported(state):
    return c.State.from_cubies(
        state.specification, corners=state.corners, twists=state.twists,
        edges=state.edges, flips=state.flips)


def observe(action, stage):
    return ((action.destinations[stage.block_index],) if stage.feature.kind == "place_block" else
            (action.destinations[stage.block_index], action.phases[stage.block_index]))


def case_algorithms(method):
    algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
    return {(stage.number, case.observation): (
                IDENTITY, "") if case.algorithm_id is None else (
                    algorithms[case.algorithm_id].permutation,
                    algorithms[case.algorithm_id].turn_sequence)
            for stage in method.stages for case in stage.cases}


def measured(method, states):
    costs = []
    for state in states:
        application = method.apply(state)
        if application.status != "solved" or not application.state.is_solved:
            raise AssertionError("compiled method failed its complete input set")
        word = application.turn_sequence.split()
        costs.append((len(word), sum(2 if move.endswith("2") else 1 for move in word)))
    return {
        "mean_htm": sum(cost[0] for cost in costs) / len(costs),
        "worst_htm": max(cost[0] for cost in costs),
        "mean_qtm": sum(cost[1] for cost in costs) / len(costs),
        "worst_qtm": max(cost[1] for cost in costs),
    }


@unittest.skipUnless(shutil.which("gap"), "GAP is required to compile the reference policies")
class HumanAlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.plans, cls.baselines, cls.searches, cls.loaded, cls.states = {}, {}, {}, {}, {}
        for name, order in REFERENCES:
            plan = c.plan_human_stages(c.fixture(name), max_group_elements=order, timeout=45)
            baseline = c.synthesize_human_method(plan, max_group_elements=order)
            cls.plans[name], cls.baselines[name] = plan, baseline
            with patch("subprocess.run", side_effect=AssertionError("algorithm discovery requires no GAP")):
                search = c.improve_human_method(baseline)
                path = Path(cls.directory.name) / (name.replace(" ", "-") + ".json")
                search.method.save(path)
                cls.loaded[name] = c.load_human_method(path)
            cls.searches[name] = search
            initial = c.State(plan.inventory.root_shape)
            cls.states[name] = tuple(imported(initial.apply(
                plan.group.witness(permutation).expanded_moves(plan.group.generators)))
                for permutation in plan.group.permutations)

    def test_all_420_imported_states_solve_with_improved_and_reloaded_methods_without_gap(self):
        with patch("subprocess.run", side_effect=AssertionError("policy application requires no GAP")):
            for name, order in REFERENCES:
                self.assertEqual(len(self.states[name]), order)
                search = self.searches[name]
                self.assertEqual(search.baseline.to_json(), self.baselines[name].to_json())
                for origin, method in (("improved", search.method), ("reloaded", self.loaded[name])):
                    self.assertEqual(method.coverage, "certified")
                    self.assertEqual(method.group_order, order)
                    for index, source in enumerate(self.states[name]):
                        with self.subTest(puzzle=name, origin=origin, element=index):
                            self.assertIsNone(source.scramble)
                            application = method.apply(source)
                            self.assertEqual(application.status, "solved")
                            self.assertTrue(application.state.is_solved)
                            self.assertEqual(source.apply(application.turn_sequence), application.state)
                            current, previous = source, 0
                            for step in application.steps:
                                self.assertGreater(step.stage_number, previous)
                                self.assertEqual(step.before, current)
                                self.assertEqual(current.apply(step.turn_sequence), step.after)
                                action = method.inventory.action(step.after)
                                for stage in method.stages[:step.stage_number]:
                                    self.assertEqual(observe(action, stage), stage.solved_observation)
                                current, previous = step.after, step.stage_number

    def test_every_retained_alternative_corrects_its_entire_fiber_and_has_a_legal_witness(self):
        for name, _ in REFERENCES:
            plan, search = self.plans[name], self.searches[name]
            group = plan.group
            initial = c.State(plan.inventory.root_shape)
            self.assertTrue(search.alternatives)
            for alternative in search.alternatives:
                stage = plan.stages[alternative.stage_number - 1]
                algorithm = alternative.algorithm
                with self.subTest(puzzle=name, stage=stage.number,
                                  observation=alternative.observation, source=alternative.source):
                    current = {group.permutations[index] for index in stage.members_before}
                    target = {group.permutations[index] for index in stage.members_after}
                    fiber = {group.permutations[index] for index in stage.members_before
                             if observe(group._summaries[index], stage) == alternative.observation}
                    self.assertTrue(fiber)
                    self.assertNotEqual(alternative.observation, stage.solved_observation)
                    self.assertIn(algorithm.permutation, current)
                    self.assertTrue(all(then(permutation, algorithm.permutation) in target
                                        for permutation in fiber))
                    physical = initial.apply(algorithm.turn_sequence)
                    self.assertEqual(physical.shape, initial.shape)
                    self.assertEqual(physical.sticker_permutation, algorithm.permutation)
                    self.assertEqual(algorithm.expression.evaluate(algorithm._generators),
                                     algorithm.permutation)
                    expression = initial.apply(algorithm.expression.expanded_moves(
                        algorithm._generators, max_expanded_moves=100_000))
                    self.assertEqual(expression, physical)

    def test_shark_default_search_materially_improves_whole_policy_lengths(self):
        name = "Shark Fin Soup"
        with patch("subprocess.run", side_effect=AssertionError("measurement requires no GAP")):
            baseline = measured(self.baselines[name], self.states[name])
            improved = measured(self.searches[name].method, self.states[name])
        for metric in ("mean_htm", "worst_htm", "mean_qtm", "worst_qtm"):
            self.assertLess(improved[metric], 0.8 * baseline[metric], metric)

    def test_repeated_search_preserves_admitted_native_actions_without_gap(self):
        first = self.searches["Shark Fin Soup"]
        self.assertGreater(first.metadata["seed_action_count"], 0)
        with patch("subprocess.run", side_effect=AssertionError("repeated discovery requires no GAP")):
            second = c.improve_human_method(first.method)
        self.assertEqual(second.metadata["seed_action_count"], first.metadata["seed_action_count"])
        self.assertEqual(second.baseline.to_json(), first.method.to_json())
        self.assertEqual(second.metadata["baseline_metrics"], first.metadata["improved_metrics"])
        self.assertEqual(second.method.coverage, "certified")
        self.assertLessEqual(second.metadata["improved_metrics"]["total_htm"],
                             second.metadata["baseline_metrics"]["total_htm"])
        self.assertLessEqual(second.metadata["improved_metrics"]["worst_htm"],
                             second.metadata["baseline_metrics"]["worst_htm"])

    def test_zero_candidate_or_expansion_budget_preserves_every_baseline_case(self):
        baseline = self.baselines["Shark Fin Soup"]
        expected = case_algorithms(baseline)
        with patch("subprocess.run", side_effect=AssertionError("fallback requires no GAP")):
            for mode in ("original", "shallow", "structured"):
                for limit in ({"max_candidates": 0}, {"max_expanded_moves": 0}):
                    with self.subTest(mode=mode, limit=limit):
                        search = c.improve_human_method(baseline, mode=mode, **limit)
                        self.assertEqual(search.baseline.to_json(), baseline.to_json())
                        self.assertEqual(case_algorithms(search.method), expected)
                        self.assertEqual(search.method.coverage, "certified")
                        self.assertTrue(search.metadata["fallback_policy_retained"])
                        self.assertEqual(sum(stage["fallback_cases"] for stage in search.metadata["stages"]),
                                         sum(stage.case_count - 1 for stage in baseline.stages))

    def test_optional_expansion_bound_smaller_than_the_baseline_does_not_truncate_it(self):
        baseline = self.baselines["Alcatraz"]
        self.assertGreater(max(algorithm.htm_length for algorithm in baseline.algorithms), 1)
        with patch("subprocess.run", side_effect=AssertionError("fallback requires no GAP")):
            search = c.improve_human_method(baseline, max_expanded_moves=1)
            self.assertEqual(case_algorithms(search.method), case_algorithms(baseline))
            self.assertEqual(search.method.coverage, "certified")
            source = self.states["Alcatraz"][-1]
            self.assertTrue(search.method.apply(source).state.is_solved)

    def test_report_is_deterministic_and_roundtrips_as_json(self):
        baseline = self.baselines["Shark Fin Soup"]
        options = dict(mode="shallow", max_candidates=64, max_word_length=2,
                       max_states=100, max_stage_generators=8)
        with patch("subprocess.run", side_effect=AssertionError("reporting requires no GAP")):
            first = c.improve_human_method(baseline, **options)
            second = c.improve_human_method(baseline, **options)
        self.assertEqual(first.to_dict(), json.loads(first.to_json()))
        self.assertEqual(first.to_json(), second.to_json())
        path = Path(self.directory.name) / "algorithm-search.json"
        first.save(path)
        self.assertEqual(path.read_text(), first.to_json())

    def test_reported_whole_method_metrics_match_independent_physical_application(self):
        with patch("subprocess.run", side_effect=AssertionError("measurement requires no GAP")):
            for name, order in REFERENCES:
                search = self.searches[name]
                for label, method in (("baseline", search.baseline), ("improved", search.method)):
                    reported = search.metadata[label + "_metrics"]
                    actual = measured(method, self.states[name])
                    with self.subTest(puzzle=name, method=label):
                        self.assertEqual(reported["states"], order)
                        for key, value in actual.items():
                            self.assertEqual(reported[key], value)
                        self.assertEqual(reported["algorithm_count"], len(method.algorithms))
                        self.assertEqual(reported["definition_htm"],
                                         sum(algorithm.htm_length for algorithm in method.algorithms))
                        self.assertEqual(reported["definition_qtm"],
                                         sum(algorithm.qtm_length for algorithm in method.algorithms))
                self.assertFalse(search.metadata["exhaustive_word_search"])
                self.assertTrue(search.metadata["fallback_policy_retained"])
                self.assertEqual(search.metadata["coverage"], "certified")
                self.assertLessEqual(search.metadata["improved_metrics"]["total_htm"],
                                     search.metadata["baseline_metrics"]["total_htm"])
                self.assertLessEqual(search.metadata["improved_metrics"]["worst_htm"],
                                     search.metadata["baseline_metrics"]["worst_htm"])

    def test_proposal_and_state_caps_include_duplicate_attempts_and_fallbacks_remain_explicit(self):
        baseline = self.baselines["Alcatraz"]
        with patch("subprocess.run", side_effect=AssertionError("bounded search requires no GAP")):
            search = c.improve_human_method(baseline, max_candidates=7, max_states=3,
                                           max_stage_generators=2, max_alternatives=2)
        metadata = search.metadata
        self.assertEqual(metadata["candidates_examined"], 7)
        self.assertTrue(metadata["candidate_limit_reached"])
        self.assertLessEqual(metadata["candidates_built"], metadata["candidates_examined"])
        self.assertEqual(sum(metadata["attempted_by_source"].values()), metadata["candidates_examined"])
        self.assertLessEqual(metadata["states_expanded"], 3)
        self.assertTrue(metadata["fallback_policy_retained"])
        counts = Counter((alternative.stage_number, alternative.observation)
                         for alternative in search.alternatives)
        self.assertEqual(set(counts), {key for key, (action, _) in case_algorithms(baseline).items()
                                      if action != IDENTITY})
        self.assertTrue(all(count <= 2 for count in counts.values()))
        detached = search.metadata
        detached["candidates_examined"] = -1
        self.assertEqual(search.metadata["candidates_examined"], 7)

    def test_invalid_budget_types_and_values_fail_before_any_external_work(self):
        baseline = self.baselines["Shark Fin Soup"]
        invalid = (({"mode": "unknown"}, ValueError),
                   ({"max_candidates": True}, TypeError),
                   ({"max_states": 1.0}, TypeError),
                   ({"max_word_length": -1}, ValueError),
                   ({"max_expanded_moves": -1}, ValueError),
                   ({"max_alternatives": 0}, ValueError))
        with patch("subprocess.run", side_effect=AssertionError("validation requires no GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    c.improve_human_method(baseline, **options)
            with self.assertRaises(TypeError):
                c.improve_human_method(object())

    def test_nonzero_root_portable_method_keeps_existing_ids_and_legal_new_leaves(self):
        graph = c.explore(c.fixture("Bicube Fuse"))
        original = c.synthesize_human_method(graph, root=1, max_group_elements=60, timeout=45)
        with patch("subprocess.run", side_effect=AssertionError("portable search requires no GAP")):
            baseline = c.HumanMethod.from_dict(original.to_dict())
            search = c.improve_human_method(baseline, max_candidates=256)
            loaded = c.HumanMethod.from_dict(search.method.to_dict())
            self.assertEqual(loaded.root_vertex, 1)
            self.assertEqual(loaded.reference_shape, graph[1])
            merged = {generator.id: generator for generator in search.method.generators}
            self.assertEqual(len(merged), len(search.method.generators))
            for generator in baseline.generators:
                self.assertIn(generator.id, merged)
                self.assertEqual(merged[generator.id].permutation, generator.permutation)
                self.assertEqual(merged[generator.id].moves, generator.moves)
            initial = c.State(loaded.reference_shape)
            for generator in loaded.generators:
                physical = initial.apply(generator.moves)
                self.assertEqual(physical.shape, loaded.reference_shape)
                self.assertEqual(physical.sticker_permutation, generator.permutation)
            for stage in baseline.stages:
                for case in stage.cases:
                    source = imported(baseline.example_state(stage.number, case.observation))
                    self.assertTrue(loaded.apply(source).state.is_solved)

    def test_composite_protection_is_checked_at_the_whole_algorithm_boundary(self):
        plan = self.plans["Alcatraz"]
        baseline = self.baselines["Alcatraz"]
        algorithms = {algorithm.id: algorithm for algorithm in baseline.algorithms}
        found = False
        for stage in plan.stages:
            current = {plan.group.permutations[index] for index in stage.members_before}
            for case in baseline.stages[stage.number - 1].cases:
                if case.algorithm_id is None:
                    continue
                algorithm = algorithms[case.algorithm_id]
                steps = algorithm.expression.loop_steps()
                if any(c.LoopExpression.power(c.LoopExpression.loop(identifier), exponent).evaluate(
                        baseline.generators) not in current for identifier, exponent in steps):
                    self.assertIn(algorithm.permutation, current)
                    found = True
        self.assertTrue(found, "reference fixture must exercise a composite that restores prior features")
        self.assertGreater(self.searches["Alcatraz"].metadata["attempted_by_source"].get("schreier", 0), 0)


@unittest.skipUnless(shutil.which("gap"), "GAP is required to compile the small reference policy")
class HumanAlgorithmBudgetTests(unittest.TestCase):
    def test_duplicate_proposals_consume_the_candidate_cap(self):
        baseline = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
                                             max_group_elements=4, timeout=45)
        repeated = c.LoopExpression.power(c.LoopExpression.loop(baseline.generators[0].id), 2)
        # Force a duplicate independently of which equivalent seed expression
        # the heuristic prefers; discovery must charge both proposal attempts.
        with patch("subprocess.run", side_effect=AssertionError("bounded discovery requires no GAP")), patch(
                "bce_v2.human_algorithms._shallow_words", return_value=iter((repeated, repeated))):
            search = c.improve_human_method(baseline, mode="shallow", max_candidates=7,
                                           max_word_length=2, max_states=16)
        metadata = search.metadata
        self.assertGreater(metadata["duplicate_expressions"], 0)
        self.assertEqual(metadata["candidates_examined"], 7)
        self.assertTrue(metadata["candidate_limit_reached"])
        self.assertEqual(sum(metadata["attempted_by_source"].values()), 7)
        self.assertLess(metadata["candidates_built"], metadata["candidates_examined"])
