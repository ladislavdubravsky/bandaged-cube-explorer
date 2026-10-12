"""Notebook views retain exact-domain and sampled bounded-entry cost scopes."""

from copy import deepcopy
from dataclasses import replace
import importlib.util
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.notebook_method_views import (
    coarse_method_overview,
    coarse_validation_summary,
    method_application_diagram,
    method_application_trace,
    workspace_method_overview,
    workspace_sample_summary,
)
from bce_v2.coarse_methods import _palette_record


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare the small certificate")
class NotebookMethodViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1] * 9 + [2] * 18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        builder = c.AlgorithmLibrary(cls.analysis.loops, (), (), ())
        generator = next(loop for loop in cls.analysis.loops.generators if loop.turn_sequence == "U")
        cls.clockwise = replace(builder.build_algorithm(c.LoopExpression.loop(generator.id)),
                                id="clockwise")
        cls.feature = c.BlockFeature("solve_block", tuple(range(9)))
        palette = c.AlgorithmPalette.from_algorithms((cls.clockwise,), allow_inverse=False)
        cls.coarse = c.compile_coarse_method(cls.analysis, features=(cls.feature,), palette=palette,
                                             timeout=30)
        cls.suffix = c.compile_coarse_method(cls.analysis, features=(),
            palette=c.AlgorithmPalette(()), domain_features=(cls.feature,), timeout=30)
        cls.adjustments = c.AlgorithmPalette.from_algorithms((), adjustments=(cls.clockwise,))
        cls.workspace = c.compile_workspace_method(cls.suffix, entry_palette=cls.adjustments,
            max_taught_bodies=0, controller_options={"max_depth": 4, "max_pattern_count": 0})
        cls.limited = c.compile_workspace_method(cls.suffix, entry_palette=cls.adjustments,
                                                max_entry_nodes=0, max_taught_bodies=0)

    def state(self, word):
        return c.State.from_facelets(c.State(self.shape).apply(word).facelets, self.shape)

    def test_overview_uses_fused_geometry_exact_stage_cost_and_declared_body(self):
        view = coarse_method_overview(self.coarse)
        self.assertIn("all **4** reference-group states", view)
        self.assertIn("Taught bodies: **1**", view)
        self.assertIn("before cancellation between stage words", view)
        self.assertIn(f"**{self.coarse.additive_costs()['htm']['mean']:.2f} HTM**", view)
        self.assertIn("clockwise", view)
        self.assertIn("Inverse permitted", view)
        self.assertIn("No", view)
        self.assertIn("| 4 |", view)
        self.assertNotIn("F2L", view)
        self.assertNotIn("62.47", view)

    def test_trace_reports_actual_named_calls_and_endpoint_word(self):
        state = self.state("U")
        with patch("subprocess.run", side_effect=AssertionError("views execute offline")):
            application = self.workspace.apply(state)
            view = method_application_trace(self.workspace, application)
            self.assertIn("**solved**", view)
            self.assertIn(application.entry_steps[0].turn_sequence, view)
            self.assertIn("`clockwise`", view)
            self.assertIn("Entry 1", view)
            self.assertIn("Prior constrained components", view)
            self.assertNotIn("Continuation 1", view)
            self.assertEqual(state.apply(application.turn_sequence), application.state)

    def test_summary_keeps_failed_attempts_out_of_completed_means(self):
        solved = self.workspace.apply(self.state("U"))
        already = self.workspace.apply(self.state(""))
        failure = self.limited.apply(self.state("U"))
        self.assertEqual(failure.status, "entry_limit")
        view = workspace_sample_summary(self.workspace, (solved, already, failure),
                                        scrambles=("U", "", "U"))
        self.assertIn("Solved **2 / 3**", view)
        self.assertIn("**2 completed solutions**", view)
        self.assertIn("entry **0.50 HTM**", view)
        self.assertIn("entry_limit: 1", view)
        self.assertIn("solved: 2", view)
        self.assertIn("excluded from completed-solution means", view)
        self.assertIn(failure.reason, view)

    def test_empty_and_all_failed_samples_have_no_synthetic_average(self):
        empty = workspace_sample_summary(self.workspace, ())
        self.assertIn("Solved **0 / 0**", empty)
        self.assertIn("means are undefined", empty)
        failure = self.limited.apply(self.state("U"))
        view = workspace_sample_summary(self.workspace, (failure,))
        self.assertIn("Solved **0 / 1**", view)
        self.assertIn("means are undefined", view)
        with self.assertRaisesRegex(ValueError, "equal lengths"):
            workspace_sample_summary(self.workspace, (failure,), scrambles=())

    def test_workspace_overview_keeps_entry_bound_and_coverage_explicit(self):
        view = workspace_method_overview(self.workspace)
        self.assertIn("Entry is bounded search", view)
        self.assertIn("**0 / 0**", view)
        self.assertIn("expanded nodes in total", view)
        self.assertIn("all **1** reference-group states", view)
        self.assertIn("Starting contract:", view)

    def test_coarse_trace_and_already_solved_trace(self):
        application = self.coarse.apply(self.state("U"))
        view = method_application_trace(self.coarse, application)
        self.assertIn("Continuation 1", view)
        self.assertIn("`clockwise`", view)
        view = method_application_trace(self.coarse, self.coarse.apply(self.state("")))
        self.assertIn("No corrections were executed", view)
        self.assertIn("**0 HTM**", view)

    def validation_record(self):
        method = self.coarse
        cases = {(number, observation): list(path)
                 for number, observation, path in method.case_recipes}
        applications = [method.apply(self.state(word)) for word in ("", "U", "U2", "U'")]
        costs = [len(application.turn_sequence.split()) for application in applications]
        return {"format": "bce-v2-discovered-last-layer-acceptance", "version": 1,
                "reference_shape": method.reference_shape.labels,
                "validation_palette": _palette_record(method.palette),
                "coverage_scope": method.coverage_scope,
                "start_domain_order": method.group_order,
                "ambient_group_order": str(method.ambient_group_order),
                "inferred_workspace_features": [feature.to_dict() for feature in method.domain_features],
                "discovered_stage_features": [stage.feature.to_dict() for stage in method.stages],
                "case_counts": [stage.case_count for stage in method.stages],
                "certified_additive_costs": method.additive_costs(),
                "supplied_long_bodies": {body.id: body.algorithm.turn_sequence
                                         for body in method.palette.bodies},
                "used_long_body_ids": list(method.taught_body_ids),
                "complete_physical_state_replays": method.group_order,
                "distinct_native_states": method.group_order,
                "all_complete_states_solved": True,
                "all_cumulative_endpoint_goals_preserved": True,
                "loaded_method_replayed_without_gap": True,
                "strict_palette_coverage": True,
                "unconstrained_fallback_used": False,
                "mean_last_layer_physical_htm": sum(costs) / len(costs),
                "worst_last_layer_physical_htm": max(costs),
                "cumulative_stabilizer_endpoint_checks": sum(len(application.steps)
                                                            for application in applications),
                "stage_reports": [{"stage": stage.number, "feature": stage.feature.to_dict(),
                    "case_count": stage.case_count, "order_before": str(stage.order_before),
                    "order_after": str(stage.order_after),
                    "complete_native_hidden_state_visits": method.group_order,
                    "cases": [{"observation": list(case.observation),
                               "recipe": cases[stage.number, case.observation]}
                              for case in stage.cases]} for stage in method.stages]}

    def test_retained_physical_cost_is_bound_to_current_domain_and_all_case_recipes(self):
        record = self.validation_record()
        view = coarse_validation_summary(self.coarse, record)
        self.assertIn("Previous exhaustive native replay matching this policy", view)
        self.assertIn("**4 / 4**", view)
        self.assertIn("Mean concatenated physical continuation", view)
        self.assertIn("excludes entry", view)
        altered = deepcopy(record)
        altered["validation_palette"]["bodies"][0]["algorithm"]["expression"] = {"unrelated_proof": True}
        self.assertIn("matching this policy", coarse_validation_summary(self.coarse, altered))
        for kind in ("word", "recipe", "domain", "visits", "permission", "additive", "setup", "adjustment"):
            altered = deepcopy(record)
            if kind == "word":
                altered["validation_palette"]["bodies"][0]["algorithm"]["turn_sequence"] = "U'"
            elif kind == "recipe":
                next(case for case in altered["stage_reports"][0]["cases"]
                     if case["recipe"])["recipe"] = []
            elif kind == "domain":
                altered["inferred_workspace_features"] = [self.feature.to_dict()]
            elif kind == "visits":
                altered["distinct_native_states"] -= 1
            elif kind == "permission":
                altered["validation_palette"]["bodies"][0]["allow_inverse"] = True
            elif kind == "additive":
                altered["certified_additive_costs"]["htm"]["mean"] += 1
            else:
                altered["validation_palette"]["setups" if kind == "setup" else "adjustments"].append(
                    {"id": "new-operation", "algorithm": deepcopy(
                        altered["validation_palette"]["bodies"][0]["algorithm"])})
            with self.subTest(kind=kind):
                self.assertIn("No matching previous exhaustive", coarse_validation_summary(self.coarse, altered))
        self.assertIn("No matching previous exhaustive", coarse_validation_summary(self.coarse, {}))

    def test_retained_physical_cost_rejects_incomplete_or_malformed_reports(self):
        for key in ("validation_palette", "reference_shape", "stage_reports"):
            altered = self.validation_record()
            del altered[key]
            self.assertIn("No matching previous exhaustive", coarse_validation_summary(self.coarse, altered))
        altered = self.validation_record()
        altered["stage_reports"][0]["cases"].append(altered["stage_reports"][0]["cases"][0])
        self.assertIn("No matching previous exhaustive", coarse_validation_summary(self.coarse, altered))
        for value in (float("nan"), float("inf"), -1, "1"):
            altered = self.validation_record()
            altered["mean_last_layer_physical_htm"] = value
            self.assertIn("No matching previous exhaustive", coarse_validation_summary(self.coarse, altered))

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "matplotlib is optional")
    def test_diagrams_use_real_fused_before_after_states_and_step_bounds(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        application = self.workspace.apply(self.state("U"))
        figure = method_application_diagram(self.workspace, application, step_index=0)
        self.assertEqual(len(figure.axes), 4)
        self.assertIn("Before correction", figure.axes[0].get_title())
        self.assertIn("After correction", figure.axes[2].get_title())
        plt.close(figure)
        for value in (-1, True, len(application.entry_steps)):
            with self.assertRaisesRegex(ValueError, "executed trace"):
                method_application_diagram(self.workspace, application, step_index=value)


if __name__ == "__main__":
    unittest.main()
