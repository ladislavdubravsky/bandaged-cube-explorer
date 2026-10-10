# Staged solution performance investigation

The recommendations below have since been implemented. See the
[implementation report](staged-performance-implementation.md) for production
changes, budget semantics, validation and new measurements. This investigation
retains the original interruption evidence and diagnostic experiments.

The long example-notebook runs have several distinct causes. BeltRoad and
MostSignaturesCube were cancelled while drawing their shape graphs, before
staged solving began. Their solver preparation also scales poorly with the
number of extracted loops. FourPair reached dictionary validation, where the
same large witness library is reconstructed repeatedly. These costs can be
reduced while retaining the stronger methods developed for the ordinary cube.

The most useful design change is to separate a small, certified generating
basis for algebra from a bounded, richer collection of physical algorithms for
solution quality. Graph rendering needs its own size policy. Block signatures
can inform discovery, but they cannot select the computational backend alone.

## Puzzle sizes and interruption evidence

The current notebook inputs give the following exact quantities. Singleton
counts include physical face centers; the independent virtual core is omitted.
The reference group is the group of colored states already in the reference
shape. Its order determines the feasibility of enumerating that group; the
total colored-state count additionally includes every reachable shape.

| Puzzle | Block signature | Shapes | Extracted generators | Reduced generators | Reference group order |
| --- | --- | ---: | ---: | ---: | ---: |
| BeltRoad | 4 Clock, 4 Pair, 10 singleton | 84,584 | 19,473 | 5 | 1,492,992 |
| MostSignaturesCube | 311, 4 Clock, 3 Pair, 9 singleton | 92,176 | 3,336 | 4 | 10,368 |
| FourPair | 4 Pair, 18 singleton | 4,062 | 4,968 | 3 | 40,131,624,960 |
| Unbandaged3x3 | 26 singleton | 1 | 6 | 6 | 43,252,003,274,489,856,000 |

The saved `KeyboardInterrupt` stacks in
[BeltRoad](../examples/BeltRoad.ipynb) and
[MostSignaturesCube](../examples/MostSignaturesCube.ipynb) end in
`draw_bandage_graph → bandage_graph_layout → _symmetric_spring → np.linalg.norm`.
The repertoire call follows this drawing in the same cell. The saved
[FourPair](../examples/FourPair.ipynb) interruption instead ends in
`SymbolicAlgorithmDictionary.validate → signatures → LoopGenerator.moves`.
Thus changing solver discovery budgets alone would not address the first two
recorded cancellations.

Measurements below are diagnostic runs on this workspace. Some ran alongside
other bounded research jobs, and profiles include cProfile overhead. Cutoffs
show the phase reached within the bound, rather than a measured completion
time. Exact group sizes and operation counts do not depend on those timing
conditions.

## Large shape graphs dominate the notebook cell

The Rust shape exploration itself took approximately 0.10 seconds for BeltRoad,
0.07 seconds for MostSignaturesCube and 0.002 seconds for FourPair in the graph
probe. Graph drawing has a very different cost.

The symmetry spring implementation uses exact repulsion between every ordered
pair of vertices at each iteration. Its default is 300 iterations. Processing
128 rows at a time bounds temporary memory, but retains quadratic computation.

| Puzzle | Pair interactions per iteration | Pair interactions at 300 iterations | Visible cube diagrams | Directed arrows |
| --- | ---: | ---: | ---: | ---: |
| BeltRoad | 7,154,453,056 | 2,146,335,916,800 | 54,912 | 153,594 |
| MostSignaturesCube | 8,496,414,976 | 2,548,924,492,800 | 52,064 | 154,272 |
| FourPair | 16,499,844 | 4,949,953,200 | 4,062 | 11,406 |

The sampled exact repulsion kernel suggests about 657 seconds for one
MostSignaturesCube iteration and 1.03 seconds for one FourPair iteration on this
run. BeltRoad samples varied substantially under concurrent work. These are
extrapolations of repulsion only, excluding attraction, symmetry projection and
rendering; convergence can reduce the iteration count. The exact interaction
counts already explain why a full 90,000-node drawing is unsuitable as a
prerequisite for generating a guide.

