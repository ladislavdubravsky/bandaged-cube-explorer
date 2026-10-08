# Bandaged cube explorer roadmap

Roadmap updated 8 October 2026. The Rust model and move engine, Python research interface, and initial shape tools are implemented in [v2](../v2/README.md). Milestone four now supplies validated colored input, colored exploration, exact direct BFS and bidirectional BFS for tractable cases, a general GAP loop-factorization baseline, exact reference-block actions with decorated cycle notation, and an opt-in solver for block placement and abelian kernel correction. Larger memory-conscious exact searches and improved loop-solving methods remain followups. Milestone five's default shell enumeration is complete, with 7,073 behavioral classes, or **4,857** after identifying mirror pairs and excluding permanently frozen or one-axis puzzles. Its APIs support exact partition generation/counting, proper rotations, motion classification, and optional implicit-bond closure; an atlas postprocessor handles mirrors and named mobility filters. See [the enumeration investigation](enumeration.md) for definitions, proofs, old-code reconciliation, and measured results. Reusable human solving methods belong to milestone six; broader puzzle mechanics remain later work.

The replacement uses a Rust computational library with a Python research interface and a thin command-line application, developed alongside the existing Python project. Build shape exploration, colored solving, and enumeration on a precise model and verified move engine; use their results to develop human solving methods and an atlas of bandaged puzzles. Keep the general theory in view while making the first implementation specific to 3×3 cubes.

## Preserve the existing project

Leave `bce/`, `puzzles/`, the example scripts, images, and the existing README untouched. The new implementation lives in `v2/`, with its own build configuration and documentation.

The old project remains a working reference until the replacement reproduces its useful behavior, imports its puzzle records, supplies better documentation and visualizations, and solves colored puzzles. Migration should be a later, explicit decision. When an old behavior is incorrect or ambiguous, document the difference rather than reproduce it silently or modify the reference.

The existing design has substantial value:

- The [README](../README.md) already models legal transports as a groupoid over uncolored bandage shapes, and proposes restoring shape before solving the remaining sticker permutation.
- [The core](../bce/core.py) provides shape normalization, move legality, reachable-shape exploration, and shortest paths.
- [The examples](../usage.py) develop recognizable feature chains, measure distances between stages, and display difficult cases. These are a useful starting point for human solving methods.
- [The renderer](../bce/graphics.py) and [puzzle database](../puzzles/database.csv) supply galleries, transparent views, and three named fixtures.

The replacement tracks complete corner and edge identities and orientations. It does not carry forward the old block-label permutation mode or incorrect move directions: all v2 interfaces use standard Singmaster notation.

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

