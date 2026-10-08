# Exact reference-block actions

8 October 2026. Shape-loop generators expose exact physical block actions as
well as their original 48-sticker permutations and legal move witnesses. The
[Alcatraz](../v2/examples/Alcatraz.ipynb) and
[Most Signatures Cube](../v2/examples/MostSignaturesCube.ipynb) notebooks show
reference inventories and one-line decorated cycles beside each reduced
generator. Block actions require no GAP installation; GAP is needed for the
existing exact group analysis and general loop solver.

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
sequence's face turns, including each half turn as one. Both notebooks show
Turn sequence immediately after Generator ID, followed by Block action and
both move lengths, and replay-check both versions against the same sticker
action.

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
block actions alongside their
sticker permutations and legal witnesses. Omitting move expansion with
`include_moves=False` does not remove the block actions. Existing group counts
remain exact integers in Python and decimal strings in JSON.

## Subsequent solving delivery

This delivery describes actions; it leaves the existing GAP sticker
factorization solver in place. A later solver will project the isotropy group
`H` to its action `P` on reference footprints and correct the lifted word in
the kernel `K`, with `|H| = |P| * |K|`. It must preserve executable witnesses,
subgroup constraints, and the coupling between coordinates. It must not
assume independent block orbits or a split extension.

In the current six-outer-face model, the footprint-fixing kernel is abelian.
A block not wholly contained in an outer face cannot move. A face-contained
block has a nonzero centroid; a rotation preserving its footprint fixes that
centroid, giving a cyclic stabilizer of order one, two, three, or four. The
observable local actions embed the kernel in a product of these cyclic groups.
This includes order-four rotations permuting constituent cubies inside a
fixed footprint, beyond the ordinary corner-twist and edge-flip kernel.
Unmarked center and virtual-core spin are excluded.

Keep a free group on the witnessed original loops, with maps to both `H` and
`P`. A quotient word then lifts through the same original generator IDs to an
executable word in `H`; after applying it, factor the remaining correction in
`K`. Every kernel basis algorithm also needs a legal move witness. GAP provides
induced actions through `ActionHomomorphism` and `OnSets`, images and kernels,
and abelian bases through `IndependentGeneratorsOfAbelianGroup` and
`IndependentGeneratorExponents`. Validate the action domain: center/core-only
blocks have no points in the faithful 48-sticker action and need separate fixed
handling. See the official [group-action documentation](https://gap-system.github.io/gap/doc/ref/chap41_mj.html)
and [abelian-generator operations](https://gap-system.github.io/gap/doc/ref/chap39_mj.html).

Later macro discovery can use affected-block support, orientation-only powers,
commutators, and conjugation within actual legal loop orbits. When choices are
otherwise comparable, prefer a small reusable algorithm library over shorter
physical move sequences. Human recognition and application rules remain
milestone six.

Measured reference-root `(H, P, K)` orders are Alcatraz `(324, 18, 18)`, Bicube
Fuse `(60, 60, 1)`, Shark Fin Soup `(36, 12, 3)`, and Most Signatures Cube
`(10368, 144, 72)`. Recompute these when implementing the projection rather
than treating these measurements as proofs. The
[roadmap](roadmap.md#fourth-milestone-solve-colored-puzzles) retains this next
delivery, exact quotient tables, and macro discovery; human recognition and
application rules remain milestone six.
