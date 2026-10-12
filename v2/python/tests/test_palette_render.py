import unittest
from types import SimpleNamespace

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteSetup
from bce_v2.palette_render import (certified_procedure, execution_vocabulary,
                                 execution_vocabulary_lines,
                                 expanded_recipe_path, palette_method_guide,
                                 recipe_structure, _phase_frame_lines,
                                 _recognition_fields)


class PaletteRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.reference, timeout=30)

    def test_inverse_repetition_is_the_same_physical_correction(self):
        palette = c.palette_from_turn_words(self.analysis, {"internal-loop-id": "U"},
            setup_words=(), adjustment_words=(), allow_inverse=True)
        inverse = next(record["id"] for record in palette.recipe_records if record["exponent"] == -1)
        path = (inverse,) * 3
        declarations, aliases = execution_vocabulary(palette, (path,))
        self.assertEqual([name for _, name, _ in declarations], ["A"])
        self.assertEqual(recipe_structure(palette, path, aliases), "A⁻³")
        physical = c.State(self.reference).apply("U' U' U'")
        declared = {algorithm.id: algorithm for algorithm in palette.recipes}
        self.assertEqual(c.State(self.reference).apply(" ".join(declared[name].turn_sequence for name in path)), physical)
        self.assertEqual(palette.bodies[0].id, "internal-loop-id")

    def test_role_names_do_not_confuse_same_id_with_different_words(self):
        original = c.palette_from_turn_words(self.analysis, {"same": "U"},
            setup_words=("U2",), adjustment_words=("U'",), allow_inverse=False)
        palette = AlgorithmPalette(original.bodies,
            (AlgorithmPaletteSetup("same", original.setups[0].algorithm),),
            (AlgorithmPaletteSetup("same", original.adjustments[0].algorithm),))
        conjugate = next(record["id"] for record in palette.recipe_records if record["setup_id"] == "same")
        adjustment = next(record["id"] for record in palette.recipe_records if record["adjustment_id"] == "same")
        path = (conjugate, conjugate, adjustment)
        declarations, aliases = execution_vocabulary(palette, (path,))
        self.assertEqual([(kind, name) for kind, name, _ in declarations],
                         [("Body", "A"), ("Setup", "B"), ("Adjustment", "C")])
        self.assertEqual(recipe_structure(palette, path, aliases), "[B: A]² C")
        declared = {algorithm.id: algorithm for algorithm in palette.recipes}
        actual = c.State(self.reference).apply(" ".join(declared[name].turn_sequence for name in path))
        self.assertEqual(actual, c.State(self.reference).apply("U2 U U2 U2 U U2 U'"))
        self.assertFalse(palette.bodies[0].allow_inverse)

    def test_setup_and_adjustment_can_share_the_exact_same_word(self):
        palette = c.palette_from_turn_words(self.analysis, {"body": "U"},
            setup_words=("U2",), adjustment_words=("U2",), allow_inverse=False)
        conjugate = next(record["id"] for record in palette.recipe_records if record["setup_id"])
        adjustment = next(record["id"] for record in palette.recipe_records if record["adjustment_id"])
        path = (conjugate, adjustment)
        declarations, aliases = execution_vocabulary(palette, (path,))
        self.assertEqual([(kind, name) for kind, name, _ in declarations],
                         [("Body", "A"), ("Setup", "B"), ("Adjustment", "B")])
        self.assertEqual(recipe_structure(palette, path, aliases), "[B: A] B")

    def test_shared_same_role_word_has_one_displayed_definition(self):
        original = c.palette_from_turn_words(self.analysis, {},
            setup_words=(), adjustment_words=("U",), allow_inverse=False)
        algorithm = original.adjustments[0].algorithm
        palette = AlgorithmPalette((), adjustments=(AlgorithmPaletteSetup("first", algorithm),
                                                    AlgorithmPaletteSetup("second", algorithm)))
        declarations, aliases = execution_vocabulary(palette, ((action.id for action in palette.recipes),))
        self.assertEqual(set(aliases.values()), {"A"})
        guide = "\n".join(execution_vocabulary_lines(declarations))
        self.assertEqual(guide.count("| Adjustment | `A` |"), 1)

    def test_derived_powers_render_the_original_body_without_new_definitions(self):
        palette = c.palette_from_turn_words(self.analysis, {"native": "U"},
            setup_words=(), adjustment_words=(), allow_inverse=False).with_derived_actions()
        square = next(record["id"] for record in palette.recipe_records
                      if record["derived"] and len(record["original_recipe_ids"]) == 2)
        declarations, aliases = execution_vocabulary(palette, ((square,),))
        self.assertEqual([(kind, name) for kind, name, _ in declarations], [("Body", "A")])
        self.assertEqual(recipe_structure(palette, (square,), aliases), "A²")
        self.assertEqual(len(expanded_recipe_path(palette, (square,))), 2)

    def test_ordered_composition_repetition_is_factored_without_commuting_calls(self):
        palette = c.palette_from_turn_words(self.analysis, {"native": "U"},
            setup_words=(), adjustment_words=("U2",), allow_inverse=False)
        adjustment = next(record["id"] for record in palette.recipe_records if record["adjustment_id"])
        body = next(record["id"] for record in palette.recipe_records if record["body_id"])
        path = (adjustment, body) * 2
        _, aliases = execution_vocabulary(palette, (path,))
        self.assertEqual(recipe_structure(palette, path, aliases), "(B A)²")

    def test_forward_only_policy_becomes_one_certified_repeat_rule(self):
        palette = c.palette_from_turn_words(self.analysis, {"native": "U"},
            setup_words=(), adjustment_words=(), allow_inverse=False).with_derived_actions()
        method = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        procedure, = certified_procedure(method)
        self.assertEqual(procedure.rule_count, 1)
        self.assertEqual(procedure.rules[0].conditions, ())
        self.assertEqual(procedure.maximum_repetitions, 3)
        algorithms = {algorithm.id: algorithm for algorithm in palette.recipes}
        saved = {(number, observation): path for number, observation, path in method.case_recipes}
        ranks = dict(zip(procedure.observations, procedure.ranks))
        for observation in procedure.observations:
            state = method.example_state(1, observation)
            original, calls = [], 0
            while not state.is_solved:
                current = method.recognize(state).observation
                recipe = procedure.instruction_for(current)
                original.extend(expanded_recipe_path(palette, recipe))
                after = state.apply(" ".join(algorithms[identifier].turn_sequence for identifier in recipe))
                successor = method.recognize(after).observation if not after.is_solved else procedure.solved_observation
                self.assertLess(ranks[successor], ranks[current])
                state, calls = after, calls + 1
                self.assertLessEqual(calls, procedure.maximum_repetitions)
            self.assertEqual(tuple(original), expanded_recipe_path(palette, saved[1, observation]))
        guide = palette_method_guide(method)
        self.assertIn("Repeat **`A`**", guide)
        self.assertIn("Block action", guide)
        self.assertNotIn("## Algorithms", guide)

    def test_inverse_policy_uses_a_visible_phase_condition(self):
        palette = c.palette_from_turn_words(self.analysis, {"native": "U"},
            setup_words=(), adjustment_words=(), allow_inverse=True).with_derived_actions()
        method = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        procedure, = certified_procedure(method)
        self.assertEqual(procedure.rule_count, 2)
        guide = palette_method_guide(method)
        self.assertIn("phase of", guide)
        self.assertIn("A⁻¹", guide)
        self.assertEqual(max(procedure.htm_costs), 2)

    def test_residual_observer_does_not_leak_erased_absolute_phases(self):
        from bce_v2.human_chains import _observation, _resolve_feature

        inventory = self.analysis.block_inventory
        block = next(block for block in inventory.blocks if block.orientation_order > 1)
        family = tuple(tuple(c.State(self.reference).apply(" ".join(["U"] * power)).sticker_permutation)
                       for power in range(4))
        feature = c.BlockFeature("solve_blocks_up_to_actions", block.cells,
                                 alignment_permutations=family)
        handle = _resolve_feature(inventory, feature)
        goal = _observation(inventory.identity(), handle, feature.kind)
        stage = SimpleNamespace(feature=feature, recognition_features=(), observations=(goal,))
        fields = _recognition_fields(stage, inventory)
        self.assertFalse(any(kind in ("phase", "relative_phase") for _, _, kind, _ in fields))
        for permutation in family:
            self.assertEqual(_observation(inventory.action(permutation), handle, feature.kind), goal)

    def test_partial_phase_family_cue_retains_the_common_phase_coset(self):
        from bce_v2.human_chains import _observation, _resolve_feature
        from bce_v2.human_render import _feature_cue

        inventory = self.analysis.block_inventory
        block = next(block for block in inventory.blocks if block.orientation_order == 4)
        family = tuple(tuple(c.State(self.reference).apply(word).sticker_permutation)
                       for word in ("", "U2"))
        feature = c.BlockFeature("solve_blocks_up_to_actions", block.cells,
                                alignment_permutations=family)
        handle = _resolve_feature(inventory, feature)
        goal = _observation(inventory.identity(), handle, feature.kind)
        other = _observation(inventory.action(c.State(self.reference).apply("U")), handle, feature.kind)
        self.assertNotEqual(goal, other)
        goal_cue = _feature_cue(feature, goal, inventory)
        other_cue = _feature_cue(feature, other, inventory)
        self.assertNotEqual(goal_cue, other_cue)
        self.assertIn("phase 0", goal_cue)
        self.assertIn("phase 2", goal_cue)
        self.assertIn("phase 1", other_cue)
        self.assertIn("phase 3", other_cue)

    def test_phase_frame_table_matches_native_marker_positions(self):
        from bce_v2.human_diagrams import _orientation_marker_points
        from bce_v2.human_render import _sticker

        palette = c.palette_from_turn_words(self.analysis, {"native": "U"},
            setup_words=(), adjustment_words=(), allow_inverse=True)
        method = c.compile_coarse_method(self.analysis, palette=palette,
            features=(c.BlockFeature("solve_blocks", tuple(range(27))),), timeout=30)
        stage, = method.stages
        inventory = method.inventory
        source = next(index for index, block in enumerate(inventory.blocks) if block.orientation_order > 1)
        marker, = _orientation_marker_points(inventory, (source,))
        row = next(line for line in _phase_frame_lines(stage, inventory)
                   if line.startswith(f"| `{inventory.blocks[source].compact_name}` |"))
        columns = row.strip("|").strip().split(" | ")
        for power in range(4):
            state = c.State(self.reference).apply(" ".join(["U"] * power))
            phase = inventory.action(state).phases[source]
            self.assertEqual(columns[phase + 1], f"`{_sticker(state.sticker_permutation[marker])}`")


if __name__ == "__main__":
    unittest.main()
