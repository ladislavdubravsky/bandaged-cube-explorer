# Exact reference-block actions

8 October 2026. Shape-loop generators expose exact physical block actions as
well as their original 48-sticker permutations and legal move witnesses. The
[Alcatraz](../v2/examples/Alcatraz.ipynb) and
[Most Signatures Cube](../v2/examples/MostSignaturesCube.ipynb) notebooks show
reference inventories and one-line decorated cycles beside each reduced
generator. Block actions require no GAP installation; GAP is needed for the
exact group analysis and both loop-factorization strategies.

## Reference identities and slots

An inventory is anchored to `loops.root_shape`, including loop libraries
extracted from a nonzero graph root. A block's reference member-cell tuple
identifies it throughout the calculation. Normalized partition labels can
change after a move and are not physical block identities. At the reference
shape, the same member-cell tuples name slots; cycle notation describes how
their contents move.

Singleton names distinguish `Corner UFR`, `Edge UF`, and `Center U`, while their
signature type remains `111`. Larger names retain their actual member cells
and signature metadata, such as `Pair FL-DFL` or `Clock U-UF`. Cell names use
the established `CELL_NAMES` spelling, including `DFL` rather than `FLD`.
Connected noncuboid inputs retain their actual member cells and an absent
cuboid type. No hull completion or implicit-bond merging changes the physical
pieces being described. An independent virtual core is omitted from the human
inventory; actual core bonds remain part of their physical block.

A loop returns to the reference partition, so its block destinations are other
reference footprints. An off-root scramble need not permute those footprints.
Restore its shape before interpreting its residual as a reference-block
action. The original loop IDs and replayable face-turn witnesses remain
available independently of these descriptions.

## Decorated cycles

The one-line notation is a deterministic product of disjoint cycles. Each
suffix annotates the transition **from that source entry**, in the
**destination's reference orientation frame**. For example,

```text
(UFL- UFR UBR+)
```

moves the contents of UFL to UFR with phase minus one, UFR to UBR with phase
zero, and UBR to UFL with phase plus one. This retains every individual phase;
the total phase around the cycle alone does not determine the action.

`(UFL+ UFR+ UBR+)` is one three-cycle whose three transitions have phase plus
one. `(UFL+)(UFR+)(UBR+)` instead gives three in-place twists. Decorated
one-element cycles are retained; only blocks whose slot and observable
orientation are both unchanged are omitted. Identity is `()`. Larger block
names are bracketed to keep member-cell hyphens clear, for example
`([FL-DFL] [FR-DFR] [BR-DBR])`.

The inventory supplies each block's orientation order:

| Order | Nonzero suffixes | Interpretation |
| --- | --- | --- |
| 1 | none | No additional observable orientation coordinate |
| 2 | `+` | Edge flip or a symmetric block's half turn |
| 3 | `+`, `-` | Corner twists by one or minus one |
| 4 | `+`, `++`, `-` | Quarter turn, half turn, or inverse quarter turn |

A bare entry has phase zero. Corner `+` is the ordinary clockwise twist and
`-` the counterclockwise twist; edge `+` is the ordinary flip. An orientation
suffix inside a cycle belongs to that source transition. An exponent outside
a cycle raises the whole action to a power. Disjoint cycles describe the
complete effect; they need not be individually executable loops in this
puzzle's isotropy group.

For Alcatraz, loop `L142` has witness
`U' R U R R F R F' F' U F U'`. All cubie positions are fixed; UFR, UFL, and UBR
have twist two, and UR and UF are flipped. Its notation is equivalent to
`(UFR-)(UFL-)(UBR-)(UR+)(UF+)`, with the formatter choosing the deterministic order
`(UBR-)(UR+)(UFL-)(UF+)(UFR-)`.

## Exact rotations and consistent frames

