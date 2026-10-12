"""Collection goals use the actual inventory and certified endpoint actions."""

from copy import deepcopy
from itertools import product
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_chains import _feature_successor, _observation, _resolve_feature


class CompositeActionTests(unittest.TestCase):
    def test_mixed_corner_edge_assembly_is_a_conjunction_of_real_components(self):
        inventory = c.BlockInventory()
        feature = c.BlockFeature("solve_blocks", (c.UFR, c.FR))
        blocks = _resolve_feature(inventory, feature)
        self.assertEqual(len(blocks), 2)
        for word, correction in product(("", "R U F'", "R2 B D' F2"), ("R", "U' F2", "L B2")):
            before = c.State().apply(word)
            value = _observation(inventory.action(before), blocks, feature.kind)
            action = inventory.action(c.State().apply(correction))
            after = before.apply(correction)
            self.assertEqual(_feature_successor(value, action, inventory, blocks, feature.kind),
                             _observation(inventory.action(after), blocks, feature.kind))
            self.assertEqual(value, tuple(v for block in blocks
                                         for v in _observation(inventory.action(before), block, "solve_block")))

    def test_membership_ignores_internal_assignment_and_phase(self):
        inventory = c.BlockInventory()
        feature = c.BlockFeature("occupy_slots", (c.UR, c.UF, c.UL, c.UB))
        blocks = _resolve_feature(inventory, feature)
        identity = _observation(inventory.action(c.State()), blocks, feature.kind)
        self.assertEqual(_observation(inventory.action(c.State().apply("U")), blocks, feature.kind), identity)
        self.assertNotEqual(_observation(inventory.action(c.State().apply("R")), blocks, feature.kind), identity)
        for kind in ("place_blocks", "occupy_slots"):
            before = c.State().apply("R U F'")
            observation = _observation(inventory.action(before), blocks, kind)
            action = inventory.action(c.State().apply("B L2"))
            self.assertEqual(_feature_successor(observation, action, inventory, blocks, kind),
                             _observation(inventory.action(before.apply("B L2")), blocks, kind))

    def test_partial_fused_components_are_rejected_for_every_collection_kind(self):
        inventory = c.BlockInventory(c.Shape([1]*9 + [2]*18))
        for kind in ("place_blocks", "solve_blocks", "occupy_slots"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "complete reference blocks"):
                _resolve_feature(inventory, c.BlockFeature(kind, (c.UBL,)))


@unittest.skipUnless(shutil.which("gap"), "GAP prepares exact test chains")
class CompositeChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = c.plan_human_stages(c.fixture("Alcatraz"), timeout=60)
        cls.reference = c.State(cls.plan.inventory.root_shape)
        cls.states = []
        for permutation in cls.plan.group.permutations:
            state = cls.reference.apply(cls.plan.group.witness(permutation).expanded_moves(cls.plan.group.generators))
            cls.states.append(c.State.from_cubies(state.specification, corners=state.corners,
                                                 twists=state.twists, edges=state.edges, flips=state.flips))

    def test_explicit_and_symbolic_collections_solve_all_hidden_states_and_load_offline(self):
        for kind in ("place_blocks", "solve_blocks", "occupy_slots"):
            cells = (c.UBR, c.UFL) if kind == "occupy_slots" else (c.UR, c.UF)
            feature = c.BlockFeature(kind, cells)
            tail = tuple(c.BlockFeature("solve_block", block.cells) for block in self.plan.inventory.blocks)
            methods = [c.synthesize_human_method(self.plan.analysis, strategy="manual",
                        features=(feature, *tail), backend=backend, timeout=60)
                       for backend in ("explicit", "symbolic")]
            self.assertEqual([(s.feature, s.observations, s.order_after) for s in methods[0].stages],
                             [(s.feature, s.observations, s.order_after) for s in methods[1].stages])
            for original in methods:
                with patch("subprocess.run", side_effect=AssertionError("portable methods are offline")):
                    loaded = c.HumanMethod.from_dict(original.to_dict())
                    self.assertEqual(loaded.to_dict(), original.to_dict())
                    self.assertIn("Recognition pattern", loaded.write_guide())
                    for state in self.states:
                        result = loaded.apply(state)
                        self.assertTrue(result.state.is_solved)
                        self.assertEqual(state.apply(result.turn_sequence), result.state)
                    stage = loaded.stages[0]
                    diagrams = c.recognition_stage_diagrams(loaded, 1)
                    self.assertEqual(set(diagrams), set(stage.observations))
                    self.assertTrue(all(len(pictures[0].current_blocks) == 2 for pictures in diagrams.values()))
                    if kind == "solve_blocks" and loaded.backend == "symbolic":
                        repertoire = c.template_human_repertoire(
                            loaded, allow_symmetry=False, select_chain=False,
                            max_trials=0, max_word_candidates=0, max_applications=0,
                            chunk_options={"max_candidates": 0, "max_chunks": 0, "max_word_moves": 0})
                        portable = c.HumanRepertoire.from_dict(repertoire.to_dict())
                        self.assertIn("Collection pattern", portable.write_guide())
                        for case in stage.cases:
                            self.assertTrue(portable.apply(loaded.example_state(1, case.observation)).state.is_solved)

    def test_tuple_handle_tampering_is_rejected(self):
        features = (c.BlockFeature("solve_blocks", (c.UR, c.UF)),
                    *(c.BlockFeature("solve_block", b.cells) for b in self.plan.inventory.blocks))
        plan = c.plan_human_stages(self.plan.analysis, strategy="manual", features=features,
                                   backend="symbolic", timeout=60)
        record = deepcopy(plan.to_dict())
        record["stages"][0]["block_index"].reverse()
        from bce_v2.symbolic_chains import symbolic_plan_from_dict
        with self.assertRaises(c.GapError):
            symbolic_plan_from_dict(record, plan.inventory, plan.analysis.loops.generators)


if __name__ == "__main__":
    unittest.main()
