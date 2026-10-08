# Human methods from reference-shape loops

This document fixes the initial semantics for milestone six and describes the
reproducible baseline investigation and implemented stage planner. The complete
method compiler remains future work. A **puzzle solution** supplies a reusable
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
when the stage starts. The implemented planner records that stage's observation
orbit and stabilizer. A complete method will read the declared observation and
select a correction from a case table. That correction must:

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

Generation, coverage and human quality are separate properties. Records must
state the scope to which each claim applies. The implemented stage plan uses
`status: completed` or `status: limit_reached`,
`coverage_scope: chain_structure_only`, and `human_method_complete: false`.
The additional method-compiler fields below remain provisional.

| Property | Values and meaning |
| --- | --- |
| `generation_status` | `completed`: every requested part of the declared artifact was generated; `limit_reached`: an explicit resource bound stopped generation. Backend errors remain errors, rather than becoming unreachability claims. |
| `coverage_status` | `exhaustive`: every state in the declared finite domain was checked; `proved`: exact group and stage certificates establish coverage; `sampled`: only stated samples were checked; `unverified`: no coverage claim. |
| `coverage_scope` | The object checked, such as `chain_structure_only` or `method_application`, with the reference group and state count or certificate attached. |
| `quality_status` | `unreviewed`: mathematical or heuristic output only; `experimental`: a proposed human guide with stated limitations; `reviewed`: recorded human review and solving experience. Review does not prove a minimum repertoire or universal memorability. |

A completed chain investigation with exhaustive subgroup checks is still only
`chain_structure_only` evidence. It does not establish that a case policy was
generated, that its algorithms were replayed, or that a person can remember
them. Likewise a complete computational method may have unreviewed human
quality. Report heuristic scores as measured scores with their definitions.

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
original witness move expansion. These are stage-plan exports; they do not
provide the future method's application trace or guide.

There is no default group-element cap. The example explicitly selects 10,368,
the largest group in the initial validated fixture set. If the certified order
exceeds `max_group_elements`, the result is `limit_reached`, without an
enumerated group or partial stages; `terminal_order` is `None`. This is not an
unreachability result. The cap does not bound shape exploration, GAP analysis,
or the sizes of physical move witnesses. `timeout` applies to each GAP call,
not the entire preparation or Python enumeration.

## Future method records and API

The future public entry point is provisionally:

```python
# Proposed interface; not implemented by the baseline investigation.
method = c.synthesize_human_method(reference, chain="auto", **budgets)
method.save("method.json")
method.write_guide("method.md")
trace = method.apply(root_shape_colored_state)
```

Reference inputs should follow the existing isotropy and block-structure
interfaces. Applying a method requires a matching reference specification and
the declared root-shape precondition. Application should return a structured
trace of observations, selected cases, corrections and resulting stages.

The initial record boundaries are:

| Record | Required information |
| --- | --- |
| `HumanMethod` | Model and reference frame, root shape, block inventory, witnessed loop-library identity, stages, shared algorithm definitions, budgets, evidence and quality metadata. |
| `MethodStage` | Feature descriptor, features already fixed, subgroup orders and index, complete observation cases, endpoint preservation semantics. |
| `MethodCase` | Exact observable condition, correction expression, algorithm references and exact progress promise; include the identity case. |
| Algorithm definition | Existing `LoopExpression`, original-loop provenance, exact action, physical face-turn witness and measured costs. Distinguish memorized leaves from derived constructions. |
| Application trace | Input/reference checks, ordered observations and cases, replayable corrections, final state and explicit outcome. |

Use stable reference member-cell identities alongside inventory indices.
Original loop IDs are graph-local: equal root shapes alone do not establish
compatible witnesses. Record or validate the actual generator actions and
witnesses, as the current solution-options interface already does. Preserve
exact expression provenance even when a literal turn sequence is the visible
memorized algorithm.

The first guide must show the reference shape and coloring, named blocks,
entry conditions, all recognition cases, shared algorithm definitions, their
effects, stage progress and the evidence supporting coverage. JSON should
retain the same information. A chain diagram without correction definitions
is an investigation result, not the promised method guide.

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

1. **Complete baseline methods for bounded groups.** Use the retained
   enumeration witnesses to construct all legal case corrections, export a guide
   and application trace, and exhaustively validate all 324 Alcatraz root-loop
   states. Add the other small named fixtures as regressions.
2. **Better stage algorithms and shared repertoire.** Reuse bounded discovery,
   powers, commutators, conjugates and certified symmetry transfers. Search for
   feature/coset targets, keep complete fallbacks, and optimize shared move and
   decision information across the whole guide.
3. **Automatic chain selection.** Compare placement-first, block-first and
   mixed chains using correction quality, recognition complexity and repertoire
   cost. Greedy and beam searches report their limits without claiming a global
   optimum.
4. **Symbolic preparation for larger groups.** Use standard stabilizers,
   orbits and transversals with original-loop witnesses. Certify subgroup
   indices, cases and terminal triviality without enumerating all of `H`.
5. **Human review and visual integration.** Explain cases with the existing
   renderers and notebooks, record difficult examples and solving experience,
   and add a CLI once the Python and export contracts are stable.

These deliveries can reuse the current Rust engine. Broader geometric feature
chains and human paths through the shape graph remain separate followups.
