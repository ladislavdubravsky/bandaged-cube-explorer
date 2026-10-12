#!/usr/bin/env python3
"""Execute the Bicube Fuse optimal-search notebook and certify its statistics.

Run with v2/.venv/bin/python. Experiments and exhaustive replay stay outside
the notebook, whose saved displays contain only the distance statistics.
"""

from __future__ import annotations

from collections import Counter, deque
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import bce_v2 as c
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output


V2 = Path(__file__).resolve().parents[1]
NOTEBOOK = V2 / "examples" / "optimal-colored-search" / "BicubeFuse.ipynb"
REPORT = V2 / "research-results" / "optimal-colored-bicube-fuse.json"


def execute_notebook():
    document = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    shell = InteractiveShell.instance()
    execution_count = 0
    for cell in document["cells"]:
        if cell["cell_type"] != "code":
            continue
        execution_count += 1
        with capture_output() as captured:
            result = shell.run_cell("".join(cell["source"]), store_history=False)
        if result.error_before_exec or result.error_in_exec:
            raise RuntimeError("notebook execution failed") from (
                result.error_before_exec or result.error_in_exec)
        outputs = [{"output_type": "display_data", "data": output.data,
                    "metadata": output.metadata} for output in captured.outputs]
        for name in ("stdout", "stderr"):
            value = getattr(captured, name)
            if value:
                outputs.append({"output_type": "stream", "name": name, "text": value})
        cell["execution_count"] = execution_count
        cell["outputs"] = outputs
    return document, shell.user_ns


def certify_graph(graph, initial):
    assert graph.complete and len(graph) == 7_260
    assert graph[0] == initial and graph.vertex_id(initial) == 0
    states = graph.states
    identities = {state.hex_id: vertex for vertex, state in enumerate(states)}
    assert len(identities) == len(states)
    shape_counts = Counter(state.shape for state in states)
    assert len(shape_counts) == 121 and set(shape_counts.values()) == {60}

    outgoing = [[] for _ in states]
    arcs = set(graph.arcs)
    assert len(arcs) == len(graph.arcs)
    for source, target, move in arcs:
        assert states[source].apply(move) == states[target]
        assert graph.metric == "HTM" or not move.endswith("2")
        inverse = move if move.endswith("2") else (
            move[:-1] if move.endswith("'") else move + "'")
        assert (target, source, inverse) in arcs
        outgoing[source].append(target)
    for source, state in enumerate(states):
        for move in state.legal_moves:
            if graph.metric == "QTM" and move.endswith("2"):
                continue
            target = identities[state.apply(move).hex_id]
            assert (source, target, move) in arcs

    # A separate Python BFS verifies every native distance using retained arcs.
    independent = [None] * len(states)
    independent[0] = 0
    queue = deque((0,))
    while queue:
        source = queue.popleft()
        for target in outgoing[source]:
            if independent[target] is None:
                independent[target] = independent[source] + 1
                queue.append(target)
    distances = graph.distances()
    assert all(value is not None for value in independent)
    assert independent == distances
    histogram = Counter(distances)
    assert histogram[0] == 1 and sum(histogram.values()) == len(states)

    # Every state has a legal solution attaining its independently checked cost.
    for vertex, state in enumerate(states):
        path = graph.shortest_path(vertex, 0)
        assert path is not None and state.apply(path) == initial
        assert len(path.split()) == distances[vertex]
        assert graph.metric == "HTM" or all(not move.endswith("2") for move in path.split())

    mean = Fraction(sum(distances), len(states))
    return {
        "metric": graph.metric, "complete": True, "colored_states": len(states),
        "shape_count": len(shape_counts), "states_per_shape": 60,
        "arc_count": len(arcs), "maximum_distance_from_solved": max(distances),
        "mean_distance": float(mean), "mean_numerator": mean.numerator,
        "mean_denominator": mean.denominator,
        "distance_histogram": {str(distance): histogram[distance]
                               for distance in range(max(distances) + 1)},
        "all_legal_actions_retained": True, "all_arcs_replayed": True,
        "all_arcs_have_legal_inverses": True, "independent_bfs_matches": True,
        "all_optimal_solution_paths_replayed": True,
    }


def main():
    document, namespace = execute_notebook()
    htm, qtm = namespace["htm_graph"], namespace["qtm_graph"]
    rows = [certify_graph(graph, namespace["initial"]) for graph in (htm, qtm)]
    htm_by_id = {state.hex_id: distance for state, distance in zip(htm.states, htm.distances())}
    qtm_by_id = {state.hex_id: distance for state, distance in zip(qtm.states, qtm.distances())}
    assert htm_by_id.keys() == qtm_by_id.keys()
    assert all(htm_by_id[key] <= qtm_by_id[key] <= 2 * htm_by_id[key]
               for key in htm_by_id)
    NOTEBOOK.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    report = {
        "notebook": str(NOTEBOOK.relative_to(V2)), "fixture": "Bicube Fuse",
        "all_checks_passed": True, "scope": "complete fixed-frame colored component",
        "rotation_quotient": False, "center_spin": False, "metrics": rows,
        "same_states_in_both_metrics": True, "htm_qtm_distance_bounds_checked": True,
        "notebook_sha256": hashlib.sha256(NOTEBOOK.read_bytes()).hexdigest(),
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": True,
                      "notebook": str(NOTEBOOK.relative_to(V2)),
                      "metrics": [{key: row[key] for key in (
                          "metric", "colored_states", "maximum_distance_from_solved",
                          "mean_distance", "arc_count")} for row in rows]}, indent=2))


if __name__ == "__main__":
    main()
