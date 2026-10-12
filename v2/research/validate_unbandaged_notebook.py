#!/usr/bin/env python3
"""Execute every ordinary-cube notebook cell in an independent v2 kernel.

Run with v2/.venv/bin/python. Only jupyter_client/ipykernel are required;
the notebook extra already installs both. Outputs are collected from the real
kernel and saved as ordinary notebook JSON, including Markdown and figures.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
import os
from pathlib import Path
from queue import Empty
import tempfile
from time import monotonic, perf_counter

from jupyter_client import KernelManager


V2 = Path(__file__).resolve().parents[1]
NOTEBOOK = V2 / "examples" / "action-family-methods" / "Unbandaged3x3.ipynb"


def unbandaged_audit_source(interpreter):
    """Check physical entry and suffix execution independently of guide output."""
    return f'''import json as _audit_json, sys as _audit_sys
from bce_v2.human_chains import _observation as _audit_observation, _resolve_feature as _audit_resolve
from bce_v2._moves import _simplified_moves as _audit_simplify
assert _audit_sys.executable == {str(interpreter)!r}
assert len(applications) == len(sample_scrambles) > 0
assert suffix.group_order == 62208
assert method.human_method_complete is False
assert method.coverage_scope == "bounded_constructive_entry_then_certified_domain_suffix"
_audit_checks = 0
_audit_rows = []
def _audit_satisfied(state, feature):
    handle = _audit_resolve(suffix.inventory, feature)
    action = suffix.inventory.action(tuple(state.sticker_permutation))
    return (_audit_observation(action, handle, feature.kind) ==
            _audit_observation(suffix.inventory.identity(), handle, feature.kind))
for _audit_word, _audit_application in zip(sample_scrambles, applications):
    _audit_fixture = c.State(method.reference_shape).apply(_audit_word)
    _audit_initial = c.State.from_cubies(_audit_fixture.specification,
        corners=_audit_fixture.corners, twists=_audit_fixture.twists,
        edges=_audit_fixture.edges, flips=_audit_fixture.flips)
    assert _audit_initial.scramble is None
    _audit_current = _audit_initial
    for _audit_step in _audit_application.entry_steps:
        assert _audit_step.before.scramble is None
        assert _audit_step.before == _audit_current
        _audit_current = _audit_current.apply(_audit_step.turn_sequence)
        assert _audit_current == _audit_step.after
        for _audit_feature in (*_audit_step.protected_features, _audit_step.feature):
            assert _audit_satisfied(_audit_current, _audit_feature)
            _audit_checks += 1
    _audit_suffix = _audit_application.suffix_application
    if _audit_suffix is not None:
        for _audit_feature in suffix.domain_features:
            assert _audit_satisfied(_audit_current, _audit_feature)
            _audit_checks += 1
        _audit_done = list(suffix.domain_features)
        for _audit_step in _audit_suffix.steps:
            assert _audit_current == _audit_step.before
            _audit_current = _audit_current.apply(_audit_step.turn_sequence)
            assert _audit_current == _audit_step.after
            _audit_done.extend(stage.feature for stage in suffix.stages
                               if stage.number <= _audit_step.stage_number
                               and stage.feature not in _audit_done)
            for _audit_feature in _audit_done:
                assert _audit_satisfied(_audit_current, _audit_feature)
                _audit_checks += 1
    assert _audit_current == _audit_application.state
    assert _audit_initial.apply(_audit_application.turn_sequence) == _audit_application.state
    if _audit_application.status == "solved":
        assert _audit_application.state.is_solved
    _audit_rows.append({{"status": _audit_application.status,
        "entry_stage_htm": sum(step.htm_length for step in _audit_application.entry_steps),
        "entry_physical_htm": len(_audit_simplify(" ".join(step.turn_sequence
            for step in _audit_application.entry_steps).split()).split()),
        "suffix_physical_htm": (len(_audit_suffix.turn_sequence.split())
                                if _audit_suffix is not None else None),
        "physical_htm": _audit_application.htm_length,
        "entry_stage_count": len(_audit_application.entry_steps)}})
_audit_solved = [row for row in _audit_rows if row["status"] == "solved"]
_audit_report = {{"kernel_interpreter_verified": True,
    "package_file": c.__file__, "native_endpoint_checks": _audit_checks,
    "cache_metadata": cached.metadata,
    "suffix_domain_order": str(suffix.group_order),
    "suffix_case_counts": [stage.case_count for stage in suffix.stages],
    "suffix_additive_costs": suffix.additive_costs(),
    "whole_solution_metric_scope": "sampled_native_solutions",
    "complete_entry_coverage_claim": False,
    "sample_count": len(_audit_rows), "solved_count": len(_audit_solved),
    "mean_physical_htm_over_solved": (sum(row["physical_htm"] for row in _audit_solved)
        / len(_audit_solved) if _audit_solved else None),
    "mean_entry_stage_htm_over_solved": (sum(row["entry_stage_htm"] for row in _audit_solved)
        / len(_audit_solved) if _audit_solved else None),
    "mean_entry_physical_htm_over_solved": (sum(row["entry_physical_htm"] for row in _audit_solved)
        / len(_audit_solved) if _audit_solved else None),
    "mean_suffix_physical_htm_over_solved": (sum(row["suffix_physical_htm"] for row in _audit_solved)
        / len(_audit_solved) if _audit_solved else None),
    "fixtures": _audit_rows}}
print("BCE_NOTEBOOK_AUDIT=" + _audit_json.dumps(_audit_report, sort_keys=True))
'''


def check_sources(notebook):
    """Reject the old planner and a prebuilt temporary-file dependency."""
    calls = []
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else node.func.id if isinstance(node.func, ast.Name) else None)
                if name:
                    calls.append(name)
                if name == "template_human_repertoire":
                    raise AssertionError(f"cell {index} still invokes the legacy planner")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("/tmp/"):
                    raise AssertionError(f"cell {index} depends on an absolute temporary artifact")
    return {"legacy_template_planner_called": False,
            "absolute_temporary_artifact_dependency": False,
            "called_functions": sorted(set(calls))}


def check_rendered_sample_lengths(notebook, report):
    """Bind the displayed segment lengths to the independently replayed cases."""
    heading = "| Input | Fixture scramble | Status | Entry HTM | Continuation HTM |"
    text = next(result["data"]["text/markdown"]
                for cell in notebook["cells"] for result in cell.get("outputs", ())
                if heading in result.get("data", {}).get("text/markdown", ""))
    rows = []
    for line in text.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) >= 8 and fields[1].isdigit():
            rows.append(fields)
    audit = report["native_audit"]
    assert len(rows) == len(audit["fixtures"])
    for number, (row, fixture) in enumerate(zip(rows, audit["fixtures"]), 1):
        assert int(row[1]) == number and row[3] == fixture["status"]
        assert int(row[6]) == fixture["physical_htm"]
        entry = int(row[4])
        suffix = None if row[5] == "—" else int(row[5])
        if "entry_physical_htm" in fixture:
            assert fixture["entry_physical_htm"] == entry
            assert fixture["suffix_physical_htm"] == suffix
        fixture.update(entry_physical_htm=entry, suffix_physical_htm=suffix)
    solved = [fixture for fixture in audit["fixtures"] if fixture["status"] == "solved"]
    audit["mean_entry_physical_htm_over_solved"] = (
        sum(row["entry_physical_htm"] for row in solved) / len(solved) if solved else None)
    audit["mean_suffix_physical_htm_over_solved"] = (
        sum(row["suffix_physical_htm"] for row in solved) / len(solved) if solved else None)
    report["live_sample_summary_matches_native_replay"] = True


def execute_cell(client, cell, timeout):
    """Preserve the Jupyter display protocol while waiting for cell completion."""
    source = "".join(cell["source"])
    cell["outputs"] = []
    cell["execution_count"] = None
    request = client.execute(source, store_history=True, stop_on_error=True)
    deadline = monotonic() + timeout
    displays = {}
    deferred_clear = False
    failure = None
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f"notebook cell exceeded {timeout} seconds")
        try:
            message = client.get_iopub_msg(timeout=min(remaining, 1))
        except Empty:
            continue
        if message.get("parent_header", {}).get("msg_id") != request:
            continue
        kind, content = message["msg_type"], message["content"]
        if kind == "status" and content["execution_state"] == "idle":
            break
        if kind == "execute_input":
            cell["execution_count"] = content["execution_count"]
        elif kind == "clear_output":
            if content.get("wait", False):
                deferred_clear = True
            else:
                cell["outputs"].clear()
                displays.clear()
        elif kind in ("stream", "display_data", "execute_result", "error", "update_display_data"):
            if deferred_clear:
                cell["outputs"].clear()
                displays.clear()
                deferred_clear = False
            if kind == "stream":
                output = {"output_type": "stream", "name": content["name"],
                          "text": content["text"]}
                print(content["text"], end="", flush=True)
            elif kind == "error":
                output = {"output_type": "error", "ename": content["ename"],
                          "evalue": content["evalue"], "traceback": content["traceback"]}
                failure = f"{content['ename']}: {content['evalue']}"
            else:
                display_id = content.get("transient", {}).get("display_id")
                if kind == "update_display_data":
                    for old in displays.get(display_id, ()):
                        old.update(data=content["data"], metadata=content["metadata"])
                    continue
                output = {"output_type": kind, "data": content["data"],
                          "metadata": content["metadata"]}
                if kind == "execute_result":
                    output["execution_count"] = content["execution_count"]
                if display_id:
                    displays.setdefault(display_id, []).append(output)
            cell["outputs"].append(output)
    # Consume execute_reply so the shell queue stays bounded and failures cannot
    # silently pass when a frontend suppresses an IOPub error display.
    while True:
        reply = client.get_shell_msg(timeout=max(1, deadline - monotonic()))
        if reply.get("parent_header", {}).get("msg_id") == request:
            break
    if reply["content"]["status"] != "ok":
        failure = failure or repr(reply["content"])
    if failure:
        raise RuntimeError(failure)


def run_notebook(path, output, report_path, *, timeout=1200, working_directory=None):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    source_checks = check_sources(notebook)
    executed = deepcopy(notebook)
    for cell in executed["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    interpreter = V2 / ".venv" / "bin" / "python"
    working_directory = path.parent if working_directory is None else working_directory
    report = {"format": "bce-v2-unbandaged-notebook-acceptance", "version": 1,
              "fresh_kernel": True, "notebook": str(path.resolve()),
              "interpreter": str(interpreter), "source_checks": source_checks,
              "cells": [], "completed": False}
    started = perf_counter()
    manager = None
    client = None
    try:
        with tempfile.TemporaryDirectory(prefix="bce-notebook-kernel-") as temporary:
            env = os.environ.copy()
            env.update(JUPYTER_CONFIG_DIR=temporary,
                       JUPYTER_RUNTIME_DIR=temporary,
                       IPYTHONDIR=temporary,
                       MPLBACKEND="module://matplotlib_inline.backend_inline")
            manager = KernelManager(kernel_name="python3",
                connection_file=str(Path(temporary) / "kernel.json"))
            manager.kernel_spec.argv = [str(interpreter), "-m", "ipykernel_launcher",
                                        "-f", "{connection_file}"]
            manager.start_kernel(cwd=str(working_directory), env=env)
            client = manager.blocking_client()
            client.start_channels()
            client.wait_for_ready(timeout=60)
            for index, cell in enumerate(executed["cells"]):
                if cell["cell_type"] != "code":
                    continue
                cell_started = perf_counter()
                print(f"Executing cell {index} in a fresh kernel", flush=True)
                execute_cell(client, cell, timeout)
                report["cells"].append({"index": index,
                    "execution_count": cell["execution_count"],
                    "seconds": perf_counter() - cell_started,
                    "output_count": len(cell["outputs"]),
                    "output_mime_types": sorted({mime for result in cell["outputs"]
                        for mime in result.get("data", {})})})
                print(f"Cell {index} passed in {report['cells'][-1]['seconds']:.2f}s", flush=True)
            if (path.name == NOTEBOOK.name and
                    "workspace_sample_summary" in source_checks["called_functions"]):
                audit_cell = {"source": unbandaged_audit_source(interpreter)}
                execute_cell(client, audit_cell, timeout=60)
                prefix = "BCE_NOTEBOOK_AUDIT="
                audit_text = "".join(result.get("text", "")
                                     for result in audit_cell["outputs"])
                audit_line = next(line[len(prefix):] for line in audit_text.splitlines()
                                  if line.startswith(prefix))
                report["native_audit"] = json.loads(audit_line)
                check_rendered_sample_lengths(executed, report)
            report["completed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if client is not None:
            client.stop_channels()
        if manager is not None and manager.has_kernel:
            manager.shutdown_kernel(now=True)
        report["seconds"] = perf_counter() - started
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(executed, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=NOTEBOOK)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=V2 / "research-results"
                        / "unbandaged-notebook-integration.json")
    parser.add_argument("--cell-timeout", type=float, default=1200)
    parser.add_argument("--working-directory", type=Path,
                        help="execution directory (defaults to the notebook directory)")
    args = parser.parse_args()
    if args.cell_timeout <= 0:
        parser.error("cell timeout must be positive")
    report = run_notebook(args.notebook, args.output, args.report,
                          timeout=args.cell_timeout, working_directory=args.working_directory)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
