"""The batch commands use the same public Python objects and export contracts."""

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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

    def test_isotropy_loops_export_without_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "loops.json"
            missing_gap = str(Path(directory) / "missing-gap")
            status, output, errors = self.invoke(
                "isotropy", "Bicube Fuse", "--loops-only",
                "--gap-executable", missing_gap, "--output", str(exported))
            self.assertEqual((status, errors), (0, ""))
            expected = c.isotropy_loops(c.fixture("Bicube Fuse")).to_dict(include_moves=True)
            self.assertEqual(json.loads(output), expected)
            self.assertEqual(json.loads(exported.read_text()), expected)

    def test_isotropy_missing_gap_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_gap = str(Path(directory) / "missing-gap")
            status, output, errors = self.invoke(
                "isotropy", "Bicube Fuse", "--gap-executable", missing_gap)
            self.assertEqual((status, output), (1, ""))
            self.assertIn("bce-v2:", errors)
            self.assertIn("GAP", errors)

    @unittest.skipUnless(shutil.which("gap"), "optional GAP executable")
    def test_isotropy_analysis_command(self):
        status, output, errors = self.invoke("isotropy", "Bicube Fuse", "--timeout", "30")
        self.assertEqual((status, errors), (0, ""))
        expected = c.analyze_isotropy(c.fixture("Bicube Fuse"), timeout=30).to_dict(include_moves=True)
        self.assertEqual(json.loads(output), expected)

    def test_solve_loops_options_exports_and_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "solution.json"
            for result_status, expected_exit in (("solved", 0), ("unreachable", 3),
                                                 ("limit_reached", 2)):
                with self.subTest(status=result_status):
                    record = {"status": result_status, "solution": None}
                    result = SimpleNamespace(status=result_status, to_dict=lambda: record)
                    with patch("bce_v2.__main__.solve_colored_loops", return_value=result) as solve:
                        status, output, errors = self.invoke(
                            "solve-loops", "Alcatraz", "F R2", "--metric", "htm",
                            "--gap-executable", "custom-gap", "--timeout", "5.5",
                            "--max-expanded-moves", "100", "--output", str(exported))
                    self.assertEqual((status, errors), (expected_exit, ""))
                    self.assertEqual(json.loads(output), record)
                    self.assertEqual(json.loads(exported.read_text()), record)
                    solve.assert_called_once_with(
                        c.State(c.fixture("Alcatraz")).apply("F R2"), metric="HTM",
                        gap_executable="custom-gap", timeout=5.5, max_expanded_moves=100)

    def test_solve_loops_backend_error_exit_status(self):
        with patch("bce_v2.__main__.solve_colored_loops", side_effect=RuntimeError("GAP failed")):
            status, output, errors = self.invoke("solve-loops", "Bicube Fuse", "F R2")
        self.assertEqual((status, output), (1, ""))
        self.assertIn("bce-v2: GAP failed", errors)

    @unittest.skipUnless(shutil.which("gap"), "optional GAP executable")
    def test_solve_loops_imported_state_without_scramble_history(self):
        initial = c.fixture("Bicube Fuse")
        loop = c.isotropy_loops(initial).generators[0]
        scrambled = c.State(initial).apply(loop.moves)
        imported = c.State.from_facelets(scrambled.facelets, initial)
        self.assertIsNone(imported.scramble)
        with tempfile.TemporaryDirectory() as directory:
            puzzle = Path(directory) / "imported.json"
            c.save_puzzle(imported, puzzle)
            status, output, errors = self.invoke(
                "solve-loops", str(puzzle), "U", "--metric", "HTM", "--timeout", "30")
        self.assertEqual((status, errors), (0, ""))
        record = json.loads(output)
        self.assertEqual(record["status"], "solved")
        self.assertFalse(record["optimal"])
        self.assertEqual(record["metric"], "HTM")
        self.assertTrue(imported.apply("U").apply(record["solution"]).is_solved)

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
