"""Exact rigid block actions and source-decorated cycle notation."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

import bce_v2 as c


# Kociemba order is independent of the inventory's display order. The facelet
# tables let synthetic cubie arrays serve as an oracle for source annotations.
CORNER_CELLS = (c.UFR, c.UFL, c.UBL, c.UBR, c.DFR, c.DFL, c.DBL, c.DBR)
EDGE_CELLS = (c.UR, c.UF, c.UL, c.UB, c.DR, c.DF, c.DL, c.DB,
              c.FR, c.FL, c.BL, c.BR)
CORNER_FACELETS = ((8, 9, 20), (6, 18, 38), (0, 36, 47), (2, 45, 11),
                   (29, 26, 15), (27, 44, 24), (33, 53, 42), (35, 17, 51))
EDGE_FACELETS = ((5, 10), (7, 19), (3, 37), (1, 46), (32, 16), (28, 25),
                 (30, 43), (34, 52), (23, 12), (21, 41), (50, 39), (48, 14))
MOVABLE_FACELETS = tuple(index for index in range(54) if index % 9 != 4)
STICKER_INDEX = {facelet: index for index, facelet in enumerate(MOVABLE_FACELETS)}
FACE_NORMALS = ((0, 0, 1), (1, 0, 0), (0, -1, 0),
                (0, 0, -1), (-1, 0, 0), (0, 1, 0))
STICKER_GEOMETRY = {}
CELL_STICKERS = {}
for _cells, _facelets in ((CORNER_CELLS, CORNER_FACELETS), (EDGE_CELLS, EDGE_FACELETS)):
    for _cell, _stickers in zip(_cells, _facelets):
        CELL_STICKERS[_cell] = tuple(STICKER_INDEX[index] for index in _stickers)
        for _facelet in _stickers:
            STICKER_GEOMETRY[STICKER_INDEX[_facelet]] = (_cell, FACE_NORMALS[_facelet // 9])


def coordinates(cell):
    return (cell % 3 - 1, 1 - (cell // 3) % 3, 1 - cell // 9)


def rotate(rotation, vector):
    return tuple((1 if axis > 0 else -1) * vector[abs(axis) - 1] for axis in rotation)


def assert_rotations(test, inventory, action):
    """Check signed-axis records directly against every faithful sticker image."""
    for source, block in enumerate(inventory.blocks):
        rotation = action.rotations[source]
        if rotation is None:
            test.assertTrue(all(cell not in CELL_STICKERS for cell in block.cells))
            test.assertEqual(action.destinations[source], source)
            test.assertEqual(action.phases[source], 0)
            continue
        test.assertEqual({abs(axis) for axis in rotation}, {1, 2, 3})
        inversions = sum(abs(rotation[i]) > abs(rotation[j])
                         for i in range(3) for j in range(i + 1, 3))
        determinant = (-1) ** inversions
        for axis in rotation:
            determinant *= 1 if axis > 0 else -1
        test.assertEqual(determinant, 1)
        destination = inventory.blocks[action.destinations[source]]
        test.assertEqual({rotate(rotation, coordinates(cell)) for cell in block.cells},
                         {coordinates(cell) for cell in destination.cells})
        for cell in block.cells:
            for sticker in CELL_STICKERS.get(cell, ()):
                target_cell, target_normal = STICKER_GEOMETRY[action.permutation[sticker]]
                test.assertEqual(rotate(rotation, coordinates(cell)), coordinates(target_cell))
                test.assertEqual(rotate(rotation, STICKER_GEOMETRY[sticker][1]), target_normal)


def cubie_permutation(*, corners=tuple(range(8)), twists=(0,) * 8,
                      edges=tuple(range(12)), flips=(0,) * 12):
    """Convert destination-indexed cubie arrays to source sticker images."""
    result = list(range(48))
    for pieces, orientations, facelets in ((corners, twists, CORNER_FACELETS),
                                          (edges, flips, EDGE_FACELETS)):
        for destination, source in enumerate(pieces):
            width = len(facelets[source])
            for sticker, facelet in enumerate(facelets[source]):
                target = facelets[destination][(sticker + orientations[destination]) % width]
                result[STICKER_INDEX[facelet]] = STICKER_INDEX[target]
    return tuple(result)


def fused(*groups):
    labels = [0] * 27
    for label, cells in enumerate(groups, 1):
        for cell in cells:
            labels[cell] = label
    return c.Shape(labels)


def block_index(inventory, cells):
    cells = tuple(sorted(cells))
    return next(index for index, block in enumerate(inventory.blocks) if block.cells == cells)


def inverse_images(permutation):
    result = [0] * len(permutation)
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


class BlockInventoryTests(unittest.TestCase):
    def test_cell_names_canonicalize_equivalent_face_letter_orders(self):
        for value, expected in (("FLD", "DFL"), ("RUF", "UFR"),
                                 ("FU", "UF"), (c.DFL, "DFL"), ("C", "C")):
            with self.subTest(value=value):
                self.assertEqual(c.cell_name(value), expected)

    def test_singleton_names_metadata_and_unmarked_centers(self):
        inventory = c.BlockInventory(c.Shape())
        self.assertEqual(len(inventory.blocks), 26)
        self.assertNotIn((c.C,), [block.cells for block in inventory.blocks])
        for cell, name, order in ((c.UFR, "Corner UFR", 3),
                                  (c.UF, "Edge UF", 2), (c.U, "Center U", 1)):
            block = inventory.blocks[block_index(inventory, (cell,))]
            self.assertEqual((block.name, block.type, block.orientation_order),
                             (name, "111", order))
        identity = inventory.identity()
        self.assertEqual(identity.notation, "()")
        self.assertEqual(identity.to_permutation(), tuple(range(48)))
        for index, block in enumerate(inventory.blocks):
            if block.cells[0] in (c.U, c.R, c.F, c.D, c.L, c.B):
                self.assertIsNone(identity.rotations[index])
                self.assertEqual(identity.phases[index], 0)

    def test_inventory_retains_actual_core_bonds_and_nonbox_members(self):
        for cells, code in (((c.U, c.C), "211Core"),
                            ((c.L, c.C, c.R), "311Core"),
                            ((c.UBL, c.UB, c.UL), None)):
            with self.subTest(cells=cells):
                inventory = c.BlockInventory(fused(cells))
                index = block_index(inventory, cells)
                self.assertEqual(inventory.blocks[index].type, code)
                self.assertEqual(inventory.identity().notation, "()")
                self.assertEqual(sum(len(block.cells) for block in inventory.blocks),
                                 27 if c.C in cells else 26)
                if c.C in cells:
                    self.assertEqual(inventory.blocks[index].orientation_order, 1)
                    self.assertIsNone(inventory.identity().rotations[index])
                    moved = c.State(inventory.root_shape).apply("B")
                    action = inventory.action(moved)
                    self.assertIsNone(action.rotations[index])
                    self.assertEqual(action.phases[index], 0)
                    self.assertEqual(action.to_permutation(), moved.sticker_permutation)

    def test_inventory_does_not_depend_on_partition_label_values(self):
        shape = fused((c.FL, c.DFL), (c.U, c.UF))
        relabeled = [1000 + 9 * label for label in shape]
        first, second = c.BlockInventory(shape), c.BlockInventory(relabeled)
        self.assertEqual([(b.cells, b.name, b.kind, b.type, b.orientation_order)
                          for b in first.blocks],
                         [(b.cells, b.name, b.kind, b.type, b.orientation_order)
                          for b in second.blocks])
        self.assertEqual(first.identity().to_dict(), second.identity().to_dict())
        pair = first.blocks[block_index(first, (c.FL, c.DFL))]
        self.assertEqual(pair.name, "Pair FL-DFL")
        clock = first.blocks[block_index(first, (c.U, c.UF))]
        self.assertEqual(clock.name, "Clock U-UF")

    def test_state_inventory_uses_its_reference_specification(self):
        shape = fused((c.UBL, c.UB))
        scrambled = c.State(shape).apply("U")
        self.assertNotEqual(scrambled.shape, shape)
        inventory = c.BlockInventory(scrambled)
        self.assertIn((c.UBL, c.UB), [block.cells for block in inventory.blocks])
        with self.assertRaises(ValueError):
            inventory.action(scrambled.sticker_permutation)

    def test_nonzero_loop_root_anchors_slots_and_replay(self):
        # U quarter turns exchange the two asymmetric pairs after two turns.
        shape = fused((c.UBL, c.UB), (c.UFR, c.UF), range(9, 27))
        graph = c.explore(shape)
        loops = graph.isotropy_loops(root=1)
        self.assertNotEqual(loops.root_shape, shape)
        inventory = loops.block_inventory
        analysis = c.IsotropyAnalysis(loops, 2, tuple(g.id for g in loops), "test")
        self.assertIs(analysis.block_inventory, inventory)
        self.assertEqual(c.BlockInventory(analysis), inventory)
        self.assertEqual(analysis.to_dict()["block_inventory"], inventory.to_dict())
        expected = c.BlockInventory(loops.root_shape)
        self.assertEqual([b.cells for b in inventory.blocks],
                         [b.cells for b in expected.blocks])
        self.assertEqual([b.cells for b in c.BlockInventory(loops).blocks],
                         [b.cells for b in expected.blocks])
        for generator in loops:
            replayed = c.State(loops.root_shape).apply(generator.moves)
            self.assertEqual(replayed.shape, loops.root_shape)
            self.assertEqual(generator.block_action.to_permutation(), replayed.sticker_permutation)
            self.assertEqual(generator.block_action.notation,
                             expected.action(replayed.sticker_permutation).notation)


class DecoratedCycleTests(unittest.TestCase):
    def setUp(self):
        self.inventory = c.BlockInventory(c.Shape())

    def assert_cubie_arrays(self, action, corners, twists, edges, flips):
        for cells, pieces, orientations in ((CORNER_CELLS, corners, twists),
                                            (EDGE_CELLS, edges, flips)):
            for destination, source in enumerate(pieces):
                index = block_index(self.inventory, (cells[source],))
                self.assertEqual(action.destinations[index],
                                 block_index(self.inventory, (cells[destination],)))
                self.assertEqual(action.phases[index], orientations[destination])

    def test_ordinary_moves_match_destination_indexed_cubie_oracle(self):
        for moves in ("U", "F", "R", "L D B", "R U F' L2 D B R' U2"):
            with self.subTest(moves=moves):
                state = c.State().apply(moves)
                permutation = cubie_permutation(corners=state.corners, twists=state.twists,
                                                edges=state.edges, flips=state.flips)
                self.assertEqual(permutation, state.sticker_permutation)
                action = self.inventory.action(permutation)
                self.assert_cubie_arrays(action, state.corners, state.twists,
                                        state.edges, state.flips)
                self.assertEqual(action.to_permutation(), permutation)
                assert_rotations(self, self.inventory, action)

    def test_source_annotations_mixed_signs_and_fixed_twists(self):
        # UFL -> UFR -> UBR -> UFL, with phases 2, 0, 1 at those sources.
        corners = (1, 3, 2, 0, 4, 5, 6, 7)
        twists = (2, 1, 0, 0, 0, 0, 0, 0)
        action = self.inventory.action(cubie_permutation(corners=corners, twists=twists))
        self.assert_cubie_arrays(action, corners, twists, tuple(range(12)), (0,) * 12)
        # Inventory order starts the cycle at UBR, independently of source signs.
        self.assertIn(action.notation, ("(UFL- UFR UBR+)", "(UFR UBR+ UFL-)",
                                       "(UBR+ UFL- UFR)"))
        fixed = self.inventory.action(cubie_permutation(twists=(1, 1, 0, 1, 0, 0, 0, 0),
                                                       flips=(1, 1) + (0,) * 10))
        self.assertEqual(set(fixed.notation.split(")")[:-1]),
                         {"(UFR+", "(UFL+", "(UBR+", "(UR+", "(UF+"})
        self.assertEqual(fixed.destinations, self.inventory.identity().destinations)
        self.assertNotEqual(fixed.to_permutation(), tuple(range(48)))

    def test_equal_cycle_totals_do_not_erase_per_source_phases(self):
        corners = (1, 3, 2, 0, 4, 5, 6, 7)
        first = self.inventory.action(cubie_permutation(corners=corners,
                                                       twists=(2, 1, 0, 0, 0, 0, 0, 0)))
        second = self.inventory.action(cubie_permutation(corners=corners,
                                                        twists=(1, 2, 0, 0, 0, 0, 0, 0)))
        self.assertEqual(first.destinations, second.destinations)
        self.assertEqual(sum(first.phases) % 3, sum(second.phases) % 3)
        self.assertNotEqual(first.phases, second.phases)
        self.assertNotEqual(first.notation, second.notation)
        self.assertNotEqual(first.to_permutation(), second.to_permutation())

    def test_alcatraz_l142_in_place_orientation_regression(self):
        loops = c.isotropy_loops(c.fixture("Alcatraz"))
        generator = next(generator for generator in loops if generator.id == 142)
        self.assertEqual(generator.qtm_length, 12)
        replayed = c.State(loops.root_shape).apply(generator.moves)
        self.assertEqual(replayed.corners, list(range(8)))
        self.assertEqual(replayed.edges, list(range(12)))
        action = generator.block_action
        self.assertEqual(action.to_permutation(), replayed.sticker_permutation)
        self.assertEqual(set(action.notation.split(")")[:-1]),
                         {"(UFR-", "(UFL-", "(UBR-", "(UR+", "(UF+"})

    def test_symmetric_bar_half_turn_and_fused_face_quarter_turn(self):
        for cells, moves, order, phase in (((c.UL, c.U, c.UR), "U2", 2, 1),
                                          (tuple(range(9)), "U2", 4, 2)):
            with self.subTest(cells=cells):
                shape = fused(cells)
                inventory = c.BlockInventory(shape)
                index = block_index(inventory, cells)
                state = c.State(shape).apply(moves)
                action = inventory.action(state.sticker_permutation)
                self.assertEqual(action.destinations[index], index)
                self.assertEqual(inventory.blocks[index].orientation_order, order)
                self.assertEqual(action.phases[index], phase)
                self.assertEqual(action.to_permutation(), state.sticker_permutation)
                self.assertEqual((action ** 2).notation, "()")
                if order == 4:
                    self.assertIn("++", action.notation)
                    quarter = inventory.action(c.State(shape).apply("U").sticker_permutation)
                    self.assertEqual(quarter.phases[index], 1)
                    self.assertEqual((quarter ** 2).permutation, action.permutation)
                    self.assertEqual((quarter ** 4).notation, "()")

    def test_asymmetric_pairs_exchange_without_extra_orientation_coordinate(self):
        shape = fused((c.UBL, c.UB), (c.UFR, c.UF), range(9, 27))
        inventory = c.BlockInventory(shape)
        action = inventory.action(c.State(shape).apply("U2").sticker_permutation)
        left = block_index(inventory, (c.UBL, c.UB))
        right = block_index(inventory, (c.UFR, c.UF))
        self.assertEqual((action.destinations[left], action.destinations[right]), (right, left))
        self.assertEqual((inventory.blocks[left].orientation_order,
                          inventory.blocks[right].orientation_order), (1, 1))
        self.assertEqual((action.phases[left], action.phases[right]), (0, 0))
        self.assertIsNotNone(action.rotations[left])
        self.assertEqual(action.to_permutation(), c.State(shape).apply("U2").sticker_permutation)


class BlockActionAlgebraTests(unittest.TestCase):
    def test_composition_inverse_and_powers_transport_source_phases(self):
        inventory = c.BlockInventory(c.Shape())
        first = inventory.action(c.State().apply("R U F").sticker_permutation)
        second = inventory.action(c.State().apply("L D B").sticker_permutation)
        combined = first.then(second)
        self.assertEqual(combined.to_permutation(), c.State().apply("R U F L D B").sticker_permutation)
        for source, destination in enumerate(first.destinations):
            order = inventory.blocks[source].orientation_order
            self.assertEqual(combined.destinations[source], second.destinations[destination])
            self.assertEqual(combined.phases[source],
                             (first.phases[source] + second.phases[destination]) % order)
        inverse = first.inverse()
        self.assertEqual(inverse.to_permutation(), inverse_images(first.permutation))
        for source, destination in enumerate(first.destinations):
            order = inventory.blocks[source].orientation_order
            self.assertEqual(inverse.phases[destination], -first.phases[source] % order)
        self.assertEqual(first.then(inverse).notation, "()")
        self.assertEqual(inverse.then(first).notation, "()")
        self.assertEqual((first ** 0).notation, "()")
        self.assertEqual((first ** 3).to_permutation(),
                         c.State().apply("R U F R U F R U F").sticker_permutation)
        self.assertEqual((first ** -2).to_permutation(),
                         c.State().apply("F' U' R' F' U' R'").sticker_permutation)

    def test_all_named_witnesses_round_trip_and_exports_are_deterministic(self):
        for name in c.fixture_names():
            with self.subTest(name=name):
                loops = c.isotropy_loops(c.fixture(name))
                inventory = loops.block_inventory
                for generator in loops:
                    action = generator.block_action
                    self.assertEqual(action.permutation, generator.permutation)
                    assert_rotations(self, inventory, action)
                    self.assertEqual(action.to_permutation(), generator.permutation)
                    self.assertEqual(action.inverse().to_permutation(), inverse_images(generator.permutation))
                    self.assertEqual(action.then(action.inverse()).notation, "()")
                    self.assertEqual(action.to_dict(), inventory.action(generator.permutation).to_dict())
                    self.assertEqual(json.loads(json.dumps(action.to_dict())), action.to_dict())
                    record = generator.to_dict(include_moves=False)
                    self.assertEqual(record["block_action"], action.to_dict())
                    self.assertNotIn("moves", record)
                self.assertEqual(loops.to_json(), c.isotropy_loops(loops.root_shape).to_json())

    def test_public_records_are_immutable_and_export_exact_json(self):
        inventory = c.block_inventory()
        self.assertEqual(inventory, c.BlockInventory(c.Shape()))
        state = c.State().apply("R U F'")
        action = inventory.action(state)
        self.assertEqual(action.permutation, state.sticker_permutation)
        for record, attribute, value in ((inventory, "blocks", ()),
                                          (inventory.blocks[0], "cells", ()),
                                          (action, "phases", ())):
            with self.subTest(record=type(record).__name__), self.assertRaises(FrozenInstanceError):
                setattr(record, attribute, value)
        with tempfile.TemporaryDirectory() as directory:
            for name, record in (("inventory", inventory), ("action", action)):
                path = Path(directory) / (name + ".json")
                text = record.to_json(path)
                self.assertEqual(json.loads(text), record.to_dict())
                self.assertEqual(path.read_text(), text)
                self.assertEqual(text, record.to_json())
        self.assertEqual(str(action), action.notation)

    def test_invalid_public_operation_types_are_rejected(self):
        inventory = c.BlockInventory()
        for value in (True, 1.5, "0"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                inventory.action((value,) + tuple(range(1, 48)))
            with self.subTest(exponent=value), self.assertRaises(TypeError):
                inventory.identity() ** value
        with self.assertRaises(TypeError):
            inventory.identity().then(None)
        for value in ("UU", "UD", -1, 27):
            with self.subTest(name=value), self.assertRaises(ValueError):
                c.cell_name(value)
        for value in (True, 1.5, None):
            with self.subTest(name=value), self.assertRaises(TypeError):
                c.cell_name(value)
        with self.assertRaises(ValueError):
            inventory.action(c.State(fused((c.UBL, c.UB))))

    def test_invalid_permutations_shape_changes_and_nonrigid_blocks_are_rejected(self):
        ordinary = c.BlockInventory(c.Shape())
        for permutation in (tuple(range(47)), (0,) * 48, tuple(range(47)) + (48,)):
            with self.subTest(permutation=permutation), self.assertRaises(ValueError):
                ordinary.action(permutation)
        pair = c.BlockInventory(fused((c.UFR, c.UR)))
        # The pair remains in its footprint, but one member twists alone.
        with self.assertRaises(ValueError):
            pair.action(cubie_permutation(twists=(1, 2, 0, 0, 0, 0, 0, 0)))
        split_pair = c.BlockInventory(fused((c.UFR, c.UF)))
        with self.assertRaises(ValueError):
            split_pair.action(c.State().apply("R").sticker_permutation)
        reflection = list(range(48))
        first, second = (STICKER_INDEX[facelet] for facelet in CORNER_FACELETS[0][:2])
        reflection[first], reflection[second] = reflection[second], reflection[first]
        with self.assertRaises(ValueError):
            ordinary.action(reflection)
        with self.assertRaises(ValueError):
            ordinary.identity().then(pair.identity())


if __name__ == "__main__":
    unittest.main()
