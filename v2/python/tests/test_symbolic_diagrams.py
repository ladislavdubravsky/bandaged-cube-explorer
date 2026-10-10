"""Symbolic recognition pictures cover exact target orientation orbits."""

import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_diagrams import recognition_stage_diagrams
from bce_v2.human_methods import _observe


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare symbolic methods")
class SymbolicDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        analysis = c.analyze_isotropy(c.fixture("Alcatraz"), timeout=30)
        cls.explicit = c.synthesize_human_method(analysis, timeout=30)
        cls.symbolic = c.synthesize_human_method(analysis, backend="symbolic", timeout=45)

    def test_every_orientation_matches_exhaustive_prior_subgroup(self):
        method = self.symbolic
        members = set(self.explicit._permutations)
        actions = {p: method.inventory.action(p) for p in members}
        multiple_phases = False
        for stage in method.stages:
            pictures = recognition_stage_diagrams(method, stage.number)
            explicit_pictures = recognition_stage_diagrams(self.explicit, stage.number)
            self.assertEqual(set(pictures), set(stage.observations))
            for case in stage.cases:
                variants = pictures[case.observation]
                if stage.feature.kind == "place_block":
                    expected = {actions[p].phases[stage.block_index] for p in members
                                if _observe(actions[p], stage.block_index, stage.feature.kind) == case.observation}
                    multiple_phases |= len(expected) > 1
                    self.assertEqual({d.phase for d in variants}, expected)
                else:
                    self.assertEqual(len(variants), 1)
                self.assertEqual({d.phase for d in variants},
                                 {d.phase for d in explicit_pictures[case.observation]})
                declared_phase = method.inventory.action(case.representative).phases[stage.block_index]
                declared = next(d for d in variants if d.phase == declared_phase)
                self.assertEqual(tuple(declared.state.sticker_permutation), case.representative)
                for diagram in variants:
                    permutation = tuple(diagram.state.sticker_permutation)
                    self.assertIn(permutation, members)
                    self.assertEqual(_observe(actions[permutation], stage.block_index, stage.feature.kind),
                                     case.observation)
                    self.assertEqual(diagram.current_blocks, (stage.block_index,))
                    self.assertEqual(diagram.state.shape, method.reference_shape)
            members = {p for p in members if _observe(actions[p], stage.block_index,
                       stage.feature.kind) == stage.solved_observation}
        self.assertTrue(multiple_phases)

    def test_loaded_symbolic_diagrams_are_offline_and_never_iterate_group_elements(self):
        record = self.symbolic.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("diagram loading and generation are offline")):
            loaded = c.HumanMethod.from_dict(record)
            # Certificates implement membership, but deliberately have no
            # full-element iterator. Diagram construction must use feature BFS.
            self.assertFalse(hasattr(loaded._permutations, "__iter__"))
            for stage in loaded.stages:
                pictures = recognition_stage_diagrams(loaded, stage.number)
                expected = recognition_stage_diagrams(self.symbolic, stage.number)
                self.assertEqual(pictures, expected)


if __name__ == "__main__":
    unittest.main()
