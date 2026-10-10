#!/usr/bin/env python3
"""Measure production reduced-basis plans while checking full native coverage.

Run with v2/.venv/bin/python. Graph pictures and optional quality mining are
excluded; each completed method is replayed on three history-free states.
"""

import json
from pathlib import Path
from time import perf_counter, process_time

import bce_v2 as c
from bce_v2.human_methods import _compile_plan
from profile_notebook_graph import notebook_bandage


DESTINATION = Path(__file__).resolve().parent.parent / "research-results" / "staged-performance-implementation-plans.json"


def measured(function):
    wall, cpu = perf_counter(), process_time()
    result = function()
    return result, {"wall_seconds": perf_counter() - wall, "python_cpu_seconds": process_time() - cpu}


def probe(name):
    shape = c.Shape(notebook_bandage(name))
    analysis, analysis_time = measured(lambda: c.analyze_isotropy(shape, timeout=90))
    plan, plan_time = measured(lambda: c.plan_human_stages(analysis, backend="symbolic", timeout=90))
    full = analysis.loops.generators
    coverage, coverage_time = measured(lambda: all(plan.group.contains(g.permutation) for g in full))
    assert coverage
    assert plan.group.root_generators == tuple(g.permutation for g in full)
    assert plan.group.input_generators == plan.group.root_generators
    assert all(stage.group_after.root_generators is plan.group.root_generators for stage in plan.stages)
    method, compile_time = measured(lambda: _compile_plan(plan))
    roots = analysis.generators
    words = [roots[0].turn_sequence,
             roots[0].turn_sequence + " " + roots[-1].turn_sequence,
             roots[-1].turn_sequence + " " + roots[0].turn_sequence + " " + roots[-1].turn_sequence]
    replays = []
    for word in words:
        scrambled = c.State(shape).apply(word)
        state = c.State.from_cubies(shape, corners=scrambled.corners, twists=scrambled.twists,
                                   edges=scrambled.edges, flips=scrambled.flips)
        solved, solve_time = measured(lambda: method.apply(state))
        assert state.scramble is None
        assert solved.status == "solved" and solved.state.is_solved
        assert state.apply(solved.turn_sequence) == solved.state
        replays.append({"input_htm": len(word.split()), "solution_htm": len(solved.turn_sequence.split()), **solve_time})
    result = {"puzzle": name, "shape_count": analysis.loops.shape_count,
              "native_generator_count": len(full), "algebra_generator_count": len(plan.algebra_generators),
              "algebra_generator_ids": [g.id for g in plan.algebra_generators],
              "reference_group_order": analysis.group_order, "quotient_order": plan.quotient_order,
              "kernel_order": plan.kernel_order, "stage_count": len(plan.stages),
              "case_count": sum(stage.case_count for stage in plan.stages),
              "terminal_order": plan.terminal_order, "full_native_coverage": coverage,
              "analysis": analysis_time, "planning_including_full_certificate": plan_time,
              "independent_full_membership_check": coverage_time,
              "executable_compilation_including_validation": compile_time,
              "fallback_additive_htm": method.additive_costs()["htm"],
              "history_free_replays": replays}
    print(json.dumps(result), flush=True)
    return result


def main():
    record = {"scope": "production reduced-basis symbolic control plans; full native certificate and physical witness validation retained; optional graph rendering and quality search excluded",
              "measurements": []}
    for name in ("BeltRoad", "MostSignaturesCube", "FourPair"):
        record["measurements"].append(probe(name))
        DESTINATION.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