The exact action recovers each block's destination and proper rotation from
the faithful sticker action, including both cubie locations and sticker
directions. Occupied cells alone cannot recover corner twists, edge flips, or
rotations within a symmetric footprint. Blocks containing a corner or edge
have an observable rigid rotation. Unmarked center spin and virtual-core spin
are excluded rather than assigned arbitrary rotation labels.

Frames are fixed once for each inventory, rather than selected separately for
each generator. A template is chosen for each proper-rotation class of
footprints, together with fixed rotations taking that template to every
reference slot. The residual rotation in those frames lies in the template's
rotational stabilizer and gives the modular phase. Thus an asymmetric pair can
have order one even when transporting it changes its constituent cubie
twists or flips. A symmetric bar can have order two, and a fully fused outer
face can rotate with order four while its footprint stays fixed.

For each footprint class, the template is the lexicographically least sorted
member-cell tuple among its proper rotations. Slot frames choose the first
matching rotation in the engine's fixed order of 24 proper rotations.
Singleton corner and edge frames additionally match the ordered Kociemba
sticker normals, so their phases agree with the ordinary cubie arrays. For
larger blocks, the positive stabilizer generator rotates clockwise about the
outward template centroid; an order-two half turn has only one nontrivial
choice. Blocks not wholly contained in an outer face are immobile in this
model and have order one.

Inventory records expose `template_cells`, `frame`, and `positive_rotation` so
frames are reproducible. A rotation is a signed-axis tuple: its entry `a[i]`
means `output[i] = sign(a[i]) * input[abs(a[i]) - 1]`, with physical axes right,
back, and up. Identity is `(1, 2, 3)`. Center/core-only blocks have no observable
rotation and use `None`, with orientation order one.

Let `r_i` carry the template to slot `i`, `R_i` carry the source block to its
destination `pi(i)`, and composition apply the rightmost map first. The local
rotation is

```text
a_i = inverse(r_pi(i)) compose R_i compose r_i
```

Executing action `g` followed by `h` transports the orientation coordinate
with the block permutation:

```text
pi_gh(i) = pi_h(pi_g(i))
q_gh(i) = q_g(i) + q_h(pi_g(i))  modulo the block's orientation order
```

Inversion moves each negated phase to the corresponding inverse source slot.
Adding phase arrays at unchanged indices, or reversing a cycle while leaving
negated suffixes on the same names, gives the wrong result. Exact composition,
inversion, and powers retain agreement with the full sticker action.

## Python access and exports

```python
import bce_v2 as c

loops = c.isotropy_loops(c.fixture("Alcatraz"))
inventory = loops.block_inventory
for block in inventory.blocks:
    print(block.name, block.type, block.orientation_order)

for generator in loops.generators:
    action = generator.block_action
    print(f"L{generator.id}", generator.turn_sequence, action.notation)
    record = action.to_dict()

analysis = loops.analyze()
assert analysis.block_inventory is inventory
for generator in analysis.generators:
    print(f"L{generator.id}", generator.turn_sequence, generator.block_action.notation)
```

`generator.turn_sequence` combines adjacent same-face turns for display,
including `R R` and `R' R'` as `R2`, and cancels inverse turns. The original
legal witness remains `generator.moves`; `generator.qtm_length` retains its
unsimplified quarter-turn cost. `generator.htm_length` counts the displayed
sequence's face turns, including each half turn as one. Algorithm tables in
both notebooks show Turn sequence, Block action, HTM length, and Affected
blocks. They replay-check both witnesses against the same sticker action;
original IDs and QTM costs remain available through the API and exports.

For a separate reference, use `c.BlockInventory(reference)` or
`c.block_inventory(reference)`. Inputs can be a shape, 27-cell list, state
specification, loop set, or isotropy analysis. `inventory.action(permutation)`
accepts a 48-image source-to-destination permutation, or a `State` using the
same reference specification. It validates reference-shape preservation and
rigid block rotations in the current outer-face model; this does not prove
bandaged reachability. `inventory.identity()` constructs the identity action.
`c.cell_name("FLD")` returns the canonical `"DFL"` spelling.

