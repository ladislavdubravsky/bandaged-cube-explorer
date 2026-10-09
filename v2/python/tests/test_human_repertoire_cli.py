"""Repertoire postprocessing and independent artifacts in the shape-only CLI."""

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
    def __init__(self, name="baseline", status="completed"):
        self.status = status
        self.record = {"format": "bce-v2-human-method", "version": 1,
                       "status": status, "policy": name}

    def to_dict(self):
        return dict(self.record)

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")

    def write_guide(self, path):
        Path(path).write_text("# Expanded " + self.record["policy"] + "\n", encoding="utf-8")


class _ChoiceResult:
    def __init__(self, method):
        self.method = method

    def save(self, path):
        Path(path).write_text(json.dumps({"method": self.method.record}), encoding="utf-8")


class _RepertoireResult(_ChoiceResult):
    def __init__(self, method):
        super().__init__(method)
        self.record = {"format": "bce-v2-human-repertoire", "version": 1, "method": method.record}

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")

    def write_guide(self, path):
        Path(path).write_text("# Compressed repertoire\n", encoding="utf-8")


class _CommandInvocation:
    def invoke(self, *arguments):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, output.getvalue(), errors.getvalue()


class HumanRepertoireCommandTests(_CommandInvocation, unittest.TestCase):
    def backend(self, **options):
        return patch.object(c, "optimize_human_repertoire", create=True, **options)

    def test_baseline_postprocessing_and_expanded_and_compressed_artifacts(self):
        baseline, selected = _MethodResult(), _MethodResult("selected")
        repertoire = _RepertoireResult(selected)
        with tempfile.TemporaryDirectory() as directory:
            output_path, guide_path, repertoire_path, compressed_path = (
                Path(directory) / name for name in ("method.json", "method.md", "repertoire.json", "repertoire.md"))
            with patch.object(c, "synthesize_human_method", return_value=baseline), self.backend(
                    return_value=repertoire) as optimize:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--optimize-repertoire",
                    "--output", str(output_path), "--guide", str(guide_path),
                    "--repertoire-output", str(repertoire_path), "--repertoire-guide", str(compressed_path))
            self.assertEqual((status, errors), (0, ""))
            optimize.assert_called_once_with(
                baseline, preference="memory", max_trials=64, max_recipes=2000,
                max_power=4, max_extra_macros=16, max_setup_macros=16,
                allow_symmetry=True, max_cost_ratio=1.0)
            self.assertEqual(json.loads(output), selected.record)
            self.assertEqual(json.loads(output_path.read_text()), selected.record)
            self.assertEqual(guide_path.read_text(), "# Expanded selected\n")
            self.assertEqual(json.loads(repertoire_path.read_text()), repertoire.record)
            self.assertEqual(compressed_path.read_text(), "# Compressed repertoire\n")

    def test_zero_budgets_and_explicit_tradeoff_are_forwarded(self):
        baseline = _MethodResult()
        with patch.object(c, "synthesize_human_method", return_value=baseline), self.backend(
                return_value=_RepertoireResult(baseline)) as optimize:
            status, output, errors = self.invoke(
                "plan-method", "Alcatraz", "--optimize-repertoire",
                "--repertoire-preference", "execution", "--repertoire-max-trials", "0",
                "--repertoire-max-recipes", "0", "--repertoire-max-power", "0",
                "--repertoire-max-extra-macros", "0", "--repertoire-max-setup-macros", "0",
                "--repertoire-no-symmetry", "--repertoire-max-cost-ratio", "1.25")
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output), baseline.record)
        optimize.assert_called_once_with(
            baseline, preference="execution", max_trials=0, max_recipes=0,
            max_power=0, max_extra_macros=0, max_setup_macros=0,
            allow_symmetry=False, max_cost_ratio=1.25)

    def test_postprocessing_uses_improved_or_selected_policy(self):
        baseline, chosen, selected = (_MethodResult(name) for name in ("baseline", "chosen", "selected"))
        for option, api in (("--improve-algorithms", "improve_human_method"),
                            ("--select-chain", "select_human_chain")):
            with self.subTest(option=option):
                with patch.object(c, "synthesize_human_method", return_value=baseline), patch.object(
                        c, api, return_value=_ChoiceResult(chosen)), self.backend(
                        return_value=_RepertoireResult(selected)) as optimize:
                    status, output, errors = self.invoke(
                        "plan-method", "Alcatraz", option, "--optimize-repertoire")
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), selected.record)
                self.assertIs(optimize.call_args.args[0], chosen)

    def test_repertoire_paths_require_opt_in(self):
        for option in ("--repertoire-output", "--repertoire-guide"):
            with self.subTest(option=option):
                with patch.object(c, "synthesize_human_method") as synthesize, self.backend() as optimize:
                    status, output, errors = self.invoke("plan-method", "Alcatraz", option, "unused.json")
                self.assertEqual((status, output), (1, ""))
                self.assertIn("require --optimize-repertoire", errors)
                synthesize.assert_not_called()
                optimize.assert_not_called()

    def test_invalid_budgets_fail_before_preparation_and_preserve_artifacts(self):
        options = tuple((name, "-1") for name in (
            "--repertoire-max-trials", "--repertoire-max-recipes", "--repertoire-max-power",
            "--repertoire-max-extra-macros", "--repertoire-max-setup-macros"))
        options += tuple(("--repertoire-max-cost-ratio", value) for value in ("0.99", "nan", "inf", "-inf"))
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in (
                "shape.json", "method.json", "method.md", "repertoire.json", "repertoire.md")]
            contents = [json.dumps([1] * 27), "old method", "old guide", "old repertoire", "old compressed guide"]
            for path, content in zip(paths, contents):
                path.write_text(content, encoding="utf-8")
            for arguments in options:
                with self.subTest(arguments=arguments):
                    with patch.object(c, "synthesize_human_method") as synthesize, self.backend() as optimize:
                        status, output, errors = self.invoke(
                            "plan-method", str(paths[0]), "--optimize-repertoire", *arguments,
                            "--output", str(paths[1]), "--guide", str(paths[2]),
                            "--repertoire-output", str(paths[3]), "--repertoire-guide", str(paths[4]))
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn(arguments[0], errors)
                    synthesize.assert_not_called()
                    optimize.assert_not_called()
                    self.assertEqual([path.read_text() for path in paths], contents)

    def test_repertoire_aliases_cover_inputs_outputs_guides_and_prior_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shape.json"
            source.write_text(json.dumps([1] * 27), encoding="utf-8")
            source_alias = root / "shape-alias.json"
            os.link(source, source_alias)
            artifact = root / "artifact.json"
            artifact.write_text("existing artifact", encoding="utf-8")
            hardlink = root / "artifact-hardlink.json"
            os.link(artifact, hardlink)
            symlink = root / "artifact-symlink.json"
            symlink.symlink_to(artifact)
            cases = (
                ("--repertoire-output", str(source)),
                ("--repertoire-guide", str(source_alias)),
                ("--output", str(artifact), "--repertoire-output", str(hardlink)),
                ("--guide", str(artifact), "--repertoire-guide", str(symlink)),
                ("--repertoire-output", str(artifact), "--repertoire-guide", str(hardlink)),
                ("--improve-algorithms", "--search-report", str(artifact), "--repertoire-output", str(symlink)),
                ("--select-chain", "--chain-report", str(artifact), "--repertoire-guide", str(hardlink)),
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    with patch.object(c, "synthesize_human_method") as synthesize, patch.object(
                            c, "select_human_chain") as select, self.backend() as optimize:
                        status, output, errors = self.invoke(
                            "plan-method", str(source), "--optimize-repertoire", *arguments)
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn("must be different files", errors)
                    synthesize.assert_not_called()
                    select.assert_not_called()
                    optimize.assert_not_called()
                    self.assertEqual(source.read_text(), json.dumps([1] * 27))
                    self.assertEqual(artifact.read_text(), "existing artifact")

    def test_preparation_cap_skips_repertoire_and_leaves_its_artifacts_untouched(self):
        limited = _MethodResult(status="limit_reached")
        for arguments in ((), ("--select-chain",)):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as directory:
                output_path, guide_path, repertoire_path, compressed_path = (
                    Path(directory) / name for name in ("method.json", "method.md", "repertoire.json", "repertoire.md"))
                repertoire_path.write_text("existing repertoire", encoding="utf-8")
                compressed_path.write_text("existing compressed guide", encoding="utf-8")
                with patch.object(c, "synthesize_human_method", return_value=limited), patch.object(
                        c, "select_human_chain", return_value=_ChoiceResult(limited)), self.backend() as optimize:
                    status, output, errors = self.invoke(
                        "plan-method", "Alcatraz", "--max-group-elements", "0", *arguments,
                        "--optimize-repertoire", "--output", str(output_path), "--guide", str(guide_path),
                        "--repertoire-output", str(repertoire_path), "--repertoire-guide", str(compressed_path))
                self.assertEqual((status, errors), (2, ""))
                self.assertEqual(json.loads(output), limited.record)
                self.assertEqual(json.loads(output_path.read_text()), limited.record)
                self.assertTrue(guide_path.exists())
                self.assertEqual(repertoire_path.read_text(), "existing repertoire")
                self.assertEqual(compressed_path.read_text(), "existing compressed guide")
                optimize.assert_not_called()

    def test_invalid_repertoire_options(self):
        for arguments in (("--repertoire-preference", "recognition"),
                          ("--repertoire-max-recipes", "many"), ("--repertoire-max-cost-ratio", "many")):
            with self.subTest(arguments=arguments):
                status, output, errors = self.invoke("plan-method", "Alcatraz", "--optimize-repertoire", *arguments)
                self.assertEqual((status, output), (1, ""))
                self.assertIn("error:", errors)


@unittest.skipUnless(shutil.which("gap"), "optional GAP executable")
class HumanRepertoireCommandIntegrationTests(_CommandInvocation, unittest.TestCase):
    def test_default_symmetry_after_improvement_preserves_cost_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            repertoire_path = Path(directory) / "repertoire.json"
            status, output, errors = self.invoke(
                "plan-method", json.dumps([1] * 9 + [2] * 18),
                "--max-group-elements", "4", "--improve-algorithms", "--search-mode", "original",
                "--search-max-seed-loops", "4", "--search-max-candidates", "16",
                "--search-max-states", "0", "--optimize-repertoire",
                "--repertoire-max-trials", "0", "--repertoire-max-recipes", "16",
                "--repertoire-max-extra-macros", "0", "--repertoire-max-setup-macros", "0",
                "--repertoire-output", str(repertoire_path))
            self.assertEqual((status, errors), (0, ""))
            loaded = c.load_human_repertoire(repertoire_path)
            self.assertEqual(json.loads(output), loaded.method.to_dict())
            metadata = loaded.metadata
            self.assertTrue(metadata["settings"]["allow_symmetry"])
            self.assertEqual(metadata["settings"]["max_cost_ratio"], 1.0)
            self.assertLessEqual(metadata["selected_metrics"]["mean_htm"], metadata["baseline_metrics"]["mean_htm"])
            self.assertLessEqual(metadata["selected_metrics"]["worst_htm"], metadata["baseline_metrics"]["worst_htm"])

    def test_real_repertoire_load_and_compressed_guide(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            repertoire_path = Path(directory) / "repertoire.json"
            compressed_path = Path(directory) / "repertoire.md"
            status, output, errors = self.invoke(
                "plan-method", json.dumps([1] * 9 + [2] * 18), "--optimize-repertoire",
                "--max-group-elements", "4", "--repertoire-max-trials", "2",
                "--repertoire-max-recipes", "16", "--repertoire-max-extra-macros", "0",
                "--repertoire-max-setup-macros", "0", "--repertoire-no-symmetry",
                "--output", str(output_path), "--repertoire-output", str(repertoire_path),
                "--repertoire-guide", str(compressed_path))
            self.assertEqual((status, errors), (0, ""))
            record = json.loads(output)
            wrapper = json.loads(repertoire_path.read_text())
            self.assertEqual(record, json.loads(output_path.read_text()))
            self.assertEqual(record, wrapper["method"])
            self.assertEqual((record["format"], record["version"]), ("bce-v2-human-method", 1))
            self.assertEqual((wrapper["format"], wrapper["version"]), ("bce-v2-human-repertoire", 1))
            loaded = c.load_human_repertoire(repertoire_path)
            self.assertTrue(loaded.method.human_method_complete)
            for moves in ("", "U", "U2", "U'"):
                state = c.State(loaded.method.reference_shape).apply(moves)
                result = loaded.apply(state)
                self.assertEqual(result.status, "solved")
                self.assertTrue(result.state.is_solved)
            self.assertGreater(len(compressed_path.read_text()), 100)


if __name__ == "__main__":
    unittest.main()