There are two more quadratic graph steps:

- `_cycles` repeatedly calls `min(unseen)` on a set. With many short cycles,
  each new cycle scans the remaining vertex set. A single increasing scan of
  vertex IDs produces the same ordered cycles in linear time. On a synthetic
  16,000-vertex involution, the original took 3.58 CPU seconds versus 0.0073
  seconds for that equivalent scan. Fifteen identity, involution and four-cycle
  comparisons retained exactly the same cycle ordering. On the actual FourPair
  graph, symmetry detection changed from 5.55 to 1.21 seconds and selected the
  identical symmetry. Both large graphs hit a 30-second bound in the original
  cycle routine; the local linear variant completed MostSignaturesCube symmetry
  detection in 27.83 seconds.
- Automatic picture sizing, `_shape_width_limit`, performs another all-pairs
  distance calculation. Supplying positions or accelerating layout would still
  leave this calculation and tens of thousands of Matplotlib artists.

The practical notebook change is to separate guide preparation from drawing,
and make the full graph an explicit visualization choice for small components.
For larger components, show counts, distance distributions and a clearly
labelled local neighborhood or aggregate graph. Disabling `show_shapes` or
edge labels alone leaves the expensive layout intact. Merely reducing spring
iterations is also insufficient at this scale.

For an optional full-layout experiment, Graphviz's
[sfdp](https://graphviz.org/docs/layouts/sfdp/) provides a multilevel algorithm
intended for large graphs. It would need visual evaluation and an explicit
policy for preserving the desired symmetry. Switching to NetworkX spring
`method="energy"` is not a general solution: its
[implementation](https://networkx.org/documentation/stable/_modules/networkx/drawing/layout.html)
still evaluates batches against all vertices. A sparse adjacency matrix saves
memory without eliminating that repulsion cost.

Evidence: [graph measurements](notebook-graph-performance.json),
[cycle comparisons](graph-cycle-performance.json),
[graph rendering source](../python/python/bce_v2/graph_render.py).

## Symbolic planning uses an unnecessarily large algebra alphabet

`plan_symbolic_stages` uses `analysis.loops.generators`, the complete extracted
loop collection. The explicit backend instead uses `analysis.generators`, the
small witnessed basis already certified by GAP. The symbolic implementation
derives block actions and projection images for every extracted generator,
builds a free-group map over that alphabet, and requests words for transversal
and strong-generator certificates.

The 90-second BeltRoad solver profile never reached dictionary discovery. It
remained in the first symbolic stage planner. Deriving 19,473 block actions
accounted for 75.6 cumulative profiled seconds, including 4.79 million rotation
composition calls. Only five generators are needed to generate the same group.
Caching block actions and rotation/frame tables would help, and using the
certified basis avoids almost all this preparation in the first place.

For FourPair, disabling chain selection still exceeded a 90-second bound in
raw symbolic synthesis. A separate original-alphabet stage-plan run exceeded its
60-second GAP limit. A local experiment exposing the three GAP-reduced original
witnesses completed a symbolic plan with the same exact group order, placement
quotient 11,612,160 and orientation kernel 3,456. It had 13 stages, 104 cases and
terminal order one. Its certificate independently contained every one of the
4,968 full original loops. A separate planning repeat completed in 7.55 seconds
plus 0.82 seconds to check every original loop against the certificate.
Reduced-basis executable synthesis completed in 12.77 seconds, followed by
2.06 seconds for independent method validation against the full native library.
These are separate runs and phase scopes rather than one combined benchmark.

Reduced generators can have long physical words. Using only that basis for all
quality search could make guides worse. The intended architecture therefore has
two collections: reduced witnessed generators for algebra and certification,
and selected cheap or useful redundant loops for algorithm discovery. The
[symbolic implementation plan](../../docs/symbolic-human-methods-plan.md)
already describes this separation. A complete native-group membership check
must remain when certifying a reduced-basis method.

The experimental reduced-alphabet MostSignaturesCube run completed the full
symbolic template pipeline in **33.54 seconds**, plus 2.32 seconds for analysis.
It produced seven stages, 29 cases and four macros, with exact reference order
10,368, certified coverage and terminal order one. Its final certificate checked
all 3,336 original loops. Three history-free reference-shape scrambles were
solved and replayed successfully. Exact additive mean and worst costs were
141.33 and 224 HTM. This run omitted cProfile. Guide quality relative to a
completed full-alphabet template run remains unmeasured, and these experiments
do not supply a direct end-to-end speedup ratio.

The final BeltRoad reduced-basis run completed both control plans, dictionary
discovery and both adaptive plans within 42.04 seconds. It reached template
repertoire construction but exceeded the 60-second total solver bound there.
This substantially changes the phase reached compared with the default
profile, but does not establish complete BeltRoad guide preparation within a
minute. The default profile used cProfile and this reduced run did not.

Evidence: [BeltRoad solver profile](beltroad-template-profile.json),
[BeltRoad reduced template probe](beltroad-template-reduced-profile.json),
[symbolic basis experiment](symbolic-basis-performance.json),
[MostSignaturesCube complete template experiment](mostsignaturescube-template-reduced-profile.json),
[symbolic planner](../python/python/bce_v2/symbolic_chains.py),
[explicit planner](../python/python/bce_v2/human_chains.py).

## Dictionary construction and validation repeat expensive work

The saved FourPair interruption identifies a concrete validation problem.
`SymbolicAlgorithmDictionary.validate` constructs a signature containing every
generator ID, permutation and expanded physical word twice for every retained
algorithm. With 4,968 roots and 1,024 algorithms, that means more than ten
million generator-word reads in one validation, before its other checks.

These reads have hidden costs. `LoopGenerator.moves` reconstructs its native
tree-path witness on every access. The Rust `generator_moves` implementation
also finds the generator ID by linearly scanning the original generator list.
Repeated full-library signatures therefore combine repeated word expansion
with repeated ID searches.

An experiment on the same real 16-algorithm FourPair dictionary preserved every
validation check:

| Validation implementation | Wall seconds | Python CPU seconds | Native witness reads |
| --- | ---: | ---: | ---: |
| Current | 4.17 | 2.14 | 178,864 |
| Signatures computed once per library | 0.664 | 0.333 | 14,920 |
| Same signature change and cold word cache | 0.346 | 0.241 | 4,968 |
| Same checks with warm word cache | 0.192 | 0.187 | 0 |

This approximately 22-fold improvement applies to that validation experiment,
not to the entire pipeline. It requires no reduction in solution quality or
physical replay coverage.

Dictionary discovery has additional costs before validation:

- Every extracted root, inverse and square is attempted outside the
  `max_candidates` mining budget. `max_seed_loops` bounds structured mining,
  rather than this original-loop admission step.
- `AlgorithmLibrary.build_algorithm` rebuilds the entire generator-ID map and
  resets word and expression caches for each candidate. The direct root loop
  alone performs approximately three times the generator count in builds, each
  rebuilding a map proportional to that count.
- Symbolic method compilation recomputes all generator HTM lengths for every
  correction. Length properties expand and simplify the same native words.
- Dictionary, chain and method validation run repeatedly during optimization
  and repertoire construction. Several downstream calls extract the complete
  isotropy loops afresh instead of reusing prepared provenance.

A bounded FourPair dictionary profile spent 24.8 seconds deriving block actions
and 13.2 seconds in 5,396 algorithm builds, including 4.35 seconds rebuilding
generator maps. It stopped during original-loop admission. The original
90-second dictionary experiment also ended before validation. Thus fixing the
saved validation stack alone would expose earlier and later costs.

With the compact 34-loop FourPair alphabet, signature hoisting and witness
caching, dictionary discovery retained the normal generous budgets and completed
in 31.84 seconds. It retained 1,024 algorithms and covered the entire orientation
kernel exactly, with span 3,456 of 3,456. This supports retaining meaningful
discovery after bounding the input alphabet. A final improved stage policy was
not compiled from that dictionary, so this result does not establish improved
complete-solution costs. Its settings and metadata are retained in the
[FourPair preparation record](fourpair-performance.json).

The appropriate changes are computation-local caches for immutable words,
actions, lengths, ID maps and proof results; an indexed native generator lookup;
and bounded admission of redundant physical candidates. Imported artifacts
should still receive independent full validation. Reusing a verified immutable
object inside one compilation can avoid repeating the same proof.

Evidence: [dictionary source](../python/python/bce_v2/symbolic_dictionary.py),
[algorithm builder](../python/python/bce_v2/loop_algorithms.py),
[native witness lookup](../engine/src/isotropy.rs). The
[FourPair validation experiment](fourpair-validation-performance.json)
retains the identical-dictionary comparisons.

## Backend selection and solution quality

The relevant backend size is the reference group order. MostSignaturesCube's
955,680,768 total colored states do not prevent explicit reference-group
enumeration: that group has only 10,368 elements. Conversely, FourPair's modest
shape graph does not make explicit enumeration feasible for its 40-billion
element reference group.

An initial policy should use the following measured properties:

| Property | What it controls |
| --- | --- |
| Shape count and arc count | Exploration, graph visualization and loop extraction |
| Reference group order | Feasibility of explicit group enumeration |
| Extracted and reduced generator counts | Projection preparation, symbolic words and validation workload |
| Witness lengths | Physical expansion, replay cost and likely fallback quality |
| Movable block orbits and orientation moduli | Stage case sizes and useful discovery patterns |
| Dictionary coverage and measured quality | Whether further mining is likely to improve the guide |

Signatures can supply discovery hints, such as emphasizing singleton cycles or
fused-block orientation corrections. They omit spatial arrangement, mobility,
actual subgroup structure and witness workload. Even singleton counts include
fixed face-center blocks, which contribute differently from movable corners
and edges. Three problematic examples cannot establish a calibrated signature
threshold for the entire atlas.

MostSignaturesCube should be benchmarked with the explicit reduced-basis path
as a candidate; BeltRoad and FourPair should start with reduced-basis symbolic
certification. Existing explicit repertoire construction still performs group
enumeration and substantial validation, so backend eligibility does not imply
instant guide preparation.

In the bounded
[MostSignaturesCube generator profile](mostsignaturescube-generator-profile.json),
the explicit planner completed in 49.9 profiled seconds and baseline compilation
took 33.4 seconds. The full repertoire still exceeded the 90-second bound;
repeated block-action derivation dominated. This route is eligible for explicit
algebra, but it is not yet a measured instant fallback.

The three-generator FourPair executable control had an exact additive mean of
3,541.51 HTM and worst case of 6,613 HTM, before stage-boundary cancellation.
Minimal template preparation took a further 34.61 seconds. This complete control
establishes the speed benefit of reduced algebra, while its physical costs show
why good redundant algorithms must remain available for solution optimization.
The [FourPair preparation record](fourpair-performance.json) keeps those scopes
and replay checks.

Adding the first 32 short original loops to the certified basis yielded 34
distinct generators. This compact, richer alphabet completed synthesis in
7.28 seconds, full-native validation in 1.32 seconds and minimal repertoire
preparation in 21.05 seconds. Exact additive costs fell to **666.34 mean and
1,172 worst HTM**, and legal replay passed. Neither control performed the usual
dictionary and chain quality search. The difference shows that generator
diversity and the physical words returned by algebra matter alongside generator
count; using the smallest possible alphabet everywhere is not the design goal.

Keep the current stronger ordinary-cube optimization available. Its native loop
alphabet has only six entries, so several large-alphabet problems barely occur
there. Its existing measurement records show substantial benefits from adaptive
ordering and shared templates. The saved ordinary-cube notebook run took
438.4 seconds; the separate 22.2-second record measures loading a saved
repertoire, not fresh compilation. Persisting a certified repertoire is useful
when rerunning diagrams or changing display colors.

Quality comparisons should retain exact additive mean and worst HTM/QTM costs,
definition and chunk counts, instruction complexity, and legal execution
checks. A fast fallback may be computationally complete while teaching long
words. Preserve that distinction when introducing faster presets.

## Priority changes

1. Separate drawing from guide compilation in the notebooks. Use a size-aware
   graph presentation, and replace repeated set-minimum cycle scanning.
2. Use the GAP-certified reduced witnessed basis for symbolic algebra. Preserve
   complete native-group certification and a separate physical candidate pool.
3. Cache immutable witness metadata, block actions, expression evaluations and
   proof results within a compilation. Hoist library signatures and index native
   generator IDs. These changes preserve existing search quality.
4. Apply candidate budgets to original-loop admission and template seeds as
   well as synthesized proposals. Reuse prepared graphs, loops and dictionaries.
5. Produce a certified baseline before optional quality passes, with progress
   and a total quality-search budget. Retain the best complete artifact after
   each pass; a cutoff during initial certification must remain incomplete.
6. Select explicit versus symbolic algebra using actual group and workload
   measurements. Let signatures guide candidate discovery rather than dictate
   the whole pipeline. Save compiled artifacts for subsequent notebook runs.

The current `timeout` only limits individual GAP calls. It does not bound
Python discovery, validation, template compression or graph drawing.
`max_chain_expansions` counts optimized stage decisions, each of which can scan
many block features and lookahead choices. Disabling chain selection avoids
dictionary mining but still leaves raw symbolic planning and template work.
Those settings cannot currently guarantee a notebook finishes within fifteen
minutes.

## History and reproduction

Commit `717aa2d` introduced the symbolic large-group methods on 10 October 2026.
Commit `92f7818` introduced symmetry graph rendering earlier that day. The
current BeltRoad and FourPair notebooks were untracked at the start of this
investigation, and MostSignaturesCube's committed predecessor did not call the
staged compiler. There is no comparable earlier staged run for these exact
notebooks from which to establish a timing regression. The findings establish
current scaling problems rather than attributing every delay to the stronger
ordinary-cube methods.

The research scripts read literal notebook bandages without executing their
drawing cells. Runtime-local changes are confined to explicit experiments;
solver implementation changes remain proposals.

```sh
v2/.venv/bin/python v2/research/profile_notebook_graph.py \
  --output /tmp/notebook-graph-performance.json
v2/.venv/bin/python v2/research/profile_staged_solver.py BeltRoad \
  --seconds 90 --output /tmp/beltroad-template-profile.json
v2/.venv/bin/python v2/research/profile_staged_solver.py MostSignaturesCube \
  --reduced --no-profile --seconds 90 --output /tmp/most-reduced-template.json
v2/.venv/bin/python v2/research/profile_symbolic_basis.py \
  --puzzle FourPair --basis reduced --output /tmp/fourpair-basis.json
v2/.venv/bin/python v2/research/profile_fourpair_validation.py \
  --algorithms 16 --output /tmp/fourpair-validation.json
v2/.venv/bin/python v2/research/profile_fourpair_method.py \
  --output /tmp/fourpair-method.json
v2/.venv/bin/python v2/research/profile_fourpair_dictionary.py \
  --short-loops 32 --cache --hoist --no-profile \
  --output /tmp/fourpair-compact-dictionary.json
v2/.venv/bin/python v2/research/profile_cycle_scan.py \
  --output /tmp/graph-cycles.json
```

The cycle, basis and FourPair experiments retain their scripts and machine
records alongside these graph and solver probes. The reduced-basis tests are
experimental implementations of the proposed separation, rather than new
public solver options.
