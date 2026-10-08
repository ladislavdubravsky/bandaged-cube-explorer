#!/usr/bin/env python3
"""Reproduce exact block-feature chains, without synthesizing a human method.

Run with the installed v2 Python environment and GAP:

    v2/.venv/bin/python v2/research/probe_human_chains.py \
        --output /tmp/human-chain-baseline.json \
        --measurements /tmp/human-chain-measurements.json

The default probes the three bundled fixtures and the documented Most
Signatures Cube reference. Select individual inputs with repeated --puzzle.
JSON results are deterministic; optional timings and process high-water RSS
are written separately. An explicitly requested group-element limit is
checked against the certified order before enumeration and exits with code 2.
There is no default enumeration limit.

Only the small-group research backend lives here. Complete chain structure
does not establish a case policy, short algorithms, or human memorability.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
import json
from math import prod
from pathlib import Path
import platform
import sys
from time import perf_counter

import bce_v2 as c


IDENTITY = tuple(range(48))
MOST_SIGNATURES = (
    0, 0, 0, 0, 0, 0, 1, 0, 0,
    7, 6, 5, 8, 0, 4, 1, 2, 3,
    7, 6, 5, 8, 0, 4, 1, 2, 3,
)
PUZZLES = ("Alcatraz", "Bicube Fuse", "Shark Fin Soup", "Most Signatures Cube")
STRATEGIES = {
    "placement_then_orientation": ("place_block", "solve_block"),
    "fully_solve_each_block": ("solve_block",),
}


def require(condition, message):
    """Validation must remain enabled when Python runs with -O."""
    if not condition:
        raise ValueError(message)


def then(first, second):
    """Compose source-to-destination permutations in execution order."""
    return tuple(second[p] for p in first)


def inverse(permutation):
    result = [0] * len(permutation)
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


def enumerate_group(generators, expected_order):
    """Close the selected alphabet and verify its independently known order."""
    generators = tuple(generators)
    alphabet = tuple(dict.fromkeys((*generators, *(inverse(g) for g in generators))))
    seen = {IDENTITY}
    queue = deque([IDENTITY])
    while queue:
        element = queue.popleft()
        for generator in alphabet:
            successor = then(element, generator)
            if successor not in seen:
                require(len(seen) < expected_order,
                        "enumeration exceeds the certified group order")
                seen.add(successor)
                queue.append(successor)
    require(len(seen) == expected_order,
            "enumerated group order disagrees with GAP")
    return tuple(sorted(seen)), alphabet


@dataclass(frozen=True)
class ActionSummary:
    """Only coordinates used by this probe; BlockAction remains authoritative."""

    destinations: tuple[int, ...]
    phases: tuple[int, ...]


def action_summaries(inventory, elements):
    summaries = {}
    for permutation in elements:
        action = inventory.action(permutation)
        require(action.to_permutation() == permutation,
                "block action fails exact sticker reconstruction")
        summaries[permutation] = ActionSummary(action.destinations, action.phases)
    return summaries


def check_feature_actions(inventory, elements, alphabet, summaries):
    """Check all oriented-block action formulas on every element/generator.

    This independently checks the action contract underlying the stabilizer
    predicates, including destination-indexed phase transport. It establishes
    equivariance on all generator transitions, not only selected examples.
    """
    moduli = tuple(block.orientation_order for block in inventory.blocks)
    for permutation in elements:
        action = summaries[permutation]
        for generator in alphabet:
            next_action = summaries[generator]
            composed = summaries[then(permutation, generator)]
            destinations = tuple(next_action.destinations[d] for d in action.destinations)
            phases = tuple((phase + next_action.phases[d]) % modulus
                           for d, phase, modulus in
                           zip(action.destinations, action.phases, moduli))
            require(composed.destinations == destinations and composed.phases == phases,
                    "block-feature observations are not equivariant")


def observe(action, block, kind):
    if kind == "place_block":
        return (action.destinations[block],)
    if kind == "solve_block":
        return (action.destinations[block], action.phases[block])
    raise ValueError(f"unknown feature kind: {kind}")


def validate_cosets(current, target, fibers):
    """Every feature fiber must be the right coset K*t, not just equal in size."""
    require(IDENTITY in target, "a stage target must contain the identity")
    require(len(current) == len(target) * len(fibers),
            "feature orbit size disagrees with the stabilizer index")
    for fiber in fibers.values():
        representative = fiber[0]
        require({then(k, representative) for k in target} == set(fiber),
                "feature observation does not identify a right coset")


def build_chain(inventory, elements, summaries, strategy):
    """Select the smallest nontrivial index, then stable inventory order."""
    current = elements
    stages = []
    placement_order = None
    for kind in STRATEGIES[strategy]:
        while True:
            candidates = []
            for block in range(len(inventory.blocks)):
                solved = observe(summaries[IDENTITY], block, kind)
                target = tuple(p for p in current
                               if observe(summaries[p], block, kind) == solved)
                if 0 < len(target) < len(current):
                    require(len(current) % len(target) == 0,
                            "feature target order does not divide its stage group")
                    candidates.append((len(current) // len(target), block, target))
            if not candidates:
                break
            index, block, target = min(candidates, key=lambda item: item[:2])
            fibers = defaultdict(list)
            for permutation in current:
                fibers[observe(summaries[permutation], block, kind)].append(permutation)
            validate_cosets(current, target, fibers)
            slot = inventory.blocks[block]
            stages.append({
                "feature": {"kind": kind, "block_index": block,
                            "reference_cells": list(slot.cells), "block_name": slot.name},
                "order_before": str(len(current)), "order_after": str(len(target)),
                "index": index,
                "solved_observation": list(observe(summaries[IDENTITY], block, kind)),
                "observations": [list(value) for value in sorted(fibers)],
            })
            current = target
        if kind == "place_block":
            placement_order = len(current)
    require(current == (IDENTITY,), "chain leaves a nontrivial colored residual")
    require(prod(stage["index"] for stage in stages) == len(elements),
            "chain index product disagrees with the root group order")
    result = {"stages": stages, "terminal_order": "1",
              "case_count_sum": sum(stage["index"] for stage in stages),
              "maximum_case_count": max((stage["index"] for stage in stages), default=0)}
    if placement_order is not None:
        result["placement_terminal_order"] = str(placement_order)
    return result


def peak_rss_kib():
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes. This is process high-water RSS,
    # not an isolated per-puzzle measurement when several puzzles share a run.
    return round(value / 1024) if sys.platform == "darwin" else value


def probe(shape, *, name=None, max_group_elements=None, gap_executable="gap", timeout=None):
    """Check chain structure for a reference shape, never a scramble solution."""
    if max_group_elements is not None:
        if isinstance(max_group_elements, bool) or not isinstance(max_group_elements, int):
            raise TypeError("max_group_elements must be a positive integer or None")
        if max_group_elements <= 0:
            raise ValueError("max_group_elements must be positive")
    started = perf_counter()
    analysis = c.isotropy_loops(shape).analyze(gap_executable=gap_executable, timeout=timeout)
    prepared = perf_counter()
    structure = c.analyze_block_structure(analysis, gap_executable=gap_executable, timeout=timeout)
    structured = perf_counter()
    inventory = analysis.block_inventory
    record = {
        "puzzle": name, "reference_shape": inventory.root_shape.labels,
        "model": "full-grid-27-fixed-centers", "frame": "fixed",
        "shape_component_complete": True,
        "permutation_action": "source-to-destination",
        "permutation_composition": "execution-order",
        "gap_version": analysis.gap_version,
        "group_order": str(analysis.group_order),
        "quotient_order": str(structure.quotient_order),
        "kernel_order": str(structure.kernel_order),
        "shape_count": analysis.loops.shape_count, "arc_count": analysis.loops.arc_count,
        "extracted_generator_count": len(analysis.loops),
        "reduced_generator_ids": list(analysis.generator_ids),
        "block_inventory": inventory.to_dict(),
        "coverage_scope": "chain_structure_only", "human_method_complete": False,
        "selection": "smallest nontrivial index, then stable block inventory order",
        "limits": {"max_group_elements": max_group_elements},
    }
    measurements = {"puzzle": name, "prepare_seconds": prepared - started,
                    "block_structure_seconds": structured - prepared}
    if max_group_elements is not None and analysis.group_order > max_group_elements:
        record.update(status="limit_reached", reason="group_order_exceeds_limit",
                      enumerated_elements=0, enumeration_complete=False, chains={})
    else:
        initial = c.State(inventory.root_shape)
        for generator in analysis.generators:
            replay = initial.apply(generator.turn_sequence)
            require(replay.shape == inventory.root_shape and
                    tuple(replay.sticker_permutation) == generator.permutation,
                    "original loop witness fails legal fixed-frame colored replay")
        replayed = perf_counter()
        elements, alphabet = enumerate_group(
            (generator.permutation for generator in analysis.generators), analysis.group_order)
        enumerated = perf_counter()
        summaries = action_summaries(inventory, elements)
        check_feature_actions(inventory, elements, alphabet, summaries)
        reconstructed = perf_counter()
        kernel = tuple(p for p in elements if summaries[p].destinations ==
                       summaries[IDENTITY].destinations)
        placements = {summaries[p].destinations for p in elements}
        require(len(kernel) == structure.kernel_order and
                len(placements) == structure.quotient_order,
                "enumerated placement/kernel orders disagree with GAP")
        chains = {strategy: build_chain(inventory, elements, summaries, strategy)
                  for strategy in STRATEGIES}
        require(int(chains["placement_then_orientation"]["placement_terminal_order"]) == len(kernel),
                "placement stages do not terminate at the footprint-fixing kernel")
        record.update(
            status="completed", enumeration_complete=True, enumerated_elements=len(elements),
            alphabet_size=len(alphabet), chains=chains,
            generators=[generator.to_dict() for generator in analysis.generators],
            validation={"selected_generator_replays": len(analysis.generators),
                        "action_roundtrips": len(elements),
                        "equivariant_generator_transitions": len(elements) * len(alphabet),
                        "orders_match_gap": True, "all_stage_fibers_are_right_cosets": True},
        )
        measurements.update(generator_replay_seconds=replayed - structured,
                            enumeration_seconds=enumerated - replayed,
                            action_validation_seconds=reconstructed - enumerated,
                            chain_validation_seconds=perf_counter() - reconstructed)
    measurements.update(elapsed_seconds=perf_counter() - started,
                        process_peak_rss_kib=peak_rss_kib())
    return record, measurements


def reference_shape(name):
    return c.Shape(MOST_SIGNATURES) if name == "Most Signatures Cube" else c.fixture(name)


def json_text(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def positive_integer(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", choices=PUZZLES, action="append",
                        help="repeat to select references; default: all four")
    parser.add_argument("--output", type=Path, help="write deterministic JSON instead of stdout")
    parser.add_argument("--measurements", type=Path, help="write separate timing/RSS diagnostics")
    parser.add_argument("--max-group-elements", type=positive_integer, default=None,
                        help="explicit preflight bound; larger certified groups are not enumerated")
    parser.add_argument("--gap-executable", default="gap")
    parser.add_argument("--timeout", type=float, default=None, help="seconds per GAP operation")
    args = parser.parse_args(argv)
    if args.output is not None and args.measurements is not None:
        same_path = args.output.resolve() == args.measurements.resolve()
        if args.output.exists() and args.measurements.exists():
            same_path = same_path or args.output.samefile(args.measurements)
        if same_path:
            parser.error("--output and --measurements must name different files")
    records, measurements = [], []
    try:
        for name in args.puzzle or PUZZLES:
            record, measurement = probe(reference_shape(name), name=name,
                                        max_group_elements=args.max_group_elements,
                                        gap_executable=args.gap_executable, timeout=args.timeout)
            records.append(record)
            measurements.append(measurement)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"probe failed: {error}\n")
    report = {"format": "bce-v2-human-chain-probe", "version": 1,
              "human_method_complete": False, "results": records}
    if args.output is None:
        sys.stdout.write(json_text(report))
    else:
        args.output.write_text(json_text(report), encoding="utf-8")
    if args.measurements is not None:
        args.measurements.write_text(json_text({
            "format": "bce-v2-human-chain-measurements", "version": 1,
            "environment": {"python": platform.python_version(),
                            "platform": platform.platform()},
            "rss_scope": "process high-water mark; cumulative across puzzles in one invocation",
            "results": measurements,
        }), encoding="utf-8")
    return 0 if all(record["status"] == "completed" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
