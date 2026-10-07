# Python research interface

`bce_v2` keeps puzzle definitions and experiments in Python and runs checked
moves, shape and colored exploration, and exact constrained search in Rust. It accepts ordinary
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

## Block signatures and the puzzle atlas

Open [PuzzleSignatures.ipynb](../examples/PuzzleSignatures.ipynb) for the complete
non-isomorphic puzzle atlas grouped by block type. The notebook defaults to all
7,073 behavioral classes; set `COHORT = "filtered"` for the 4,857-class filtered
atlas. Both cohorts merge implicit bonds. Queries run against the retained
SQLite database without enumeration or additional dependencies. The Python
`PuzzleAtlas` constructor defaults to `cohort="filtered"`, as in this example:

```python
from pathlib import Path
import bce_v2 as c

path = Path("v2/enumeration-results/2026-10-07-shell-signatures.sqlite3")
with c.PuzzleAtlas(path) as atlas:
    print(len(atlas.containing("222")))  # 238
    maximum, puzzles = atlas.maximum("211", only=("211",))  # 12, one class
    counts = atlas.signature_counts()  # every signature and its puzzle count
    exact = atlas.select(signature="2x221 Clock 2xPair")
    example = atlas.shape(puzzles[0]["id"])
    print(c.block_signature(example, include_singletons=True))
    print(c.format_signature(c.block_signature(example)))  # 5xClock 7xPair
```

Types distinguish center/core placement: `221Core`, `321Core`, and `331Core`
are separate from their outer variants; a center-containing 311 is `BigClock`.
The optional core-enabled model also admits `211Core` and `311Core`.
`211` combines Clock and Pair in the shell atlas; other names match exact types.
`only` always allows remaining 111 cubies, including free centers. Numeric
dimensions are sorted longest first; output orders types by box volume.
`classify_blocks` also returns exact physical cubie and center/corner/edge/core
counts and rejects noncuboid footprints. These position-aware signatures
determine the remaining singleton count. The [signature guide](../../docs/block-signatures.md)
documents all seventeen types and data provenance. Restart an existing notebook
kernel after updating the package to load the new definitions.

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
in `restored`; `is_solved` checks the full colored cube. Use `solve_colored` below
to solve the colors as well.

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
Centers are fixed and unmarked. States can start solved and advance through
checked legal moves, or be imported with the validation described below.

## Import and solve colored puzzles

```python
scrambled = c.State(c.fixture("Alcatraz")).apply("F R2")
result = c.solve_colored(scrambled, metric="HTM")
assert result.status == "solved"
assert result.optimal and result.distance == 2
assert scrambled.apply(result.solution).is_solved
print(result.solution)  # R2 F'

# Both import forms retain the reference bandage membership, not merely shape.
imported = c.State.from_cubies(
    scrambled.specification, corners=scrambled.corners, twists=scrambled.twists,
    edges=scrambled.edges, flips=scrambled.flips)
scanned = c.State.from_facelets(scrambled.facelets, scrambled.specification)
assert imported == scanned == scrambled
assert imported.scramble is None
```

`State.from_cubies(specification=None, *, corners, twists, edges, flips)` uses
the orders above. `State.from_facelets(facelets, specification=None)` accepts
exactly 54 uppercase face letters, nine per face in `URFDLB` order, each face
read row by row while viewed from outside. Letters name colors relative to the
fixed centers, which must match their face letters. `state.facelets` exports
the same format. A specification may be a `Shape`, 27-cell list, or `State`;
passing a `State` preserves its reference membership. Omitting the specification
means the unbandaged cube.

Looking directly at a face also requires fixing its top edge: keep B at the top
of U, F at the top of D, and U at the top of R/F/L/B. The numbered net in
[ColoredSolving.ipynb](../examples/ColoredSolving.ipynb) shows the complete input
order. Inspect the colored scramble with the existing 3D renderer:

```python
c.draw_cubes(imported, colors=True, views=("UFR", "BLD"))
```

