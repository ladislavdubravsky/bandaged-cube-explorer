"""Candidate targets use the full residual group and the supplied vocabulary."""

from itertools import permutations, product
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _inverse


BODY = "F R U R' U' F'"
TOP_EDGE_CELLS = frozenset((c.UR, c.UF, c.UL, c.UB))
TOP_CORNER_CELLS = frozenset((c.UFR, c.UFL, c.UBL, c.UBR))
F2L_CELLS = (c.DFR, c.DFL, c.DBL, c.DBR,
             c.DR, c.DF, c.DL, c.DB, c.FR, c.FL, c.BL, c.BR)


def witnessed_algorithms(analysis, words):
    """Use exact original face-loop witnesses for the declared taught words."""
    loops = analysis.loops.generators
    leaves = {}
    for generator in loops:
        leaf = c.LoopExpression.loop(generator.id)
        leaves[generator.permutation] = leaf
        leaves[_inverse(generator.permutation)] = c.LoopExpression.power(leaf, -1)
        square = c.State(analysis.block_inventory.root_shape).apply(
            generator.turn_sequence + " " + generator.turn_sequence).sticker_permutation
        leaves[tuple(square)] = c.LoopExpression.power(leaf, 2)
    lengths = tuple((generator.id, generator.htm_length) for generator in loops)
    result = []
    for identifier, word in words.items():
        witness = c.LoopExpression.sequence(*(leaves[tuple(c.State().apply(move).sticker_permutation)]
                                             for move in word.split()))
        effect = tuple(c.State(analysis.block_inventory.root_shape).apply(word).sticker_permutation)
        result.append(c.LoopAlgorithm(identifier, c.LoopExpression.turns(word, witness),
                                      effect, word, analysis.block_inventory, lengths, loops))
    return tuple(result)


def parity(permutation):
    return sum(permutation[i] > permutation[j]
               for i in range(len(permutation)) for j in range(i + 1, len(permutation))) % 2


def target_for(candidates, cells):
    return next(candidate for candidate in candidates if frozenset(candidate.feature.cells) == cells)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares independently certified current groups")
class AlgorithmInformedTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from bce_v2.algorithm_targets import discover_algorithm_targets
        cls.discover = staticmethod(discover_algorithm_targets)
        cls.analysis = c.analyze_isotropy(c.Shape(), timeout=45)
        features = tuple(c.BlockFeature("solve_block", (cell,)) for cell in F2L_CELLS)
        features += tuple(c.BlockFeature("solve_block", block.cells)
                          for block in cls.analysis.block_inventory.blocks)
        cls.plan = c.plan_human_stages(cls.analysis, strategy="manual", features=features,
                                      backend="symbolic", timeout=90)
        cls.group = cls.plan.stages[11].group_after
        if cls.group.order != 62208:
            raise AssertionError("the protected first-two-layer subgroup changed")
        cls.palette = witnessed_algorithms(cls.analysis,
                                          {"U": "U", "U2": "U2", "U'": "U'", "A": BODY})
        with patch("subprocess.run", side_effect=AssertionError("prepared discovery is offline")):
            cls.candidates = cls.discover(cls.analysis.block_inventory, cls.group, cls.palette,
                                         max_observations=128, max_candidates=32)

    def test_available_actions_propose_grouped_anonymous_edge_and_corner_orientations(self):
        edge = target_for(self.candidates, TOP_EDGE_CELLS)
        corner = target_for(self.candidates, TOP_CORNER_CELLS)
        self.assertEqual(edge.feature.kind, "orient_slots")
        self.assertEqual(corner.feature.kind, "orient_slots")
        self.assertEqual((len(edge.observations), edge.covered_count), (8, 8))
        self.assertEqual((len(corner.observations), corner.covered_count), (27, 27))
        self.assertEqual(edge.mean_htm, 10.375)
        self.assertEqual(set(edge.preserving_algorithm_ids), {"U", "U2", "U'"})

    def test_partial_vocabulary_reports_missing_full_group_cases(self):
        with patch("subprocess.run", side_effect=AssertionError("coverage is checked offline")):
            candidates = self.discover(self.analysis.block_inventory, self.group, self.palette[-1:],
                                       max_observations=128, max_candidates=32)
        edge = target_for(candidates, TOP_EDGE_CELLS)
        self.assertEqual((len(edge.observations), edge.covered_count), (8, 3))
        self.assertIsNone(edge.mean_htm)

    def test_region_closed_only_under_palette_cannot_be_a_full_group_target(self):
        with patch("subprocess.run", side_effect=AssertionError("full-group orbit validation is offline")):
            candidates = self.discover(self.analysis.block_inventory, self.plan.group, self.palette,
                                       max_observations=8, max_candidates=32)
        self.assertFalse(any(frozenset(candidate.feature.cells) in
                             (TOP_EDGE_CELLS, TOP_CORNER_CELLS) for candidate in candidates))
        for candidate in candidates:
            slots = set(candidate.block_indices)
            for generator in self.plan.group.strong_generators:
                action = self.analysis.block_inventory.action(generator.permutation)
                self.assertEqual({action.destinations[slot] for slot in slots}, slots)

    def test_case_caps_do_not_turn_a_truncated_orbit_into_a_complete_stage(self):
        with patch("subprocess.run", side_effect=AssertionError("bounded orbit discovery is offline")):
            below = self.discover(self.analysis.block_inventory, self.group, self.palette,
                                  max_observations=7, max_candidates=32)
            exact = self.discover(self.analysis.block_inventory, self.group, self.palette,
                                  max_observations=8, max_candidates=32)
        self.assertFalse(any(frozenset(candidate.feature.cells) == TOP_EDGE_CELLS
                             for candidate in below))
        edge = target_for(exact, TOP_EDGE_CELLS)
        self.assertEqual((len(edge.observations), edge.covered_count), (8, 8))
        self.assertFalse(any(frozenset(candidate.feature.cells) == TOP_CORNER_CELLS
                             for candidate in exact))

    def test_fixed_slots_do_not_consume_the_active_candidate_budget(self):
        with patch("subprocess.run", side_effect=AssertionError("active target discovery is offline")):
            candidates = self.discover(self.analysis.block_inventory, self.group, self.palette,
                                       max_observations=128, max_candidates=1)
        self.assertEqual(len(candidates), 1)
        target = candidates[0]
        self.assertIn(frozenset(target.feature.cells), (TOP_EDGE_CELLS, TOP_CORNER_CELLS))
        self.assertTrue(target.complete)
        self.assertGreater(target.case_count, 1)

    def test_compiled_orientation_recipes_add_no_opaque_learned_bodies(self):
        from bce_v2.symbolic_chain_search import _SEARCH_DEFAULTS, _compile_dictionary_policy
        target = target_for(self.candidates, TOP_EDGE_CELLS)
        features = tuple(stage.feature for stage in self.plan.stages[:12]) + (target.feature,)
        features += tuple(stage.feature for stage in self.plan.stages[12:])
        plan = c.plan_human_stages(self.analysis, strategy="manual", features=features,
                                  backend="symbolic", timeout=90)
        settings = {**_SEARCH_DEFAULTS, "mode": "original", "max_states": 0}
        _, method, _ = _compile_dictionary_policy(plan, self.palette, settings, target_policies=(target,))
        stage = next(stage for stage in method.stages if stage.feature == target.feature)
        self.assertEqual((stage.order_before, stage.order_after, stage.case_count), (62208, 7776, 8))
        algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
        permitted = {key for algorithm in self.palette for key in algorithm.expression.memory_keys
                     if key[0] == "turns"}
        for case in stage.cases:
            if case.algorithm_id is None:
                continue
            algorithm = algorithms[case.algorithm_id]
            taught = {key for key in algorithm.expression.memory_keys if key[0] == "turns"}
            self.assertLessEqual(taught, permitted)
            self.assertTrue(all(generator.htm_length == 1 for generator in method.generators
                                if generator.id in algorithm.expression.base_ids))
            source = method.example_state(stage.number, case.observation)
            after = source.apply(algorithm.turn_sequence)
            self.assertEqual(after.flips, [0] * 12)
            self.assertEqual(after.corners[4:], list(range(4, 8)))
            self.assertEqual(after.twists[4:], [0] * 4)
            self.assertEqual(after.edges[4:], list(range(4, 12)))

    def test_native_anonymous_observations_and_transitions_ignore_edge_identities(self):
        from bce_v2.human_chains import _feature_successor, _observation
        edge = target_for(self.candidates, TOP_EDGE_CELLS)
        inventory, slots = self.analysis.block_inventory, edge.block_indices
        slot_to_cubie = {next(index for index, block in enumerate(inventory.blocks)
                              if block.cells == (cell,)): cubie
                         for cubie, cell in enumerate((c.UR, c.UF, c.UL, c.UB))}
        algorithms = {algorithm.id: algorithm for algorithm in self.palette}
        physical = {}
        for observation, recipe, cost in zip(edge.observations, edge.recipes, edge.costs):
            self.assertIsNotNone(recipe)
            self.assertEqual(sum(algorithms[identifier].htm_length for identifier in recipe), cost)
            physical[observation] = " ".join(algorithms[identifier].turn_sequence for identifier in recipe)
        masks = tuple(mask for mask in product((0, 1), repeat=4) if sum(mask) % 2 == 0)
        observations = set()
        for order in permutations(range(4)):
            corners = ([1, 0, 2, 3, 4, 5, 6, 7] if parity(order) else list(range(8)))
            for mask in masks:
                source = c.State.from_cubies(corners=corners, twists=[0] * 8,
                                            edges=list(order) + list(range(4, 12)),
                                            flips=list(mask) + [0] * 8)
                self.assertIsNone(source.scramble)
                observation = _observation(inventory.action(source), slots, "orient_slots")
                self.assertEqual(observation, tuple(mask[slot_to_cubie[slot]] for slot in slots))
                observations.add(observation)
                for algorithm in self.palette:
                    after = source.apply(algorithm.turn_sequence)
                    expected = _feature_successor(observation, algorithm.block_action,
                                                  inventory, slots, "orient_slots")
                    self.assertEqual(_observation(inventory.action(after), slots, "orient_slots"), expected)
                    self.assertEqual(after.corners[4:], list(range(4, 8)))
                    self.assertEqual(after.twists[4:], [0] * 4)
                    self.assertEqual(after.edges[4:], list(range(4, 12)))
                    self.assertEqual(after.flips[4:], [0] * 8)
                corrected = source.apply(physical[observation])
                self.assertEqual(corrected.flips, [0] * 12)
                self.assertEqual(corrected.corners[4:], list(range(4, 8)))
                self.assertEqual(corrected.twists[4:], [0] * 4)
                self.assertEqual(corrected.edges[4:], list(range(4, 12)))
        self.assertEqual(observations, set(edge.observations))

    def test_outside_subgroup_algorithms_are_not_used_by_the_target_policy(self):
        extra = witnessed_algorithms(self.analysis, {"R": "R"})
        with patch("subprocess.run", side_effect=AssertionError("eligible palette filtering is offline")):
            candidates = self.discover(self.analysis.block_inventory, self.group, (*self.palette, *extra))
        edge = target_for(candidates, TOP_EDGE_CELLS)
        self.assertEqual(edge, target_for(self.candidates, TOP_EDGE_CELLS))
        self.assertNotIn("R", edge.available_algorithm_ids)

    def test_invalid_budget_and_physical_effect_records_are_rejected(self):
        from dataclasses import replace
        options = (({"max_observations": True}, TypeError), ({"max_candidates": 1.5}, TypeError),
                   ({"max_observations": -1}, ValueError), ({"max_candidates": -1}, ValueError))
        with patch("subprocess.run", side_effect=AssertionError("public validation is offline")):
            for kwargs, error in options:
                with self.subTest(kwargs=kwargs), self.assertRaises(error):
                    self.discover(self.analysis.block_inventory, self.group, self.palette, **kwargs)
            forged = replace(self.palette[-1], turn_sequence="U")
            with self.assertRaisesRegex(ValueError, "witness"):
                self.discover(self.analysis.block_inventory, self.group, (forged,))
            with self.assertRaisesRegex(ValueError, "unique"):
                self.discover(self.analysis.block_inventory, self.group, (*self.palette, self.palette[0]))

    def test_candidates_are_deterministic_and_leave_the_supplied_vocabulary_unchanged(self):
        original = tuple(algorithm.to_dict() for algorithm in self.palette)
        with patch("subprocess.run", side_effect=AssertionError("repeat discovery is offline")):
            repeated = self.discover(self.analysis.block_inventory, self.group, self.palette,
                                     max_observations=128, max_candidates=32)
        self.assertEqual(repeated, self.candidates)
        self.assertEqual(tuple(algorithm.to_dict() for algorithm in self.palette), original)
        self.assertEqual(sum(algorithm.htm_length > 4 for algorithm in self.palette), 1)


if __name__ == "__main__":
    unittest.main()
