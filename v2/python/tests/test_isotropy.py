"""Witnessed loop extraction and exact algebra against small colored components."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import bce_v2 as c


def one_face_shapes():
    # Only U can turn. Distinguish four, two, and one geometric U positions.
    pair = [0] * 9 + [1] * 18
    pair[c.UBL] = pair[c.UB] = 2
    opposite_pairs = pair.copy()
    opposite_pairs[c.UFR] = opposite_pairs[c.UF] = 3
    return c.Shape(pair), c.Shape(opposite_pairs), c.Shape([0] * 9 + [1] * 18)


def inverse_images(images):
    inverse = [0] * len(images)
    for source, destination in enumerate(images):
        inverse[destination] = source
    return tuple(inverse)


class LoopExtractionTests(unittest.TestCase):
    def test_generator_display_combines_half_turns_in_both_directions(self):
        loops = c.isotropy_loops(c.fixture("Alcatraz"))
        generator = next(generator for generator in loops if generator.id == 142)
        self.assertIn("R R", generator.moves)
        self.assertIn("F' F'", generator.moves)
        self.assertEqual(generator.turn_sequence, "U' R U R2 F R F2 U F U'")
        self.assertEqual((generator.qtm_length, generator.htm_length), (12, 10))

    def test_named_witnesses_and_reductions_are_replayable(self):
        for name, vertices, arcs, candidates, generators in (
            ("Alcatraz", 1449, 2048, 600, 31),
            ("Bicube Fuse", 121, 168, 48, 3),
            ("Shark Fin Soup", 1938, 2968, 1031, 18),
        ):
            with self.subTest(name=name):
                shape = c.fixture(name)
                loops = c.isotropy_loops(shape)
                self.assertEqual((loops.shape_count, loops.arc_count, loops.candidate_count),
                                 (vertices, arcs, candidates))
                self.assertEqual(len(loops), generators)
                self.assertEqual(loops.root_shape, shape)
                self.assertEqual(loops.root_vertex, 0)
                signatures = set()
                for generator in loops:
                    replayed = c.State(shape).apply(generator.moves)
                    self.assertEqual(replayed.shape, shape)
                    self.assertEqual(replayed.sticker_permutation, generator.permutation)
                    displayed = c.State(shape).apply(generator.turn_sequence)
                    self.assertEqual(displayed, replayed)
                    self.assertEqual(generator.htm_length, len(generator.turn_sequence.split()))
                    self.assertEqual(sum(2 if move.endswith("2") else 1
                                         for move in generator.moves.split()), generator.qtm_length)
                    self.assertNotEqual(generator.permutation, tuple(range(48)))
                    self.assertNotIn(generator.permutation, signatures)
                    self.assertNotIn(inverse_images(generator.permutation), signatures)
                    signatures.add(generator.permutation)

    def test_small_fibers_include_identity_groups_and_block_exchange(self):
        for shape, expected_shapes, expected_group in zip(one_face_shapes(), (4, 2, 1), (1, 2, 4)):
            with self.subTest(shapes=expected_shapes):
                loops = c.isotropy_loops(shape)
                self.assertEqual(loops.shape_count, expected_shapes)
                self.assertEqual(loops.candidate_count, 1)
                colored = c.explore_colored(c.State(shape))
                self.assertTrue(colored.complete)
                self.assertEqual(len(colored), expected_shapes * expected_group)
                if expected_group == 1:
                    self.assertEqual(len(loops), 0)
                else:
                    self.assertEqual(len(loops), 1)

    def test_complete_htm_input_and_alternate_roots(self):
        shape = one_face_shapes()[0]
        qtm_graph = c.explore(shape)
        for metric in ("QTM", "HTM"):
            graph = c.explore(shape, metric=metric)
            for root in range(len(graph)):
                loops = graph.isotropy_loops(root)
                self.assertEqual(loops.root_shape, graph[root])
                self.assertEqual(loops.root_vertex, root)
                self.assertEqual((loops.arc_count, loops.candidate_count), (4, 1))
                for vertex in range(len(graph)):
                    witness = loops.transport(vertex)
                    self.assertEqual(graph[root].apply(witness), graph[vertex])
                    expected = qtm_graph.distances(graph[root])[qtm_graph.vertex_id(graph[vertex])]
                    self.assertEqual(len(witness.split()), expected)

    def test_reusing_loop_sets_preserves_or_checks_the_root(self):
        loops = c.isotropy_loops(one_face_shapes()[0], root=1)
        self.assertIs(c.isotropy_loops(loops), loops)
        self.assertIs(c.isotropy_loops(loops, root=1), loops)
        with self.assertRaises(ValueError):
            c.isotropy_loops(loops, root=0)
        with self.assertRaises(ValueError):
            c.analyze_isotropy(loops, root=0)
        for root in (True, 1.5, "0"):
            with self.subTest(root=root), self.assertRaises(TypeError):
                c.analyze_isotropy(loops, root=root)

    def test_state_input_uses_reference_membership(self):
        shape = one_face_shapes()[0]
        state = c.State(shape).apply("U")
        self.assertNotEqual(state.shape, shape)
        self.assertEqual(c.isotropy_loops(state).to_dict(), c.isotropy_loops(shape).to_dict())

    def test_frozen_and_unbandaged_graphs(self):
        frozen = c.isotropy_loops(c.Shape([1] * 27))
        self.assertEqual((frozen.shape_count, frozen.arc_count, frozen.candidate_count, len(frozen)),
                         (1, 0, 0, 0))
        ordinary = c.isotropy_loops(c.Shape())
        self.assertEqual((ordinary.shape_count, ordinary.arc_count, ordinary.candidate_count, len(ordinary)),
                         (1, 6, 6, 6))

    def test_exports_are_deterministic_with_explicit_permutation_conventions(self):
        loops = c.isotropy_loops(one_face_shapes()[1])
        record = loops.to_dict()
        self.assertEqual(record["format"], "bce-v2-isotropy-loops")
        self.assertTrue(record["complete"])
        self.assertEqual(record["symmetry"], "none")
        self.assertEqual(record["metric"], "QTM")
        self.assertEqual(record["permutation_degree"], 48)
        self.assertEqual(record["permutation_index_base"], 0)
        self.assertEqual(record["permutation_action"], "source-to-destination")
        self.assertIn("moves", record["generators"][0])
        self.assertEqual(record["generators"][0]["turn_sequence"], loops[0].turn_sequence)
        self.assertEqual(record["generators"][0]["htm_length"], loops[0].htm_length)
        self.assertNotIn("moves", loops.to_dict(include_moves=False)["generators"][0])
        self.assertNotIn("turn_sequence", loops.to_dict(include_moves=False)["generators"][0])
        self.assertNotIn("htm_length", loops.to_dict(include_moves=False)["generators"][0])
        self.assertEqual(json.loads(loops.to_json()), record)
        self.assertEqual(loops.to_json(), c.isotropy_loops(loops.root_shape).to_json())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loops.json"
            self.assertEqual(loops.save(path), record)
            self.assertEqual(path.read_text(), loops.to_json())

    def test_immutable_results_and_invalid_roots(self):
        loops = c.isotropy_loops(one_face_shapes()[1])
        with self.assertRaises(AttributeError):
            loops.root_vertex = 1
        with self.assertRaises(FrozenInstanceError):
            loops[0].id = 100
        for root in (-1, 2):
            with self.subTest(root=root), self.assertRaises(IndexError):
                c.isotropy_loops(loops.root_shape, root=root)
        for root in (True, 1.5, "0"):
            with self.subTest(root=root), self.assertRaises(TypeError):
                c.isotropy_loops(loops.root_shape, root=root)
        with self.assertRaises(IndexError):
            loops.transport(-1)
        with self.assertRaises(TypeError):
            loops.transport(True)
        partial = c.explore(one_face_shapes()[0], max_vertices=2)
        self.assertFalse(partial.complete)
        with self.assertRaisesRegex(ValueError, "complete"):
            c.isotropy_loops(partial)


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external dependency")
class GapIsotropyTests(unittest.TestCase):
    def test_exact_colored_count_matches_all_small_components(self):
        shapes = list(one_face_shapes()) + [c.Shape([1] * 27), c.Shape([0] * 9 + [1] * 9 + [0] * 9)]
        for shape, order in zip(shapes, (1, 2, 4, 1, 16)):
            with self.subTest(order=order, shape=shape):
                analysis = c.analyze_isotropy(shape)
                self.assertEqual(analysis.group_order, order)
                colored = c.explore_colored(c.State(shape))
                self.assertTrue(colored.complete)
                self.assertEqual(analysis.colored_state_count, len(colored))
                for generator in analysis.generators:
                    self.assertEqual(c.State(shape).apply(generator.moves).sticker_permutation,
                                     generator.permutation)
                self.assertTrue(set(analysis.generator_ids).issubset({g.id for g in analysis.loops}))
                record = analysis.to_dict()
                self.assertEqual(record["group_order"], str(order))
                self.assertEqual(record["colored_state_count"], str(len(colored)))
                self.assertEqual(json.loads(analysis.to_json()), record)
                with self.assertRaises(FrozenInstanceError):
                    analysis.group_order = 5

    def test_ordinary_cube_order_and_exact_json_precision(self):
        analysis = c.isotropy_loops(c.Shape()).analyze()
        self.assertEqual(analysis.group_order, 43_252_003_274_489_856_000)
        self.assertEqual(analysis.colored_state_count, analysis.group_order)
        self.assertEqual(json.loads(analysis.to_json())["group_order"], "43252003274489856000")


if __name__ == "__main__":
    unittest.main()
