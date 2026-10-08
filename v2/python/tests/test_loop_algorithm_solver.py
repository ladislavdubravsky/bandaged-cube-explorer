"""Replayable physical and structured answers with complete GAP fallback."""

from dataclasses import FrozenInstanceError
import json
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.gap_backend import GapTimeoutError
from test_loop_algorithms import expand_move_notation


def one_face():
    return c.Shape([0] * 9 + [1] * 18)


def independent_faces():
    return c.Shape([0] * 9 + [1] * 9 + [0] * 9)


def prepared(shape, order):
    loops = c.isotropy_loops(shape)
    analysis = c.IsotropyAnalysis(loops, order, tuple(g.id for g in loops), "test")
    return c.LoopSolver(analysis)


def imported(state):
    return c.State.from_facelets(state.facelets, state.specification)


def inverse_moves(word):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(word.split()))


def leaf_for(loops, move):
    return c.LoopExpression.loop(next(g.id for g in loops if g.moves == move))


def replay_option(source, option, loops):
    state = source.apply(option.shape_solution)
    def has_rotation(node):
        return node.kind == "rotated" or any(has_rotation(child) for child in node.children)

    if has_rotation(option.structured_expression):
        return state.apply(option.structured_expression.expanded_moves(loops))
    by_id = {generator.id: generator for generator in loops}
    for identifier, exponent in option.structured_expression.loop_steps():
        moves = by_id[identifier].moves
        if exponent < 0:
            moves = inverse_moves(moves)
        for _ in range(abs(exponent)):
            state = state.apply(moves)
    return state


