"""Alignment goals are transported sets, with physical subgroup certificates."""

from copy import deepcopy
from dataclasses import replace
from itertools import product
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import (_check_alignment_membership, _feature_indices,
                                 _feature_successor, _observation, _resolve_feature, _then)
from bce_v2.symbolic_chains import plan_symbolic_stages, symbolic_plan_from_dict


KIND = "place_blocks_up_to_alignment"
EDGES = (c.UR, c.UF, c.UL, c.UB)
CORNERS = (c.UFR, c.UFL, c.UBL, c.UBR)


def adjustments(word="U"):
    return tuple(tuple(c.State().apply(" ".join([word] * exponent)).sticker_permutation)
                 for exponent in range(4))


class AlignmentActionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = c.BlockInventory()
        self.feature = c.BlockFeature(KIND, CORNERS, adjustments())
        self.block = _resolve_feature(self.inventory, self.feature)

    def test_observation_has_a_complete_endpoint_action_outside_the_solved_region(self):
        for prefix, suffix in product(("", "U", "R F' U2", "B2 L D'"),
                                      ("U'", "R B2", "F' L2")):
            before = c.State().apply(prefix)
            observation = _observation(self.inventory.action(before), self.block, KIND)
            successor = _feature_successor(observation,
                self.inventory.action(c.State().apply(suffix)), self.inventory, self.block, KIND)
            self.assertEqual(successor, _observation(
                self.inventory.action(before.apply(suffix)), self.block, KIND))
        target = _observation(self.inventory.action(c.State()), self.block, KIND)
        for word in ("U", "U2", "U'"):
            self.assertEqual(_observation(self.inventory.action(c.State().apply(word)),
                                          self.block, KIND), target)
        self.assertNotEqual(_observation(self.inventory.action(c.State().apply("R")),
                                        self.block, KIND), target)

    def test_a_joint_alignment_requires_the_same_offset_for_all_named_components(self):
        joint = c.BlockFeature(KIND, (*CORNERS, *EDGES), adjustments())
        block = _resolve_feature(self.inventory, joint)
        target = _observation(self.inventory.action(c.State()), block, KIND)
        self.assertEqual(_observation(self.inventory.action(c.State().apply("U2")), block, KIND), target)
        identity = self.inventory.action(c.State())
        rotated = self.inventory.action(c.State().apply("U2"))
        destinations = list(identity.destinations)
        for index in _feature_indices(self.inventory, self.feature):
            destinations[index] = rotated.destinations[index]
        from types import SimpleNamespace
        mixed = SimpleNamespace(destinations=tuple(destinations), phases=identity.phases)
        self.assertNotEqual(_observation(mixed, block, KIND), target)

    def test_invalid_adjustment_groups_and_regions_are_rejected(self):
        group = adjustments()
        with self.assertRaisesRegex(ValueError, "complete group"):
            c.BlockFeature(KIND, CORNERS, group[:3])
        with self.assertRaisesRegex(ValueError, "distinct"):
            c.BlockFeature(KIND, CORNERS, (*group, group[0]))
        with self.assertRaisesRegex(ValueError, "preserve the named"):
            _resolve_feature(self.inventory, c.BlockFeature(KIND, CORNERS, adjustments("R")))
        with self.assertRaisesRegex(ValueError, "require place_blocks_up_to_alignment"):
            c.BlockFeature("place_blocks", CORNERS, group)

    def test_adjustments_are_checked_against_the_preceding_physical_subgroup(self):
        with self.assertRaisesRegex(ValueError, "preceding subgroup"):
            _check_alignment_membership(self.feature, {tuple(range(48))}.__contains__)
        _check_alignment_membership(self.feature, set(adjustments()).__contains__)
        self.assertEqual(_feature_indices(self.inventory, self.feature),
                         _resolve_feature(self.inventory, c.BlockFeature("place_blocks", CORNERS)))


