#!/usr/bin/env python3
"""Discover and exhaustively validate the pocket method with checked regrips.

Run with v2/.venv/bin/python. The notebook supplies only the bandage; no
algorithms, goals, stage order, or enlarged search budget are supplied here.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import bce_v2 as c
from validate_compact_automatic_methods import (
    audit_all_stage_fibers, audit_coarse_application, audit_shape_restoration,
    metric, native_reference_states, portable_roundtrip, stage_metadata,
)


V2 = Path(__file__).resolve().parents[1]
NOTEBOOK = V2 / "examples/action-family-methods/BandagedPocketCube.ipynb"


def compact_metadata(metadata):
    """Keep search diagnostics; the portable artifact retains full evidence."""
    def search(record):
        return {"status": record["status"], "selected_id": record["selected_id"],
                "candidate_count": len(record.get("candidates", ())),
                "metadata": {key: value for key, value in record["metadata"].items()
                             if key != "profile_evidence"}}
    result = dict(metadata)
    for key in ("coarse_search", "coarse_search_without_regrips"):
        if key in result:
            result[key] = search(result[key])
    if "regrip_search" in result:
        result["regrip_search"] = dict(result["regrip_search"])
        if "coarse_search" in result["regrip_search"]:
            result["regrip_search"]["coarse_search"] = search(
                result["regrip_search"]["coarse_search"])
    return result


def run(*, refresh_notebook=False):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    sources = tuple((cell["cell_type"], cell["source"]) for cell in notebook["cells"])
    bandage = next(ast.literal_eval(node.value)
        for cell in notebook["cells"] if cell["cell_type"] == "code"
        for node in ast.parse("".join(cell["source"])).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "bandage" for target in node.targets))
    started = perf_counter()
    result = c.discover_method(bandage)
    assert result.status == "completed", result.metadata
    automatic, inner = result.method, result.method.inner_method
    assert result.metadata["route"] == "palette_staged_policy", result.metadata
    assert automatic.coverage_complete
    loaded, certificate = portable_roundtrip(inner)
    order = int(result.metadata["reference_group_order"])
    references = native_reference_states(inner.reference_shape, order)
    stage_fibers, checks = audit_all_stage_fibers(loaded, references)
    costs = []
    with patch("subprocess.run", side_effect=AssertionError("execution must be offline")):
        for state in references:
            application = loaded.apply(state)
            assert application.status == "solved" and application.state.is_solved
            checks += audit_coarse_application(loaded, application, state)
            costs.append(len(application.turn_sequence.split()))
        shape_samples, shape_checks = audit_shape_restoration(automatic, references)
        checks += shape_checks
    stages, recognition = stage_metadata(inner)
    guide = automatic.write_guide()
    prefix = V2 / "research-results/pocket-regrips"
    method_path = prefix.with_suffix(".method.json")
    loaded.save(method_path)
    guide_path = prefix.with_suffix(".md")
    guide_path.write_text(guide, encoding="utf-8")
    certificate["artifact"] = str(method_path.relative_to(V2))
    report = {"all_checks_passed": True, "route": result.metadata["route"],
        "reference_group_order": order, "reference_states_checked": len(references),
        "native_endpoint_checks": checks, "shape_restoration_samples": shape_samples,
        "nonidentity_shape_symmetries": list(c.bandage_symmetries(inner.reference_shape)),
        "taught_body_count": len(inner.taught_body_ids),
        "admitted_regrip_count": len(inner.palette.regrips),
        "regrips": [{"body_id": item.body_id, "rotation": item.rotation,
                     "turn_sequence": item.algorithm.turn_sequence} for item in inner.palette.regrips],
        "stages": stages, "recognition": recognition, "stage_fibers": stage_fibers,
        "complete_physical_htm": metric(costs), "portable_certificate": certificate,
        "guide": str(guide_path.relative_to(V2)),
        "discovery_metadata": compact_metadata(result.metadata),
        "wall_seconds": perf_counter() - started}
    if refresh_notebook:
        guide_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"
                       and "method.write_guide(" in "".join(cell["source"])]
        assert len(guide_cells) == 1
        cell = guide_cells[0]
        diagrams = any(isinstance(node, ast.keyword) and node.arg == "recognition_diagrams"
                       and ast.literal_eval(node.value)
                       for node in ast.walk(ast.parse("".join(cell["source"]))))
        displayed = automatic.write_guide(recognition_diagrams=diagrams)
        output = next(output for output in cell["outputs"]
                      if "text/markdown" in output.get("data", {}))
        original = output["data"]["text/markdown"]
        output["data"]["text/markdown"] = (displayed.splitlines(keepends=True)
                                              if isinstance(original, list) else displayed)
        assert sources == tuple((cell["cell_type"], cell["source"]) for cell in notebook["cells"])
        NOTEBOOK.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        report["notebook_refreshed"] = True
        report["notebook_sources_unchanged"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-notebook", action="store_true")
    parser.add_argument("--output", type=Path,
                        default=V2 / "research-results/pocket-regrips.json")
    args = parser.parse_args()
    report = run(refresh_notebook=args.refresh_notebook)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("route", "reference_states_checked",
        "taught_body_count", "admitted_regrip_count", "recognition", "complete_physical_htm")},
        indent=2))


if __name__ == "__main__":
    main()
