"""Witnessed placement quotients and abelian rigid-block corrections."""

from dataclasses import FrozenInstanceError
import json
import shutil
import unittest

import bce_v2 as c


IDENTITY = tuple(range(48))
MOST_SIGNATURES = [0, 0, 0, 0, 0, 0, 1, 0, 0,
                   7, 6, 5, 8, 0, 4, 1, 2, 3,
                   7, 6, 5, 8, 0, 4, 1, 2, 3]


def one_face_shapes():
    pair = [0] * 9 + [1] * 18
    pair[c.UBL] = pair[c.UB] = 2
    opposite = pair.copy()
    opposite[c.UFR] = opposite[c.UF] = 3
    return c.Shape(pair), c.Shape(opposite), c.Shape([0] * 9 + [1] * 18)


def fused_face():
    # A symmetric U face can turn; the fused remaining layers block D/R/F/L/B.
    return c.Shape([1] * 9 + [2] * 18)


def imported(state):
    return c.State.from_facelets(state.facelets, state.specification)


def inverse_moves(moves):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(moves.split()))


def replay_steps(state, steps, algorithms, *, kernel=False):
    by_id = {algorithm.id: algorithm for algorithm in algorithms}
    for step in steps:
        key = step.basis_id if kernel else step.generator_id
        moves = by_id[key].moves
        if step.exponent < 0:
            moves = inverse_moves(moves)
        for _ in range(abs(step.exponent)):
            state = state.apply(moves)
    return state


def distinct_prime_factors(value):
    prime = 2
    while prime * prime <= value:
        if value % prime == 0:
            yield prime
            while value % prime == 0:
                value //= prime
        prime += 1
    if value > 1:
        yield value


class BlockFactorizationModeTests(unittest.TestCase):
    def test_default_sticker_mode_and_explicit_strategy_are_validated(self):
        shape = one_face_shapes()[2]
        loops = c.isotropy_loops(shape)
        analysis = c.IsotropyAnalysis(loops, 4, tuple(g.id for g in loops), "test")
        baseline = c.LoopSolver(analysis).solve(c.State(shape))
        self.assertEqual(baseline.factorization, "sticker")
        explicit = c.LoopSolver(analysis, factorization="sticker").solve(c.State(shape))
        self.assertEqual(explicit.factorization, "sticker")
        with self.assertRaises(ValueError):
            c.LoopSolver(analysis, factorization="unknown")
        prepared = c.LoopSolver(analysis, factorization="sticker")
        with self.assertRaises(ValueError):
            c.solve_colored_loops(c.State(shape), solver=prepared, factorization="quotient_kernel")


