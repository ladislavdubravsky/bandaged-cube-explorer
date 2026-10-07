# Colourless puzzle enumeration

6 October 2026. Milestone four (colored solving) is deferred. The verified move engine and shape explorer from milestones two and three are sufficient for enumeration; no earlier implementation blocker was found.

The exhaustive default shell run is complete: **3,498,007** classes under legal
turns and proper rotations, or **7,073** after merging implicit bonds. It covered
all 312,238,908 seeds in **822.819 seconds** (13 minutes 43 seconds), with
**308.35 MiB** peak resident memory. All behavioral representatives are saved in
[the atlas](../v2/enumeration-results/README.md). Core-inclusive class enumeration
is available through the same APIs; only its partition/rotation counts have
been computed in this session.

Identifying mirror pairs and excluding permanently frozen or one-axis puzzles,
as requested, reduces the behavioral atlas to **4,857** classes. This uses the
same shell model and implicit closure. The original 7,073-class atlas and the
filtered atlas are both retained.

## Objects and equivalences

A reference **shape** is a partition of physical cubie positions into connected rigid blocks, forgetting colors and arbitrary block names. By default the domain consists of the 26 shell cells; cell 13 remains an independent ghost core in the existing engine. Generated blocks are rectangular bounding boxes intersected with this domain. A corner 2×2×2 block therefore contains seven shell cells, without an invisible core bond.

Two seeds belong to the same **motion class** when legal outer-face turns and any of the 24 proper whole-cube rotations connect them. Rotations change the frame and rename the move faces; they need not be executable as face turns. All eight corner placements of a 2×2×2 block are equivalent. The baseline atlas keeps mirror images separate unless turns and proper rotations already identify them. The filtered atlas additionally identifies reflections, giving all 48 spatial cube symmetries.

The optional **behavioral quotient** adds every implicit physical adjacency: adjacent cubie pairs that no legal move word ever splits between a moving layer and its complement. Geometrically different specifications can then have exactly the same legal words and cubie transports. This is distinct from abstract unlabeled graph isomorphism, which could merge unrelated geometries or move actions.

The scope is the six outer faces of the current fixed-center 3×3 model. Slices, wide turns, marked-center spin, nonadjacent mechanical links, and other mechanisms need separate definitions.

## Exact spatial counts

These are our derived counts, independently reproduced in Rust and standard-library Python. They are **before legal-turn equivalence and dynamic implicit closure**.

| Model | Block footprints | Placements | Spatial partitions | Proper-rotation classes |
| --- | --- | ---: | ---: | ---: |
| `shell-cuboids` (default) | Connected boxes with the core omitted | 206 | 312,238,908 | 13,016,719 |
| `full-cuboids` | Boxes on all 27 cells; core bonds allowed | 216 | 701,898,882 | 29,255,694 |
| `strict-core-singleton-cuboids` (comparison) | Boxes avoiding core, plus singleton core | 153 | 170,204,427 | 7,095,461 |

Strict singleton-core cuboids exclude the requested seven-shell-cell corner block; that is why the first and third models differ. Starting with `binomial(4,2)^3 = 216` full boxes, the shell model removes the empty core-only box, deduplicates six core-center dominoes projecting to existing singleton centers, and rejects three rods projecting to disconnected opposite-center pairs. This leaves 206 footprints. Allowing those disconnected footprints would give 384,240,508 spatial partitions, outside the connected-bandage model.

For a remaining-cell mask `R`, set `F(0)=1`. Choose the least uncovered cell `c`, then use

```text
F(R) = sum F(R minus B)
       over admitted blocks B containing c and entirely contained in R.
```

Each partition has exactly one block covering `c`, so this counts or emits every partition once. Memoization counts hundreds of millions of partitions using just 21,933 nonempty shell masks. Release Rust counts, including rotation counts, take approximately 3–8 ms here. Counting time is distinct from emitting and classifying all partitions.

For Burnside counting, a partition fixed by a rotation contains entire orbits of block placements. Reject overlapping placement orbits; treat each remaining orbit's union as an exact-cover tile. Different orbits sharing a union retain multiplicity. Average the 24 fixed-partition counts. Simply dividing by 24 would miss symmetric partitions.