@unittest.skipUnless(shutil.which("gap"), "GAP is required to construct exact stabilizers")
class AlignmentCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.Shape(), timeout=90)
        inventory = cls.analysis.block_inventory
        prefix = tuple(c.BlockFeature("solve_block", block.cells) for block in inventory.blocks
                       if block.orientation_order > 1 and
                       not set(block.cells).intersection((*EDGES, *CORNERS)))
        group = adjustments()
        cls.features = (c.BlockFeature("orient_slots", EDGES),
                        c.BlockFeature("orient_slots", CORNERS),
                        c.BlockFeature(KIND, CORNERS, group),
                        c.BlockFeature(KIND, (*CORNERS, *EDGES), group),
                        c.BlockFeature("place_blocks", CORNERS))
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no root enumeration")):
            cls.plan = plan_symbolic_stages(cls.analysis, strategy="manual",
                                           features=(*prefix, *cls.features), timeout=90)

    def test_small_ladder_finishes_with_one_shared_alignment(self):
        stages = tuple(stage for stage in self.plan.stages if stage.feature in self.features)
        self.assertEqual([stage.index for stage in stages], [8, 27, 6, 12, 4])
        self.assertEqual(stages[0].order_before, 62_208)
        self.assertEqual(stages[-1].order_after, 1)
        for stage in stages:
            for representative in stage.representatives:
                self.assertEqual(_observation(self.plan.inventory.action(representative.permutation),
                                               stage.block_index, stage.feature.kind),
                                 representative.observation)

    def test_offline_replay_certifies_and_rejects_adjustments_that_break_earlier_goals(self):
        record = self.plan.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("certificate load is offline")):
            loaded = symbolic_plan_from_dict(record, self.plan.inventory,
                                            self.analysis.loops.generators, self.plan.group_order)
            self.assertEqual(loaded.to_dict(), record)
            broken = deepcopy(record)
            row = next(row for row in broken["stages"] if row["feature"]["kind"] == KIND)
            # UD acts exactly like U on the named top corners, but D violates
            # the prior lower-layer commitments. Its placement-set observer
            # is identical; only physical subgroup certification catches it.
            row["feature"] = c.BlockFeature(KIND, CORNERS, adjustments("U D")).to_dict()
            with self.assertRaises(c.GapError) as failure:
                symbolic_plan_from_dict(broken, self.plan.inventory,
                                       self.analysis.loops.generators, self.plan.group_order)
            self.assertIn("preceding subgroup", str(failure.exception.__cause__))

    def test_independent_corner_and_edge_alignments_leave_a_relative_offset(self):
        prefix = tuple(stage.feature for stage in self.plan.stages
                       if stage.feature not in self.features)
        independent = (self.features[0], self.features[1], self.features[2],
                       c.BlockFeature(KIND, EDGES, adjustments()), self.features[4])
        with self.assertRaisesRegex(ValueError, "subgroup of order 2"):
            plan_symbolic_stages(self.analysis, strategy="manual",
                                 features=(*prefix, *independent), timeout=90)

    def test_selected_coarse_paths_retain_their_recipes_and_solve_every_aligned_fiber(self):
        from bce_v2.algorithm_palette import AlgorithmPalette
        from bce_v2.coarse_methods import CoarseMethod, _compile_coarse_plan, _palette_paths
        from bce_v2.human_methods import _state_for_permutation
        from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
        from test_coarse_methods import BODIES

        builder = AlgorithmLibrary(self.analysis.loops, (), (), ())
        by_face = {generator.turn_sequence: generator for generator in self.analysis.loops.generators}

        def algorithm(identifier, word):
            proof = LoopExpression.sequence(*(LoopExpression.power(
                LoopExpression.loop(by_face[token[0]].id),
                2 if token.endswith("2") else -1 if token.endswith("'") else 1)
                for token in word.split()))
            return replace(builder.build_algorithm(LoopExpression.turns(word, proof)), id=identifier)

        turns = tuple(algorithm(word, word) for word in ("U", "U2", "U'"))
        palette = AlgorithmPalette.from_algorithms(
            tuple(algorithm(identifier, word) for identifier, word in BODIES.items()),
            setups=turns, adjustments=turns, allow_inverse=False)
        domain_cells = tuple(cell for block in self.plan.inventory.blocks
                             if block.orientation_order > 1 and
                             not set(block.cells).intersection((*EDGES, *CORNERS))
                             for cell in block.cells)
        domain = (c.BlockFeature("solve_blocks", domain_cells),)
        suffix = tuple(stage for stage in self.plan.stages if stage.feature in self.features)
        paths = tuple(_palette_paths(stage, self.plan.inventory, palette) for stage in suffix)
        u_recipe = next(record["id"] for record in palette.recipe_records
                        if record["adjustment_id"] == "U")
        selected = tuple(dict(table) for table in paths)
        unsolved = next(value for value in suffix[0].observations
                        if value != suffix[0].solved_observation)
        # A deliberately longer valid declaration proves compilation preserves
        # the chosen policy rather than silently replacing it with local paths.
        selected[0][unsolved] = (u_recipe,) * 4 + selected[0][unsolved]
        with patch("bce_v2.coarse_methods._palette_paths",
                   side_effect=AssertionError("selected policies must be retained")):
            method = _compile_coarse_plan(self.plan, palette, domain, stage_recipes=selected)
        self.assertEqual({(number, observation): recipe
                          for number, observation, recipe in method.case_recipes},
                         {(number, observation): recipe for number, table in enumerate(selected, 1)
                          for observation, recipe in table.items()})
        with patch("subprocess.run", side_effect=AssertionError("coarse replay is offline")):
            loaded = CoarseMethod.from_dict(method.to_dict())
            self.assertEqual(loaded.to_dict(), method.to_dict())
            for stage in loaded.stages:
                for case in stage.cases:
                    state = loaded.example_state(stage.number, case.observation)
                    self.assertTrue(loaded.apply(state).state.is_solved)
            aligned = suffix[2]
            target, queue = {tuple(range(48))}, [tuple(range(48))]
            for permutation in queue:
                for generator in aligned.group_after.strong_generators:
                    image = _then(permutation, generator.permutation)
                    if image not in target:
                        target.add(image)
                        queue.append(image)
            self.assertEqual(len(target), 48)
            states = set()
            for representative in aligned.representatives:
                for hidden in target:
                    permutation = _then(hidden, representative.permutation)
                    states.add(permutation)
                    self.assertEqual(_observation(self.plan.inventory.action(permutation),
                                                   aligned.block_index, aligned.feature.kind),
                                     representative.observation)
                    state = _state_for_permutation(self.plan.inventory.root_shape, permutation)
                    self.assertIsNone(state.scramble)
                    result = loaded.apply(state)
                    self.assertTrue(result.state.is_solved)
                    self.assertEqual(state.apply(result.turn_sequence), result.state)
            self.assertEqual(len(states), 288)

        failures = []
        omitted = tuple(dict(table) for table in selected)
        del omitted[0][unsolved]
        failures.append((omitted, "omits certified observations"))
        unknown = tuple(dict(table) for table in selected)
        unknown[0][unsolved] = ("not-declared",)
        failures.append((unknown, "outside the supplied palette"))
        stalled = tuple(dict(table) for table in selected)
        stalled[0][unsolved] = ()
        failures.append((stalled, "does not reach its certified goal"))
        broken_prior = tuple(dict(table) for table in selected)
        fourth_case = next(value for value in suffix[3].observations
                           if value != suffix[3].solved_observation)
        disruptive = next(recipe.id for recipe in palette.recipes
                          if recipe.permutation not in suffix[3].group_before)
        broken_prior[3][fourth_case] = (disruptive,)
        failures.append((broken_prior, "does not preserve preceding goals"))
        failures.append((selected[:-1], "omits certified stages"))
        with patch("bce_v2.coarse_methods._entry_correction",
                   side_effect=AssertionError("invalid policies fail before witness expansion")):
            for tables, reason in failures:
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    _compile_coarse_plan(self.plan, palette, domain, stage_recipes=tables)


