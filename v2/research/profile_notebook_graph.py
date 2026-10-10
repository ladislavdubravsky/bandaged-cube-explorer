#!/usr/bin/env python3
"""Measure notebook graph preparation without running a quadratic full layout.

Run with v2/.venv/bin/python. Sampled repulsion timings are extrapolations,
not measured full-layout completion times. No solver or graph code is changed.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import signal
from statistics import median
from time import perf_counter, process_time

import bce_v2 as c
from bce_v2 import graph_render as render


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def notebook_bandage(name):
    notebook = json.loads((EXAMPLES / f"{name}.ipynb").read_text())
    # Read the literal without importing or executing notebook drawing cells.
    import ast

    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            for node in ast.parse("".join(cell["source"])).body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "bandage"
                        for target in node.targets):
                    return ast.literal_eval(node.value)
    raise ValueError(f"{name} has no literal bandage assignment")


def bounded_symmetry(graph, seconds):
    interrupted = {}

    class Deadline(Exception):
        pass

    def expired(signum, frame):
        interrupted.update(function=frame.f_code.co_name, line=frame.f_lineno,
                           file=frame.f_code.co_filename)
        raise Deadline()

    previous = signal.signal(signal.SIGALRM, expired)
    start = perf_counter()
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        symmetry = render._planar_symmetry(graph)
        return symmetry, {"status": "completed", "seconds": perf_counter() - start}
    except Deadline:
        return None, {"status": "cutoff", "seconds": perf_counter() - start,
                      "interrupted_at": interrupted}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def linear_cycles(permutation):
    """Same deterministic cycle order, using one ordered scan of vertex IDs."""
    unseen = set(range(len(permutation)))
    result = []
    for vertex in range(len(permutation)):
        if vertex not in unseen:
            continue
        cycle = []
        while vertex in unseen:
            unseen.remove(vertex)
            cycle.append(vertex)
            vertex = permutation[vertex]
        result.append(cycle)
    return result


def measure(name, samples, symmetry_seconds):
    bandage = notebook_bandage(name)
    start = perf_counter()
    graph = c.explore(bandage)
    exploration_seconds = perf_counter() - start
    print(f"{name}: explored {len(graph)} shapes in {exploration_seconds:.3f}s", flush=True)
    nx, np = render._dependencies()
    start = perf_counter()
    geometry = render._geometry(graph, nx)
    geometry_seconds = perf_counter() - start
    symmetry, symmetry_measurement = bounded_symmetry(graph, symmetry_seconds)
    print(f"{name}: symmetry {symmetry_measurement}", flush=True)
    # Compare a local implementation of the same cycle decomposition only.
    # Restore production code even when the bounded experiment fails.
    original_cycles = render._cycles
    try:
        render._cycles = linear_cycles
        fast_symmetry, fast_measurement = bounded_symmetry(graph, symmetry_seconds)
    finally:
        render._cycles = original_cycles
    print(f"{name}: linear cycles symmetry {fast_measurement}", flush=True)
    if symmetry is not None and fast_symmetry != symmetry:
        raise ValueError("linear cycle scan changed the selected symmetry")
    actions = render._actions(graph)
    degrees = Counter(vertex for source, target, _ in actions for vertex in (source, target))
    count = len(graph)
    rng = np.random.RandomState(0)
    positions = rng.normal(size=(count, 2))
    block_rows = min(count, 128)
    elapsed, cpu_elapsed = [], []
    for sample in range(samples):
        first = (sample * block_rows) % max(1, count - block_rows + 1)
        start, cpu_start = perf_counter(), process_time()
        difference = positions[first:first + block_rows, None, :] - positions[None, :, :]
        distance = np.maximum(np.linalg.norm(difference, axis=-1), 0.01)
        forces = np.einsum("ijk,ij->ik", difference, (1 / count) / distance**2)
        if not np.isfinite(forces).all():
            raise ValueError("repulsion sample produced nonfinite forces")
        elapsed.append(perf_counter() - start)
        cpu_elapsed.append(process_time() - cpu_start)
    pair_seconds = median(elapsed) / (block_rows * count)
    cpu_pair_seconds = median(cpu_elapsed) / (block_rows * count)
    return {
        "puzzle": name, "signature": c.block_signature(bandage, include_singletons=True),
        "shape_count": count, "positive_actions": len(actions),
        "geometry_edges": geometry.number_of_edges(),
        "visible_node_diagrams": sum(degrees[v] != 2 or v == 0 for v in range(count)),
        "exploration_seconds": exploration_seconds,
        "networkx_geometry_seconds": geometry_seconds,
        "symmetry_detection": symmetry_measurement,
        "symmetry_with_linear_cycle_scan": fast_measurement,
        "planar_symmetry_order": fast_symmetry[0] if fast_symmetry else None,
        "symmetry_equivalence_checked": symmetry is not None,
        "default_iterations": 300,
        "ordered_repulsion_pairs_per_iteration": count**2,
        "ordered_repulsion_pairs_300_iterations": count**2 * 300,
        "sample_block_rows": block_rows,
        "sample_block_wall_seconds": elapsed,
        "sample_block_cpu_seconds": cpu_elapsed,
        "estimated_repulsion_seconds_per_iteration": pair_seconds * count**2,
        "estimated_repulsion_seconds_300_iterations": pair_seconds * count**2 * 300,
        "estimated_repulsion_cpu_seconds_per_iteration": cpu_pair_seconds * count**2,
        "estimated_repulsion_cpu_seconds_300_iterations": cpu_pair_seconds * count**2 * 300,
        "estimate_scope": "sampled exact repulsion kernel only; excludes attraction, symmetry projection and rendering; early convergence may reduce iterations",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzle", action="append", choices=("BeltRoad", "MostSignaturesCube", "FourPair"))
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--symmetry-seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.symmetry_seconds <= 0:
        parser.error("sample count and symmetry bound must be positive")
    records = []
    for name in args.puzzle or ("BeltRoad", "MostSignaturesCube", "FourPair"):
        record = measure(name, args.samples, args.symmetry_seconds)
        records.append(record)
        print(json.dumps(record), flush=True)
    args.output.write_text(json.dumps({
        "format": "bce-v2-notebook-graph-performance", "version": 1,
        "python": platform.python_version(), "platform": platform.platform(),
        "timing_conditions": "concurrent bounded research jobs; timings are diagnostic, not calibrated uncontended benchmarks",
        "measurements": records,
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
