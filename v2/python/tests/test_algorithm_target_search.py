"""Algorithm-informed targets retain certified complete chain continuations."""

import shutil
from dataclasses import replace
import unittest
from unittest.mock import patch

import bce_v2 as c


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners,
                              twists=state.twists, edges=state.edges, flips=state.flips)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for complete target-chain preparation")
class AlgorithmTargetSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=45)
        cls.explicit = c.plan_human_stages(cls.analysis, max_group_elements=324, timeout=45)
        cls.dictionary = c.discover_symbolic_dictionary(
            cls.analysis, max_candidates=256, rounds=1, max_algorithms=128,
            max_setup_words=16, max_conjugates=128)
        cls.options = {"max_candidates":1000, "max_states":1000, "max_word_length":8}
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("search must use small observation orbits")):
            cls.search = c.select_human_chain(
                cls.analysis, backend="symbolic", dictionary=cls.dictionary,
                max_expansions=8, max_methods=2, beam_width=1,
                discovery_options=cls.options, timeout=45)
        cls.attribute_method = next(candidate.method for candidate in cls.search.candidates
                                    if candidate.source == "dictionary:attributes:1")

    def test_targets_are_evaluated_as_complete_methods_with_preserved_controls(self):
        sources = {candidate.source for candidate in self.search.candidates}
        for strategy in ("placement_then_orientation", "fully_solve_each_block"):
            self.assertIn("fallback:"+strategy, sources)
            self.assertIn("dictionary:"+strategy, sources)
        self.assertIn("dictionary:adaptive:1", sources)
        self.assertIn("dictionary:attributes:1", sources)
        metadata = self.search.metadata
        self.assertEqual(len(metadata["attribute_targets"]), 1)
        self.assertLessEqual(metadata["additional_methods_evaluated"], 2)
        self.assertLessEqual(metadata["nodes_expanded"], 8)
        target = metadata["attribute_targets"][0]["target"]
        self.assertTrue(target["complete"])
        self.assertEqual(target["covered_count"], target["case_count"])
        stages = [stage for stage in self.attribute_method.stages if stage.feature.kind == "orient_slots"]
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0].feature.to_dict(), target["feature"])
        self.assertEqual(self.attribute_method.terminal_order, 1)
        self.assertLessEqual(self.search.method.additive_costs()["htm"]["mean"],
                             self.search.baseline.additive_costs()["htm"]["mean"])

    def test_attribute_artifact_loads_offline_and_solves_every_imported_group_state(self):
        with patch("subprocess.run", side_effect=AssertionError("portable loading and solving must be offline")):
            method = c.HumanMethod.from_dict(self.attribute_method.to_dict())
            self.assertEqual(method.to_dict(), self.attribute_method.to_dict())
            for permutation in self.explicit.group.permutations:
                word = self.explicit.group.witness(permutation).expanded_moves(self.analysis.loops)
                source = imported(c.State(self.analysis.block_inventory.root_shape).apply(word))
                self.assertIsNone(source.scramble)
                result = method.apply(source)
                self.assertEqual(result.status, "solved")
                self.assertTrue(result.state.is_solved)
                self.assertEqual(source.apply(result.turn_sequence), result.state)

    def test_zero_search_budget_keeps_complete_controls_without_attribute_discovery(self):
        with patch("bce_v2.symbolic_chain_search._discover_algorithm_targets",
                   side_effect=AssertionError("zero node budget must skip target discovery")):
            search = c.select_human_chain(
                self.analysis, backend="symbolic", dictionary=self.dictionary,
                max_expansions=0, max_methods=0,
                discovery_options={"max_candidates":0, "max_states":0}, timeout=45)
        self.assertEqual(len(search.candidates), 4)
        self.assertEqual(search.method.terminal_order, 1)
        self.assertFalse(search.metadata["attribute_targets"])
        self.assertEqual(search.metadata["attribute_prefixes_evaluated"], 0)
        self.assertEqual(search.metadata["nodes_expanded"], 0)

    def test_disabled_targets_do_not_reserve_existing_adaptive_search_budget(self):
        with patch("bce_v2.symbolic_chain_search._discover_algorithm_targets",
                   side_effect=AssertionError("disabled targets must skip discovery")):
            search = c.select_human_chain(
                self.analysis, backend="symbolic", dictionary=self.dictionary,
                max_expansions=8, max_methods=2, beam_width=1,
                target_options={"max_prefixes":0}, discovery_options=self.options, timeout=45)
        self.assertEqual(search.metadata["effective_search_limits"]["adaptive_kind_count"], 2)
        self.assertEqual(search.metadata["effective_search_limits"]["attribute_method_count"], 0)
        self.assertFalse(search.metadata["attribute_targets"])
        self.assertEqual(len(search.metadata["adaptive_chains"]), 2)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for initial complete group preparation")
class ExplicitAlgorithmTargetSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = c.plan_human_stages(c.fixture("Alcatraz"), max_group_elements=324, timeout=45)
        cls.options = {"max_candidates":128, "max_states":1000, "max_word_length":3}
        with patch("subprocess.run", side_effect=AssertionError("prepared explicit target search must be offline")):
            cls.search = c.select_human_chain(
                cls.plan, max_expansions=8, max_methods=2, beam_width=2,
                discovery_options=cls.options)
        cls.attribute_candidate = next(candidate for candidate in cls.search.candidates
                                       if candidate.source in ("greedy", "beam") and
                                       any(stage.feature.kind == "orient_slots"
                                           for stage in candidate.method.stages))

    def test_explicit_greedy_uses_grouped_phase_goal_and_compares_complete_physical_cost(self):
        target = self.attribute_candidate
        self.assertEqual(target.method.terminal_order, 1)
        self.assertTrue(self.search.metadata["attribute_targets"])
        self.assertLessEqual(self.search.metadata["attribute_prefixes_evaluated"], 12)
        self.assertLessEqual(self.search.metadata["attribute_methods_evaluated"], 2)
        self.assertLessEqual(self.search.metadata["nodes_expanded"], 8)
        controls = [candidate for candidate in self.search.candidates if candidate.source.startswith("baseline:")]
        self.assertLess(target.metrics["mean_htm"], min(candidate.metrics["mean_htm"] for candidate in controls))

    def test_explicit_phase_method_portable_replay_covers_all_324_group_states(self):
        with patch("subprocess.run", side_effect=AssertionError("portable explicit phase method is offline")):
            method = c.HumanMethod.from_dict(self.attribute_candidate.method.to_dict())
            total = 0
            for permutation in self.plan.group.permutations:
                word = self.plan.group.witness(permutation).expanded_moves(self.plan.group.generators)
                source = imported(c.State(self.plan.inventory.root_shape).apply(word))
                result = method.apply(source)
                self.assertEqual(result.status, "solved")
                self.assertTrue(result.state.is_solved)
                self.assertEqual(source.apply(result.turn_sequence), result.state)
                total += len(result.turn_sequence.split())
            self.assertEqual(total / 324, self.attribute_candidate.metrics["mean_htm"])

    def test_disabling_explicit_phase_targets_retains_old_feature_search(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared explicit search is offline")), \
             patch("bce_v2.human_chain_search._discover_targets_from_actions",
                   side_effect=AssertionError("disabled targets must skip pattern discovery")):
            search = c.select_human_chain(
                self.plan, max_expansions=8, max_methods=2, beam_width=2,
                target_options={"max_methods":0}, discovery_options=self.options)
        self.assertFalse(search.metadata["attribute_targets"])
        self.assertEqual(search.metadata["attribute_prefixes_evaluated"], 0)
        self.assertEqual(search.metadata["attribute_methods_evaluated"], 0)
        self.assertTrue(all(stage.feature.kind != "orient_slots"
                            for candidate in search.candidates for stage in candidate.method.stages))


