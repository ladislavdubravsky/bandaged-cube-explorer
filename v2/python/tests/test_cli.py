"""The batch commands use the same public Python objects and export contracts."""

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

import bce_v2 as c
from bce_v2.__main__ import main


class CommandTests(unittest.TestCase):
    def invoke(self, *arguments):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, output.getvalue(), errors.getvalue()

    def test_inspect_replay_and_shape_solution(self):
        status, output, errors = self.invoke("inspect", "Alcatraz")
        self.assertEqual((status, errors), (0, ""))
        initial = c.fixture("Alcatraz")
        self.assertEqual(json.loads(output)["shape"], initial.labels)
        status, output, errors = self.invoke("replay", "Alcatraz", "F R2")
        self.assertEqual((status, errors), (0, ""))
        scrambled = c.State(initial).apply("F R2")
        self.assertEqual(json.loads(output)["corners"], scrambled.corners)
        self.assertEqual(json.loads(output)["shape"], scrambled.shape.labels)
        status, output, errors = self.invoke("solve", "Alcatraz", "F R2", "--metric", "HTM")
        self.assertEqual((status, errors), (0, ""))
        record = json.loads(output)
        restored = scrambled.apply(record["shape_solution"])
        self.assertEqual(restored.shape, initial)
        self.assertEqual(record["metric"], "HTM")
        self.assertEqual(record["colored_solved_after"], restored.is_solved)

    def test_versioned_file_input_and_graph_export(self):
        state = c.State(c.fixture("Bicube Fuse"))
        with tempfile.TemporaryDirectory() as directory:
            puzzle = Path(directory) / "puzzle.json"
            exported = Path(directory) / "graph.json"
            c.save_puzzle(state, puzzle)
            status, output, errors = self.invoke("inspect", str(puzzle))
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(json.loads(output)["shape"], state.shape.labels)
            status, output, errors = self.invoke("explore", str(puzzle), "--output", str(exported))
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(json.loads(output), {
                "shapes": 121, "arcs": 168, "metric": "QTM", "complete": True})
            record = json.loads(exported.read_text())
            self.assertTrue(record["complete"])
            self.assertEqual(len(record["arcs"]), 168)

    def test_bounded_exploration_exit_status(self):
        status, output, errors = self.invoke("explore", "Alcatraz", "--max-vertices", "3")
        self.assertEqual((status, errors), (2, ""))
        record = json.loads(output)
        self.assertFalse(record["complete"])
        self.assertEqual(record["shapes"], 3)

    def test_invalid_input_exit_status(self):
        for arguments in (("inspect", "unknown-puzzle"), ("replay", "Alcatraz", "xyz"),
                          ("explore", "Alcatraz", "--max-vertices", "-1")):
            with self.subTest(arguments=arguments):
                status, output, errors = self.invoke(*arguments)
                self.assertEqual((status, output), (1, ""))
                self.assertIn("bce-v2:", errors)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("{broken")
            status, output, errors = self.invoke("inspect", str(path))
            self.assertEqual((status, output), (1, ""))
            self.assertIn("bce-v2:", errors)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "optional plots extra")
    def test_render_command(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shape.png"
            status, output, errors = self.invoke("render", "Alcatraz", "--output", str(path))
            self.assertEqual((status, output, errors), (0, "", ""))
            self.assertGreater(path.stat().st_size, 1000)
        plt.close("all")


if __name__ == "__main__":
    unittest.main()
