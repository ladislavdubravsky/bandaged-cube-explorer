#!/usr/bin/env python3
"""Execute shape-navigation notebooks and check complete metric searches.

Notebook outputs remain short. Independent BFS, exhaustive action replay and
metric checks live here instead of in the user-facing input workflow.
"""

from __future__ import annotations

import ast
from collections import deque
import hashlib
import json
from pathlib import Path
import re

import bce_v2 as c
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output


V2 = Path(__file__).resolve().parents[1]
EXAMPLES = V2 / "examples"
NOTEBOOKS = EXAMPLES / "shapes-graph-navigation"
REPORT = V2 / "research-results" / "shape-navigation-notebooks.json"


def inverse(move):
    return move if move.endswith("2") else (
        move[:-1] if move.endswith("'") else move + "'")


def execute_notebook(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    shell = InteractiveShell.instance()
    shell.user_ns.clear()
    execution_count = 0
    for cell in document["cells"]:
        if cell["cell_type"] != "code":
            continue
        execution_count += 1
        with capture_output() as captured:
            result = shell.run_cell("".join(cell["source"]), store_history=False)
        if result.error_before_exec or result.error_in_exec:
            raise RuntimeError(f"notebook execution failed: {path}") from (
                result.error_before_exec or result.error_in_exec)
        cell["outputs"] = [
            {"output_type": "display_data", "data": output.data,
             "metadata": output.metadata} for output in captured.outputs]
        for name in ("stdout", "stderr"):
            value = getattr(captured, name)
            if value:
                cell["outputs"].append({"output_type": "stream", "name": name,
                                        "text": value})
        cell["execution_count"] = execution_count
    return document, shell.user_ns


def bandage_input(document):
    for cell in document["cells"]:
        if cell["cell_type"] == "code":
            for node in ast.parse("".join(cell["source"])).body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "bandage"
                        for target in node.targets):
                    return ast.literal_eval(node.value)
    raise AssertionError("notebook has no bandage input")


def certify_graph(graph, reference, scrambled):
    assert graph.complete and graph[0] == reference
    shapes = graph.shapes
    arcs = set(graph.arcs)
    assert len(arcs) == len(graph.arcs)
    # Native QTM stores positive quarter turns; their inverse traversals are
    # implicit. HTM explicitly stores all three allowed turns on each face.
    if graph.metric == "QTM":
        assert all(len(move) == 1 for _, _, move in arcs)
        arcs |= {(target, source, inverse(move))
                 for source, target, move in tuple(arcs)}
    outgoing = [[] for _ in shapes]
    actions = [set() for _ in shapes]
    for source, target, move in arcs:
        assert shapes[source].apply(move) == shapes[target]
        assert (target, source, inverse(move)) in arcs
        outgoing[source].append(target)
        actions[source].add(move)
    for source, shape in enumerate(shapes):
        legal = set(shape.legal_moves)
        if graph.metric == "QTM":
            legal = {move for move in legal if not move.endswith("2")}
        assert actions[source] == legal

    # Separate Python BFS certifies every distance from the reference shape.
    distances = [None] * len(shapes)
    distances[0] = 0
    queue = deque((0,))
    while queue:
        source = queue.popleft()
        for target in outgoing[source]:
            if distances[target] is None:
                distances[target] = distances[source] + 1
                queue.append(target)
    assert all(distance is not None for distance in distances)
    assert distances == graph.distances(reference)

    selected = graph.vertex_id(scrambled)
    endpoints = sorted({0, selected, len(shapes) // 2,
                        distances.index(max(distances))})
    for vertex in endpoints:
        path = graph.shortest_path(vertex, reference)
        assert path is not None and shapes[vertex].apply(path) == reference
        cost = sum(2 if graph.metric == "QTM" and move.endswith("2") else 1
                   for move in path.split())
        assert cost == distances[vertex]
    return {
        "metric": graph.metric, "complete": True, "shape_count": len(shapes),
        "stored_arc_count": len(graph.arcs), "checked_action_count": len(arcs),
        "maximum_distance_from_reference": max(distances),
        "example_shortest_cost": distances[selected],
        "all_legal_actions_retained": True, "all_actions_replayed": True,
        "all_actions_have_legal_inverses": True,
        "independent_bfs_matches_all_distances": True,
        "replayed_shortest_return_endpoints": len(endpoints),
    }


