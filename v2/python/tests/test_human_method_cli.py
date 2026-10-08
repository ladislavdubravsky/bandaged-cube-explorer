"""Shape-only method generation and artifact protection in the batch interface."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.__main__ import main


class _MethodResult:
    def __init__(self, status="completed"):
        self.status = status
        self.record = {"format": "bce-v2-human-method", "status": status,
                       "human_method_complete": status == "completed"}

    def to_dict(self):
        return self.record

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")

    def write_guide(self, path):
        Path(path).write_text("# Method guide\n", encoding="utf-8")


class _CommandInvocation:
    def invoke(self, *arguments):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, output.getvalue(), errors.getvalue()


class HumanMethodCommandTests(_CommandInvocation, unittest.TestCase):
    def backend(self, **options):
        return patch.object(c, "synthesize_human_method", create=True, **options)

    def test_fixture_options_and_both_artifacts(self):
        result = _MethodResult()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            with self.backend(return_value=result) as synthesize:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--strategy", "fully_solve_each_block",
                    "--max-group-elements", "324", "--gap-executable", "custom-gap",
                    "--timeout", "5.5", "--output", str(output_path),
                    "--guide", str(guide_path))
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(json.loads(output), result.record)
            self.assertEqual(json.loads(output_path.read_text()), result.record)
            self.assertEqual(guide_path.read_text(), "# Method guide\n")
            synthesize.assert_called_once_with(
                c.fixture("Alcatraz"), strategy="fully_solve_each_block",
                max_group_elements=324, gap_executable="custom-gap", timeout=5.5)

    def test_inline_and_file_labels_need_no_colored_state(self):
        labels = [1] * 9 + [2] * 18
        with tempfile.TemporaryDirectory() as directory:
            label_path = Path(directory) / "labels.json"
            label_path.write_text(json.dumps(labels), encoding="utf-8")
            for source in ("  " + json.dumps(labels), str(label_path)):
                with self.subTest(source=source):
                    with self.backend(return_value=_MethodResult()) as synthesize:
                        status, output, errors = self.invoke("plan-method", source)
                    self.assertEqual((status, errors), (0, ""))
                    self.assertEqual(json.loads(output)["status"], "completed")
                    synthesize.assert_called_once_with(
                        c.Shape(labels), strategy="placement_then_orientation",
                        max_group_elements=None, gap_executable="gap", timeout=None)
                    self.assertIsInstance(synthesize.call_args.args[0], c.Shape)

    def test_puzzle_file_uses_reference_instead_of_scrambled_shape(self):
        state = c.State(c.fixture("Alcatraz")).apply("F R2")
        self.assertNotEqual(state.shape, state.specification)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "puzzle.json"
            c.save_puzzle(state, source)
            with self.backend(return_value=_MethodResult()) as synthesize:
                status, _, errors = self.invoke("plan-method", str(source))
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(synthesize.call_args.args[0], state.specification)

    def test_preflight_stop_has_distinct_exit_and_retains_artifacts(self):
        result = _MethodResult("limit_reached")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "limited.json"
            guide_path = Path(directory) / "limited.md"
            with self.backend(return_value=result):
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--max-group-elements", "323",
                    "--output", str(output_path), "--guide", str(guide_path))
            self.assertEqual((status, errors), (2, ""))
            self.assertEqual(json.loads(output), result.record)
            self.assertEqual(json.loads(output_path.read_text()), result.record)
            self.assertTrue(guide_path.exists())

    def test_invalid_reference_and_backend_failure_write_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_file = Path(directory) / "invalid.json"
            invalid_file.write_text("{broken", encoding="utf-8")
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            sources = ("unknown-puzzle", "[broken", "[0, 0]", str(invalid_file))
            for source in sources:
                with self.subTest(source=source):
                    with self.backend(side_effect=AssertionError("unexpected synthesis")):
                        status, output, errors = self.invoke(
                            "plan-method", source, "--output", str(output_path),
                            "--guide", str(guide_path))
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn("bce-v2:", errors)
                    self.assertFalse(output_path.exists())
                    self.assertFalse(guide_path.exists())
            with self.backend(side_effect=RuntimeError("GAP failed")):
                status, output, errors = self.invoke("plan-method", "Alcatraz")
            self.assertEqual((status, output), (1, ""))
            self.assertIn("bce-v2: GAP failed", errors)

    def test_invalid_command_options_return_one(self):
        for options in (("--strategy", "manual"), ("--max-group-elements", "many")):
            with self.subTest(options=options):
                status, output, errors = self.invoke("plan-method", "Alcatraz", *options)
                self.assertEqual((status, output), (1, ""))
                self.assertIn("error:", errors)

    def test_all_artifact_aliases_are_rejected_before_synthesis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shape.json"
            original = json.dumps([1] * 27)
            source.write_text(original, encoding="utf-8")
            hardlink = root / "hardlink.json"
            os.link(source, hardlink)
            symlink = root / "symlink.json"
            symlink.symlink_to(source)
            separate = root / "separate.json"
            separate.write_text("existing artifact", encoding="utf-8")
            separate_alias = root / "separate-alias.md"
            os.link(separate, separate_alias)
            cases = (
                ("--output", str(source)),
                ("--guide", str(source)),
                ("--output", str(hardlink)),
                ("--guide", str(symlink)),
                ("--output", str(root / "unused" / ".." / "shape.json")),
                ("--output", str(separate), "--guide", str(separate)),
                ("--output", str(separate), "--guide", str(separate_alias)),
            )
            for options in cases:
                with self.subTest(options=options):
                    with self.backend(side_effect=AssertionError("unexpected synthesis")):
                        status, output, errors = self.invoke("plan-method", str(source), *options)
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn("must be different files", errors)
                    self.assertEqual(source.read_text(), original)
                    self.assertEqual(separate.read_text(), "existing artifact")


@unittest.skipUnless(shutil.which("gap"), "optional GAP executable")
class HumanMethodCommandIntegrationTests(_CommandInvocation, unittest.TestCase):
    def test_real_shape_only_method_and_guide(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            status, output, errors = self.invoke(
                "plan-method", json.dumps([1] * 9 + [2] * 18),
                "--max-group-elements", "4", "--timeout", "30",
                "--output", str(output_path), "--guide", str(guide_path))
            self.assertEqual((status, errors), (0, ""))
            record = json.loads(output)
            self.assertEqual(record, json.loads(output_path.read_text()))
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["group_order"], "4")
            self.assertEqual(record["coverage"], "certified")
            self.assertEqual(record["coverage_scope"], "all_reference_group_states")
            self.assertEqual(record["quality"], "computational_baseline")
            self.assertTrue(record["human_method_complete"])
            self.assertGreater(len(guide_path.read_text()), 100)


if __name__ == "__main__":
    unittest.main()
