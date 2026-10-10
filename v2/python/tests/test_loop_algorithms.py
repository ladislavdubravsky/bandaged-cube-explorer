"""Faithful, bounded discovery of readable loop constructions without GAP."""

from dataclasses import FrozenInstanceError
import json
from math import lcm
import re
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.loop_algorithms import _diverse_candidates, _mining_expressions


IDENTITY = tuple(range(48))


def expand_move_notation(text):
    """Independent tiny parser for rendered powers, commutators and conjugates."""
    position = 0

    def skip_spaces():
        nonlocal position
        while position < len(text) and text[position].isspace():
            position += 1

    def inverse(word):
        return [move if move.endswith("2") else move[:-1] if move.endswith("'")
                else move + "'" for move in reversed(word)]

    def sequence(stops):
        result = []
        while True:
            skip_spaces()
            if position >= len(text) or text[position] in stops:
                return result
            result.extend(atom())

    def atom():
        nonlocal position
        symbol = text[position]
        if symbol in "URFDLBxyz":
            match = re.match(r"[URFDLBxyz](?:2|')?", text[position:])
            position += len(match.group())
            return [match.group()]
        if symbol == "(":
            position += 1
            word = sequence(")")
            if position >= len(text) or text[position] != ")":
                raise ValueError("unterminated move group")
            position += 1
        elif symbol == "[":
            position += 1
            first = sequence(",:")
            if position >= len(text) or text[position] not in ",:":
                raise ValueError("missing commutator or conjugate separator")
            operation = text[position]
            position += 1
            second = sequence("]")
            if position >= len(text) or text[position] != "]":
                raise ValueError("unterminated move construction")
            position += 1
            word = first + second + inverse(first)
            if operation == ",":
                word += inverse(second)
        else:
            raise ValueError(f"unexpected move notation at {position}: {text!r}")
        exponent = 1
        if position < len(text) and text[position].isdigit():
            match = re.match(r"\d+", text[position:])
            exponent = int(match.group())
            position += len(match.group())
        return word * exponent

    moves = sequence("")
    skip_spaces()
    if position != len(text):
        raise ValueError("trailing move notation")
    # Regrips change the frame in which following face letters are read.
    # These explicit maps are independent of the implementation geometry.
    frame = dict(zip("URFDLB", "URFDLB"))
    rotations = {"x": dict(zip("URFDLB", "FRDBLU")),
                 "y": dict(zip("URFDLB", "UBRDFL")),
                 "z": dict(zip("URFDLB", "LUFRDB"))}
    result = []
    for move in moves:
        if move[0] in rotations:
            amount = 2 if move.endswith("2") else 3 if move.endswith("'") else 1
            for _ in range(amount):
                frame = {face: frame[rotations[move[0]][face]] for face in frame}
        else:
            result.append(frame[move[0]] + move[1:])
    if frame != dict(zip("URFDLB", "URFDLB")):
        raise ValueError("move display leaves an unbalanced regrip")
    return " ".join(result)


def independent_faces():
    return c.Shape([0] * 9 + [1] * 9 + [0] * 9)


def inverse_moves(word):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(word.split()))


def replay_expression(loops, expression):
    def has_rotation(node):
        return node.kind == "rotated" or any(has_rotation(child) for child in node.children)

    if has_rotation(expression):
        return c.State(loops.root_shape).apply(expression.expanded_moves(loops))
    by_id = {generator.id: generator for generator in loops}
    state = c.State(loops.root_shape)
    for identifier, exponent in expression.loop_steps():
        word = by_id[identifier].moves
        if exponent < 0:
            word = inverse_moves(word)
        for _ in range(abs(exponent)):
            state = state.apply(word)
    return state


def leaf_for(loops, move):
    return c.LoopExpression.loop(next(generator.id for generator in loops
                                      if generator.moves == move))


def by_effect(algorithms, permutation):
    return next(algorithm for algorithm in algorithms if algorithm.permutation == permutation)


