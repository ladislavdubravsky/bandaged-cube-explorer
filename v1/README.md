# Original Python implementation

The original shape explorer and scripts live here. New explorations should use
the [v2 notebooks](../v2/examples/README.md).

From the repository root, using a Python environment with NetworkX, NumPy and
Matplotlib installed (the v2 notebook environment includes them):

```sh
v2/.venv/bin/python -m v1.usage
v2/.venv/bin/python -m v1.development
```

Direct execution also works: `v2/.venv/bin/python v1/usage.py` and
`v2/.venv/bin/python v1/development.py`. The development script writes
`graph_good.csv` into the current working directory.

Legacy imports are now `import v1.core as c` and
`from v1.graphics import draw_cubes`. The old puzzle database is preserved in
[v2's bundled fixtures](../v2/engine/data/fixtures.csv). The legacy move
conventions are unchanged; v2 uses standard Singmaster notation.
