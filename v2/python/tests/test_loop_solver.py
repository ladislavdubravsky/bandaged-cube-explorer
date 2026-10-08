"""Constructive colored solving, compact witnesses, and reachability proofs."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.gap_backend import GapFactorization, GapTimeoutError


def one_face_shapes():
    pair = [0] * 9 + [1] * 18
    pair[c.UBL] = pair[c.UB] = 2
    opposite = pair.copy()
    opposite[c.UFR] = opposite[c.UF] = 3
    return c.Shape(pair), c.Shape(opposite), c.Shape([0] * 9 + [1] * 18)


def imported(state):
    return c.State.from_facelets(state.facelets, state.specification)


def small_analysis(shape, order):
    loops = c.isotropy_loops(shape)
    return c.IsotropyAnalysis(loops, order, tuple(g.id for g in loops), "4.12.1")


def replay_expression(state, result):
    replayed = state.apply(result.shape_solution)
    algorithms = {algorithm.id: algorithm for algorithm in result.algorithms}
    for step in result.steps:
        moves = algorithms[step.generator_id].moves.split()
        if step.exponent < 0:
            moves = [move if move.endswith("2") else
                     move[:-1] if move.endswith("'") else move + "'"
                     for move in reversed(moves)]
        for _ in range(abs(step.exponent)):
            replayed = replayed.apply(" ".join(moves))
    return replayed


class LoopSolutionContractTests(unittest.TestCase):
    def setUp(self):
        self.shape = one_face_shapes()[2]
        self.solver = c.LoopSolver(small_analysis(self.shape, 4))
        self.half = imported(c.State(self.shape).apply("U2"))

    def test_compact_powers_costs_and_expansion_cap(self):
        factored = GapFactorization(4, True, ((0, 2),), "4.12.1")
        with patch("bce_v2.gap_backend.factor_permutation", return_value=factored):
            stopped = self.solver.solve(self.half, max_expanded_moves=1)
            solved = self.solver.solve(self.half, metric="htm", max_expanded_moves=2)
        self.assertEqual(stopped.status, "limit_reached")
        self.assertEqual(stopped.stop_reason, "expansion_limit")
        self.assertIsNone(stopped.solution)
        self.assertIsNone(stopped.distance)
        self.assertEqual(stopped.required_expanded_moves, 2)
        self.assertEqual(stopped.algorithm_count, 1)
        self.assertEqual(stopped.steps[0].exponent, 2)
        self.assertTrue(replay_expression(self.half, stopped).is_solved)
        self.assertEqual(solved.status, "solved")
        self.assertEqual(solved.solution, "U2")
        self.assertEqual((solved.qtm_length, solved.htm_length, solved.distance), (2, 1, 1))
        self.assertEqual(solved.metric, "HTM")
        self.assertFalse(solved.optimal)

    def test_solved_and_restoration_only_need_no_factorization(self):
        pair = one_face_shapes()[0]
        solver = c.LoopSolver(small_analysis(pair, 1))
        with patch("bce_v2.gap_backend.factor_permutation") as factor:
            empty = self.solver.solve(c.State(self.shape), max_expanded_moves=0)
            restored = solver.solve(imported(c.State(pair).apply("U")))
            factor.assert_not_called()
        self.assertEqual((empty.status, empty.solution, empty.required_expanded_moves),
                         ("solved", "", 0))
        self.assertEqual(restored.status, "solved")
        self.assertEqual(restored.steps, ())
        self.assertTrue(c.State(pair).apply("U").apply(restored.solution).is_solved)

    def test_absent_shape_proves_unreachability_before_factorization(self):
        labels = [0] * 27
        for cell in (c.U, c.R, c.F, c.D, c.L, c.B, c.C):
            labels[cell] = 1
        labels[c.UFR] = labels[c.UR] = 2
        shape = c.Shape(labels)
        solver = c.LoopSolver(small_analysis(shape, 1))
        source = c.State.from_facelets(c.State().apply("R").facelets, shape)
        with patch("bce_v2.gap_backend.factor_permutation") as factor:
            result = solver.solve(source)
            factor.assert_not_called()
        self.assertEqual(result.status, "unreachable")
        self.assertEqual(result.stop_reason, "shape_outside_component")
        self.assertIsNone(result.shape_solution)
        self.assertIsNone(result.required_expanded_moves)

    def test_backend_failures_and_inconsistent_order_are_never_unreachable(self):
        with patch("bce_v2.gap_backend.factor_permutation", side_effect=GapTimeoutError("test timeout")):
            with self.assertRaises(GapTimeoutError):
                self.solver.solve(self.half)
        with patch("bce_v2.gap_backend.factor_permutation",
                   return_value=GapFactorization(2, False, (), "4.12.1")):
            with self.assertRaisesRegex(c.GapError, "order"):
                self.solver.solve(self.half)

    def test_options_and_specification_are_validated_even_for_solved_input(self):
        solved = c.State(self.shape)
        invalid = [({"metric": "bad"}, ValueError), ({"metric": None}, TypeError),
                   ({"max_expanded_moves": True}, TypeError),
                   ({"max_expanded_moves": -1}, ValueError),
                   ({"max_expanded_moves": 1.5}, TypeError),
                   ({"timeout": True}, TypeError), ({"timeout": 0}, ValueError),
                   ({"timeout": float("inf")}, ValueError)]
        for options, error in invalid:
            with self.subTest(options=options), self.assertRaises(error):
                self.solver.solve(solved, **options)
        with self.assertRaisesRegex(ValueError, "specification"):
            self.solver.solve(c.State())
        with self.assertRaises(TypeError):
            self.solver.solve(self.shape)
        with self.assertRaises(TypeError):
            c.solve_colored_loops(self.shape)
        with self.assertRaises(TypeError):
            c.solve_colored_loops(solved, solver=object())
        with self.assertRaisesRegex(ValueError, "prepared"):
            c.solve_colored_loops(solved, solver=self.solver, gap_executable="custom-gap")
        with self.assertRaises(ValueError):
            c.LoopSolver(self.solver.analysis, timeout=0)
        with self.assertRaisesRegex(ValueError, "complete"):
            c.LoopSolver(c.explore(one_face_shapes()[0], max_vertices=1))

    def test_results_are_immutable_and_export_replayable_algorithms(self):
        with patch("bce_v2.gap_backend.factor_permutation",
                   return_value=GapFactorization(4, True, ((0, 2),), "4.12.1")):
            result = c.solve_colored_loops(self.half, solver=self.solver)
        record = result.to_dict()
        self.assertEqual(record["group_order"], "4")
        self.assertEqual(record["algorithm_count"], 1)
        self.assertEqual(record["steps"], [result.steps[0].to_dict()])
        self.assertIn("moves", record["algorithms"][0])
        self.assertEqual(json.loads(result.to_json()), record)
        record["steps"].clear()
        self.assertEqual(len(result.steps), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solution.json"
            self.assertEqual(result.save(path), json.loads(path.read_text()))
        with self.assertRaises(FrozenInstanceError):
            result.status = "unreachable"
        with self.assertRaises(FrozenInstanceError):
            result.steps[0].exponent = 5
        with self.assertRaises(AttributeError):
            self.solver.generators = ()


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external dependency")
class LiveLoopSolvingTests(unittest.TestCase):
    def assert_solution(self, solver, state):
        self.assertIsNone(state.scramble)
        result = solver.solve(state, timeout=45)
        self.assertEqual(result.status, "solved")
        self.assertTrue(state.apply(result.solution).is_solved)
        self.assertTrue(replay_expression(state, result).is_solved)
        self.assertTrue({algorithm.id for algorithm in result.algorithms}.issubset(
            {algorithm.id for algorithm in solver.generators}))
        self.assertEqual(result.algorithm_count, len({step.generator_id for step in result.steps}))
        return result

    def test_exhaust_all_small_components_with_different_fiber_sizes(self):
        for shape in one_face_shapes():
            solver = c.LoopSolver(shape, timeout=30)
            graph = c.explore_colored(c.State(shape))
            self.assertEqual(len(graph), 4)
            for state in graph:
                with self.subTest(shapes=solver.shape_count, state=state.facelets):
                    self.assert_solution(solver, state)

    def test_named_fixtures_nontrivial_loops_and_scrambled_initial_reference(self):
        rng = random.Random(47)
        for name in ("Alcatraz", "Bicube Fuse", "Shark Fin Soup"):
            shape = c.fixture(name)
            solver = c.LoopSolver(c.State(shape), timeout=30)
            state = c.State(shape)
            for generator in solver.generators[:2]:
                state = state.apply(generator.moves)
            for _ in range(12):
                state = state.apply(rng.choice(state.legal_moves))
            with self.subTest(name=name):
                result = self.assert_solution(solver, imported(state))
                self.assertGreaterEqual(result.algorithm_count, 1)
        # This scramble changes shape; preparation must use its specification.
        state = c.State(c.fixture("Alcatraz")).apply("F R2")
        solver = c.LoopSolver(imported(state), timeout=30)
        self.assertEqual(solver.specification, state.specification)
        self.assert_solution(solver, imported(state))

    def test_nonzero_root_loops_and_analysis_keep_original_algorithm_ids(self):
        original = c.explore(one_face_shapes()[1], metric="HTM")
        loops = original.isotropy_loops(root=1)
        analysis = loops.analyze(timeout=30)
        for initial in (loops, analysis):
            solver = c.LoopSolver(initial, timeout=30)
            self.assertEqual(solver.specification, loops.root_shape)
            self.assertEqual(tuple(g.id for g in solver.generators), analysis.generator_ids)
            for amount in ("U", "U2", "U'"):
                self.assert_solution(solver, imported(c.State(loops.root_shape).apply(amount)))
            with self.assertRaisesRegex(ValueError, "specification"):
                solver.solve(c.State(original[0]))

    def test_unreachable_orientation_and_empty_loop_group(self):
        shape = one_face_shapes()[2]
        solver = c.LoopSolver(shape, timeout=30)
        state = c.State.from_cubies(shape, corners=list(range(8)),
                                   twists=[1, 2] + [0] * 6,
                                   edges=list(range(12)), flips=[0] * 12)
        result = solver.solve(state, timeout=30)
        self.assertEqual((result.status, result.stop_reason),
                         ("unreachable", "residual_not_in_group"))
        labels = [0] * 27
        for cell in (c.U, c.R, c.F, c.D, c.L, c.B, c.C):
            labels[cell] = 1
        frozen = c.Shape(labels)
        solver = c.LoopSolver(frozen, timeout=30)
        state = c.State.from_facelets(c.State().apply("R").facelets, frozen)
        self.assertEqual(solver.generators, ())
        self.assertEqual(solver.solve(state, timeout=30).status, "unreachable")

    def test_large_colored_component_and_ordinary_cube_without_colored_enumeration(self):
        msc = [0, 0, 0, 0, 0, 0, 1, 0, 0,
               7, 6, 5, 8, 0, 4, 1, 2, 3,
               7, 6, 5, 8, 0, 4, 1, 2, 3]
        for shape, order in ((c.Shape(msc), 10_368),
                             (c.Shape(), 43_252_003_274_489_856_000)):
            with self.subTest(order=order):
                solver = c.LoopSolver(shape, timeout=45)
                self.assertEqual(solver.group_order, order)
                state = c.State(shape)
                for generator in solver.generators[:2]:
                    state = state.apply(generator.moves)
                state = state.apply("R L U")
                result = self.assert_solution(solver, imported(state))
                self.assertGreaterEqual(result.algorithm_count, 1)
                self.assertEqual(result.to_dict()["group_order"], str(order))


if __name__ == "__main__":
    unittest.main()