`action.destinations`, `action.phases`, and `action.rotations` are immutable
source-indexed arrays. `action.permutation` and `action.to_permutation()`
reconstruct the authoritative 48-sticker action. `g.then(h)` executes `g` and
then `h`; `g.inverse()` reverses the action; `g ** n` applies any integer power,
including zero and negative powers. These operations retain the same reference
inventory and its frames.

The inventory and actions are immutable. `inventory.to_dict()` and
`action.to_dict()` supply deterministic structured records; `to_json(path=None)`
returns JSON and optionally writes it. The standalone formats are
`bce-v2-block-inventory` and `bce-v2-block-action`, both version one. Inventories
include reference cells, names, signature metadata, frames, and orientation
orders. Action records contain the reference shape, notation, and source-indexed
transitions with source cells, destination cells, rotation, phase, and modulus.
The original generator's sticker permutation remains authoritative and need
not be duplicated in each action record.

Loop and isotropy-analysis version-one exports add `block_inventory`; each
generator record adds `block_action`. With move witnesses included, generator
records also include `turn_sequence` and `htm_length`; `include_moves=False`
omits `moves`, `turn_sequence`, and `htm_length` without expanding witnesses.
Existing fields remain intact. Loop-solution algorithms also retain their
block actions alongside their sticker permutations and legal witnesses. Omitting move expansion with
`include_moves=False` does not remove the block actions. Existing group counts
remain exact integers in Python and decimal strings in JSON.

## Block placement and abelian kernel correction

The opt-in `quotient_kernel` strategy is implemented alongside the default
`sticker` factorization. It projects the isotropy group `H` to its action `P`
on reference footprints, lifts a placement word through the original legal
loops, and corrects the remaining action in the footprint-fixing kernel `K`.
The exact orders satisfy `|H| = |P| * |K|`. Exact quotient membership followed
by residual kernel membership establishes reachability. The lifted word is
verified against the full sticker action, retaining physical subgroup
constraints and the coupling between coordinates without assuming independent
block orbits or a split extension.

```python
solver = c.LoopSolver(analysis, factorization="quotient_kernel", timeout=60)
structure = solver.block_structure  # Computed lazily and reused.
assert structure.group_order == structure.quotient_order * structure.kernel_order
for algorithm in structure.basis:
    print(algorithm.id, algorithm.turn_sequence, algorithm.block_action.notation)
    print(algorithm.order, algorithm.expression)

result = solver.solve(imported, metric="HTM", max_expanded_moves=100_000)
if result.status == "solved":
    assert imported.apply(result.solution).is_solved
    print(result.shape_solution)
    print(result.placement_expression, result.kernel_expression)
```

`c.analyze_block_structure(reference, ...)` also computes the structure without
preparing a solver, accepting the same puzzle, loop-set, and isotropy-analysis
references used by the loop interfaces. A complete graph can select its root
explicitly. Both notebooks show exact `H`, `P`, and `K` orders and the
independent kernel basis next to the original loop library.

Each witnessed `KernelAlgorithm` has an ID such as `K0` local to the prepared
reference library, a cyclic `order`, the full `permutation` and `block_action`,
and an expression and `steps`
in original `L` loops, and a simplified `turn_sequence`. `htm_length` counts
the displayed face turns; `qtm_length` retains the unsimplified quarter-turn
cost of its original-loop expansion. Basis independence concerns cyclic
factors of the actual kernel, rather than arbitrary per-block orientation
coordinates. Every basis algorithm fixes all reference footprints and has a
legal reference-loop witness.

`structure.to_dict(include_moves=True)`, `to_json()`, and `save(path)` export
version-one `bce-v2-block-structure` records with the reference inventory,
original generator IDs, witnessed basis, and exact `H`, `P`, and `K` orders as
decimal strings. `include_moves=False` keeps each kernel algorithm's original
loop steps and exact action without expanding its face-turn witness.