These two orthographic views look directly at opposite corners and together
show all 54 stickers. They are related by a half-turn about the line through
the FL and BR edge centers, with camera roll included. U is above F/R in the
first view; D is above L/B in the second. Center letters identify the faces,
and thick black outlines preserve the current bandage geometry. Thin lines
divide stickers within a fused block.

Colors are optional: omit `colors` for the original uncolored shape drawing.
The default palette is U white, R red, F green, D yellow, L orange, and B blue;
pass a mapping instead of `True` to override colors, for example
`colors={"U": "yellow", "D": "white"}`. `views="BLD"` selects just the back
corner, and `ncol` controls gallery columns. `draw_net(state)` remains available
for an unfolded view. Rendering uses the optional `plots` extra.

Imports check cubie identities, orientation ranges and sums, matching permutation
parity, and rigid-block compatibility. Every fused block must share one proper
rotation mapping its reference positions and sticker directions to the current
configuration. Position checks alone would miss a twisted cubie inside a glued
block. This validation supports connected noncuboid blocks and core bonds;
fixed center stickers are unmarked. It does **not** establish reachability by
legal bandaged turns. Imported states and their subsequent replays have
`scramble is None`, rather than a claimed solved-to-state witness.

`solve_colored` defaults to bidirectional BFS and the solved state of the same
reference specification. Set `algorithm="bfs"` for one-way BFS or pass
`target=another_state` for a different exact colored target. Both inputs must
have the same reference specification. Search keys include identities and
orientations; no symmetry quotient is applied. Only legal face moves are
generated. QTM solutions use quarter/inverse turns; HTM also permits unit-cost
half turns. Both algorithms guarantee shortest successful solutions in the
declared metric. Bidirectional BFS expands complete layers from the smaller
frontier, avoiding the need to enumerate a whole component for a short solution.

`SearchResult` is immutable and has `status`, `solution`, `distance`, `metric`,
`algorithm`, `optimal`, `visited`, `expanded`, and `stop_reason` fields.
`to_dict()` returns a JSON-compatible copy. Outcomes are explicit:

- `solved`: a replayable shortest move string, possibly empty, and its cost.
- `unreachable`: complete component exhaustion proves no solution exists.
- `limit_reached`: an explicit state or depth bound prevented a conclusion;
  `solution` and `distance` are `None`, and `stop_reason` names the bound.

Limits are optional; there is no implicit state or depth cap. These exact
searches target tractable cases and short solutions. For a bounded experiment:

```python
result = c.solve_colored(imported, max_states=100_000, max_depth=12)
if result.status == "solved":
    assert imported.apply(result.solution).is_solved
elif result.status == "limit_reached":
    print(result.stop_reason)
```

`max_states` is positive and counts stored search records, including both roots
and both frontiers for bidirectional search. `max_depth` is nonnegative and
bounds the **total** solution cost, including zero. `optimal` is true only for
`solved`. A cutoff does not imply unreachability. Larger memory-conscious
searches and the shape-loop group solver remain future work.

## Explore colored components

```python
# Only U can turn. The bandage shape stays constant, but colors have four states.
one_face = c.State(c.Shape([0] * 9 + [1] * 18))
colored = c.explore_colored(one_face, metric="QTM")
assert colored.complete and len(colored) == 4
assert len(colored.arcs) == 8
for state in colored:
    path = colored.shortest_path(state, one_face)
    assert state.apply(path) == one_face

partial = c.explore_colored(scrambled, max_states=100)
print(partial.complete, partial.metric, partial.distances())
colored.save("colors.json")
```

`ColoredGraph` exposes `states`, `arcs`, `complete`, `metric`, `vertex_id`,
`distances(start=0)`, and `shortest_path(start=0, target=0)`, along with iteration,
indexing, `to_dict`, `to_json`, `save`, and optional `to_networkx` adapters.
Vertex arguments accept integer IDs or `State` values. States carry their
reference specification and full cubies; exported graph states have no scramble
witness. Paths supply executable transports between graph vertices. A missing
retained path returns `None`.