Python is the primary research interface beginning in milestone three. A separate PyO3 binding layer, packaged with maturin, exposes the Rust implementation without making the core depend on Python. Accept ordinary Python lists for bandage definitions; keep experiments, notebook inspection, and plotting convenient in Python. Expose substantial operations such as exploring a component or solving a batch, so Python calls do not dominate computation. [PyO3 documentation](https://pyo3.rs/), [maturin documentation](https://www.maturin.rs/).

Interactive graphics can use a browser frontend, with a native service or eventually a WebAssembly build of the core. Select that interface after the move engine and export formats exist.

## Define the objects and equivalences

Separate three concepts in both the mathematics and API:

1. A **bandage specification** says which identified cubies are fused in a reference configuration, together with the puzzle's move and mechanical conventions.
2. A **colored state** records where the identified cubies are and how they are oriented.
3. A **bandage shape** records the occupied footprints of the blocks after forgetting colors and arbitrary block names. It is a projection of a colored state.

The specification stays fixed while the state changes. Two different colored states can project to the same shape and still need very different solutions.

### Decide what all bandaged cubes includes

The explorer documents cuboid blocks on a 27-cell lattice, including a virtual core. The [enumerator's definitions](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/README.md) narrow the target further to partitions obtained by repeatedly cutting a block with a face plane, excluding size-two blocks containing the core. A broader shell-cubie model would permit arbitrary connected groups of the 26 shell cubies; physical realizability still depends on the declared mechanics.

The first enumeration target is now all partitions into connected cuboid shell footprints, allowing a box with its virtual core omitted. Invisible core bonds are excluded by default; an explicit parameter admits full 27-cell cuboids. Strict cuboids with singleton core are a separate comparison family, since they would exclude a seven-shell-cell corner 2×2×2 block. The old cut-generated family is retained only as a research comparison. Hull completion preserves every legal outer-face word, proving that every connected bandage specification has a representative in the cuboid family for behavioral equivalence. It does not identify their raw geometric specifications.

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

Use the 24 proper rotations for the baseline geometric enumeration and identify legal-motion components up to those rotations for puzzle classification. Optional dynamic implicit closure additionally identifies behaviorally redundant specifications. The requested filtered atlas adds reflection equivalence and excludes components whose union of turnable face axes has size at most one; the complete component is checked, retaining puzzles that later unlock another axis. Preserve the original atlas and record these policies explicitly in each export. The old C++ `filter_rotations` also explores reachable face turns, so its result is a quotient by motion as well as rotation. [Filtering implementation](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/cubes/main.cpp#L66).

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

Provide a documented Python library for defining and importing puzzles, inspecting legal moves, replaying legal moves with full colors, exploring a reachable shape component, finding a shortest shape solution, and exporting results. Accept inline 27-cell lists, named fixtures, and versioned puzzle records. Keep a thin CLI for repeatable batch operations. Use queues and compact values, dense vertex IDs, and lazy successor generation when storing a graph is unnecessary.

Retain distinct labeled edges and self-loops, with their induced colored permutations. The ordinary unbandaged cube has one shape vertex, but its face turns still generate the entire cube group. Collapsing those actions would destroy the information needed for colored solving.

Support explicit QTM and HTM shape paths. Explore complete components by default. Any resource limits must be explicitly requested, with clear reporting of incomplete exploration; add cancellation and checkpointing when needed. Begin with versioned puzzle records and deterministic exports recording the model, metric, symmetry convention, and completeness status. Save colored states through a reference specification and a legal move witness until arbitrary colored import is validated in milestone four.

Completion criterion: Python users can define a puzzle in a list, replay moves, inspect its shapes and legal moves, explore it, obtain replayable shortest shape solutions, render basic shapes or galleries, and save reproducible results. Named legacy fixtures retain their verified counts and QTM distances. Feature chains, distance-layer experiments, and human strategy analysis belong to milestone six.

### Fourth milestone Solve colored puzzles

Direct exact search and colored exploration implemented 7 October 2026. Colored solving is not a dependency of milestone five; the complete labeled shape graph supplies all transports needed to compute implicit adjacent bonds.

Distinguish two solving outputs:

- A **scramble solution** is a replayable legal move sequence taking one given colored state to the target.
- A **puzzle solution** is a reusable collection of algorithms together with recognition and application rules that solve any reachable colored scramble of that puzzle in the declared component. A generating set alone does not supply those rules.

Milestone four first delivers scramble solutions and a complete computational procedure for obtaining them. Developing a puzzle solution that a person can memorize and apply belongs to milestone six.

The Rust core and Python API accept cubie arrays or standard 54-facelet URFDLB input. Import separately checks ordinary cube invariants and rigid-block compatibility, including orientations, without assuming reachability. Imported states persist in version-2 puzzle records; existing version-1 replay records remain supported. Fixed-frame colored exploration retains all directed unit-cost actions and explicitly marks resource-limited graphs incomplete. Direct BFS and bidirectional BFS return replayable shortest QTM/HTM solutions, proven unreachability after exhaustion, or an explicit state/depth cutoff. Limits are opt-in; the bidirectional state cap counts records on both sides. Python and CLI expose the same search results. The general GAP loop-factorization baseline is also implemented; larger memory-conscious exact searches remain pending.

Accept colored cubie or sticker input together with bandage membership. Check ordinary cube validity separately from reachability under the bandaging: a valid ordinary cube configuration may still be unreachable for this puzzle. Use scrambles generated by legal moves as reliable positive fixtures.

Develop two complementary approaches:

- **Direct constrained search:** exact BFS and bidirectional BFS are implemented for tractable cases, generating only currently legal turns and retaining full cubie identities and orientations. Next add IDA* or another suitable memory-conscious search for larger ones. Combine exact shape distance and relaxed ordinary-cube pattern distances using a maximum; use sums only with a proof of admissibility or a valid cost partition.
- **Shape restoration followed by loop solving:** complete loop extraction, GAP group analysis, and the first general scramble-factorization solver are implemented. The Rust engine chooses a spanning tree in the complete labeled QTM shape graph. Each remaining edge gives a legal root loop by tree transport, edge traversal, and inverse return transport. It retains 48-sticker permutations and executable witnesses through shared tree paths, removing identity actions and duplicates up to inverse. GAP reduces the generators by subgroup membership while retaining original loop witnesses and computes the exact isotropy-group order. Multiplying that order by the complete fixed-frame shape count gives the exact colored-component size. The solver restores an imported scramble's shape, tests residual membership, and factors the inverse through witnessed loops without enumerating colored states. Expanded solutions are legally replay-checked. Python and CLI expose structured loop expressions and deterministic records; GAP is optional for extraction.

The second approach develops the original README's proposal and may solve puzzles whose full colored graphs are much too large to store. It requires a complete shape component for a completeness claim; its solutions need not be shortest. GAP is the external algebra backend; Rust owns shape exploration, permutation construction, and legal loop witnesses. [GAP permutation-group documentation](https://gap-system.github.io/gap/doc/ref/chap43_mj.html).

For the first loop-factorization solver, when choices are otherwise comparable in correctness and practicality, prefer fewer distinct base algorithms within a scramble solution over fewer turns. Reuse a stable algorithm library across scrambles of the same puzzle; count an algorithm and its inverse together. Retain algorithm references and structured expressions such as repetitions, powers, commutators, and conjugations alongside expanded executable moves. Physical move length remains useful to report and as a secondary preference. Existing exact-search APIs retain their shortest-path guarantees; dedicated human-memory optimization belongs to milestone six.

The baseline uses a stable reduced library of original loops and greedily chooses a smaller candidate subgroup containing each scramble's residual permutation. It does not prove a minimum algorithm count. Results retain ordered generator references and signed powers, the used algorithm witnesses, and physical move cost. An optional expansion limit preserves the compact expression while reporting `limit_reached`; exact membership failure proves `unreachable`.

Exact reference-block actions and one-line decorated cycles are implemented as the first block-action delivery. Inventories use stable reference member-cell identities, distinguish singleton corners, edges, and centers without changing signature type `111`, and retain actual noncuboid footprints and core bonds. Each witnessed loop exposes exact destinations, observable proper rotations, and per-source modular phases in deterministic shared frames; composition, inverses, and powers agree with the authoritative 48-sticker action. Decorated one-element cycles retain in-place twists, flips, and symmetric-block rotations; order-four half turns use `++`. Both analysis notebooks display inventories and compact algorithm tables with physical turn sequences, exact block actions, HTM lengths, and affected-block counts. The [block-action guide](block-actions.md) documents the API, frame conventions, and exports. An opt-in quotient/kernel solver now uses these exact actions for block placement followed by orientation correction.

Block quotient and abelian correction are implemented as the opt-in `quotient_kernel` factorization strategy; the original `sticker` strategy remains the default. The solver factors the block permutation through witnessed loop generators, lifts the same word, then corrects the residual using a witnessed independent cyclic basis of the subgroup fixing every footprint. GAP computes exact isotropy, quotient, and kernel orders with `|H| = |P| * |K|`, and establishes exact reachability through quotient membership followed by residual kernel membership, verifying the lifted full action. In the current six-outer-face model the kernel is abelian and can include order-four rotations of symmetric blocks; it is not limited to ordinary corner twists and edge flips. The implementation retains actual subgroup constraints and executable witnesses without assuming independent block coordinates or a split extension. Results expose separate placement and kernel expressions, plus the complete expression in original loop IDs for compatibility. Both notebooks show the decomposition and legally replay-checked kernel basis. Exact quotient tables, further algorithm discovery, recognition rules, and a memorable reusable puzzle solution remain followups; human application rules belong to milestone six.

Bounded algorithm discovery and dual solution views are implemented as opt-in research tools. Every legal base loop is reusable, without a turn threshold. Discovery retains exact trees for powers, commutators, conjugates, nested constructions, and transfers through actual reference-bandage symmetries. Roots with no nonidentity symmetry supply no such transfers; regrips restore the frame and expand to legal face-only witnesses without adding HTM moves. Shortest-found ranking favors physical length. Structured scores compare total affected-block count, then the largest constituent application's affected-block count, shared memory and description cost, and finally turns. Equal-effect solutions therefore favor localized intermediate applications. Inverses or opaque names do not make a long description easier. Bounded searches and enriched GAP factorizations compare both solve views with the verified baseline. Both notebooks show compact candidate rankings and solution options, with explicit budgets and legal replay checks. These are heuristic comparisons without a global shortest-path or human-memorability proof. Kernel algorithms commute with one another, but the abelian kernel need not be central in the full isotropy group, so conjugation by placement loops can change their effect. Exact precomputed `P` tables and human recognition/application rules remain pending.

Ordinary-cube solutions are not automatically legal on a bandaged cube. Relaxed ordinary-cube distances can supply lower bounds, but restricting a conventional two-phase solver does not automatically give a complete bandaged solver. Move rewrites and pruning also require legality proofs because replacing a word can change where it is executable. [Ordinary two-phase algorithm](https://kociemba.org/math/twophase.htm).

Completion criterion: replayable colored solutions for the named fixtures and generated legal scrambles, with documented metric and optimality guarantees. Distinguish solved, proven unreachable, and search stopped by a resource limit.

### Fifth milestone Enumerate and classify the chosen family

This proceeds before colored solving on the verified engine. Implemented in `v2`: exact-cover counting and streaming generation; all 24 proper rotations with stable AxisMajor canonical keys; complete seed/component classification; and optional exact implicit adjacent-bond closure using backward separation propagation through every labeled arc and self-loop. Python and Rust interfaces expose core-bond and closure parameters. Explicit resource limits report partial coverage and never credit incomplete components.

The default shell run exhausted all 312,238,908 partitions: 13,016,719 proper-
rotation classes, 3,498,007 motion/rotation classes, and 7,073 classes with
implicit closure. It took 13 minutes 43 seconds and 308.35 MiB peak RSS.
[All behavioral representatives](../v2/enumeration-results/README.md) are retained
with originating seeds, stable IDs, metadata, and independent validation. The
core-inclusive parameter is implemented; its complete class scan is a separate
run rather than an earlier-milestone dependency.

The mirror/mobility postprocessor checks every closed component and matches
mirror partners through legal motion, rather than only comparing stored
reference shapes. Its complete run visited 7,858,798 vertices in 33.687 seconds:
2,647 classes are equivalent to their mirrors and 2,213 mirror pairs merge,
giving 4,860 classes. The agreed dead-end filter removes the fused shell and
two slab puzzles, leaving **4,857**. The filtered atlas, full partner map,
counts for alternative mobility policies, and file checksums are retained.

Block inventories are now stored in a derived SQLite atlas with stable class
IDs, all four symmetry/mobility cohorts, and types distinguishing dimensions and
center/core placement: Clock/Pair, BigClock, 221Core, 321Core, and 331Core.
There are 1,735 block signatures in the full atlas and 1,732 in the filtered
atlas. All singleton cubies remain 111; each signature implies their remaining
count. The optional core-enabled model also admits 211Core and 311Core. The
[block-signature guide](block-signatures.md) and
[exploration notebook](../v2/examples/PuzzleSignatures.ipynb) provide queries,
complete signature counts, and galleries.

Avoid scanning all `2^48` raw shell-bond subsets. Generate admitted partitions directly by choosing the block covering the first uncovered cell. Hull completion proves behavioral representative coverage for all connected outer-face bandages, and the exact-cover recurrence proves duplicate-free coverage of admitted partitions. Independent Bell-partition, layer-transfer, and Burnside calculations reproduce the counts. Default shell partitions number 312,238,908, or 13,016,719 under proper rotations before legal turns; core-inclusive cuboids number 701,898,882, or 29,255,694 under rotations.

Publish counts at each reduction step: generated partitions, geometric rotation classes, reachable motion classes, and any behavioral quotient. Retain representatives and transformation witnesses. Small exhaustive instances and independent algorithms should check completeness and deduplication.

The old `enumerate_analytic()` evaluates to 6,473,251 while its comment records 6,399,617. It mixes selected first cuts and special core-bar treatment, and performs no dynamic closure or puzzle-class quotient. An exact repaired inclusion-exclusion recurrence counts all guillotine partitions (369,362,176 full-grid partitions), still fewer than all cuboid covers. The [enumeration investigation](enumeration.md) and two standalone `v2/research/` checks preserve the derivations. The referenced forum post denied access; the public code was audited directly.

Completion criterion: a reproducible enumeration for a precisely declared family and equivalence, with evidence of completeness, stable identifiers, and resource measurements. Behavioral representatives of all connected outer-face bandages are covered by the hull argument; enumerating their distinct raw noncuboid geometries is a separate larger family.

### Sixth milestone Human solving methods and visual exploration

Develop reusable human **puzzle solutions**: a small algorithm repertoire and explicit recognition and application rules covering every reachable colored scramble in the declared component. Optimize the amount of information a person must remember, including both move sequences and decision rules. Prefer repeated use of a few base algorithms and compressible descriptions through powers, commutators, and conjugations. Move length is a reported property, not the optimization objective of this milestone.

Turn the existing feature-chain and distance-layer experiments into an explicit strategy system. Replace all-pairs distance calculations for feature stages with reverse multi-source BFS from each target set. Candidate features include recognizable block locations, available faces, restored bandage relations, and reusable algorithms with useful effects. Seek a small number of stages with simple recognition, limited branching, and structured actions that guarantee progress.

For each proposed rule, record its recognition condition, legal setup, action, intended progress, and exceptions. Specify whether earlier features must hold throughout an algorithm or only at stage boundaries. Measure coverage and worst-case distances exhaustively on tractable shape components; distinguish these guarantees from sampled colored-state evidence. A geometric stage need not preserve an algebraic subgroup, so keep feature chains and stabilizer chains distinct.

The initial bounded loop-discovery tools now retain short witnesses, powers, conjugates, commutators, and nested expression trees, with shortest-found and structured views. Extend these candidates into useful algorithms with small colored effects. Present readable algorithm definitions, their reusable compositions, and recognition examples. Assess the shared repertoire across scrambles, including how much unstructured move information must be memorized. Computer-generated candidates become human methods only after review of memorability and actual solving experience; shortest paths alone do not measure either.

Build an interactive viewer showing colors and bandages, enabled turns, the blocking block for a disabled turn, and replayable solutions. Link it to shape graphs, distance layers, strategy stages, difficult-case galleries, and filtered views of the puzzle atlas. Aggregate large graphs and posets instead of attempting to draw every vertex at once. Support static exports for research and sharing.

Completion criterion: at least one documented reusable method for a named puzzle, with legal application rules, a coverage and progress proof or complete exhaustive validation for every reachable colored scramble, representative difficult cases, and visual explanations. Label methods supported only by samples as experimental and state their evidence limits. Document the required algorithm repertoire and recognition rules.

### Seventh milestone The poset and algebraic atlas

For labeled partitions of the same reference pieces, define `P ≤ Q` when every block of `P` lies inside a block of `Q`: `Q` adds bandaging. This refinement order is a precise starting point. With the same move model and reference colored state, every `Q`-legal word is `P`-legal, so the reachable colored states for `Q` are contained in those for `P`.

Build cover relations, symmetry-orbit comparisons, mobility statistics, shape-component sizes, loop-subgroup orders, and strategy complexity. On rotation classes, define comparability using a rotation that makes representatives comparable; comparing independently chosen canonical encodings alone is insufficient. Establish which meet and join operations survive the chosen geometric restrictions and quotient.

Do not infer that unlabeled shape graphs or their isotropy groups simply nest. For example, a fully glued U layer returns to its own shape under `U`; refining it to one glued corner-edge pair allows `U` but changes that pair's footprint. Coarsening maps on shape quotients also require enough retained block correspondence to be well-defined.

Implicit adjacent bonds are now implemented in milestone five separately from geometric normalization. The complete labeled shape graph supports exact separation tracking through every transport and loop; its surviving adjacencies preserve every legal word. Tests cover extensivity, idempotence, projection, independent identified-position searches, and an old DFS counterexample. Monotonicity holds for partitions of the same identified reference cubies because coarsening shrinks the legal-word language. Nonadjacent co-motion and other mechanical models remain separate questions.

The groupoid offers a useful counting result: for a complete reachable shape component in a fixed frame, with a colored representation on which the ambient permutation action has trivial stabilizer at the solved state, the number of reachable colored states equals the number of shapes times the order of the reference isotropy group. Check these hypotheses before applying the formula to symmetry quotients or variants with ignored markings.

Completion criterion: a browsable atlas with rigorously defined relations and invariants, accompanied by proofs or clearly labeled experimental conjectures.

### Eighth milestone General bandaged puzzles and Python access

Extract the common interface after the 3×3 implementation works: a state key, invertible generators with legal domains, transition and inverse operations, target predicates, symmetry actions, and optional permutation labels. Make search reusable without forcing every puzzle into the 3×3 representation.

An abstract permutation group alone is insufficient to define bandaging. We also need the physically available generators, their geometric actions, and which rigid pieces can undergo each action together. A move's affected region can include pieces fixed by its position permutation: the U center stays in its slot but belongs to the rotating U layer. For more complicated mechanisms, legality may depend on the whole trajectory rather than the endpoints.

A general model is a graph of legal invertible transitions, together with their permutation or geometric actions. Its legal paths, modulo cancellation of a move followed by its inverse, form a groupoid; when appropriate, further identify paths with the same source, target, and induced permutation. Alternatively, the generators act as partial bijections and generate an inverse monoid. Two words with the same ambient permutation can have different legal domains, so a partial action of the whole ambient group is not automatic. Isotropy groups at different shapes are conjugate within a connected component.

Test the abstraction on another cube size with different center or inner-layer behavior before treating it as settled. Extend the Python research interface to the shared model when it is useful for external experimentation.

Completion criterion: a second puzzle model uses the shared search and analysis machinery and is accessible through the Python interface.

## Proposed immediate scope

The implementation in `v2/` provides connected partitions, 54-bond shape encodings, validated colored cube input, checked outer-face moves, exact colored exploration and direct solving, a general GAP loop-factorization solver, Python research tools, and an exact enumeration baseline. Milestone four's direct-search approach and general loop-solving baseline are implemented, and the default milestone-five shell run is complete; its settings exclude invisible bonds, include proper rotations and legal motion, and optionally merge every implicit adjacent bond. Enumeration research, the full behavioral atlas, and resource measurements are recorded separately from the old project. Checkpoint resume, parallelization, core-inclusive class enumeration, human strategies, larger memory-conscious exact searches, improved loop-solving methods, and visual atlas tools can extend this foundation.
