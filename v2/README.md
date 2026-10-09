# Rust cube engine and Python research interface

This replacement is developed alongside the original Python project. The computational engine uses only Rust's standard library. A separate PyO3 extension supplies the `bce_v2` Python research interface, packaged with maturin. The old project remains a reference.

## Use from Python

See the [Python guide](python/README.md) for installation, inline bandage definitions, validated colored input, exact QTM/HTM colored search, shape-loop solving and GAP group counts, shape solutions, galleries, optional NetworkX views, and deterministic records. From the repository root:

```sh
python3 -m venv v2/.venv
v2/.venv/bin/python -m pip install './v2/python[all]'
```

Open [Alcatraz.ipynb](examples/Alcatraz.ipynb) in VS Code for an interactive
research session with inline galleries. The workspace settings select
`v2/.venv` and activate terminals automatically. Install the recommended Python
and Jupyter extensions and choose the `v2/.venv` notebook kernel once if prompted.

[BandagedPocketCube.ipynb](examples/BandagedPocketCube.ipynb) is a minimal
shape-only example: one cell displays exact counts, loop-generator effects,
and a reusable human-style solution using only the reduced isotropy generators,
with the existing stage plan and recognition diagrams. The notebook calls
`c.generator_human_repertoire(selection.method)`, so each correction is a
combination of the three generators shown above it. Set `diagram_mode` to
`c.DiagramMode.OPPOSITE_CORNERS` or
`c.DiagramMode.TRANSPARENT` and edit `face_colors` before evaluating its cell.
Face colors accept names such as `"blue"` and `"orange"`. Opposite-corner mode
shows solved blocks in light tints and the current target in the selected face
colors. Transparent mode looks along the UFR diagonal and colors only centers
and current targets; other stickers stay white.
Each instruction repeats its algorithm identifier and moves beside a diagram
in the required starting grip. The algorithms appear in a compact table before
the stages. The cell refreshes rendering code on each evaluation so an open
kernel picks up display changes made during review.

For a direct shape-to-guide pipeline, call
`c.generator_human_repertoire(shape)`; this skips algorithm discovery and
chain-quality search. Passing an existing method retains its chosen stage
features and order. Whole corrections restore earlier stage features even if
individual generator applications temporarily disturb them. Repertoire save,
load and application work with the existing portable format. The algorithm
optimizers remain available, but further human-quality improvements are shelved
after the initial review preferred the smaller generator vocabulary.

[PuzzleSignatures.ipynb](examples/PuzzleSignatures.ipynb) explores the complete
non-isomorphic atlas by block inventory. Its saved SQLite database supports
queries such as puzzles containing a 222, maximum domino-only puzzles, and every
signature with its class count. The [signature guide](../docs/block-signatures.md)
explains the 1,735 full-atlas signatures, 1,732 filtered signatures, and types
distinguishing center/core placement, including 221Core, 321Core, and BigClock.

The Python package is the primary research interface. [Alcatraz.ipynb](examples/Alcatraz.ipynb) combines shape exploration, facelet input, direct colored solving, loop generators with exact block actions and decorated cycles, exact group counts, colored distance profiles, and farthest-state views. [MostSignaturesCube.ipynb](examples/MostSignaturesCube.ipynb) uses loop-group analysis to count the colored states of the puzzle with the most shapes, with the same reference-block inventories and generator effects, together with a short colored solve. The [human-method compiler](../docs/human-methods.md) now turns a reference shape into exact stabilizer stages, a complete reusable case policy, legal correction algorithms, portable JSON and a Markdown guide. Its precompiled policy handles every reachable colored state already in that shape without factoring each scramble. Bounded stage-algorithm improvement supplements this policy with native-loop, shallow-word and structured searches while retaining complete fallbacks. Algorithm-aware chain selection compares original BFS controls with pool-based automatic and mixed-feature methods using one common witnessed word pool; separate reports retain physical costs, recognition and repertoire measures, and the Pareto frontier. Repertoire optimization shares taught master definitions and verifies compressed recognition rules while preserving complete fallback policies; independently loadable repertoire artifacts include comparison metadata. The stage backend is validated on both puzzles and the other named fixtures. Initial review accepted the diagrams but preferred reduced-generator recipes; further algorithm-quality improvements are shelved in the [evolving plan](../docs/human-methods-plan.md).

