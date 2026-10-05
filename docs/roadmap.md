# Bandaged cube explorer roadmap

Tentative roadmap, 5 October 2026. Rust has been chosen and the first representations and move engine are implemented in [v2](../v2/README.md). Later milestones and broader puzzle definitions remain proposals.

The replacement uses a Rust library and command-line application, developed alongside the existing Python project. Build shape exploration, colored solving, and enumeration on a precise model and verified move engine; use their results to develop human solving methods and an atlas of bandaged puzzles. Keep the general theory in view while making the first implementation specific to 3×3 cubes.

## Preserve the existing project

Leave `bce/`, `puzzles/`, the example scripts, images, and the existing README untouched. The new implementation lives in `v2/`, with its own build configuration and documentation.

The old project remains a working reference until the replacement reproduces its useful behavior, imports its puzzle records, supplies better documentation and visualizations, and solves colored puzzles. Migration should be a later, explicit decision. When an old behavior is incorrect or ambiguous, document the difference rather than reproduce it silently or modify the reference.

The existing design has substantial value:

- The [README](../README.md) already models legal transports as a groupoid over uncolored bandage shapes, and proposes restoring shape before solving the remaining sticker permutation.
- [The core](../bce/core.py) provides shape normalization, move legality, reachable-shape exploration, and shortest paths.
- [The examples](../usage.py) develop recognizable feature chains, measure distances between stages, and display difficult cases. These are a useful starting point for human solving methods.
- [The renderer](../bce/graphics.py) and [puzzle database](../puzzles/database.csv) supply galleries, transparent views, and three named fixtures.

An important boundary: `fullperm=True` preserves block labels; it does not track all cubie identities, corner twists, edge flips, or stickers. A complete colored solver requires an additional state representation.

Read-only runs of the existing exploration code produced these migration baselines. Distances use an undirected graph of quarter turns, with reverse traversal interpreted as an inverse turn.

| Recorded puzzle | Reachable shapes | Clockwise quarter-turn arcs | Maximum distance from recorded solved shape in QTM |
| --- | ---: | ---: | ---: |
| Alcatraz | 1,449 | 2,048 | 16 |
| Bicube Fuse | 121 | 168 | 7 |
| Shark Fin Soup | 1,938 | 2,968 | 20 |

These are shape counts and distances, not colored-state counts or graph diameters. NetworkX was unavailable, so its unused import was omitted when running `explore`; distances were computed independently with a standard-library BFS.

## Choose Rust for the computational core

