# Python research interface

`bce_v2` keeps puzzle definitions and experiments in Python and runs checked
moves, shape exploration, and shortest-path search in Rust. It accepts ordinary
27-cell lists and includes Alcatraz, Bicube Fuse, and Shark Fin Soup as named
fixtures. The computational core has no Python dependency.

## Enumeration

Exact partition counts, cuboid generation, motion classes up to 24 proper cube
rotations, and optional implicit-bond closure are available in the same package.
Invisible core bonds are excluded by default. A cuboid can contain a hole at the
core, so the seven visible cubies of a corner 2×2×2 block remain admissible.

```python
import bce_v2 as c

counts = c.count_partitions()
assert counts["partitions"] == 312_238_908
assert counts["rotation_classes"] == 13_016_719
full_grid = c.count_partitions(core_bonds=True)

shapes = c.cuboid_partitions(limit=100)
scan = c.enumerate_puzzles(max_seeds=100_000, implicit_bonds=True)
assert not scan["complete"]
print(scan["progress"])
representatives = [c.Shape(r["labels"]) for r in scan["representatives"]]

windmill = c.Shape([1, 1, 4, 2, 5, 4, 2, 3, 3] + [0] * 18)
closed = c.close_implicit(windmill)
canonical = closed.canonical()
key = canonical.rotation_key
rotated = canonical.rotated(7)  # indices 0..23; 0 is identity
```

`enumerate_puzzles()` explores the entire family unless explicit limits are
supplied. `max_component_vertices` stops the scan at an incomplete component,
which contributes no class. `close_implicit(..., max_vertices=...)` raises
`ValueError` if that limit prevents complete exploration. `core_bonds=True`
allows all 27 cells; `strict_core_singleton=True` selects literal cuboids avoiding
the core as a comparison model. These two flags cannot both be enabled.

Count and scan reports are JSON-compatible dictionaries. Scan representatives
include `id` (minimum AxisMajor hexadecimal key), `labels`, `seed_labels`, and
`raw_component_vertices`. Record the model, symmetry, and closure settings along
with an ID. Mirror images and immobile puzzles are retained. The existing puzzle
and graph persistence formats keep their fixed-frame meaning.

The [enumeration investigation](../../docs/enumeration.md) explains representative
completeness, the exact counting method, dead ends, and the legacy analytic
function; [measurements](../benchmark-results/enumeration.md) distinguish partial
prefix counts from complete enumeration results.

## Install

From the repository root, with Python 3.10+ and Rust 1.85+ installed:

```sh
python3 -m venv v2/.venv
v2/.venv/bin/python -m pip install './v2/python[all]'
```

Use `./v2/python` without extras for a dependency-free Python interface. The
`plots` extra installs matplotlib; `graph` installs NetworkX; `notebooks` adds
matplotlib and the IPython kernel; `all` includes all three.
These adapters import their dependencies only when used. The package distribution
is named `bandaged-cube-explorer-v2`; its import name is `bce_v2`.

## Play in VS Code

Open the repository root in VS Code and install the recommended Python, Python
Environments, and Jupyter extensions. The workspace settings select `v2/.venv`
and activate it in new terminals, including an existing terminal when the
Python extension starts. Environment creation and package installation above
are a one-time setup; opening the project does not reinstall packages.

Open [Alcatraz.ipynb](../examples/Alcatraz.ipynb) for the main research example.
It has editable cells for the bandage list, scramble, full colored replay,
QTM/HTM shape exploration and solutions, inline galleries, and saved records.
Select the Python environment at `v2/.venv` in the notebook's **Select Kernel**
menu if prompted. VS Code remembers the selected notebook kernel. A separate
Jupyter server is unnecessary.

After adding these settings to an already-open workspace, run **Developer:
Reload Window** and open a new terminal. If VS Code has previously remembered a
different interpreter, choose `v2/.venv` once with **Python: Select Interpreter**.
The notebook kernel picker is separate from terminal environment selection.

For an existing installation made before notebook support was added, install
the kernel without activating a shell:

```sh
v2/.venv/bin/python -m pip install 'ipykernel>=6'
```

## Development

For development, rebuild the extension after changing Rust:

```sh
v2/.venv/bin/python -m pip install maturin
VIRTUAL_ENV="$PWD/v2/.venv" v2/.venv/bin/maturin develop --release --locked --manifest-path v2/python/Cargo.toml
v2/.venv/bin/python -m unittest discover -s v2/python/tests -v
```

Python source edits take effect directly after `maturin develop`. The extension
uses the stable Python ABI from Python 3.10 onward. Building from source needs
Rust; an already-built wheel does not.

## Define, replay, and solve a shape

```python
import bce_v2 as c

alcatraz = [
    6, 6, 0, 6, 6, 0, 0, 0, 0,
    7, 7, 5, 7, 7, 4, 1, 2, 3,
    7, 7, 5, 7, 7, 4, 1, 2, 3,
]
initial = c.Shape(alcatraz)       # or c.fixture("Alcatraz")
scrambled = c.State(initial).apply("F R2")
print(scrambled.legal_moves)

graph = c.explore(initial)        # complete exploration, QTM by default
assert graph.complete
assert len(graph) == 1449
solution = graph.shortest_path(scrambled, initial)
restored = scrambled.apply(solution)
assert restored.shape == initial
print(solution, restored.is_solved)
```