class LoopExpressionTests(unittest.TestCase):
    def setUp(self):
        self.loops = c.isotropy_loops(c.Shape())
        self.r = leaf_for(self.loops, "R")
        self.u = leaf_for(self.loops, "U")

    def assert_expression(self, expression, moves):
        expected = c.State().apply(moves)
        self.assertEqual(expression.evaluate(self.loops), expected.sticker_permutation)
        self.assertEqual(replay_expression(self.loops, expression), expected)
        self.assertEqual(c.State().apply(expression.expanded_moves(self.loops)), expected)
        self.assertEqual(c.State().apply(expand_move_notation(expression.render_moves(self.loops))), expected)
        self.assertEqual(json.loads(json.dumps(expression.to_dict())), expression.to_dict())

    def test_noncommuting_commutator_and_nested_conjugate_execute_in_written_order(self):
        self.assertNotEqual(c.State().apply("R U"), c.State().apply("U R"))
        commutator = c.LoopExpression.commutator(self.r, self.u)
        self.assert_expression(commutator, "R U R' U'")
        self.assertNotEqual(commutator.evaluate(self.loops), IDENTITY)
        self.assertIn("[", commutator.render())
        nested = c.LoopExpression.conjugate(
            self.u, c.LoopExpression.conjugate(self.r, commutator))
        self.assert_expression(nested, "U R R U R' U' R' U'")
        inverse = c.LoopExpression.power(commutator, -2)
        self.assert_expression(inverse, "U R U' R' U R U' R'")
        self.assertEqual(str(nested), nested.render())

    def test_sequences_and_powers_retain_compact_original_loop_provenance(self):
        expression = c.LoopExpression.sequence(self.r, self.r, self.u,
                                                c.LoopExpression.power(self.u, -1))
        self.assert_expression(expression, "R2")
        self.assertEqual(expression.loop_steps(), ((self.r.generator_id, 2),))
        self.assertEqual(c.LoopExpression.sequence().evaluate(self.loops), IDENTITY)
        self.assertEqual(c.LoopExpression.power(self.r, 0).loop_steps(), ())
        large = c.LoopExpression.power(c.LoopExpression.sequence(self.r, self.u), 1_000_000)
        self.assertEqual(len(large.evaluate(self.loops)), 48)
        with self.assertRaises(ValueError):
            large.loop_steps(max_syllables=4)
        with self.assertRaises(FrozenInstanceError):
            expression.kind = "loop"

    def test_actual_move_rendering_preserves_structure_and_canonical_face_powers(self):
        expression = c.LoopExpression.power(c.LoopExpression.sequence(self.r, self.u), 3)
        self.assertEqual(expression.render_moves(self.loops), "(R U)3")
        self.assertEqual(expression.render(), f"(L{self.r.generator_id} L{self.u.generator_id})^3")
        commutator = c.LoopExpression.commutator(self.r, self.u)
        self.assertEqual(commutator.render_moves(self.loops), "[R, U]")
        nested = c.LoopExpression.conjugate(self.r,
                                           c.LoopExpression.conjugate(self.u, commutator))
        self.assertEqual(nested.render_moves(self.loops), "[R: [U: [R, U]]]")
        self.assert_expression(nested, "R U R U R' U' U' R'")
        body = c.LoopExpression.sequence(self.r, self.u)
        self.assertEqual(c.LoopExpression.power(body, -1).render_moves(self.loops), "U' R'")
        self.assertEqual(c.LoopExpression.power(body, -2).render_moves(self.loops), "(U' R')2")
        self.assertEqual(c.LoopExpression.power(body, -3).render_moves(self.loops), "(U' R')3")
        self.assertEqual(c.LoopExpression.power(commutator, -1).render_moves(self.loops), "[U, R]")
        conjugate = c.LoopExpression.conjugate(self.r, commutator)
        self.assertEqual(c.LoopExpression.power(conjugate, -1).render_moves(self.loops),
                         "[R: [U, R]]")
        negative = c.LoopExpression.power(c.LoopExpression.power(body, -2), -3)
        self.assertEqual(negative.render_moves(self.loops), "(R U)6")
        inverse_repeat = c.LoopExpression.power(c.LoopExpression.power(body, 2), -3)
        self.assertEqual(inverse_repeat.render_moves(self.loops), "(U' R')6")
        for expression in (negative, inverse_repeat, c.LoopExpression.power(conjugate, -1)):
            self.assertEqual(c.State().apply(expand_move_notation(expression.render_moves(self.loops))),
                             replay_expression(self.loops, expression))
        for exponent, rendered in ((2, "R2"), (-2, "R2"), (-1, "R'"), (3, "R'"), (4, "()")):
            with self.subTest(exponent=exponent):
                power = c.LoopExpression.power(self.r, exponent)
                self.assertEqual(power.render_moves(self.loops), rendered)
                self.assertEqual(c.State().apply(expand_move_notation(rendered)),
                                 replay_expression(self.loops, power))
        inverse = c.LoopExpression.power(self.r, -1)
        self.assertEqual(c.LoopExpression.power(inverse, 2).render_moves(self.loops), "R2")
        literal = c.LoopExpression.turns("R U R' U'", commutator)
        sequence = c.LoopExpression.sequence(literal, self.r)
        self.assertEqual(sequence.render_moves(self.loops), "R U R' U' R")
        self.assert_expression(sequence, "R U R' U' R")
        self.assertEqual(c.LoopExpression.sequence().render_moves(()), "()")
        with self.assertRaises(ValueError):
            c.LoopExpression.loop(999_999).render_moves(self.loops)

    def test_rotated_expressions_preserve_frame_and_reuse_the_original_algorithm(self):
        body = c.LoopExpression.commutator(self.r, self.u)
        rotated = c.LoopExpression.rotated("x", body)
        self.assertEqual(rotated.render_moves(self.loops), "x ([R, U]) x'")
        self.assertEqual(rotated.expanded_moves(self.loops), "R F R' F'")
        self.assert_expression(rotated, "R F R' F'")
        self.assertEqual(rotated.base_ids, body.base_ids)
        self.assertEqual(rotated.memory_keys, body.memory_keys)
        self.assertEqual(rotated.structure_cost(self.loops), body.structure_cost(self.loops))
        reused = c.LoopExpression.sequence(body, rotated)
        self.assertEqual(reused.memory_keys, body.memory_keys)
        self.assert_expression(reused, "R U R' U' R F R' F'")
        with self.assertRaisesRegex(ValueError, "rotation.*expanded_moves"):
            rotated.loop_steps()

        nested = c.LoopExpression.rotated("x", c.LoopExpression.rotated("y", self.r))
        self.assertEqual(nested, c.LoopExpression.rotated("x y", self.r))
        self.assertEqual(nested.children, (self.r,))
        self.assert_expression(nested, "U")
        doubled = c.LoopExpression.rotated("x", rotated)
        self.assertEqual(doubled.rotation, "x2")
        self.assertEqual(doubled.children, (body,))
        self.assertEqual(doubled.render_moves(self.loops), "x2 ([R, U]) x2")
        self.assert_expression(doubled, "R D R' D'")
        canceled = c.LoopExpression.rotated("x'", rotated)
        self.assertIs(canceled, body)
        self.assertEqual(canceled.loop_steps(), body.loop_steps())
        self.assertIs(c.LoopExpression.rotated("x x x x", body), body)
        self.assertIs(c.LoopExpression.rotated("", body), body)
        inverse = c.LoopExpression.power(rotated, -1)
        self.assert_expression(inverse, "F R F' R'")
        self.assertEqual(inverse.render_moves(self.loops), "x ([U, R]) x'")
        self.assertEqual(rotated.to_dict()["rotation"], "x")
        with self.assertRaises(ValueError):
            c.LoopExpression.power(rotated, 3).expanded_moves(self.loops, max_expanded_moves=8)

    def test_invalid_expression_inputs_and_unknown_original_ids_are_rejected(self):
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                c.LoopExpression.loop(value)
            with self.subTest(exponent=value), self.assertRaises(TypeError):
                c.LoopExpression.power(self.r, value)
        with self.assertRaises(ValueError):
            c.LoopExpression.loop(-1)
        with self.assertRaises(TypeError):
            c.LoopExpression.sequence(self.r, None)
        with self.assertRaises(ValueError):
            c.LoopExpression.loop(999_999).evaluate(self.loops)