[check_partition_counts.py](../v2/research/check_partition_counts.py) reproduces small exhaustive set-partition checks, exact-cover counts, rotations, and an independent planar layer-transfer count. Enumerate the 322 planar 3×3 tilings; between adjacent layers `A,B` each matching rectangle can independently join, giving `W(A,B)=2^|A∩B|`. The three-layer total is `sum_B (sum_A W(A,B))^2 = 701,898,882`. Restricting the middle center to singleton and forbidding vertical joins of that singleton yields 170,204,427.

The [Blanco–Dougherty-Bliss–Ter-Saakov–Zeilberger paper](https://sites.math.rutgers.edu/~zeilberg/mamarim/mamarimPDF/recto.pdf) independently publishes the planar count 322 and related DP methods; it does not publish our 3D counts. Literature counting block-dimension multisets, partitions into cubes, or recursive fixed-arity subdivisions studies different objects. For example [Au–Bagherzadeh–Bremner](https://cs.uwaterloo.ca/journals/JIS/VOL23/Au/au3.html) counts recursive subdivisions rather than all spatial grid covers.

## Why cuboid representatives suffice for behavior

This is a derived proof for the declared outer-face move model. For a connected block `S`, let `H(S)` be its axis-aligned bounding box intersected with the physical domain. For every outer layer `L`, `S` is entirely in `L` exactly when `H(S)` is, and `S` is disjoint from `L` exactly when `H(S)` is. Coordinate intervals cannot acquire a new extreme coordinate absent from the original block.

Filling the hull therefore preserves legality. Every block touched by that hull has the same moved/fixed status under any currently legal turn, so merge the touched blocks, fill the new hull, and repeat. A legal turn moves a hull wholly or leaves it fixed, and the hull rotates to the hull of the rotated block. Hull filling and induced merging consequently commute with every legal turn. Induction over move words proves that the original and completed specifications permit exactly the same legal words and original-cubie transports.

Shell hulls remain connected: the only disconnected box-minus-core footprints are the opposite-center rods, which cannot be hulls of connected shell blocks. The final partition consists of admitted box footprints.

Thus every connected specification has a behavior-equivalent cuboid representative. This proves completeness for the **behavioral target**; literal raw noncuboid specifications are still distinct geometric objects. The cuboid family remains too fine because globally constrained cuboids can move together implicitly.

## Exact dynamic implicit closure

The existing bond encoding already saturates adjacency inside explicit blocks. That removes multiple glue-edge descriptions of one partition, but does not find dynamically inseparable distinct blocks.

Explore the entire fixed-frame shape graph, retaining labeled arcs and self-loops. Conceptually track `(shape, adjacent pair)`. Mark pairs separable if any legal face includes exactly one endpoint, then pull those marks backwards through every move's endpoint transport to a fixed point. The unmarked pairs are implicit. The implementation propagates one 54-bit mask per vertex; it adds only the 48 shell adjacencies by default, or all 54 when core bonds are enabled. It checks completeness and legal clockwise-arc coverage before drawing conclusions. Clockwise arcs suffice because three clockwise turns give an inverse; QTM and HTM yield the same closure.

Loops matter: `114 / 254 / 233` is invariant under a quarter turn after relabeling its four dominoes. Its one-vertex colorless graph still moves identified cubies, and closure fuses the whole face. The unbandaged cube also has one shape vertex, but no implicit bonds. Another regression supplies a legal `U U U B B U` separation witness for a pair incorrectly declared implicit by the old one-pass DFS in a five-shape cuboid puzzle with singleton core. Tests compare against independent identified-position search and verify projection, idempotence, legal domains, core modes, and the three legacy components.

Adding survivors preserves every executable word: all old words move each added pair together, and adding constraints cannot create new words. For connected specifications in a common reference frame, equal admitted-adjacency closures are equivalent to identical legal word languages: any explicit edge of either specification must be a surviving edge of the other. Disconnected co-moving sets are not introduced as new nonadjacent physical bonds.

## Enumeration and measurements

The algorithm follows the proposed seed/component approach. Stream exact covers; skip seeds already in an explored raw motion/rotation class; otherwise explore their complete fixed-frame component. Optionally close its vertices under implicit bonds, then canonicalize the resulting shapes under proper rotations. The closure image is itself a complete component; overlap with an already known image identifies the same class. Use the minimum AxisMajor key over the whole image as representative.

Keys are independent of the optimized move layout, and identify classes together with their model/equivalence metadata. Exports record the core policy, closure policy, symmetry, completeness, coverage, representative labels, and originating seed. Existing fixed-frame puzzle/graph persistence keeps its schema. Rotation canonicalization supplies a rotation witness in Rust; originating seeds let complete move witnesses be reconstructed through the graph explorer.

Explicit seed or component limits report `complete=False`. Partial components receive no class credit or visited keys. `expanded_shape_vertices` counts completed components only. The baseline retains global visited keys and representatives in memory. Checkpoint resume and parallel classification remain performance extensions.

Initial shell measurements on an Intel i7-7500U:

| Work | Seeds | Raw components | Expanded vertices | Discovered classes | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Generate only | 100,000 | — | — | — | 0.052 |
| Legal turns + proper rotations | 100,000 | 9,358 | 2,044,119 | 9,358 | 9.288 |
| Also merge implicit bonds | 100,000 | 9,358 | 2,044,119 | 1,540 | 16.477 |

These prefixes are incomplete. They discover 1,318,838 raw rotation keys (about 10% of the complete 13,016,719) from only 0.032% of the spatial seeds. Prefix order is biased and future seeds often hit already explored components. Linear extrapolation is therefore misleading. Pure generation extrapolates to about 163 seconds; classification adds symmetry, hashing, component search, and closure. See [the benchmark record](../v2/benchmark-results/enumeration.md) for complete-run evidence.

Exact completion counts also provide zero-based unranking and uniform spatial rank sampling. The CLI `sample` uses fixed-seed SplitMix64 with rejection to avoid modulo bias, sampling with replacement. It measures typical spatial-seed workloads, not a uniform distribution over puzzle classes or proof of full coverage.

## Old analytic function and an exact repair

The function is in the public [bandaged-cubes-enumerator repository](https://github.com/ladislavdubravsky/bandaged-cubes-enumerator/blob/master/cubes/enumerator.py), not `bce/core.py`. It evaluates to **6,473,251**; its 6,399,617 comment is stale. The linked [forum post](https://twistypuzzles.com/forum/viewtopic.php?p=384851#p384851) denied access, so its prose derivation was unavailable.

Early formulas use inclusion-exclusion over cuts, but later ones choose only particular first cuts. For example `p33 = 1 + p32*p3 = 137` permits one chosen face split rather than all 320 slicing or 322 arbitrary spatial face tilings. `p3c=1` is consistent with excluding both two- and three-cell core bars, beyond a rule merely excluding core-containing dominoes. The function has no dynamic closure, component search, rotation quotient, or general dead-end predicate. It is neither an exact all-cuboid total nor a verified puzzle-class total. Restricted seeds may have been intended to cover a subsequent quotient, but that needs an independent completeness proof.

The analytic approach can exactly count **all guillotine partitions** using inclusion-exclusion over nonempty subsets `S` of a box's internal full cut planes:

```text
G(B) = allowed_whole_block(B)
       + sum (-1)^(|S|+1) * product G(C)
         over nonempty S and subboxes C formed by those cuts.
```

There are at most six planes and 63 terms per box. Different slicing trees are deduplicated. Full-grid guillotine partitions number **369,362,176**; singleton-core guillotine partitions number **97,445,695**. They differ from arbitrary cuboid covers: a 3×3 face already has two nonslicing windmills, giving 320 slicing tilings versus 322 total. [check_guillotine_counts.py](../v2/research/check_guillotine_counts.py) preserves and independently checks this repaired recurrence. The main enumerator includes nonslicing covers.

All 7,073 closed atlas representatives also pass an independent guillotine
test. There is a useful derived explanation: a nonslicing subbox of whole
closed blocks has no full internal cut. Any face plane slicing it must cross a
block and be blocked; every legal move therefore moves the whole subbox or
leaves it fixed. This stays true under its rigid rotations, so its connected
footprint would already have merged under implicit closure. Recursively cutting
along existing full cuts gives a guillotine decomposition. Thus the general
slicing family suffices for behavioral representatives, although completeness
of the old **selected-first-cut** family is still unproved. Exact covers retain
the broader spatial counts and provide a transparent independent baseline.

## Mirrors and dead ends

Moves have legal inverses, so there are no irreversible graph traps. A configuration without a legal face turn is isolated and cannot be entered by a last move from a mobile configuration. Other components may have only self-loops or stay confined to one axis. These are different possible mobility filters. Deleting every one-vertex component would delete the unbandaged cube.

The chosen dead-end predicate excludes a puzzle if the union of turnable face
axes over its **entire fixed-frame reachable component** has size zero or one.
Opposite faces share an axis. Legal self-loops count as turns. Whole-cube frame
rotations are handled by the spatial quotient, not counted as additional face
axes. The union must be taken over the component: 2,564 saved representatives
initially permit at most one axis, but 2,561 of them later unlock other axes.

Exactly three behavioral classes are excluded:

| AxisMajor ID | Puzzle | Faces ever turnable |
| --- | --- | --- |
| `00000fedffdfef` | Three full 3×3 slabs | L, R |
| `15455fedffdfef` | One full face and a thickness-two slab | R |
| `3fcfffedffdfef` | Completely fused shell | None |

All three are equivalent to their mirrors. There are **64,056,605** completely
frozen shell partitions, or **2,671,527** frozen proper-rotation classes before
implicit closure; all merge into the one rigid-shell class above. Independent
spatial mobility counts use subset Möbius inversion in
`check_partition_counts.py --rotations --mobility`.

To pair mirror classes exactly, fix the reflection `x → -x`. For each class,
reflect every vertex of its complete component and take the minimum proper-
rotation key. This is the mirrored class ID. A reflection conjugates a face
turn to the inverse turn on the reflected face, so the reflected vertices form
the entire mirror component without a second search. Reflecting just the saved
representative and canonicalizing it spatially can miss equivalence through
legal turns.

The complete analysis checked all **7,858,798** closed fixed-frame vertices in
**33.687 seconds**. Every partner exists in the source atlas; the partner map
is involutive and preserves component size, proper-rotation shape count, and
mobility counts. There are **2,647** classes equivalent to their own mirror and
**2,213** distinct mirror pairs: `2,647 + 2×2,213 = 7,073`, giving 4,860 classes
before mobility filtering.

| Dead-end filter | Proper rotations | Rotations and reflections |
| --- | ---: | ---: |
| None | 7,073 | 4,860 |
| Frozen only | 7,072 | 4,859 |
| **Frozen or permanently one-axis (chosen)** | **7,070** | **4,857** |
| Every unchanging fixed-frame shape | 7,065 | 4,852 |

The last row is a separate, stronger policy. Its eight exclusions include the
ordinary unbandaged cube and four other puzzles that permit turns on multiple
axes while retaining one bandage shape. It is available for comparison through
`--dead-ends unchanging-shape`.

The [filtered representatives and mirror partner map](../v2/enumeration-results/README.md)
retain stable IDs, originating seeds, model metadata, and checksums. The
`analyze_atlas` CLI defaults to the chosen `one-axis` filter and supports `none`,
`frozen`, and `unchanging-shape`. It postprocesses the completed atlas without
regenerating 312 million spatial seeds. Reflection transport is also public in
the Rust symmetry module; its single-shape canonical key is distinct from a
complete puzzle-class key.

## Run it

```python
import bce_v2 as c
counts = c.count_partitions()  # no invisible bonds
full_counts = c.count_partitions(core_bonds=True)
prefix = c.enumerate_puzzles(max_seeds=100_000, implicit_bonds=True)
assert not prefix["complete"]
representatives = [c.Shape(r["labels"]) for r in prefix["representatives"]]
windmill = c.Shape([1,1,4,2,5,4,2,3,3] + [0]*18)
closed = c.close_implicit(windmill)
# A deliberate complete run has no max_seeds:
# atlas = c.enumerate_puzzles(implicit_bonds=True)
```

From `v2/`:

```sh
cargo run --release --bin enumerate -- count
cargo run --release --bin enumerate -- count --core-bonds
cargo run --release --bin enumerate -- generate --max-seeds 100000
cargo run --release --bin enumerate -- scan --max-seeds 100000 --implicit-bonds
cargo run --release --bin enumerate -- sample --samples 10000 --random-seed 1 --implicit-bonds
cargo run --release --bin enumerate -- scan --implicit-bonds --output /tmp/classes.csv
cargo run --release --bin analyze_atlas -- enumeration-results/2026-10-06-shell-puzzles.csv --dead-ends one-axis --output /tmp/filtered-classes.csv --summary /tmp/mirror-analysis.json --pairs /tmp/mirror-pairs.csv
python3 research/check_partition_counts.py --rotations --mobility
python3 research/check_guillotine_counts.py --check
```