A shape solution restores bandage geometry. Its remaining colors are available
in `restored`; `is_solved` checks the full colored cube. Colored solving belongs
to milestone four.

`Shape` is an immutable sequence of normalized labels. Each zero in an input
list becomes its own singleton; equal positive labels denote one connected
block. Large nonnegative integer labels are accepted and normalized before
conversion to Rust. Disconnected blocks, wrong list lengths, negative labels,
and unknown move tokens are rejected. Connected noncuboid blocks are supported.
The grid includes the virtual core at `c.C`, and cell constants retain the
formula `down * 9 + front * 3 + right`:

```python
print(initial[c.F], initial[c.DF])
print(c.normalize([0] * 27))
shape_only = c.do(alcatraz, "F R2")
assert shape_only == scrambled.shape
```

Moves always use standard Singmaster notation: `U R F D L B`, with optional
`2` or `'`. Slice turns, wide turns, and frame rotations are outside the current
model. There is no legacy direction switch or block-label permutation mode.
All replay methods return new values; a blocked sequence raises
`c.BlockedMoveError`, a `ValueError` subclass, and leaves its input intact.

`State` retains corner identities and twists, edge identities and flips, and
immutable reference bandage membership. Read these through `corners`, `twists`,
`edges`, `flips`, and `specification`. Corners use order
`URF UFL ULB UBR DFR DLF DBL DRB`, edges use
`UR UF UL UB DR DF DL DB FR FL BL BR`, with the standard orientation convention.
Centers are fixed and unmarked. States start solved and advance through checked
legal moves. Arbitrary colored-state input requires the additional validation
planned for milestone four.

## Explore and inspect

```python
graph = c.explore(initial, metric="HTM")
print(graph.metric, graph.complete, len(graph))
print(graph.shapes[0], graph.arcs[:3])
vertex = graph.vertex_id(scrambled)
print(graph.distances(0)[vertex])
print(graph.shortest_path(vertex, 0))
front_turnable = [s for s in graph if s.is_turnable("F")]
```

Distances and paths accept vertex IDs, `Shape`, `State`, or 27-cell lists. IDs
are dense and deterministic for a given starting shape and metric; they are
local to that graph. `graph.shapes` is a cached immutable sequence. Arc records
are `(source_id, target_id, move)` triples, retaining parallel actions and
self-loops. Each move label also specifies its complete colored action, which
can be replayed with `State.apply`.

QTM assigns quarter and inverse turns cost one and half turns cost two. Its
stored arcs are clockwise turns; reverse traversal supplies inverse turns.
HTM assigns every face move cost one and stores all 18 move actions. Shortest
QTM paths contain quarter/inverse turns; HTM paths may include half turns.

Exploration has no implicit resource cap. For a deliberately bounded experiment:

```python
partial = c.explore(initial, max_vertices=100)
assert not partial.complete
```

Distances and paths from partial results describe paths within the retained
vertices. They do not establish global optimality or unreachability. Exported
results record completeness explicitly. Long native operations detach from
Python so other Python threads can run; no Python callback executes per turn.

The optional NetworkX adapter preserves individual actions by default:

```python
actions = graph.to_networkx()                 # MultiDiGraph
geometry = graph.to_networkx(undirected=True) # Graph for shape statistics
```

The directed QTM view expands inverse traversals. The undirected view preserves
shape distances in the declared metric, but its edges are a geometric projection.

## Galleries and reproducible records

```python
figure = c.draw_cubes([initial, scrambled, restored], alpha=0.35)
figure.savefig("gallery.png")

c.save_puzzle(scrambled, "experiment.json", name="Alcatraz experiment")
assert c.load_puzzle("experiment.json") == scrambled
graph.save("shapes.json")
```

The renderer shows bandage shapes and returns a matplotlib figure. It draws
actual cell surfaces, including connected noncuboid blocks, and supports
transparent views. It does not display sticker colors. The
[Alcatraz notebook](../examples/Alcatraz.ipynb) displays example galleries inline.

Version-1 puzzle JSON records include reference labels and the validated move
witness needed to reproduce full colors. Loading checks conventions and replays
the moves through the Rust engine. Version-1 graph exports include normalized
shapes and all stored labeled arcs. Both formats record the model
`full-grid-27-fixed-centers`, standard notation, metric, and symmetry `none`;
graph exports also record `complete`. JSON output is deterministic for the same
input. Graph exports are inspection artifacts; recompute a graph with `explore`
to obtain trusted search results.

`load_puzzle` returns the reconstructed physical `State`. The saved name and
metric remain record metadata; choose the metric explicitly when recomputing a
search. Python exploration and CLI searches default to QTM.

Feature chains, distance-layer experiments, and human strategy helpers are
deferred to milestone six.

## Batch commands

The thin CLI calls the same Python API. A puzzle argument accepts a fixture name
or a saved puzzle JSON file:

```sh
bce-v2 fixtures
bce-v2 inspect 'Alcatraz'
bce-v2 replay 'Alcatraz' 'F R2'
bce-v2 solve 'Alcatraz' 'F R2' --metric HTM
bce-v2 explore 'Alcatraz' --output /tmp/alcatraz-graph.json
bce-v2 render 'Alcatraz' --alpha 0.35 --output /tmp/alcatraz.png
```

`python -m bce_v2` provides the same commands. A bounded `explore` prints
`complete: false`, exports that status, and exits with code 2. Invalid inputs
exit with code 1. Shape solutions report whether the replay also solved colors.