A quotient solution retains separate `placement_steps` and `kernel_steps`,
their `placement_expression` and `kernel_expression`, exact `quotient_order`
and `kernel_order`, and only the referenced `kernel_algorithms`.
`placement_algorithms` supplies all original witnesses used by the placement
stage, including any whose references cancel when the complete word is
flattened. `steps` and
`expression` remain the complete correction flattened into original loop IDs,
and `algorithms` retains those original witnesses. Existing consumers can
therefore replay the original loop expression. Shape restoration remains the
separate first stage. The result's `factorization` identifies the selected
strategy. Expanded solutions are legally replay-checked; the existing
expansion limit preserves the compact stages when returning `limit_reached`.
Placement steps use original `generator_id` references; kernel steps use
`basis_id` references such as `K0`, both with signed `exponent` values. JSON
retains both stage records and exports the quotient and kernel orders as
decimal strings. This strategy guarantees neither shortest solutions nor
minimum algorithm repertoires.

Failure of quotient membership reports `block_permutation_not_in_group`.
Failure of residual kernel membership reports `kernel_residual_not_in_group`
and retains any successfully found placement word for inspection. GAP failures
and timeouts raise errors, rather than returning either unreachability result.

In the current six-outer-face model, the footprint-fixing kernel is abelian.
A block not wholly contained in an outer face cannot move. A face-contained
block has a nonzero centroid; a rotation preserving its footprint fixes that
centroid, giving a cyclic stabilizer of order one, two, three, or four. The
observable local actions embed the kernel in a product of these cyclic groups.
This includes order-four rotations permuting constituent cubies inside a
fixed footprint, beyond the ordinary corner-twist and edge-flip kernel.
Unmarked center and virtual-core spin are excluded.

