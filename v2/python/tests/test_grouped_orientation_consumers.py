"""Grouped slot stages remain recognizable, replayable, and portable."""

from copy import deepcopy
import importlib.util
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_method_io import _fingerprint


def imported(state):
    return c.State.from_cubies(state.specification, corners=state.corners, twists=state.twists,
                              edges=state.edges, flips=state.flips)


@unittest.skipUnless(shutil.which("gap"), "GAP prepares certified test methods")
class GroupedOrientationConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.explicit = c.plan_human_stages(c.fixture("Alcatraz"), timeout=45)
        cls.feature = c.BlockFeature("orient_slots", (c.UR, c.UF))
        features = (cls.feature, *(c.BlockFeature("solve_block", block.cells)
                                  for block in cls.explicit.inventory.blocks))
        cls.methods = tuple(c.synthesize_human_method(cls.explicit.analysis, strategy="manual",
                                                      features=features, backend=backend, timeout=60)
                            for backend in ("explicit", "symbolic"))
        initial = c.State(cls.explicit.inventory.root_shape)
        cls.states = tuple(imported(initial.apply(cls.explicit.group.witness(permutation).expanded_moves(
            cls.explicit.group.generators))) for permutation in cls.explicit.group.permutations)

    def test_grouped_stage_reduces_only_orientation_and_preserves_piece_freedom(self):
        explicit, symbolic = self.methods
        for method in self.methods:
            stage = method.stages[0]
            self.assertEqual(stage.feature, self.feature)
            self.assertEqual(stage.observations, ((0, 0), (1, 1)))
            self.assertEqual((stage.order_before, stage.order_after, stage.index), (324, 162, 2))
            self.assertIsInstance(stage.block_index, tuple)
            self.assertEqual(method.terminal_order, 1)
        self.assertEqual([(stage.feature, stage.order_before, stage.order_after, stage.observations)
                          for stage in explicit.stages],
                         [(stage.feature, stage.order_before, stage.order_after, stage.observations)
                          for stage in symbolic.stages])

    def test_complete_methods_and_portable_copies_solve_every_history_free_state_offline(self):
        from bce_v2.human_methods import _observe
        with patch("subprocess.run", side_effect=AssertionError("application and loading are offline")):
            for original in self.methods:
                loaded = c.HumanMethod.from_dict(original.to_dict())
                self.assertEqual(loaded.to_dict(), original.to_dict())
                self.assertIn("Orient slots", loaded.write_guide())
                for method in (original, loaded):
                    for source in self.states:
                        self.assertIsNone(source.scramble)
                        result = method.apply(source)
                        self.assertEqual(result.status, "solved")
                        self.assertTrue(result.state.is_solved)
                        self.assertEqual(source.apply(result.turn_sequence), result.state)
                        for step in result.steps:
                            stage = method.stages[step.stage_number - 1]
                            action = method.inventory.action(step.after)
                            self.assertEqual(_observe(action, stage.block_index, stage.feature.kind),
                                             stage.solved_observation)

    def test_recognition_diagrams_show_all_slot_phases_without_piece_identity_colors(self):
        for method in self.methods:
            stage = method.stages[0]
            diagrams = c.recognition_stage_diagrams(method, 1)
            self.assertEqual(set(diagrams), set(stage.observations))
            for observation, pictures in diagrams.items():
                self.assertEqual(len(pictures), 1)
                diagram = pictures[0]
                self.assertEqual(diagram.phase, observation)
                self.assertEqual(diagram.orientation_slots, stage.block_index)
                self.assertEqual(len(diagram.current_blocks), len(stage.block_index))
                self.assertEqual({cell for cell, role in enumerate(diagram.cell_roles) if role == "current"},
                                 {c.UR, c.UF})
                self.assertEqual({role for role in diagram.sticker_roles if role == "current"}, {"current"})

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Matplotlib renders recognition colors")
    def test_anonymous_orientation_pictures_distinguish_different_phase_patterns(self):
        from bce_v2.human_diagram_render import recognition_diagram_colors
        for method in self.methods:
            diagrams = c.recognition_stage_diagrams(method, 1)
            color_patterns = {recognition_diagram_colors(pictures[0]) for pictures in diagrams.values()}
            self.assertEqual(len(color_patterns), len(method.stages[0].observations),
                             "different phase patterns must be distinguishable in their recognition pictures")

    def test_shared_template_guides_retain_grouped_stage_coverage_and_portability(self):
        with patch("subprocess.run", side_effect=AssertionError("prepared shared policies are offline")):
            for method in self.methods:
                repertoire = c.template_human_repertoire(
                    method, allow_symmetry=False, select_chain=False,
                    max_trials=0, max_word_candidates=0, max_applications=0,
                    chunk_options={"max_candidates": 0, "max_chunks": 0, "max_word_moves": 0})
                loaded = c.HumanRepertoire.from_dict(repertoire.to_dict())
                self.assertEqual(loaded.to_dict(), repertoire.to_dict())
                self.assertIn("Orient slots", loaded.write_guide())
                source_algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
                selected_algorithms = {algorithm.id: algorithm for algorithm in loaded.method.algorithms}
                for before, after in zip(method.stages, loaded.method.stages):
                    self.assertEqual(before.feature, after.feature)
                    self.assertEqual(before.observations, after.observations)
                    for old_case, new_case in zip(before.cases, after.cases):
                        if old_case.algorithm_id is None:
                            self.assertIsNone(new_case.algorithm_id)
                        elif method.backend == "symbolic":
                            self.assertEqual(source_algorithms[old_case.algorithm_id].turn_sequence,
                                             selected_algorithms[new_case.algorithm_id].turn_sequence)
                self.assertLessEqual(loaded.method.additive_costs()["htm"]["mean"],
                                     method.additive_costs()["htm"]["mean"])
                for case in loaded.method.stages[0].cases:
                    source = loaded.method.example_state(1, case.observation)
                    if method.backend == "symbolic":
                        self.assertEqual(loaded.apply(source).turn_sequence, method.apply(source).turn_sequence)
                    self.assertTrue(loaded.apply(source).state.is_solved)

    def test_portable_slot_handle_tampering_is_rejected_even_after_refingerprinting(self):
        for method in self.methods:
            record = method.to_dict()
            self.assertIsInstance(record["stages"][0]["block_index"], list)
            mutations = []
            changed = deepcopy(record)
            changed["stages"][0]["block_index"] = changed["stages"][0]["block_index"][0]
            mutations.append(changed)
            changed = deepcopy(record)
            changed["stages"][0]["solved_observation"] = [0]
            mutations.append(changed)
            changed = deepcopy(record)
            changed["stages"][0]["cases"][1]["observation"] = [1, 0]
            mutations.append(changed)
            with patch("subprocess.run", side_effect=AssertionError("portable checks are offline")):
                for changed in mutations:
                    changed["fingerprint"] = _fingerprint(changed)
                    with self.assertRaises((ValueError, c.GapError)):
                        c.HumanMethod.from_dict(changed)

    def test_real_symmetric_bandaged_footprints_support_order_two_and_four_phases(self):
        # The five-cell U-face snake is connected and symmetric under U2,
        # while U2 also exchanges two separate asymmetric corner-edge pairs.
        labels = [3] * 9 + [4] * 18
        for cell in (c.UBL, c.UB, c.U, c.UF, c.UFR):
            labels[cell] = 1
        for cell in (c.UBR, c.UR):
            labels[cell] = 2
        for shape, order in ((c.Shape(labels), 2), (c.Shape([1] * 9 + [2] * 18), 4)):
            inventory = c.BlockInventory(shape)
            block = next(block for block in inventory.blocks if block.orientation_order == order)
            feature = c.BlockFeature("orient_slots", block.cells)
            methods = tuple(c.synthesize_human_method(shape, strategy="manual", features=(feature,),
                                                      backend=backend, timeout=45)
                            for backend in ("explicit", "symbolic"))
            with patch("subprocess.run", side_effect=AssertionError("bandaged execution is offline")):
                for original in methods:
                    loaded = c.HumanMethod.from_dict(original.to_dict())
                    stage = loaded.stages[0]
                    self.assertEqual(stage.observations, tuple((phase,) for phase in range(order)))
                    self.assertEqual((stage.order_before, stage.order_after), (order, 1))
                    for observation in stage.observations:
                        source = loaded.example_state(1, observation)
                        self.assertIsNone(source.scramble)
                        self.assertEqual(loaded.recognize(source).status,
                                         "solved" if observation == (0,) else "ready")
                        self.assertTrue(loaded.apply(source).state.is_solved)


if __name__ == "__main__":
    unittest.main()
