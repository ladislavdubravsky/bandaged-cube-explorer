#!/usr/bin/env python3
"""Measure the updated notebook solver, rendered guide and certified replays.

Run with v2/.venv/bin/python. Reads only literal notebook bandages; production
APIs are used without runtime patches. Optional graph layout is excluded.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter

import bce_v2 as c
from profile_notebook_graph import notebook_bandage


def measured(function):
    start = perf_counter()
    value = function()
    return value, perf_counter() - start


def probe(name, seconds):
    shape = c.Shape(notebook_bandage(name))
    analysis, analysis_seconds = measured(lambda: c.analyze_isotropy(shape))
    events = []

    def progress(event):
        events.append(event)
        if event["status"] != "running":
            print(json.dumps({"puzzle": name, **event}), flush=True)

    repertoire, solver_seconds = measured(lambda: c.template_human_repertoire(
        analysis, preference="memory", backend="auto", optimization_seconds=seconds,
        progress=progress))
    method = repertoire.method
    assert method.status == "completed" and method.terminal_order == 1
    full_coverage, coverage_seconds = measured(lambda: all(
        generator.permutation in method._permutations for generator in analysis.loops.generators))
    assert full_coverage
    guide, guide_seconds = measured(lambda: repertoire.write_guide(
        diagram_mode=c.DiagramMode.OPPOSITE_CORNERS,
        face_colors=dict(U="white", R="red", F="green", D="yellow", L="orange", B="blue")))
    assert len(guide) > 0
    roots = analysis.generators
    words = [roots[0].turn_sequence,
             roots[0].turn_sequence + " " + roots[-1].turn_sequence,
             roots[-1].turn_sequence + " " + roots[0].turn_sequence + " " + roots[-1].turn_sequence]
    samples = []
    for word in words:
        scrambled = c.State(shape).apply(word)
        state = c.State.from_facelets(scrambled.facelets, shape)
        solution, elapsed = measured(lambda: repertoire.apply(state))
        assert state.scramble is None and solution.status == "solved" and solution.state.is_solved
        assert state.apply(solution.turn_sequence) == solution.state
        samples.append(dict(input_htm=len(word.split()), solution_htm=len(solution.turn_sequence.split()),
                            wall_seconds=elapsed, replay_verified=True))
    result = dict(puzzle=name, status="completed", analysis_seconds=analysis_seconds,
        solver_including_validation_seconds=solver_seconds, guide_render_seconds=guide_seconds,
        total_analysis_solver_guide_seconds=analysis_seconds + solver_seconds + guide_seconds,
        guide_bytes=len(guide.encode()), backend=method.backend, stages=len(method.stages),
        cases=sum(stage.case_count for stage in method.stages), macros=len(repertoire.macros),
        group_order=method.group_order, terminal_order=method.terminal_order,
        full_native_generator_coverage=full_coverage, full_membership_check_seconds=coverage_seconds,
        additive_htm=method.additive_costs()["htm"], selected_metrics=repertoire.metadata["selected_metrics"],
        computation=repertoire.metadata["computation"], history_free_replays=samples, progress_events=events)
    print(json.dumps({key: value for key, value in result.items() if key != "progress_events"}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=("BeltRoad", "MostSignaturesCube", "FourPair"))
    parser.add_argument("--optimization-seconds", type=float, default=120)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                        "research-results" / "staged-performance-implementation-repertoires.json")
    args = parser.parse_args()
    record = dict(scope="updated notebook production APIs; analysis, certified solver and actual guide rendering timed separately; optional graph rendering excluded",
                  runtime_patches=False, optimization_seconds=args.optimization_seconds,
                  measurement_note="Wall times depend on machine load; no before/after ratio is claimed.", measurements=[])
    for name in ((args.puzzle,) if args.puzzle else ("BeltRoad", "MostSignaturesCube", "FourPair")):
        record["measurements"].append(probe(name, args.optimization_seconds))
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
