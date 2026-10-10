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
`plots` extra installs matplotlib; `graph` installs NetworkX, matplotlib, and
SciPy for graph drawing and layouts; `notebooks` adds these graph dependencies
and the IPython kernel; `all` includes all extras.
These adapters import their dependencies only when used. The package distribution
is named `bandaged-cube-explorer-v2`; its import name is `bce_v2`.

Group analysis uses an optional external [GAP installation](https://www.gap-system.org/).
Install GAP separately and make its `gap` executable available on `PATH`, or
pass `gap_executable="/path/to/gap"`. No GAP Python binding is needed. Shape-loop
extraction works without GAP or any Python extras.

## Play in VS Code

Open the repository root in VS Code and install the recommended Python, Python
Environments, and Jupyter extensions. The workspace settings select `v2/.venv`
and activate it in new terminals, including an existing terminal when the
Python extension starts. Environment creation and package installation above
are a one-time setup; opening the project does not reinstall packages.

Open [Alcatraz.ipynb](../examples/Alcatraz.ipynb) for the main research example.
It has editable cells for the bandage list, scramble, full colored replay,
facelet input, shape and colored solutions, loop generators, exact group and
colored-state counts, distance profiles, galleries, and saved records.
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
[Alcatraz.ipynb](../examples/Alcatraz.ipynb) shows the complete input
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
exact searches remain future work. Shape-loop analysis and the general GAP
factorization solver are available below.

## Shape loops and exact group counts

Obtain a complete generating set of legal loops at the reference shape without
exploring colored states:

```python
initial = c.fixture("Bicube Fuse")
loops = c.isotropy_loops(initial)
print(loops.shape_count, loops.candidate_count, len(loops.generators))
for loop in loops.generators:
    replayed = c.State(loops.root_shape).apply(loop.moves)
    assert replayed.shape == loops.root_shape
    assert replayed.sticker_permutation == loop.permutation

# This step needs the optional GAP executable.
analysis = loops.analyze(timeout=60)
print(analysis.group_order, analysis.colored_state_count)
assert analysis.colored_state_count == loops.shape_count * analysis.group_order
print([loop.moves for loop in analysis.generators])
```

`c.analyze_isotropy(initial, gap_executable="gap", timeout=None)` combines both
steps. Inputs accept a `Shape`, 27-cell list, or `State`; a `State` supplies its
reference specification, regardless of its current scramble. To reuse an
existing complete QTM or HTM shape graph, call `graph.isotropy_loops(root=0)` or
`c.isotropy_loops(graph, root=0)`. `root` is a graph vertex ID. Partial shape
graphs cannot establish a complete generating set and are rejected.

The Rust extractor chooses a spanning tree, then constructs a root loop for
every remaining edge: travel along the tree to the edge, traverse it, and
return along the tree. Parallel actions and self-loops are retained. For a
connected QTM graph with `n` shapes and `m` stored clockwise arcs, there are
`m - n + 1` candidates; reverse traversal supplies inverse moves. An HTM input
uses its clockwise arcs and builds a QTM tree with the same vertex IDs;
`arc_count` reports those clockwise arcs. Identity actions and duplicates up to
inverse are removed. The surviving permutations
still generate the full isotropy group. Move witnesses are expanded lazily
from the shared tree, rather than storing every long path.

Each `LoopGenerator` exposes `id`, `source`, `target`, `permutation`,
`qtm_length`, `moves`, `turn_sequence`, and `htm_length`. The ID identifies its
original graph arc. `moves` retains the unsimplified witness, and `qtm_length`
counts its quarter turns. `turn_sequence` combines adjacent turns of the same
face, so `R R` or `R' R'` becomes `R2`; `htm_length` counts the displayed face
turns, including half turns as one. A permutation maps 48
movable sticker positions to their destinations, using zero-based URFDLB
facelet order with the fixed unmarked centers omitted. `LoopGenerators` exposes
`root_shape`, `root_vertex`, `shape_count`, `arc_count`, `candidate_count`,
`nonidentity_count`, and immutable `generators`. `loops.transport(vertex)`
returns the shortest QTM tree path from the root to that graph vertex.

GAP computes the exact permutation-group order using stabilizer chains and
reduces the generators by subgroup membership. The reduced set retains actual
extracted loops and their executable witnesses; it is not guaranteed to have
minimum cardinality. `analysis.generators` holds this set, `analysis.loops`
retains the full extraction, and `analysis.gap_version` records the backend.
No group elements or full colored graph are enumerated.

Every fixed-frame shape in the complete component has exactly `group_order`
reachable colored states, so `colored_state_count = shape_count * group_order`
is exact in this model. Full cubie identities and orientations are retained;
center spin is excluded. Do not substitute a rotation-quotiented shape count.
Use the separate loop solver below to test an imported scramble's reachability
and factor its solution into these algorithms.

The default reference roots give the following results with GAP 4.12.1. All
three colored-component counts were independently checked by exhaustive
colored BFS. Generator counts describe the retained witnessed subset and need
not be minimum cardinalities.

| Puzzle | Group order | Colored states | Retained generators |
| --- | ---: | ---: | ---: |
| Alcatraz | 324 | 469,476 | 5 |
| Bicube Fuse | 60 | 7,260 | 2 |
| Shark Fin Soup | 36 | 69,768 | 2 |

Both result types provide deterministic `to_dict(include_moves=True)`,
`to_json()`, and `save(path)` JSON exports; pass `include_moves=False` to omit
expanded move strings. Python group
orders and colored-state counts are exact integers. Their JSON representations
are decimal strings so consumers cannot lose precision through floating-point
conversion. A missing GAP executable, failed backend, or explicit subprocess
timeout raises an error instead of returning a partial count.

## Inspect exact block actions

Each loop describes its effect on physical blocks in the reference partition,
using the same inventory and orientation frames across the whole library:

```python
inventory = loops.block_inventory  # Anchored to loops.root_shape.
for block in inventory.blocks:
    print(block.name, block.type, block.orientation_order)

for generator in analysis.generators:
    action = generator.block_action
    print(f"L{generator.id}", generator.turn_sequence, action.notation)
    assert action.permutation == generator.permutation
```

`analysis.block_inventory` is the same reference inventory. Block identities
are reference member-cell tuples rather than changing normalized partition
labels. Singleton corners, edges, and centers have descriptive names and
retain signature type `111`. Connected noncuboid blocks retain their actual
cells and no cuboid type; independent virtual cores are omitted while actual
core bonds remain intact.

The one-line notation annotates each **source** transition: `(UFL- UFR UBR+)`
moves UFL to UFR with phase minus one, UFR to UBR with phase zero, and UBR to
UFL with phase plus one, measured in each destination's fixed reference frame.
`(UFR-)` is an in-place twist and `()` is identity. Order two uses `+`, order
three `+` and `-`, and order four `+`, `++`, and `-`. Corner `+` follows the
ordinary clockwise convention; edge `+` is a flip. Larger blocks use
deterministic template frames and a documented positive rotation. Unmarked
center and virtual-core spin are excluded.

Exact block destinations and observable rotations retain the complete sticker
action. `inventory.to_dict()` and `action.to_dict()` provide structured
records, and loop and analysis exports include these descriptions alongside
sticker permutations and move witnesses. Read the
[block-action guide](../../docs/block-actions.md) for frame construction,
composition, inversion, powers, and export details. Both analysis notebooks
show the reference inventory and decorate each reduced generator. Restore an
off-root scramble's shape before interpreting it as an action on reference
slots. The opt-in quotient/kernel strategy below uses these actions for
placement followed by orientation correction.

## Solve scrambles with shape loops

The GAP loop solver restores the shape, tests the remaining sticker permutation
for membership in the isotropy group, and factors its inverse into legal root
loops. It uses the complete shape graph and permutation-group methods without
enumerating colored states. Validated facelet or cubie imports need no scramble
history. The target is the solved colored state of the same reference
specification.

```python
# Reuse this solver and its stable algorithm library for the same puzzle.
solver = c.LoopSolver(imported.specification, timeout=60)
result = solver.solve(imported, metric="HTM", timeout=60)
if result.status == "solved":
    assert imported.apply(result.solution).is_solved
    print(result.shape_solution)
    print([(step.generator_id, step.exponent) for step in result.steps])
    print({algorithm.id: algorithm.moves for algorithm in result.algorithms})

# Convenience entry point for one scramble:
result = c.solve_colored_loops(imported, timeout=60, max_expanded_moves=100_000)
```

`LoopSolver(initial, *, gap_executable="gap", timeout=None,
factorization="sticker")` accepts a `Shape`,
27-cell list, `State` specification, complete `ShapeGraph`, `LoopGenerators`, or
`IsotropyAnalysis`. A graph uses vertex zero as its reference; a loop set or
analysis uses its `root_shape`. Supplying an existing analysis avoids repeating
GAP group analysis, but the shape graph is re-explored from that reference.
`solver.solve(state, *, metric="QTM",
timeout=None, max_expanded_moves=None)` checks that the state uses that same
specification. `solve_colored_loops` accepts the same solve options and an
optional `solver=existing_solver`; otherwise it constructs a solver with the
specified GAP executable. Pass `factorization="quotient_kernel"` to this
convenience entry point to select the quotient strategy, or reuse a prepared
solver already configured for it.

A prepared solver reuses its complete shape graph and stable reduced algorithm
library. Each solve requiring a nontrivial loop correction still launches a
fresh GAP factorization subprocess; GAP stabilizer chains are not cached
between solves.

The default `sticker` strategy starts with a deterministic reduced subset of
the original witnessed loops. For each scramble it greedily chooses a smaller
candidate subgroup that still contains the residual permutation before
factorization. This favors
fewer distinct base algorithms; an algorithm and its inverse share an ID. It
does not prove minimum algorithm count or shortest physical move length. The
stable library makes algorithm references reusable across scrambles.

`LoopSolution` is immutable. `shape_solution` restores the geometry first;
ordered `steps` then refer to generator IDs and signed integer powers.
`algorithms` contains only the referenced original loops, including executable
witnesses. Positive exponents repeat a loop; negative exponents repeat its
inverse. `solution` expands the complete executable move string, `distance`
reports its cost in `metric`, and `optimal` is always false. Adjacent turns of
the same face are combined, so `R R` becomes `R2`: that costs two in QTM and
one in HTM. `qtm_length` and `htm_length` report both costs. `algorithm_count`
counts distinct used root loops, and `expression` displays their signed powers
only; shape restoration remains the separate `shape_solution` field.
`group_order` and
`gap_version` record the algebra backend. The result is a computational
scramble solution; a reusable human method also needs recognition and
application rules.

To factor block placement separately from the remaining orientation action,
select the opt-in quotient/kernel strategy:

```python
solver = c.LoopSolver(analysis, factorization="quotient_kernel", timeout=60)
structure = solver.block_structure
assert structure.group_order == structure.quotient_order * structure.kernel_order
for algorithm in structure.basis:
    print(algorithm.id, algorithm.turn_sequence, algorithm.block_action.notation)
    print("Order:", algorithm.order)

result = solver.solve(imported, metric="HTM", max_expanded_moves=100_000)
if result.status == "solved":
    assert imported.apply(result.solution).is_solved
    print(result.placement_expression, result.kernel_expression)
```

`block_structure` is computed lazily and reused. It records the exact isotropy
order `|H|`, footprint-permutation quotient order `|P|`, and footprint-fixing
kernel order `|K|`, with `|H| = |P| * |K|`. `c.analyze_block_structure(reference,
...)` also computes this structure from a puzzle, complete graph, loop set, or
isotropy analysis without preparing a solver.

After shape restoration, this strategy tests and factors the inverse block
permutation and lifts that word through the original `L` loops. It then tests
and corrects the residual in the actual abelian kernel. These membership tests
establish exact reachability, and the lifted full sticker action is verified. The
independent cyclic kernel basis has witnessed `K0`, `K1`, ... algorithms with
`order`, `steps`, `expression`, `turn_sequence`, `permutation`, and
`block_action`. Their `htm_length` counts displayed face turns; `qtm_length`
counts unsimplified original-loop expansion. The kernel includes rotations
within symmetric fused footprints, and retains coupling between physical
orientation coordinates.

Results expose `factorization`, `placement_steps`, `kernel_steps`,
`placement_expression`, `kernel_expression`, `quotient_order`, `kernel_order`,
and the used `kernel_algorithms`. `placement_algorithms` retains the original
witnesses needed to replay the placement stage on its own, even if their
references cancel when flattening the whole correction. The existing `steps`, `expression`, and
`algorithms` still express the whole correction through original witnessed
loops for replay compatibility. The expansion limit preserves both compact
stages. The default `sticker` strategy remains available, and neither strategy
promises a shortest physical solution or minimum algorithm repertoire. See
the [block-action guide](../../docs/block-actions.md#block-placement-and-abelian-kernel-correction)
for the model proof, reference orders, and basis semantics.

Outcomes are explicit:

- `solved`: the expanded move string was replayed and reaches the solved state.
- `unreachable`: the complete shape component or exact subgroup-membership
  test proves the imported state cannot reach solved.
- `limit_reached`: `max_expanded_moves` prevents expansion. The compact steps,
  used algorithms, and `required_expanded_moves` remain available;
  `solution` and `distance` are `None`. This does not imply unreachability.

GAP factorization can produce long words. The optional nonnegative expansion
cap counts the unsimplified QTM witness length: shape restoration plus each
loop's `qtm_length` multiplied by its absolute exponent. It applies before
combining adjacent face turns, independently of the reporting metric. It
allows inspection of the compact expression before materializing the moves.
There is no implicit expansion cap. `stop_reason` names an explicit limit.
`to_dict()`, `to_json()`, and `save(path)` export the structured expression and
algorithm witnesses alongside the expanded solution when available, with the
exact group order represented as a decimal string in JSON.

`timeout` bounds each GAP subprocess, including group analysis during solver
preparation, and excludes shape exploration. Passing `timeout=None` to a
prepared solver's `solve` uses its preparation-time timeout. A GAP timeout or
backend failure raises an error and never proves unreachability.

Both general sticker factorization and block quotient/abelian correction are
available. Bounded algorithm discovery and two solution views are also available
below. Exact quotient tables, further discovery improvements, and dedicated
human-memory optimization remain followups. The direct `solve_colored` API retains its
shortest-path guarantees.

## Discover algorithms and compare solution views

Build a bounded research library of root loops and structured compositions
without changing the baseline solver:

```python
library = c.discover_loop_algorithms(
    analysis, max_seed_loops=12, rounds=2, max_candidates=500,
    max_algorithms=64, max_htm_length=96,
)
for algorithm in library.shortest[:8]:
    print(algorithm.turn_sequence, algorithm.block_action.notation)
for algorithm in library.structured[:12]:
    print(algorithm.structured_turn_sequence, algorithm.block_action.notation)

options = solver.solve_options(
    imported, library=library, metric="HTM", max_states=500, max_depth=3,
)
for option in (options.shortest_found, options.most_structured):
    if option.status == "solved":
        assert imported.apply(option.solution).is_solved
        print(option.shape_solution, option.structured_turn_sequence)
```

The immutable `LoopAlgorithm` records expose IDs, expression trees, simplified
turn sequences, exact block actions, HTM/QTM lengths, affected-block `support`,
kernel membership, and structural scores. Every legal base loop is reusable,
without a turn threshold. Discovery considers powers, commutators, conjugates,
nested constructions, and transfers through actual reference-bandage
symmetries. Power proposals prioritize footprint-permutation order and include
all nontrivial proper divisors of full action order, subject to budgets.
Taking an inverse or assigning an opaque name does not improve description
cost. A linear literal is retained as an alternative when cheaper than its
construction, with its original-loop witness preserved.

`shortest` favors physical length. Lower `structured` score tuples start with
total affected-block count, then the largest constituent application's
affected-block count, followed by shared memory and description cost and
physical length. For equal-effect solutions, the constituent count favors
localized intermediate applications. `support` includes blocks twisted in place. Both physical and
structured representatives can be retained for the same exact action.
`library.to_dict()` exports witnessed records. `library.metadata` exposes
limits, seed/candidate/round counts, pruning and limit flags, `symmetry_count`,
`symmetry_transfer_count`, and `exhaustive=False`.

`algorithm.structured_turn_sequence` renders physical construction notation:
`(R U)3` repeats a group, `[A, B]` is a commutator, and `[S: A]` is conjugation,
with nesting retained. Inverse words are reversed and inverted: `R U` becomes
`U' R'`, and its negative third power becomes `(U' R')3`. Single-face powers
use `R2`/`R'`. `expression.render()` retains original loop IDs;
`expression.render_moves(generators)` substitutes physical turns.
`turn_sequence` remains the expanded face-turn word for replay. Both notebooks
show only Turn sequence, Block action, HTM length, and Affected blocks in their
algorithm tables, with one shortest ranking and one structured ranking.

`LoopExpression.rotated(rotation_word, body)` displays a regrip transfer such
as `x (A) x'`. Only proper rotations preserving the actual reference bandage
shape are admitted; a root with no nonidentity symmetry supplies no transfers.
Bicube Fuse has two nonidentity reference-shape symmetries and Shark Fin Soup
has one. Both notebook roots, Alcatraz and Most Signatures Cube, have zero,
so their tables contain no regrip transfers. Colored markings need not stay
fixed under the setup because the frame is
restored. Regrips are not HTM face turns. `expression.expanded_moves(generators)`
and algorithm witnesses contain legal face turns; `State.apply` keeps its
existing face-only parser. `loop_steps()` rejects rotated trees,
whose transferred word need not use named original loops. Expression exports
retain the rotation word, and remembered definitions reuse the body.
`symmetry_count` counts nonidentity bandage symmetries;
`symmetry_transfer_count` counts evaluated transfers.

Expressions combine legal loops at one reference shape. A commutator
`[A, B]` executes `A B A^-1 B^-1`; conjugating body `A` by legal setup loop `S`
executes `S A S^-1`. The kernel is abelian but need not be central: kernel
algorithms commute with each other, while a placement-loop conjugation can
change a kernel action.

`solve_options` searches the supplied library within state/depth budgets and
also factors through up to 24 discovered macros from each ranking plus the
original reduced generators. These retain the full group, and enriched GAP
factorizations can exceed search depth. Each GAP call respects the prepared
solver's timeout; the existing solve remains a fallback. Each option exposes
status, separate shape restoration, loop expression and `structured_expression`
tree, loop-stage `structured_turn_sequence`, full executable `solution`,
physical lengths, and used algorithms. `algorithm_count` counts distinct
remembered leaves, folding inverses together; `original_loop_count` counts
witness IDs in `base_algorithms`. The ordinary `LoopSolution.algorithm_count`
still counts original loops. These counts do not prove minimum human repertoire.

The full solution includes shape restoration and is legally replay-checked.
Notebook solution tables show the option, shape restoration when needed,
loop-stage Turn sequence, full HTM length, and Remembered algorithms.
`source` remains available in the API for baseline, direct discovered,
bounded-search, and enriched-factorization provenance. The ordinary `solve`
API is unchanged. `options.to_dict()`, `to_json()`, and `save(path)` export both
trees, witnesses, source labels, and search metadata. `options.library_metadata`
copies the discovery limits and counts, even with a default library.

Discovery bounds seeds, rounds, candidates, library size, and witness length.
State limits apply separately to each solve objective; GAP calls use the
per-call timeout. Options retain `searched_states`, `search_complete`,
`stop_reason`, and `candidate_stop_reasons`. Optional enrichment timeouts or
expansion cutoffs preserve the verified baseline; baseline GAP failure still
raises. Both options have `optimal=False`. “Shortest found” compares available
candidates without proving global optimality; structured scoring estimates
localized, reusable descriptions without proving human memorability.
See the [discovery guide](../../docs/block-actions.md#bounded-algorithm-discovery-and-two-solution-views)
for conventions and guarantees. The method compiler below supplies reusable
stage recognition, application and whole-method coverage rules.

## Plan human solving stages from a shape

Prepare a reusable stage skeleton from a reference bandage shape, without
supplying a colored scramble:

```python
import bce_v2 as c

plan = c.plan_human_stages(
    c.fixture("Alcatraz"), strategy="placement_then_orientation",
    max_group_elements=10_368,
)
if plan.status == "completed":
    for stage in plan.stages:
        print(stage.feature.kind, stage.block_name,
              stage.order_before, stage.order_after, stage.index)
    plan.save("alcatraz-stages.json")
```

`plan_human_stages(initial, *, strategy="placement_then_orientation",
features=None, max_group_elements=None, gap_executable="gap", timeout=None,
root=None, backend="explicit")` accepts the reference inputs used by the isotropy/block-structure
interfaces. A `State` supplies its reference specification. Every planned
algorithm will start and finish at the selected root shape; human shape
restoration remains separate work.

The two automatic strategies are `placement_then_orientation` and
`fully_solve_each_block`. They greedily choose the smallest nontrivial stage
index, then stable block inventory order. `strategy="manual"` accepts an
ordered `features` list of `c.BlockFeature(kind, cells)` values, where `kind`
is `place_block` or `solve_block` and `cells` are the exact members of one
reference block. Redundant manual features are recorded in `skipped_features`;
a manual list must finish at the identity subgroup.

With the explicit backend, immutable `HumanStagePlan` and `HumanStage` records retain exact group,
quotient and kernel orders; selected block features; observation cases;
subgroup indices; and automatically implied features. Case counts include the
already-solved observation. `plan.block_structure` also retains the witnessed
independent orientation-kernel basis.

A completed explicit `plan.group` stores `permutations`, original `generators` and
`inventory`. `group.witness(permutation)` reconstructs a `LoopExpression`
through compact enumeration parents, so every group element has an executable
original-loop witness. These witnesses are not yet a stage correction policy
or a short human algorithm repertoire. The plan's metadata therefore records
`coverage_scope: chain_structure_only` and `human_method_complete: false`.

`plan.to_dict()`, `to_json()` and `save(path)` export deterministic stage
records. `include_elements=False` omits the full group-element listing;
`include_moves=True` includes original witness move expansions. There is no
default enumeration cap. The example explicitly uses the largest initially
validated group order, 10,368. An exceeded `max_group_elements` returns
`limit_reached` with no enumerated group or partial stages and
`terminal_order=None`; it does not establish unreachability. The cap excludes
shape exploration and GAP preparation, and `timeout` bounds each GAP call.

Read the [human-method guide](../../docs/human-methods.md#plan-stages-from-a-shape-delivery-one)
for feature observations, endpoint preservation, manual orders, witness use
and the distinction between a stage plan and a complete human puzzle solution.

## Generate and apply a reusable method

Compile every stage case and its legal correction from a reference bandage
shape. No colored scramble is needed to generate the method:

```python
reference = c.fixture("Alcatraz")
method = c.synthesize_human_method(reference, max_group_elements=10_368)
if method.status == "completed":
    method.save("alcatraz-method.json")
    method.write_guide("alcatraz-method.md")
    print(method.coverage, method.quality)
```

`synthesize_human_method(initial, *, strategy="placement_then_orientation",
features=None, max_group_elements=None, gap_executable="gap", timeout=None,
root=None, backend="explicit")` accepts the same references, automatic/manual features and opt-in
limits as `plan_human_stages`. Passing a completed stage plan reuses its
prepared group. The baseline inverts exact coset representatives to obtain
case corrections and shares identical correction effects across the method.

A completed `HumanMethod` retains immutable `HumanMethodStage` and
`HumanMethodCase` records, original `generators` and shared `algorithms`.
Every case is covered; the already-solved case has `algorithm_id=None`.
Each correction preserves earlier features when the whole algorithm finishes.
`coverage="certified"`, `coverage_scope="all_reference_group_states"` and
`human_method_complete=True` describe computational coverage for all reachable
colored states already in the reference shape. `quality="computational_baseline"`
does not claim short, memorable or human-reviewed algorithms.

For any reachable root-shaped colored input, `method.recognize(state)` reads
the first unfinished stage, `next_step(state)` returns its checked correction,
and `apply(state)` runs the complete precompiled policy without a fresh GAP
factorization:

```python
case = next(case for case in method.stages[0].cases
            if case.algorithm_id is not None)
example = method.example_state(1, case.observation)
result = method.apply(example)
assert result.status == "solved" and result.state.is_solved
print(result.turn_sequence)
```

The application result retains each performed stage, observation, expression,
physical moves and before/after state. Wrong references, unrestored shapes,
incomplete methods and unreachable residuals have distinct outcomes. Shape
restoration remains separate work.

`to_dict()`, `to_json()` and `save(path)` write a self-contained version-one
`bce-v2-human-method` artifact. `c.load_human_method(path)` or
`c.HumanMethod.from_dict(record)` reconstructs it and independently checks its
source-loop coverage, physical witnesses and case policy without invoking GAP.
Loading a completed method explores its reference shape component again;
the saved fingerprint and certification labels are not accepted as a proof.
`write_guide(path=None)` returns Markdown and optionally writes it, with
footprint/sticker recognition cues, complete case tables and expanded algorithms.

There is no default group-element cap. An exceeded explicit cap returns
`limit_reached`, `coverage="partial"` and `human_method_complete=False`, with
no case policy. JSON and guide output then report the incomplete preparation.
Read the [method guide](../../docs/human-methods.md#synthesize-a-complete-method-delivery-two)
for exact semantics and the current quality limits.

### Symbolic methods for large groups

Use `backend="symbolic"` in `plan_human_stages` or `synthesize_human_method`
to build exact stabilizers and small feature orbits without enumerating the
colored group. The ordinary cube has about 43 quintillion states, but a fully
solved block chain uses 18 stages and 257 cases including the solved cases.
The placement/orientation chain uses 35 stages and 153 cases. These are
complete computational baselines; generic witnesses can still be long.

```python
cube = c.Shape([0] * 27)
method = c.synthesize_human_method(
    cube, backend="symbolic", strategy="fully_solve_each_block", timeout=90)
method.save("unbandaged3x3-method.json")
method.write_guide("unbandaged3x3-method.md")
scanned = c.State.from_facelets(c.State(cube).apply("B R U2 F'").facelets, cube)
assert method.apply(scanned).state.is_solved
print(method.additive_costs())
```

Symbolic methods use version-two artifacts with portable strong generating
certificates. Loading independently reconstructs small point orbits, checks
Schreier closure, verifies subgroup orders and feature stabilizers, and replays
physical corrections. Loading and application need no GAP. The original six
face loops remain available as witnesses even if the group analysis prunes a
redundant generator. `max_group_elements` applies only to the explicit backend.
Symbolic planning returns a `SymbolicStagePlan` whose `group` has an exact
`order` and offline membership tests, rather than an element array. Its stage
records retain certified before/after subgroups and witnessed representatives.
A prepared native plan can be reused with `backend="symbolic"`.

`improve_human_method` also accepts symbolic methods. It searches feature orbits
using witnessed algorithms in each certified stabilizer and retains complete
fallbacks. `additive_costs()` reports exact uniform-group mean and worst costs
before cancellation between stages, with rational means; it does not claim
exact costs of the simplified full solution. Chain selection also supports the
symbolic backend and a shared physical dictionary, as described below.
`template_human_repertoire` also supports symbolic shared bodies and recipes.
The older `optimize_human_repertoire` search uses the explicit backend. Further
work follows the [saved implementation sequence](../../docs/symbolic-human-methods-plan.md).

The equivalent CLI starts with `python -m bce_v2 plan-method '[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]' --backend symbolic`.
Add `--select-chain` to compare dictionary-aware chains.

## Discover a dictionary and choose a symbolic chain

Discover short algorithms from legal reference loops before choosing the
feature order. The dictionary keeps native moves, corner and edge permutations,
pure orientations and bounded legal setup conjugates. It checks the exact
orientation span in the actual cyclic block coordinates, including order-four
fused blocks; finding a few sparse effects does not establish full span.

```python
analysis = c.analyze_isotropy([0] * 27)
dictionary = c.discover_symbolic_dictionary(analysis)
print(dictionary.metadata["orientation_complete"])
selection = c.select_human_chain(
    analysis, backend="symbolic", dictionary=dictionary,
    preference="execution", max_expansions=64, max_methods=2, timeout=180)
selection.method.save("unbandaged3x3-optimized-method.json")
print(selection.method.additive_costs())
```

`SymbolicAlgorithmDictionary` exposes `algorithms`, `orientation_basis`,
`generators`, `inventory` and detached `metadata`. Its basis spans precisely the
retained pure-orientation effects; `orientation_complete` compares that span
with the exact kernel order obtained from the input and placement groups.
Consuming a dictionary checks those orders against the method's portable
certificates and independently replays its original-loop expressions.
The richer pool stays available for stage choices and coupled parity moves.
Discovery separately bounds mining proposals, retained algorithms, setup depth,
setup words, conjugation proposals, physical length and witness expansion.
`save`/`to_dict` retain the original-loop witnesses;
`SymbolicAlgorithmDictionary.from_dict(record, initial=analysis)` validates and
reconstructs the pool offline without remaking it. Standalone loading verifies
physical words and coordinate span; a consuming method also checks the declared
target against its independently certified group and quotient orders.

`improve_human_method(method, dictionary=dictionary)` reuses the pool offline
for a fixed symbolic chain. `select_human_chain(..., backend="symbolic")`
compares both automatic chains and bounded dictionary-aware feature orders.
Small observation-orbit paths supply corrections. Bounded Schreier words
carry useful algorithms into later exact stabilizers, including coupled odd
permutations that three-cycles alone cannot supply. The report records
dictionary reachability and generating-subset orders separately from complete
method coverage; long certified fallback corrections remain available.

Symbolic candidate costs are exact additive means and worst lengths before
cancellation between stages. The feature-order ranking is heuristic, and
`beam_width` bounds a shortlist for one-step lookahead rather than an exhaustive
chain search. Selected methods retain version-two offline certificates.

## Improve reusable stage algorithms

Search for alternative corrections without changing the stage features or
losing the complete baseline policy:

```python
search = c.improve_human_method(
    method, mode="structured", max_candidates=3_000, max_states=2_000,
)
search.method.save("alcatraz-improved-method.json")
search.method.write_guide("alcatraz-improved-method.md")
search.save("alcatraz-algorithm-search.json")
print(search.metadata["baseline_metrics"], search.metadata["improved_metrics"])
```

`improve_human_method(method, *, mode="structured", max_seed_loops=32,
max_candidates=3000, max_word_length=3, rounds=1, max_states=2000,
max_stage_generators=24, max_alternatives=3, max_htm_length=120,
max_expanded_moves=480, dictionary=None)` requires a completed `HumanMethod`. It regenerates
native reference loops and independently validates the baseline, without GAP.
It returns an immutable `HumanAlgorithmSearch` containing `baseline`, the
selected `method`, per-case `alternatives` and copied `metadata`.

`original` mode considers native loop seeds and their inverses. `shallow` adds
short words and bounded searches over exact actions. `structured` also mines
stage-preserving Schreier words, same-observation differences, powers,
commutators and conjugates. A candidate can correct an entire case without
matching the baseline's full permutation, provided it preserves earlier
features and enters the next subgroup. Full case coverage and legal witnesses
are rechecked before a policy is accepted.

Selection ranks simplified HTM, then QTM and expression description cost.
Whole-group evaluation rejects a proposal if mean or worst-case HTM increases;
the report retains proposed and selected metrics. This is bounded discovery,
not a shortest-face-word guarantee or a minimum-repertoire method. The method
keeps `quality="computational_baseline"` and its original coverage guarantees.

The proposal, settled-state and witness-expansion budgets constrain search;
reference preparation, certification and exhaustive policy metrics run
separately. `max_word_length` limits shallow words and Dijkstra paths in macro
steps, while structured expressions use the expansion bound. All integer
settings accept zero except positive `max_alternatives`; zero proposal budget
retains the baseline policy. Search reports include the settings, work counts,
pruning, proposed stage changes and baseline/proposed/selected metrics.

`search.save(path)` writes a `bce-v2-human-algorithm-search` inspection report;
there is no report loader. `search.method.save(path)` writes an ordinary
version-one method that `load_human_method` independently validates. Read the
[algorithm-improvement contract](../../docs/human-methods.md#improve-stage-algorithms-delivery-three)
for budget and metric definitions.

## Select a chain using its correction algorithms

The default explicit backend compares placement-first, block-first and bounded mixed-feature methods from
the reference shape. New policies receive the same witnessed algorithm pool
and complete case fallbacks; original BFS methods remain selectable controls:

```python
selection = c.select_human_chain(
    reference, preference="execution", beam_width=4,
    max_expansions=64, max_methods=16, max_group_elements=10_368,
    discovery_options={"mode": "structured", "max_candidates": 3_000},
)
selection.method.save("alcatraz-selected-method.json")
selection.method.write_guide("alcatraz-selected-method.md")
selection.save("alcatraz-chain-search.json")
print(selection.selected_id, selection.frontier)
```

`select_human_chain(initial, *, strategy="placement_then_orientation",
manual_features=None, preference="execution", beam_width=4, max_expansions=64,
max_methods=16, discovery_options=None, max_group_elements=None,
gap_executable="gap", timeout=None, root=None, backend="explicit", dictionary=None,
dictionary_options=None)` prepares one exact group with the explicit backend and
runs Delivery 3 discovery once using the origin `strategy`. `discovery_options`
overrides the improvement defaults. The placement-first and block-first
chains each retain their original BFS and pool-based policies as explicit
controls; `manual_features` adds a supplied complete chain. Discovery's
stage-aware origin is recorded because its common word
pool can favor that chain.

Greedy and beam exploration mix block-placement and full-block features.
Every feature shrinks the current subgroup and every completed chain reaches
the identity. `beam_width` must be positive. `max_expansions` bounds expanded
partial nodes; `max_methods` bounds additional completed greedy/beam methods.
Both accept zero, leaving the automatic and manual controls available. These
quality budgets exclude exact preparation, certification and whole-group
evaluation. Complete rollouts guide exploration using an additive stage-cost
proxy; final metrics simplify the entire executed word for every group state.

The selected `preference="execution"` orders exact mean HTM, worst HTM,
maximum case count, summed case counts, original leaf count, original leaf HTM,
correction definition HTM and stage count. `"recognition"` puts the two case
counts first. Case counts include the solved observation. The report retains
the Pareto frontier over these eight dimensions and all controls; a selected
chain may exchange worst-case length for mean length or simpler recognition.
This is bounded computational selection without a global optimum or human
memorability claim. Delivery 6 records human review separately from these scores.

The immutable `HumanChainSearch` exposes the original raw BFS `baseline`, `method`, `candidates`,
`frontier` IDs, `selected_id`, copied `metadata` and `status`. A candidate has
an `id`, `source`, complete `method` and copied `metrics`. `save`, `to_json`
and `to_dict` write a `bce-v2-human-chain-search` inspection report without a
report loader; selected methods keep the independently loadable version-one
format. A preparation cap returns `limit_reached` with a partial method and
no candidates, while quality-search bounds retain completed/certified methods.
Read the [chain-selection contract](../../docs/human-methods.md#select-an-algorithm-aware-chain-delivery-four)
for exact objective and budget semantics.

## Build a guide using only reduced isotropy generators

Use the reduced generating set as the complete taught vocabulary while retaining
the stage guide, diagrams, recognition and application interfaces:

```python
repertoire = c.generator_human_repertoire(shape, max_group_elements=10_368)
# Or preserve the features and order of an existing selected method:
repertoire = c.generator_human_repertoire(selection.method)
repertoire.write_guide("method.md", diagram_mode=c.DiagramMode.TRANSPARENT,
                       face_colors={"U": "white", "F": "green"})
repertoire.save("generator-repertoire.json")
loaded = c.load_human_repertoire("generator-repertoire.json")
result = loaded.apply(state)
```

`generator_human_repertoire(initial, *, strategy="fully_solve_each_block",
features=None, max_group_elements=None, gap_executable="gap", timeout=None,
root=None)` accepts a shape, block analysis, prepared stage plan, or completed
`HumanMethod`. Passing a method preserves its stage features and order but
rebuilds correction words using the reduced generator set. Shape inputs use
the requested strategy or explicit features. This path skips algorithm
discovery and chain-quality search, but still enumerates the exact finite
group; `max_group_elements` is an optional preparation cap.

Exactly `M1` through `Mn` are taught, in reduced-generator analysis order.
Cases use combinations of those masters, inverses and powers, with no extra
learned definitions. Earlier stage features are restored at each whole
correction's endpoint; intermediate master applications may disturb them.
Saved repertoires use the existing format and load and apply without GAP.

This compiler remains available as a fixed-basis comparison. The Pocket Cube
notebook now uses the template compiler below.

## Select templates, symmetry variants and reusable pieces

```python
repertoire = c.template_human_repertoire(shape, preference="memory")
repertoire.write_guide("method.md", diagram_mode=c.DiagramMode.OPPOSITE_CORNERS)
repertoire.save("templates.json")
loaded = c.load_human_repertoire("templates.json")
assert loaded.apply(state).state.is_solved
```

For the ordinary cube and other large groups, select the symbolic backend:

```python
analysis = c.analyze_isotropy([0] * 27)
repertoire = c.template_human_repertoire(analysis, backend="symbolic", preference="memory")
repertoire.write_guide("cube.md", diagram_mode=c.DiagramMode.OPPOSITE_CORNERS)
```

This prepares a physical dictionary, selects a certified feature chain, and
shares witnessed algorithm bodies, inverses, legal symmetry variants and typed
physical chunks. It searches the small case tables and their expression trees,
without enumerating the reference group. Supplying an existing symbolic
`HumanMethod` selects this backend automatically and retains its physical
corrections and certified chain; template compilation, loading and application
then work offline. Shape inputs use `dictionary_options` and `discovery_options`
to configure discovery, or accept an existing `dictionary`.

The symbolic compression phase compares an exact whole-word fallback with
bounded shared-body recipes. It preserves every selected physical case word;
the learned definitions and recipes change. `max_trials` bounds accepted shared
bodies, `max_word_candidates` bounds inspected expression nodes, and
`max_word_frontier` bounds candidate bodies. `max_applications` bounds the
expression depth of eligible learned bodies; zero disables shared-body
proposals. These budgets do not bound the complete case correction.
`chunk_options` bounds separate substring mining.
`max_chain_expansions` defaults to 64 for symbolic preparation and 12 for the
explicit backend. Symbolic costs are exact additive costs under the uniform
reference-group distribution, before cancellation between stages. Portable
version-two repertoires retain this cost scope and independently verified
subgroup, word, progress and recipe certificates. The resulting guide remains
a computational method awaiting human review.

The explicit backend remains the default for shape inputs and supplies the
finite-group vocabulary search described below.

The input can be a shape, isotropy analysis, stage plan or completed method.
Shape-based preparation selects chains in the actual taught vocabulary. Passing
an existing method retains its chain unless `select_chain=True`. Reference
symmetries are included before template deletion, so an inverse or legal
regripped template can share one definition. Each complete case correction is
checked over its whole observation fiber and leaves later features free.

Complete additive macro Dijkstra supplies fallback words. Bounded physical-word
search seeks cancellations, while dictionary extraction identifies repeated
open pieces, inverse/rotation references and setup/local-loop/undo patterns.
The guide puts piece definitions under Shared piece recipes in the Algorithms
section and spells out whole-cube rotations: x follows R, y follows U, z follows F.
An exact input fallback is retained; selected mean and worst HTM may not exceed
it by more than `max_cost_ratio` (default 1.0).

`preference` accepts `memory`, `execution`, or `recognition`. Metadata records
actual solve costs, dictionary and instruction symbols, case counts, the Pareto
frontier and search scope. These are proxies, without a global quality or human
review claim. Quality limits include `max_trials`, `max_applications`,
`max_word_candidates`, `max_word_frontier`, `beam_width`,
`max_chain_expansions`, `max_chain_methods` and `chunk_options`. Physical-word
budgets apply per trial vocabulary; search counters report aggregate use.
Exact preparation retains optional `max_group_elements`, GAP timeout and root
controls. Saved artifacts load and apply without GAP.

Open paths and chunks are also public APIs:

```python
setup = c.ShapePath.from_moves(shape, setup_moves)
body = c.ShapePath.local_loop(setup.target_shape, loop_moves)
loop = setup.transport_loop(body)
dictionary = c.extract_algorithm_chunks(shape, {"A": loop.moves})
assert dictionary.expand("A") == loop.moves
```

`ShapePath` checks source/target shapes, frame, physical moves and faithful
action on construction, composition, inversion, rotation and portable loading.
Only a closed reference path with a matching original-loop witness can compile
into `LoopExpression`. `AlgorithmChunk`, `ChunkExpression` and `ChunkDictionary`
retain exact source guards for every reused piece, verified formulas, costs and
bounded search settings. Read the
[full contract](../../docs/human-methods.md#select-symmetry-templates-and-shared-pieces)
for details.

## Share a taught repertoire and verified recognition rules

Compile a completed baseline, improved method or selected chain into named
master definitions and checked instructions that reuse them:

```python
repertoire = c.optimize_human_repertoire(
    selection.method, preference="memory", max_trials=64, max_recipes=2_000,
)
repertoire.save("alcatraz-repertoire.json")
repertoire.write_guide("alcatraz-repertoire.md")
repertoire.method.save("alcatraz-expanded-method.json")
loaded = c.load_human_repertoire("alcatraz-repertoire.json")
print(loaded.metadata["baseline_metrics"], loaded.metadata["selected_metrics"])
```

`optimize_human_repertoire(method, *, preference="memory", max_trials=64,
max_recipes=2000, max_power=4, max_extra_macros=16, max_setup_macros=16,
allow_symmetry=True, max_cost_ratio=1.0)` requires a completed `HumanMethod`.
Taught master definitions are distinct from original provenance loops.
Instruction recipes include inverses, powers and checked setup/undo
constructions; symmetry transfers require an actual proper reference-bandage
symmetry. Complete recipes preserve earlier stage features at their endpoints,
while constituent master applications may disturb them temporarily.

The input's exact policy remains a selectable fallback. Bounded recipe
construction and master-removal trials seek a smaller shared vocabulary with
complete case reachability. Compressed rule families retain explicit
observation cases and are verified by expansion. Their count measures rule
families rather than reachable observations, and the guide retains concrete
footprint and sticker cues. Full policies are certified and exhaustively
evaluated across the reference group after whole-word simplification.

The default `max_cost_ratio=1.0` requires both mean and worst HTM to stay at or
below the actual input policy. A larger finite ratio permits an explicit
execution/memory tradeoff; QTM is reported without the same guarantee.
The Pareto dimensions are master count, master-definition HTM, mean HTM,
worst HTM and rule count. `preference="memory"` uses that lexicographic order;
`"execution"` puts mean/worst HTM first. These are computational proxies,
without a minimum-repertoire or human-memorability claim. Initial Delivery 6
review preferred the reduced-generator vocabulary described above.

All integer budgets accept zero. `max_trials` bounds attempted master removals,
including rejected or unreachable trials. `max_recipes` counts new proposals,
including duplicates, identities and prunes; direct master/inverse recipes and
complete fallbacks are unconditional. Powers, extra masters and setup masters
have separate limits. Exact preparation, validation and policy evaluation are
outside quality-search budgets, which preserve completed coverage when reached.

`HumanRepertoire` retains `baseline`, selected expanded `method`, `macros`,
`stages` and copied `metadata`, and exposes `recognize`, `next_step` and `apply`.
Its `save`, `to_json` and `to_dict` write a self-contained
`bce-v2-human-repertoire` version-one artifact for explicit methods or a
cost-scoped version-two artifact for symbolic methods; `from_dict` and
`load_human_repertoire(path)` validate methods, definitions and rule expansions
independently without GAP. Loading rechecks actual baseline/selected costs and
metadata consistency; historical candidate costs and search counts remain
experiment records, without a minimum-repertoire claim. The fingerprint detects changes, while exact checks
establish coverage. The selected expanded method keeps its corresponding
version-one or version-two method format. `write_guide` writes the compressed guide. Read the
[repertoire contract](../../docs/human-methods.md#share-algorithms-and-compress-rules-delivery-five)
for budget and metric semantics.

Choose `DiagramMode.OPPOSITE_CORNERS` or `DiagramMode.TRANSPARENT` when writing a
visual guide:

```python
repertoire.write_guide("method.md", diagram_mode=c.DiagramMode.OPPOSITE_CORNERS,
                       face_colors={"U": "white", "F": "limegreen"})
```

Every recognition case has an embedded cube picture and its next instruction.
Dark grey identifies guaranteed solved blocks. Face-center stickers and the
current target use the full selected face colors; all other stickers are white, including blocks
with guaranteed placement but unfinished orientation. Initial and implied guarantees count. Placement
cases show all possible target orientations together. Opposite-corner mode
uses UFR and BLD views. Transparent mode looks along the UFR diagonal with an
orthographic camera. Centers and solved grey stickers remain opaque;
unfinished non-target stickers stay white and transparent.
These diagrams need the optional `plots` extra.

`face_colors` overrides any of U/R/F/D/L/B with Matplotlib colors; omitted faces
keep the standard palette. It changes diagram colors only, preserving reference
face labels and the complete solving policy.
Use names directly, for example `face_colors={"B": "blue", "L": "orange"}`;
hex colors and RGB tuples are also accepted.
Exact white face colors receive ten thin black stripes spanning the stickers
carrying recognition colors. Only white centers and current targets receive
these marks; grey solved stickers and plain white hidden stickers remain unmarked.

Each instruction includes its identifier and the complete move sequence, such
as `M1: R U R' U'`. Rotated instructions use a diagram showing their required
starting grip, with moves and face labels expressed in that pictured frame.
The next case diagram supplies the next grip. Physical sticker colors and
guaranteed block roles follow the cube through the displayed rotation.

`recognition_block_roles`, `recognition_case_diagrams` and
`recognition_stage_diagrams` expose the semantic picture data without drawing.
`draw_cubes` accepts individual `sticker_colors` in 54-facelet URFDLB order
(one sequence per State for a gallery) and `exterior_only=True` to omit interior
surfaces. The **Algorithms** table precedes the stages, with **Turn sequence**,
**Block action**, and **Structure** columns. Its structured notation shows
exact powers, conjugates and commutators via `structured_move_notation`, alongside
expanded turns. Preparation, color legends, repeated footprint instructions,
move counts and witness provenance are omitted from the guide; portable
records retain provenance for replay and validation.
Conjugation uses `S^A = A⁻¹ S A`; nontrivial exponents are grouped, as in
`S^(X Y Z)`. Numeric exponents still denote repeated or inverse algorithms.

The BandagedPocketCube review cell refreshes rendering modules on each
evaluation. A running kernel otherwise keeps cached imports even after the
source files change. To refresh only presentation code while retaining puzzle
and method objects:

```python
from bce_v2.notebook import refresh_renderers
refresh_renderers()
```

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

The [Alcatraz notebook](../examples/Alcatraz.ipynb) also builds a table of shortest distances from
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

## Draw bandage graphs

The bandage graph has one vertex for each fixed-frame shape (a colorless
groupoid object) and a directed edge for each clockwise quarter face turn
`U`, `R`, `F`, `D`, `L`, or `B`. Parallel actions and self-loops remain visible;
inverse and half-turn edges are omitted, including when drawing an HTM graph.
Whole-cube rotation variants retain their individual vertices.

```python
graph = c.explore(initial)
figure = c.draw_bandage_graph(
    graph, layout="symmetry", show_shapes=True, edge_labels=True,
    face_colors={"U": "white", "F": "green"},
    diagram_mode=c.DiagramMode.OPPOSITE_CORNERS,
)
figure.savefig("bandage-graph.svg")

# A Shape, State, or ordinary 27-cell bandage is explored in QTM automatically.
figure = c.draw_bandage_graph(initial, layout="kamada_kawai")
figure = graph.draw(layout="spring", seed=4)

# Reuse or adjust positions before drawing.
positions = c.bandage_graph_layout(graph, layout="symmetry", seed=0)
figure = c.draw_bandage_graph(graph, pos=positions)
```

Install `./v2/python[graph]` or `./v2/python[notebooks]` to use these helpers.
The returned figure is a regular matplotlib figure. The
[BandagedPocketCube notebook](../examples/BandagedPocketCube.ipynb) displays the
graph in its third code cell, after the staged guide. All graph settings live
in this optional drawing cell, with editable
`graph_view`, `graph_max_vertices`, `graph_radius`,
`graph_layout`, `graph_show_shapes`, `graph_edge_labels`, `graph_figsize`, and
`graph_shape_size` settings. The renderer's two size arguments default to `None`,
which lets it choose them from the layout. This notebook sets shape width to
one inch and leaves figure size automatic.

`view="auto"` draws the full graph through `max_vertices=1000` and returns a
small summary above that limit. Summary rendering skips layout and shape
materialization. `view="local"` draws a neighborhood around `start`, bounded by
`radius=2` and `max_vertices`; original vertex IDs and induced clockwise actions
are retained. `view="summary"` always returns the summary, while `view="full"`
explicitly requests the complete layout. These options also work on `graph.draw`.
Leave the optional graph cell unevaluated to omit the drawing.
Calling `bandage_graph_layout` directly still explicitly requests a full layout.

[Unbandaged3x3.ipynb](../examples/Unbandaged3x3.ipynb) applies the same workflow
to the classic cube. It reports the template compiler's explicit group-size
cutoff and compares bounded direct search with both loop factorization
strategies on imported colored states, retaining timings, move counts, and
replay-checked solutions.

`layout="symmetry"` uses a force layout constrained by a whole-cube rotation
that acts within the explored component. For BandagedPocketCube, the selected
threefold subgroup appears as a planar rotation. This displays a cyclic
subgroup rather than the entire 24-element spatial rotation group in two
dimensions. If the component has no suitable cyclic rotation symmetry, the
layout falls back to a spring layout. Order-two symmetries appear as planar
reflections, allowing distinct fixed vertices along the reflection axis.
Other choices are [spring](https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.spring_layout.html),
[Kamada–Kawai](https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.kamada_kawai_layout.html)
(`"kamada_kawai"`, a distance-based energy layout), and
[spectral](https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.spectral_layout.html).
`seed` makes randomized layouts reproducible, and `iterations` controls force
relaxation. `bandage_graph_layout` returns an ID-to-`(x, y)` mapping; `pos`
accepts such a mapping for custom or reused layouts.

With `show_shapes=True`, vertex pictures use white for arbitrary stickers and
face colors for the exterior stickers on blocks containing face centers.
White face colors appear black in these pictures to match their graph edges.
`diagram_mode` selects opposite-corner or transparent views. Picture size is
proportional to directed incident degree, counting a loop twice; the `start`
vertex (default ID `0`, also accepts a shape) always has the maximum size.
Degree-two vertices keep their incident edges but display neither a marker nor
a shape picture, except for the starting vertex.

`figsize=None` (the default) chooses a square figure from typical edge lengths,
between 6 and 24 inches per side. `shape_size=None` chooses a maximum picture
width from nearby vertex spacing, degree, and diagram mode, leaving room for
incident edges. It also adapts to an explicitly supplied figure size. On large
graphs, the tightest tenth of local spacings is ignored so a few crowded
vertices do not shrink every picture; coincident or unusually close vertices
can still overlap. Changing sizes cannot resolve edge crossings in the layout.
Pass `figsize=(width, height)` or `shape_size=width` in inches to override either
setting independently. Without pictures, marker sizes use the same degree rule.
`edge_labels=True` shows Singmaster face labels in black. Edges use the selected face
palette, with white rendered as black so it remains visible.

Drawing a bounded `ShapeGraph` retains its partial status in the figure title;
it does not fill in omitted shapes. Supplying a bandage directly explores its
entire shape component. Use `c.explore(bandage, max_vertices=...)` first when a
deliberately bounded graph is wanted.

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
bce-v2 solve-loops 'Alcatraz' 'F R2' --metric HTM --timeout 60
bce-v2 solve-loops 'Alcatraz' 'F R2' --factorization quotient_kernel --metric HTM --timeout 60
bce-v2 solve-loops imported.json --max-expanded-moves 100000 --output /tmp/solution.json
bce-v2 plan-method 'Alcatraz' --max-group-elements 10368 --output /tmp/method.json --guide /tmp/method.md
bce-v2 plan-method 'Alcatraz' --max-group-elements 10368 --improve-algorithms --search-max-candidates 3000 --search-max-states 2000 --output /tmp/improved-method.json --search-report /tmp/search.json
bce-v2 plan-method 'Alcatraz' --max-group-elements 10368 --select-chain --chain-preference recognition --output /tmp/selected-method.json --chain-report /tmp/chains.json
bce-v2 plan-method 'Alcatraz' --max-group-elements 10368 --select-chain --optimize-repertoire --output /tmp/expanded-method.json --repertoire-output /tmp/repertoire.json --repertoire-guide /tmp/repertoire.md
bce-v2 plan-method shape-labels.json --strategy fully_solve_each_block
bce-v2 explore-colored imported.json --max-states 100 --output /tmp/colors.json
bce-v2 explore 'Alcatraz' --output /tmp/alcatraz-graph.json
bce-v2 isotropy 'Bicube Fuse' --output /tmp/bicube-isotropy.json
bce-v2 isotropy 'Alcatraz' --loops-only --output /tmp/alcatraz-loops.json
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

`isotropy` emits loop generators, a reduced witnessed generating set, the exact
group order, and the colored-component size. `--loops-only` extracts loops
without GAP. `--gap-executable` selects a GAP binary and `--timeout` limits its
runtime in seconds. `--output` also saves the emitted deterministic JSON.

`solve-loops` solves a fixture scramble or imported state through shape
restoration and GAP loop factorization. It accepts an optional additional
scramble, `--metric`, `--gap-executable`, `--timeout`, `--max-expanded-moves`,
`--factorization sticker|quotient_kernel`, and `--output`. The default is
`sticker`. JSON includes the ordered loop powers and only the algorithms they
use; quotient mode also records placement and kernel stages and the used
kernel algorithms. Solved, unreachable, and expansion-limited results exit with codes
0, 3, and 2 respectively; backend failures exit with code 1.

`plan-method` generates a reusable computational method from a fixture,
inline JSON list of 27 labels, label-list JSON file, or the reference
specification in a saved puzzle file. It accepts `--strategy`,
`--max-group-elements`, `--gap-executable`, `--timeout`, `--output` and `--guide`.
Full method JSON is emitted to stdout and optionally saved; `--guide` writes
Markdown. Completed methods exit with code 0, cap stops with code 2, and invalid
inputs or backend errors with code 1. `--improve-algorithms` runs bounded
correction discovery for a completed baseline. Its options are `--search-mode`,
`--search-max-seed-loops`, `--search-max-candidates`, `--search-max-states`,
`--search-rounds`, `--search-max-word-length`, `--search-max-htm-length` and
`--search-max-expanded-moves`, with the Python API defaults.
`--search-report` writes a separate inspection report and requires improvement
to be enabled. A preparation cap skips improvement and leaves any search-report
path untouched. Method stdout/output retains the version-one method schema.
Input, method JSON, guide and search report files must be distinct, including
symlink and hardlink aliases.

`--select-chain` compares bounded mixed-feature chains with a common algorithm
pool, using the existing `--search-*` settings for one discovery run.
`--strategy` chooses its origin baseline. Selection options are
`--chain-preference execution|recognition`, `--chain-beam-width` (default 4),
`--chain-max-expansions` (64) and `--chain-max-methods` (16).
`--chain-report` saves the separate inspection report and requires selection.
It must differ from every other file, including aliases. Selection cannot be
combined with `--improve-algorithms`, and `--search-report` retains its
improvement-only meaning. A preparation cap writes an explicit partial chain
report alongside the partial method/guide and exits with code 2. Quality
budgets leave the selected method complete and its portable schema unchanged.

`--optimize-repertoire` runs after ordinary synthesis, improvement or chain
selection. Stdout, `--output` and `--guide` describe the selected expanded
version-one method. `--repertoire-output` saves the independently loadable
wrapper with shared master definitions, compressed rules and comparison
metadata; `--repertoire-guide` writes its compressed guide. Both require
optimization and must differ from all input/other artifact files, including
aliases. Its options are `--repertoire-preference memory|execution`,
`--repertoire-max-trials` (64), `--repertoire-max-recipes` (2000),
`--repertoire-max-power` (4), `--repertoire-max-extra-macros` (16),
`--repertoire-max-setup-macros` (16), `--repertoire-no-symmetry`, and
`--repertoire-max-cost-ratio` (1.0, finite and at least one).
A preparation cap skips optimization and leaves repertoire output/guide paths
untouched; ordinary partial method artifacts and a requested partial chain
report remain available.
