"""Chain-selection dispatch, artifact safety and portable CLI integration."""

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
        self.record = {"format": "bce-v2-human-method", "version": 1,
                       "status": status, "selected_chain": True}

    def to_dict(self):
        return dict(self.record)

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")

    def write_guide(self, path):
        Path(path).write_text("# Selected chain\n", encoding="utf-8")


class _ChainResult:
    def __init__(self, status="completed"):
        self.status = status
        self.method = _MethodResult(status)
        self.record = {"format": "bce-v2-human-chain-search", "status": status,
                       "method": self.method.record}

    def save(self, path):
        Path(path).write_text(json.dumps(self.record), encoding="utf-8")


class _CommandInvocation:
    def invoke(self, *arguments):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, output.getvalue(), errors.getvalue()


class HumanChainCommandTests(_CommandInvocation, unittest.TestCase):
    def backend(self, **options):
        return patch.object(c, "select_human_chain", create=True, **options)

    def test_symbolic_chain_backend_is_forwarded(self):
        with self.backend(return_value=_ChainResult()) as select, patch.object(
                c, "synthesize_human_method") as synthesize:
            status, _, errors = self.invoke(
                "plan-method", "Alcatraz", "--select-chain", "--backend", "symbolic")
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(select.call_args.kwargs["backend"], "symbolic")
        synthesize.assert_not_called()

    def test_selection_options_and_three_artifacts(self):
        result = _ChainResult()
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            report_path = Path(directory) / "chain.json"
            with self.backend(return_value=result) as select, patch.object(
                    c, "synthesize_human_method") as synthesize, patch.object(
                    c, "improve_human_method") as improve:
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--select-chain",
                    "--strategy", "fully_solve_each_block", "--chain-preference", "recognition",
                    "--chain-beam-width", "2", "--chain-max-expansions", "7",
                    "--chain-max-methods", "3", "--max-group-elements", "324",
                    "--gap-executable", "custom-gap", "--timeout", "5.5",
                    "--search-mode", "original", "--search-max-candidates", "41",
                    "--search-max-states", "17", "--search-max-seed-loops", "11",
                    "--search-rounds", "2", "--search-max-word-length", "4",
                    "--search-max-htm-length", "35", "--search-max-expanded-moves", "140",
                    "--output", str(output_path), "--guide", str(guide_path),
                    "--chain-report", str(report_path))
            self.assertEqual((status, errors), (0, ""))
            synthesize.assert_not_called()
            improve.assert_not_called()
            select.assert_called_once_with(
                c.fixture("Alcatraz"), strategy="fully_solve_each_block", preference="recognition",
                beam_width=2, max_expansions=7, max_methods=3,
                discovery_options={"mode": "original", "max_candidates": 41, "max_states": 17,
                                   "max_seed_loops": 11, "rounds": 2, "max_word_length": 4,
                                   "max_htm_length": 35, "max_expanded_moves": 140},
                max_group_elements=324, gap_executable="custom-gap", timeout=5.5)
            self.assertEqual(json.loads(output), result.method.record)
            self.assertEqual(json.loads(output_path.read_text()), result.method.record)
            self.assertEqual(guide_path.read_text(), "# Selected chain\n")
            self.assertEqual(json.loads(report_path.read_text()), result.record)

    def test_shape_only_defaults_and_zero_search_budgets(self):
        cases = (
            ((), {"mode": "structured", "max_seed_loops": 32, "max_candidates": 3000,
                  "max_states": 2000, "rounds": 1, "max_word_length": 3,
                  "max_htm_length": 120, "max_expanded_moves": 480}, 64, 16),
            (("--chain-max-expansions", "0", "--chain-max-methods", "0",
              "--search-max-seed-loops", "0", "--search-max-candidates", "0",
              "--search-max-states", "0", "--search-rounds", "0",
              "--search-max-word-length", "0", "--search-max-htm-length", "0",
              "--search-max-expanded-moves", "0"),
             {"mode": "structured", "max_seed_loops": 0, "max_candidates": 0,
              "max_states": 0, "rounds": 0, "max_word_length": 0,
              "max_htm_length": 0, "max_expanded_moves": 0}, 0, 0),
        )
        labels = [1] * 9 + [2] * 18
        for arguments, discovery, expansions, methods in cases:
            with self.subTest(arguments=arguments):
                result = _ChainResult()
                with self.backend(return_value=result) as select:
                    status, output, errors = self.invoke(
                        "plan-method", json.dumps(labels), "--select-chain", *arguments)
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), result.method.record)
                select.assert_called_once_with(
                    c.Shape(labels), strategy="placement_then_orientation", preference="execution",
                    beam_width=4, max_expansions=expansions, max_methods=methods,
                    discovery_options=discovery, max_group_elements=None,
                    gap_executable="gap", timeout=None)

    def test_puzzle_file_uses_reference(self):
        scrambled = c.State(c.fixture("Alcatraz")).apply("F R2")
        self.assertNotEqual(scrambled.shape, scrambled.specification)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "puzzle.json"
            c.save_puzzle(scrambled, source)
            with self.backend(return_value=_ChainResult()) as select:
                status, _, errors = self.invoke("plan-method", str(source), "--select-chain")
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(select.call_args.args[0], scrambled.specification)

    def test_preparation_cap_saves_partial_selection_and_method(self):
        result = _ChainResult("limit_reached")
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            report_path = Path(directory) / "chain.json"
            with self.backend(return_value=result):
                status, output, errors = self.invoke(
                    "plan-method", "Alcatraz", "--select-chain", "--max-group-elements", "323",
                    "--output", str(output_path), "--guide", str(guide_path),
                    "--chain-report", str(report_path))
            self.assertEqual((status, errors), (2, ""))
            self.assertEqual(json.loads(output), result.method.record)
            self.assertEqual(json.loads(output_path.read_text()), result.method.record)
            self.assertEqual(json.loads(report_path.read_text()), result.record)
            self.assertTrue(guide_path.exists())

    def test_report_opt_in_and_conflicting_improvement_fail_before_backend(self):
        options = (
            ("--chain-report", "unused-chain.json"),
            ("--select-chain", "--improve-algorithms"),
            ("--select-chain", "--search-report", "unused-search.json"),
        )
        for arguments in options:
            with self.subTest(arguments=arguments):
                with self.backend() as select, patch.object(c, "synthesize_human_method") as synthesize:
                    status, output, errors = self.invoke("plan-method", "Alcatraz", *arguments)
                self.assertEqual((status, output), (1, ""))
                self.assertIn("bce-v2:", errors)
                select.assert_not_called()
                synthesize.assert_not_called()

    def test_invalid_budgets_preserve_all_artifacts(self):
        options = (("--chain-beam-width", "0"), ("--chain-beam-width", "-1"),
                   ("--chain-max-expansions", "-1"), ("--chain-max-methods", "-1"))
        options += tuple((name, "-1") for name in (
            "--search-max-seed-loops", "--search-max-candidates", "--search-max-states",
            "--search-rounds", "--search-max-word-length", "--search-max-htm-length",
            "--search-max-expanded-moves"))
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("shape.json", "method.json", "guide.md", "chain.json")]
            contents = [json.dumps([1] * 27), "existing method", "existing guide", "existing report"]
            for path, content in zip(paths, contents):
                path.write_text(content, encoding="utf-8")
            for arguments in options:
                with self.subTest(arguments=arguments):
                    with self.backend() as select, patch.object(c, "synthesize_human_method") as synthesize:
                        status, output, errors = self.invoke(
                            "plan-method", str(paths[0]), "--select-chain", *arguments,
                            "--output", str(paths[1]), "--guide", str(paths[2]),
                            "--chain-report", str(paths[3]))
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn(arguments[0], errors)
                    select.assert_not_called()
                    synthesize.assert_not_called()
                    self.assertEqual([path.read_text() for path in paths], contents)

    def test_invalid_selection_options(self):
        for arguments in (("--chain-preference", "memory"), ("--chain-beam-width", "many")):
            with self.subTest(arguments=arguments):
                with self.backend() as select:
                    status, output, errors = self.invoke("plan-method", "Alcatraz", "--select-chain", *arguments)
                self.assertEqual((status, output), (1, ""))
                self.assertIn("error:", errors)
                select.assert_not_called()

    def test_report_path_and_inode_aliases_fail_before_preparation(self):
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
            cases = (("--chain-report", str(source)),
                     ("--chain-report", str(source_alias)),
                     ("--output", str(artifact), "--chain-report", str(artifact)),
                     ("--output", str(artifact), "--chain-report", str(hardlink)),
                     ("--guide", str(artifact), "--chain-report", str(symlink)))
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    with self.backend() as select:
                        status, output, errors = self.invoke(
                            "plan-method", str(source), "--select-chain", *arguments)
                    self.assertEqual((status, output), (1, ""))
                    self.assertIn("must be different files", errors)
                    select.assert_not_called()
                    self.assertEqual(source.read_text(), json.dumps([1] * 27))
                    self.assertEqual(artifact.read_text(), "existing artifact")


