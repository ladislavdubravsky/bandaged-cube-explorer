# Familiar 3×3 algorithms transported through the shape graph

The human strategy is useful and fits the architecture: reach a shape where a
familiar algorithm works, execute it, and undo the setup. The existing code
represents and checks that construction, but does not systematically discover
these opportunities. A research implementation now scans a finite catalog
across complete shape graphs and independently replays a bounded shortlist.
No production solver or notebook behavior was changed.

The strongest result is that the proposed discovery is inexpensive on the
three problem notebooks, and its usefulness differs sharply by puzzle. This
is a useful additional algorithm source; the earlier
[performance investigation](staged-solution-performance.md) still applies to
graph drawing, algebra preparation and repeated witness validation.

## Measured availability

The catalog has 27 nonidentity base templates and 552 physical word forms up to
inversion. It covers **every adjacent two-face commutator** with quarter,
inverse-quarter or half turns and powers 1–3. An independent enumeration checks
648 ordered candidates, excludes 24 identity words and obtains the same 312
distinct nonidentity commutator words up to inversion.

The remaining forms are all proper face orientations of two selected nested
commutators, a Ua edge cycle, two verified pure edge flips, selected OLLs,
and T/Jb PLLs. Antisune is supplied by inverse Sune. The nested and last-layer
families are a sample, rather than an exhaustive catalog. The native colored
engine independently verifies every ordinary-cube effect. CubeSkills' primary
[PLL catalog](https://www.cubeskills.com/uploads/pdf/tutorials/pll-algorithms.pdf)
provides a source for further curated variants; every adopted word still needs
its own effect and legality checks.

| Puzzle | Reachable shapes | Forms closed at the reference shape | Forms closed somewhere | Shapes with at least one closed form | Discovery time |
| --- | ---: | ---: | ---: | ---: | ---: |
| BeltRoad | 84,584 | 16 | 272 | 3,518 | 3.50 s |
| MostSignaturesCube | 92,176 | 0 | 0 | 0 | 2.61 s |
| FourPair | 4,062 | 20 | 360 | 2,778 | 0.29 s |

Times are single unprofiled runs in the repository's v2 environment. They
include graph exploration, move-array construction, a shared shortest-HTM
setup tree, the full catalog scan and up to 256 independently checked
conjugates. Catalog construction is shared and excluded. The actual full scans
take 1.95, 1.78 and 0.10 seconds respectively. These are discovery timings,
not end-to-end staged-solution compilation timings or solve-quality results.

| Family | BeltRoad forms closed somewhere | MostSignaturesCube | FourPair |
| --- | ---: | ---: | ---: |
| Two-face commutators and powers | 168 | 0 | 168 |
| Selected nested commutators | 16 | 0 | 24 |
| Selected OLLs | 72 | 0 | 72 |
| T/Jb PLLs | 16 | 0 | 48 |
| Ua edge cycles | 0 | 0 | 24 |
| Selected pure edge flips | 0 | 0 | 24 |

BeltRoad confirms the value of the Pair observation: selected OLLs and PLLs
can execute and return to the same partition, and reaching other shapes adds
many usable forms. FourPair also admits the tested edge cycles and one pure
edge-flip family. Its 18-move opposite-edge-flip template even works at the
reference shape.

MostSignaturesCube is a useful counterexample to dispatching by singleton
count alone. It has nine physical singleton blocks, while BeltRoad has ten,
but availability is very different. On MostSignaturesCube, 224 tested forms
are executable somewhere, yet none returns to its starting shape. Therefore
none supplies the direct setup/body/inverse-setup construction. This does
**not** rule out different OLL/PLL words, other nested commutators, longer
powers, compositions of open bodies, or a different return route.

A follow-up tests 1,392 additional nested-commutator forms on all 92,176
MostSignaturesCube shapes. It varies quarter/half-turn inner operands, inner
powers, the third face and its turn amount, with all proper orientations.
Forty-eight additional forms are executable somewhere, across 1,764 shapes,
but none is closed. This broader bounded scan takes under five seconds in
both measured runs and supports the same routing decision without making a
global impossibility claim. The retained run also checks a native replay
sample for every one of the 48 executable forms.

The tested two-corner-twist template `[[R,U]²,D]` has no legal occurrence on
any of these three graphs, including its rotations and inverses. That rules
out this template, not every way of twisting two corners.

## Concrete transported algorithms

For BeltRoad and FourPair, `[R,U]` cannot execute as a closed body at the
reference shape. A one-move setup `F` makes it available:

```text
setup: F
body:  R U R' U'
undo:  F'
```

The resulting six-move root loop is independently replayed on the colored
bandaged cube. The stage planner can use its exact effect where appropriate.

A BeltRoad example of the selected nested corner-cycle family is:

```text
setup: R B' R
body:  B R F R' F' B' F R F' R'
undo:  R' B R'
```

The simplified conjugate costs 15 HTM and affects three corners while leaving
every edge untouched. Rotation and conjugation can change the reported
corner-twist and edge-flip coordinates; stage suitability must use the exact
transported action, rather than inherit all orientation labels from the base.

For FourPair, a Ua variant becomes available after setup `R2`. Setup/body/undo
cancels to a ten-move root loop that cycles three edges and fixes all corners:

```text
R' U' R U R U R U' R' U'
```

Setup and body can be taught separately even when execution cancels at their
boundaries. The JSON retains both the human structure and the shorter physical
word.

## Legality and closure are separate requirements

Every turn must be legal when reached, and the body must return to its exact
starting geometric partition. Otherwise the inverse setup need not work.
This partition includes invisible core bonds. Congruent physical blocks may
exchange places; colored replay verifies that their actual fused memberships
remain intact.

For Bicube Fuse, setup `U` and body `F2` are separately legal, but `U F2 U'`
is blocked. `U F U'` executes but finishes at a different partition. Even an
ordinary commutator needs a closure check: with just the F2L Pair `FR–DFR`,
`R U R' U'` is legal but moves the Pair to `UR–UFR`.

Conversely, requiring every mentioned face to be free initially is too strict.
With the Clock bond `UR–R`, `U` is initially blocked, but
`R U R' D R U' R' D'` is legal and closed. Exact sequence testing recognizes
temporary extraction and reinsertion.

Powers must be scanned as whole words. A body can be open after one application
and close after its second or third. Equal ordinary-cube effects also do not
justify merging different physical words before testing: they can have
different bandage compatibility. Inverse deduplication is safe for closed
availability, because a closed legal body can always be reversed at the same
shape.

## Fast discovery and independent verification

The research scan derives all 18 outer-face transitions from the complete
native QTM graph, retaining distinct face labels, adding inverse traversals
and composing half turns. A blocked-transition sentinel propagates failure.
For each catalog word, NumPy gathers compute its endpoint from every vertex;
endpoint equality gives exact closure. Cost scales with graph size times
total catalog length. It does not enumerate colored states or arbitrary words.

One shared HTM breadth-first tree supplies setup paths. The shortlist retains
at most two nearest vertices per word, reserves a representative of each
available base and fills the remaining budget by setup/body cost. Checked
`ShapePath` composition and native colored replay independently verify every
materialized conjugate. The 256-candidate shortlists contain 164 distinct
nonidentity rooted effects for BeltRoad and 211 for FourPair.

A second implementation compiles each word's forbidden initial bonds and
final bond action. For any connected fused block, an illegal turn must split
some original adjacency along a path through that block. Thus the word is
legal exactly when none of the shape's saturated bonds is forbidden. For a
legal input, the final bond image determines the exact endpoint partition.
Legality becomes one mask intersection; closure is a fixed-size bond action.

The compiler is independently validated against native replay on 16,800
random connected-partition trials, including core bonds and targeted endpoint
regressions, with no discrepancies. The full graph scan is then compared
element by element against that compiler for **99,813,744 word/shape pairs**:
every legality result and every closure result agrees. Compilation of all
552 forms takes 0.70 seconds on the retained verification run through the
public Python API (1.04 seconds on the first run). Native prefix-mask
composition could avoid the current 54 single-bond replay calls per word.
These checks establish correctness on these complete components, not a
production benchmark for a native implementation.

An independent small-graph review also checked every one of 2,178 vertex/move
transitions on Bicube Fuse against native replay, all 121 setup endpoints,
and every shortest HTM distance against a separate native HTM exploration.

## Coverage: use familiar algorithms together with native loops

Exact GAP analysis of the checked shortlists gives:

| Puzzle | Group generated by retained familiar conjugates | Complete isotropy order | Missing coverage |
| --- | ---: | ---: | --- |
| BeltRoad | 746,496 | 1,492,992 | Index 2; one five-move native loop suffices |
| FourPair | 20,065,812,480 | 40,131,624,960 | Index 2; one six-move native loop suffices |

The retained native augmentation for BeltRoad is `R L U2 L' R'`. For FourPair
it is `F B U D' L' R'`. GAP checks membership of all 19,473 and 4,968 native
original generators respectively after adjoining these witnesses. Every
augmentation is independently replayed. MostSignaturesCube keeps its native
machinery, whose complete order is 10,368.

The index-two result concerns only the bounded shortlists. Other vertices,
alternate setup paths or further familiar bodies might supply more effects.
It is nevertheless a concrete reason to preserve certified native coverage
while using the familiar repertoire for quality. No actual staged method
was compiled from these new candidates, so a solve-length improvement has
not yet been measured.

## Production integration

Existing [`ShapePath`](../python/python/bce_v2/shape_paths.py) already provides
checked open setup paths, local loops and `transport_loop`. Human chunks can
teach setup/body/undo extracted from an existing algorithm. In contrast,
[`discover_symbolic_dictionary`](../python/python/bce_v2/symbolic_dictionary.py)
currently uses concatenations of **closed reference loops** as setups. Those
setups never reach a different geometric shape. Accidental familiar patterns
can appear, but shape-wide catalog discovery is missing.

The natural integration is a bounded additional dictionary source before
algorithm and chain improvement:

1. Cache a verified catalog and its exact obstruction masks. Search reachable
   shapes in setup-distance order with explicit work, depth and time budgets.
2. Compute transported sticker actions, deduplicate by rooted effect and retain
   short witnesses plus a small variety of useful supports and body families.
   Several routes to one shape can place an algorithm on different colored
   pieces; one shortest route is a starting point rather than complete coverage.
3. Retain original-loop certificates without factoring each macro in GAP.
   The native spanning tree gives a fundamental loop for each graph arc;
   products telescope to certify any closed word. Expose an arc-to-retained-
   original-generator/sign map after identity and inverse deduplication.
4. Keep the complete stable witness library, but use a reduced generating basis
   inside expensive algebra operations. Cache leaf actions and validated
   signatures. A physically short transported word must have a separate length
   budget from its potentially long expanded provenance proof.
5. Feed candidates into the existing stage stabilizer and feature-orbit search.
   It already filters exact endpoint actions through `group_before`, protecting
   prior stages. Intermediate turns may disturb solved pieces; the complete
   macro must restore the prior features. Keep certified fallback cases when
   the extra vocabulary cannot supply a stage transition.

The final `templates=` vocabulary-packing argument is not the main discovery
hook: candidates need to influence case selection first. Current dictionary
validation also excludes literal `turns` expressions from its accepted
original-expression kinds; imported short physical words should be accepted
only with checked original-loop children and matching independent replay.

Dispatch should use observed availability, setup cost, exact localized effects
and stage usefulness. Singleton count is a hint, and Pair compatibility is
tested directly. A zero-hit bounded scan should fall back promptly rather
than enlarge an ineffective familiar-algorithm search. Fixing the prior
algebra/witness overhead remains necessary: adding these candidates alone
does not remove that overhead or the quadratic notebook graph layout.

## Reproduction

From the repository root:

```sh
v2/.venv/bin/python v2/research/familiar_algorithm_catalog.py
v2/.venv/bin/python v2/research/probe_familiar_algorithm_transport.py
v2/.venv/bin/python v2/research/probe_algorithm_obstructions.py
v2/.venv/bin/python v2/research/verify_familiar_algorithm_transport.py
v2/.venv/bin/python v2/research/probe_additional_nested_algorithms.py
```

Machine records:

- [Discovery, exact words and checked setup/body/undo examples](familiar-algorithm-transport.json)
- [Full graph/mask comparison and exact group coverage](familiar-algorithm-transport-check.json)
- [Independent random-partition and endpoint checks](algorithm-obstruction-check.json)
- [Broader bounded nested-commutator sample for MostSignaturesCube](mostsignatures-additional-nested.json)

Research scripts are isolated from the production solver. Notebook inputs are
read as literal bandage assignments; notebook drawing and solver cells are not
executed. Bounded discovery is concrete and reviewable, while complete staged
integration and solution-quality comparisons remain future work.