The engine models connected partitions of the legacy 27-cell grid, including its virtual core, and the six outer faces of an ordinary fixed-center 3×3 cube. It supports quarter turns, half turns, and inverses in standard Singmaster notation. Noncuboid connected blocks are allowed; the narrower enumeration family in the roadmap is a separate concern.

Milestone five adds exact cuboid-cover counting and generation, 24 proper
rotations, legal-motion classification, and optional complete implicit-bond
closure. The default omits core bonds and admits connected boxes with the core
removed, including a seven-shell-cubie corner 2×2×2 block. There are 312,238,908
such spatial partitions and 13,016,719 proper-rotation classes before legal
turns. See [the enumeration model and research](../docs/enumeration.md) and
[measurements](benchmark-results/enumeration.md). Exact direct colored solving is available for tractable cases.

The complete behavioral atlas contains 7,073 classes, or **4,857** after
identifying mirror pairs and excluding permanently frozen or one-axis puzzles.
[Both datasets](enumeration-results/README.md) include representatives and
originating seeds. The `analyze_atlas` CLI postprocesses the original atlas using
all 48 spatial symmetries and complete-component mobility checks; its
`--dead-ends` policies are `none`, `frozen`, `one-axis` (default), and
`unchanging-shape`.

## Run the engine

From this directory:

```sh
cargo test
cargo clippy --all-targets -- -D warnings
cargo run --release --bin cube_engine -- fixtures
cargo run --release --bin cube_engine -- replay Alcatraz "F R2"
```

The fixture command explores a bundled snapshot of the existing CSV puzzles and reports reachable shape counts, labeled clockwise arcs, and solved-shape eccentricity in QTM. Reverse traversal supplies inverse turns when calculating distances. Parallel move actions and self-loops are retained. The snapshot lets packaged builds run independently of the old project.

`explore(initial)` runs until the entire reachable shape component is discovered, without a vertex limit. Bounded experiments must explicitly call `explore_with_limit(initial, max_vertices)` and check the returned `complete` flag. `explore_with_options` also supports HTM, storing all 18 legal actions. Graph distances and shortest paths use the declared metric and retain move witnesses. The Rust fixture CLI requires complete exploration before reporting counts or distances.

The replay command starts from the recorded solved state, applies checked moves, and prints both the resulting shape and colored state. Invalid notation and blocked moves produce an error. The Python package and its batch CLI provide colored input, exploration, and exact direct solving, as well as shape exploration.

## Representations

| Type | Meaning | Storage |
| --- | --- | --- |
| `Partition` | Connected footprints, with arbitrary block names removed | 27 bytes |
| `BondShape<L>` | Canonical adjacency equality in a declared bit layout | 8 bytes |
| `CubeState` | Corner identities/twists and edge identities/flips | 40 bytes |
| `BandageSpec` | Immutable membership by solved home-cell identity | A partition |
| `BandagedState` | A colored state, owned specification, and matching cached shape | Specification plus state values |

`Partition::from_legacy` treats each input zero as a separate singleton and normalizes internal labels to `1..k`. It rejects disconnected blocks. `Partition::footprints` supplies derived `u32` occupancy masks for inspection and comparison.

Bond bits are set for **every adjacent pair belonging to the same block**, including bonds implied by connectivity. This closure makes the encoding unique. `BondShape::from_bits` rejects unused bits and bond sets missing that closure; `from_partition` constructs a valid shape directly. Layout conversions use `reencode` and do not reinterpret raw words.

All layouts in this implementation retain the full grid's 54 adjacency edges. A 48-edge shell-only model would need its own conventions and conversion checks: deleting the core can change connectivity or legality.

