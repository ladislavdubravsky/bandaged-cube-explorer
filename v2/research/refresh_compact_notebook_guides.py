#!/usr/bin/env python3
"""Refresh only saved guide displays from validated portable methods.

The two notebooks keep their minimal guide source and final scramble cell.
Discovery, experiments and native acceptance stay in research scripts; this
command only replaces stale Markdown outputs after the acceptance report has passed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bce_v2 as c
from bce_v2.automatic_methods import AutomaticMethod
from validate_compact_automatic_methods import check_minimal_notebooks


V2 = Path(__file__).resolve().parents[1]


def refresh(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("all_checks_passed"):
        raise ValueError("refresh requires completed native acceptance checks")
    notebook_checks = {row["notebook"]: row for row in check_minimal_notebooks()}
    fixtures = {row["fixture"]: row for row in report["fixtures"]}
    updates = []
    for name, notebook_name in (("Alcatraz", "Alcatraz"),
                                 ("unbandaged", "Unbandaged3x3")):
        row = fixtures[name]
        certificate = row["portable_certificate"]
        record = json.loads((V2 / certificate["artifact"]).read_text(encoding="utf-8"))
        cls = c.WorkspaceMethod if record["format"] == "bce-v2-workspace-method" else c.CoarseMethod
        inner = cls.from_dict(record)
        if record["fingerprint"] != certificate["fingerprint"]:
            raise ValueError("guide artifact differs from the validated certificate")
        reference_guide = inner.write_guide()
        row["guide"] = {
            "character_count": len(reference_guide),
            "line_count": len(reference_guide.splitlines()),
            "markdown_table_row_count": sum(line.startswith("| ") for line in reference_guide.splitlines()),
            "has_block_action_column": "Block action" in reference_guide,
            "has_algorithm_column": "Algorithm" in reference_guide,
        }
        if name == "Alcatraz":
            (V2 / "research-results" / "compact-alcatraz-guide.md").write_text(
                reference_guide, encoding="utf-8")
        metadata = row["discovery_metadata"]
        graph = c.explore(inner.reference_shape, max_vertices=metadata["shape_count"]+1)
        if not graph.complete or len(graph) != metadata["shape_count"]:
            raise ValueError("retained guide shape scope differs from native shape closure")
        method = AutomaticMethod(inner, graph, json.dumps(metadata, sort_keys=True))
        path = V2 / "examples" / "action-family-methods" / (notebook_name + ".ipynb")
        preferences = notebook_checks[str(path.relative_to(V2))]
        guide = method.write_guide(recognition_diagrams=preferences["recognition_diagrams"],
                                    face_colors=preferences["face_colors"])
        notebook = json.loads(path.read_text(encoding="utf-8"))
        sources = tuple((cell["cell_type"], cell["source"]) for cell in notebook["cells"])
        guide_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"
                       and "method.write_guide(" in "".join(cell["source"])]
        if len(guide_cells) != 1:
            raise ValueError("minimal notebook requires exactly one guide cell")
        outputs = guide_cells[0]["outputs"]
        if len(outputs) != 1 or outputs[0]["output_type"] != "display_data":
            raise ValueError("minimal guide cell requires exactly one Markdown display")
        original = outputs[0]["data"]["text/markdown"]
        before = len("".join(original))
        outputs[0]["data"]["text/markdown"] = (
            guide.splitlines(keepends=True) if isinstance(original, list) else guide)
        assert sources == tuple((cell["cell_type"], cell["source"]) for cell in notebook["cells"])
        path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False)+"\n", encoding="utf-8")
        updates.append({"notebook": str(path.relative_to(V2)), "code_cells_unchanged": True,
                        "all_cell_sources_unchanged": True, "validated_portable_certificate": True,
                        "previous_guide_characters": before, "guide_characters": len(guide)})
    report["notebooks"] = check_minimal_notebooks()
    report["notebook_guide_refresh"] = updates
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return updates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
        default=V2 / "research-results" / "compact-automatic-methods.json")
    args = parser.parse_args()
    print(json.dumps(refresh(args.report), indent=2))


if __name__ == "__main__":
    main()