@unittest.skipUnless(shutil.which("gap"), "GAP is required to construct exact stabilizers")
class BandagedAlignmentTests(unittest.TestCase):
    def test_the_same_alignment_action_compiles_and_loads_a_bandaged_method(self):
        analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=60)
        identity = tuple(range(48))
        generator = next(generator for generator in analysis.loops.generators
                         if generator.block_action.destinations !=
                         analysis.block_inventory.action(identity).destinations)
        group, current = [], identity
        while current not in group:
            group.append(current)
            current = _then(current, generator.permutation)
        self.assertEqual(current, identity)
        feature = c.BlockFeature(KIND, tuple(range(27)), tuple(group))
        features = (feature, *(c.BlockFeature("solve_block", block.cells)
                              for block in analysis.block_inventory.blocks))
        methods = [c.synthesize_human_method(analysis, strategy="manual", features=features,
                                            backend=backend, timeout=60)
                   for backend in ("explicit", "symbolic")]
        self.assertEqual([(stage.feature, stage.observations, stage.order_after)
                          for stage in methods[0].stages],
                         [(stage.feature, stage.observations, stage.order_after)
                          for stage in methods[1].stages])
        self.assertEqual(methods[0].stages[0].feature, feature)
        with patch("subprocess.run", side_effect=AssertionError("method replay is offline")):
            for original in methods:
                loaded = c.HumanMethod.from_dict(original.to_dict())
                self.assertEqual(loaded.to_dict(), original.to_dict())
                guide = loaded.write_guide()
                self.assertIn("allowed alignment", guide)
                self.assertIn("Equivalent placements:", guide)
                first = loaded.stages[0]
                indices = _feature_indices(loaded.inventory, first.feature)
                diagrams = c.recognition_stage_diagrams(loaded, 1)
                self.assertEqual(set(diagrams), set(first.observations))
                for observation, pictures in diagrams.items():
                    for picture in pictures:
                        self.assertEqual(picture.current_blocks, indices)
                        self.assertTrue(all(type(index) is int for index in picture.current_blocks))
                        self.assertTrue(picture.orientation_independent)
                        action = loaded.inventory.action(picture.state)
                        self.assertEqual(_observation(action, first.block_index, KIND), observation)
                        self.assertEqual(picture.phase, tuple(action.phases[index] for index in indices))
                        placements = tuple(action.destinations[index] for index in indices)
                        self.assertIn(placements, tuple(observation[offset:offset+len(indices)]
                                                       for offset in range(0, len(observation), len(indices))))
                if len(loaded.stages) > 1:
                    roles = c.recognition_block_roles(loaded, 2)
                    next_indices = set(_feature_indices(loaded.inventory, loaded.stages[1].feature))
                    moved = {index for permutation in feature.alignment_permutations
                             for index, destination in enumerate(loaded.inventory.action(permutation).destinations)
                             if index != destination} - next_indices
                    self.assertTrue(moved)
                    self.assertTrue(all(roles[index] == "unsolved" for index in moved))
                for stage in loaded.stages:
                    for case in stage.cases:
                        state = loaded.example_state(stage.number, case.observation)
                        self.assertTrue(loaded.apply(state).state.is_solved)
                if loaded.backend == "symbolic":
                    repertoire = c.template_human_repertoire(
                        loaded, allow_symmetry=False, select_chain=False,
                        max_trials=0, max_word_candidates=0, max_applications=0,
                        chunk_options={"max_candidates": 0, "max_chunks": 0, "max_word_moves": 0})
                    portable = c.HumanRepertoire.from_dict(repertoire.to_dict())
                    self.assertIn("Place up to alignment", portable.write_guide())
                    self.assertIn("Equivalent placements:", portable.write_guide())
                    for case in first.cases:
                        state = loaded.example_state(1, case.observation)
                        self.assertTrue(portable.apply(state).state.is_solved)


if __name__ == "__main__":
    unittest.main()
