"""Recognition may inspect extra pieces without committing to solve them."""

from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.human_method_io import _fingerprint
from bce_v2.human_methods import (_compile_plan, _goal_observation, _observe,
                                 _stage_observation, _state_for_permutation, _then)


@unittest.skipUnless(shutil.which("gap"), "GAP is required for preparation")
class IndependentRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.fixture("Alcatraz")
        cls.plan = c.plan_human_stages(cls.shape, timeout=45)
        cls.baseline = _compile_plan(cls.plan)
        first = cls.plan.stages[0]
        cls.extra = next(c.BlockFeature("solve_block", block.cells)
                         for index, block in enumerate(cls.plan.inventory.blocks)
                         if index != first.block_index and block.orientation_order > 1)
        # Put the goal second to check that recovery uses the actual projection.
        cls.spec = {1: (cls.extra, first.feature)}
        cls.method = _compile_plan(cls.plan, recognition=cls.spec)
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no enumeration")):
            cls.symbolic = c.synthesize_human_method(cls.shape, backend="symbolic",
                                                    recognition=cls.spec, timeout=60)

    def test_refinement_preserves_goal_chain_and_exact_costs(self):
        method, baseline = self.method, self.baseline
        self.assertEqual([(s.feature, s.order_before, s.order_after) for s in method.stages],
                         [(s.feature, s.order_before, s.order_after) for s in baseline.stages])
        self.assertGreater(method.stages[0].case_count, method.stages[0].index)
        self.assertEqual(method.stages[0].recognition_features, self.spec[1])
        self.assertEqual(method.additive_costs(), baseline.additive_costs())

    def test_every_refined_fiber_corrects_only_the_committed_goal(self):
        for method in (self.method, self.symbolic):
            stage = method.stages[0]
            fibers = defaultdict(list)
            for permutation in self.plan.group.permutations:
                fibers[_stage_observation(method.inventory.action(permutation), stage,
                                          method.inventory)].append(permutation)
            self.assertEqual(set(fibers), set(stage.observations))
            algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
            self.assertTrue(any(len(fiber) > 1 for fiber in fibers.values()))
            for case in stage.cases:
                self.assertIn(case.representative, fibers[case.observation])
                goal = _goal_observation(case.observation, method.inventory, stage)
                if goal == stage.solved_observation:
                    self.assertIsNone(case.algorithm_id)
                    correction = tuple(range(48))
                else:
                    correction = algorithms[case.algorithm_id].permutation
                for permutation in fibers[case.observation]:
                    after = method.inventory.action(_then(permutation, correction))
                    self.assertEqual(_observe(after, stage.block_index, stage.feature.kind),
                                     stage.solved_observation)

    def test_all_group_states_solve_and_finished_goal_skips_extra_observers(self):
        for method in (self.method, self.symbolic):
            saw_extra_unsolved = False
            stage = method.stages[0]
            solved_pattern = _stage_observation(method.inventory.action(tuple(range(48))),
                                               stage, method.inventory)
            for permutation in self.plan.group.permutations:
                state = _state_for_permutation(self.shape, permutation)
                action = method.inventory.action(permutation)
                goal = _observe(action, stage.block_index, stage.feature.kind)
                observation = _stage_observation(action, stage, method.inventory)
                recognition = method.recognize(state)
                if goal == stage.solved_observation and observation[:2] != solved_pattern[:2]:
                    saw_extra_unsolved = True
                    self.assertNotEqual(recognition.stage_number, 1)
                elif goal != stage.solved_observation:
                    self.assertEqual(recognition.stage_number, 1)
                    self.assertEqual(recognition.observation, observation)
                self.assertTrue(method.apply(state).state.is_solved)
            self.assertTrue(saw_extra_unsolved)

    def test_portable_refinement_loads_offline_and_rechecks_coverage(self):
        for method in (self.method, self.symbolic):
            record = method.to_dict()
            self.assertEqual(record["version"], 3)
            with patch("subprocess.run", side_effect=AssertionError("load requires no GAP")):
                loaded = c.HumanMethod.from_dict(record)
            self.assertEqual(loaded.to_dict(), record)
            self.assertEqual(loaded.stages[0].recognition_features, self.spec[1])
            broken = deepcopy(record)
            broken["stages"][0]["recognition_features"] = [self.extra.to_dict()]
            broken["fingerprint"] = _fingerprint(broken)
            with self.assertRaisesRegex(ValueError, "explicitly include"):
                c.HumanMethod.from_dict(broken)
            broken = deepcopy(record)
            del broken["stages"][0]["cases"][0]
            broken["stages"][0]["case_count"] -= 1
            broken["fingerprint"] = _fingerprint(broken)
            with self.assertRaisesRegex(ValueError, "omit"):
                c.HumanMethod.from_dict(broken)

    def test_observers_require_goal_recovery_and_complete_inventory_regions(self):
        goal = self.plan.stages[0].feature
        for features in ((), (self.extra,), (goal, goal)):
            with self.assertRaisesRegex(ValueError, "include|distinct"):
                _compile_plan(self.plan, recognition={1: features})
        with self.assertRaisesRegex(ValueError, "stage number"):
            _compile_plan(self.plan, recognition={True: (goal,)})
        with self.assertRaises(TypeError):
            _compile_plan(self.plan, recognition=[(goal,)])

    def test_goal_only_optimizers_reject_refined_patterns_explicitly(self):
        for optimizer in (c.improve_human_method, c.optimize_human_repertoire,
                          c.generator_human_repertoire):
            with self.assertRaisesRegex(ValueError, "independent recognition"):
                optimizer(self.method)

    def test_guides_describe_observers_and_diagrams_reject_incomplete_patterns(self):
        for method in (self.method, self.symbolic):
            guide = method.write_guide()
            first_stage = guide.split("## Stage 1:")[1].split("## Stage 2:")[0]
            self.assertIn("| Recognition pattern | Correction |", first_stage)
            extra_block = next(block for block in method.inventory.blocks
                               if block.cells == self.extra.cells)
            self.assertIn(extra_block.compact_name, first_stage)
            with self.assertRaisesRegex(ValueError, "independent recognition"):
                c.recognition_stage_diagrams(method, 1)
            with self.assertRaisesRegex(ValueError, "independent recognition"):
                c.recognition_case_diagrams(method, 1, method.stages[0].cases[0].observation)

    def test_exact_additive_claim_requires_goal_determined_effect_and_cost(self):
        stage = self.method.stages[0]
        case = next(case for case in stage.cases if case.algorithm_id is not None)
        algorithm = next(algorithm for algorithm in self.method.algorithms
                         if algorithm.id == case.algorithm_id)
        # A longer legally replayable witness with the same endpoint still
        # makes cost depend on a finer observer than the committed goal.
        from bce_v2.block_solver import _permutation_order
        for generator in self.method.generators:
            order = _permutation_order(generator.permutation)
            moves = _simplified_moves((algorithm.turn_sequence + " " +
                                      " ".join([generator.turn_sequence] * order)).split())
            if len(moves.split()) > algorithm.htm_length:
                break
        else:
            self.fail("fixture has no longer identity witness after adjacent-turn simplification")
        longer = replace(algorithm, id="longer",
                         expression=c.LoopExpression.sequence(
                             algorithm.expression,
                             c.LoopExpression.power(c.LoopExpression.loop(generator.id), order)),
                         turn_sequence=moves)
        modified = replace(self.method, algorithms=(*self.method.algorithms, longer),
                           stages=(replace(stage, cases=tuple(replace(original, algorithm_id="longer")
                                        if original == case else original for original in stage.cases)),
                                   *self.method.stages[1:]))
        self.assertEqual(longer.expression.evaluate(self.method.generators), algorithm.permutation)
        self.assertEqual(c.State(self.shape).apply(longer.turn_sequence).sticker_permutation,
                         algorithm.permutation)
        with self.assertRaisesRegex(ValueError, "effect and cost"):
            modified.additive_costs()


if __name__ == "__main__":
    unittest.main()