Use `state.hex_id` for a stable, collision-free colored-state identifier.
It includes the reference bandages and cubie permutations and orientations in
the fixed URFDLB center frame, independent of replay history or graph ordering.
Format v1 is 54 lowercase hex digits: 14 for the reference AxisMajor bonds,
then eight corner bytes (`3 * identity + twist`) and twelve edge bytes
(`2 * identity + flip`), both in Kociemba order. Whole-cube rotations are not
merged. `Shape.rotation_key` instead identifies uncolored shapes up to rotation.

Colored arcs retain **all directed unit-cost moves**: quarter and inverse turns
in QTM, plus half turns in HTM. This differs from the shape graph's clockwise
QTM storage convention. Parallel actions and self-loops are preserved. Complete
exploration has no implicit cap. An explicit positive `max_states` marks the
graph incomplete only when a reachable state is omitted; hitting the exact
component size still reports `complete=True`. Partial-graph paths and distances
describe the retained vertices and cannot establish global optimality or
unreachability. Graph exports are inspection artifacts, not imported proofs.

The colored-solving notebook also builds a table of shortest distances from
solved and displays states at maximum distance. On a complete graph, use
`distances = colored.distances(c.State(specification))` and
`Counter(distances)` from Python's `collections` module for the counts. Select
farthest vertices by their distance and inspect them with `colored[vertex]`.
The notebook shows each example's `hex_id` and a shortest sequence from solved
using `colored.shortest_path(solved, vertex)`. Integer and slice indexing
fetch only selected states, while `colored.states`
materializes the entire Python cache. Complete exploration is required for an
exact distance profile and a global maximum from solved.

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
transparent views. `draw_cubes` also displays colored stickers with `colors=True`
for `State` inputs and supports opposite UFR/BLD views. `draw_net(state)` provides
an unfolded alternative. The
[Alcatraz notebook](../examples/Alcatraz.ipynb) displays example galleries inline.

Version-1 puzzle JSON records include reference labels and the validated move
witness needed to reproduce full colors. Loading checks conventions and replays
the moves through the Rust engine. Imported colored states use version-2 puzzle
records with reference labels and validated cubie arrays; loading repeats both
ordinary-cube and rigid-block checks without asserting reachability. Existing
version-1 records remain supported. Version-1 shape graph exports include normalized
shapes and all stored labeled arcs. Both formats record the model
`full-grid-27-fixed-centers`, standard notation, metric, and symmetry `none`;
graph exports also record `complete`. JSON output is deterministic for the same
input. Graph exports are inspection artifacts; recompute a graph with `explore`
to obtain trusted search results.

`load_puzzle` returns the reconstructed physical `State`. The saved name and
metric remain record metadata; choose the metric explicitly when recomputing a
search. Python exploration and CLI searches default to QTM.

Feature chains and human strategy helpers remain milestone-six work; basic
colored distance profiles and farthest-state inspection are available now.

## Batch commands

The thin CLI calls the same Python API. A puzzle argument accepts a fixture name
or a saved puzzle JSON file:

```sh
bce-v2 fixtures
bce-v2 inspect 'Alcatraz'
bce-v2 replay 'Alcatraz' 'F R2'
bce-v2 solve 'Alcatraz' 'F R2' --metric HTM
bce-v2 solve-colored 'Alcatraz' 'F R2' --metric HTM --max-states 100000
bce-v2 solve-colored imported.json --algorithm bfs --max-depth 8
bce-v2 explore-colored imported.json --max-states 100 --output /tmp/colors.json
bce-v2 explore 'Alcatraz' --output /tmp/alcatraz-graph.json
bce-v2 render 'Alcatraz' --alpha 0.35 --output /tmp/alcatraz.png
```

`python -m bce_v2` provides the same commands. `solve` continues to solve shapes;
`solve-colored` solves full colored states and accepts an optional additional
scramble, algorithm, metric, state/depth bounds, and `--target` fixture or puzzle
record. `explore-colored` accepts an optional `--moves` scramble, metric, state
cap, and export path. Solved or complete results exit with code 0; bounded
incomplete results exit with code 2; proven colored unreachability exits with
code 3. Invalid inputs exit with code 1. Shape solutions report whether the
replay also solved colors.