@unittest.skipUnless(shutil.which("gap"), "GAP is required for initial exact orientation preparation")
class RefinedTargetPaletteTests(unittest.TestCase):
    def test_target_recipe_survives_replacement_of_its_original_palette_id(self):
        from bce_v2.human_chains import _resolve_feature
        from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
        from bce_v2.symbolic_chain_search import _compile_dictionary_policy

        analysis = c.analyze_isotropy(c.Shape([1]*9 + [2]*18), timeout=30)
        inventory = analysis.block_inventory
        slot = next(block for block in inventory.blocks if block.orientation_order == 4)
        feature = c.BlockFeature("orient_slots", slot.cells)
        plan = c.plan_human_stages(analysis, strategy="manual", features=(feature,),
                                   backend="symbolic", timeout=30)
        index = _resolve_feature(inventory, feature)[0]
        generator = next(generator for generator in analysis.loops.generators
                         if inventory.action(generator.permutation).phases[index] % 2)
        library = AlgorithmLibrary(analysis.loops, (), (), ())
        algorithm = library.build_algorithm(LoopExpression.loop(generator.id))
        original = replace(algorithm, id="original-palette-id")
        replacement = replace(algorithm, id="refined-effect-id")
        target = c.discover_algorithm_targets(inventory, plan.group, (original,))[0]
        self.assertEqual(target.case_count, 4)
        self.assertTrue(target.complete)
        self.assertTrue(any(original.id in recipe for recipe in target.recipes if recipe))
        self.assertNotEqual(original.id, replacement.id)
        settings = {"max_htm_length":30, "max_expanded_moves":120,
                    "max_stage_generators":4, "mode":"original",
                    "max_states":0, "max_word_length":0}
        _, method, _ = _compile_dictionary_policy(
            plan, (replacement,), settings, target_policies=(target,),
            recipe_algorithms=(original,))
        for case in method.stages[0].cases:
            source = method.example_state(1, case.observation)
            result = method.apply(source)
            self.assertEqual(result.status, "solved")
            self.assertTrue(result.state.is_solved)
            self.assertEqual(source.apply(result.turn_sequence), result.state)

    def test_cheaper_refined_graph_repair_wins_over_the_original_target_recipe(self):
        from bce_v2.block_solver import _permutation_order
        from bce_v2.human_methods import _compile_plan
        from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
        from bce_v2.symbolic_chain_search import _compile_dictionary_policy

        analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=45)
        control = c.plan_human_stages(analysis, backend="symbolic", timeout=45)
        prefix = next(index for index, stage in enumerate(control.stages)
                      if stage.feature.kind == "solve_block")
        current = control.stages[prefix].group_before
        palette = c.discover_symbolic_dictionary(
            analysis, max_candidates=256, rounds=1, max_algorithms=128,
            max_setup_words=16, max_conjugates=128).algorithms
        library = AlgorithmLibrary(analysis.loops, (), (), ())
        identity = next(expression for generator in analysis.loops.generators
                        if (expression := LoopExpression.power(LoopExpression.loop(generator.id),
                                                               _permutation_order(generator.permutation)))
                        and library.build_algorithm(expression, max_expanded_moves=2400).htm_length >= 4)
        # A witnessed multi-face identity detour makes genuine longer physical
        # words for the same effects; shorter refinement preserves every action.
        original = tuple(replace(library.build_algorithm(
            LoopExpression.sequence(algorithm.expression, identity), max_expanded_moves=2400),
            id="original-"+algorithm.id) for algorithm in palette)
        refined = tuple(replace(algorithm, id="refined-"+algorithm.id) for algorithm in palette)
        target = next(target for target in c.discover_algorithm_targets(control.inventory, current, original)
                      if target.complete)
        features = (*(stage.feature for stage in control.stages[:prefix]), target.feature,
                    *(stage.feature for stage in control.stages[prefix:]))
        plan = c.plan_human_stages(analysis, strategy="manual", features=features,
                                   backend="symbolic", timeout=45)
        baseline = _compile_plan(plan)
        baseline = replace(baseline, algorithms=tuple(replace(library.build_algorithm(
            LoopExpression.sequence(algorithm.expression, identity), max_expanded_moves=2400),
            id=algorithm.id) for algorithm in baseline.algorithms))
        settings = {"max_htm_length":1000, "max_expanded_moves":2400,
                    "max_stage_generators":128, "mode":"structured",
                    "max_states":2000, "max_word_length":8}
        _, method, _ = _compile_dictionary_policy(
            plan, refined, settings, baseline=baseline, target_policies=(target,),
            recipe_algorithms=original)
        stage = next(stage for stage in method.stages if stage.feature == target.feature)
        algorithms = {algorithm.id:algorithm for algorithm in method.algorithms}
        palette_by_id = {algorithm.id:algorithm for algorithm in original}
        old_costs, costs = [], []
        for case, recipe in zip(stage.cases, target.recipes):
            if case.algorithm_id is None:
                continue
            old = library.build_algorithm(LoopExpression.sequence(
                *(palette_by_id[identifier].expression for identifier in recipe)),
                max_expanded_moves=2400)
            old_costs.append(old.htm_length)
            costs.append(algorithms[case.algorithm_id].htm_length)
            source = method.example_state(stage.number, case.observation)
            result = method.apply(source)
            self.assertTrue(result.state.is_solved)
            self.assertEqual(source.apply(result.turn_sequence), result.state)
        self.assertLess(sum(costs), sum(old_costs))


if __name__ == "__main__":
    unittest.main()