The default layout is `LegacySparse`, carrying forward the original enumerator's 48 shell positions and assigning six previously unused positions to core bonds. `AxisMajor` is the straightforward comparison layout. `Tuned` is an experimental candidate read from `engine/layouts/tuned.txt`; the first search found no better assignment, so it currently equals `LegacySparse`. Its benchmark rows are a duplicate control, not evidence for a third distinct layout.

Bit positions follow the canonical bond list in [geometry.rs](engine/src/geometry.rs): strides 9, 3, then 1, each with ascending source cell. The associated `POSITIONS` array maps that order to physical bit positions. Raw words are layout-specific; Python persistence exports canonical labels rather than raw bond words.

## Move and color conventions

Cell indices preserve the old formula `down * 9 + front * 3 + right`. Physical coordinates are right, back, and up, centered at zero. A clockwise turn is viewed from outside its face. Center positions and the virtual core stay fixed, but a rotating face's center still belongs to its moving layer for bandage legality.

All v2 interfaces use standard Singmaster notation, including `B` and `D`. There is no legacy direction conversion or block-label permutation mode. Slice turns, wide turns, and whole-cube frame operations are not accepted by the current parser.

`CubeState` uses corner order `URF UFL ULB UBR DFR DLF DBL DRB` and edge order `UR UF UL UB DR DF DL DB FR FL BL BR`, with the standard orientation convention. `try_new` checks identities, orientation sums, and matching permutation parity. Center markings and center spin are outside this ordinary-cube representation. [Reference conventions](https://kociemba.org/math/CubeDefs.htm).

`BandageSpec::solved_state` constructs a matching `BandagedState`. A successful checked turn updates colors and bonds together; a blocked move leaves the state unchanged. In debug builds, the cached shape is also compared against a fresh derivation from piece identities and the specification. `CubeState::from_facelets` and `to_facelets` use standard 54-character URFDLB order. `BandageSpec::state_from_cube` checks that every fused block shares one proper spatial rotation of its home positions and sticker directions. This includes unmarked fixed centers, core bonds, and noncuboid blocks. Ordinary cube validity and rigid compatibility do not establish bandaged reachability.

```rust
use bandaged_cube_engine::{BandageSpec, Partition, parse_moves};

let specification = BandageSpec::new(Partition::singletons());
let mut state = specification.solved_state();
for movement in parse_moves("R U R' U'").unwrap() {
    state.try_turn(movement).unwrap();
}
assert!(state.check_shape());
assert!(!state.cube().is_solved());
```

QTM assigns half turns cost two and other face turns cost one; HTM assigns each parsed face move cost one. The engine generates all 18 moves directly, rather than executing an inverse as three separate quarter turns.

## Exact colored search

`colored_search::solve(initial, target, options)` performs BFS or bidirectional
BFS on full colored states, checking bandage legality at every step. `None`
target selects solved with the initial reference specification; an explicit
target must have exactly the same specification. `SearchOptions::default()`
selects bidirectional QTM without an implicit cap. Successful results contain a
shortest executable move witness and distance. `Unreachable` means a component
was exhausted; `LimitReached` means an explicit `max_states` or `max_depth`
prevented a conclusion. Depth bounds include zero and apply to total solution
cost. State caps count stored records, including both bidirectional roots.

Bidirectional search expands complete frontier layers from the smaller side.
Before a meeting, the visited sets are disjoint balls of radii a and b, so the
target distance exceeds a+b. A meeting in the next layer has distance a+b+1,
which proves optimality. A memory cutoff in a partial layer reports a cutoff.

`colored_search::explore_colored(initial, metric, max_states)` retains a complete
colored component unless a positive explicit cap omits reachable states. It
stores every directed unit-cost action (quarter/inverse in QTM, also half turns
in HTM), including parallel actions and self-loops. Distances and paths in a
partial graph describe only retained vertices. The search key is `CubeState`:
the specification is fixed and determines the cached shape, while orientations
remain part of the key. No spatial symmetry quotient is used.

These searches are intended for tractable components and short solutions.
Memory-conscious larger exact searches remain future milestone-four work.

## Shape loops and GAP analysis

The Rust engine extracts legal root loops from a complete QTM shape graph using
a spanning tree. Every non-tree edge contributes a tree transport, its move,
and the inverse return transport, giving `arcs - shapes + 1` candidates.
Self-loops and parallel actions remain distinct. Identity permutations and
duplicates up to inverse are discarded without changing the generated group.
The remaining 48-sticker permutations generate the full root isotropy group,
with replayable move witnesses stored through shared tree paths.

Python exposes `c.isotropy_loops(initial)` and `c.analyze_isotropy(initial)`.
The latter invokes an optional external GAP executable to compute the exact
group order and reduce generators by subgroup membership while retaining
original loop witnesses. Install GAP separately; use `gap_executable` when it
is outside `PATH`. Extraction alone has no GAP dependency. The batch commands
are `bce-v2 isotropy PUZZLE` and `bce-v2 isotropy PUZZLE --loops-only`.

In the fixed-frame model with full cubie identities and orientations and
unmarked centers, the exact reachable colored-state count is the complete
shape count multiplied by the isotropy-group order. This computes counts
without enumerating colored states. Partial shape graphs are rejected, and
rotation-quotiented counts cannot be substituted. See the [Python guide](python/README.md#shape-loops-and-exact-group-counts)
for examples and deterministic JSON export conventions.

Each witnessed loop also exposes an exact reference-block action, with stable
member-cell identities, destinations, observable proper rotations, and modular
orientation phases. Deterministic shared frames give one-line decorated cycles
such as `(UFL- UFR UBR+)` and preserve in-place twists, flips, and rotations of
symmetric fused blocks. The Python API provides `loops.block_inventory`,
`analysis.block_inventory`, and `generator.block_action`; deterministic exports
retain both block descriptions and the authoritative sticker permutations.
See the [block-action guide](../docs/block-actions.md) for notation and frames.
An opt-in quotient/kernel solver uses the same exact actions for block
placement followed by abelian orientation correction.

## General loop-factorization solver

`c.solve_colored_loops(state)` restores the shape and uses GAP subgroup
membership and word factorization to express the remaining correction through
legal root loops. A reusable `c.LoopSolver(specification)` keeps a stable
repertoire of reduced original loop algorithms across scrambles. Each solve
greedily chooses a smaller candidate subgroup containing the residual state,
favoring fewer distinct algorithms without claiming a minimum. Imported
colored states need no move history. The target is solved with the same
specification; no colored component is enumerated.

The prepared solver reuses its shape graph and algorithm library. Each
nontrivial residual correction launches a fresh GAP factorization subprocess;
its stabilizer chain is not cached across solves. Timeouts apply to each GAP
call and exclude shape exploration.

Results retain a shape-restoration path, ordered generator IDs with signed
powers, only the algorithm witnesses they reference, and an expanded executable
solution. Every expanded solution is replay-checked. The declared QTM/HTM metric
reports physical move cost; these solutions have no shortest-path guarantee.
An explicit `max_expanded_moves` caps the unsimplified QTM witness length and
can retain the compact expression while
returning `limit_reached` before expansion. Exact membership failure proves
`unreachable`; backend errors remain errors.

The batch interface is `bce-v2 solve-loops PUZZLE [MOVES]`, with metric, GAP
executable, timeout, expansion limit, `--factorization sticker|quotient_kernel`,
and JSON output options. See the
[Python loop-solving guide](python/README.md#solve-scrambles-with-shape-loops).
The opt-in `factorization="quotient_kernel"` strategy first factors reference
block placement, lifts that word through original loops, and corrects the
remaining action in the footprint-fixing abelian kernel. A lazy
`solver.block_structure` exposes exact isotropy, quotient, and kernel orders,
and a witnessed independent cyclic basis. Results retain separate placement
and kernel expressions alongside the complete expression in original loop IDs.
The original `sticker` factorization remains the default. Both notebooks show
the decomposition and kernel algorithms with legal replay checks.

`c.discover_loop_algorithms(analysis)` now mines a bounded library of powers,
commutators, and conjugates, preserving nested expressions and verified short
literal turn sequences. It retains separate shortest and structured witnesses
for each selected effect. `solver.solve_options(state, library=library)` compares
the baseline, bounded searches, and enriched GAP factorizations, exposing both
`shortest_found` and `most_structured`. The notebooks show both views, their
physical lengths, remembered leaves, original witnesses, and resource limits.
These rankings are heuristic; they do not prove shortest physical solutions or
human memorability. Exact quotient tables and reusable recognition rules remain
followups. Direct colored search retains its existing shortest-path guarantees.

## Generated kernels and tuning

[build.rs](engine/build.rs) generates turn tables and mask-and-shift kernels from coordinates. For each move, it groups source bits with the same displacement into one mask and shift, then combines the groups. The legal domain is checked separately with one boundary mask:

```text
(shape_bits & face_boundary_mask) == 0
```

The library forbids unsafe Rust. CPU-specific code is confined to a benchmark experiment, guarded by runtime BMI2 detection.

Run the deterministic layout search and retain its output separately before changing the candidate:

```sh
cargo run --release --bin layout_search -- 400000 > /tmp/candidate-layout.txt
```

Its score sums the distinct nonzero shift displacements across all 18 moves, assigning each move equal weight. It uses simulated annealing with a fixed seed and makes no global-optimality claim. This is a cheap candidate-generation objective, not an instruction count or a timing prediction. Compiler output, constant loads, instruction dependencies, dispatch, and workload frequencies still matter. Only adopt a candidate after testing and measuring it.

## Benchmarks and evidence

See [the hardware measurements](benchmark-results/README.md) for recorded results, raw samples, and interpretation.

The dependency-free harness calibrates repetition counts, warms workloads, interleaves layouts, and returns observable results through `black_box`. It measures mixed legality queries, turns on known legal inputs, complete successor generation, a dependent U-turn chain, and complete BFS with labeled arcs. Its corpus contains all 3,508 shapes of the three recorded puzzles.

```sh
cargo bench --bench layouts
RUSTFLAGS="-C target-cpu=native" taskset -c 1 cargo bench --bench layouts -- --samples 9 --sample-ms 100 --csv benchmark-results/local-native.csv
```

The second command is for Linux and optimizes for the current CPU. Keep portable compilation as the normal build; do not distribute a native-target binary to arbitrary hardware. Relative CSV paths are interpreted from `v2/`, even though Cargo launches the benchmark from its package directory.

On x86-64 with BMI2, the harness also tests `PEXT` plus six lookup tables. It verifies the results against the shared-shift kernels before timing. Those tables occupy 192 KiB of entries and are excluded from the portable engine default. Their current measurements cover isolated turns, not complete BFS or large datasets.

## Verification coverage

The integration suite checks every reachable shape of Alcatraz, Bicube Fuse, and Shark Fin Soup against an independent partition BFS, and compares all 18 moves across the three layouts. It also covers randomized connected partitions, closure validation, core anchoring, move/inverse identities, rejected moves, self-loop preservation, bounded exploration, QTM/HTM path replay and optimality against an independent graph BFS, and owned colored states.

Colored turns are checked against independent standard quarter-turn tables and a separate geometric sticker simulation over 1,200 random moves. Legal bandaged walks of 600 moves per fixture check cache agreement, ordinary cube invariants, and complete inverse replay.

Verified fixture totals are 1,449 / 121 / 1,938 shapes, 2,048 / 168 / 2,968 clockwise arcs, and solved QTM eccentricities 16 / 7 / 20 respectively. These baselines concern uncolored shapes; colored components are explored separately with explicit completeness reporting.

Colored import tests replay 4,800 legal steps across legacy fixtures, noncuboid
blocks, core bonds, and the unbandaged cube, and compare exported facelets with
independent geometric sticker transport over 1,000 random words. Search tests
compare all-pairs optimal distances on four- and sixteen-state colored
components with an independent ordinary-cube BFS, replay every returned path,
and check state/depth caps, orientation-only differences, and geometrically valid
unreachable imports. Python integration tests cover both metrics and algorithms
on generated short scrambles of every named fixture, persistence, graph exports,
and CLI outcomes.
