#!/usr/bin/env python3
"""Bounded solver-only profiles of the example notebooks; never execute cells.

Run with the project's v2/.venv Python. Timings include cProfile overhead and
are intended to locate dominant work, not serve as uncontended benchmarks.
Only the literal bandage assignment is read; plots and guides are skipped.
"""

import argparse
import ast
from collections import Counter
import cProfile
from functools import wraps
import importlib
import json
from pathlib import Path
import pstats
import resource
import signal
from time import perf_counter

import bce_v2 as c


class ProfileDeadline(Exception):
    pass


def bandage_from_notebook(path):
    notebook = json.loads(path.read_text())
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.parse("".join(cell["source"])).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "bandage"
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
    raise ValueError("notebook has no literal bandage assignment")


def instrument(events, show_progress=False):
    names = (
        "symbolic_chain_search", "symbolic_dictionary", "symbolic_template_repertoire",
        "human_methods", "human_chains", "symbolic_chains", "loop_algorithms",
        "symbolic_repertoire_core", "human_generator_repertoire", "human_repertoire",
    )
    modules = [importlib.import_module("bce_v2." + name) for name in names]
    selected = {
        "select_symbolic_human_chain", "discover_symbolic_dictionary",
        "plan_symbolic_stages", "plan_human_stages", "_compile_symbolic_plan",
        "_compile_plan", "_compile_dictionary_policy", "_adaptive_plan",
        "_prepare", "discover_loop_algorithms", "_validate_method",
        "build_symbolic_repertoire", "validate_symbolic_repertoire",
    }
    wrappers = {}
    for module in modules:
        for name, value in list(vars(module).items()):
            if name not in selected or not callable(value):
                continue
            if value not in wrappers:
                def wrap(function):
                    @wraps(function)
                    def timed(*args, **kwargs):
                        start = perf_counter()
                        event = {"function": function.__module__ + "." + function.__name__,
                                 "started": start, "status": "running"}
                        events.append(event)
                        visible = function.__name__ in {
                            "_prepare", "plan_symbolic_stages", "discover_symbolic_dictionary",
                            "discover_loop_algorithms", "_adaptive_plan", "build_symbolic_repertoire",
                        }
                        if show_progress and visible:
                            print(json.dumps({"phase": event["function"], "event": "started"}), flush=True)
                        try:
                            result = function(*args, **kwargs)
                            event["status"] = "completed"
                            return result
                        except BaseException as error:
                            event["status"] = type(error).__name__
                            raise
                        finally:
                            event["seconds"] = perf_counter() - start
                            if show_progress and visible:
                                print(json.dumps({"phase": event["function"], "event": event["status"],
                                                  "seconds": event["seconds"]}), flush=True)
                    return timed
                wrappers[value] = wrap(value)
            setattr(module, name, wrappers[value])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("puzzle", choices=("BeltRoad", "MostSignaturesCube", "FourPair"))
    parser.add_argument("--mode", choices=("template", "fixed", "generator", "method"), default="template")
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--reduced", action="store_true",
                        help="experimental: use GAP's exact-order reduced original witnesses")
    parser.add_argument("--no-profile", action="store_true", help="measure wall time without cProfile overhead")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1]
    bandage = bandage_from_notebook(base / "examples" / (args.puzzle + ".ipynb"))
    begin = perf_counter()
    analysis_self = resource.getrusage(resource.RUSAGE_SELF)
    analysis_child = resource.getrusage(resource.RUSAGE_CHILDREN)
    analysis = c.analyze_isotropy(bandage)
    analysis_seconds = perf_counter() - begin
    full_generators = analysis.loops.generators
    blocks = Counter(block.type or block.kind for block in analysis.block_inventory.blocks)
    record = {"puzzle": args.puzzle, "mode": args.mode, "deadline_seconds": args.seconds,
              "experimental_reduced_alphabet": args.reduced,
              "scope": "solver only; analysis is timed separately",
              "cprofile_enabled": not args.no_profile,
              "analysis_seconds": analysis_seconds, "shapes": analysis.loops.shape_count,
              "analysis_self_cpu_seconds": sum(resource.getrusage(resource.RUSAGE_SELF)[:2]) - sum(analysis_self[:2]),
              "analysis_child_cpu_seconds": sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2]) - sum(analysis_child[:2]),
              "arcs": analysis.loops.arc_count, "group_order": analysis.group_order,
              "raw_generator_count": len(analysis.loops.generators),
              "reduced_generator_count": len(analysis.generators), "block_types": dict(blocks)}
    if args.reduced:
        from bce_v2.isotropy import IsotropyAnalysis, LoopGenerators
        # Preserve original IDs/native legal witnesses. Only this fresh Python
        # view's alphabet is reduced. This is a research experiment: production
        # must explicitly certify coverage against the full native loop set.
        reduced = analysis.generators
        loops = LoopGenerators(analysis.loops._native)
        object.__setattr__(loops, "_generators", reduced)
        analysis = IsotropyAnalysis(loops, analysis.group_order,
                                   analysis.generator_ids, analysis.gap_version)
    print(json.dumps(record), flush=True)
    events = []
    instrument(events, show_progress=args.no_profile)
    profile = cProfile.Profile()
    def deadline(*_):
        raise ProfileDeadline("solver exceeded the requested wall-clock bound")
    signal.signal(signal.SIGALRM, deadline)
    begin = perf_counter()
    solver_self = resource.getrusage(resource.RUSAGE_SELF)
    solver_child = resource.getrusage(resource.RUSAGE_CHILDREN)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    if not args.no_profile:
        profile.enable()
    try:
        if args.mode == "generator":
            repertoire = c.generator_human_repertoire(analysis)
        elif args.mode == "method":
            method = c.synthesize_human_method(analysis, backend="symbolic",
                                              strategy="fully_solve_each_block")
            repertoire = None
        else:
            repertoire = c.template_human_repertoire(
                analysis, preference="memory", backend="symbolic",
                **({"select_chain": False} if args.mode == "fixed" else {}))
        method = repertoire.method if repertoire is not None else method
        record["complete_original_generator_membership_verified"] = all(
            generator.permutation in method._permutations for generator in full_generators)
        if not record["complete_original_generator_membership_verified"]:
            raise ValueError("experimental alphabet omits part of the complete native loop group")
        sample_words = [generator.moves for generator in analysis.generators[:2]]
        if len(sample_words) == 2:
            sample_words.append(" ".join(sample_words))
        samples = []
        for word in sample_words:
            state = c.State.from_facelets(c.State(method.reference_shape).apply(word).facelets,
                                         method.reference_shape)
            result = (repertoire or method).apply(state)
            if (state.scramble is not None or result.status != "solved" or not result.state.is_solved
                    or state.apply(result.turn_sequence) != result.state):
                raise ValueError("history-free root-loop sample failed solve/replay")
            samples.append({"scramble_htm": len(word.split()),
                            "solution_htm": len(result.turn_sequence.split()), "replay_verified": True})
        record["history_free_samples"] = samples
        record.update(status="completed", stages=len(method.stages),
                      cases=sum(stage.case_count for stage in method.stages),
                      method_generator_count=len(method.generators),
                      macros=len(repertoire.macros) if repertoire is not None else None,
                      coverage=method.coverage, terminal_order=method.terminal_order,
                      additive_costs=method.additive_costs())
    except ProfileDeadline:
        record["status"] = "deadline"
        print(json.dumps({"event": "deadline", "seconds": args.seconds}), flush=True)
    except Exception as error:
        record.update(status="error", error=type(error).__name__, message=str(error))
    finally:
        profile.disable()
        signal.setitimer(signal.ITIMER_REAL, 0)
    record["solver_seconds"] = perf_counter() - begin
    record["solver_self_cpu_seconds"] = sum(resource.getrusage(resource.RUSAGE_SELF)[:2]) - sum(solver_self[:2])
    record["solver_child_cpu_seconds"] = sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2]) - sum(solver_child[:2])
    for event in events:
        event["started"] -= begin
    record["phases"] = events
    rows = []
    if not args.no_profile:
        stats = pstats.Stats(profile)
        for (filename, line, function), (primitive, calls, own, cumulative, _) in stats.stats.items():
            rows.append({"file": filename, "line": line, "function": function,
                         "primitive_calls": primitive, "calls": calls,
                         "own_seconds": own, "cumulative_seconds": cumulative})
    record["profile_by_cumulative"] = sorted(rows, key=lambda row: -row["cumulative_seconds"])[:40]
    record["profile_by_own"] = sorted(rows, key=lambda row: -row["own_seconds"])[:30]
    output = args.output or base / "research-results" / (
        args.puzzle.lower() + "-" + args.mode + ("-reduced" if args.reduced else "") + "-profile.json")
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: record[key] for key in ("puzzle", "mode", "status", "solver_seconds")}), flush=True)
    print("Saved", output)


if __name__ == "__main__":
    main()