class _StageReplayAssertions:
    def assert_staged_solution(self, solver, source, *, max_expanded_moves=None):
        result = solver.solve(source, max_expanded_moves=max_expanded_moves)
        self.assertEqual(result.factorization, "quotient_kernel")
        self.assertEqual(result.status, "solved" if max_expanded_moves is None else "limit_reached")
        structure = solver.block_structure
        self.assertEqual((result.quotient_order, result.kernel_order),
                         (structure.quotient_order, structure.kernel_order))
        restored = source.apply(result.shape_solution)
        self.assertEqual(restored.shape, solver.specification)
        placed = replay_steps(restored, result.placement_steps, result.placement_algorithms)
        action = solver.analysis.block_inventory.action(placed)
        self.assertEqual(action.destinations,
                         solver.analysis.block_inventory.identity().destinations)
        corrected = replay_steps(placed, result.kernel_steps, result.kernel_algorithms, kernel=True)
        self.assertTrue(corrected.is_solved)
        self.assertTrue(replay_steps(restored, result.steps, result.algorithms).is_solved)
        self.assertTrue({step.generator_id for step in result.steps}.issubset(
            {generator.id for generator in solver.generators}))
        self.assertEqual({algorithm.id for algorithm in result.placement_algorithms},
                         {step.generator_id for step in result.placement_steps})
        self.assertEqual({algorithm.id for algorithm in result.kernel_algorithms},
                         {step.basis_id for step in result.kernel_steps})
        if result.status == "solved":
            self.assertTrue(source.apply(result.solution).is_solved)
        return result


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external dependency")
class LiveBlockStructureTests(_StageReplayAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.named = []
        for name, orders in (("Alcatraz", (324, 18, 18)),
                             ("Bicube Fuse", (60, 60, 1)),
                             ("Shark Fin Soup", (36, 12, 3)),
                             ("MostSignaturesCube", (10_368, 144, 72))):
            shape = c.Shape(MOST_SIGNATURES) if name == "MostSignaturesCube" else c.fixture(name)
            solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=45)
            cls.named.append((name, solver, orders))

    def test_named_exact_orders_and_legally_witnessed_kernel_bases(self):
        for name, solver, expected in self.named:
            with self.subTest(name=name):
                structure = solver.block_structure
                self.assertIs(solver.block_structure, structure)
                self.assertEqual((structure.group_order, structure.quotient_order,
                                  structure.kernel_order), expected)
                self.assertEqual(structure.group_order,
                                 structure.quotient_order * structure.kernel_order)
                self.assertEqual([algorithm.id for algorithm in structure.basis],
                                 [f"K{index}" for index in range(len(structure.basis))])
                basis_order_product = 1
                for algorithm in structure.basis:
                    basis_order_product *= algorithm.order
                    self.assertGreater(algorithm.order, 1)
                    witnessed = replay_steps(c.State(solver.specification), algorithm.steps,
                                              solver.generators)
                    replayed = c.State(solver.specification).apply(algorithm.moves)
                    self.assertEqual(witnessed, replayed)
                    self.assertEqual(replayed.sticker_permutation, algorithm.permutation)
                    self.assertEqual(replayed.shape, solver.specification)
                    action = algorithm.block_action
                    self.assertEqual(action.permutation, algorithm.permutation)
                    self.assertEqual(action.destinations,
                                     solver.analysis.block_inventory.identity().destinations)
                    self.assertEqual((action ** algorithm.order).permutation, IDENTITY)
                    for prime in distinct_prime_factors(algorithm.order):
                        self.assertNotEqual((action ** (algorithm.order // prime)).permutation, IDENTITY)
                    turns = c.State(solver.specification).apply(algorithm.turn_sequence)
                    self.assertEqual(turns, replayed)
                    self.assertEqual(algorithm.htm_length, len(algorithm.turn_sequence.split()))
                    self.assertEqual(algorithm.qtm_length,
                                     sum(2 if move.endswith("2") else 1
                                         for move in algorithm.moves.split()))
                self.assertEqual(basis_order_product, structure.kernel_order)
                compact = structure.to_dict(include_moves=False)
                self.assertEqual(json.loads(structure.to_json(include_moves=False)), compact)
                for record in compact["basis"]:
                    self.assertNotIn("moves", record)
                    self.assertNotIn("turn_sequence", record)

    def test_named_scrambles_replay_placement_then_correction_and_original_steps(self):
        for name, solver, _ in self.named:
            with self.subTest(name=name):
                state = c.State(solver.specification)
                for generator in solver.generators[:2]:
                    state = state.apply(generator.moves)
                for index in range(8):
                    state = state.apply(state.legal_moves[index % len(state.legal_moves)])
                self.assert_staged_solution(solver, imported(state))

    def test_two_stage_result_exports_replayable_basis_and_original_references(self):
        _, solver, _ = self.named[0]
        state = c.State(solver.specification)
        for generator in solver.generators[:2]:
            state = state.apply(generator.moves)
        result = self.assert_staged_solution(solver, imported(state))
        record = result.to_dict()
        self.assertEqual(record["factorization"], "quotient_kernel")
        self.assertEqual(record["quotient_order"], str(result.quotient_order))
        self.assertEqual(record["kernel_order"], str(result.kernel_order))
        self.assertEqual(record["placement_steps"], [step.to_dict() for step in result.placement_steps])
        self.assertEqual(record["placement_algorithms"],
                         [algorithm.to_dict() for algorithm in result.placement_algorithms])
        self.assertEqual(record["kernel_steps"], [step.to_dict() for step in result.kernel_steps])
        self.assertEqual(record["placement_expression"], result.placement_expression)
        self.assertEqual(record["kernel_expression"], result.kernel_expression)
        self.assertEqual(json.loads(result.to_json()), record)
        with self.assertRaises(FrozenInstanceError):
            result.factorization = "sticker"
        if result.kernel_steps:
            with self.assertRaises(FrozenInstanceError):
                result.kernel_steps[0].exponent = 0
        for algorithm in result.kernel_algorithms:
            self.assertEqual(json.loads(json.dumps(algorithm.to_dict())), algorithm.to_dict())


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external dependency")
class LiveBlockSolverEdgeTests(_StageReplayAssertions, unittest.TestCase):
    def test_exhaust_all_small_components_including_trivial_kernel_and_group(self):
        shapes = (*one_face_shapes(), fused_face(), c.Shape([1] * 27))
        for shape in shapes:
            solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
            structure = solver.block_structure
            self.assertEqual(structure.group_order, solver.group_order)
            self.assertEqual(structure.group_order,
                             structure.quotient_order * structure.kernel_order)
            for state in c.explore_colored(c.State(shape)):
                with self.subTest(shape_count=solver.shape_count, facelets=state.facelets):
                    self.assert_staged_solution(solver, state)
            if structure.group_order == 1:
                self.assertEqual((structure.quotient_order, structure.kernel_order,
                                  structure.basis), (1, 1, ()))

    def test_order_four_kernel_moves_members_within_one_fixed_fused_face(self):
        shape = fused_face()
        solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        structure = solver.block_structure
        self.assertEqual((structure.group_order, structure.quotient_order,
                          structure.kernel_order), (4, 1, 4))
        self.assertEqual(len(structure.basis), 1)
        algorithm = structure.basis[0]
        self.assertEqual(algorithm.order, 4)
        state = c.State(shape).apply(algorithm.moves)
        self.assertNotEqual(state.corners, list(range(8)))
        self.assertEqual(state.shape, shape)
        self.assertNotEqual((algorithm.block_action ** 2).permutation, IDENTITY)
        self.assertEqual((algorithm.block_action ** 4).permutation, IDENTITY)

    def test_compact_cap_keeps_both_stages_and_executable_kernel_basis(self):
        shape = fused_face()
        solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        source = imported(c.State(shape).apply("U2"))
        result = self.assert_staged_solution(solver, source, max_expanded_moves=0)
        self.assertEqual(result.stop_reason, "expansion_limit")
        self.assertIsNone(result.solution)
        self.assertIsNone(result.distance)
        self.assertGreater(result.required_expanded_moves, 0)
        self.assertEqual(result.placement_steps, ())
        self.assertNotEqual(result.kernel_steps, ())
        self.assertEqual(result.placement_expression, "")
        self.assertTrue(result.kernel_expression)
        self.assertTrue(result.expression)
        self.assertTrue(result.kernel_algorithms)

    def test_valid_placement_can_have_an_unreachable_orientation_residual(self):
        shape = one_face_shapes()[2]
        solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        source = c.State.from_cubies(shape, corners=list(range(8)),
                                    twists=[1, 2] + [0] * 6,
                                    edges=list(range(12)), flips=[0] * 12)
        self.assertEqual(source.shape, shape)
        action = solver.analysis.block_inventory.action(source)
        self.assertEqual(action.destinations,
                         solver.analysis.block_inventory.identity().destinations)
        for partial in (source, source.apply("U")):
            result = solver.solve(partial)
            self.assertEqual((result.status, result.stop_reason),
                             ("unreachable", "kernel_residual_not_in_group"))
            self.assertIsNone(result.solution)
            self.assertIsNone(result.required_expanded_moves)
            self.assertEqual(result.kernel_steps, ())
            placed = replay_steps(partial.apply(result.shape_solution), result.placement_steps,
                                  result.placement_algorithms)
            self.assertEqual(solver.analysis.block_inventory.action(placed).destinations,
                             solver.analysis.block_inventory.identity().destinations)
            self.assertFalse(placed.is_solved)
            if partial != source:
                self.assertTrue(result.placement_steps)
                self.assertTrue(result.placement_algorithms)

    def test_ordinary_valid_cubies_can_have_an_unreachable_block_permutation(self):
        shape = one_face_shapes()[2]
        solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        source = c.State.from_cubies(shape, corners=[1, 3, 2, 0, 4, 5, 6, 7],
                                    twists=[0] * 8, edges=list(range(12)), flips=[0] * 12)
        self.assertEqual(source.shape, shape)
        result = solver.solve(source)
        self.assertEqual((result.status, result.stop_reason),
                         ("unreachable", "block_permutation_not_in_group"))
        self.assertEqual(result.kernel_steps, ())
        self.assertIsNone(result.solution)

    def test_rigid_but_permanently_immobile_import_is_reported_unreachable(self):
        labels = [0] * 27
        for cell in (c.UFR, c.UR, c.UF, c.FR):
            labels[cell] = 1
        shape = c.Shape(labels)
        source = c.State.from_cubies(
            shape, corners=list(range(8)), twists=[1, 2] + [0] * 6,
            edges=[1, 8, 2, 3, 4, 5, 6, 7, 0, 9, 10, 11],
            flips=[1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0])
        self.assertEqual(source.shape, shape)
        solver = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        result = solver.solve(source)
        self.assertEqual((result.status, result.stop_reason),
                         ("unreachable", "kernel_residual_not_in_group"))

    def test_wrapper_selects_new_strategy_and_respects_prepared_strategy(self):
        shape = fused_face()
        source = imported(c.State(shape).apply("U2"))
        result = c.solve_colored_loops(source, factorization="quotient_kernel", timeout=30)
        self.assertEqual((result.status, result.factorization), ("solved", "quotient_kernel"))
        self.assertTrue(source.apply(result.solution).is_solved)
        prepared = c.LoopSolver(shape, factorization="quotient_kernel", timeout=30)
        result = c.solve_colored_loops(source, solver=prepared)
        self.assertEqual((result.status, result.factorization), ("solved", "quotient_kernel"))
        self.assertTrue(source.apply(result.solution).is_solved)

    def test_nonzero_reference_root_preserves_original_generator_ids(self):
        graph = c.explore(one_face_shapes()[1], metric="HTM")
        loops = graph.isotropy_loops(root=1)
        self.assertNotEqual(loops.root_shape, graph[0])
        analysis = loops.analyze(timeout=30)
        solver = c.LoopSolver(analysis, factorization="quotient_kernel", timeout=30)
        self.assertEqual(solver.specification, loops.root_shape)
        self.assertEqual(tuple(g.id for g in solver.generators), analysis.generator_ids)
        for moves in ("U", "U2", "U'"):
            source = imported(c.State(loops.root_shape).apply(moves))
            self.assert_staged_solution(solver, source)
        structure = c.analyze_block_structure(analysis, timeout=30)
        self.assertEqual((structure.group_order, structure.quotient_order, structure.kernel_order),
                         (2, 2, 1))
        self.assertEqual(structure.root_shape, loops.root_shape)
        self.assertEqual(structure.analysis.loops.root_vertex, 1)
        self.assertIs(c.analyze_block_structure(structure), structure)
        with self.assertRaises(ValueError):
            c.analyze_block_structure(analysis, root=0)
        with self.assertRaises(TypeError):
            c.analyze_block_structure(analysis, root=True)
        with self.assertRaises(ValueError):
            solver.solve(c.State(graph[0]))


if __name__ == "__main__":
    unittest.main()
