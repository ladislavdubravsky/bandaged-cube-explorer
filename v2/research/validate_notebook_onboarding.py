#!/usr/bin/env python3
"""Smoke-test an installed consumer environment using fresh Jupyter kernels.

Pass --python for a freshly source-built environment. The tests execute no
notebook magics, renderer refreshes or per-call GAP configuration. They check
the example sources separately from expensive full solving explorations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from queue import Empty
import shutil
import sys
import tempfile
from time import monotonic

from jupyter_client import KernelManager


V2 = Path(__file__).resolve().parents[1]


def notebook_sources():
    rows = []
    for path in sorted((V2 / "examples").rglob("*.ipynb")):
        document = json.loads(path.read_text())
        for cell in document["cells"]:
            source = "".join(cell["source"])
            assert not any(term in source for term in ("%matplotlib", "GAP_EXECUTABLE", "refresh_renderers")), path
            if cell["cell_type"] == "code":
                compile(source, str(path), "exec")
        rows.append({"notebook": str(path.relative_to(V2)), "plain_python_cells": True,
                     "no_manual_environment_setup": True,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows


def kernel_check(interpreter, directory, *, gap_override=None, missing_gap=False):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("MPLBACKEND", None)
    env.pop("BCE_GAP_EXECUTABLE", None)
    env.update(IPYTHONDIR=str(directory / "ipython"),
               MPLCONFIGDIR=str(directory / "matplotlib"),
               JUPYTER_RUNTIME_DIR=str(directory / "runtime"))
    if gap_override is not None:
        env["BCE_GAP_EXECUTABLE"] = str(gap_override)
    manager = KernelManager(kernel_name="python3")
    if interpreter.absolute() != Path(sys.executable).absolute():
        manager.kernel_spec.argv = [str(interpreter), "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    client = None
    try:
        manager.start_kernel(cwd=str(directory), env=env)
        client = manager.client()
        client.start_channels()
        client.wait_for_ready(timeout=45)
        source = """import json, sys
import bce_v2 as c
import matplotlib.pyplot as plt
from IPython.display import Markdown, display

reference = c.Shape([1] * 9 + [2] * 18)
graph = c.explore(reference)
assert graph.complete and len(graph) == 1
word = c.scramble(reference, seed=7)
assert not c.State(reference).apply(word).is_solved
figure = c.draw_cubes(reference)
plt.show()
"""
        if missing_gap:
            source += """from bce_v2.gap_backend import GapUnavailableError
try:
    c.analyze_isotropy(reference)
except GapUnavailableError as error:
    assert 'Install GAP' in str(error) and 'BCE_GAP_EXECUTABLE' in str(error)
else:
    raise AssertionError('missing GAP must fail analysis clearly')
"""
        else:
            source += """analysis = c.analyze_isotropy(reference)
assert analysis.group_order == 4
method = c.discover_method(reference, cache_dir=None)
assert method.status == 'completed'
display(Markdown(method.write_guide()))
"""
        source += "print('__BCE_ONBOARDING__' + json.dumps({'python': sys.executable, 'package': c.__file__, 'backend': plt.get_backend()}))\n"
        identifier = client.execute(source)
        deadline = monotonic() + 60
        messages = []
        while monotonic() < deadline:
            try:
                message = client.get_iopub_msg(timeout=1)
            except Empty:
                continue
            if message.get("parent_header", {}).get("msg_id") != identifier:
                continue
            messages.append(message)
            if message["msg_type"] == "status" and message["content"]["execution_state"] == "idle":
                break
        else:
            raise TimeoutError("onboarding kernel did not finish its smoke check")
        errors = [message["content"] for message in messages if message["msg_type"] == "error"]
        assert not errors, errors
        while True:
            reply = client.get_shell_msg(timeout=10)
            if reply.get("parent_header", {}).get("msg_id") == identifier:
                break
        assert reply["content"]["status"] == "ok", reply["content"]
        streams = "".join(message["content"]["text"] for message in messages if message["msg_type"] == "stream")
        output = next(line[len("__BCE_ONBOARDING__"):] for line in streams.splitlines()
                      if line.startswith("__BCE_ONBOARDING__"))
        result = json.loads(output)
        assert Path(result["python"]).absolute() == interpreter.absolute()
        assert "matplotlib_inline" in result["backend"]
        data = [message["content"].get("data", {}) for message in messages
                if message["msg_type"] in ("display_data", "execute_result")]
        assert any("image/png" in item for item in data)
        if missing_gap:
            assert "GAP executable" in streams and "was not found" in streams
        else:
            assert any("text/markdown" in item for item in data)
            assert "RuntimeWarning" not in streams
        result.update(inline_figure_without_magic=True, legal_scramble=True,
                      missing_gap_warning_and_analysis_error_checked=missing_gap,
                      default_gap_analysis_and_guide_checked=not missing_gap,
                      default_kernel_selection_checked=interpreter.absolute() == Path(sys.executable).absolute(),
                      no_manual_notebook_setup=True)
        return result
    finally:
        if client is not None:
            client.stop_channels()
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path, default=V2 / "research-results" / "notebook-onboarding.json")
    args = parser.parse_args()
    notebooks = notebook_sources()
    with tempfile.TemporaryDirectory(prefix="bce-onboarding-") as temporary:
        directory = Path(temporary)
        ready = kernel_check(args.python, directory)
        missing = kernel_check(args.python, directory, gap_override=directory / "missing-gap", missing_gap=True)
        # A launcher with spaces exercises the shared environment setting and
        # subprocess argument handling, without a GAP variable in the notebook.
        gap = shutil.which("gap")
        assert gap is not None
        launcher = directory / "custom gap launcher"
        launcher.write_text("#!" + str(args.python) + "\nimport os, sys\nos.execv(" + repr(gap) + ", [" + repr(gap) + ", *sys.argv[1:]])\n")
        launcher.chmod(0o755)
        custom = kernel_check(args.python, directory, gap_override=launcher)
    report = {"all_checks_passed": True, "notebooks": notebooks,
              "fresh_notebook_kernel": ready, "missing_gap_notebook_kernel": missing,
              "custom_gap_launcher_notebook_kernel": custom}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"all_checks_passed": True, "plain_python_notebooks": len(notebooks),
                      "fresh_kernels_checked": 3, "interpreter": str(args.python)}, indent=2))


if __name__ == "__main__":
    main()
