"""Case pictures preserve the exact observers and executable guide instructions."""

import base64
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.automatic_methods import AutomaticMethod, MethodDiscoveryResult
from bce_v2.human_chains import _feature_indices, _observation, _resolve_feature
from bce_v2.human_diagrams import _orientation_marker_points
from bce_v2.human_methods import (HumanMethodCase, _goal_observation,
                                 _stage_observation, _then)
from bce_v2.human_render import recognition_wording
from bce_v2.palette_render import (certified_procedure, execution_vocabulary,
                                  expanded_recipe_path, recipe_structure,
                                  _grid_field_label, _grid_value, _recognition_grid)
from bce_v2.stage_diagrams import stage_case_diagrams, stage_recognition_diagrams


RESULTS = Path(__file__).resolve().parents[2] / "research-results"
HAS_PLOTS = importlib.util.find_spec("matplotlib") is not None
HEADING = "### Diagrammatic guide:"
FAKE_IMAGE = "data:image/png;base64,cGljdHVyZQ=="
POINTS = tuple(index for index in range(54) if index % 9 != 4)


def without_stage_diagrams(guide):
    """Remove appended galleries, retaining every original instruction byte."""
    return re.sub(r"### Diagrammatic guide:\n.*?(?=## Stage |The \d+ learned bodies)",
                  "", guide, flags=re.DOTALL)


class StageDiagramsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("subprocess.run", side_effect=AssertionError("portable cases need no GAP")):
            cls.alcatraz = c.load_coarse_method(RESULTS / "compact-alcatraz.method.json")
            cls.workspace = c.WorkspaceMethod.load(RESULTS / "compact-unbandaged.method.json")
            cls.shark = c.load_coarse_method(RESULTS / "compact-shark-fin-soup.method.json")
            cls.complete = c.load_human_method(RESULTS / "alcatraz-execution-method.json")
        cls.methods = (cls.alcatraz, cls.workspace.suffix, cls.shark)
        cls.automatic = AutomaticMethod(cls.alcatraz, c.explore(cls.alcatraz.reference_shape),
                                       json.dumps({"route": "certified_test_method"}))
        cls.discovery = MethodDiscoveryResult("completed", cls.automatic, "{}")

    def assert_certified_picture(self, method, stage, picture, *, observations=None):
        inventory = method.inventory
        group = method.ambient_method._symbolic_chain.stages[
            method.prefix_stage_count + stage.number - 1].group_before
        self.assertEqual(picture.stage_number, stage.number)
        self.assertIn(picture.observation, stage.observations)
        self.assertEqual(picture.ready,
                         _goal_observation(picture.observation, inventory, stage)
                         == stage.solved_observation)
        self.assertTrue(picture.cue)
        self.assertTrue(picture.variants)
        self.assertNotRegex(picture.cue + " " + " ".join(picture.notes),
                            r"(?i)\b(?:footprints?|phases?|markers?|facets?|structure|commit to)\b")
        for variant in picture.variants:
            state = variant.state
            action = inventory.action(state)
            self.assertEqual(state.shape, method.reference_shape)
            self.assertIsNone(state.scramble)
            self.assertIn(state.sticker_permutation, group)
            allowed = (picture.observation,) if observations is None else observations
            self.assertIn(_stage_observation(action, stage, inventory), allowed)
            for previous in method.stages[:stage.number - 1]:
                self.assertEqual(_observation(action, previous.block_index, previous.feature.kind),
                                 previous.solved_observation)
            for feature in method.domain_features:
                handle = _resolve_feature(inventory, feature)
                self.assertEqual(_observation(action, handle, feature.kind),
                                 _observation(inventory.identity(), handle, feature.kind))
            for source in variant.solved_blocks:
                self.assertEqual(action.destinations[source], source)
                self.assertEqual(action.phases[source], 0)
            self.assertTrue(all(0 <= sticker < 54 and sticker % 9 != 4
                                for sticker in variant.reference_stickers))
            expected_readings = {}
            for source, block in enumerate(inventory.blocks):
                if block.orientation_order > 1:
                    point, = _orientation_marker_points(inventory, (source,))
                    expected_readings[POINTS[state.sticker_permutation[point]]] = str(action.phases[source])
            self.assertEqual(set(dict(variant.orientation_labels)), set(variant.reference_stickers))
            for sticker, reading in variant.orientation_labels:
                self.assertEqual(reading, expected_readings[sticker])

    def test_every_observation_has_a_certified_picture_in_three_portable_methods(self):
        expected = ((6, 9, 2, 3), (4, 6, 8, 9, 3, 12), (36,))
        with patch("subprocess.run", side_effect=AssertionError("pictures are offline")):
            for method, counts in zip(self.methods, expected):
                counts_seen = []
                for stage in method.stages:
                    pictures = stage_case_diagrams(method, stage.number)
                    counts_seen.append(len(pictures))
                    self.assertEqual(tuple(picture.observation for picture in pictures),
                                     stage.observations)
                    for picture in pictures:
                        with self.subTest(order=method.group_order, stage=stage.number,
                                          observation=picture.observation):
                            self.assert_certified_picture(method, stage, picture)
                self.assertEqual(tuple(counts_seen), counts)

    def test_all_324_alcatraz_states_in_each_prior_subgroup_match_a_pictured_case(self):
        self.assertEqual(len(self.complete._permutations), 324)
        sizes = []
        for stage in self.alcatraz.stages:
            group = self.alcatraz.ambient_method._symbolic_chain.stages[
                stage.number - 1].group_before
            observations = {picture.observation for picture in
                            stage_case_diagrams(self.alcatraz, stage.number)}
            encountered = set()
            count = 0
            for permutation in self.complete._permutations:
                if permutation not in group:
                    continue
                count += 1
                observed = _stage_observation(self.alcatraz.inventory.action(permutation),
                                               stage, self.alcatraz.inventory)
                self.assertIn(observed, observations)
                encountered.add(observed)
            self.assertEqual(encountered, observations)
            sizes.append(count)
        self.assertEqual(sizes, [324, 54, 6, 3])

    def test_ordered_recognition_rows_cover_all_cases_with_the_existing_instruction(self):
        for method in self.methods:
            for stage, procedure in zip(method.stages, certified_procedure(method)):
                rows = stage_recognition_diagrams(method, stage.number, procedure)
                self.assertTrue(rows[0].diagram.ready)
                covered = set()
                for row in rows:
                    self.assertTrue(row.observations)
                    self.assertTrue(set(row.observations).issubset(row.matching_observations))
                    self.assertFalse(covered.intersection(row.observations))
                    covered.update(row.observations)
                    for observation in row.observations:
                        self.assertEqual(row.recipe, procedure.instruction_for(observation))
                    self.assertIn(row.diagram.observation, row.observations)
                    self.assert_certified_picture(method, stage, row.diagram,
                                                  observations=row.observations)
                self.assertEqual(covered, set(stage.observations))

    def test_first_pair_occupancy_rule_has_one_picture_of_only_the_tested_pair(self):
        method = self.alcatraz
        stage = method.stages[0]
        procedure = certified_procedure(method)[0]
        rows = stage_recognition_diagrams(method, 1, procedure)
        row = rows[1]
        self.assertEqual(row.conditions, ("`FR-DFR` occupies `FL-DFL`",))
        self.assertEqual(set(row.observations), set(procedure.rules[0].observations))
        self.assertEqual(len(row.observations), 2)
        source = next(index for index, block in enumerate(method.inventory.blocks)
                      if block.compact_name == "FR-DFR")
        destination = next(index for index, block in enumerate(method.inventory.blocks)
                           if block.compact_name == "FL-DFL")
        variant, = row.diagram.variants
        self.assertEqual(variant.full_blocks, (source,))
        self.assertFalse(variant.location_blocks)
        self.assertFalse(variant.reference_stickers)
        self.assertEqual(variant.piece_labels, ((source, "FR-DFR"),))
        self.assertFalse(variant.slot_labels)
        self.assertEqual(method.inventory.action(variant.state).destinations[source], destination)

    def test_all_324_states_select_the_existing_instruction_from_first_matching_row(self):
        method = self.alcatraz
        for stage, procedure in zip(method.stages, certified_procedure(method)):
            rows = stage_recognition_diagrams(method, stage.number, procedure)
            group = method.ambient_method._symbolic_chain.stages[stage.number - 1].group_before
            for permutation in self.complete._permutations:
                if permutation not in group:
                    continue
                observation = _stage_observation(method.inventory.action(permutation),
                                                   stage, method.inventory)
                row = next(row for row in rows if observation in row.matching_observations)
                self.assertEqual(row.recipe, procedure.instruction_for(observation))

    def test_each_pictured_case_replays_the_existing_legal_instruction_and_preserves_boundaries(self):
        for method in self.methods:
            recipes = {algorithm.id: algorithm for algorithm in method.palette.recipes}
            learned = tuple(method.taught_body_ids)
            for stage, procedure in zip(method.stages, certified_procedure(method)):
                ranks = dict(zip(procedure.observations, procedure.ranks))
                for picture in stage_case_diagrams(method, stage.number):
                    instruction = procedure.instruction_for(picture.observation)
                    self.assertTrue(set(instruction).issubset(recipes))
                    for variant in picture.variants:
                        state = variant.state
                        for identifier in instruction:
                            # Native apply checks every physical intermediate
                            # turn, including temporary displacement.
                            state = state.apply(recipes[identifier].turn_sequence)
                        self.assertEqual(state.shape, method.reference_shape)
                        action = method.inventory.action(state)
                        successor = _stage_observation(action, stage, method.inventory)
                        if picture.ready:
                            self.assertFalse(instruction)
                        else:
                            self.assertLess(ranks[successor], ranks[picture.observation])
                        for previous in method.stages[:stage.number - 1]:
                            self.assertEqual(_observation(action, previous.block_index,
                                                          previous.feature.kind),
                                             previous.solved_observation)
            self.assertEqual(tuple(method.taught_body_ids), learned)

    def test_location_cases_use_insets_only_when_orientation_can_vary(self):
        for method in self.methods[:2]:
            for stage in method.stages:
                if stage.feature.kind != "place_blocks":
                    continue
                named = set(_feature_indices(method.inventory, stage.feature))
                varying = {index for index in named
                           if method.inventory.blocks[index].orientation_order > 1}
                trivial = named - varying
                for picture in stage_case_diagrams(method, stage.number):
                    variant, = picture.variants
                    self.assertEqual(set(variant.location_blocks), varying)
                    self.assertEqual(set(variant.full_blocks), trivial)
                    self.assertFalse(variant.reference_stickers)

    def test_full_pose_cases_color_the_actual_named_pieces(self):
        stage, = self.shark.stages
        named = set(_feature_indices(self.shark.inventory, stage.feature))
        for picture in stage_case_diagrams(self.shark, 1):
            variant, = picture.variants
            self.assertEqual(set(variant.full_blocks), named)
            self.assertFalse(variant.location_blocks)

    def test_relative_orientation_erases_common_absolute_orientation(self):
        for method in self.methods[:2]:
            for stage in method.stages:
                if stage.feature.kind != "solve_blocks_up_to_actions":
                    continue
                indices = _feature_indices(method.inventory, stage.feature)
                for picture in stage_case_diagrams(method, stage.number):
                    variant, = picture.variants
                    expected = {POINTS[variant.state.sticker_permutation[point]]
                                for point in _orientation_marker_points(method.inventory, indices)}
                    self.assertEqual(set(variant.reference_stickers), expected)
                    self.assertFalse(variant.full_blocks)
                    self.assertFalse(variant.location_blocks)
                    self.assertEqual({index for index, _ in variant.piece_labels}, set(indices))
                    self.assertFalse(variant.slot_labels)
                    self.assertEqual(len({method.inventory.blocks[index].orientation_order
                                          for index in indices}), 1)
                    residual = stage.feature.alignment_permutations[-1]
                    alternative = _then(residual, variant.state.sticker_permutation)
                    self.assertEqual(_stage_observation(method.inventory.action(alternative),
                                                        stage, method.inventory),
                                     picture.observation)
                    # Shared reference-sticker colors cannot identify these
                    # corners; source labels keep their identities explicit.
                    self.assertEqual({method.inventory.blocks[index].compact_name
                                      for index in indices},
                                     {name for _, name in variant.piece_labels})

    def test_procedural_relative_cases_show_the_complete_common_orientation_cycle(self):
        for method, number in ((self.alcatraz, 2), (self.workspace.suffix, 4)):
            stage = method.stages[number - 1]
            procedure = certified_procedure(method)[number - 1]
            rows = stage_recognition_diagrams(method, number, procedure)
            self.assertEqual(len(rows), 9)
            indices = _feature_indices(method.inventory, stage.feature)
            grid = _recognition_grid(stage, procedure, method.inventory)
            comparisons = tuple(field for field in grid[:2] if field[2] == "relative_phase")
            self.assertTrue(comparisons)
            by_name = {block.compact_name: index for index, block in enumerate(method.inventory.blocks)}
            for row in rows:
                picture = row.diagram
                self.assert_certified_picture(method, stage, picture)
                self.assertEqual(len(picture.variants), 3)
                self.assertEqual(len({variant.reference_stickers for variant in picture.variants}), 3)
                orientations = []
                position = stage.observations.index(picture.observation)
                for variant in picture.variants:
                    action = method.inventory.action(variant.state)
                    orientations.append(tuple(action.phases[index] for index in indices))
                    for field in comparisons:
                        first, second = re.findall(r"`([^`]+)`", field[0])
                        difference = (action.phases[by_name[first]] -
                                      action.phases[by_name[second]]) % field[3]
                        self.assertEqual(difference, field[1][position])
                shifts = set()
                for orientation in orientations:
                    shift = {(value - original) % 3
                             for value, original in zip(orientation, orientations[0])}
                    self.assertEqual(len(shift), 1)
                    shifts.update(shift)
                self.assertEqual(shifts, {0, 1, 2})
            # The certificate-facing exact API still gives a canonical
            # representative; only procedural pictures expand the cycle.
            self.assertTrue(all(len(picture.variants) == 1
                                for picture in stage_case_diagrams(method, number)))

    def recognition_adapter(self, feature, observers=(), *, moved_occupants=False):
        """Physical observations over the real, complete certified prior group."""
        inventory = self.alcatraz.inventory
        handle = _resolve_feature(inventory, feature)
        stage = replace(self.alcatraz.stages[0], feature=feature, block_index=handle,
                        recognition_features=observers,
                        solved_observation=_observation(inventory.identity(), handle, feature.kind))
        representatives = {}
        indices = _feature_indices(inventory, feature)
        for permutation in sorted(self.complete._permutations):
            action = inventory.action(permutation)
            observation = _stage_observation(action, stage, inventory)
            score = sum(action.destinations[index] != index for index in indices)
            if observation not in representatives or (moved_occupants and
                                                      score > representatives[observation][0]):
                representatives[observation] = score, permutation
        stage = replace(stage, cases=tuple(HumanMethodCase(observation, None, permutation)
                    for observation, (_, permutation) in sorted(representatives.items())))
        return replace(self.alcatraz,
            ambient_method=replace(self.alcatraz.ambient_method, stages=(stage,)),
            prefix_stage_count=0, domain_features=(), case_recipes=())

    def corner_cells(self):
        return tuple(cell for block in self.alcatraz.inventory.blocks
                     if block.orientation_order == 3 for cell in block.cells)

    def test_anonymous_orientation_uses_actual_occupants_reference_stickers(self):
        method = self.recognition_adapter(c.BlockFeature("orient_slots", self.corner_cells()),
                                          moved_occupants=True)
        stage, = method.stages
        slots = _feature_indices(method.inventory, stage.feature)
        saw_permuted_occupant = False
        for picture in stage_case_diagrams(method, 1):
            self.assert_certified_picture(method, stage, picture)
            variant, = picture.variants
            action = method.inventory.action(variant.state)
            occupants = tuple(action.destinations.index(slot) for slot in slots)
            saw_permuted_occupant |= occupants != slots
            expected = {POINTS[variant.state.sticker_permutation[point]]
                        for point in _orientation_marker_points(method.inventory, occupants)}
            self.assertEqual(set(variant.reference_stickers), expected)
            self.assertEqual({index for index, _ in variant.slot_labels}, set(slots))
            self.assertFalse(variant.piece_labels)
            self.assertFalse(variant.full_blocks)
            self.assertFalse(variant.location_blocks)
        self.assertTrue(saw_permuted_occupant)

    def test_independent_observers_combine_complete_patterns(self):
        corner = next(block for block in self.alcatraz.inventory.blocks
                      if block.orientation_order == 3)
        extra = c.BlockFeature("solve_block", corner.cells)
        goal = self.alcatraz.stages[0].feature
        method = self.recognition_adapter(goal, (extra, goal))
        extra_index = _resolve_feature(method.inventory, extra)
        locations = set(_feature_indices(method.inventory, goal))
        varying = {index for index in locations
                   if method.inventory.blocks[index].orientation_order > 1}
        for picture in stage_case_diagrams(method, 1):
            self.assert_certified_picture(method, method.stages[0], picture)
            variant, = picture.variants
            self.assertEqual(set(variant.full_blocks), (locations - varying) | {extra_index})
            self.assertEqual(set(variant.location_blocks), varying)

    def test_regions_and_general_equivalent_arrangements_keep_exact_observations(self):
        inventory = self.alcatraz.inventory
        indices = tuple(index for index, block in enumerate(inventory.blocks)
                        if block.orientation_order == 3)
        generator = next(body.algorithm.permutation for body in self.alcatraz.palette.bodies
                         if any(inventory.action(body.algorithm.permutation).destinations[index]
                                != index for index in indices))
        family, element = [], tuple(range(48))
        while element not in family:
            family.append(element)
            element = _then(element, generator)
        region_cells = tuple(cell for index in indices[:2] for cell in inventory.blocks[index].cells)
        features = (c.BlockFeature("occupy_slots", region_cells),
                    c.BlockFeature("place_blocks_up_to_alignment", self.corner_cells(),
                                   alignment_permutations=tuple(family)),
                    c.BlockFeature("solve_blocks_up_to_actions", self.corner_cells(),
                                   alignment_permutations=tuple(family)))
        for feature in features:
            method = self.recognition_adapter(feature)
            pictures = stage_case_diagrams(method, 1)
            named = _feature_indices(inventory, feature)
            with self.subTest(kind=feature.kind):
                for picture in pictures:
                    self.assert_certified_picture(method, method.stages[0], picture)
                    for variant in picture.variants:
                        if feature.kind == "occupy_slots":
                            self.assertTrue(variant.regions)
                            action = inventory.action(variant.state)
                            expected_cells = {cell for index in named
                                              for cell in inventory.blocks[
                                                  action.destinations[index]].cells}
                            self.assertIn(tuple(sorted(expected_cells)), variant.regions)
                            self.assertEqual(len(variant.regions), 1)
                            self.assertEqual(set(variant.location_blocks), set(named))
                        elif feature.kind == "place_blocks_up_to_alignment":
                            self.assertEqual(set(variant.location_blocks), set(indices))
                            self.assertFalse(variant.full_blocks)
                        else:
                            self.assertEqual(set(variant.full_blocks), set(indices))
                            self.assertFalse(variant.location_blocks)
                if feature.kind != "occupy_slots":
                    self.assertTrue(any(len(picture.variants) > 1 for picture in pictures))

    def test_independent_residual_families_include_combined_equivalent_arrangements(self):
        inventory = self.alcatraz.inventory
        corners = tuple(index for index, block in enumerate(inventory.blocks)
                        if block.orientation_order == 3)
        edges = tuple(index for index, block in enumerate(inventory.blocks)
                      if block.orientation_order == 2)
        action = next(body.algorithm.permutation for body in self.alcatraz.palette.bodies
                      if inventory.action(body.algorithm.permutation).destinations
                      == tuple(range(len(inventory.blocks))) and
                      any(inventory.action(body.algorithm.permutation).phases[index]
                          for index in corners) and
                      any(inventory.action(body.algorithm.permutation).phases[index]
                          for index in edges))
        square = _then(action, action)
        cube = _then(square, action)
        identity = tuple(range(48))
        corner = c.BlockFeature("solve_blocks_up_to_actions", inventory.blocks[corners[0]].cells,
                               alignment_permutations=(identity, square, _then(square, square)))
        edge = c.BlockFeature("solve_blocks_up_to_actions", inventory.blocks[edges[0]].cells,
                             alignment_permutations=(identity, cube))
        method = self.recognition_adapter(corner, (corner, edge))
        for picture in stage_case_diagrams(method, 1):
            self.assert_certified_picture(method, method.stages[0], picture)
            poses = set()
            for variant in picture.variants:
                current = inventory.action(variant.state)
                poses.add((current.destinations[corners[0]], current.phases[corners[0]],
                           current.destinations[edges[0]], current.phases[edges[0]]))
            # There are three corner orientations and two edge orientations.
            # Their independent alternatives include simultaneous changes.
            self.assertEqual(len(poses), 6)
            self.assertEqual(len(picture.variants), 6)

    def test_a_falsified_saved_representative_is_rejected_before_drawing(self):
        original = self.alcatraz.stages[0]
        bad = replace(original.cases[0], representative=original.cases[1].representative)
        stage = replace(original, cases=(bad, *original.cases[1:]))
        method = replace(self.alcatraz,
            ambient_method=replace(self.alcatraz.ambient_method, stages=(stage,)))
        with self.assertRaises(ValueError):
            stage_case_diagrams(method, 1)

    def test_prior_commitment_is_checked_even_for_the_correct_current_observation(self):
        stage = self.alcatraz.stages[1]
        group = self.alcatraz.ambient_method._symbolic_chain.stages[1].group_before
        target = stage.cases[0]
        outsider = next(permutation for permutation in self.complete._permutations
                        if permutation not in group and
                        _stage_observation(self.alcatraz.inventory.action(permutation), stage,
                                           self.alcatraz.inventory) == target.observation)
        bad = replace(target, representative=outsider)
        stages = (self.alcatraz.stages[0], replace(stage, cases=(bad, *stage.cases[1:])))
        method = replace(self.alcatraz,
            ambient_method=replace(self.alcatraz.ambient_method, stages=stages))
        with self.assertRaises(ValueError):
            stage_case_diagrams(method, 2)

    def test_optional_galleries_leave_instructions_and_certificates_identical(self):
        wrappers = (self.alcatraz, self.workspace, self.automatic, self.discovery)
        for wrapper in wrappers:
            stored = self.alcatraz.to_dict(), self.workspace.to_dict()
            plain = wrapper.write_guide()
            with patch("subprocess.run", side_effect=AssertionError("guide rendering is offline")), \
                    patch("bce_v2.stage_diagram_render.stage_case_image",
                          return_value=FAKE_IMAGE) as renderer:
                illustrated = wrapper.write_guide(recognition_diagrams=True)
            suffix = self.workspace.suffix if wrapper is self.workspace else self.alcatraz
            expected = sum(len(stage_recognition_diagrams(suffix, stage.number))
                           for stage in suffix.stages)
            with self.subTest(wrapper=type(wrapper).__name__):
                self.assertEqual(illustrated.count(HEADING), len(suffix.stages))
                self.assertEqual(without_stage_diagrams(illustrated), plain)
                self.assertNotIn("Recognition notation examples", illustrated)
                self.assertEqual(renderer.call_count, expected)
                self.assertEqual(illustrated.count(FAKE_IMAGE), expected)
                self.assertNotIn("#### Algorithm:", illustrated)
                self.assertIn("Algorithm: — (no moves)", illustrated)
                galleries = "\n".join(part.split("## Stage", 1)[0]
                                      for part in illustrated.split(HEADING)[1:])
                self.assertNotIn("This relative reading", galleries)
                self.assertNotIn("Read the stickers", galleries)
                self.assertEqual((self.alcatraz.to_dict(), self.workspace.to_dict()), stored)

    def test_workspace_galleries_use_the_shared_execution_vocabulary(self):
        method, suffix = self.workspace, self.workspace.suffix
        entry = expanded_recipe_path(method.entry_palette,
                                     (action.id for action in method.entry_palette.recipes))
        continuation = expanded_recipe_path(suffix.palette,
            (identifier for _, _, recipe in suffix.case_recipes for identifier in recipe))
        _, shared = execution_vocabulary(method.palette, (entry, continuation))
        _, local = execution_vocabulary(suffix.palette,
                                        (recipe for _, _, recipe in suffix.case_recipes))
        procedures = certified_procedure(suffix)
        differing = {(stage.number, observation): (recipe_structure(suffix.palette,
                       procedure.instruction_for(observation), shared),
                       recipe_structure(suffix.palette, procedure.instruction_for(observation), local))
                     for stage, procedure in zip(suffix.stages, procedures)
                     for observation in stage.observations
                     if procedure.instruction_for(observation) and
                     recipe_structure(suffix.palette, procedure.instruction_for(observation), shared)
                     != recipe_structure(suffix.palette, procedure.instruction_for(observation), local)}
        self.assertTrue(differing)
        with patch("bce_v2.stage_diagram_render.stage_case_image", return_value=FAKE_IMAGE):
            guide = method.write_guide(recognition_diagrams=True)
        for (number, _), (expected, _) in differing.items():
            stage_text = guide.split(HEADING)[number]
            self.assertIn("Algorithm: `" + expected + "`", stage_text)

    def test_gallery_bullets_follow_recognition_order_and_print_physical_turn_words(self):
        method = self.alcatraz
        _, aliases = execution_vocabulary(method.palette,
                                           (recipe for _, _, recipe in method.case_recipes))
        algorithms = {algorithm.id: algorithm for algorithm in method.palette.recipes}
        with patch("bce_v2.stage_diagram_render.stage_case_image", return_value=FAKE_IMAGE):
            guide = method.write_guide(recognition_diagrams=True)
        for stage in method.stages:
            gallery = guide.split(HEADING)[stage.number].split("## Stage", 1)[0]
            rows = stage_recognition_diagrams(method, stage.number)
            self.assertEqual(len(re.findall(r"^- case \d+:", gallery, flags=re.MULTILINE)),
                             len(rows))
            for number, row in enumerate(rows, 1):
                cue = f"- case {number}: {row.cue}"
                self.assertIn(cue, gallery)
                if row.recipe:
                    expression = recipe_structure(method.palette, row.recipe, aliases)
                    turns = " ".join(algorithms[identifier].turn_sequence for identifier in row.recipe)
                    self.assertIn(f"Algorithm: `{expression}` (`{turns}`)", gallery)
                else:
                    self.assertIn("Algorithm: — (no moves)", gallery)
            self.assertNotIn("#### Algorithm:", gallery)

    def test_guide_face_colors_pass_through_all_four_wrappers_without_mutating_certificates(self):
        palette = {"U": "yellow", "D": "white", "R": "#cc2211"}
        for wrapper in (self.alcatraz, self.workspace, self.automatic, self.discovery):
            snapshot = self.alcatraz.to_dict(), self.workspace.to_dict()
            with patch("bce_v2.stage_diagram_render.stage_case_image",
                       return_value=FAKE_IMAGE) as renderer:
                guide = wrapper.write_guide(recognition_diagrams=True, face_colors=palette)
            self.assertIn(FAKE_IMAGE, guide)
            self.assertTrue(renderer.call_args_list)
            for call in renderer.call_args_list:
                self.assertEqual(call.kwargs["face_colors"], palette)
            self.assertEqual(wrapper.write_guide(face_colors=palette), wrapper.write_guide())
            self.assertEqual((self.alcatraz.to_dict(), self.workspace.to_dict()), snapshot)

    def test_grid_picture_captions_use_the_printed_difference_signs_and_coordinate_order(self):
        stage = self.alcatraz.stages[1]
        procedure = certified_procedure(self.alcatraz)[1]
        first, second, _, _, _ = _recognition_grid(stage, procedure, self.alcatraz.inventory)
        with patch("bce_v2.stage_diagram_render.stage_case_image",
                   return_value=FAKE_IMAGE) as renderer:
            self.alcatraz.write_guide(recognition_diagrams=True)
        captions = [call.args[0] for call in renderer.call_args_list
                    if call.args[0].stage_number == stage.number]
        self.assertEqual(len(captions), stage.case_count)
        for picture in captions:
            offset = stage.observations.index(picture.observation)
            labels = [recognition_wording(_grid_field_label(field)) for field in (first, second)]
            for label, field in zip(labels, (first, second)):
                value = _grid_value(field, field[1][offset], self.alcatraz.inventory)
                self.assertIn(label + " = " + value, picture.cue)
            self.assertLess(picture.cue.index(labels[0]), picture.cue.index(labels[1]))

    def test_saved_optional_guide_matches_returned_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            with patch("bce_v2.stage_diagram_render.stage_case_image", return_value=FAKE_IMAGE):
                guide = self.discovery.write_guide(path, recognition_diagrams=True)
            self.assertEqual(path.read_text(encoding="utf-8"), guide)
            self.assertIn(HEADING, guide)

    def test_flag_is_boolean_and_false_does_not_enter_diagram_renderer(self):
        for wrapper in (self.alcatraz, self.workspace, self.automatic, self.discovery):
            with patch("bce_v2.stage_diagram_render.stage_case_image") as renderer:
                for invalid in (None, 0, 1, "yes", ()):
                    with self.subTest(wrapper=type(wrapper).__name__, flag=invalid):
                        with self.assertRaises(TypeError):
                            wrapper.write_guide(recognition_diagrams=invalid)
                self.assertEqual(wrapper.write_guide(recognition_diagrams=False),
                                 wrapper.write_guide())
                renderer.assert_not_called()

    def test_plain_guide_and_semantic_cases_import_no_optional_plot_dependencies(self):
        program = """
import json, sys
import bce_v2 as c
method = c.load_coarse_method(sys.argv[1])
guide = method.write_guide()
assert 'Diagrammatic guide:' not in guide
from bce_v2.stage_diagrams import stage_case_diagrams, stage_recognition_diagrams
assert len(stage_case_diagrams(method, 1)) == 6
assert len(stage_recognition_diagrams(method, 1)) == 4
assert not any(name.split('.')[0] in ('matplotlib', 'networkx', 'scipy', 'PIL')
               for name in sys.modules)
print(json.dumps({'lazy': True}))
"""
        result = subprocess.run((sys.executable, "-c", program,
                                 str(RESULTS / "compact-alcatraz.method.json")),
                                check=True, capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(result.stdout), {"lazy": True})

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_actual_case_picture_uses_opposite_orthographic_3d_views_and_closes_png(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from bce_v2.stage_diagram_render import stage_case_figure, stage_case_image

        picture = stage_case_diagrams(self.alcatraz, 2)[1]
        figure = stage_case_figure(picture, self.alcatraz.inventory)
        try:
            self.assertEqual(len(figure.texts), 1)
            self.assertEqual(figure.texts[0].get_text(), figure._suptitle.get_text())
            self.assertEqual(len(figure.axes), 2 * len(picture.variants))
            for first, second in zip(figure.axes[::2], figure.axes[1::2]):
                self.assertEqual((first.name, second.name), ("3d", "3d"))
                self.assertEqual(first._focal_length, float("inf"))
                self.assertEqual(second._focal_length, float("inf"))
                self.assertAlmostEqual(first.elev, -second.elev)
                self.assertAlmostEqual((first.azim - second.azim) % 360, 180)
        finally:
            plt.close(figure)
        before = plt.get_fignums()
        with patch("subprocess.run", side_effect=AssertionError("portable PNG")):
            data = stage_case_image(picture, self.alcatraz.inventory)
        self.assertEqual(plt.get_fignums(), before)
        self.assertTrue(data.startswith("data:image/png;base64,"))
        png = base64.b64decode(data.split(",", 1)[1])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertGreater(width, 300)
        self.assertGreater(height, 150)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_orientation_numbers_are_drawn_on_reference_stickers_without_figure_notes(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from bce_v2.stage_diagram_render import stage_case_figure

        for number in (2, 4):
            row = stage_recognition_diagrams(self.alcatraz, number)[1]
            variant = row.diagram.variants[0]
            self.assertTrue(variant.orientation_labels)
            figure = stage_case_figure(row.diagram, self.alcatraz.inventory)
            try:
                self.assertEqual(len(figure.texts), 1)
                texts = {text.get_text() for axis in figure.axes for text in axis.texts}
                for _, reading in variant.orientation_labels:
                    self.assertTrue(any(text == reading or text.endswith(": " + reading)
                                        for text in texts))
                self.assertFalse(any("This relative" in text or "Read the stickers" in text
                                     for text in texts))
            finally:
                plt.close(figure)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_sticker_masks_hide_unobserved_colors_and_preserve_actual_pose_colors(self):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.colors import to_rgb
        from bce_v2.graphics import _palette
        from bce_v2.stage_diagram_render import (_CONTEXT, _OBSERVED_GREY, _SOLVED_GREY,
                                                _facelet_cell, _variant_colors)

        for method, number in ((self.alcatraz, 1), (self.alcatraz, 2),
                               (self.alcatraz, 3), (self.shark, 1)):
            variant = stage_case_diagrams(method, number)[1].variants[0]
            action = method.inventory.action(variant.state)
            source_at = {cell: source for source, destination in enumerate(action.destinations)
                         for cell in method.inventory.blocks[destination].cells}
            actual_colors = {face: to_rgb(color) for face, color in _palette(None).items()}
            colors = _variant_colors(variant, method.inventory)
            self.assertEqual(len(colors), 54)
            for sticker, color in enumerate(colors):
                source = source_at[_facelet_cell(sticker)]
                if (sticker % 9 == 4 or source in variant.full_blocks
                        or sticker in variant.reference_stickers):
                    self.assertEqual(color, actual_colors[variant.state.facelets[sticker]])
                else:
                    self.assertIn(color, (_CONTEXT, _OBSERVED_GREY, _SOLVED_GREY))
                    if source in variant.location_blocks:
                        self.assertEqual(color, _OBSERVED_GREY)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_custom_face_colors_reach_full_reference_and_inset_colors_with_actual_white_hatching(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from bce_v2.graphics import _palette
        from bce_v2.stage_diagram_render import (_facelet_cell, _variant_colors,
                                                stage_case_figure)

        face_colors = {"U": "yellow", "D": "white", "R": "#cc2211", "L": "white"}
        palette = {face: to_rgb(color) for face, color in _palette(face_colors).items()}
        for method, number in ((self.shark, 1), (self.alcatraz, 2), (self.workspace.suffix, 1)):
            picture = stage_case_diagrams(method, number)[1]
            variant, = picture.variants
            colors = _variant_colors(variant, method.inventory, face_colors=face_colors)
            action = method.inventory.action(variant.state)
            source_at = {cell: source for source, destination in enumerate(action.destinations)
                         for cell in method.inventory.blocks[destination].cells}
            for sticker in range(54):
                if (sticker % 9 == 4 or source_at[_facelet_cell(sticker)] in variant.full_blocks
                        or sticker in variant.reference_stickers):
                    self.assertEqual(colors[sticker], palette[variant.state.facelets[sticker]])
            self.assertEqual(colors[4], to_rgb("yellow"))
            self.assertEqual(colors[31], to_rgb("white"))
            figure = stage_case_figure(picture, method.inventory, face_colors=face_colors)
            try:
                self.assertEqual(len(figure.texts), 1)
                white_stickers = set()
                insets_seen = set()
                for axis in figure.axes:
                    for collection in axis.collections:
                        identifier = collection.get_gid()
                        if identifier.endswith("-location-insets"):
                            colors_3d = collection._facecolor3d
                            for sticker, color in zip(collection.stage_facelet_indices, colors_3d):
                                self.assertEqual(tuple(color[:3]), palette[variant.state.facelets[sticker]])
                                insets_seen.add(sticker)
                        if identifier.endswith("-white-sticker-stripes"):
                            white_stickers.update(collection.stage_facelet_indices)
                self.assertTrue(white_stickers)
                self.assertTrue(all(variant.state.facelets[sticker] in ("D", "L")
                                    for sticker in white_stickers))
                if variant.location_blocks:
                    self.assertTrue(insets_seen)
                    self.assertTrue(any(variant.state.facelets[sticker] == "U"
                                        for sticker in insets_seen))
                    self.assertTrue(white_stickers.intersection(insets_seen))
                if variant.reference_stickers:
                    self.assertTrue(all(colors[sticker] == to_rgb("yellow")
                                        for sticker in variant.reference_stickers))
                    self.assertFalse(set(variant.reference_stickers) & white_stickers)
            finally:
                plt.close(figure)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_location_insets_are_small_and_each_exterior_sticker_appears_once(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from bce_v2.stage_diagram_render import (_facelet_cell, _sticker_square,
                                                stage_case_figure)

        method = self.workspace.suffix
        picture = stage_case_diagrams(method, 1)[1]
        variant, = picture.variants
        action = method.inventory.action(variant.state)
        occupied = {cell for source in variant.location_blocks
                    for cell in method.inventory.blocks[action.destinations[source]].cells}
        expected = {index for index in range(54) if index % 9 != 4
                    and _facelet_cell(index) in occupied}
        figure = stage_case_figure(picture, method.inventory)
        try:
            seen = set()
            for axis, visible in zip(figure.axes, ("UFR", "BLD")):
                inset = next(collection for collection in axis.collections
                             if collection.get_gid().endswith("-location-insets"))
                indices = set(inset.stage_facelet_indices)
                self.assertFalse(seen & indices)
                self.assertTrue(all("URFDLB"[index // 9] in visible for index in indices))
                seen.update(indices)
                for index in indices:
                    square = _sticker_square(index, .48)
                    sizes = [max(vertex[coordinate] for vertex in square)
                             - min(vertex[coordinate] for vertex in square)
                             for coordinate in range(3)]
                    self.assertEqual(sum(size < 1e-12 for size in sizes), 1)
                    self.assertTrue(all(abs(size - .48) < 1e-12
                                        for size in sizes if size > 1e-12))
                # Hatching on a physical white sticker stays inside the
                # corresponding small inset, rather than coloring its grey rim.
                for collection in axis.collections:
                    if not collection.get_gid().endswith("-white-sticker-stripes"):
                        continue
                    for ordinal, index in enumerate(collection.stage_facelet_indices):
                        if index not in indices:
                            continue
                        square = _sticker_square(index, .48, .012)
                        lower = tuple(min(vertex[axis] for vertex in square) for axis in range(3))
                        upper = tuple(max(vertex[axis] for vertex in square) for axis in range(3))
                        for segment in collection._segments3d[ordinal * 7:(ordinal + 1) * 7]:
                            for point in segment:
                                self.assertTrue(all(lo - 1e-12 <= value <= hi + 1e-12
                                                    for value, lo, hi in zip(point, lower, upper)))
            self.assertEqual(seen, expected)
        finally:
            plt.close(figure)

    @unittest.skipUnless(HAS_PLOTS, "optional plots extra")
    def test_png_encoding_failure_releases_its_figure(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        from bce_v2.stage_diagram_render import stage_case_image

        picture = stage_case_diagrams(self.alcatraz, 1)[0]
        before = plt.get_fignums()
        with patch.object(Figure, "savefig", side_effect=OSError("simulated output failure")):
            with self.assertRaises(OSError):
                stage_case_image(picture, self.alcatraz.inventory)
        self.assertEqual(plt.get_fignums(), before)


if __name__ == "__main__":
    unittest.main()
