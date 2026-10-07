# Rust cube engine and Python research interface

This replacement is developed alongside the original Python project. The computational engine uses only Rust's standard library. A separate PyO3 extension supplies the `bce_v2` Python research interface, packaged with maturin. The old project remains a reference.

## Use from Python

See the [Python guide](python/README.md) for installation, inline bandage definitions, full colored replay, QTM/HTM shape solutions, galleries, optional NetworkX views, and deterministic records. From the repository root:

```sh
python3 -m venv v2/.venv
v2/.venv/bin/python -m pip install './v2/python[all]'
```

Open [Alcatraz.ipynb](examples/Alcatraz.ipynb) in VS Code for an interactive
research session with inline galleries. The workspace settings select
`v2/.venv` and activate terminals automatically. Install the recommended Python
and Jupyter extensions and choose the `v2/.venv` notebook kernel once if prompted.

[PuzzleSignatures.ipynb](examples/PuzzleSignatures.ipynb) explores the complete
non-isomorphic atlas by block inventory. Its saved SQLite database supports
queries such as puzzles containing a 222, maximum domino-only puzzles, and every
signature with its class count. The [signature guide](../docs/block-signatures.md)
explains the 931 full-atlas signatures, 928 filtered signatures, and exact
physical refinements for blocks whose box includes the omitted core.

The Python package is the primary research interface. Feature-chain and distance-layer experiments remain milestone-six work.

The engine models connected partitions of the legacy 27-cell grid, including its virtual core, and the six outer faces of an ordinary fixed-center 3×3 cube. It supports quarter turns, half turns, and inverses in standard Singmaster notation. Noncuboid connected blocks are allowed; the narrower enumeration family in the roadmap is a separate concern.

Milestone five adds exact cuboid-cover counting and generation, 24 proper
rotations, legal-motion classification, and optional complete implicit-bond
closure. The default omits core bonds and admits connected boxes with the core
removed, including a seven-shell-cubie corner 2×2×2 block. There are 312,238,908
such spatial partitions and 13,016,719 proper-rotation classes before legal
turns. See [the enumeration model and research](../docs/enumeration.md) and
[measurements](benchmark-results/enumeration.md). Colored solving is deferred.

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

The replay command starts from the recorded solved state, applies checked moves, and prints both the resulting shape and colored state. Invalid notation and blocked moves produce an error. The Python package and its batch CLI provide the larger shape exploration interface; colored solving remains milestone-four work.

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

`BandageSpec::solved_state` constructs a matching `BandagedState`. A successful checked turn updates colors and bonds together; a blocked move leaves the state unchanged. In debug builds, the cached shape is also compared against a fresh derivation from piece identities and the specification. Arbitrary colored-state import into a bandaged puzzle will require additional rigid-block and reachability checks; that interface is not inferred from ordinary cube validity alone.

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

Verified fixture totals are 1,449 / 121 / 1,938 shapes, 2,048 / 168 / 2,968 clockwise arcs, and solved QTM eccentricities 16 / 7 / 20 respectively. These results concern uncolored shapes; the engine retains colors without enumerating their much larger state spaces.