class AlgorithmSolutionContractTests(unittest.TestCase):
    def test_solved_and_restoration_only_answers_need_no_gap_and_export_immutable_records(self):
        labels = [0] * 9 + [1] * 18
        labels[c.UBL] = labels[c.UB] = 2
        pair = c.Shape(labels)
        for solver, source in ((prepared(one_face(), 4), c.State(one_face())),
                               (prepared(pair, 1), imported(c.State(pair).apply("U")))):
            library = c.discover_loop_algorithms(solver.analysis, rounds=0,
                                                 max_candidates=8, max_algorithms=8)
            with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("trivial solve called GAP")):
                options = solver.solve_options(source, library=library, max_states=0, max_depth=0)
            for option in (options.shortest_found, options.most_structured):
                self.assertEqual(option.status, "solved")
                self.assertTrue(source.apply(option.solution).is_solved)
                self.assertTrue(replay_option(source, option, library.loops).is_solved)
                self.assertEqual(option.structured_turn_sequence, "()")
                self.assertEqual(option.to_dict()["structured_turn_sequence"], "()")
                self.assertEqual(option.algorithm_count, 0)
                self.assertFalse(option.optimal)
                self.assertEqual(option.algorithms, ())
            self.assertTrue(options.search_complete)
            self.assertEqual(options.searched_states, 0)
            self.assertEqual(json.loads(options.to_json()), options.to_dict())
            with self.assertRaises(FrozenInstanceError):
                options.max_depth = 1
            with self.assertRaises(FrozenInstanceError):
                options.shortest_found.status = "unreachable"
        self.assertTrue(options.shortest_found.shape_solution)
        self.assertEqual(options.shortest_found.solution, options.shortest_found.shape_solution)

    def test_invalid_options_and_mismatched_reference_library_are_rejected_before_gap(self):
        solver = prepared(one_face(), 4)
        library = c.discover_loop_algorithms(solver.analysis, rounds=0,
                                             max_candidates=8, max_algorithms=8)
        source = c.State(one_face())
        invalid = (({"max_states": True}, TypeError), ({"max_states": -1}, ValueError),
                   ({"max_depth": 1.5}, TypeError), ({"max_depth": -1}, ValueError),
                   ({"metric": None}, TypeError), ({"metric": "bad"}, ValueError))
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("validation called GAP")):
            for kwargs, error in invalid:
                with self.subTest(kwargs=kwargs), self.assertRaises(error):
                    solver.solve_options(source, library=library, **kwargs)
            with self.assertRaises(TypeError):
                solver.solve_options(source, library=object())
            with self.assertRaises(TypeError):
                solver.solve_options(None, library=library)
            other = c.discover_loop_algorithms(c.Shape([1] * 9 + [2] * 18), rounds=0,
                                               max_candidates=8, max_algorithms=8)
            with self.assertRaisesRegex(ValueError, "reference"):
                solver.solve_options(source, library=other)

    def test_optional_factorization_timeout_keeps_verified_answers_and_visible_memory_count(self):
        shape = independent_faces()
        solver = prepared(shape, 16)
        loops = solver.analysis.loops
        u, d = leaf_for(loops, "U"), leaf_for(loops, "D")
        repeated = c.LoopExpression.power(c.LoopExpression.sequence(u, d), 2)
        literal = c.LoopExpression.turns("U2 D2", repeated)
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16).with_expressions(literal)
        source = imported(c.State(shape).apply("U2 D2"))
        steps = (c.LoopStep(u.generator_id, 1), c.LoopStep(d.generator_id, 1)) * 2
        baseline = c.LoopSolution("solved", "U D U D", "", steps,
                                  tuple(loops.generators), shape, 16, "test", "HTM",
                                  required_expanded_moves=4)
        with patch.object(c.LoopSolver, "solve", return_value=baseline), patch(
                "bce_v2.gap_backend.factor_permutation", side_effect=GapTimeoutError("optional timeout")):
            options = solver.solve_options(source, library=library, max_states=0, max_depth=0)
        self.assertIs(options.baseline, baseline)
        self.assertIn("factorization_timeout", options.candidate_stop_reasons)
        for option in (options.shortest_found, options.most_structured):
            self.assertEqual(option.status, "solved")
            self.assertTrue(source.apply(option.solution).is_solved)
            self.assertTrue(replay_option(source, option, library.loops).is_solved)
            self.assertEqual(option.original_loop_count, 2)
            self.assertEqual(len(option.base_algorithms), 2)
        self.assertEqual(options.shortest_found.htm_length, 2)
        self.assertEqual(options.shortest_found.algorithm_count, 1)

    def test_optional_goal_expansion_limit_preserves_the_verified_baseline(self):
        shape = independent_faces()
        solver = prepared(shape, 16)
        loops = solver.analysis.loops
        u, d = leaf_for(loops, "U"), leaf_for(loops, "D")
        body = c.LoopExpression.sequence(u, d)
        macro = c.LoopExpression.power(body, 1)
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16).with_expressions(macro)
        source = imported(c.State(shape).apply("U2 D2"))
        steps = (c.LoopStep(u.generator_id, 1), c.LoopStep(d.generator_id, 1)) * 2
        baseline = c.LoopSolution("solved", "U D U D", "", steps,
                                  tuple(loops.generators), shape, 16, "test", "HTM",
                                  required_expanded_moves=4)
        original_builder = c.AlgorithmLibrary.build_algorithm

        def contains_repeat_goal(expression):
            return (expression.kind == "power" and abs(expression.exponent) == 2
                    and expression.children == (body,)) or any(
                        contains_repeat_goal(child) for child in expression.children)

        def limited_optional_builder(instance, expression, **kwargs):
            # Lower only the optional repeated-goal budget; this reproduces a
            # long macro exceeding 100k turns without allocating that payload.
            if contains_repeat_goal(expression):
                kwargs["max_expanded_moves"] = 3
            return original_builder(instance, expression, **kwargs)

        with patch.object(c.LoopSolver, "solve", return_value=baseline), patch.object(
                c.AlgorithmLibrary, "build_algorithm", new=limited_optional_builder), patch(
                "bce_v2.gap_backend.factor_permutation", side_effect=GapTimeoutError("optional timeout")):
            options = solver.solve_options(source, library=library, max_states=64, max_depth=2)
        self.assertIs(options.baseline, baseline)
        self.assertIn("expression_limit", options.candidate_stop_reasons)
        for option in (options.shortest_found, options.most_structured):
            self.assertEqual(option.status, "solved")
            self.assertTrue(source.apply(option.solution).is_solved)
            self.assertTrue(replay_option(source, option, library.loops).is_solved)

    def test_rotated_option_exports_a_frame_neutral_display_and_face_only_execution(self):
        shape = c.Shape()
        solver = prepared(shape, 43_252_003_274_489_856_000)
        loops = solver.analysis.loops
        r, u, f = (leaf_for(loops, move) for move in ("R", "U", "F"))
        rotated = c.LoopExpression.rotated("x", c.LoopExpression.commutator(r, u))
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16).with_expressions(rotated)
        source = imported(c.State(shape).apply("F R F' R'"))
        # The commutator has order six, so seven repetitions are a valid,
        # deliberately longer baseline for the same correction.
        direct = c.LoopExpression.commutator(r, f)
        baseline_word = " ".join(["R F R' F'"] * 7)
        self.assertTrue(source.apply(baseline_word).is_solved)
        steps = tuple(c.LoopStep(identifier, exponent)
                      for identifier, exponent in c.LoopExpression.power(direct, 7).loop_steps())
        baseline = c.LoopSolution("solved", baseline_word, "", steps,
                                  tuple(loops.generators), shape, solver.group_order, "test", "HTM",
                                  required_expanded_moves=28)
        with patch.object(c.LoopSolver, "solve", return_value=baseline), patch(
                "bce_v2.gap_backend.factor_permutation", side_effect=GapTimeoutError("optional timeout")):
            options = solver.solve_options(source, library=library, max_states=0, max_depth=0)
        for option in (options.shortest_found, options.most_structured):
            self.assertEqual(option.structured_expression, rotated)
            self.assertEqual(option.structured_turn_sequence, "x ([R, U]) x'")
            self.assertEqual(option.solution, "R F R' F'")
            self.assertEqual((option.htm_length, option.qtm_length), (4, 4))
            self.assertTrue(source.apply(expand_move_notation(option.structured_turn_sequence)).is_solved)
            self.assertTrue(replay_option(source, option, loops).is_solved)
            self.assertEqual(option.algorithm_count, 2)
            self.assertEqual(option.to_dict()["structured_turn_sequence"], "x ([R, U]) x'")

    def test_same_reference_shape_does_not_make_different_original_loop_ids_compatible(self):
        shape = c.fixture("Alcatraz")
        solver = prepared(shape, 324)
        other_loops = c.isotropy_loops(c.explore(shape, metric="HTM"))
        self.assertEqual(other_loops.root_shape, solver.specification)
        self.assertNotEqual({g.id: g.permutation for g in other_loops},
                            {g.id: g.permutation for g in solver.analysis.loops})
        library = c.discover_loop_algorithms(other_loops, rounds=0, max_candidates=8,
                                             max_algorithms=8, max_htm_length=24)
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("mismatch called GAP")):
            with self.assertRaisesRegex(ValueError, "witness"):
                solver.solve_options(c.State(shape), library=library)


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external dependency")
class LiveAlgorithmSolutionTests(unittest.TestCase):
    def assert_option(self, source, option, library):
        self.assertEqual(option.status, "solved")
        self.assertTrue(source.apply(option.solution).is_solved)
        self.assertTrue(replay_option(source, option, library.loops).is_solved)
        self.assertEqual(option.structured_turn_sequence,
                         option.structured_expression.render_moves(option.base_algorithms))
        stage = expand_move_notation(option.structured_turn_sequence)
        self.assertTrue(source.apply(option.shape_solution).apply(stage).is_solved)
        self.assertEqual(option.to_dict()["structured_turn_sequence"], option.structured_turn_sequence)
        self.assertEqual(option.htm_length, len(option.solution.split()))
        self.assertEqual(option.qtm_length, sum(2 if move.endswith("2") else 1
                                              for move in option.solution.split()))
        self.assertEqual(option.algorithm_count, len(option.structured_expression.memory_keys))
        self.assertEqual(option.original_loop_count, len(option.base_algorithms))
        self.assertEqual(set(option.structured_expression.base_ids),
                         {generator.id for generator in option.base_algorithms})
        self.assertFalse(option.optimal)

    def test_short_physical_answer_and_localized_composite_are_both_retained(self):
        shape = independent_faces()
        solver = prepared(shape, 16)
        loops = solver.analysis.loops
        u, d = leaf_for(loops, "U"), leaf_for(loops, "D")
        localized = c.LoopExpression.sequence(u, d, u, d)
        short = c.LoopExpression.turns("U2 D2", localized)
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16).with_expressions(short, localized)
        source = imported(c.State(shape).apply("U2 D2"))
        # This genuine legal word is deliberately longer than the new direct
        # candidate, so selection is checked independently of GAP's word choice.
        steps = (c.LoopStep(u.generator_id, 1), c.LoopStep(d.generator_id, 1)) * 2
        baseline = c.LoopSolution("solved", "U D U D", "", steps,
                                  tuple(loops.generators), shape, 16, "test", "HTM",
                                  required_expanded_moves=4)
        with patch.object(c.LoopSolver, "solve", return_value=baseline):
            options = solver.solve_options(source, library=library, max_states=64, max_depth=2)
        self.assertIs(options.baseline, baseline)
        self.assertEqual(options.shortest_found.htm_length, 2)
        self.assertLess(options.shortest_found.htm_length, options.baseline.htm_length)
        self.assertEqual(options.most_structured.htm_length, 4)
        self.assertEqual(options.most_structured.structure_score[:2], (16, 8))
        self.assertEqual(options.shortest_found.structure_score[:2], (16, 16))
        self.assertLess(options.most_structured.structure_score, options.shortest_found.structure_score)
        self.assert_option(source, options.shortest_found, library)
        self.assert_option(source, options.most_structured, library)
        self.assertEqual(json.loads(options.to_json()), options.to_dict())

    def test_imported_half_turn_finds_one_htm_even_with_zero_search_budget(self):
        shape = one_face()
        solver = prepared(shape, 4)
        library = c.discover_loop_algorithms(solver.analysis, rounds=0,
                                             max_candidates=8, max_algorithms=8)
        library = library.with_expressions(c.LoopExpression.power(leaf_for(library.loops, "U"), 2))
        source = imported(c.State(shape).apply("U2"))
        self.assertIsNone(source.scramble)
        options = solver.solve_options(source, library=library, metric="HTM", max_states=0, max_depth=0)
        self.assert_option(source, options.shortest_found, library)
        self.assert_option(source, options.most_structured, library)
        self.assertEqual((options.shortest_found.htm_length, options.shortest_found.qtm_length), (1, 2))
        self.assertFalse(options.search_complete)
        self.assertEqual(options.stop_reason, "state_limit")
        self.assertEqual(options.searched_states, 0)
        self.assertIsInstance(options.baseline, c.LoopSolution)
        self.assertEqual(options.baseline.factorization, "sticker")

    def test_pruned_library_and_capped_search_keep_the_complete_original_solver(self):
        shape = c.fixture("Alcatraz")
        solver = prepared(shape, 324)
        library = c.discover_loop_algorithms(solver.analysis, rounds=0, max_candidates=8,
                                             max_algorithms=8, max_htm_length=1)
        self.assertEqual(library.algorithms, ())
        generator = next(g for g in solver.analysis.loops if g.id == 142)
        source = imported(c.State(shape).apply(generator.moves))
        options = solver.solve_options(source, library=library, max_states=0, max_depth=0)
        self.assertEqual(options.baseline.status, "solved")
        self.assertEqual(options.shortest_found.source, "baseline")
        self.assertEqual(options.most_structured.source, "baseline")
        self.assertFalse(options.search_complete)
        self.assertEqual(options.stop_reason, "state_limit")
        self.assert_option(source, options.shortest_found, library)
        self.assert_option(source, options.most_structured, library)
        original = solver.solve(source, metric="HTM")
        self.assertIsInstance(original, c.LoopSolution)
        self.assertEqual(original.factorization, "sticker")
        self.assertTrue(source.apply(original.solution).is_solved)

    def test_discovery_limits_do_not_replace_exact_unreachability_with_a_search_miss(self):
        shape = one_face()
        solver = prepared(shape, 4)
        library = c.discover_loop_algorithms(solver.analysis, rounds=0,
                                             max_candidates=8, max_algorithms=8)
        source = c.State.from_cubies(shape, corners=list(range(8)), twists=[1, 2] + [0] * 6,
                                    edges=list(range(12)), flips=[0] * 12)
        options = solver.solve_options(source, library=library, max_states=0, max_depth=0)
        self.assertEqual(options.baseline.status, "unreachable")
        for option in (options.shortest_found, options.most_structured):
            self.assertEqual(option.status, "unreachable")
            self.assertEqual(option.stop_reason, "residual_not_in_group")
            self.assertIsNone(option.solution)
            self.assertFalse(option.optimal)


if __name__ == "__main__":
    unittest.main()