class LoopAlgorithmDiscoveryTests(unittest.TestCase):
    def assert_algorithm(self, library, algorithm):
        expected = replay_expression(library.loops, algorithm.expression)
        self.assertEqual(algorithm.permutation, expected.sticker_permutation)
        self.assertEqual(c.State(library.loops.root_shape).apply(algorithm.turn_sequence), expected)
        self.assertEqual(algorithm.moves, algorithm.turn_sequence)
        self.assertEqual(algorithm.structured_turn_sequence,
                         algorithm.expression.render_moves(library.loops))
        rendered = expand_move_notation(algorithm.structured_turn_sequence)
        self.assertEqual(c.State(library.loops.root_shape).apply(rendered), expected)
        self.assertEqual(algorithm.to_dict()["structured_turn_sequence"], algorithm.structured_turn_sequence)
        self.assertEqual(algorithm.htm_length, len(algorithm.turn_sequence.split()))
        self.assertEqual(algorithm.qtm_length,
                         sum(2 if move.endswith("2") else 1
                             for move in algorithm.turn_sequence.split()))
        action = algorithm.block_action
        self.assertEqual(action.permutation, algorithm.permutation)
        self.assertEqual(algorithm.support,
                         tuple(index for index, (destination, phase) in
                               enumerate(zip(action.destinations, action.phases))
                               if destination != index or phase))
        self.assertEqual(algorithm.is_kernel,
                         action.destinations == library.loops.block_inventory.identity().destinations)
        self.assertEqual(algorithm.base_ids, algorithm.expression.base_ids)
        self.assertIsInstance(algorithm.structure_score, tuple)

    def test_localized_effect_ranks_before_a_shorter_large_effect_algorithm(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        r, u = leaf_for(loops, "R"), leaf_for(loops, "U")
        face_turn = library.build_algorithm(r)
        localized = library.build_algorithm(c.LoopExpression.power(
            c.LoopExpression.commutator(r, u), 3))
        self.assert_algorithm(library, face_turn)
        self.assert_algorithm(library, localized)
        self.assertEqual((face_turn.htm_length, len(face_turn.support)), (1, 8))
        self.assertEqual((localized.htm_length, len(localized.support)), (12, 4))
        self.assertTrue(all(loops.block_inventory.blocks[index].kind == "Corner"
                            for index in localized.support))
        state = c.State().apply(localized.turn_sequence)
        self.assertEqual(state.edges, list(range(12)))
        self.assertEqual(state.flips, [0] * 12)
        self.assertLess(localized.structure_score, face_turn.structure_score)

    def test_inverse_is_not_extra_structure_and_long_literal_reuse_has_no_six_turn_cliff(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        r, u = leaf_for(loops, "R"), leaf_for(loops, "U")
        body = c.LoopExpression.commutator(r, u)
        direct = library.build_algorithm(body)
        inverse = library.build_algorithm(c.LoopExpression.power(body, -1))
        self.assertEqual(body.structure_cost(loops), inverse.expression.structure_cost(loops))
        self.assertEqual(direct.structure_score, inverse.structure_score)
        for exponent in (2, 3):
            positive = library.build_algorithm(c.LoopExpression.power(body, exponent))
            negative = library.build_algorithm(c.LoopExpression.power(body, -exponent))
            self.assertEqual(positive.structure_score, negative.structure_score)
            self.assert_algorithm(library, negative)

        literals = []
        for length in (5, 6, 7, 8):
            leaves = tuple(r if index % 2 == 0 else u for index in range(length))
            witness = c.LoopExpression.sequence(*leaves)
            word = " ".join("R" if index % 2 == 0 else "U" for index in range(length))
            literal = c.LoopExpression.turns(word, witness)
            self.assert_algorithm(library, library.build_algorithm(literal))
            literals.append(literal)
        costs = [literal.structure_cost(loops) for literal in literals]
        increments = [after - before for before, after in zip(costs, costs[1:])]
        self.assertTrue(all(increment > 0 for increment in increments))
        self.assertEqual(len(set(increments)), 1)
        long_leaf = literals[-1]
        repeated = c.LoopExpression.power(long_leaf, 3)
        self.assertEqual(repeated.memory_keys, long_leaf.memory_keys)
        self.assertLess(repeated.structure_cost(loops), 3 * long_leaf.structure_cost(loops))

    def test_rotated_algorithm_building_requires_an_actual_reference_symmetry(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        body = c.LoopExpression.commutator(leaf_for(loops, "R"), leaf_for(loops, "U"))
        expression = c.LoopExpression.rotated("x", body)
        algorithm = library.build_algorithm(expression)
        self.assert_algorithm(library, algorithm)
        self.assertEqual(algorithm.turn_sequence, "R F R' F'")
        self.assertEqual((algorithm.htm_length, algorithm.qtm_length), (4, 4))
        self.assertNotRegex(algorithm.moves, "[xyz]")
        self.assertEqual(algorithm.expression.memory_keys, body.memory_keys)
        self.assertEqual(json.loads(json.dumps(algorithm.to_dict())), algorithm.to_dict())

        asymmetric = c.isotropy_loops(c.Shape([0] * 9 + [1] * 18))
        other = c.discover_loop_algorithms(asymmetric, rounds=0, max_candidates=8,
                                           max_algorithms=8)
        u = leaf_for(asymmetric, "U")
        accepted = other.build_algorithm(c.LoopExpression.rotated("y", u))
        self.assert_algorithm(other, accepted)
        self.assertEqual(accepted.turn_sequence, "U")
        with self.assertRaisesRegex(ValueError, "preserve"):
            other.build_algorithm(c.LoopExpression.rotated("x", u))
        with self.assertRaisesRegex(ValueError, "preserve"):
            other.build_algorithm(c.LoopExpression.rotated("x", c.LoopExpression.sequence()))

    def test_discovery_evaluates_and_retains_transfers_only_for_symmetric_bandages(self):
        loops = c.isotropy_loops(independent_faces())
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("discovery called GAP")):
            symmetric = c.discover_loop_algorithms(
                loops, max_seed_loops=1, rounds=1, max_candidates=32,
                max_algorithms=32, max_htm_length=8)
            asymmetric = c.discover_loop_algorithms(
                c.fixture("Alcatraz"), max_seed_loops=1, rounds=1,
                max_candidates=32, max_algorithms=32, max_htm_length=40)
        self.assertGreater(symmetric.symmetry_count, 0)
        self.assertGreater(symmetric.symmetry_transfer_count, 0)
        self.assertEqual(symmetric.metadata["symmetry_transfer_count"],
                         symmetric.symmetry_transfer_count)
        transfers = tuple(algorithm for algorithm in symmetric.algorithms
                          if algorithm.expression.kind == "rotated")
        self.assertTrue(transfers)
        # Only U was seeded; D is supplied by a genuine spatial transfer,
        # while the complete original loop set remains available separately.
        self.assertEqual(loops.generators[0].moves, "U")
        destination_effect = c.State(loops.root_shape).apply("D").sticker_permutation
        self.assertIn(destination_effect, {algorithm.permutation for algorithm in transfers})
        transferred_d = next(algorithm for algorithm in transfers
                             if algorithm.permutation == destination_effect)
        self.assertEqual(transferred_d.expression.rotation, "x2")
        for algorithm in transfers:
            self.assertEqual(algorithm.base_ids, (loops.generators[0].id,))
            self.assert_algorithm(symmetric, algorithm)
        self.assertEqual(tuple(symmetric.loops), tuple(loops))
        self.assertEqual(asymmetric.symmetry_count, 0)
        self.assertEqual(asymmetric.symmetry_transfer_count, 0)
        self.assertFalse(any(algorithm.expression.kind == "rotated"
                             for algorithm in asymmetric.algorithms))

    def test_alcatraz_l142_powers_isolate_real_corner_and_edge_orientations(self):
        loops = c.isotropy_loops(c.fixture("Alcatraz"))
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("discovery called GAP")):
            library = c.discover_loop_algorithms(loops, rounds=1, max_candidates=64,
                                                 max_algorithms=64, max_htm_length=40)
            leaf = c.LoopExpression.loop(142)
            for exponent, affected in ((2, {(c.UFR,), (c.UFL,), (c.UBR,)}),
                                       (3, {(c.UR,), (c.UF,)})):
                with self.subTest(exponent=exponent):
                    algorithm = library.build_algorithm(c.LoopExpression.power(leaf, exponent))
                    self.assert_algorithm(library, algorithm)
                    self.assertIn(algorithm.permutation, {a.permutation for a in library.algorithms})
                    self.assertTrue(algorithm.is_kernel)
                    self.assertEqual({loops.block_inventory.blocks[index].cells
                                      for index in algorithm.support}, affected)
                    self.assertTrue(all(algorithm.block_action.phases[index]
                                        for index in algorithm.support))

    def test_fifth_and_seventh_powers_isolate_components_of_a_real_order_35_macro(self):
        loops = c.isotropy_loops(c.Shape())
        r, u = leaf_for(loops, "R"), leaf_for(loops, "U")
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        expression = c.LoopExpression.power(c.LoopExpression.sequence(r, u), 3)
        macro = library.build_algorithm(expression)
        seen, order = set(), 1
        for point in range(48):
            if point in seen:
                continue
            length = 0
            while point not in seen:
                seen.add(point)
                length += 1
                point = macro.permutation[point]
            order = lcm(order, length)
        self.assertEqual(order, 35)
        proposals = tuple(_mining_expressions((macro,)))
        for exponent, kind, count in ((5, "Edge", 7), (7, "Corner", 5)):
            with self.subTest(exponent=exponent):
                expected = c.State().apply(" ".join(["R U"] * (3 * exponent)))
                proposal = next((p for p in proposals if p.evaluate(loops) == expected.sticker_permutation),
                                None)
                self.assertIsNotNone(proposal, "discovery omitted the isolating divisor power")
                isolated = library.build_algorithm(proposal)
                self.assert_algorithm(library, isolated)
                self.assertEqual(len(isolated.support), count)
                self.assertEqual({loops.block_inventory.blocks[i].kind for i in isolated.support}, {kind})
                if kind == "Edge":
                    self.assertEqual(expected.corners, list(range(8)))
                    self.assertEqual(expected.twists, [0] * 8)
                else:
                    self.assertEqual(expected.edges, list(range(12)))
                    self.assertEqual(expected.flips, [0] * 12)

    def test_inverse_and_mixed_sign_commutators_are_distinct_proposals(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        r, u = (library.build_algorithm(leaf_for(loops, move)) for move in ("R", "U"))
        proposals = tuple(_mining_expressions((r, u)))
        expected = (
            c.LoopExpression.power(r.expression, -1),
            c.LoopExpression.commutator(r.expression, c.LoopExpression.power(u.expression, -1)),
            c.LoopExpression.commutator(c.LoopExpression.power(r.expression, -1), u.expression),
        )
        swapped = c.LoopExpression.commutator(u.expression, r.expression).evaluate(loops)
        for expression in expected:
            with self.subTest(expression=expression.render()):
                self.assertIn(expression, proposals)
                algorithm = library.build_algorithm(expression)
                self.assert_algorithm(library, algorithm)
                if expression.kind == "commutator":
                    self.assertNotEqual(algorithm.permutation, swapped)

    def test_frontier_reserves_corner_edge_and_orientation_families(self):
        loops = c.isotropy_loops(c.Shape())
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        u, r, f, d = (leaf_for(loops, move) for move in ("U", "R", "F", "D"))
        edge = library.build_algorithm(c.LoopExpression.commutator(
            c.LoopExpression.commutator(u, r), c.LoopExpression.commutator(f, d)))

        def word_algorithm(word):
            return library.build_algorithm(c.LoopExpression.sequence(*(
                c.LoopExpression.power(leaf_for(loops, move[0]),
                                       -1 if move.endswith("'") else 2 if move.endswith("2") else 1)
                for move in word.split())))

        corner = word_algorithm("B U F U' B' U F' U'")
        twist = word_algorithm("B D B' U B D' B' L U R U' L' U R' U2")
        candidates = [library.build_algorithm(c.LoopExpression.rotated(rotation, corner.expression))
                      for rotation in ("", "x", "y", "z", "x2", "y2", "z2")]
        candidates.extend((edge, twist, library.build_algorithm(u)))
        frontier = tuple(_diverse_candidates(candidates))[:4]
        families = {(algorithm.is_kernel,
                     frozenset(loops.block_inventory.blocks[i].kind for i in algorithm.support))
                    for algorithm in frontier}
        self.assertEqual(families, {(False, frozenset({"Corner"})),
                                    (False, frozenset({"Edge"})),
                                    (False, frozenset({"Corner", "Edge"})),
                                    (True, frozenset({"Corner"}))})

    def test_unbandaged_discovery_finds_orientation_algorithms_before_method_compilation(self):
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("discovery called GAP")):
            library = c.discover_loop_algorithms(c.Shape(), rounds=3, max_candidates=1800,
                                                 max_algorithms=256)
        self.assertGreater(library.collision_proposal_count, 0)
        self.assertGreater(library.inverse_proposal_count, 0)
        self.assertLessEqual(library.examined_count, 1800)
        self.assertEqual(library.metadata["collision_proposal_count"],
                         library.collision_proposal_count)
        for kind in ("Corner", "Edge"):
            candidates = [algorithm for algorithm in library.shortest
                          if algorithm.is_kernel and len(algorithm.support) == 2
                          and {library.loops.block_inventory.blocks[i].kind
                               for i in algorithm.support} == {kind}]
            self.assertTrue(candidates, f"discovery omitted pure two-{kind.lower()} orientation effects")
            algorithm = min(candidates, key=lambda candidate: candidate.htm_length)
            self.assertEqual(algorithm.block_action.destinations,
                             tuple(range(len(library.loops.block_inventory.blocks))))
            self.assert_algorithm(library, algorithm)

    def test_distinct_short_and_structured_representatives_of_one_exact_effect(self):
        loops = c.isotropy_loops(independent_faces())
        u, d = leaf_for(loops, "U"), leaf_for(loops, "D")
        localized = c.LoopExpression.sequence(u, d, u, d)
        short = c.LoopExpression.turns("U2 D2", localized)
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=32,
                                             max_algorithms=16).with_expressions(short, localized)
        effect = c.State(loops.root_shape).apply("U2 D2").sticker_permutation
        shortest = by_effect(library.shortest, effect)
        structured = by_effect(library.structured, effect)
        self.assertEqual((shortest.htm_length, structured.htm_length), (2, 4))
        self.assertEqual(shortest.expression, short)
        self.assertEqual(structured.expression, localized)
        self.assertLess(structured.structure_score, shortest.structure_score)
        self.assertNotEqual(shortest.id, structured.id)
        self.assert_algorithm(library, shortest)
        self.assert_algorithm(library, structured)
        self.assertIn(shortest, library.algorithms)
        self.assertIn(structured, library.algorithms)

    def test_literal_short_turns_replay_the_declaration_and_keep_a_verified_witness(self):
        loops = c.isotropy_loops(independent_faces())
        u, d = leaf_for(loops, "U"), leaf_for(loops, "D")
        witness = c.LoopExpression.power(c.LoopExpression.sequence(u, d), 2)
        literal = c.LoopExpression.turns("U2 D2", witness)
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=32,
                                             max_algorithms=16)
        algorithm = library.build_algorithm(literal)
        self.assertEqual(algorithm.turn_sequence, "U2 D2")
        self.assertEqual(algorithm.htm_length, 2)
        self.assertEqual(literal.loop_steps(), witness.loop_steps())
        self.assert_algorithm(library, algorithm)
        with self.assertRaises(ValueError):
            library.build_algorithm(c.LoopExpression.turns("U", witness))
        one_face = c.isotropy_loops(c.Shape([0] * 9 + [1] * 18))
        constrained = c.discover_loop_algorithms(one_face, rounds=0, max_candidates=8,
                                                 max_algorithms=8)
        with self.assertRaises(ValueError):
            constrained.build_algorithm(c.LoopExpression.turns("R", leaf_for(one_face, "U")))

    def test_conjugated_commutator_of_two_literal_four_turn_algorithms(self):
        loops = c.isotropy_loops(c.Shape())
        r, u, f, d = (leaf_for(loops, move) for move in ("R", "U", "F", "D"))
        first_word, second_word = "R U R' U'", "F D F' D'"
        first_witness = c.LoopExpression.commutator(r, u)
        second_witness = c.LoopExpression.commutator(f, d)
        first = c.LoopExpression.turns(first_word, first_witness)
        second = c.LoopExpression.turns(second_word, second_witness)
        expression = c.LoopExpression.conjugate(r, c.LoopExpression.commutator(first, second))
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        algorithm = library.build_algorithm(expression)
        expected = " ".join(("R", first_word, second_word, inverse_moves(first_word),
                             inverse_moves(second_word), "R'"))
        self.assertEqual(algorithm.permutation, c.State().apply(expected).sticker_permutation)
        self.assertNotEqual(algorithm.permutation, IDENTITY)
        self.assert_algorithm(library, algorithm)
        self.assertIn("conj(", expression.render())
        self.assertIn("[{R U R' U'}, {F D F' D'}]", expression.render())
        self.assertEqual(len(expression.memory_keys), 3)
        self.assertEqual(len(expression.base_ids), 4)
        self.assertEqual({key for key in expression.memory_keys if key[0] == "loop"},
                         {("loop", r.generator_id)})
        self.assertLess(first.structure_cost(loops), first_witness.structure_cost(loops))
        self.assertLess(second.structure_cost(loops), second_witness.structure_cost(loops))

    def test_bounded_discovery_is_deterministic_and_needs_no_gap(self):
        limits = dict(max_seed_loops=4, rounds=2, max_candidates=64,
                      max_algorithms=16, max_htm_length=12)
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("discovery called GAP")):
            first = c.discover_loop_algorithms(c.Shape(), **limits)
            second = c.discover_loop_algorithms(first.loops, **limits)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertLessEqual(first.examined_count, limits["max_candidates"])
        self.assertLessEqual(first.seed_count, limits["max_seed_loops"])
        self.assertLessEqual(len(first.algorithms), limits["max_algorithms"])
        self.assertLessEqual(first.rounds_completed, limits["rounds"])
        self.assertEqual({a.permutation for a in first.shortest},
                         {a.permutation for a in first.structured})
        self.assertEqual(len({a.id for a in first.algorithms}), len(first.algorithms))
        original_effects = {g.permutation for g in first.loops}
        self.assertTrue(any(a.permutation not in original_effects for a in first.algorithms))
        for algorithm in first.algorithms:
            self.assertLessEqual(algorithm.htm_length, limits["max_htm_length"])
            self.assert_algorithm(first, algorithm)
        self.assertEqual(json.loads(first.to_json()), first.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.algorithms = ()
        with self.assertRaises(FrozenInstanceError):
            first.algorithms[0].turn_sequence = ""

    def test_inputs_preserve_nonzero_reference_roots_and_complete_original_loops(self):
        labels = [0] * 9 + [1] * 18
        labels[c.UBL] = labels[c.UB] = 2
        labels[c.UFR] = labels[c.UF] = 3
        graph = c.explore(labels)
        loops = graph.isotropy_loops(root=1)
        analysis = c.IsotropyAnalysis(loops, 2, tuple(g.id for g in loops), "test")
        solver = c.LoopSolver(analysis)
        with patch("bce_v2.gap_backend._run_gap", side_effect=AssertionError("discovery called GAP")):
            for initial in (loops, analysis, solver):
                library = c.discover_loop_algorithms(initial, rounds=0, max_seed_loops=1,
                                                      max_candidates=8, max_algorithms=8)
                self.assertEqual(library.loops.root_shape, graph[1])
                self.assertEqual(library.loops.root_vertex, 1)
                self.assertEqual(tuple(g.id for g in library.loops), tuple(g.id for g in loops))
                for algorithm in library.algorithms:
                    self.assert_algorithm(library, algorithm)

    def test_discovery_and_custom_expansion_limits_validate_inputs(self):
        loops = c.isotropy_loops(c.Shape())
        for option in ("max_seed_loops", "max_candidates", "max_algorithms", "max_htm_length"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                c.discover_loop_algorithms(loops, **{option: 0})
        with self.assertRaises(ValueError):
            c.discover_loop_algorithms(loops, rounds=-1)
        for option in ("max_seed_loops", "rounds", "max_candidates", "max_algorithms", "max_htm_length"):
            with self.subTest(option=option), self.assertRaises(TypeError):
                c.discover_loop_algorithms(loops, **{option: True})
        library = c.discover_loop_algorithms(loops, rounds=0, max_candidates=16,
                                             max_algorithms=16)
        large = c.LoopExpression.power(c.LoopExpression.sequence(leaf_for(loops, "R"),
                                                               leaf_for(loops, "U")), 100)
        with self.assertRaises(ValueError):
            library.build_algorithm(large, max_expanded_moves=8)
        with self.assertRaises(ValueError):
            library.build_algorithm(c.LoopExpression.loop(999_999))

    def test_discovery_tightens_expansion_budget_before_building_candidates(self):
        library = c.discover_loop_algorithms(c.Shape(), rounds=2, max_candidates=100,
                                             max_htm_length=120, max_expanded_moves=1)
        self.assertEqual(library.max_expanded_moves, 1)
        self.assertGreater(library.expansion_pruned_count, 0)
        self.assertTrue(library.algorithms)
        self.assertTrue(all(algorithm.htm_length == 1 for algorithm in library.algorithms))
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                c.discover_loop_algorithms(library.loops, max_expanded_moves=bad)
        with self.assertRaises(TypeError):
            c.discover_loop_algorithms(library.loops, max_expanded_moves=True)


if __name__ == "__main__":
    unittest.main()
