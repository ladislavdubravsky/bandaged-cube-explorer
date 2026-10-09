"""Live-kernel refreshes restore current guides without invalidating puzzles."""

from importlib import import_module, util
from pathlib import Path
import unittest

import bce_v2 as c
from bce_v2.notebook import refresh_renderers


RESULTS = Path(__file__).resolve().parents[2] / "research-results"


class NotebookRendererRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repertoire = c.load_human_repertoire(RESULTS / "alcatraz-execution-repertoire.json")

    def tearDown(self):
        refresh_renderers()

    def test_import_reuses_stale_renderer_but_refresh_updates_existing_method(self):
        renderer = import_module("bce_v2.human_repertoire_render")
        renderer.repertoire_guide = lambda *args, **kwargs: "stale guide from the open kernel"
        self.assertIs(import_module("bce_v2.human_repertoire_render"), renderer)
        self.assertIs(import_module("bce_v2"), c)
        self.assertEqual(self.repertoire.write_guide(), "stale guide from the open kernel")

        refresh_renderers()
        guide = self.repertoire.write_guide()
        self.assertIn("| Turn sequence | Block action | Structure |", guide)
        self.assertNotIn("Before starting", guide)
        self.assertNotIn("Recognition colors", guide)

    def test_refresh_preserves_classes_native_engine_and_existing_objects(self):
        identities = (c.State, c.Shape, c.HumanRepertoire, c.HumanMacroRecipe,
                      c.DiagramMode, c._native)
        solved = c.State(self.repertoire.method.reference_shape)
        record = self.repertoire.to_dict()
        refresh_renderers()
        self.assertEqual(identities, (c.State, c.Shape, c.HumanRepertoire, c.HumanMacroRecipe,
                                     c.DiagramMode, c._native))
        self.assertIsInstance(solved, c.State)
        self.assertEqual(self.repertoire.recognize(solved).status, "solved")
        self.assertEqual(self.repertoire.to_dict(), record)

    @unittest.skipUnless(util.find_spec("matplotlib") is not None, "optional plots extra")
    def test_refresh_updates_bound_formatter_and_dependencies_on_repeated_evaluation(self):
        diagram_renderer = import_module("bce_v2.human_diagram_render")
        for _ in range(2):
            c.structured_move_notation = lambda *args: "stale formatting"
            diagram_renderer.recognition_diagram_colors = lambda *args, **kwargs: "stale colors"
            refresh_renderers()
            self.assertEqual(c.structured_move_notation("R U' B' U R'"), "B'^(U R')")
            self.assertIs(c.structured_move_notation,
                          import_module("bce_v2.human_move_notation").structured_move_notation)
            colors = diagram_renderer.recognition_diagram_colors(self.diagram())
            self.assertIsInstance(colors, tuple)
            self.assertEqual(len(colors), 54)

    def diagram(self):
        return next(iter(c.recognition_stage_diagrams(self.repertoire, 1).values()))[0]


if __name__ == "__main__":
    unittest.main()
