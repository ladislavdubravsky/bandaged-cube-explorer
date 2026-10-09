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


class _SearchResult:
    def __init__(self, baseline, method):
        self.baseline = baseline
        self.method = method
        self.record = {"format": "bce-v2-human-algorithm-search", "metadata": {"exhaustive": False}}

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")


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
        for options in (("--strategy", "manual"), ("--max-group-elements", "many"),
                        ("--search-mode", "optimal"), ("--search-max-states", "many")):
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

    def test_improvement_options_and_separate_report(self):
        baseline, improved = _MethodResult(), _MethodResult()
        improved.record["algorithm_choice"] = "improved"
        search = _SearchResult(baseline, improved)
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            report_path = Path(directory) / "search.json"
            with self.backend(return_value=baseline), patch.object(
                    c, "improve_human_method", create=True, return_value=search) as improve:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--improve-algorithms", "--search-mode", "shallow",
                    "--search-max-candidates", "41", "--search-max-states", "17",
                    "--search-max-seed-loops", "11",
                    "--search-rounds", "2", "--search-max-word-length", "4",
                    "--search-max-htm-length", "35", "--search-max-expanded-moves", "140",
                    "--output", str(output_path), "--guide", str(guide_path),
                    "--search-report", str(report_path))
            self.assertEqual((status, errors), (0, ""))
            improve.assert_called_once_with(
                baseline, mode="shallow", max_candidates=41, max_states=17, rounds=2,
                max_seed_loops=11,
                max_word_length=4, max_htm_length=35, max_expanded_moves=140)
            self.assertEqual(json.loads(output), improved.record)
            self.assertEqual(json.loads(output_path.read_text()), improved.record)
            self.assertEqual(json.loads(report_path.read_text()), search.record)
            self.assertTrue(guide_path.exists())

    def test_improvement_defaults_and_zero_budgets_are_forwarded(self):
        baseline = _MethodResult()
        cases = (
            ((), {"mode": "structured", "max_candidates": 3000, "max_states": 2000,
                  "max_seed_loops": 32,
                  "rounds": 1, "max_word_length": 3, "max_htm_length": 120,
                  "max_expanded_moves": 480}),
            (("--search-mode", "original", "--search-max-candidates", "0",
              "--search-max-states", "0", "--search-rounds", "0",
              "--search-max-word-length", "0", "--search-max-seed-loops", "0",
              "--search-max-htm-length", "0", "--search-max-expanded-moves", "0"),
             {"mode": "original", "max_candidates": 0, "max_states": 0,
              "max_seed_loops": 0,
              "rounds": 0, "max_word_length": 0, "max_htm_length": 0,
              "max_expanded_moves": 0}),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                with self.backend(return_value=baseline), patch.object(
                        c, "improve_human_method", create=True,
                        return_value=_SearchResult(baseline, baseline)) as improve:
                    status, output, errors = self.invoke(
                        "plan-method", "Alcatraz", "--improve-algorithms", *options)
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), baseline.record)
                improve.assert_called_once_with(baseline, **expected)

    def test_negative_search_budgets_fail_before_synthesis_and_preserve_artifacts(self):
        options = ("--search-max-seed-loops", "--search-max-candidates", "--search-max-states",
                   "--search-rounds", "--search-max-word-length", "--search-max-htm-length",
                   "--search-max-expanded-moves")
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("shape.json", "method.json", "guide.md", "search.json")]
            contents = [json.dumps([1] * 27), "existing method", "existing guide", "existing report"]
            for path, content in zip(paths, contents):
                path.write_text(content, encoding="utf-8")
            for option in options:
                with self.subTest(option=option):
                    with self.backend() as synthesize:
                        status, output, errors = self.invoke(
                            "plan-method", str(paths[0]), "--improve-algorithms", option, "-1",
                            "--output", str(paths[1]), "--guide", str(paths[2]),
                            "--search-report", str(paths[3]))
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn(f"{option} must be nonnegative", errors)
                    synthesize.assert_not_called()
                    self.assertEqual([path.read_text() for path in paths], contents)

    def test_improvement_skipped_when_preparation_hits_group_cap(self):
        limited = _MethodResult("limit_reached")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            report_path = Path(directory) / "search.json"
            report_path.write_text("existing report", encoding="utf-8")
            with self.backend(return_value=limited), patch.object(
                    c, "improve_human_method", create=True) as improve:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--improve-algorithms",
                    "--max-group-elements", "323", "--output", str(output_path),
                    "--guide", str(guide_path), "--search-report", str(report_path))
            self.assertEqual((status, errors), (2, ""))
            self.assertEqual(json.loads(output), limited.record)
            self.assertEqual(json.loads(output_path.read_text()), limited.record)
            self.assertTrue(guide_path.exists())
            self.assertEqual(report_path.read_text(), "existing report")
            improve.assert_not_called()

    def test_search_report_requires_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "search.json"
            with self.backend() as synthesize:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--search-report", str(report_path))
            self.assertEqual((status, output), (1, ""))
            self.assertIn("--search-report requires --improve-algorithms", errors)
            self.assertFalse(report_path.exists())
            synthesize.assert_not_called()

    def test_search_report_aliases_preserve_input_and_other_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shape.json"
            original = json.dumps([1] * 27)
            source.write_text(original, encoding="utf-8")
            source_alias = root / "shape-alias.json"
            os.link(source, source_alias)
            artifact = root / "artifact.json"
            artifact.write_text("existing artifact", encoding="utf-8")
            artifact_hardlink = root / "artifact-hardlink.json"
            os.link(artifact, artifact_hardlink)
            artifact_symlink = root / "artifact-symlink.json"
            artifact_symlink.symlink_to(artifact)
            cases = (
                ("--search-report", str(source)),
                ("--search-report", str(source_alias)),
                ("--output", str(artifact), "--search-report", str(artifact)),
                ("--output", str(artifact), "--search-report", str(artifact_hardlink)),
                ("--guide", str(artifact), "--search-report", str(artifact_symlink)),
            )
            for options in cases:
                with self.subTest(options=options):
                    with self.backend() as synthesize:
                        status, output, errors = self.invoke(
                            "plan-method", str(source), "--improve-algorithms", *options)
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn("must be different files", errors)
                    synthesize.assert_not_called()
                    self.assertEqual(source.read_text(), original)
                    self.assertEqual(artifact.read_text(), "existing artifact")


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

    def test_real_improvement_keeps_portable_method_and_separate_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            report_path = Path(directory) / "search.json"
            status, output, errors = self.invoke(
                "plan-method", json.dumps([1] * 9 + [2] * 18),
                "--max-group-elements", "4", "--improve-algorithms",
                "--search-max-seed-loops", "4", "--search-max-candidates", "30",
                "--search-max-states", "16", "--search-max-word-length", "2",
                "--search-max-htm-length", "20", "--search-max-expanded-moves", "80",
                "--output", str(output_path), "--search-report", str(report_path))
            self.assertEqual((status, errors), (0, ""))
            record = json.loads(output)
            report = json.loads(report_path.read_text())
            self.assertEqual(record, json.loads(output_path.read_text()))
            self.assertEqual(record, report["method"])
            self.assertEqual((record["format"], record["version"]), ("bce-v2-human-method", 1))
            self.assertEqual(record["coverage"], "certified")
            self.assertEqual(record["quality"], "computational_baseline")
            self.assertEqual(report["format"], "bce-v2-human-algorithm-search")
            self.assertLessEqual(report["metadata"]["candidates_examined"], 30)
            self.assertLessEqual(report["metadata"]["states_expanded"], 16)
            self.assertTrue(report["metadata"]["fallback_policy_retained"])
            self.assertTrue(c.load_human_method(output_path).human_method_complete)


if __name__ == "__main__":
    unittest.main()
