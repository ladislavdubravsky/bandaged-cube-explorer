#!/usr/bin/env python3
"""Check generator legality, notebook cells and small-puzzle scramble distance.

Only the appended cells are executed; existing notebook analyses and displays
are left untouched. Optional baseline checks certify that all earlier cells
and metadata survived the append unchanged.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
from statistics import mean

import bce_v2 as c


V2 = Path(__file__).resolve().parents[1]


def inverse(word):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(word.split()))


def replay(reference, word):
    initial = current = c.State(reference)
    for move in word.split():
        assert move in current.legal_moves
        current = current.apply(move)
    assert current != initial and not current.is_solved
    assert current.apply(inverse(word)) == initial
    return current


def notebook_input(document, variable):
    for cell in document["cells"][:-1]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.parse("".join(cell["source"])).body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == variable
                    for target in node.targets):
                value = node.value.args[0] if isinstance(node.value, ast.Call) else node.value
                return c.Shape(ast.literal_eval(value))
    raise AssertionError(f"no {variable} input")


def check_scramble_cell(cell, variable):
    """Keep the final cell a single print, with optional literal API settings."""
    assert cell["cell_type"] == "code"
    statements = ast.parse("".join(cell["source"])).body
    assert len(statements) == 1 and isinstance(statements[0], ast.Expr)
    call = statements[0].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert call.func.id == "print" and len(call.args) == 1 and not call.keywords
    generator = call.args[0]
    assert isinstance(generator, ast.Call) and isinstance(generator.func, ast.Attribute)
    assert isinstance(generator.func.value, ast.Name) and generator.func.value.id == "c"
    assert generator.func.attr == "scramble" and len(generator.args) == 1
    assert isinstance(generator.args[0], ast.Name) and generator.args[0].id == variable
    for keyword in generator.keywords:
        assert keyword.arg in ("length", "seed")
        ast.literal_eval(keyword.value)


def validate_notebooks(baseline):
    rows, puzzles = [], {}
    for path in sorted((V2 / "examples").glob("*/*.ipynb")):
        document = json.loads(path.read_text())
        variable = "reference" if path.parent.name == "shapes-graph-navigation" else "bandage"
        last = document["cells"][-1]
        source = "".join(last["source"])
        check_scramble_cell(last, variable)
        heading = document["cells"][-2]
        assert heading["cell_type"] == "markdown"
        assert "".join(heading["source"]).strip() == "## Generate a scramble"
        reference = notebook_input(document, variable)
        saved = "".join("".join(output["text"]) for output in last["outputs"]
                        if output["output_type"] == "stream" and output["name"] == "stdout").strip()
        replay(reference, saved)
        captured = StringIO()
        with redirect_stdout(captured):
            exec(compile(source, str(path), "exec"), {"c": c, variable: reference})
        replay(reference, captured.getvalue().strip())
        row = {"notebook": str(path.relative_to(V2)), "one_line_scramble_cell": True,
               "scramble_heading": True,
               "saved_scramble_replayed": True, "final_cell_executed_and_replayed": True,
               "notebook_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if baseline is not None:
            prior = baseline[str(path.relative_to(V2.parent))]
            assert len(document["cells"]) == prior["cell_count"] + 2
            del document["cells"][-2:]
            assert hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() == prior["document_sha256"]
            row["all_previous_cells_and_metadata_unchanged"] = True
        rows.append(row)
        puzzles.setdefault(reference, []).append(row["notebook"])
    if baseline is not None:
        for path in (V2 / "examples").glob("*.ipynb"):
            prior = baseline[str(path.relative_to(V2.parent))]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == prior["sha256"]
    return rows, puzzles


def validate_walks(puzzles):
    rows = []
    for reference, notebooks in puzzles.items():
        lengths, endpoints = [], set()
        for seed in range(32):
            word = c.scramble(reference, length=100, seed=seed)
            assert word == c.scramble(reference, length=100, seed=seed)
            after = replay(reference, word)
            lengths.append(len(word.split()))
            endpoints.add(after.hex_id)
        rows.append({"notebooks": notebooks, "samples": 32, "walk_steps": 100,
                     "all_turns_legal": True, "all_endpoints_changed": True,
                     "all_inverse_returns_replayed": True, "all_seeds_repeatable": True,
                     "distinct_sampled_colored_endpoints": len(endpoints),
                     "printed_htm_length": {"mean": mean(lengths), "minimum": min(lengths),
                                            "maximum": max(lengths)}})
    return rows


def bicube_distance_probe():
    initial = c.State(c.fixture("Bicube Fuse"))
    graph = c.explore_colored(initial, metric="HTM")
    assert graph.complete and len(graph) == 7260
    distances = graph.distances()
    samples = []
    for length in (20, 100):
        values = []
        for seed in range(128):
            word = c.scramble(initial, length=length, seed=seed)
            after = replay(initial.specification, word)
            values.append(distances[graph.vertex_id(after)])
        samples.append({"walk_steps": length, "samples": len(values),
                       "exact_htm_distance_from_solved": {
                           "mean": mean(values), "minimum": min(values), "maximum": max(values),
                           "histogram": dict(sorted(Counter(values).items()))}})
    return {"fixture": "Bicube Fuse", "complete_colored_states": len(graph),
            "uniform_component_mean_htm_distance": mean(distances),
            "sampling_claim": "bounded random walks; no uniform-state or optimal-distance guarantee",
            "samples": samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path,
                        default=V2 / "research-results" / "scramble-generator.json")
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    notebooks, puzzles = validate_notebooks(baseline)
    walks = validate_walks(puzzles)
    report = {"all_checks_passed": True, "notebook_count": len(notebooks),
              "distinct_notebook_puzzles": len(puzzles), "notebooks": notebooks,
              "puzzle_walk_checks": walks, "small_puzzle_distance_probe": bicube_distance_probe()}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"all_checks_passed": True, "notebook_count": len(notebooks),
                      "distinct_puzzles": len(puzzles), "seeded_walks_checked": 32 * len(puzzles),
                      "distance_probe": report["small_puzzle_distance_probe"]}, indent=2))


if __name__ == "__main__":
    main()
