"""Exact stage guarantees, physical identity coloring, and placement variants."""

from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.graphics import _FACE_CELLS
from bce_v2.human_diagrams import (
    recognition_block_roles, recognition_case_diagrams, recognition_stage_diagrams,
)


IDENTITY = tuple(range(48))
RESULTS = Path(__file__).resolve().parents[2] / "research-results"
POCKET_RECORD = Path("/tmp/bandaged-pocket-cube-repertoire.json")
POCKET_BANDAGE = [1, 1, 2, 1, 1, 2, 3, 3, 0,
                  0, 0, 4, 0, 0, 4, 5, 5, 6,
                  0, 0, 4, 0, 0, 4, 5, 5, 6]


def observe(action, block, kind):
    return ((action.destinations[block],) if kind == "place_block" else
            (action.destinations[block], action.phases[block]))


class HumanDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("subprocess.run", side_effect=AssertionError("portable diagrams need no GAP")):
            cls.methods = {
                "execution": c.load_human_method(RESULTS / "alcatraz-execution-method.json"),
                "recognition": c.load_human_method(RESULTS / "alcatraz-recognition-method.json"),
            }
            cls.pocket_repertoire = (c.load_human_repertoire(POCKET_RECORD)
                                    if POCKET_RECORD.exists() else None)
        if cls.pocket_repertoire is not None:
            cls.methods["pocket"] = cls.pocket_repertoire.method
        elif shutil.which("gap"):
            cls.methods["pocket"] = c.synthesize_human_method(
                POCKET_BANDAGE, max_group_elements=432, timeout=45)
        cls.actions = {name: {p: method.inventory.action(p) for p in method._permutations}
                       for name, method in cls.methods.items()}

    def test_every_role_matches_guarantees_over_the_entire_prior_subgroup(self):
        for name, method in self.methods.items():
            members = set(method._permutations)
            actions = self.actions[name]
            identity = actions[IDENTITY]
            for stage in method.stages:
                roles = recognition_block_roles(method, stage.number)
                for i, block in enumerate(method.inventory.blocks):
                    solved = all(observe(actions[p], i, "solve_block") ==
                                 observe(identity, i, "solve_block") for p in members)
                    placed = all(actions[p].destinations[i] == i for p in members)
                    expected = ("current" if i == stage.block_index else "solved" if solved
                                else "placed" if placed else "unsolved")
                    with self.subTest(method=name, stage=stage.number, block=block.name):
                        self.assertEqual(roles[i], expected)
                members = {p for p in members if observe(actions[p], stage.block_index,
                           stage.feature.kind) == stage.solved_observation}

    def test_all_case_pictures_are_physical_states_and_follow_source_identity(self):
        with patch("subprocess.run", side_effect=AssertionError("diagram generation needs no GAP")):
            for name, method in self.methods.items():
                for stage in method.stages:
                    pictures = recognition_stage_diagrams(method, stage.number)
                    self.assertEqual(set(pictures), set(stage.observations))
                    for observation, variants in pictures.items():
                        self.assertTrue(variants)
                        for diagram in variants:
                            action = method.inventory.action(diagram.state)
                            with self.subTest(method=name, stage=stage.number,
                                              observation=observation, phase=diagram.phase):
                                self.assertEqual(diagram.state.shape, method.reference_shape)
                                self.assertIn(diagram.state.sticker_permutation, method._permutations)
                                self.assertEqual(observe(action, stage.block_index,
                                                 stage.feature.kind), observation)
                                self.assertEqual(diagram.phase, action.phases[stage.block_index])
                                self.assertEqual(diagram.current_blocks, (stage.block_index,))
                                for source, destination in enumerate(action.destinations):
                                    for cell in method.inventory.blocks[destination].cells:
                                        self.assertEqual(diagram.cell_roles[cell],
                                                         diagram.block_roles[source])
                                self.assertEqual(diagram.sticker_roles, tuple(
                                    diagram.cell_roles[cell] for face in "URFDLB"
                                    for cell in _FACE_CELLS[face]))
                                for face_index in range(6):
                                    self.assertEqual(diagram.sticker_roles[face_index * 9 + 4], "solved")

    def test_placement_variants_cover_all_and_only_actual_target_orientations(self):
        method = self.methods["recognition"]
        members = set(method._permutations)
        actions = self.actions["recognition"]
        has_multiple_orientations = False
        for stage in method.stages:
            pictures = recognition_stage_diagrams(method, stage.number)
            for observation, diagrams in pictures.items():
                if stage.feature.kind == "place_block":
                    expected = {actions[p].phases[stage.block_index] for p in members
                                if observe(actions[p], stage.block_index, stage.feature.kind) == observation}
                    self.assertEqual({diagram.phase for diagram in diagrams}, expected)
                    self.assertEqual(len(diagrams), len(expected))
                    self.assertTrue(all(diagram.orientation_independent for diagram in diagrams))
                    has_multiple_orientations |= len(expected) > 1
                else:
                    self.assertEqual(len(diagrams), 1)
                    self.assertFalse(diagrams[0].orientation_independent)
            members = {p for p in members if observe(actions[p], stage.block_index,
                       stage.feature.kind) == stage.solved_observation}
        self.assertTrue(has_multiple_orientations)

    def test_incidental_solved_positions_in_a_representative_remain_white(self):
        method = self.methods["execution"]
        stage = method.stages[0]
        diagrams = recognition_case_diagrams(method, stage.number, stage.solved_observation)
        diagram = diagrams[0]
        self.assertTrue(diagram.state.is_solved)
        self.assertIn("unsolved", diagram.block_roles)
        self.assertEqual(diagram.block_roles[stage.block_index], "current")

    def test_implied_guarantees_become_protected_at_the_next_stage(self):
        tested = set()
        for method in self.methods.values():
            by_cells = {block.cells: i for i, block in enumerate(method.inventory.blocks)}
            for stage in method.stages[:-1]:
                roles = recognition_block_roles(method, stage.number + 1)
                for feature in stage.implied_features:
                    block = by_cells[feature.cells]
                    if block == method.stages[stage.number].block_index:
                        continue
                    expected = "solved" if feature.kind == "solve_block" else ("solved", "placed")
                    if isinstance(expected, tuple):
                        self.assertIn(roles[block], expected)
                    else:
                        self.assertEqual(roles[block], expected)
                    tested.add(feature.kind)
        self.assertEqual(tested, {"place_block", "solve_block"})

    def test_pocket_cube_initial_fixed_blocks_are_dark_at_stage_one(self):
        if "pocket" not in self.methods:
            self.skipTest("GAP or the saved PocketCube repertoire is required")
        method = self.methods["pocket"]
        self.assertEqual(method.group_order, 432)
        roles = recognition_block_roles(method, 1)
        by_cells = {block.cells: i for i, block in enumerate(method.inventory.blocks)}
        self.assertEqual(roles[by_cells[(0, 1, 3, 4)]], "solved")
        self.assertEqual(roles[by_cells[(11, 14, 20, 23)]], "solved")
        self.assertEqual(roles[by_cells[(15, 16, 24, 25)]], "solved")
        for feature in method.initial_features:
            if feature.kind == "solve_block":
                self.assertEqual(roles[by_cells[feature.cells]], "solved")

    def test_repertoire_input_and_single_case_lookup_match_method_input(self):
        if self.pocket_repertoire is None:
            self.skipTest("saved PocketCube repertoire is unavailable")
        repertoire = self.pocket_repertoire
        stage = repertoire.method.stages[0]
        for observation in stage.observations:
            self.assertEqual(recognition_case_diagrams(repertoire, 1, observation),
                             recognition_stage_diagrams(repertoire.method, 1)[observation])

    def test_invalid_stage_and_case_inputs_fail_explicitly(self):
        method = self.methods["execution"]
        for stage in (0, len(method.stages) + 1):
            with self.assertRaises(ValueError):
                recognition_stage_diagrams(method, stage)
        for stage in (True, 1.0, "1"):
            with self.assertRaises(TypeError):
                recognition_stage_diagrams(method, stage)
        with self.assertRaises(ValueError):
            recognition_case_diagrams(method, 1, (999, 0))
        with self.assertRaises(TypeError):
            recognition_case_diagrams(method, 1, (True, 0))
        with self.assertRaises(TypeError):
            recognition_stage_diagrams(object(), 1)


if __name__ == "__main__":
    unittest.main()