A free group on witnessed original loops retains maps to both `H` and `P`,
so a quotient word lifts through the same original generator IDs to an
executable word in `H`. Kernel basis algorithms also retain legal original-loop
witnesses. The GAP backend computes the induced footprint action, its image and
kernel, and uses `IndependentGeneratorsOfAbelianGroup` and
`IndependentGeneratorExponents` for the actual abelian correction. Blocks
containing only centers or the core have no points in the faithful 48-sticker
action and are handled as
separately fixed blocks. See the official [group-action documentation](https://gap-system.github.io/gap/doc/ref/chap41_mj.html)
and [abelian-generator operations](https://gap-system.github.io/gap/doc/ref/chap39_mj.html).

Bounded algorithm discovery now uses affected-block support, powers,
commutators, and conjugation within actual legal loop orbits, as described
below. When choices are otherwise comparable, a small reusable algorithm
library remains preferable to shorter physical move sequences. Human
recognition and application rules remain milestone six.

Reference-root `(H, P, K)` orders are Alcatraz `(324, 18, 18)`, Bicube Fuse
`(60, 60, 1)`, Shark Fin Soup `(36, 12, 3)`, and Most Signatures Cube
`(10368, 144, 72)`. The structure computation derives these from the actual
reference action. The [roadmap](roadmap.md#fourth-milestone-solve-colored-puzzles)
retains exact quotient tables and further discovery improvements as followups;
human recognition and application rules remain milestone six.

## Bounded algorithm discovery and two solution views

`c.discover_loop_algorithms(analysis, ...)` builds a bounded library of exact,
witnessed root-loop algorithms. Every legal base loop can be reused, regardless
of length. Discovery explores powers, commutators, conjugates, and transfers
through actual symmetries of the reference bandage shape. Composite expressions
retain their trees, including nested constructions. Separate `shortest` and
`structured` views compare physical length with a human-oriented heuristic:
total affected-block count first, the largest constituent application's
affected-block count next, shared memory and description cost afterward,
and physical turns last. Giving a long word an opaque name or taking its
inverse does not make its description easier.

```python
library = c.discover_loop_algorithms(
    analysis, max_seed_loops=12, rounds=2, max_candidates=500,
    max_algorithms=64, max_htm_length=96,
)
for algorithm in library.shortest[:8]:
    print(algorithm.turn_sequence, algorithm.block_action.notation)
for algorithm in library.structured[:12]:
    print(algorithm.structured_turn_sequence, algorithm.block_action.notation)

options = solver.solve_options(
    imported, library=library, metric="HTM", max_states=500, max_depth=3,
)
for option in (options.shortest_found, options.most_structured):
    if option.status == "solved":
        assert imported.apply(option.solution).is_solved
        print(option.shape_solution, option.structured_turn_sequence)
```

Power proposals first prioritize the footprint-permutation order, which can
isolate an orientation-only action. They also include every nontrivial proper
divisor of the full action order: for example, fifth and seventh powers can
separate the two cycle lengths in an order-35 action. Identity effects are
omitted, and candidate and length budgets bound which proposals are evaluated
and retained. An inverse alone is not proposed as a structural improvement.
A flattened literal alternative is considered when its linear description is
cheaper than the expression it replaces, without an arbitrary turn threshold.

Each `LoopAlgorithm` exposes its `id`, expression tree, simplified
`turn_sequence`, exact `block_action`, physical `htm_length` and `qtm_length`,
affected-block `support`, `is_kernel`, and `structure_score`. `support` holds
affected source-inventory indices, including blocks twisted in place. Lower
structure-score tuples start with total affected-block count, then the largest
constituent application's affected-block count, followed by shared memory and
description cost and physical length. For equal-effect solutions, the first
count is the same, so the constituent count favors localized intermediate
applications. Both physical and structured
representatives can remain available for the same exact action.
`library.to_dict()` exports witnessed records and bounded-discovery metadata.
`library.metadata` exposes limits, observed seed/candidate/round counts, pruning
counts, limit flags, `symmetry_count`, `symmetry_transfer_count`, and
`exhaustive=False`; the retained union is `library.algorithms`.

`algorithm.structured_turn_sequence` renders the construction in physical
moves. `(R U)3` repeats a group, `[A, B]` is a commutator, and `[S: A]` is
conjugation by setup `S`; brackets retain nesting. Inverse words are reversed
and inverted: the inverse of `R U` displays `U' R'`, and its negative third
power displays `(U' R')3`. Single-face powers use ordinary forms such as `R2`
and `R'`. Plain leaves show their actual turns without inventing a construction.
`expression.render()` keeps original loop IDs for provenance, while
`expression.render_moves(generators)` substitutes physical turn words.
`turn_sequence` remains the expanded face-turn word for executable replay.
Move lengths count expanded physical turns.

Both notebooks display one shortest-found ranking and one structured ranking.
Their algorithm tables use four columns: Turn sequence, Block action, HTM
length, and Affected blocks. The structured view uses construction notation;
the shortest view uses expanded turns. Full witnesses, expression trees, IDs,
and diagnostic metadata remain accessible through the API and exports.

`LoopExpression.loop(id)`, `sequence(...)`, `power(body, exponent)`,
`commutator(first, second)`, `conjugate(setup, body)`, and
`rotated(rotation_word, body)` retain explicit construction trees. For example,
using two witnessed loops from the current analysis:

```python
a = c.LoopExpression.loop(analysis.generators[0].id)
b = c.LoopExpression.loop(analysis.generators[1].id)
tree = c.LoopExpression.conjugate(b, c.LoopExpression.commutator(a, b))
algorithm = library.build_algorithm(tree)
print(algorithm.structured_turn_sequence)
library = library.with_expressions(tree)
```

`build_algorithm` validates the exact construction with a finite expansion
budget. `with_expressions` returns a new library considering these alternatives
under its existing bounds. Literal-turn leaves retain their original-loop
witness in the tree for provenance.

All expression leaves are legal loops at the same reference shape. In engine
execution order, `[A, B]` expands to `A B A^-1 B^-1`, and a conjugate with setup
`S` and body `A` expands to `S A S^-1`. These constructions cannot be applied to
arbitrary face-turn words without checking intermediate shapes. The kernel
`K` is abelian but need not be central in `H`: two kernel algorithms commute,
while conjugating one by a placement algorithm can change its effect.

A rotated expression displays a regrip, body, and inverse regrip, such as
`x (A) x'`. It transfers the loop only through a proper rotation preserving the
actual reference bandage shape. Bicube Fuse has two nonidentity reference-shape
symmetries, and Shark Fin Soup has one. Alcatraz and Most Signatures Cube have
none at their notebook roots, so their candidate tables contain no regrip
transfers. A root with no nonidentity symmetry supplies no such transfers.
Colored markings need not be preserved by the setup:
the frame is restored, while the loop's action is transported to other slots.
Regrips do not count as HTM face turns. `expanded_moves(generators)` produces the
legal face-only witness, and `algorithm.moves`/`turn_sequence` remain executable
by `State.apply`; its parser is unchanged. `loop_steps()` explicitly
rejects rotated trees, whose transferred witnesses need not be words in the
original named loops. Rotation words are retained in expression exports.
`symmetry_count` counts nonidentity reference-shape automorphisms, and
`symmetry_transfer_count` counts evaluated transfers within the discovery
budget. Rotated constructions reuse the body's remembered definitions.

`solver.solve_options` combines an opt-in bounded search over the discovered
library with GAP factorization through up to 24 discovered macros from each
ranking plus the original reduced generators. Retaining the original
generators preserves the full group. Enriched factorizations can find words
beyond the search-depth limit; each GAP call respects the prepared solver's
timeout. The existing solver remains a fallback. `shortest_found` favors
physical length; `most_structured` uses the total-effect and largest-constituent
counts before shared memory, description cost, and turns. Equal-effect
solutions therefore compare localization of their intermediate applications
before description cost.

Each option exposes `status`, separate `shape_solution`, loop `expression`
string and `structured_expression` tree, physical `structured_turn_sequence`
for the loop stage, full executable `solution`, physical move lengths, and used
`algorithms`. `algorithm_count` counts distinct remembered leaves, treating a
leaf and its inverse together; `original_loop_count` counts underlying
original IDs in `base_algorithms`. The ordinary
`LoopSolution.algorithm_count` continues counting original loops. Literal
leaves retain their witness construction without counting every hidden witness
leaf as a separate remembered description. These are heuristic description
counts, without a proof of minimum human repertoire. `source` identifies
`baseline`, `discovered`, `short_search`, `structured_search`,
`short_factorization`, or `structured_factorization`.

Structured physical turns describe the loop correction only; shape restoration
remains separate. The full solution includes both and is legally replay-checked.
The compact notebook comparison shows each option's shape restoration when
needed, loop-stage Turn sequence, full HTM length, and Remembered algorithms.
The ordinary `solver.solve` behavior is unchanged. `options.to_dict()`,
`to_json()`, and `save(path)` export version-one
`bce-v2-loop-solution-options` records with both trees, original witnesses,
source labels, and search metadata. `options.library_metadata` retains a copy
of discovery limits and counts, including with an automatically created library.

Discovery bounds seeds, rounds, candidates, retained library size, and witness
length. Solve state and depth budgets apply to the bounded search, with the
state cap applied separately to each objective; GAP calls use the existing
per-call timeout. Options retain `searched_states`, `search_complete`, and
`stop_reason` about the macro searches. `candidate_stop_reasons` also records
optional enrichment timeouts or expansion cutoffs. These optional cutoffs
retain the verified baseline; a baseline GAP failure still raises an error.
Both options have `optimal=False`. “Shortest found” compares available
candidates without a global shortest-path guarantee. The structural score
estimates localized, reusable descriptions without proving human memorability.

Exact precomputed tables for the block-permutation quotient `P` remain future
work. A human puzzle solution also needs recognition, legal application rules,
and coverage and progress validation beyond these computational algorithms.
