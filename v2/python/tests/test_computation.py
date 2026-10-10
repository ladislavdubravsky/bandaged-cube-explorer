"""Quality budgets retain complete policies and share one compilation scope."""

from copy import deepcopy
from dataclasses import replace
import importlib
import shutil
import subprocess
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.computation import (
    Computation, OptimizationBudgetExceeded, checkpoint, current_computation,
    quality_timeout, validate_computation_metadata,
)
from bce_v2.gap_backend import GapTimeoutError, _run_gap
from bce_v2.human_method_io import _fingerprint
from bce_v2.preparation import preparation_profile


SMALL = c.Shape([1] * 9 + [2] * 18)
MOST_SIGNATURES = c.Shape([
    0, 0, 0, 0, 0, 0, 1, 0, 0,
    7, 6, 5, 8, 0, 4, 1, 2, 3,
    7, 6, 5, 8, 0, 4, 1, 2, 3,
])
TEMPLATE_MODULE = importlib.import_module("bce_v2.template_human_repertoire")


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


class ComputationArgumentTests(unittest.TestCase):
    def test_invalid_public_limits_fail_before_external_work(self):
        invalid = (
            {"optimization_seconds": True}, {"optimization_seconds": "1"},
            {"optimization_seconds": -1}, {"optimization_seconds": float("inf")},
            {"optimization_seconds": float("nan")}, {"max_optimization_work": True},
            {"max_optimization_work": 1.5}, {"max_optimization_work": -1},
            {"progress": "print"}, {"backend": "unknown"},
            {"backend": "auto", "root": True},
            {"backend": "auto", "max_group_elements": 0},
            {"backend": "auto", "max_group_elements": True},
        )
        with patch("subprocess.run", side_effect=AssertionError("invalid input launched GAP")):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises((TypeError, ValueError)):
                    c.template_human_repertoire(SMALL, **options)

    def test_invalid_auto_inputs_fail_before_gap_for_every_public_entry_point(self):
        calls = (
            (c.template_human_repertoire, {"preference": "unknown"}),
            (c.template_human_repertoire, {"max_trials": -1}),
            (c.template_human_repertoire, {"max_word_frontier": 0}),
            (c.template_human_repertoire, {"allow_symmetry": 1}),
            (c.template_human_repertoire, {"chunk_options": {"unknown": 1}}),
            (c.template_human_repertoire, {"chunk_options": {"max_chunks": True}}),
            (c.template_human_repertoire, {"discovery_options": {"unknown": 1}}),
            (c.template_human_repertoire, {"dictionary_options": {"max_candidates": -1}}),
            (c.template_human_repertoire, {"strategy": "unknown"}),
            (c.template_human_repertoire, {"strategy": "manual", "features": ("U",)}),
            (c.select_human_chain, {"preference": "unknown"}),
            (c.select_human_chain, {"beam_width": 0}),
            (c.select_human_chain, {"max_expansions": True}),
            (c.select_human_chain, {"strategy": "unknown"}),
            (c.select_human_chain, {"discovery_options": {"unknown": 1}}),
            (c.select_human_chain, {"dictionary_options": {"unknown": 1}}),
            (c.select_human_chain, {"manual_features": ("U",)}),
            (c.plan_human_stages, {"strategy": "unknown"}),
            (c.plan_human_stages, {"strategy": "manual"}),
            (c.plan_human_stages, {"strategy": "manual", "features": ("U",)}),
            (c.plan_human_stages, {"root": True}),
            (c.plan_human_stages, {"max_group_elements": 0}),
            (c.synthesize_human_method, {"strategy": "unknown"}),
            (c.synthesize_human_method, {"strategy": "manual"}),
            (c.synthesize_human_method, {"strategy": "manual", "features": ("U",)}),
            (c.synthesize_human_method, {"root": True}),
            (c.synthesize_human_method, {"max_group_elements": 0}),
        )
        with patch("subprocess.run", side_effect=AssertionError("invalid auto input launched GAP")):
            for function, options in calls:
                with self.subTest(function=function.__name__, options=options), \
                     self.assertRaises((TypeError, ValueError)):
                    function(SMALL, backend="auto", **options)

    def test_progress_is_throttled_but_terminal_events_are_delivered(self):
        clock, events = Clock(), []
        with patch("bce_v2.computation.monotonic", clock):
            context = Computation(progress=events.append)
            context.event("mining")
            clock.now = .1
            context.event("mining")
            context.event("mining", "completed")
            context.event("validation")
        self.assertEqual([(e["phase"], e["status"]) for e in events],
                         [("mining", "running"), ("mining", "completed"),
                          ("validation", "running")])
        self.assertTrue(all(e["elapsed_seconds"] >= 0 for e in events))

    def test_initial_certification_has_no_quality_deadline_or_work_charge(self):
        clock = Clock()
        with patch("bce_v2.computation.monotonic", clock):
            context = Computation(optimization_seconds=0, max_optimization_work=0)
            with context.activate():
                clock.now = 10000.
                checkpoint("initial_certificate", work=1000)
                self.assertEqual(quality_timeout(30), 30)
                self.assertIsNone(quality_timeout(None))
            self.assertEqual(context.work, 0)
            self.assertIsNone(context.quality_started)
            self.assertIsNone(current_computation())


