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

The stage planner supports two feature kinds for a specific colored block
`b`, identified by its reference inventory entry and member cells:

| Feature | Observation from a `BlockAction` | Solved value |
| --- | --- | --- |
| `place_block` | `destinations[b]`: the occupied reference footprint | `b` |
| `solve_block` | `(destinations[b], phases[b])`: footprint and observable orientation in the inventory frames | `(b, 0)` |

These observations use the exact action and phase conventions documented in
[block-actions.md](block-actions.md). A phase is a modular coordinate in the
declared source and destination frames; it is not a general instruction to
twist a block independently of the rest of the puzzle. Blocks with orientation
order one need placement alone. Unmarked center spin and independent virtual
core spin are outside the observable 48-sticker model.

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
unobservable point sets contribute no stage. The old predicates in `usage.py`
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

The observation orbit has size `[Hi : Hi+1]`. A representative of each orbit
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
`c.BlockFeature(kind, cells)` values. `kind` is `place_block` or `solve_block`;
`cells` must be the exact member cells of one reference inventory block.
Features use physical member-cell identities, not arbitrary bandage labels.
For example, the automatic list can be supplied explicitly:

```python
manual = c.plan_human_stages(
    plan, strategy="manual",
    features=[stage.feature for stage in plan.stages],
    max_group_elements=10_368,
)
```

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
JSON encodes both as arrays. Cases include the already-solved observation.
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
guide explains the reference convention, footprint/sticker recognition cues,
stage progress, complete case tables, shared algorithm definitions and physical
move sequences.
A cap stop produces an incomplete report rather than a claimed solution.
This guide is a computational baseline. For visual recognition cases, use the
repertoire guide described below. Human review is separate from coverage.

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
algorithm. The minimal [BandagedPocketCube notebook](../v2/examples/BandagedPocketCube.ipynb)
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
[`Most Signatures Cube notebook`](../v2/examples/MostSignaturesCube.ipynb).

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