def certify_optional_drawing(namespace):
    import matplotlib.pyplot as plt

    graph, scrambled = namespace["shape_graph"], namespace["scrambled_shape"]
    figure = graph.draw(
        view="local", start=scrambled, radius=2, max_vertices=24,
        layout="spring", show_shapes=True, edge_labels=True, figsize=(10, 10),
    )
    assert figure.axes
    plt.close(figure)


def execute_metric_edit(document, namespace):
    """Exercise the user-facing HTM-to-QTM edit and its displayed cost."""
    modified = dict(namespace)
    for cell in document["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        if "shape_graph = c.explore(" in source:
            source = source.replace('metric="HTM"', 'metric="QTM"')
        elif "return_path = shape_graph.shortest_path(" not in source:
            continue
        with capture_output():
            exec(compile(source, "<shape-navigation metric edit>", "exec"), modified)
    assert modified["shape_graph"].metric == "QTM"
    assert modified["units"] == "quarter turns"
    assert modified["scrambled_shape"].apply(modified["return_path"]) == modified["reference_shape"]
    assert modified["return_cost"] == sum(
        2 if move.endswith("2") else 1 for move in modified["return_path"].split())
    return modified


def main():
    expected = {path.name for path in (EXAMPLES / "stabilizer-chain-methods").glob("*.ipynb")}
    paths = sorted(NOTEBOOKS.glob("*.ipynb"))
    assert {path.name for path in paths} == expected
    rows = []
    for path in paths:
        document, namespace = execute_notebook(path)
        original = json.loads((EXAMPLES / "stabilizer-chain-methods" / path.name).read_text())
        assert bandage_input(document) == bandage_input(original)
        reference, scrambled = namespace["reference_shape"], namespace["scrambled_shape"]
        return_path = namespace["return_path"]
        assert scrambled.apply(return_path) == reference
        assert namespace["return_cost"] == len(return_path.split())
        assert namespace["units"] == "moves"
        assert not namespace["draw_graph"]
        # The commented move alternative must construct exactly the same input
        # partition; for the ordinary cube, any legal scramble has that shape.
        input_code = next("".join(cell["source"]) for cell in document["cells"]
                          if cell["cell_type"] == "code" and
                          "# scrambled_shape = reference_shape.apply(" in "".join(cell["source"]))
        known_scramble = re.search(r"# scrambled_shape = reference_shape\.apply\((.+)\)", input_code)
        assert reference.apply(ast.literal_eval(known_scramble.group(1))) == scrambled
        metrics = [certify_graph(namespace["shape_graph"], reference, scrambled)]
        qtm_namespace = execute_metric_edit(document, namespace)
        qtm = qtm_namespace["shape_graph"]
        metrics.append(certify_graph(qtm, reference, scrambled))
        assert set(namespace["shape_graph"].shapes) == set(qtm.shapes)
        assert metrics[0]["example_shortest_cost"] <= metrics[1]["example_shortest_cost"]
        certify_optional_drawing(namespace)
        if path.stem == "Unbandaged3x3":
            assert return_path == "" and len(namespace["shape_graph"]) == 1
            assert not c.State(reference).apply("R U").is_solved
        path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        row = {
            "notebook": str(path.relative_to(V2)), "all_checks_passed": True,
            "direct_history_free_shape_input": True,
            "original_bandage_input_preserved": True,
            "legal_scramble_alternative_matches_input": True,
            "optional_bounded_local_drawing_checked": True,
            "qtm_metric_edit_and_display_cost_checked": True,
            "same_shapes_in_both_metrics": True, "metrics": metrics,
            "notebook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        rows.append(row)
        print(f"{path.stem}: {metrics[0]['shape_count']:,} shapes; "
              f"example HTM {metrics[0]['example_shortest_cost']}, "
              f"QTM {metrics[1]['example_shortest_cost']}", flush=True)
    report = {
        "all_checks_passed": True,
        "scope": "complete fixed-frame bandage shape components; colors ignored",
        "notebook_count": len(rows), "notebooks": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