Rust is a good fit for compact state values, bit operations, large searches, and parallel enumeration. Its control over memory layout and compiler checks support this workload. The actual speedup will depend on algorithms, state keys, allocation, and memory access; choosing Rust alone does not resolve exponential growth. [Rust language overview](https://doc.rust-lang.org/book/ch00-00-introduction.html).

Start with one library crate organized into modules and a thin CLI in a `v2/` Cargo workspace. Split out additional crates when their boundaries become useful. Keep parsing, rendering, persistence, and language bindings outside the move and search kernels. Prefer safe Rust and precomputed tables initially; introduce more specialized operations only after measurement. [Cargo workspace documentation](https://doc.rust-lang.org/book/ch14-03-cargo-workspaces.html).

Python can remain a convenient research interface later. A separate PyO3 binding layer, packaged with maturin, would expose the Rust implementation without making the core depend on Python. Expose substantial operations such as exploring a component or solving a batch, so Python calls do not dominate computation. [PyO3 documentation](https://pyo3.rs/), [maturin documentation](https://www.maturin.rs/).

Interactive graphics can use a browser frontend, with a native service or eventually a WebAssembly build of the core. Select that interface after the move engine and export formats exist.

## Define the objects and equivalences

Separate three concepts in both the mathematics and API:

1. A **bandage specification** says which identified cubies are fused in a reference configuration, together with the puzzle's move and mechanical conventions.
2. A **colored state** records where the identified cubies are and how they are oriented.
3. A **bandage shape** records the occupied footprints of the blocks after forgetting colors and arbitrary block names. It is a projection of a colored state.

The specification stays fixed while the state changes. Two different colored states can project to the same shape and still need very different solutions.

### Decide what all bandaged cubes includes

The explorer documents cuboid blocks on a 27-cell lattice, including a virtual core. The [enumerator's definitions](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/README.md) narrow the target further to partitions obtained by repeatedly cutting a block with a face plane, excluding size-two blocks containing the core. A broader shell-cubie model would permit arbitrary connected groups of the 26 shell cubies; physical realizability still depends on the declared mechanics.

Proposed first enumeration target: reconstruct the earlier cut-generated family and verify its assumptions. Treat connected noncuboid bandages as a subsequent, explicitly named family. This gives us a reproducible starting point without limiting the underlying kernel to cuboids.

Document center behavior, the virtual core, permitted connectivity, and move sets. A core cell fused to a center can impose a constraint; removing that cell is not automatically a valid conversion. Initially use the six outer faces in a fixed frame, with QTM and HTM as explicit metrics. Treat whole-cube reorientation as a frame operation; add slices and wide turns only with a defined mechanical model.

### Keep different equivalences separate

| Equivalence | Question it answers |
| --- | --- |
| Block relabeling | Are these two encodings of the same partition? |
| Proper rotations | Are these reference shapes the same after one of the 24 spatial rotations? |
| Rotations and reflections | Should mirror images also be identified? This can merge chiral pairs. |
| Legal-motion equivalence | Can one uncolored shape be reached from the other by legal turns, allowing any explicitly chosen frame equivalence? |
| Behavioral equivalence | Do different bandage specifications impose the same legal behavior, for example because some additional bonds are implicit? |
| Transition-system isomorphism | Are the move graphs equivalent under a declared rule for preserving or renaming move labels and permutation actions? |

Use proper rotations as the proposed default for geometric enumeration. Report motion classes separately. The old C++ `filter_rotations` also explores reachable face turns, so its result is a quotient by motion as well as rotation. [Filtering implementation](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/cubes/main.cpp#L66).

## Use several representations with explicit conversions

The most promising design combines a simple partition representation, a compact shape representation, and a complete colored representation. Each serves a different operation.

| Representation | Proposed role | Strength and condition |
| --- | --- | --- |
| Normalized `[u8; 27]` block labels | Reference engine, legacy import, readable fixtures | Simple and independent of bit tricks; use internal labels `1..k` in first-occurrence order and expand every input zero into its own singleton |
| Block footprints as `u32` masks | Legality reference and optional cached geometry | Each mask occupies at most 27 bits; directly handles membership in a moving layer |
| Canonical adjacency bonds in a `u64` | Candidate shape-search and enumeration kernel | 54 adjacency edges for the full 27-cell grid, or 48 for the shell; requires blocks connected within the represented domain |
| Corner and edge permutations and orientations | Colored search and permutation transport | Retains information lost by every shape-only representation |

For the bond encoding, set a bit for **every adjacent pair in the same block**, rather than only the pairs originally glued. Recover the partition by connected components. This makes the encoding unique for connected partitions; raw bond subsets can encode the same partition in many ways. The existing enumerator already uses a related 48-bond encoding and generated move operations. [Existing representation code](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/cubes/enumerator.py#L9).

Keep the full-grid and shell conventions as distinct types or explicit model parameters. A block connected through the virtual core can have a disconnected shell footprint, and a shell mask cannot retain its core membership. Converting between these conventions requires proof or validation of the resulting behavior.

For a layer mask `L` and a block footprint `B`, a turn is legal precisely when every block satisfies:

```text
(B & L) == 0  or  (B & L) == B
```

With connected blocks encoded as adjacency bonds, the equivalent test is:

```text
(shape_bonds & layer_boundary_bonds) == 0
```

A connected block crossing the layer boundary must contain a bond across that boundary. On legal states, a turn transports the layer's internal bonds, leaves the complement's internal bonds fixed, and leaves all boundary bond bits zero. Generate these operations from coordinates and verify them against the partition engine.

For ordinary colored 3×3 states, begin with explicit arrays for eight corner identities and twists, and twelve edge identities and flips; fixed centers are implicit. Orientation is essential even when all pieces occupy their home positions. Later, benchmark packing identity and orientation into 20 bytes and more compact search keys. Marked-center variants need additional state. [Cubie representation and orientation conventions](https://kociemba.org/math/cubielevel.htm).

Keep the bandage specification keyed by stable piece identities. Derive the current shape from it and the colored state; optionally cache its bond mask for fast legality. Assert agreement between the cache and that derivation. Keep rendering geometry separate from search keys.

For symmetry, precompute the 24 rotations and choose a deterministic minimum shape encoding. A geometric canonical key is useful for enumeration. Colored search may only quotient symmetries that preserve the puzzle and target, or must transport the specification, colors, goal, and move labels together and retain enough information to reconstruct the solution.

Benchmark complete exploration workloads as well as individual turns: successor generation, legality, normalization, hashing, symmetry canonicalization, allocations, peak memory, and states visited per second. Compare representative small, highly mobile, and strongly bandaged cases. Use release builds and a repeatable benchmark harness such as [Criterion](https://docs.rs/criterion/latest/criterion/). Let measurements decide whether to retain the proposed bit layout or optimize it further.

## Milestones and completion criteria

### First milestone Language and model decisions

Agree on Rust, the initial puzzle family, core and center conventions, symmetry policy, notation, and metrics. Write a short model specification with examples of distinct colored states sharing one shape. Specify validation and exact conversions from the old database.

Completion criterion: we can state precisely what constitutes a puzzle, a state, a legal move, and an enumeration class. Representation choices remain replaceable behind these definitions.

### Second milestone Verified move engine and representation benchmarks

Implement the partition reference engine, full colored turns, and candidate bond engine. Include parsing, canonical block labels, legality, move inverses, and consistent coordinate conventions. Use an independent sticker or coordinate implementation to check colored turns.

Check move/inverse round trips, four quarter turns giving identity, rejected blocked moves, preservation of rigid blocks, parity and orientation invariants, and agreement among representations. Reject malformed input and unknown move notation. Verify conversions for core-containing legacy blocks rather than assume them.

Completion criterion: the new engine reproduces all three legacy shape baselines and replayed legal sequences, passes the mathematical checks, and provides enough benchmark evidence to choose the initial search representation. No need to promise a speedup before measuring it.

### Third milestone Shape exploration and a usable replacement

Provide a CLI for importing puzzles, inspecting legal moves, exploring a reachable shape component, finding a shape solution, and exporting results. Use queues and compact values, dense vertex IDs, and lazy successor generation when storing a graph is unnecessary.

Retain distinct labeled edges and self-loops, with their induced colored permutations. The ordinary unbandaged cube has one shape vertex, but its face turns still generate the entire cube group. Collapsing those actions would destroy the information needed for colored solving.

Replace all-pairs distance calculations for feature stages with reverse multi-source BFS from each target set. Explore complete components by default. Any resource limits must be explicitly requested, with clear reporting of incomplete exploration; add cancellation and checkpointing when needed. Begin with versioned puzzle records and exports recording the model, metric, symmetry convention, and completeness status.

Completion criterion: the existing shape-analysis workflows can be reproduced through a documented CLI/library, with basic shape rendering or galleries and deterministic exports.

### Fourth milestone Solve colored puzzles

Accept colored cubie or sticker input together with bandage membership. Check ordinary cube validity separately from reachability under the bandaging: a valid ordinary cube configuration may still be unreachable for this puzzle. Use scrambles generated by legal moves as reliable positive fixtures.

Develop two complementary approaches:

- **Direct constrained search:** establish exact BFS or bidirectional BFS results for tractable cases, then add IDA* or another suitable memory-conscious search for larger ones. Generate only currently legal turns. Combine exact shape distance and relaxed ordinary-cube pattern distances using a maximum; use sums only with a proof of admissibility or a valid cost partition.
- **Shape restoration followed by loop solving:** choose a spanning tree in the complete labeled shape graph. For each remaining edge, transport from the reference shape to that edge, traverse it, and return along the tree. Record the resulting colored permutation and an executable move sequence. These loops generate the reference shape's isotropy subgroup. Use constructive permutation-group methods to test membership and factor the residual state, retaining move witnesses.

The second approach develops the original README's proposal and may solve puzzles whose full colored graphs are much too large to store. It requires a complete shape component for a completeness claim; its solutions need not be shortest. A tool such as GAP can help validate subgroup computations before deciding which operations belong in Rust. [GAP permutation-group documentation](https://gap-system.github.io/gap/doc/ref/chap43_mj.html).

Ordinary-cube solutions are not automatically legal on a bandaged cube. Relaxed ordinary-cube distances can supply lower bounds, but restricting a conventional two-phase solver does not automatically give a complete bandaged solver. Move rewrites and pruning also require legality proofs because replacing a word can change where it is executable. [Ordinary two-phase algorithm](https://kociemba.org/math/twophase.htm).

Completion criterion: replayable colored solutions for the named fixtures and generated legal scrambles, with documented metric and optimality guarantees. Distinguish solved, proven unreachable, and search stopped by a resource limit.

### Fifth milestone Enumerate and classify the chosen family

This can proceed in parallel with colored solving once the engine is verified. Reconstruct the old split rules, seeds, and treatment of implicit bonds. Implement a transparent baseline generator and deterministic symmetry canonicalization before canonical augmentation, parallel workers, or distributed runs.

Avoid scanning all `2^48` raw shell-bond subsets. Generate admitted partitions directly, normalize their representations, and prove that every intended class is reached. For a wider connected-block family, design a separate generator with connectivity and duplicate prevention built into its construction.

Publish counts at each reduction step: generated partitions, geometric rotation classes, reachable motion classes, and any behavioral quotient. Retain representatives and transformation witnesses. Small exhaustive instances and independent algorithms should check completeness and deduplication.

The old `enumerate_analytic()` currently evaluates to 6,473,251 while its comment records 6,399,617. Neither should be treated as a verified final class count. Recover and reconcile the derivation before adopting a golden total. [Analytic function](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/cubes/enumerator.py#L55).

Completion criterion: a reproducible enumeration for a precisely declared family and equivalence, with evidence of completeness, stable identifiers, and resource measurements. Expanding to all connected bandages is a further milestone whose feasibility needs measurement.

### Sixth milestone Human solving methods and visual exploration

Turn the existing feature-chain experiments into an explicit strategy system. Candidate features include recognizable block locations, available faces, restored bandage relations, and short algorithms with useful effects. Seek a small number of stages with simple recognition, limited branching, and short worst-case routes to the next stage.

For each proposed rule, record its recognition condition, legal setup, action, intended progress, and exceptions. Specify whether earlier features must hold throughout an algorithm or only at stage boundaries. Measure coverage and worst-case distances exhaustively on tractable shape components; distinguish these guarantees from sampled colored-state evidence. A geometric stage need not preserve an algebraic subgroup, so keep feature chains and stabilizer chains distinct.

Mine useful loops, conjugates, and commutators with small colored effects. Present readable algorithms and recognition examples. Computer-generated candidates become human methods only after review of memorability and actual solving experience; shortest paths alone do not measure either.

Build an interactive viewer showing colors and bandages, enabled turns, the blocking block for a disabled turn, and replayable solutions. Link it to shape graphs, distance layers, strategy stages, difficult-case galleries, and filtered views of the puzzle atlas. Aggregate large graphs and posets instead of attempting to draw every vertex at once. Support static exports for research and sharing.

Completion criterion: at least one documented method for a named puzzle, with checked rules, representative difficult cases, explicit evidence limits, and visual explanations.

### Seventh milestone The poset and algebraic atlas

For labeled partitions of the same reference pieces, define `P ≤ Q` when every block of `P` lies inside a block of `Q`: `Q` adds bandaging. This refinement order is a precise starting point. With the same move model and reference colored state, every `Q`-legal word is `P`-legal, so the reachable colored states for `Q` are contained in those for `P`.

Build cover relations, symmetry-orbit comparisons, mobility statistics, shape-component sizes, loop-subgroup orders, and strategy complexity. On rotation classes, define comparability using a rotation that makes representatives comparable; comparing independently chosen canonical encodings alone is insufficient. Establish which meet and join operations survive the chosen geometric restrictions and quotient.

Do not infer that unlabeled shape graphs or their isotropy groups simply nest. For example, a fully glued U layer returns to its own shape under `U`; refining it to one glued corner-edge pair allows `U` but changes that pair's footprint. Coarsening maps on shape quotients also require enough retained block correspondence to be well-defined.

Investigate implicit bonds as a closure operation separately from geometric normalization. Prove extensivity, monotonicity, idempotence, and preservation of legal behavior before using closure to merge enumeration classes. Validate it against colored transports and loops, since revisiting the same shape can conceal a different cubie arrangement.

The groupoid offers a useful counting result: for a complete reachable shape component in a fixed frame, with a colored representation on which the ambient permutation action has trivial stabilizer at the solved state, the number of reachable colored states equals the number of shapes times the order of the reference isotropy group. Check these hypotheses before applying the formula to symmetry quotients or variants with ignored markings.

Completion criterion: a browsable atlas with rigorously defined relations and invariants, accompanied by proofs or clearly labeled experimental conjectures.

### Eighth milestone General bandaged puzzles and Python access

Extract the common interface after the 3×3 implementation works: a state key, invertible generators with legal domains, transition and inverse operations, target predicates, symmetry actions, and optional permutation labels. Make search reusable without forcing every puzzle into the 3×3 representation.

An abstract permutation group alone is insufficient to define bandaging. We also need the physically available generators, their geometric actions, and which rigid pieces can undergo each action together. A move's affected region can include pieces fixed by its position permutation: the U center stays in its slot but belongs to the rotating U layer. For more complicated mechanisms, legality may depend on the whole trajectory rather than the endpoints.

A general model is a graph of legal invertible transitions, together with their permutation or geometric actions. Its legal paths, modulo cancellation of a move followed by its inverse, form a groupoid; when appropriate, further identify paths with the same source, target, and induced permutation. Alternatively, the generators act as partial bijections and generate an inverse monoid. Two words with the same ambient permutation can have different legal domains, so a partial action of the whole ambient group is not automatic. Isotropy groups at different shapes are conjugate within a connected component.

Test the abstraction on another cube size with different center or inner-layer behavior before treating it as settled. Add Python bindings when the library interface is stable enough for notebooks and external experimentation. These two follow-on tasks can proceed independently.

Completion criterion: a second puzzle model uses the shared search and analysis machinery, and Python users can run substantive operations through the Rust core.

## Proposed immediate scope

The first implementation in `v2/` now provides connected partitions of the legacy 27-cell grid, 54-bond shape encodings, complete ordinary colored cube states, and checked outer-face moves. Tests reproduce the three legacy components and check independent sticker behavior. Initial measurements select the portable sparse layout for the default engine; the straightforward layout and tuning candidate remain available for comparisons. Larger workloads and future puzzle models can refine that choice. Full enumeration, solver sophistication, and the visual atlas follow from this foundation.
