#!/usr/bin/env python3
"""Measure bounded runtime prefix choice with an unchanged staged method.

Run probe_geometric_chain.py --templates first to create its greedy method.
Try the empty prefix and each of 18 one-turn prefixes, apply the same compiled
method, and choose the shortest physically simplified complete solution.
This keeps the learned algorithms fixed, but adds search over whole solutions
at runtime. It is a computational diagnostic, not a demonstrated human method.
"""

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

import bce_v2 as c
from bce_v2._moves import _simplified_moves


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", type=Path, default=Path("/tmp/geometric-chain-greedy_control.json"))
    parser.add_argument("--source", type=Path, default=base / "research-results/geometric-chain-probe.json")
    parser.add_argument("--output", type=Path, default=base / "research-results/staged-prefix-search-probe.json")
    args = parser.parse_args()
    method = c.HumanMethod.from_dict(json.loads(args.method.read_text()))
    source = json.loads(args.source.read_text())
    control = next(row for row in source["results"] if row["name"] == "greedy_control")
    prefixes = ("", *(face + suffix for face in "URFDLB" for suffix in ("", "'", "2")))
    results = []
    started = perf_counter()
    for sample in control["samples"]:
        state = c.State.from_facelets(c.State(method.reference_shape).apply(sample["scramble"]).facelets,
                                     method.reference_shape)
        candidates = []
        for prefix in prefixes:
            after_prefix = state.apply(prefix)
            solution = method.apply(after_prefix)
            assert solution.status == "solved" and solution.state.is_solved
            word = _simplified_moves((prefix + " " + solution.turn_sequence).split())
            assert state.apply(word) == solution.state
            candidates.append(dict(prefix=prefix, htm=len(word.split()), turn_sequence=word))
        chosen = min(candidates, key=lambda row: (row["htm"], len(row["prefix"].split()), row["prefix"]))
        assert candidates[0]["htm"] == sample["htm"]
        results.append(dict(scramble=sample["scramble"], baseline_htm=sample["htm"],
                            chosen=chosen, candidate_lengths=[row["htm"] for row in candidates]))
    record = dict(format="bce-v2-staged-runtime-prefix-diagnostic", version=1,
        scope="32 fixed seeded 30-turn imports; no exact uniform-group average claim",
        method_source=str(args.method), method_sha256=hashlib.sha256(args.method.read_bytes()).hexdigest(),
        control_macro_count=len(control["macro_words"]),
        control_learned_body_count_gt4=control["learned_gt4_count"],
        learned_algorithms_changed=False, prefixes=prefixes, complete_policy_evaluations=len(prefixes)*len(results),
        baseline_sample_mean_htm=sum(row["baseline_htm"] for row in results)/len(results),
        selected_sample_mean_htm=sum(row["chosen"]["htm"] for row in results)/len(results),
        selected_sample_worst_htm=max(row["chosen"]["htm"] for row in results),
        improved_samples=sum(row["chosen"]["htm"] < row["baseline_htm"] for row in results),
        all_replays_verified=True, wall_seconds=perf_counter()-started, samples=results)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in record.items() if key not in ("samples", "prefixes")}), flush=True)


if __name__ == "__main__":
    main()