@unittest.skipUnless(shutil.which("gap"), "optional GAP executable")
class HumanChainCommandIntegrationTests(_CommandInvocation, unittest.TestCase):
    def test_real_selection_report_and_reloaded_complete_method(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "method.json"
            guide_path = Path(directory) / "method.md"
            report_path = Path(directory) / "chain.json"
            status, output, errors = self.invoke(
                "plan-method", json.dumps([1] * 9 + [2] * 18), "--select-chain",
                "--max-group-elements", "4", "--chain-max-expansions", "4",
                "--chain-max-methods", "4", "--search-mode", "original",
                "--search-max-seed-loops", "4", "--search-max-candidates", "16",
                "--search-max-states", "0", "--search-max-word-length", "1",
                "--output", str(output_path), "--guide", str(guide_path),
                "--chain-report", str(report_path))
            self.assertEqual((status, errors), (0, ""))
            record = json.loads(output)
            report = json.loads(report_path.read_text())
            self.assertEqual(record, json.loads(output_path.read_text()))
            self.assertEqual(record, report["method"])
            self.assertEqual((record["format"], record["version"]), ("bce-v2-human-method", 1))
            self.assertEqual((record["coverage"], record["quality"]), ("certified", "computational_baseline"))
            self.assertEqual(report["format"], "bce-v2-human-chain-search")
            self.assertEqual(report["status"], "completed")
            loaded = c.load_human_method(output_path)
            self.assertTrue(loaded.human_method_complete)
            for moves in ("", "U", "U2", "U'"):
                state = c.State(loaded.reference_shape).apply(moves)
                result = loaded.apply(state)
                self.assertEqual(result.status, "solved")
                self.assertTrue(result.state.is_solved)
            self.assertGreater(len(guide_path.read_text()), 100)


if __name__ == "__main__":
    unittest.main()
