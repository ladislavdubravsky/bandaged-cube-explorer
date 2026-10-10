"""Open path endpoints, faithful actions and loop certificates stay distinct."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

import bce_v2 as c
from bce_v2.block_actions import _CELL_IMAGES
from bce_v2.human_witnesses import stored_loop_generators
from bce_v2.loop_rotations import (
    bandage_symmetries, inverse_rotation, rotation_tuple,
)
from bce_v2.shape_paths import ShapePath


IDENTITY = tuple(range(48))


def partition(reference):
    groups = {}
    for cell, label in enumerate(reference):
        groups.setdefault(label, set()).add(cell)
    return frozenset(frozenset(cells) for cells in groups.values())


class ShapePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = c.fixture("Bicube Fuse")
        cls.graph = c.explore(cls.root)
        cls.loops = c.isotropy_loops(cls.graph)

    def test_open_path_replays_and_keeps_immutable_exact_endpoints(self):
        path = ShapePath.from_moves(self.root.labels, " U U ")
        replay = c.State(self.root).apply("U U")
        self.assertEqual(path.moves, "U2")
        self.assertEqual(path.htm_length, 1)
        self.assertEqual(path.qtm_length, 2)
        self.assertEqual(path.source_shape, self.root)
        self.assertEqual(path.target_shape, replay.shape)
        self.assertEqual(path.permutation, replay.sticker_permutation)
        self.assertFalse(path.is_closed)
        with self.assertRaises(FrozenInstanceError):
            path.moves = ""
        source_labels = path.source_shape.labels
        source_labels[0] = 999
        self.assertEqual(path.source_shape, self.root)

    def test_composition_and_inverse_have_the_execution_order_action(self):
        first = ShapePath.from_moves(self.root, "U")
        second = ShapePath.from_moves(first.target_shape, "F")
        total = first.then(second)
        expected = c.State(self.root).apply("U F")
        self.assertEqual(total.target_shape, expected.shape)
        self.assertEqual(total.permutation, expected.sticker_permutation)
        self.assertEqual(total.permutation,
                         tuple(second.permutation[p] for p in first.permutation))
        inverse = total.inverse()
        self.assertEqual(inverse.source_shape, total.target_shape)
        self.assertEqual(inverse.target_shape, total.source_shape)
        round_trip = total.then(inverse)
        self.assertTrue(round_trip.is_closed)
        self.assertEqual(round_trip.moves, "")
        self.assertEqual(round_trip.permutation, IDENTITY)
        self.assertEqual(inverse.inverse(), total)

    def test_shape_and_frame_mismatches_cannot_silently_compose(self):
        path = ShapePath.from_moves(self.root, "U")
        with self.assertRaisesRegex(ValueError, "endpoint"):
            path.then(ShapePath.identity(self.root))
        same_physical_shape = ShapePath.identity(path.target_shape, frame="x")
        with self.assertRaisesRegex(ValueError, "frames"):
            path.then(same_physical_shape)
        self.assertEqual(path.then(same_physical_shape.reframed("")), path)
        with self.assertRaises(TypeError):
            path.then("U'")
        # Same motion class does not imply the same physical endpoint.
        different_shape = next(s for s in self.graph if s != path.target_shape
                               and s.rotation_key == path.target_shape.rotation_key)
        with self.assertRaisesRegex(ValueError, "endpoint"):
            path.then(ShapePath.identity(different_shape))

    def test_all_proper_regrips_rotate_both_endpoints_by_inverse_spatial_action(self):
        path = ShapePath.from_moves(self.root, "U F", frame="z")
        orientations = ("",) + bandage_symmetries(c.Shape())
        for rotation in orientations:
            with self.subTest(rotation=rotation):
                transferred = path.rotated(rotation)
                cell_images = _CELL_IMAGES[rotation_tuple(inverse_rotation(rotation))]
                for original, actual in ((path.source_shape, transferred.source_shape),
                                         (path.target_shape, transferred.target_shape)):
                    expected = frozenset(frozenset(cell_images[cell] for cell in members)
                                         for members in partition(original))
                    self.assertEqual(partition(actual), expected)
                replay = c.State(transferred.source_shape).apply(transferred.moves)
                self.assertEqual(replay.shape, transferred.target_shape)
                self.assertEqual(replay.sticker_permutation, transferred.permutation)
                self.assertEqual(transferred.displayed_moves, path.displayed_moves)
                self.assertEqual(transferred.rotated(inverse_rotation(rotation)), path)
        # Open transfers work even for a regrip that is not a root symmetry.
        self.assertNotIn("x", bandage_symmetries(self.root))
        self.assertNotEqual(path.rotated("x").source_shape, self.root)

    def test_noncommuting_regrips_and_reframing_do_not_double_transform_moves(self):
        path = ShapePath.from_moves(self.root, "U F")
        transferred = path.rotated("x").rotated("y")
        self.assertEqual(transferred, path.rotated("y x"))
        self.assertNotEqual(transferred, path.rotated("x y"))
        self.assertEqual(transferred.displayed_moves, path.moves)
        reframed = transferred.reframed("z z")
        self.assertEqual(reframed.frame, "z2")
        self.assertEqual(reframed.moves, transferred.moves)
        self.assertEqual(reframed.permutation, transferred.permutation)
        self.assertEqual(reframed.source_shape, transferred.source_shape)
        self.assertEqual(reframed.target_shape, transferred.target_shape)

    def test_regrips_retain_core_bonds_and_composition_checks_them(self):
        core_labels = [0] * 27
        core_labels[c.U] = core_labels[c.C] = 72
        bonded = c.Shape(core_labels)
        path = ShapePath.from_moves(bonded, "R F2")
        self.assertEqual(path.source_shape[c.U], path.source_shape[c.C])
        for rotation in ("",) + bandage_symmetries(c.Shape()):
            transferred = path.rotated(rotation)
            core_label = transferred.source_shape[c.C]
            self.assertEqual(sum(label == core_label for label in transferred.source_shape), 2)
            self.assertEqual(c.State(transferred.source_shape).apply(transferred.moves).shape,
                             transferred.target_shape)
        # Dropping the invisible physical bond is not an admissible endpoint.
        with self.assertRaisesRegex(ValueError, "endpoint"):
            path.then(ShapePath.identity(c.Shape()))

    def test_local_loop_transport_and_nonzero_graph_root(self):
        nonzero = c.isotropy_loops(self.graph, root=1)
        setup = ShapePath.from_graph(self.graph, 0, nonzero.root_vertex)
        generator = nonzero.generators[0]
        body = ShapePath.local_loop(nonzero.root_shape, generator.turn_sequence)
        transported = setup.transport_loop(body)
        self.assertTrue(body.is_closed)
        self.assertTrue(transported.is_closed)
        self.assertEqual(transported.source_shape, self.root)
        replay = c.State(self.root).apply(
            setup.moves + " " + body.moves + " " + setup.inverse().moves)
        self.assertEqual(transported.permutation, replay.sticker_permutation)
        self.assertNotEqual(transported.permutation, IDENTITY)
        root_transport = ShapePath.from_transport(nonzero, 0)
        self.assertEqual(root_transport.source_shape, nonzero.root_shape)
        self.assertEqual(root_transport.target_shape, self.root)
        self.assertEqual(ShapePath.from_transport(nonzero, 1),
                         ShapePath.identity(nonzero.root_shape))
        with self.assertRaisesRegex(ValueError, "closed"):
            setup.transport_loop(setup)
        with self.assertRaisesRegex(ValueError, "source"):
            ShapePath.local_loop(self.root, "U")
        with self.assertRaises(TypeError):
            setup.transport_loop(generator.turn_sequence)

    def test_lowering_requires_actual_reference_root_and_original_loop_certificate(self):
        nonzero = c.isotropy_loops(self.graph, root=1)
        first, second = nonzero.generators[:2]
        witness = c.LoopExpression.loop(first.id)
        path = ShapePath.local_loop(nonzero.root_shape, first.turn_sequence, frame="x")
        lowered = path.to_loop_expression(witness, nonzero)
        self.assertEqual(lowered.kind, "turns")
        self.assertEqual(lowered.children, (witness,))
        self.assertEqual(lowered.expanded_moves(nonzero), path.moves)
        self.assertEqual(lowered.evaluate(nonzero), path.permutation)
        with self.assertRaisesRegex(ValueError, "certificate"):
            path.to_loop_expression(c.LoopExpression.loop(second.id), nonzero)
        with self.assertRaisesRegex(ValueError, "reference root"):
            path.to_loop_expression(witness, self.loops)
        with self.assertRaisesRegex(ValueError, "reference root"):
            ShapePath.from_moves(self.root, "U").to_loop_expression(witness, self.loops)
        with self.assertRaises(TypeError):
            path.to_loop_expression(first.id, nonzero)
        # A literal certificate's claimed original effect is not trusted.
        forged = c.LoopExpression.turns("", witness)
        with self.assertRaisesRegex(ValueError, "original-loop witness"):
            path.to_loop_expression(forged, nonzero)

    def test_portable_loop_records_certify_loops_but_cannot_supply_native_tree_paths(self):
        records = stored_loop_generators(
            [generator.to_dict() for generator in self.loops], self.loops.block_inventory,
            self.loops.root_vertex, self.loops)
        with self.assertRaisesRegex(ValueError, "portable loop records.*from_graph"):
            ShapePath.from_transport(records, 1)
        first = records[0]
        path = ShapePath.local_loop(self.loops.root_shape, first.turn_sequence)
        certificate = c.LoopExpression.loop(first.id)
        self.assertEqual(path.to_loop_expression(certificate, records).expanded_moves(records),
                         path.moves)
        # An explicit graph remains a legal transport source after loading.
        transport = ShapePath.from_graph(self.graph, self.loops.root_shape, 1)
        self.assertEqual(transport.source_shape, self.loops.root_shape)
        self.assertEqual(transport.target_shape, self.graph[1])

    def test_identity_certificate_at_nonzero_root_with_no_original_generators(self):
        # The asymmetric fused U layer can turn, while the fused lower two
        # layers block every other face.  Four shapes, no colored root loops.
        graph = c.explore(c.Shape([3] + [1] * 8 + [2] * 18))
        loops = c.isotropy_loops(graph, root=1)
        self.assertEqual(loops.root_vertex, 1)
        self.assertEqual(len(loops), 0)
        self.assertEqual(len(graph), 4)
        path = ShapePath.identity(loops.root_shape)
        lowered = path.to_loop_expression(c.LoopExpression.sequence(), loops)
        self.assertEqual(lowered.expanded_moves(loops), "")
        self.assertEqual(lowered.evaluate(loops), IDENTITY)
        self.assertEqual(ShapePath.from_transport(loops, 1), path)
        transport = ShapePath.from_transport(loops, 0)
        self.assertEqual(transport.source_shape, graph[1])
        self.assertEqual(transport.target_shape, graph[0])

    def test_direct_declarations_invalid_turns_and_cancelled_blocked_paths_are_rejected(self):
        path = ShapePath.from_moves(self.root, "U")
        with self.assertRaisesRegex(ValueError, "target"):
            ShapePath(self.root, self.root, path.moves, path.permutation)
        with self.assertRaisesRegex(ValueError, "sticker action"):
            ShapePath(self.root, path.target_shape, path.moves, IDENTITY)
        for invalid in (range(47), [0] * 48, [False] + list(range(1, 48)),
                        [0.0] + list(range(1, 48))):
            with self.assertRaises(ValueError):
                ShapePath(self.root, path.target_shape, path.moves, invalid)
        for word in ("x U x'", "R3", "RUR'", "r", "F //"):
            with self.assertRaises(ValueError):
                ShapePath.from_moves(self.root, word)
        with self.assertRaises(TypeError):
            ShapePath.from_moves(self.root, ["U"])
        with self.assertRaisesRegex(ValueError, "blocked"):
            ShapePath.from_moves(c.Shape([1] * 27), "R R'")
        with self.assertRaises(ValueError):
            path.reframed("R")

    def test_portable_records_are_replayed_and_tampering_is_rejected(self):
        path = ShapePath.from_moves(self.root, "U F").rotated("x y")
        record = path.to_dict()
        self.assertEqual(ShapePath.from_dict(record), path)
        self.assertEqual(ShapePath.from_json(path.to_json()), path)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "open-path.json"
            path.to_json(target)
            self.assertEqual(ShapePath.load(target), path)
        damaged = deepcopy(record)
        damaged["permutation"][0], damaged["permutation"][1] = (
            damaged["permutation"][1], damaged["permutation"][0])
        with self.assertRaisesRegex(ValueError, "sticker action"):
            ShapePath.from_dict(damaged)
        damaged = deepcopy(record)
        damaged["target_shape"] = record["source_shape"]
        with self.assertRaisesRegex(ValueError, "target"):
            ShapePath.from_dict(damaged)
        for key, value in (("version", 2), ("version", True),
                           ("permutation_action", "destination-to-source"),
                           ("frame_convention", "physical")):
            with self.subTest(key=key, value=value):
                damaged = deepcopy(record)
                damaged[key] = value
                with self.assertRaises(ValueError):
                    ShapePath.from_dict(damaged)
        missing = deepcopy(record)
        del missing["frame"]
        with self.assertRaises(ValueError):
            ShapePath.from_dict(missing)
        extra = deepcopy(record)
        extra["root_loop"] = True
        with self.assertRaises(ValueError):
            ShapePath.from_dict(extra)
        with self.assertRaises(TypeError):
            ShapePath.from_dict(json.dumps(record))


if __name__ == "__main__":
    unittest.main()