@unittest.skipUnless(shutil.which("gap"), "GAP prepares real certified policies")
class ComputationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(SMALL, timeout=30)
        cls.methods = {backend: c.synthesize_human_method(cls.analysis,
            strategy="fully_solve_each_block", backend=backend, timeout=30)
            for backend in ("explicit", "symbolic")}
        cls.small_repertoire = c.template_human_repertoire(cls.methods["symbolic"],
            max_trials=0, max_word_candidates=0, chunk_options={"max_candidates": 0})
        cls.large_analysis = c.analyze_isotropy(c.Shape(), timeout=30)
        cls.many_loop_analysis = c.analyze_isotropy(MOST_SIGNATURES, timeout=30)

    def assert_complete_and_replay(self, repertoire):
        self.assertEqual(repertoire.method.status, "completed")
        self.assertEqual(repertoire.method.coverage, "certified")
        self.assertEqual(repertoire.method.terminal_order, 1)
        for moves in ("", "U", "U2", "U'"):
            source = c.State(SMALL).apply(moves)
            solved = repertoire.apply(source)
            self.assertTrue(solved.state.is_solved)
            self.assertEqual(source.apply(solved.turn_sequence), solved.state)
        self.assertIn("Stage 1", repertoire.write_guide())

    def test_default_serialization_is_deterministic_and_progress_opts_into_diagnostics(self):
        for backend, method in self.methods.items():
            events = []
            with self.subTest(backend=backend), patch("subprocess.run",
                    side_effect=AssertionError("supplied certified methods must remain offline")):
                first = c.template_human_repertoire(method)
                second = c.template_human_repertoire(method)
                observed = c.template_human_repertoire(method, progress=events.append)
                restored = c.HumanRepertoire.from_dict(observed.to_dict())
            self.assertNotIn("computation", first.metadata)
            self.assertNotIn("computation", second.metadata)
            self.assertEqual(first.to_json(), second.to_json())
            diagnostics = observed.metadata["computation"]
            self.assertIsNone(diagnostics["optimization_seconds"])
            self.assertIsNone(diagnostics["max_optimization_work"])
            self.assertIsNone(diagnostics["stop_reason"])
            self.assertEqual(restored.to_json(), observed.to_json())
            self.assertEqual((events[-1]["phase"], events[-1]["status"]),
                             ("complete", "certified"))
            self.assert_complete_and_replay(restored)

    def test_zero_seconds_returns_a_complete_offline_fallback(self):
        for backend, method in self.methods.items():
            events = []
            with self.subTest(backend=backend), patch("subprocess.run",
                    side_effect=AssertionError("supplied certified methods must remain offline")):
                repertoire = c.template_human_repertoire(method,
                    optimization_seconds=0, progress=events.append)
                restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
            self.assert_complete_and_replay(restored)
            self.assertEqual(repertoire.metadata["computation"]["stop_reason"], "optimization_seconds")
            self.assertEqual(repertoire.metadata["computation"]["optimization_work"], 0)
            self.assertTrue(any(e["phase"] == "baseline" and e["status"] == "certified" for e in events))
            self.assertEqual((events[-1]["phase"], events[-1]["status"]), ("complete", "certified"))

    def test_invalid_supplied_policy_is_rejected_before_certification_and_clock_start(self):
        method = self.methods["symbolic"]
        invalid = replace(method, algorithms=(replace(method.algorithms[0], turn_sequence=""),
                                              *method.algorithms[1:]))
        events, contexts = [], []

        def progress(event):
            events.append(event)
            contexts.append(current_computation())

        with patch("subprocess.run", side_effect=AssertionError("supplied input validation is offline")), \
             self.assertRaisesRegex(ValueError, "physical witness"):
            c.template_human_repertoire(invalid, optimization_seconds=0, progress=progress)
        self.assertFalse(any(e["phase"] == "baseline" and e["status"] == "certified" for e in events))
        self.assertTrue(contexts)
        self.assertTrue(all(context.quality_started is None and context.best_method is None
                            for context in contexts))
        self.assertIsNone(current_computation())

    def test_positive_shared_work_cutoff_keeps_the_initial_symbolic_certificate(self):
        events = []
        repertoire = c.template_human_repertoire(self.analysis, backend="symbolic",
            max_optimization_work=1, timeout=30, progress=events.append)
        self.assert_complete_and_replay(repertoire)
        diagnostics = repertoire.metadata["computation"]
        self.assertEqual(diagnostics["stop_reason"], "max_optimization_work")
        self.assertEqual(diagnostics["optimization_work"], 1)
        self.assertTrue(any(e["status"] == "budget_exhausted" for e in events))
        with patch("subprocess.run", side_effect=AssertionError("fallback must reload offline")):
            restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
        self.assert_complete_and_replay(restored)

    def test_time_before_certification_is_not_charged_to_optimization(self):
        clock, events = Clock(), []

        def progress(event):
            events.append(event)
            if event["phase"] == "analysis" and event["status"] == "completed":
                clock.now = 10000.
            if event["phase"] == "baseline" and event["status"] == "certified":
                clock.now = 20000.

        with patch("bce_v2.computation.monotonic", clock):
            repertoire = c.template_human_repertoire(SMALL, backend="auto",
                optimization_seconds=1, timeout=30, progress=progress)
        self.assert_complete_and_replay(repertoire)
        baseline = next(e for e in events if e["phase"] == "baseline")
        self.assertEqual(baseline["elapsed_seconds"], 10000.)
        self.assertEqual(repertoire.metadata["computation"]["stop_reason"], "optimization_seconds")

    def test_nested_calls_share_parent_counter_and_deadline(self):
        clock = Clock()
        with patch("bce_v2.computation.monotonic", clock):
            context = Computation(optimization_seconds=10, max_optimization_work=2)
            with context.activate():
                context.retain_method(self.methods["symbolic"])
                origin = context.quality_started
                checkpoint("first_chain")
                clock.now = 9.
                # The nested public entry point must reuse the active context,
                # even when its own options request a much larger allowance.
                def compile_nested(*args, **kwargs):
                    self.assertIs(current_computation(), context)
                    self.assertEqual(kwargs["backend"], "explicit")
                    checkpoint("second_chain")
                    return self.small_repertoire

                with patch.object(TEMPLATE_MODULE, "_template_human_repertoire", compile_nested):
                    c.template_human_repertoire(self.analysis, backend="auto",
                        optimization_seconds=1000, max_optimization_work=1000)
                self.assertEqual(context.work, 2)
                self.assertEqual(context.quality_started, origin)
                self.assertEqual(quality_timeout(30), 1.)
                with self.assertRaises(OptimizationBudgetExceeded):
                    checkpoint("third_chain")
                self.assertEqual(context.stop_reason, "max_optimization_work")
                with context.suspend():
                    checkpoint("mandatory_final_validation", work=1000)
                    self.assertEqual(quality_timeout(30), 30)
                self.assertEqual(context.work, 2)
                clock.now = 11.
                with self.assertRaises(OptimizationBudgetExceeded):
                    quality_timeout(30)
                self.assertEqual(context.stop_reason, "optimization_seconds")
            self.assertIsNone(current_computation())

    def test_gap_deadline_clamp_and_independent_timeout_are_distinct(self):
        clock = Clock()
        response = subprocess.CompletedProcess([], 0, "checked", "")
        with patch("bce_v2.computation.monotonic", clock):
            context = Computation(optimization_seconds=10)
            with context.activate(), patch("bce_v2.gap_backend.subprocess.run", return_value=response) as run:
                clock.now = 1000.
                _run_gap("proof", "gap", 30)
                self.assertEqual(run.call_args.kwargs["timeout"], 30)
                context.retain_method(self.methods["symbolic"])
                clock.now += 3.
                _run_gap("quality", "gap", 30)
                self.assertEqual(run.call_args.kwargs["timeout"], 7.)
                _run_gap("quality", "gap", 2)
                self.assertEqual(run.call_args.kwargs["timeout"], 2.)

                def independent_timeout(*args, **kwargs):
                    clock.now += 1.
                    raise subprocess.TimeoutExpired("gap", kwargs["timeout"])

                run.side_effect = independent_timeout
                with self.assertRaises(GapTimeoutError):
                    _run_gap("quality", "gap", 1)
                self.assertIsNone(context.stop_reason)

                def shared_deadline_timeout(*args, **kwargs):
                    clock.now += 10.
                    raise subprocess.TimeoutExpired("gap", kwargs["timeout"])

                run.side_effect = shared_deadline_timeout
                with self.assertRaises(OptimizationBudgetExceeded):
                    _run_gap("quality", "gap", 30)
                self.assertEqual(context.stop_reason, "optimization_seconds")

    def test_initial_gap_timeout_remains_a_certification_failure(self):
        with Computation(optimization_seconds=0).activate(), patch(
                "bce_v2.gap_backend.subprocess.run", side_effect=subprocess.TimeoutExpired("gap", 1)):
            with self.assertRaises(GapTimeoutError):
                _run_gap("initial proof", "gap", 1)

    def test_auto_routing_uses_group_order_and_physical_workload(self):
        small = preparation_profile(self.analysis)
        large = preparation_profile(self.large_analysis)
        many = preparation_profile(self.many_loop_analysis)
        self.assertEqual(small["recommended_backend"], "explicit")
        self.assertEqual(large["shape_count"], 1)
        self.assertFalse(large["explicit_group_eligible"])
        self.assertEqual(large["recommended_backend"], "symbolic")
        # This puzzle's reference group is small enough; its large witness
        # library makes automatic explicit quality preparation inappropriate.
        self.assertTrue(many["explicit_group_eligible"])
        self.assertGreater(many["original_loop_count"], 256)
        self.assertEqual(many["recommended_backend"], "symbolic")
        self.assertEqual(many["graph_view"], "summary")
        for analysis, expected in ((self.analysis, "explicit"),
                                   (self.large_analysis, "symbolic"),
                                   (self.many_loop_analysis, "symbolic")):
            with self.subTest(group=analysis.group_order), patch.object(TEMPLATE_MODULE,
                    "_template_human_repertoire", return_value=self.small_repertoire) as compile_method:
                result = c.template_human_repertoire(analysis, backend="auto")
            self.assertEqual(compile_method.call_args.kwargs["backend"], expected)
            self.assertIs(compile_method.call_args.args[0], analysis)
            self.assertEqual(result.metadata["computation"]["workload"]["group_order"], analysis.group_order)

    def test_preparation_profile_is_exported_by_the_public_package(self):
        self.assertIn("preparation_profile", c.__all__)
        profile = c.preparation_profile(self.analysis)
        self.assertEqual(profile["group_order"], self.analysis.group_order)
        self.assertEqual(profile["original_loop_count"], len(self.analysis.loops.generators))
        self.assertEqual(profile["recommended_backend"], "explicit")

    def test_explicit_backend_choices_and_supplied_method_backends_are_preserved(self):
        for analysis, requested in ((self.analysis, "symbolic"),
                                    (self.many_loop_analysis, "explicit")):
            with self.subTest(requested=requested), patch.object(TEMPLATE_MODULE,
                    "_template_human_repertoire", return_value=self.small_repertoire) as compile_method:
                c.template_human_repertoire(analysis, backend=requested)
            self.assertEqual(compile_method.call_args.kwargs["backend"], requested)
        for backend, method in self.methods.items():
            with self.subTest(supplied=backend), patch.object(TEMPLATE_MODULE,
                    "_template_human_repertoire", return_value=self.small_repertoire) as compile_method:
                c.template_human_repertoire(method, backend="auto")
            self.assertIs(compile_method.call_args.args[0], method)
            self.assertEqual(compile_method.call_args.kwargs["backend"], backend)

    def test_later_cutoff_returns_the_certified_repertoire_with_its_chunks(self):
        method = c.synthesize_human_method(c.fixture("Bicube Fuse"), backend="symbolic",
            strategy="fully_solve_each_block", timeout=30)
        retained = []

        def stop_optional_shared_search(*args):
            context = current_computation()
            retained.append(context.best_repertoire)
            self.assertIsNotNone(context.best_repertoire)
            self.assertEqual(context.best_repertoire.method.status, "completed")
            # Stop after the complete fallback vocabulary and its physical
            # chunks have been certified, while entering the next optional pass.
            checkpoint("forced_shared_body_cutoff", work=context.limit + 1)

        with patch("bce_v2.symbolic_template_repertoire._Bodies.shared",
                   side_effect=stop_optional_shared_search) as shared:
            repertoire = c.template_human_repertoire(method,
                max_optimization_work=1_000_000, max_trials=3, max_word_candidates=64,
                chunk_options={"max_candidates": 16, "max_chunks": 4, "min_chunk_length": 2})
        shared.assert_called_once()
        snapshot, = retained
        self.assertGreater(len(snapshot.metadata["chunk_dictionary"]["chunks"]), 0)
        self.assertEqual(repertoire.metadata["chunk_dictionary"], snapshot.metadata["chunk_dictionary"])
        self.assertEqual(repertoire.metadata["settings"], snapshot.metadata["settings"])
        self.assertEqual(repertoire.metadata["settings"]["max_trials"], 3)
        self.assertEqual(repertoire.macros, snapshot.macros)
        self.assertEqual(repertoire.stages, snapshot.stages)
        self.assertEqual(repertoire.metadata["computation"]["stop_reason"], "max_optimization_work")
        with patch("subprocess.run", side_effect=AssertionError("retained repertoire reloads offline")):
            restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
        self.assertEqual(restored.to_json(), repertoire.to_json())
        for generator in method.generators:
            source = c.State(method.reference_shape).apply(generator.moves)
            solved = restored.apply(source)
            self.assertTrue(solved.state.is_solved)
            self.assertEqual(source.apply(solved.turn_sequence), solved.state)

    def test_computation_metadata_is_portable_and_rejects_corruption(self):
        repertoire = c.template_human_repertoire(self.methods["symbolic"], optimization_seconds=0)
        record = repertoire.to_dict()
        with patch("subprocess.run", side_effect=AssertionError("portable provenance must be offline")):
            restored = c.HumanRepertoire.from_dict(record)
        self.assertEqual(restored.to_json(), repertoire.to_json())
        changes = (
            lambda m: m.__setitem__("optimization_work", -1),
            lambda m: m.__setitem__("optimization_work", True),
            lambda m: m.__setitem__("elapsed_seconds", float("nan")),
            lambda m: m.__setitem__("stop_reason", "certification_timeout"),
            lambda m: m.__setitem__("budget_scope", "all computation"),
            lambda m: m.__setitem__("max_optimization_work", 0) or m.__setitem__("optimization_work", 1),
            lambda m: m.__setitem__("workload", []),
        )
        for change in changes:
            modified = deepcopy(record)
            change(modified["metadata"]["computation"])
            # Validate diagnostics independently, then also reject rehashed
            # finite corruption through the complete portable loader.
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                validate_computation_metadata(modified["metadata"])
            if modified["metadata"]["computation"]["elapsed_seconds"] == modified["metadata"]["computation"]["elapsed_seconds"]:
                modified["fingerprint"] = _fingerprint(modified)
                with self.assertRaises((ValueError, TypeError)):
                    c.HumanRepertoire.from_dict(modified)

    def test_warm_preparation_caches_do_not_trust_rehashed_imported_witnesses(self):
        repertoire = c.template_human_repertoire(self.methods["symbolic"], optimization_seconds=0)
        record = repertoire.to_dict()
        # The valid original library has already been reused by several tests.
        # Imported data must receive fresh independent physical-witness checks.
        record["method"]["generators"][0]["moves"] = "U'"
        record["method"]["fingerprint"] = _fingerprint(record["method"])
        record["fingerprint"] = _fingerprint(record)
        with patch("subprocess.run", side_effect=AssertionError("replay verification is offline")), \
             self.assertRaises(ValueError):
            c.HumanRepertoire.from_dict(record)


if __name__ == "__main__":
    unittest.main()
