"""Notebook defaults and shared discovery of the optional GAP executable."""

from importlib.util import find_spec
import os
import shutil
import sys
import warnings


def _configured_gap_executable(executable="gap"):
    """An explicit launcher wins; the default can be configured once outside Python."""
    return os.environ.get("BCE_GAP_EXECUTABLE", "gap") if executable == "gap" else executable


def _gap_installation_help():
    return ("Install GAP from https://www.gap-system.org/install/ and put its gap "
            "launcher on PATH. For a custom installation, set BCE_GAP_EXECUTABLE "
            "to the launcher path before starting Jupyter, or pass gap_executable "
            "to the analysis call.")


def _notebook_shell():
    # IPython is optional outside notebooks. Do not import it or plotting
    # libraries into ordinary scripts just to detect the runtime.
    ipython = sys.modules.get("IPython")
    getter = getattr(ipython, "get_ipython", None)
    shell = getter() if callable(getter) else None
    return shell if getattr(shell, "kernel", None) is not None else None


def _initialize_notebook():
    """Set up a fresh notebook on import, quietly when prerequisites are present.

    Check executable availability without launching GAP. Actual analysis still
    checks its subprocess protocol. Optional dependencies stay optional for
    scripts, and explicit plotting-backend choices are preserved.
    """
    shell = _notebook_shell()
    if shell is None:
        return
    required = ("matplotlib", "matplotlib_inline", "networkx", "scipy")
    missing = [name for name in required if find_spec(name) is None]
    if missing:
        warnings.warn(
            "Notebook dependencies are missing: " + ", ".join(missing) + ". "
            f"From the repository root, run \"{sys.executable}\" -m pip install "
            "'./v2/python[notebooks]' and restart this kernel.",
            RuntimeWarning, stacklevel=2,
        )
    executable = _configured_gap_executable()
    if shutil.which(executable) is None:
        warnings.warn(
            f"GAP executable {executable!r} was not found. " + _gap_installation_help() +
            " Restart Jupyter or VS Code after changing PATH. GAP is needed for group "
            "analysis and method discovery; shape navigation and scrambling remain available.",
            RuntimeWarning, stacklevel=2,
        )
    if (not {"matplotlib", "matplotlib_inline"}.intersection(missing)
            and "matplotlib.pyplot" not in sys.modules
            and not os.environ.get("MPLBACKEND")
            and getattr(shell, "pylab_gui_select", None) is None):
        shell.enable_matplotlib("inline")
