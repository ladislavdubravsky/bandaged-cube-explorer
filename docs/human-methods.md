# Human methods from reference-shape loops

This document fixes the initial semantics for milestone six and describes the
reproducible baseline investigation, stage planner, complete computational
method compiler, bounded algorithm improvement, automatic chain selection and
shared algorithm repertoires with verified compressed rules. The Pocket Cube
review led to a template compiler that selects stages in the taught vocabulary,
reuses valid symmetry variants, and extracts checked open pieces and local loops.
A **puzzle solution** supplies a reusable
algorithm repertoire and recognition and application rules for every reachable
scramble in its declared domain. An algorithm library or a subgroup chain alone
is not that solution.
See the [roadmap](roadmap.md#sixth-milestone-human-solving-methods-and-visual-exploration)
and the existing [block-action interfaces](block-actions.md).

## Scope and reference state

The intended input to method synthesis is a bandage shape in its reference,
solved arrangement. It does not require a colored scramble or its move history.
The reference uses the existing conventional solved coloring, fixed centers,
fixed frame, and six outer-face moves. Colored block identities come from that
reference coloring and their member cells, rather than arbitrary numeric
bandage labels.

The first methods apply when a puzzle already has the reference bandage shape.
Human shape restoration is separate future work. A person applying the method
must inspect the current colors: a shape-only synthesis input does not imply
that uncolored observations suffice during solving.

Let `H` be the exact isotropy group of the reference shape in the faithful
48-sticker action. Every reachable colored state in that shape represents an
element of `H`. Complete shape exploration and witnessed loop extraction
already supply generators of `H`; GAP supplies exact group analysis. The
existing `LoopSolver` and `analyze_block_structure` accept a reference shape
without a scramble and reuse this preparation across colored inputs.

All algorithms in a method start and finish at this same reference shape.
Their internal face turns may pass through other shapes. Each algorithm must
retain an executable, legal face-turn witness. A rotation transfers an
algorithm only when the existing reference-bandage symmetry checks allow it.

## Initial observable features

The stage planner supports placement and full solving of a specific colored
block `b`, plus orientation of the anonymous occupants of a slot region `S`:

| Feature | Observation from a `BlockAction` | Solved value |
| --- | --- | --- |
| `place_block` | `destinations[b]`: the occupied reference footprint | `b` |
| `solve_block` | `(destinations[b], phases[b])`: footprint and observable orientation in the inventory frames | `(b, 0)` |
| `orient_slots` | One occupant phase per destination slot in `S`, in inventory order; identities and placements are ignored | An all-zero phase tuple |
| `place_blocks` | One destination per named component, in inventory order | The ordered reference indices |
| `solve_blocks` | Interleaved destination and phase for each named component | Interleaved reference indices and zero phases |
| `occupy_slots` | Sorted destinations of the named component identities | Their sorted reference indices |
| `place_blocks_up_to_alignment` | A transported set of ordered placement rows for the allowed physical adjustment group | The reference placement rows of that same group |

These observations use the exact action and phase conventions documented in
[block-actions.md](block-actions.md). A phase is a modular coordinate in the
declared source and destination frames; it is not a general instruction to
twist a block independently of the rest of the puzzle. Blocks with orientation
order one need placement alone. Unmarked center spin and independent virtual
core spin are outside the observable 48-sticker model.

An `orient_slots` feature names a union of complete reference-block cells.
All selected slots must have compatible footprints and the same nontrivial
cyclic orientation order. The region must be invariant under the **entire
preceding subgroup**: unfinished pieces may move within it, but may not enter
from an unobserved slot. Both backends check this condition. These stages can
finish several orientations together while leaving their placements free.
They support the general block phase orders two, three and four.

The collection kinds name unions of complete actual inventory components.
`solve_blocks` can finish a corner and its matching edge together without
pretending they are physically fused. Different footprints and orientation
orders can share one collection. `occupy_slots` promises region membership,
allowing internal permutations and phases; it differs from fixing each
component's own destination. These goals work in both explicit and symbolic
backends, portable methods, textual guides and collection diagrams.
`place_blocks_up_to_alignment` retains the shared arrangement while permitting
a declared physical alignment group; it does not independently loosen each
piece's placement. Its adjustment group must lie in the preceding subgroup.

`synthesize_human_method(..., recognition={stage_number: (goal, extra, ...)})`
separates the case observer from the endpoint goal. The feature list must
explicitly include the stage goal; this supplies a certified projection onto
the committed coordinate. The runtime skips a finished goal even when extra
observers remain unfinished. The initial compiler retains the original
goal correction for every refined subcase and verifies the full observation
orbit or explicit fibers. Version-three portable methods save those observers;
ordinary methods retain their existing version-one/two formats.
Guide tables display each observer. Recognition diagrams and the older
repertoire/algorithm optimizers currently reject multiple independent observers
explicitly. Recognition-aware policy optimization remains a later increment.

A placement-first chain uses `place_block` features until all footprints are
fixed, then uses `solve_block` features to remove the remaining orientations.
A block-first chain uses `solve_block` throughout. Mixed chains can compare
both choices. Features that impose no new restriction have index one and are
omitted. Coupled constraints may make additional blocks correct automatically;
the compiler must derive this from the actual group rather than assuming that
block coordinates are independent.

These are ordinary stabilizer features. In a future symbolic backend,
placement corresponds to preserving the block's set of faithful sticker
positions; solving the block fixes those positions individually. Empty,
unobservable point sets contribute no stage. The old predicates in `v1/usage.py`
instead define nested sets of uncolored shape vertices. Disjunctions such as
"either bandage relation holds" need not be stabilizers and are outside this
initial algebraic contract.

## Stage semantics and progress

A chain has the form

```text
H = H0 >= H1 >= ... >= Hr = {identity}
```

`Hi` fixes the features completed before stage `i`; `Hi+1` additionally fixes
that stage's selected feature. The current colored residual belongs to `Hi`
when the stage starts. The stage planner records that stage's observation
orbit and stabilizer. The method compiler reads the declared observation and
selects a correction from its case table. That correction must:

1. Be a legal witnessed root loop belonging to `Hi`.
2. Restore all earlier features at the correction's endpoint.
3. Put the selected feature into its solved value, leaving the residual in
   `Hi+1`.

The default preservation promise applies at **whole correction boundaries**.
A correction may disturb earlier features during its constituent loops or
face turns. The guide must identify the whole correction clearly so that the
person does not make another stage decision partway through it. Requiring
continuous preservation would be a stronger, separate constraint.

The goal observation orbit has size `[Hi : Hi+1]`. Independent recognition may
refine it into more cases without changing the subgroup index. A representative of each orbit
case gives a correction by inversion, with execution order agreeing with
`BlockAction.then` and `LoopExpression`. The already-correct observation has an
identity correction. A case correction must work for every member of `Hi`
with that observation, not just the representative used to construct it.

This is a **feature target**, not an exact full-permutation target. The
correction may have any reachable effect on blocks not yet constrained. This
freedom is a primary opportunity for shorter or simpler early-stage algorithms.
The existing scramble-specific `solve_options` search does not implement this
case-target search.

Coverage follows if the chain, every observation case, and all correction
promises are established and the terminal group is trivial. Each correction
advances into the next subgroup, so the finite stage list ends at the solved
colored state. Neither the number of stages nor subgroup indices alone measure
human difficulty.

## Evidence and result statuses

Generation, coverage and human quality are separate properties. Records state
the scope to which each claim applies. A stage plan retains
`coverage_scope: chain_structure_only` and `human_method_complete: false`.
The implemented method compiler additionally reports:

| Property | Values and meaning |
| --- | --- |
| `status` | `completed`: the full case policy was generated; `limit_reached`: the explicit group-element cap stopped preparation before enumeration. Backend errors remain errors, rather than becoming unreachability claims. |
| `coverage` | `certified`: exact group, case and correction checks establish complete coverage; `partial`: preparation stopped without a complete policy. |
| `coverage_scope` | `all_reference_group_states` for a completed method; `none` for a preflight stop. These claims concern reachable colored states already in the reference shape. |
| `quality` | `computational_baseline`: valid witnessed corrections, optionally improved by bounded search, without a shortest-word, minimum-repertoire or human-review claim. |
| `human_method_complete` | True for a complete executable case policy and false for a stopped method. This flag describes computational completeness; human quality is reported separately. |

A completed chain investigation with exhaustive subgroup checks is still only
`chain_structure_only` evidence. The method compiler adds and checks every case
correction before claiming complete coverage. A complete computational method
does not establish human quality. Algorithm-search reports and human review
report their evidence independently of coverage.

No resource cutoff proves unreachability. A generated method must retain
complete witnessed fallbacks when optional algorithm improvement is bounded,
or label the resulting method incomplete. Limits on enumerating `H` must be
checked against its exact order before enumeration begins where possible.

## Plan stages from a shape: delivery one

`c.plan_human_stages` prepares a reusable stage skeleton from the reference
shape, without a colored scramble. It enumerates the exact root-loop group,
retains compact parent-tree witnesses, and records the observation cases and
subgroup progression. It does not generate a correction policy or claim human
memorability.

```python
import bce_v2 as c

reference = c.fixture("Alcatraz")
plan = c.plan_human_stages(
    reference, strategy="placement_then_orientation", max_group_elements=10_368,
)
if plan.status == "completed":
    for stage in plan.stages:
        print(stage.feature.kind, stage.block_name,
              stage.order_before, stage.order_after, stage.index)
        print(stage.observations, stage.implied_features)
    plan.save("alcatraz-stages.json")
```

The signature is:

```python
plan_human_stages(
    initial, *, strategy="placement_then_orientation", features=None,
    max_group_elements=None, gap_executable="gap", timeout=None, root=None,
)
```

Reference inputs follow the existing isotropy/block-structure interfaces,
including shapes or 27-cell lists, a `State`'s reference specification,
complete shape graphs, witnessed loop sets, existing analyses and block
structures. Supplying a completed previous plan reuses its enumerated group
and block structure while selecting a new chain. `root` selects a graph vertex
when preparing loops; it must agree with an already
prepared reference. Supplied analyses must retain a generating set covering
the complete original loop library.

The automatic strategies are `placement_then_orientation` and
`fully_solve_each_block`. Both greedily minimize the next nontrivial index,
then break ties by stable inventory order. They compare recognizable stage
structure, without optimizing algorithm length or shared repertoire.

`strategy="manual"` instead consumes an ordered list of
`c.BlockFeature(kind, cells)` values. For `place_block` and `solve_block`,
`cells` must be the exact member cells of one reference inventory block.
For `orient_slots`, they are the union of the compatible slot region.
Features use reference member cells, not arbitrary bandage labels.
For example, the automatic list can be supplied explicitly:

```python
manual = c.plan_human_stages(
    plan, strategy="manual",
    features=[stage.feature for stage in plan.stages],
    max_group_elements=10_368,
)
```

To orient a restricted region, first finish a prefix that makes the region
invariant. For example, after solving the first two layers of an unbandaged
cube, its four top edge slots can be oriented without placing their occupants:

```python
reference = c.Shape(list(range(27)))
inventory = c.BlockInventory(reference)
first_two_layers = (c.DBR, c.DBL, c.DFL, c.DFR,
                    c.DR, c.DF, c.DL, c.DB, c.FR, c.FL, c.BR, c.BL)
prefix = [c.BlockFeature("solve_block", (cell,)) for cell in first_two_layers]
edge_orientation = c.BlockFeature("orient_slots", (c.UR, c.UF, c.UL, c.UB))
suffix = [c.BlockFeature("solve_block", block.cells) for block in inventory.blocks]
method = c.synthesize_human_method(
    reference, backend="symbolic", strategy="manual",
    features=[*prefix, edge_orientation, *suffix],
)
```

The suffix completes the colored solve; orientation alone does not do so.
This is a complete computational baseline rather than an optimized layer
method. A region that is not yet invariant is rejected instead of assigning
case transitions that depend on hidden incoming orientations.

Redundant manual features are skipped and retained in `skipped_features`.
The requested manual list must finish at the identity subgroup; a list leaving
a nontrivial colored residual is rejected. `initial_features` identifies
features already satisfied throughout the root group. Each stage also reports
features implied by its subgroup, so the eventual guide can explain blocks
that become correct automatically.

`HumanStagePlan` and its `HumanStage` records are immutable. A completed plan
exposes `group_order`, `quotient_order`, `kernel_order`, `terminal_order`,
`stages`, and the retained `block_structure` with its independent witnessed
kernel basis. Each stage exposes `feature`, `block_name`, `order_before`,
`order_after`, `index`, `observations`, `solved_observation` and
`implied_features`. Placement observations are one-element tuples
`(destination,)`; full-block observations are `(destination, phase)`.
Slot-orientation observations are phase tuples in stable inventory slot order.
Their `block_index` is a tuple of slot indices; the original block features
retain an integer. JSON encodes observations and slot-index tuples as arrays.
Cases include the already-solved observation.
`implied_features` lists newly guaranteed features beyond the selected feature.

The enumerated `plan.group` supplies `permutations` in deterministic BFS
discovery order, original witnessed `generators`, `inventory`, and an on-demand
expression for every element:

```python
group = plan.group
permutation = group.permutations[-1]
expression = group.witness(permutation)
assert expression.evaluate(group.generators) == permutation
print(expression.render())
```

`witness` returns an existing `LoopExpression` in original loop IDs, with
execution order and inverse exponents preserved. It reconstructs the word
from compact enumeration parents instead of storing a separate expanded word
for every element. This is a general executable group witness, not yet a
stage correction or a short human algorithm.

`to_dict()`, `to_json()` and `save(path)` provide deterministic plan records.
The `include_elements` option defaults to false; enable it to include the
enumerated group elements, parent-tree steps and subgroup membership indices.
`include_moves` defaults to true and controls
original witness move expansion. These exports describe the stage skeleton;
the method compiler below supplies the executable policy and guide.

There is no default group-element cap. The example explicitly selects 10,368,
the largest group in the initial validated fixture set. If the certified order
exceeds `max_group_elements`, the result is `limit_reached`, without an
enumerated group or partial stages; `terminal_order` is `None`. This is not an
unreachability result. The cap does not bound shape exploration, GAP analysis,
or the sizes of physical move witnesses. `timeout` applies to each GAP call,
not the entire preparation or Python enumeration.

## Synthesize a complete method: delivery two

`c.synthesize_human_method` compiles the stage skeleton into a complete reusable
case policy. It takes the same reference inputs and stage options as
`plan_human_stages`; no colored scramble is needed:

```python
import bce_v2 as c

reference = c.fixture("Alcatraz")
method = c.synthesize_human_method(reference, max_group_elements=10_368)
if method.status == "completed":
    method.save("alcatraz-method.json")
    method.write_guide("alcatraz-method.md")
    print(method.coverage, method.quality)
```

```python
synthesize_human_method(
    initial, *, strategy="placement_then_orientation", features=None,
    max_group_elements=None, gap_executable="gap", timeout=None, root=None,
)
```

The automatic and manual stage strategies, optional cap, reference selection
and per-GAP-call timeout have the same semantics as the stage planner. A
completed `HumanStagePlan` can be passed to reuse its prepared group. A cap
stop produces an explicitly incomplete `HumanMethod` with no policy;
`coverage` is `partial` and `human_method_complete` is false.

For each nontrivial stage case, the baseline inverts a deterministic BFS coset
representative and retains its original-loop expression and legal physical
witness. Equal correction effects share an algorithm definition. The solved
case has no algorithm and requires no action. This is a complete policy, with
no claim that its face turns, algorithm repertoire or recognition table are
pleasant to memorize.

The immutable records expose:

| Record | Information |
| --- | --- |
| `HumanMethod` | Reference shape and inventory, exact `group_order`/`quotient_order`/`kernel_order`, original `generators`, `stages`, shared `algorithms`, limits, coverage and quality. |
| `HumanMethodStage` | Feature and named block, subgroup orders and index, solved observation, implied features and complete `cases`. |
| `HumanMethodCase` | Observable tuple, `algorithm_id` or `None` for the solved case, and an exact representative for illustrations. |
| `LoopAlgorithm` | Shared algorithm ID, `LoopExpression`, legal `turn_sequence`, exact permutation and block action, QTM/HTM lengths. |
| `HumanMethodStep` | Performed correction, stage/observation, expression and moves, with before/after colored states. |
| `HumanMethodApplication` | Final `status`, `state`, performed `steps`, combined `turn_sequence` and any precondition-failure reason. |

`method.recognize(state)` reports the first unfinished stage and its case.
`method.next_step(state)` returns one checked correction, or `None` when solved.
`method.apply(state)` executes the precompiled policy and retains the trace.
These operations do not launch a GAP factorization for the supplied scramble.
Application requires the matching reference specification and an already
restored shape. Recognition/application distinguish `wrong_reference`,
`shape_not_restored`, `method_incomplete`, and proven `unreachable`.
Recognition reports `ready` or `solved` for accepted inputs; successful
application ends with `solved`. `next_step` raises on a failed precondition;
`recognize` and `apply` return the structured failure.

Case representatives can be inspected as ordinary colored `State` values:

```python
case = next(case for case in method.stages[0].cases
            if case.algorithm_id is not None)
example = method.example_state(1, case.observation)
trace = method.apply(example)
assert trace.status == "solved" and trace.state.is_solved
```

Synthesis verifies complete source-loop coverage, legal generator and
correction witnesses, exact observation cosets, progress for every member of
each case, implied features and terminal identity. Thus every reachable
reference-shaped colored residual is covered. The ordinary cube validity and
rigid-block checks used by colored imports remain separate from this exact
membership test.

`method.to_dict()`, `to_json()` and `save(path)` export version-one
`bce-v2-human-method` records with reference/frame conventions, the full
policy, original witnesses, algorithms, costs and a content fingerprint.
`c.HumanMethod.from_dict(record)` and `c.load_human_method(path)` independently
recheck the artifact. Loading a completed method regenerates the complete
reference shape-loop source and validates group closure, witnesses and every
case correction without invoking GAP. The fingerprint detects content
changes; saved certification labels do not replace these checks.

`method.write_guide(path=None)` returns Markdown and optionally writes it. The
guide explains the reference convention, footprint/sticker or slot-phase recognition cues,
stage progress, complete case tables, shared algorithm definitions and physical
move sequences.
A cap stop produces an incomplete report rather than a claimed solution.
This guide is a computational baseline. For visual recognition cases, use the
repertoire guide described below. Human review is separate from coverage.

`orient_slots` recognition reads the complete phase pattern at the named
slots, independently of the occupants' identities and placements. These
features work with method application, algorithm improvement, shared-template
policies and portable method/repertoire loading. Loading rechecks the invariant
region, observation orbit and every correction. Existing block-feature
artifacts retain their format and interpretation.

## Improve stage algorithms: delivery three

`c.improve_human_method` searches for better corrections while keeping a
completed method as its fallback. It needs no colored scramble or GAP call:

```python
search = c.improve_human_method(
    method, mode="structured", max_candidates=3_000, max_states=2_000,
)
improved = search.method
improved.save("alcatraz-improved-method.json")
improved.write_guide("alcatraz-improved-method.md")
search.save("alcatraz-algorithm-search.json")
print(search.metadata["baseline_metrics"], search.metadata["improved_metrics"])
```

```python
improve_human_method(
    method, *, mode="structured", max_seed_loops=32, max_candidates=3000,
    max_word_length=3, rounds=1, max_states=2000, max_stage_generators=24,
    max_alternatives=3, max_htm_length=120, max_expanded_moves=480,
)
```

The input must be a completed `HumanMethod`. Improvement regenerates the
reference shape loops and rechecks the method; it supplements the stored
generating set with at most `max_seed_loops` native loops. The three modes
provide comparable bounded experiments:

| Mode | Additional candidates |
| --- | --- |
| `original` | Selected native loop witnesses and their inverses. |
| `shallow` | Original candidates, short words and bounded searches over their exact actions. |
| `structured` | Shallow candidates plus stage-preserving Schreier words, differences of words with the same protected-feature observations, powers, commutators and conjugates. |

Candidates need only preserve the features protected at their intended stage.
A correction is eligible for a case when its full effect sends that observation
coset into the next subgroup; it need not equal the baseline correction's full
permutation. The completed proposed method undergoes the same exact coverage,
progress and legal-witness checks as the baseline.

Case selection ranks simplified physical HTM, then QTM, then expression
description cost. Bounded macro searches use additive edge costs to discover
words, so they do not prove shortest physical sequences after cancellation.
The complete policy is also evaluated on every element of the reference group:
an increase in mean or worst-case HTM rejects the proposal and returns the
baseline. This guard does not optimize recognition or the shared repertoire,
and does not promise a QTM improvement.

`max_candidates` counts proposed expressions, including duplicates, identity
effects and length-pruned candidates. `max_states` bounds settled Dijkstra
states across the run. `max_word_length` bounds shallow words and Dijkstra
paths in macro steps; structured constructions can use more original leaves.
`max_htm_length` limits simplified candidate turns, while
`max_expanded_moves` limits witness expansion before simplification. The limits
apply to improvement, never to the retained baseline. All integer settings
allow zero except `max_alternatives`, which must be positive. In particular,
`max_candidates=0` disables new proposals while preserving complete coverage.
These limits exclude reference-graph preparation, final certification and
exhaustive whole-group metrics; `preparation_group_elements` reports that
group's order separately.

`HumanAlgorithmSearch` retains `baseline`, the selected `method`, immutable
per-case `alternatives`, and a copied `metadata` dictionary. Each
`HumanAlgorithmAlternative` names its stage, observation, witnessed algorithm
and discovery source. Reports include settings, proposal and expansion counts,
pruning flags, proposed stage changes, the whole-method acceptance decision
and baseline/proposed/selected metrics. Mean and worst HTM/QTM cover all
reference-group elements, including the solved state. This strict chain has
one correction per nontrivial case; `original_leaf_count`, `original_leaf_htm`
and visible-leaf counts describe reuse beneath those correction definitions.
Bounds and counts are evidence of the experiment performed, not exhaustive
word-search certification.

The retained [Delivery 3 comparison](../v2/research-results/human-algorithms.md)
evaluates all three modes at equal configured limits on Alcatraz, Bicube Fuse
and Shark Fin Soup. It reports full-method worst/mean costs and the increase in
original-loop definitions that can accompany shorter solutions. Original-loop
selection supplies most gains on these fixtures; structured discovery finds
no further move saving at the recorded budget.

`search.to_dict()`, `to_json()` and `save(path)` produce a separate
`bce-v2-human-algorithm-search` inspection report containing both methods and
candidate witnesses. There is currently no search-report loader. Save
`search.method` for a portable, independently loadable version-one method;
its schema and `quality="computational_baseline"` stay unchanged. Optional
search limits do not change completed/certified method coverage.

## Select an algorithm-aware chain: delivery four

Both backends also propose anonymous orientation targets from the
available algorithm actions. Discovery identifies invariant slot regions under the
entire current subgroup, joins regions whose phases an algorithm changes
together, and searches their full reachable phase patterns. A target records
the available algorithms that preserve its solved condition as well as the
forward recipes that repair its cases. Missing cases have no finite stage
mean; observation limits discard oversized targets without truncating them.

```python
selection = c.select_human_chain(
    c.Shape(), backend="symbolic", max_expansions=64, max_methods=4,
    target_options={"max_observations": 128, "max_candidates": 32,
                    "max_prefixes": 12, "max_methods": 2},
)
print(selection.metadata["attribute_targets"])
```

These are the default target limits. Symbolic discovery scans certified
prefixes of complete control chains and inserts shortlisted orientation goals.
It refines the algorithm pool inside each new stabilizer and chooses the
remaining block goals adaptively, then certifies and scores the entire
continuation. Existing controls remain eligible. `max_expansions` and
`max_methods` are shared between adaptive block chains and attribute
continuations; at least one adaptive method slot is retained. The explicit
backend considers the same targets alongside block features in its greedy
and beam searches, using its already enumerated subgroup actions.
Setting any required target limit to zero, or `max_observations` below two,
disables target discovery. Target graph work has its own pattern and proposal
bounds, independently of dictionary
`max_states` and `max_word_length`; installed physical words still obey the
configured expansion and HTM limits. Shared optimization time/work budgets
also interrupt this pass and retain a certified method.

For a prepared subgroup certificate and witnessed algorithm palette, use
`c.discover_algorithm_targets(inventory, group, algorithms,
max_observations=128, max_candidates=32)` directly. It works offline and returns
`AlgorithmTarget` records with `feature`, `observations`, forward `recipes`,
`costs`, `covered_count`, `mean_htm` and `preserving_algorithm_ids`. This pass
introduces no algorithm bodies into that palette. Whole-method template
compression still determines the final learned repertoire; there is currently
no hard seven-long-body constraint on automatic chain selection.

`c.select_human_chain` compares complete methods rather than choosing a chain
from subgroup indices alone. Its input is still the reference shape, without
a colored scramble:

```python
selection = c.select_human_chain(
    c.fixture("Alcatraz"), preference="execution", beam_width=4,
    max_expansions=64, max_methods=16, max_group_elements=10_368,
    discovery_options={"mode": "structured", "max_candidates": 3_000},
)
selection.method.save("alcatraz-selected-method.json")
selection.method.write_guide("alcatraz-selected-method.md")
selection.save("alcatraz-chain-search.json")
print(selection.selected_id, selection.frontier)
```

```python
select_human_chain(
    initial, *, strategy="placement_then_orientation", manual_features=None,
    preference="execution", beam_width=4, max_expansions=64, max_methods=16,
    discovery_options=None, max_group_elements=None, gap_executable="gap",
    timeout=None, root=None,
)
```

Preparation reuses one exact enumerated reference group. The placement-first
and block-first chains each retain their original inverse-BFS policy and a
policy compiled from the common word pool as controls. `manual_features` can
supply an additional complete ordered list of `BlockFeature` values under the same
semantics as the stage planner. The search mixes `place_block` and
`solve_block` choices; each selected feature must strictly shrink the current
subgroup and the completed chain must reach the identity. Case correction
eligibility and preservation still use the exact stage subgroup, allowing
arbitrary reachable effects on blocks that have not yet been constrained.

Algorithm discovery runs once on the chain chosen by `strategy`, using the
Delivery 3 defaults modified by `discovery_options`. Pool-based automatic,
manual and searched chains receive the same discovered witnessed word pool
and complete inverse-BFS corrections. The original BFS policies remain
independently selectable fallbacks. This comparison holds the discovered
algorithm pool fixed, while its stage-aware discovery can favor the origin
chain; the report records that
origin. Selection does not rerun discovery separately for every candidate.

Bounded greedy and beam exploration use complete rollouts of a partial chain
to rank choices. `additive_mean_htm` is a ranking proxy formed from separate
stage correction costs; whole-solution cancellations can change the actual
mean and worst cost. Prefixes reaching the same subgroup may retain different
definitions and cancellation opportunities, so subgroup equality alone does
not identify equivalent methods.

Every retained completed candidate is certified and evaluated on all
reference-group states. The exact comparison reports:

- `mean_htm` and `worst_htm`, after simplifying the full executed word.
- `max_case_count` and `case_count_sum`, including the solved observation at
  each stage, as recognition-branching proxies.
- `original_leaf_count`, `original_leaf_htm` and `definition_htm`, describing
  the original loop repertoire and correction definitions.
- `stage_count`, alongside the chain's features and subgroup progression.

The Pareto frontier retains candidates that no other retained candidate
matches or improves in all eight dimensions with a strict improvement in at
least one. The default `preference="execution"` selects lexicographically by
mean HTM, worst HTM, maximum cases, summed cases, original leaf count, original
leaf HTM, correction definition HTM and stage count. `preference="recognition"`
moves maximum and summed case counts ahead of mean and worst HTM, leaving the
remaining order unchanged. These are explicit computational preferences, not
human-quality scores. Different chains may trade mean against worst-case
length or recognition complexity; the same-chain Delivery 3 nonregression
guard does not apply across chain choices. The report retains the controls
and frontier so that these tradeoffs remain reviewable.

`beam_width` is positive. `max_expansions` counts expanded partial-chain nodes
across greedy and beam exploration; `max_methods` counts additional completed
greedy/beam methods. Both accept zero. Automatic and supplied manual controls
are outside the additional-method budget and remain available when exploration
is disabled. Discovery settings retain their separate Delivery 3 bounds.
Exact preparation, certification and completed-method evaluation are outside
these quality-search bounds. Reports distinguish exhausted bounds from
completed coverage, without a global optimum claim. Delivery 6 records human
review separately from these computational scores.

`HumanChainSearch` exposes the original raw BFS `baseline`, selected `method`, immutable
`candidates`, `frontier` candidate IDs, `selected_id`, copied `metadata` and
`status`. Each `HumanChainCandidate` has an `id`, `source`, complete `method`
and copied `metrics`. `save`, `to_json` and `to_dict` write an inspection
report in `bce-v2-human-chain-search` format. There is no chain-report loader;
save the selected ordinary version-one method for independent loading.
If the group cap stops preparation, the result has `status="limit_reached"`,
an incomplete baseline method and no candidates. This explicit partial report
can still be saved. A quality-search bound instead leaves the selected method
completed and certified.

The [retained Delivery 4 experiments](../v2/research-results/human-chain-selection.md)
compare execution- and recognition-directed exploration, preserve the known
Alcatraz six-stage/three-case versus five-stage/nine-case controls, and report
the larger repertoire accompanying shorter execution. Complete Alcatraz
[execution](../v2/research-results/alcatraz-execution-method.md) and
[recognition](../v2/research-results/alcatraz-recognition-method.md) guides are
available with independently loadable JSON artifacts.

## Use the reduced generators as the taught vocabulary

`c.generator_human_repertoire` generates the same stage-by-stage guide and
recognition diagrams using only the reduced isotropy generators as master
algorithms. It accepts a reference shape, existing block analysis, prepared
stage plan, or completed `HumanMethod`:

```python
repertoire = c.generator_human_repertoire(shape, max_group_elements=10_368)
repertoire.write_guide("method.md", diagram_mode=c.DiagramMode.TRANSPARENT,
                       face_colors={"U": "white", "F": "green"})
repertoire.save("generator-repertoire.json")
loaded = c.load_human_repertoire("generator-repertoire.json")
result = loaded.apply(state)  # optional; no GAP or new factorization
```

```python
generator_human_repertoire(
    initial, *, strategy="fully_solve_each_block", features=None,
    max_group_elements=None, gap_executable="gap", timeout=None, root=None,
)
```

For an existing selected method, use
`c.generator_human_repertoire(selection.method)`. This retains the chosen stage
features and order, while rebuilding its corrections from the reduced
generators. A direct shape input uses the declared strategy or explicit
`features` and skips algorithm discovery and chain-quality search. Preparation
still uses exact finite-group enumeration, with an optional group-element cap.

The **Algorithms** table contains exactly `M1` through `Mn`, matching the
reduced generators in analysis order. Each case instruction is a combination
of those masters, their inverses and powers; no extra learned algorithm is
introduced. Executing the complete correction restores all features protected
by earlier stages. Individual master applications may temporarily disturb
them. The existing guide, recognition, application and portable-artifact APIs
work unchanged, and loading or applying a saved repertoire needs no GAP.

This fixed-vocabulary compiler remains available as a comparison control. The
BandagedPocketCube notebook now uses the template compiler below, which selects
stages and complete corrections using its actual taught vocabulary.

## Select symmetry templates and shared pieces

Familiar algorithm transport now supplies the production symbolic dictionary
before stage and chain selection. `c.discover_symbolic_dictionary(analysis)`
tests familiar bodies at nearby shapes, constructs legal setup/body/undo root
loops, and retains exact native-loop certificates with their short physical
words. Prior stage features are checked against each transported action;
intermediate turns may disturb them, but the macro endpoint must restore them.
Complete native fallback policies remain available. See the
[dictionary guide](../v2/python/README.md#discover-a-dictionary-and-choose-a-symbolic-chain)
for availability reports, separate physical/proof limits and standalone
`c.discover_familiar_algorithms` use.

```python
repertoire = c.template_human_repertoire(shape, preference="memory")
repertoire.write_guide("method.md", diagram_mode=c.DiagramMode.OPPOSITE_CORNERS)
repertoire.save("templates.json")
loaded = c.load_human_repertoire("templates.json")
result = loaded.apply(state)
```

The input can be a shape, isotropy analysis, prepared stage plan, or completed
method. Shape-based preparation compares both automatic stage strategies and
bounded mixed feature chains. A supplied method retains its chain unless
`select_chain=True`. Explicit `features` define the baseline; use
`select_chain=False` to keep them fixed. Every compared policy uses its own
taught templates, inverses and valid reference-bandage symmetries. Original loop
witnesses remain in the artifact as complete group provenance, even when fewer
templates are taught.

For each observation, the compiler searches for a complete correction into the
next stabilizer. Later features remain free, and the correction is checked on
every member of the observation fiber. Complete additive macro Dijkstra supplies
fallback words; a bounded search compares expanded physical words to exploit
cancellation across calls. The exact input policy is also an eligible fallback.
Mean and worst HTM must both stay within `max_cost_ratio` of that policy
(default 1.0). Reaching a quality budget never removes coverage.

`preference` accepts `memory`, `execution`, or `recognition`. The saved Pareto
comparison measures dictionary symbols, whole-case instruction symbols, template
count, actual mean/worst HTM and case counts. These are reproducible proxies;
the artifact makes no global shortest-word, minimum-dictionary or human-review
claim. Budgets include `max_trials`, `max_applications`,
`max_word_candidates`, `max_word_frontier`, `beam_width`,
`max_chain_expansions` and `max_chain_methods`. Physical-word budgets apply to
each trial vocabulary; counters report totals. `chunk_options` controls the
bounded dictionary search, with literal fallback when a word exceeds its limit.
`max_group_elements`, `timeout`, `gap_executable` and `root` retain the existing
exact preparation semantics. Loading and applying prepared artifacts need no GAP.

The guide lists piece definitions inside the Algorithms section's Shared piece
recipes subsection and displays whole-cube regrips around named calls. Mixed-grip case recipes reuse the taught
templates instead of adding new algorithm definitions. Piece definitions carry
exact admissible source shapes; a repeated spelling alone does not make a piece
executable from every shape.

The path and dictionary APIs can also be used independently:

```python
setup = c.ShapePath.from_moves(shape, setup_moves)
body = c.ShapePath.local_loop(setup.target_shape, loop_moves)
closed = setup.transport_loop(body)  # setup, body, inverse setup
dictionary = c.extract_algorithm_chunks(shape, {"A": closed.moves})
assert dictionary.expand("A") == closed.moves
```

`ShapePath` retains exact source/target shapes, presentation frame, normalized
face moves and faithful sticker action. Composition checks both endpoints and
frames; inversion reverses endpoints, and rotation transforms endpoints and
action. `from_graph` constructs a witnessed route between shape vertices.
`to_loop_expression(witness, generators)` only accepts a closed reference path
whose replay agrees with the supplied original-loop certificate. Open paths
are never accepted as reference-loop leaves.

`extract_algorithm_chunks` mines repeated paths in direct, inverse and proper
rotation forms, splits half-turn boundaries when useful, and retains
setup/local-loop/undo decompositions. `ChunkDictionary` records checked instances,
typed expression trees, formulas, metrics and search limits. Both it and
`ShapePath` support independently replayed portable records; malformed endpoints,
frames, actions, references and costs are rejected.

## Share algorithms and compress rules: delivery five

`c.optimize_human_repertoire` compiles a completed method into a taught
vocabulary of named master algorithms and verified stage instructions. It can
follow the baseline compiler, algorithm improvement or chain selection:

```python
repertoire = c.optimize_human_repertoire(
    selection.method, preference="memory", max_trials=64, max_recipes=2_000,
)
repertoire.method.save("alcatraz-expanded-method.json")
repertoire.save("alcatraz-repertoire.json")
repertoire.write_guide("alcatraz-repertoire.md")
loaded = c.load_human_repertoire("alcatraz-repertoire.json")
print(loaded.metadata["baseline_metrics"], loaded.metadata["selected_metrics"])
```

```python
optimize_human_repertoire(
    method, *, preference="memory", max_trials=64, max_recipes=2000,
    max_power=4, max_extra_macros=16, max_setup_macros=16,
    allow_symmetry=True, max_cost_ratio=1.0,
)
```

The input must be a completed `HumanMethod`. Taught master definitions are
distinct from its original loop-provenance definitions: the repertoire records
both the executable physical words and the words' exact witnessed origins.
Instructions may reuse a master, its inverse or power, and verified setup/undo
constructions. Symmetry transfers use only actual proper symmetries of the
reference bandage shape. Each full instruction sequence must preserve the
earlier stage features and solve every state in its declared observation case.
Its constituent master applications may temporarily disturb those features;
the same whole-correction boundary convention still applies.

Recognition compression retains the complete observation cases as its source
of truth. Grouped inverse, power and repeated-action rules are accepted only
after their expansion has been checked against all cases they replace. The
compressed guide still gives concrete footprint and sticker cues and identifies
the complete correction to execute. A shorter rule list does not remove
reachable observations from the domain or imply that recognition itself has
become easier for a person. Kernels are not assumed central, and corrections
are not reordered across placement actions without checking their effects.

The optimizer compares the actual input policy with bounded shared-vocabulary
policies, then attempts to remove master definitions while retaining complete
stage reachability. Controls and trials use one fixed recipe pool. Every
completed candidate is independently certified and evaluated across the full
reference group, including cancellation in the complete executed word.
`max_cost_ratio=1.0` requires both mean and worst HTM to stay at or below the
actual input policy. An explicit larger ratio permits execution cost to grow
within that ratio in exchange for other properties. QTM is reported without
the same guard.

The Pareto dimensions are `macro_count`, `macro_definition_htm`, `mean_htm`,
`worst_htm` and `rule_count`. `preference="memory"` compares them in that
order; `"execution"` puts mean and worst HTM first, then master count,
master-definition HTM and rule count. Named-master count and total definition
length are computational memory proxies. Original leaf costs are recorded
separately, and `rule_count` counts compressed rule families rather than
observation cases. The report retains candidates, a Pareto frontier and the
selected candidate, without claiming a minimum repertoire or human
memorability. The initial Delivery 6 review preferred the reduced-generator
vocabulary described above.

All integer quality budgets accept zero. `max_trials` counts attempted master
removals, including unreachable and quality-rejected proposals. `max_recipes`
counts new net recipe proposals, including duplicates, identities and pruned
recipes; unconditional direct master/inverse recipes and complete fallbacks
are outside that budget. `max_power`, `max_extra_macros` and
`max_setup_macros` limit the additional vocabulary constructions. Exact
validation, reference preparation and whole-group policy metrics run outside
these quality budgets. Exhausting a quality budget preserves complete
coverage and the explicit baseline fallback. The cost ratio must be finite
and at least one.

`HumanRepertoire` retains `baseline`, the selected expanded `method`, `macros`,
`stages` and copied `metadata`, and exposes `recognize`, `next_step` and `apply`.
The expanded method preserves the portable version-one method format.
`save`, `to_json` and `to_dict` produce a self-contained
`bce-v2-human-repertoire` version-one artifact with definitions, compressed
rules, both methods and a fingerprint. `HumanRepertoire.from_dict` and
`load_human_repertoire(path)` independently validate the methods, master words
and rule expansions without GAP. They recheck actual baseline/selected metrics
and the metadata's internal selection consistency. Historical candidate costs
and search counts remain recorded experiment data; they do not certify a
minimum repertoire. The fingerprint detects record changes; the mathematical
checks establish coverage. `write_guide` produces the
compressed repertoire guide.

To render recognition cases as cube diagrams, choose a mode before generation
and pass it to the guide:

```python
diagram_mode = c.DiagramMode.OPPOSITE_CORNERS
face_colors = {"U": "white", "R": "red", "F": "green",
               "D": "yellow", "L": "orange", "B": "blue"}
repertoire.write_guide("method.md", diagram_mode=diagram_mode, face_colors=face_colors)
```

`DiagramMode.OPPOSITE_CORNERS` gives opaque orthographic views from UFR and BLD.
`DiagramMode.TRANSPARENT` uses an orthographic camera looking along the UFR
diagonal. Face centers and solved grey stickers remain opaque; unfinished
non-target stickers stay white and transparent. Both modes embed
standalone PNGs for every exact case, including the already-correct case.
Placement-only cases group all attainable orientations under one instruction.
Their skip case means already placed; the sticker orientation can still require
a later correction. The two opposite-corner views expose different faces, so
two orientation rows can share the same front view while differing at the rear.

Dark grey marks blocks guaranteed fully solved before the stage, including
initial and earlier implied guarantees. Face-center stickers and the current
recognition target use the full selected face colors. All other stickers are white, including blocks
whose placement is guaranteed but whose orientation remains unfinished. Roles follow
physical block identity through its current placement, rather than whatever
looks solved in one example. Current-stage consequences join the appropriate
solved set in the following stage.

For an `orient_slots` target, blue marks one intrinsic reference facet of each
occupant; the remaining selected facets have a neutral shade. The guide names
the reference marker stickers and prints each slot's phase for the case. The
marker position distinguishes every cyclic phase, including order four, while
the rest of the occupant's colors and its identity remain hidden. Every
compatible occupant uses the same canonical-template marker, so equal slot
phase patterns have equal marker pictures even when the pieces are permuted.
The convention remains the declared inventory frame.

`face_colors` accepts a mapping from U/R/F/D/L/B to Matplotlib colors; omitted
faces retain the standard palette. This palette changes pictures only. Reference
face labels, recognition cases and solving algorithms do not change.
Ordinary color names such as `"blue"`, `"orange"`, `"gray"`, and `"white"`
work directly, as do hex colors and RGB tuples.
An exact white face color gets ten thin black stripes spanning each colored
sticker so it remains distinct from plain white hidden stickers. This marks
only white centers and current targets; grey solved stickers stay unmarked.

Each case instruction includes both its algorithm identifier and its complete
turn sequence: `M1: R U R' U'`. A rotated instruction shows the cube already in
its required starting grip, and its turns use that pictured frame. Hold the
cube as shown for each case; the next diagram supplies the next starting grip.
The labels U/R/F/D/L/B in a diagram name the faces of that execution frame,
while the colors continue to identify the same physical reference stickers.
Recipes with incompatible nested frames receive their own algorithm definition
with an exact expanded word, keeping every definition in **Algorithms**.

The **Algorithms** section appears before the stages as a table with **Turn
sequence**, **Block action**, and **Structure** columns. Identifiers appear
beside their expanded turns. The guide goes directly into the stages, without
preparation or recognition-color sections or repeated footprint instructions.
Physical structured notation uses `S^A` to mean
A⁻¹ S A, `[A, B]` means A B A⁻¹ B⁻¹, and `(A)n` repeats A. Compound exponents
are parenthesized, as in `S^(X Y Z)`. For example,
`R U' B' U R'` displays as `B'^(U R')`. The formatter detects exact written
constructions and retains the expanded turns. Move counts and witness
provenance are omitted from the guide; provenance remains in portable records.
It does not commute turns or replace a word by a different action-equivalent
algorithm. The minimal [BandagedPocketCube notebook](../v2/examples/stabilizer-chain-methods/BandagedPocketCube.ipynb)
lets you choose the view and face colors before evaluating the shape-only pipeline.
Its cell calls `bce_v2.notebook.refresh_renderers()` before evaluation so edits
to the rendering code take effect in an already running kernel. Plain repeated
imports reuse Python's cached modules. The refresh keeps existing puzzle,
method, and enum objects valid.

The [retained Delivery 5 comparison](../v2/research-results/human-repertoire-compression.md)
records definition and rule compression against actual input policies, with
complete-method costs and the limits used. These measurements remain
computational evidence; the initial human review found the learned vocabulary
less practical than the reduced generators for BandagedPocketCube.

## Generate a method from the command line

```sh
v2/.venv/bin/python -m bce_v2 plan-method Alcatraz \
    --max-group-elements 10368 \
    --output /tmp/alcatraz-method.json --guide /tmp/alcatraz-method.md
```

`plan-method` accepts a bundled fixture name, an inline JSON list of 27 labels,
a JSON file containing that list, or a versioned puzzle file. A puzzle file
supplies its reference specification, independently of its current scramble.
The input needs no colored state when labels are supplied directly. The CLI
supports both automatic `--strategy` values, `--max-group-elements`,
`--gap-executable` and `--timeout`.

Full JSON is printed to stdout, including when `--output` also saves it.
`--guide` additionally writes Markdown. Exit codes are zero for a completed
method, two for an explicit cap stop, and one for invalid input or a backend
error. Output and guide files must differ from one another and any input file;
path, symlink and hardlink aliases are rejected before synthesis or writing.

Add bounded improvement and a separate inspection report with:

```sh
v2/.venv/bin/python -m bce_v2 plan-method Alcatraz \
    --max-group-elements 10368 --improve-algorithms \
    --search-mode structured --search-max-seed-loops 32 \
    --search-max-candidates 3000 --search-max-states 2000 \
    --output /tmp/alcatraz-improved.json --guide /tmp/alcatraz-improved.md \
    --search-report /tmp/alcatraz-search.json
```

The CLI also accepts `--search-rounds`, `--search-max-word-length`,
`--search-max-htm-length` and `--search-max-expanded-moves`; defaults match the
Python API. The method JSON on stdout and at `--output` retains its existing
version-one schema. `--search-report` requires `--improve-algorithms` and must
differ from every other file, including through aliases. If the group-element
cap stops preparation, improvement is skipped and no search report is written;
the incomplete method JSON/guide and exit code two remain available.

Compare chains using one shared discovery pool with:

```sh
v2/.venv/bin/python -m bce_v2 plan-method Alcatraz \
    --max-group-elements 10368 --select-chain \
    --chain-preference recognition --chain-beam-width 4 \
    --chain-max-expansions 64 --chain-max-methods 16 \
    --search-mode structured --search-max-candidates 3000 \
    --output /tmp/alcatraz-selected.json --guide /tmp/alcatraz-selected.md \
    --chain-report /tmp/alcatraz-chain-search.json
```

`--select-chain` includes discovery using the existing `--search-*` options.
`--strategy` selects the origin baseline. It cannot be combined with
`--improve-algorithms`; `--search-report` retains its improvement-only meaning.
`--chain-report` requires chain selection and must differ from every other
artifact and input file, including aliases. A preparation cap writes the
explicit partial chain report, method and guide with exit code two. Search
bounds do not change completed-method exit code zero or the portable method
format.

Add repertoire optimization after synthesis or chain selection with:

```sh
v2/.venv/bin/python -m bce_v2 plan-method Alcatraz \
    --max-group-elements 10368 --select-chain --optimize-repertoire \
    --repertoire-preference memory --repertoire-max-trials 64 \
    --repertoire-max-recipes 2000 \
    --output /tmp/alcatraz-expanded.json --guide /tmp/alcatraz-expanded.md \
    --repertoire-output /tmp/alcatraz-repertoire.json \
    --repertoire-guide /tmp/alcatraz-repertoire.md
```

`--optimize-repertoire` can also follow `--improve-algorithms` or ordinary
synthesis. Stdout, `--output` and `--guide` describe the selected expanded
method. `--repertoire-output` additionally saves the independently loadable
wrapper, including comparison metadata; `--repertoire-guide` writes the
compressed guide. Both require optimization. The CLI accepts the Python
defaults for `--repertoire-max-power`, `--repertoire-max-extra-macros`,
`--repertoire-max-setup-macros` and `--repertoire-max-cost-ratio`;
`--repertoire-no-symmetry` disables transfers. All input and artifact paths
must be distinct, including aliases. A preparation cap skips optimization
and leaves repertoire output/guide paths untouched while retaining the
ordinary partial method artifacts and any requested partial chain report.

## Baseline investigation: delivery zero

Delivery zero promotes the initial local probe into a reproducible research
experiment and freezes the semantics above. Its work is intentionally limited
to exact loop-group enumeration, recovering block actions, and comparing
recognizable stabilizer chains. It does not implement the proposed public API,
case corrections, algorithm optimization, or a human guide.

The research entry point is
[`v2/research/probe_human_chains.py`](../v2/research/probe_human_chains.py).
Its deterministic baseline report is
[`v2/research-results/human-chain-baseline.json`](../v2/research-results/human-chain-baseline.json).
Optional `--measurements PATH` output separates timing and peak-memory
measurements from the reproducible mathematical records. The default run
selects Alcatraz, Bicube Fuse, Shark Fin Soup and the research alias
Most Signatures Cube. The alias is a documented research shape, rather than a
new native fixture; its labels match `MOST_SIGNATURES` in
[`test_block_solver.py`](../v2/python/tests/test_block_solver.py) and the
[`Most Signatures Cube notebook`](../v2/examples/stabilizer-chain-methods/MostSignaturesCube.ipynb).

From the repository root, with the installed v2 Python environment and GAP:

```sh
v2/.venv/bin/python v2/research/probe_human_chains.py \
    --output /tmp/human-chain-baseline.json \
    --measurements /tmp/human-chain-measurements.json
```

Omit `--output` to print the deterministic report to standard output. Repeated
`--puzzle` options select individual reference puzzles. The baseline command
uses no group-element cap; the supported measured sizes below
do not establish a practical threshold for arbitrary larger groups.

The script's current report uses `status: completed` for a completed baseline
investigation, `coverage_scope: chain_structure_only`, and
`human_method_complete: false`. An optional `--max-group-elements` cap is
checked against the exact GAP order before group enumeration; exceeding it
reports `status: limit_reached` without a partial chain. There is no default
group-element cap. This bound does not limit shape exploration or GAP analysis.
The CLI exits with code two if any selected puzzle reaches the cap.
Regression checks belong to
[`test_human_chain_probe.py`](../v2/python/tests/test_human_chain_probe.py).

The promoted probe uses the existing Python API and reduced witnessed loops,
with inverses, to enumerate all 48-sticker permutations by BFS. The baseline
completed all four references. It legally replayed every selected original
generator, reconstructed every permutation from its block action, and checked
feature equivariance for every enumerated element and generator transition.
Each stage's observation fibers were verified as actual right cosets of its
stabilizer, not merely equal-sized sets. Terminal triviality and the chain
index product were also checked. Enumeration and placement/kernel counts
matched the independent GAP analysis:

| Reference fixture | Enumerated `H` | Placement quotient `P` | Footprint-fixing kernel `K` |
| --- | ---: | ---: | ---: |
| Alcatraz | 324 | 18 | 18 |
| Bicube Fuse | 60 | 60 | 1 |
| Shark Fin Soup | 36 | 12 | 3 |
| Most Signatures Cube | 10,368 | 144 | 72 |

The initial explicitly validated enumeration scope is these fixtures through
order **10,368**. This is a measured upper scope, not a default cap or a claim
about a universal performance limit. The largest reference has 92,176 shapes
and 3,336 extracted loops; four reduced generators give an alphabet of seven
after including inverses and removing duplicates. In the recorded run its
total probe took 12.594 seconds: group enumeration took 0.315 seconds, action
validation 6.577 seconds and chain validation 1.044 seconds. Process high-water
RSS was 56,188 KiB, cumulative across the four-reference invocation. These
machine-specific values belong to the separate
[`measurement report`](../v2/research-results/human-chain-measurements.json),
rather than the deterministic mathematical baseline.

The greedy choice minimizes the next nontrivial index, then breaks ties by
stable inventory order. It does not optimize algorithm witnesses. Case counts
and stage indices include the already-solved observation, whose correction
will be the identity. For Alcatraz it gives:

| Feature completed | Subgroup order after the stage | Index |
| --- | ---: | ---: |
| Start | 324 | |
| Place UR edge | 162 | 2 |
| Place UBR corner | 54 | 3 |
| Place BR–DBR pair | 18 | 3 |
| Solve UR edge, with placement already fixed | 9 | 2 |
| Solve UBR corner, with placement already fixed | 3 | 3 |
| Solve UFL corner, with placement already fixed | 1 | 3 |

Fully solving one block at a time instead gives orders
`324 -> 108 -> 54 -> 27 -> 3 -> 1`, using BR–DBR pair, FL–DFL pair,
UR edge, UBR corner and UFL corner. Its indices are `3, 2, 2, 9, 3`:
one fewer stage introduces a nine-case observation orbit. This comparison
motivates measuring recognition complexity alongside stage count; it is not
evidence that either chain has a better algorithm repertoire.

## Supplied palettes and a strict coarse-stage compiler

`AlgorithmPalette` admits witnessed bodies before symbolic chain selection.
Each `AlgorithmPaletteBody` has a stable taught ID and explicit inverse
permission. `AlgorithmPaletteSetup` permits setup/body/undo recipes; standalone
adjustments are declared separately. Complete recipes are built before their
endpoint preservation is checked, so a useful conjugate survives even when
its setup alone disrupts a protected goal. Repetition and permitted inverse
calls retain the same taught ID. This initial palette API uses witnessed
fixed-frame turns; no additional rotation permission is inferred.

Pass `palette=` to `select_human_chain` or `template_human_repertoire` with
the symbolic backend (or an automatic backend that routes there). The prepared
`dictionary=` route remains available, and `templates=` still factors the
selected physical policy. Palette bodies also seed that factorization.
Ordinary symbolic selection retains certified fallback controls and records
`strict_vocabulary: false`; supplying a palette there is not a hard body budget.

`compile_coarse_method` instead requires complete coverage using only declared
palette recipes. It accepts an explicit goal ladder and optional start-domain
features. The start domain is certified independently from the palette's
generated subgroup. Large pointwise collection assumptions are split into
small singleton stabilizers for certification, avoiding a huge entry table.
The portable artifact retains those entry certificates; application refuses
states outside the declared domain before executing any correction.

Guides name the used execution vocabulary `A`, `B`, `C`, and so on. The
Algorithms table's Structure column gives each correction as calls to those
names, read from left to right: `B⁻¹ C⁻¹` calls the two inverses, and `A⁻³`
repeats the inverse of A three times. Setup recipes use `[B: A]` for B, A,
then undo B. These display names leave the stored teaching IDs and physical
move sequences intact.

```python
from dataclasses import replace
import bce_v2 as c

analysis = c.analyze_isotropy(c.Shape())
builder = c.AlgorithmLibrary(analysis.loops, (), (), ())
def body(identifier, turns):
    return replace(builder.build_algorithm(analysis.loops.certified_root_turns(turns)),
                   id=identifier)

adjustments = tuple(body(word, word) for word in ("U", "U2", "U'"))
palette = c.AlgorithmPalette.from_algorithms(
    (body("EO", "F R U R' U' F'"),
     body("Sune", "R U R' U R U2 R'"),
     body("Tperm", "R U R' U' R' F R2 U' R' U' R U R' F'"),
     body("Ua", "R U' R U R U R U' R' U' R2")),
    setups=adjustments, adjustments=adjustments, allow_inverse=False)
edges, corners = (c.UR, c.UF, c.UL, c.UB), (c.UFR, c.UFL, c.UBL, c.UBR)
f2l = tuple(cell for block in analysis.block_inventory.blocks
            if block.orientation_order > 1 and not set(block.cells).intersection((*edges, *corners))
            for cell in block.cells)
method = c.compile_coarse_method(
    analysis, palette=palette, domain_features=(c.BlockFeature("solve_blocks", f2l),),
    features=(c.BlockFeature("orient_slots", edges), c.BlockFeature("orient_slots", corners),
              c.BlockFeature("place_blocks", corners), c.BlockFeature("place_blocks", edges)))
method.save("/tmp/last-layer-method.json")
loaded = c.load_coarse_method("/tmp/last-layer-method.json")  # independent offline checks
```

The fixture above supplies its goals and region; production code contains no
ordinary-cube case logic. The reproducible acceptance run is
[`probe_compiled_last_layer.py`](../v2/research/probe_compiled_last_layer.py):
it reloads the artifact without GAP and physically replays all 62,208 allowed
states. The [retained run](../v2/research-results/compiled-last-layer.json)
solves every state with four taught bodies and 230,976 cumulative endpoint
checks. Its mean is 58.13 HTM in stored stage words and 56.87 HTM after
cancellation between stages; worst physical execution is 95 HTM. The earlier
isolated oracle charged unsimplified macro words, so its 61.33 HTM is a different
cost convention. This is a suffix method, with F2L already solved.

## Palette-led workspace and method discovery

`discover_palette_profiles(inventory, palette, ambient_group=...)` examines
the complete recipes' endpoint actions. Its immutable records describe fixed
poses, fixed placements, zero phases, invariant slot sets, shared protected
regions and candidate goals. Ambient certification excludes components already
fixed throughout the reference group from the common workspace. Profiles
suggest a starting condition; they do not establish a way to reach it.

`propose_palette_goals(inventory, current_group, palette, discovery=...)`
uses compatible footprint classes, the entire current subgroup's orientation
constraints, and contacts between actual component cells. It proposes grouped
orientation, grouped placement, component pairs and connected assemblies.
Production code contains no last-layer piece lists or standard-method cases.

`discover_coarse_method` extends several such stages together. Each edge is a
complete directed palette policy over the current feature orbit. Search labels
carry the union of taught definitions across the whole selected ladder, so a
previously learned body can be reused without charging it again. The compiler
retains the selected recipe tables rather than replacing them with independently
cheaper stage policies that might introduce additional bodies.

Before retaining a commitment, search checks the group generated by all
palette recipes preserving it. If that group is smaller than the exact
residual subgroup, some remaining states cannot be solved with the available
stage-action alphabet, so the commitment is rejected. This alphabet contains
complete admitted operations that restore earlier commitments;
their internal turns and setup operations may temporarily displace protected
pieces. Before profiling, bounded powers (through four) and useful two-operation
compositions are derived from the declared recipes. Their complete endpoints
can restore a goal even when each constituent breaks it. They retain the exact
legal word, original body dependencies and inverse permissions, and consume
the existing global teaching budget. Longer unadmitted combinations remain
outside this closure. Equal orders establish this
necessary algebraic condition; complete small-case policies and physical
certificates still decide which ladders are usable within the search bounds.

```python
# Reuse the witnessed palette from the compiler example; supply no goals or region.
result = c.discover_coarse_method(
    analysis, palette=palette, max_taught_bodies=7,
    beam_width=1, max_expansions=6, max_stages=6, max_candidates=8,
    preference="recognition", timeout=90)
if result.method is not None:
    result.method.save("/tmp/discovered-method.json")
    result.method.write_guide("/tmp/discovered-method.md")
    print(result.candidates[0].case_counts)
print(result.metadata)
```

The default search bounds include a beam of 12 labels, 64 expansions, eight
stages and at most 128 observations per proposed stage. Candidate, alignment,
policy-subset and workspace limits are recorded in metadata. Search is bounded;
`no_method_found` does not prove impossibility. Every returned method still has
exact subgroup, complete case-fiber and physical witness certificates.
`domain_features=` explicitly fixes a starting contract; omitting it requests
workspace inference. An inferred protected workspace remains a starting
contract, and application rejects states outside it before taking any steps.
The recognition preference ranks complete methods by the largest case table
and total raw observations before execution cost. During small-group discovery
(ambient order at most 512), a shortest-first independent endpoint basis also
estimates the cost of the remaining action family before a greedy commitment.
This avoids cheap local goals that force expensive restoring operations later.
The estimate ranks proposals; exact certificates establish coverage. Candidates
retain the alternatives that trade
recognition counts, stage count, taught definitions and recipe costs. Use
`result.select_candidate(candidate.id)` to compile one of those alternatives
from its existing certificates and recipe tables without repeating discovery.
This returns a new result and rechecks the same global taught-definition limit.

The [palette-only acceptance probe](../v2/research/probe_discovered_last_layer.py)
uses the narrow settings shown above, supplies no workspace or stage goals,
and infers exactly the 62,208-state F2L starting domain. It discovers edge
orientation, corner placement up to U, corner orientation, absolute corner
alignment, one edge's placement, then the remaining edges: case counts
`8, 6, 27, 4, 4, 3`. The [retained run](../v2/research-results/discovered-last-layer.json)
loads its portable artifact without GAP and physically solves all 62,208
distinct states with four taught bodies and 300,960 cumulative endpoint
checks. Mean stored-stage cost is 63.72 HTM; mean concatenated execution is
62.47 HTM, with worst 115. Discovery took 371.67 seconds and exhaustive native
execution 90.98 seconds. Repeated prefix/scaffold certification remains a
performance limitation. This recognition-directed result has 52 raw
observations, compared with 71 in the faster seeded four-stage control;
it demonstrates goal discovery and coverage rather than competitive length.

`stage_policy_frontier` exposes the per-stage alternatives independently. Its
Pareto frontier can retain a slower policy that reuses known bodies alongside
a faster policy teaching another one. `max_taught_bodies` includes setups and
standalone adjustments longer than `max_short_setup_htm` (default four moves),
using stable `setup:`/`adjustment:` definition IDs. Short declared adjustments
remain separate execution operations. Search costs sum recipe HTM before
cancellation; `method.additive_costs()` measures the compiled stage words and
can therefore be lower.

## Placement up to a shared alignment

`BlockFeature("place_blocks_up_to_alignment", cells,
alignment_permutations=...)` accepts a complete finite physical adjustment
group, including identity. Every adjustment must retain the selected region
and belong to the preceding subgroup. The observation transports a set of
ordered placement rows; its stabilizer is exact and its portable certificate
checks the physical adjustments, including their action on earlier goals.
The guide lists equivalent placement patterns, and recognition diagrams show
their realizable placements and orientations.

Discovery derives candidate alignment groups from declared standalone
adjustments. A corner-placement goal up to U has six observations rather than
24. The following edge-placement stage must couple the corner and edge
regions under the same adjustment: independent allowances leave a relative
half-turn. The coupled ladder has indices `8, 27, 6, 12, 4`; the final four-case
stage chooses the common absolute alignment.

## Constructive workspace entry and adaptive assemblies

`compile_workspace_method(suffix, ...)` attaches bounded constructive entry
to a certified continuation. Entry builds the continuation's inferred region
from a colored state, then hands off only after the exact suffix domain accepts
that state. Current entry domains must be full-pose component goals
(`solve_block` or `solve_blocks`). Bandages must have their reference shape
restored first; transporting other shapes into that frame remains separate.

`propose_workspace_anchors(inventory, domain_cells)` derives an initial anchor
from geometry. It finds faces untouched by the target region, then groups the
marked components nearest the opposite face's axis. For the inferred ordinary
F2L region this proposes the four bottom edges together. It uses actual cells
and whole physical components, with no corner/edge lists or standard-method
cases. A fused component is never split to manufacture an anchor.

`propose_relative_assemblies` grows connected collections through real cell
contacts. `observe_relative_assembly` recognizes their faithful component poses
under one common allowed rigid cube rotation, including joined pairs away from
their final slots. Matching placement alone does not count if a component is
twisted. Such a relative predicate is a union of framed arrangements and need
not be a subgroup; it remains outside the stabilizer-chain feature language.
`rank_relative_assemblies` exposes reusable proposals and per-state choices.

The workspace wrapper first builds a proposed anchor, then prefers joined
collections and jointly completes nearby unsolved components. Its collection
order depends on the scramble. Only explicitly completed goals become
commitments; pieces solved incidentally can still move. This avoids adding
unnecessary protections while building the workspace.

`ConstructiveEntryController.plan_step(state, feature,
protected_features=...)` reads the full poses of the target and protected
components, and searches only declared witnessed palette recipes. Small
complete single-component, pair and triple pattern tables provide admissible
lower bounds. Oversized tables are discarded completely; their partial results
are never used as a coverage claim. The controller combines distances by their
maximum and applies bounded IDA* to the larger joint observation. It does not
enumerate the entire F2L observation orbit. Accepted sequences may temporarily
displace commitments; independent physical replay checks their restoration and
the new goal at the endpoint. The same accepted word works throughout its
observed fiber because the retained component poses have a closed action.

```python
# suffix is result.method from palette-led discovery, or a saved CoarseMethod.
method = c.compile_workspace_method(suffix, max_taught_bodies=7)
application = method.apply(colored_state)
print(application.status, application.turn_sequence)
print(application.metadata)
method.save("/tmp/workspace-method.json")
method.write_guide("/tmp/workspace-method.md")
```

The default entry alphabet declares original loops, their inverses and squares
as standalone adjustments, retaining the cheapest declaration of equal effects.
On the ordinary cube these are the 18 elementary HTM face turns. An explicit
`entry_palette=` restricts entry to its permitted recipes, including directed
body permissions. Available entry definitions and used suffix definitions share
one `max_taught_bodies` budget, including long adjustments and setups. Computed
entry words are sequences of those operations, rather than additional named
bodies; they are currently generated by search, rather than recognized from a
finite human case table. Adding entry operations leaves the suffix's original
palette and preservation-based inference intact.

Defaults bound corrections at 12 additive recipe HTM and 20,000 expanded nodes,
with 100,000 expanded nodes across a complete entry. Up to six collections are
considered per commitment and 24 commitments are allowed. Pattern preparation
has separate bounds: 20,000 observations per pattern, 16 additional joint
patterns per correction, and a bounded cache. Every single-component pattern
is attempted too. These bounds constrain computational work separately from
the vocabulary. `controller_options=` and the wrapper limits allow adjustment.
Failures such as `node_limit`, `depth_limit` and `outside_action_orbit` are
recorded; the wrapper returns `entry_limit` with its verified partial progress.
It does not call an unrestricted colored solver or computational transversal
fallback. Saved workspace methods reload and execute without GAP, rechecking
their palette witnesses, global teaching budget and coverage scope.

The [workspace-entry probe](../v2/research/probe_workspace_entry.py) imports
history-free states and runs this generic production wrapper on the saved,
unseeded suffix. Its [retained sample](../v2/research-results/workspace-entry.json)
solves eight deterministic 20-turn scrambles and a separate late-pair fixture.
The eight scramble entries average 29 stored-stage HTM before cancellation
between corrections, with complete physical solutions averaging 75.75 HTM.
Their entry choices form four distinct chains. An independent fused
four-state bandage is covered exhaustively with only clockwise U declared;
repetition supplies its inverse effect without granting an undeclared inverse
call. Sampled ordinary success is not complete entry certification.

`WorkspaceMethod.human_method_complete` remains false. Its scope is
`bounded_constructive_entry_then_certified_domain_suffix`: the existing suffix
retains exact complete coverage over its start domain, while each successful
entry correction has a concrete observed-fiber and physical witness. Remaining
work includes complete human entry rules, choosing workspaces by entry plus
continuation cost, and guarded choices among several relative block frames.

## Automatic methods from a bandage alone

`discover_method(bandage)` packages automatic palette selection, bounded
planning and physical shape restoration behind one call. No algorithm words,
workspace goals, recognition features or search settings are required.

```python
result = c.discover_method(bandage)
if result.method is not None:
    application = result.apply(colored_state)
    print(application.status, application.turn_sequence)
    print(result.write_guide())
```

The separate [Alcatraz action-family notebook](../v2/examples/action-family-methods/Alcatraz.ipynb)
uses this interface on Alcatraz, with two code cells: bandage input and staged
guide generation. The ordinary-cube notebook uses the same minimal workflow.

Automatic selection checks a bounded built-in vocabulary against the actual
bandage. Blocked words and words that fail to close at the reference shape are
rejected. Shared physical preservation chooses a coherent family, without
ordinary piece lists or an unbandaged-shape branch. When familiar families are
unavailable, witnessed native root loops provide algorithm bodies. Long loops
and their explicitly permitted inverses share one teaching definition. Every
selected action retains its original-loop certificate.

Derived powers and restoring compositions are profiled before stage selection.
`BlockFeature("solve_blocks_up_to_actions", cells, alignment_permutations=family)`
expresses full-pose completion up to a small residual physical action subgroup.
The supplied family must be a complete group of endpoint permutations, preserve
the named region and belong to the entire preceding subgroup. Its transported
pose-set observer includes orientation, so it can express equal relative phase
without requiring zero phase. Duplicate projected families share one proposal.

The guide derives certified conditional instructions from complete observation
fibers. Visible placement and phase readings choose a complete operation;
repetition and re-observation strictly decrease a finite progress rank. The
renderer keeps original body names A, B, C… and displays exact Block action
definitions and Structure in letters, inverses and powers. Phase marker tables
give physical facet positions for the readings. These rules retain the saved
policy's original-body calls; instruction boundaries can lose turn cancellation,
so commanded and fully simplified physical costs are reported separately.

On Alcatraz, automatic discovery now finds the unseeded ladder
**324 → 54 → 6 → 3 → 1**, with **6, 9, 2, 3** observations. It places the three
fused pairs (their footprint fixes their full pose), prepares the singleton
corners at home with equal phase, orients the singleton edges using A⁻¹, then
finishes the common corner phase with A² or A⁻². This keeps five learned bodies.
The alternative order uses A⁻¹ while the corners still have a common residual
phase, then a power of A that preserves the finished edges. No Alcatraz piece
identities, goals, ordering or cases are supplied to production discovery.

The [compact-method validation script](../v2/research/validate_compact_automatic_methods.py)
exhaustively checks all 324 reference-shape states, all stage observation fibers,
every prior commitment at each complete instruction and stage boundary, and
offline portable certificates. It also checks other bandages and the ordinary
cube. Measurements are retained in
[compact-automatic-methods.json](../v2/research-results/compact-automatic-methods.json).
The notebooks keep only bandage input and guide generation; experiments live
in research scripts.

The largest Alcatraz stage has nine observations. Its preparation instructions
use a 3×3 grid of one corner's current footprint and one relative-phase reading;
the full method has ten distinct instruction forms across four stages.
Exhaustive complete-word cost averages 43.24 HTM with worst 79. Stored-stage
cost before cancellation between stages averages 47.56 HTM with worst 80;
executing displayed commands separately averages 48.83 HTM with worst 84 before
cancellation between commands. The
[portable certificate](../v2/research-results/compact-alcatraz.method.json) and
[reference guide](../v2/research-results/compact-alcatraz-guide.md) are retained.
The derivation bounds and greedy action-family score limit discovery quality;
they do not establish global optimality. Shape restoration still uses the
computational shape graph and has no compact human recognition certificate.

The larger-group route searches for a protected workspace and continuation,
then adds constructive entry with a separate generating alphabet. That entry
alphabet must fit alongside the suffix within the same seven-definition
default budget. Elementary root operations of up to four moves are short
adjustments. Entry depth adapts to actual algorithm lengths; node bounds remain
finite. The ordinary cube automatically selects the existing four bodies and
U adjustments and can reuse the ordinary notebook's continuation cache.

For exact reference groups of at most 512 elements, a failed or vacuous staged
search can instead compile one joint full-pose correction stage over the whole
group. Its cases use the same witnessed palette machinery and teaching budget.
This establishes complete computational coverage, at the cost of a potentially
large recognition table. It does not claim to discover a compact CFOP-like
method for those bandages.

The returned `AutomaticMethod.apply(state)` observes the current shape and
restores the exact reference shape through its retained complete shape graph
before running the inner policy. It does not read or invert scramble history.
`shape_turn_sequence` and `method_application` expose the actual two execution
parts. The concatenated word is checked by independent native replay.

`result.metadata` identifies the route and actual algorithm selection;
`method.coverage_complete` distinguishes full computational coverage from
bounded workspace entry. For changing-shape bandages, `human_method_complete`
remains false because the shape-graph instructions have not been compressed
into human recognition rules. Mathematical coverage does not measure the
usability of a large joint-state case table.

Defaults stop shape exploration at 10,000 vertices and reject oversized
original-loop workloads before running GAP. Incomplete preparation returns
`analysis_limit` or `preparation_limit`; bounded search failure returns
`no_method_found`. These are computational limits, not proofs that a bandage
has no method. The few optional public controls are `max_shapes`,
`max_taught_bodies`, `timeout`, `progress`, `cache_dir` and `force`. `timeout`
bounds each GAP operation rather than the entire discovery. The default cache
uses `v2/.cache/human-methods` in this checkout, or `.bce-cache/human-methods`
under the working directory elsewhere; `cache_dir=None` disables caching.

The earlier [automatic acceptance probe](../v2/research/probe_automatic_bandage_method.py)
checks native, history-free states on frozen and fused-U fixtures, Alcatraz and
Bicube Fuse. Its archived [report](../v2/research-results/automatic-bandage-method.json)
records all 415 tested inputs solved, with 806 goal endpoint checks. On Alcatraz
and Bicube Fuse, it exhaustively tests one changing-shape fiber of respectively
324 and 60 colored states, plus varied legal-walk samples. The complete shape
and root-policy certificates support full computational coverage; those native
replays do not enumerate every shape/colored-state combination.

## Viewing palette-led discovery in the ordinary-cube notebook

The [Unbandaged3x3 notebook](../v2/examples/action-family-methods/Unbandaged3x3.ipynb) runs this
pipeline through the automatic API. It has two code cells: edit the bandage,
then generate the staged guide. Palette selection, workspace discovery,
constructive-entry limits and caching are handled by the method call.

```python
method = c.discover_method(bandage)
display(Markdown(method.write_guide()))
```

The guide describes workspace entry, available operations and the complete
continuation cases. First discovery can take several minutes; later calls
reuse the revalidated local cache. Native scramble experiments and detailed
performance measurements remain in the research probes and acceptance reports.

## Later deliveries

1. **Human review and visual integration: Delivery 6.** Presentation is accepted,
   and the Pocket Cube follow-up now selects symmetry templates and shared pieces.
   Gather solving feedback on its cases, regrips and memory demands. Broader
   usability review remains separate from exhaustive coverage checks.
2. **Symbolic preparation for larger groups.** Use standard stabilizers,
   orbits and transversals with original-loop witnesses. Certify subgroup
   indices, cases and terminal triviality without enumerating all of `H`.
3. **General integration.** Expand the CLI and guide views as review identifies
   useful improvements.

These deliveries can reuse the current Rust engine. Broader geometric feature
chains and human paths through the shape graph remain separate followups.
