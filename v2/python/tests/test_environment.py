"""Notebook imports prepare displays and report actionable missing prerequisites."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

import bce_v2 as c
from bce_v2 import environment
from bce_v2.gap_backend import analyze_generators, _validated_options


class NotebookEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules)
        self.modules.start()
        sys.modules.pop("matplotlib.pyplot", None)
        self.variables = patch.dict(os.environ, {"MPLBACKEND": ""})
        self.variables.start()
        self.shell = SimpleNamespace(kernel=object(), pylab_gui_select=None,
                                     enable_matplotlib=Mock())

    def tearDown(self):
        self.variables.stop()
        self.modules.stop()

    def test_plain_scripts_keep_optional_dependencies_lazy(self):
        with patch.object(environment, "_notebook_shell", return_value=None), \
                patch.object(environment, "find_spec", side_effect=AssertionError("no dependency imports")), \
                patch.object(environment.shutil, "which", side_effect=AssertionError("no notebook checks")):
            environment._initialize_notebook()

    def test_fresh_notebook_enables_inline_without_launching_gap(self):
        with patch.object(environment, "_notebook_shell", return_value=self.shell), \
                patch.object(environment, "find_spec", return_value=object()), \
                patch.object(environment.shutil, "which", return_value="/usr/bin/gap"), \
                patch("subprocess.run", side_effect=AssertionError("no GAP launch during import")), \
                warnings.catch_warnings(record=True) as emitted:
            environment._initialize_notebook()
        self.assertEqual(emitted, [])
        self.shell.enable_matplotlib.assert_called_once_with("inline")

    def test_explicit_backends_and_already_imported_pyplot_are_preserved(self):
        for setting in ("environment", "gui", "pyplot"):
            with self.subTest(setting=setting), patch.dict(os.environ), patch.dict(sys.modules), \
                    patch.object(environment, "_notebook_shell", return_value=self.shell), \
                    patch.object(environment, "find_spec", return_value=object()), \
                    patch.object(environment.shutil, "which", return_value="/usr/bin/gap"):
                os.environ["MPLBACKEND"] = "agg" if setting == "environment" else ""
                self.shell.pylab_gui_select = "qt" if setting == "gui" else None
                if setting == "pyplot":
                    sys.modules["matplotlib.pyplot"] = object()
                environment._initialize_notebook()
                self.shell.enable_matplotlib.assert_not_called()

    def test_missing_prerequisites_warn_with_install_instructions_and_keep_shapes_usable(self):
        with patch.object(environment, "_notebook_shell", return_value=self.shell), \
                patch.object(environment, "find_spec", return_value=None), \
                patch.object(environment.shutil, "which", return_value=None), \
                warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            environment._initialize_notebook()
            self.assertFalse(c.State().apply(c.scramble(seed=7)).is_solved)
        self.assertEqual(len(emitted), 2)
        self.assertIn("./v2/python[notebooks]", str(emitted[0].message))
        self.assertIn(sys.executable, str(emitted[0].message))
        self.assertIn("Install GAP", str(emitted[1].message))
        self.assertIn("PATH", str(emitted[1].message))
        self.shell.enable_matplotlib.assert_not_called()

    def test_detects_kernels_without_importing_ipython_into_scripts(self):
        with patch.dict(sys.modules, {"IPython": SimpleNamespace(get_ipython=lambda: self.shell)}):
            self.assertIs(environment._notebook_shell(), self.shell)
        with patch.dict(sys.modules, {"IPython": SimpleNamespace(get_ipython=lambda: SimpleNamespace())}):
            self.assertIsNone(environment._notebook_shell())
        with patch.dict(sys.modules):
            sys.modules.pop("IPython", None)
            self.assertIsNone(environment._notebook_shell())
            self.assertNotIn("IPython", sys.modules)

    def test_gap_environment_default_is_shared_by_the_actual_backend(self):
        launcher = "/tmp/custom GAP launcher"
        output = "__BCE_GAP_V1_BEGIN__\nversion=4.12.1\norder=1\nindices=\n__BCE_GAP_V1_END__\n"
        with patch.dict(os.environ, {"BCE_GAP_EXECUTABLE": launcher}), \
                patch("bce_v2.gap_backend.subprocess.run", return_value=
                      subprocess.CompletedProcess([], 0, output, "")) as run:
            self.assertEqual(_validated_options("gap", None), (launcher, None))
            self.assertEqual(_validated_options(Path("/explicit/gap"), None), ("/explicit/gap", None))
            self.assertEqual(analyze_generators([]).group_order, 1)
        self.assertEqual(run.call_args.args[0][0], launcher)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_invalid_environment_launcher_uses_existing_option_validation(self):
        with patch.dict(os.environ, {"BCE_GAP_EXECUTABLE": ""}), self.assertRaises(ValueError):
            _validated_options("gap", None)

    def test_unbuilt_source_import_explains_how_to_install_the_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "bce_v2"
            package.mkdir()
            (package / "__init__.py").write_bytes(Path(c.__file__).read_bytes())
            script = "import sys; sys.path.insert(0, " + repr(directory) + "); import bce_v2"
            result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not load its Rust extension", result.stderr)
        self.assertIn("pip install './v2/python[notebooks]'", result.stderr)


if __name__ == "__main__":
    unittest.main()
