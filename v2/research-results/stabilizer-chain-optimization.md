# Stabilizer chain optimization for short cube solutions

The current ordinary-cube guide averages **216.92 HTM before cancellation
between stages**, with seven taught algorithms longer than four moves.
Its two first targets, UBR and the opposite corner DFL, already touch all
six faces. The main improvement target is a joint choice of geometric
subgoals, short legal words and a bounded taught repertoire. The number of
learned long algorithms can remain the primary constraint.

The investigation covers the current implementation, general permutation-group
methods, cube-specific subgroup features, and transfer between related
bandages. Measurements below distinguish the displayed guide, newly compiled
diagnostic methods and literature results. Production solver code and the
user's modified notebooks were preserved.

## Current guide and the source of its cost

The [current guide audit](unbandaged3x3-current-guide-audit.json) reads the saved
output in [Unbandaged3x3](../examples/stabilizer-chain-methods/Unbandaged3x3.ipynb), records its SHA256,
and extracts every expanded case word. The guide has 18 stages, 257 cases
including solved observations, and a worst additive cost of 362 HTM. Its seven
long bodies have lengths 6, 7, 10, 11, 11, 12 and 18. The older
[template measurement](unbandaged3x3-template-repertoire.json) reports 246.25
HTM for a different generated policy and should not replace this baseline.

| Part of the displayed chain | Mean additive HTM | Share of total |
| --- | ---: | ---: |
| First five stages | 15.26 | 7.0% |
| Last six stages | 123.33 | 56.9% |
| Last four stages | 92.21 | 42.5% |
| Penultimate stage alone, Solve DBL | 39.33 | 18.1% |

These overlapping rows locate the cost; they are not quantities to add.
The early choices are cheap locally and expensive through the restrictions
they impose on the tail. The DBL stage has six observations with costs
0, 17, 17, 73, 73 and 56. This is a particularly useful target for improved
late-stage algorithms or a different buffer/parity arrangement.

| Protected prefix | Unobstructed faces on the ordinary cube |
| --- | --- |
| UBR | F, D, L |
| UBR, DFL | None |
| UBR, UB, UR, BR, a compact 2x2x2 | F, D, L |
| UBR, UFR, UR, UB, UF | D, L |

A face here is unobstructed when its turn fixes the already solved cubies.
This is a useful geometric measurement, not a requirement that corrections
keep those cubies fixed at every intermediate turn. The existing solver
correctly permits temporary displacement inside a correction word.

### What the optimizer already does

[symbolic_chain_search.py](../python/python/bce_v2/symbolic_chain_search.py)
already computes weighted shortest paths on small feature orbits. Its
execution score considers missing dictionary coverage and mean cost divided
by the logarithm of the subgroup index. A bounded lookahead examines the
surviving words after a prospective target.

The search is much narrower than the public budget names might suggest:
`beam_width` is a shortlist for one-step lookahead, capped at four;
`max_methods` admits at most two adaptive feature modes. It does not retain
a beam of competing partial chains. The lookahead tests all later individual
feature orbits under the surviving pool, rather than compiling a complete
continuation. There is no direct geometric cost for consuming the last free
face, no explicit corner/edge buffer reservation, and no hard constraint of
seven bodies longer than four moves.

The next stabilizer's pool is augmented by witnessed Schreier words of the
form `r_x s r_y^-1`. Their ranking cost initially adds the three constituent
costs. Repeated augmentation can produce long words; retired entries cease
to be direct later-stage transitions, although their archived recipes can
remain ingredients in newly protected composites. Algorithm discovery and
proposal limits also affect this continuation. Algebraic generation and
complete observation coverage therefore do not establish good physical
distances.

The [dictionary retention audit](familiar-dictionary-retention-audit.json)
finds a concrete selection issue. Of 119 bounded familiar variants already
materialized during discovery, 69 exact effects survive in the final
1,024-entry dictionary. All six examined OLL variants, including Sune, and
both examined PLL variants are absent as direct effects, even after checking
matches under different algorithm IDs. They remain expressible as products
of retained words. This identifies an opportunity for stage-aware dictionary
selection or family reserves; it does not prove that importing those words
would improve every bandage or satisfy the learning budget.

[symbolic_template_repertoire.py](../python/python/bce_v2/symbolic_template_repertoire.py)
then finds shared bodies and chunks in the selected policy. Its declared
scope preserves those physical case words exactly. This is valuable memory
compression, but this phase does not search for shorter physical policies.
The current separation can commit to a physically mediocre chain before
learning that it has an excellent small presentation.

### Cost convention

For uniformly distributed elements of a reference isotropy group, each
observation coset has equal probability. Applying a fixed representative
inverse maps its coset bijectively to the next subgroup, so the residual
is again uniform. Thus the sum of case means is an **exact additive mean**,
and the sum of stage maxima is an exact additive worst case for these
deterministic tables. Both exclude cancellation across stage boundaries.

Seeded move scrambles are a different distribution; their physically
simplified totals are samples. On bandaged cubes, a long random legal walk
need not be uniform: choosing uniformly among a vertex's legal moves can
bias shape frequencies toward vertices with higher degree. Shape restoration
cost must also be included when comparing whole bandaged solutions.

Choosing an equally short representative with a different residual effect
does not improve the fixed-chain uniform additive mean. Keeping such
alternatives can improve cancellation, a particular input's continuation,
or the short words generated during chain construction. State-dependent
selection needs its own cost evaluation.

## What the literature establishes

Richard Korf's 1982 macro solver explicitly chooses subgoal order to preserve
as many primitive operators as possible, with adjacency used to break ties.
Its cube progression passes through a compact 2x2x2, a 2x2x3 and two completed
layers. It reports about 90 moves using 238 case macros, and learns invariant
macros from collisions between words having the same protected effect.
This directly supports the proposed geometric intuition, but 238 case
macros are not seven learned templates. [Korf, A Program That Learns to
Solve Rubik's Cube](https://cdn.aaai.org/AAAI/1982/AAAI82-039.pdf).

Egner and Püschel discover short words with many fixed points, adapt the
base to their supports, and improve word transversals. Their approximately
60-move result also uses **input-specific trials of short prefixes**, called
"trembling." Table 1 estimates means of 96.3, 62.7 and 53.3 quarter turns
for 1, 100 and 1,000 prefix candidates under a statistical approximation.
These are estimated expectations, not measured HTM benchmarks. The six
generators in their table are primitive face quarter turns; a human learned
repertoire size is not specified. [Egner and Püschel, Solving Puzzles Related
to Permutation Groups, sections 5 and 6 and Table 1](https://people.inf.ethz.ch/markusp/papers/game.ps).

This suggests a separate experiment within a fixed taught vocabulary:
try a small collection of legal prefixes, run the same staged policy from
each resulting state, and select the shortest complete solution including
the prefix. It adds state-dependent planning or recognition rather than
new learned bodies. For a human method, automatic per-input search needs
to become a small explainable choice rule or intuitive lookahead.

Minkwitz constructs strong generators represented by short words in the
original generators. Hulpke explains the associated transversal improvement
and recommends bases whose stabilizers retain many short words. This gives
an algebraic version of preserving free faces: preserve **cheap legal
operators**, including compound ones. Neither method guarantees shortest
physical solutions. [Minkwitz, An Algorithm for Solving the Factorization
Problem in Permutation Groups](https://www.sciencedirect.com/science/article/pii/S0747717198902024),
[Hulpke, Factorization in finite Groups, slides 14 to 16](https://www.math.colostate.edu/~hulpke/talks/decomp.pdf).

Computational BSGS objectives are different from the human objective.
For example, GAP's `MinimalStabChain` means the reduced chain for ascending
base points, not a minimum move solution or minimum-length base.
`ChangeStabChain` is useful machinery for a prescribed base; it does not choose
a good physical method. [GAP permutation-group reference](https://gap-system.github.io/gap/doc/ref/chap43.html).
The `genss` operation `FindShortGeneratorsOfSubgroup` could supply an
independent source of short subgroup words, after our physical and repertoire
checks. [GAP genss reference](https://gap-packages.github.io/genss/doc/chap3_mj.html).

## A general optimization objective

Write a chain as `H_0 > H_1 > ... > H_m = 1`. Let `D` be a taught dictionary
with legal witnesses and an allowed grammar for setup, conjugation,
commutators, inverses, powers and symmetry variants. For each stage, compute
the least physical correction costs available in that grammar for the
small observation orbit, with a certified fallback retained separately.

The appropriate additive objective is

```text
C(chain, D) = sum_i mean_q length(correction_i(q))
```

subject to full certified coverage and a bound on taught long bodies.
A fixed-dictionary model admits the recurrence

```text
V(H) = min_f [ c(H, H intersect Stab(f))
              + V(H intersect Stab(f)) ]
```

where `c` is the average cost over observation cosets. This is a proposed
optimization model derived from the uniform-residual argument above. Exact
dynamic programming can have too many subgroups; bounded rollouts, a real
beam of partial chains, and local feature swaps are practical approximations.
Joint learning requires the retained dictionary and accumulated taught bodies
in the search state. Cancellation requires additional word context or
evaluation of completed policies.

Two adjacent feature orders have the same subgroup after both features:
`H intersect Stab(a) intersect Stab(b)`. With a fixed physical dictionary,
only the two local observation tables need to change for additive scoring.
This makes swap descent and insertion search relatively cheap. If those
stages also generate new dictionary words, their downstream dictionaries
must be rebuilt or evaluated against one shared frozen pool.
Hulpke describes the analogous adjacent-swap update for ordinary bases.
[Notes on Computational Group Theory, section Changing the base](https://www.math.colostate.edu/~hulpke/CGT/cgtnotes.pdf).

A cap of seven long algorithms should be a real feasibility constraint.
Normalize inverse and permitted grip/symmetry variants consistently, and
track definition length, recipe length, setup complexity and recognition
rules alongside that cap. Otherwise any complicated instruction can be
written in single turns and appear to require zero learned algorithms.
The current 257 cases and 222 instruction families illustrate why algorithm
count alone cannot predict ease of learning.

## Controlled geometric chain probes

The [geometric probe](geometric-chain-probe.json) uses one discovered
dictionary and identical search budgets for each candidate. A diagnostic
chooser forces the selected prefix and then uses the production adaptive
continuation. The greedy control reproduces the displayed notebook's
costs, stage order and seven long bodies. Each completed method has exact
subgroup certificates; all 32 shared history-free imported scrambles solved
and passed physical replay.

| Prefix followed by current continuation | Exact additive mean HTM | Additive worst HTM | Long bodies | Sample mean HTM after simplification |
| --- | ---: | ---: | ---: | ---: |
| Greedy control | 216.92 | 362 | 7 | 209.72 |
| Compact 2x2x2 | 177.76 | 305 | 8 | 178.63 |
| Adjacent corners and three edges | 237.09 | 415 | 10 | 237.59 |
| Compact 2x2x2 then remaining corners | 154.89 | 254 | 10 | 154.16 |

All four presentations contain 22 total macros. The compact prefix is
`UBR, UB, UR, BR`; the adjacent-corner prefix is
`UBR, UFR, UR, UB, UF`. The corners-priority prefix extends the compact block
with `UBL, UFR, UFL, DBR, DBL, DFR` before returning to automatic edge
selection. These are fixed-chain controls, not Petrus methods or globally
optimized chains.

Compact clustering improves the mean by 18.1%; continuing with corners
improves it by 28.6%. Neither result satisfies the seven-long-body budget.
The adjacent-corner result is worse despite retaining two unobstructed
faces. Therefore geometry gives useful candidates, but free-face count
alone is insufficient to rank whole methods. The compact continuation
also retains an expensive penultimate corner stage averaging 41.83 moves.

Reproduction from the repository root:

```sh
v2/.venv/bin/python v2/research/audit_unbandaged_staged_guide.py
v2/.venv/bin/python v2/research/probe_geometric_chain.py --templates
```

The probe caches the witnessed dictionary and intermediate methods under
`/tmp`; its JSON records dictionary metadata, budgets, stage costs,
template sizes, scrambles and replay outcomes. Its repertoire budget is
measured after compilation, rather than enforced as a constraint.

### Short prefix trials with the existing seven bodies

The [prefix trial probe](staged-prefix-search-probe.json) keeps the greedy
control's method and vocabulary unchanged. It tries the empty prefix and
each of the 18 single face turns, solves the resulting state with the same
method, simplifies the complete prefix-plus-solution, and chooses the
shortest result.

On the same 32 imported states, this lowers the sampled mean from
**209.72 to 149.66 HTM**, a 28.6% reduction, with 31 of 32 states improving
and a sampled selected worst of 194 HTM. All 608 complete candidate
solutions passed replay. No additional long body is taught.

This demonstrates substantial execution headroom within the existing
vocabulary. It is a computational selection experiment, not an exact
uniform-group mean or evidence that a human can efficiently choose among
19 complete continuations. Its practical successor is a small set of
recognizable choice rules or a short lookahead procedure.

```sh
v2/.venv/bin/python v2/research/probe_staged_prefix_search.py
```

## Geometric criteria for bandaged cubes

For a current subgroup `H_i`, directly count root face turns that are legal
and whose faithful effects belong to `H_i`. On an ordinary cube this reduces
to the face-incidence calculation above. On a bandaged cube, use actual move
legality: an untouched face can still be physically blocked.

Extend this to the distribution of short legal root loops that survive a
candidate feature. Useful measurements include their expanded physical
lengths, how many target observations they reach, orbit distances, and the
number of future stages for which each reusable template remains applicable.
Counting generators without accounting for redundancy or covered
observations can reward a large but unhelpful pool.

Let `L_i` be the subgroup generated by available cheap legal loops in `H_i`.
Transitivity of `L_i` on a proposed feature's full `H_i` orbit is sufficient
for stage coverage using those loops. Multiple `L_i` orbits identify where
additional protected recipes must bridge observations. This turns geometric
freedom into an exact coverage measurement. Coverage still needs weighted
distances: the greedy control already spans every residual subgroup and
reaches every observation in these probes.

Prefer compact protected footprints and preserve adjacent working regions
and buffers. A block-face incidence hypergraph supplies inexpensive
candidate ordering: blocks are vertices, face layers are hyperedges, and
stabilizing scattered blocks removes many available hyperedges. The
decisive score should still come from actual legal loops and their physical
costs. A corner touches three faces while an edge touches two; fused blocks
can obstruct much larger working regions.

The shape graph also offers choices of workspace and reference root.
Two roots in one component have conjugate isotropy groups, but transport
along a path `p` turns a loop `a` into a witness `p a p^-1`, costing at most
`2 length(p) + length(a)` before simplification. A nearby shape with useful
free faces can outperform the nominal root. Consecutive loops at the same
workspace can share transport, rather than paying setup and undo separately
for each loop. Score transport together with colored correction and final
shape restoration.

### Corners and orientations

The three corner orientations do not imply corners should always be solved
first. Initially a fully solved corner has `8 * 3 = 24` observations, while
a fully solved edge has `12 * 2 = 24`. Their information content is equal.
Restricted orbit sizes, physical distances and the freedom retained for
later pieces decide their relative cost. A position-only corner has eight
observations and an edge twelve, but orientation remains to be solved.

The [block action model](../../docs/block-actions.md) already exposes
footprint permutations and cyclic orientation phases of orders 1, 2, 3 and
4. Its footprint-fixing kernel is abelian in the current outer-face model.
This supports exact modular-span tests for a small set of reusable
orientation effects. It does not imply that solving every placement first
is efficient: that can leave expensive pure twists and flips after all
working freedom has been consumed.

Reference blocks can only permute within compatible footprint classes.
Their decorated permutations give a smaller structured action than the
48 sticker points, and actual `H_i` orbits can split those geometric classes
further. Use those restricted orbits and the actual kernel, rather than
assuming every ordinary-cube permutation or orientation combination is
reachable. Abelianity of the kernel does not establish that the extension
by the placement group splits.

Phase conventions can themselves be optimized. Changing slot gauges by
values `a_i` transforms an action phase to

```text
q'_g(i) = q_g(i) + a_i - a_pi_g(i)  modulo the class orientation order.
```

Choosing gauges that make useful cheap generators preserve zero phase can
expose a convenient orientation subgroup. Cycle sums constrain which
generators can simultaneously be made phase zero. This is a research
proposal, and any chosen convention must remain observable and teachable.

## Cube subgroup features beyond individual pieces

Petrus preserves a compact block, then corrects bad edges before continuing
with the remaining two free sides. Its early stages also assemble pairs and
choose among alternative blocks. Those relative relationships are broader
than a fixed chain that permanently solves one named cubie at a time.
Petrus reports 55 to 60 moves for speed and 40 to 45 when optimizing moves;
these are his reported averages, not a controlled seven-algorithm comparison
with our uniform-group statistic. [Petrus introduction](https://lar5.com/cube/),
[2x2x2 construction](https://lar5.com/cube/fas1.html),
[2x2x3 expansion](https://lar5.com/cube/fas2.html),
[edge orientation](https://lar5.com/cube/fas3.html).

Generalize the recognized features to include:

- A pair or compact assembly fixed relative to itself, before anchoring it
  to a particular face or corner.
- A selected block family occupying a region setwise, while internal
  identities remain free.
- Orientation of an entire invariant block class, with permutation still
  allowed.
- A designated small residual region that retains a corner or edge buffer,
  plus an explicit coupled odd corner/edge permutation bridge.

A strict chain feature must have a well-defined action and its solved
condition must identify the intended subgroup or coset. Building a particular
pair anywhere need not have a single-subgroup target: it may require several
accepted observations or a separate subgoal graph, followed by anchoring
the pair. Similarly, zero phase for one named block while its location
remains arbitrary need not define a subgroup; zero phases for a whole
permutation-invariant class do. Ordinary-cube parity
and orientation-sum constraints must be respected; independently selected
corner and edge generators may miss the coupled odd-permutation component.

Known ordinary-cube reduction subgroups are useful candidate sources, rather
than mandatory methods. If `R` is such a subgroup and `H` is a bandaged root
group, `H intersect R` is a valid algebraic stage. Its physical correction
words must be found in the bandage's legal loop language. A short ordinary
word for an element of `H` can still be blocked on the bandaged puzzle.

Kociemba's phase subgroup
`<U, D, R2, L2, F2, B2>` leaves all orientations zero and the four slice edges
within their slice. He evaluates alternative first-phase solutions because
a longer first phase can yield a much shorter total solution. These ideas
support larger invariant features and whole-continuation scoring; his
computer search and tables do not supply a small human repertoire.
[Two-phase coordinates](https://kociemba.org/math/twophase.htm),
[Two-phase details](https://kociemba.org/math/imptwophase.htm).
His coset and symmetry documentation also establishes why coordinate
quotients need a valid subgroup and why symmetry reuse must preserve that
subgroup. [Cosets](https://kociemba.org/math/cosets.htm),
[Coordinates and symmetry](https://kociemba.org/math/symcord.htm).

Composite features can have much larger observation orbits than the current
24-state single-block orbits. Global edge orientation on an ordinary cube
has 2,048 values. Use factored recognition rules or bounded searches on
smaller projections instead of requiring a learner to memorize one case
for each value. Offline pattern databases can guide computation without
becoming part of the taught repertoire.

## Slot patterns that solve several orientations together

A stage can observe the phases of arbitrary occupants of several slots,
ignoring their identities and all other attributes. This represents a
different subgoal from placing or fully solving an identified block. The
current block actions already contain the necessary information: reindex
the source block phase `phi(i)` into its destination slot `d(i)` with
`q[d(i)] = phi(i)`.

For a macro `a`, the resulting slot field obeys

```text
q'[d_a(j)] = q[j] + phi_a(j)  modulo the footprint class orientation order.
```

This is an affine action: the algorithm transports the incoming phases
and changes some of them. A recognition pattern therefore predicts its
orientation effect without identifying the occupying pieces. Kociemba's
destination-indexed orientation coordinates use this distinction, and
his move-table construction requires that states sharing a coordinate have
the same successor coordinate. [Coordinate level](https://kociemba.org/math/coordlevel.htm),
[Move tables](https://kociemba.org/math/movetables.htm).

### An automatically compiled last layer stage

The [slot orientation probe](slot-orientation-stage-probe.json) takes the
single body `A = F R U R' U' F'` and the three U turns. It extracts their
exact native effects, constructs an eight-observation graph, and uses a
weighted reverse search to generate a correction policy. Only the four
slot phases `(UR, UF, UL, UB)` are observed; top edge identities and all
top corner attributes are ignored. The first two layers are protected
at complete macro and correction boundaries.

The eight even-parity phase patterns group into four shapes under U turns:
cross, line, elbow and dot. Dispatch must retain the selected rotation or
setup frame; a shape name alone does not determine the effect of fixed `A`.

| Flipped slot mask in UR UF UL UB order | Generated recipe | HTM |
| --- | --- | ---: |
| 0000 | Skip | 0 |
| 0011 | A U A | 13 |
| 0101 | A | 6 |
| 0110 | U' A A | 13 |
| 1001 | U A A | 13 |
| 1010 | U A | 7 |
| 1100 | A A | 12 |
| 1111 | A A U A | 19 |

The stage averages 10.375 HTM over these eight equally likely observations,
with a worst of 19. It uses one long body and never its inverse. These are
shortest additive paths in the declared four-macro graph, not globally
shortest physical orientation corrections.

The probe physically verifies all **62,208 valid configurations with the
first two layers solved**, including every allowed top-edge permutation,
top-corner permutation and twist assignment. Every recipe orients the
remaining edges and preserves the first two layers. A separate 768
transition replay checks that hidden edge identities do not affect the
abstract dynamics. This proves coverage of this isolated stage; it does
not supply a complete cube method or production integration.

```sh
v2/.venv/bin/python v2/research/probe_slot_orientation_stage.py
```

If `H` fixes the first two layers and `K` additionally makes the top-edge
phase pattern zero, then `[H:K] = 8`. Thus simultaneous orientation fits
the stabilizer-chain framework as one stage. `K` need not be normal:
the observations form a coset space, rather than necessarily a quotient
group. It leaves placement free, so an algorithm can make several edges
correct in this attribute while moving their identities and changing
unfinished corners.

### Discovering useful pattern stages

Automated feature discovery can propose slot regions and attributes from
geometry and from the algorithms' existing decorated effects. For each
candidate current subgroup `H`, compute its compatible slot orbits and
consider phase patterns over invariant unions, including modular phase
projections. Algorithm supports identify promising sets whose orientation
changes are already coordinated by a short reusable word.

For each candidate, derive its observation transitions, search its reachable
pattern orbit, and score the entire continuation under the taught-body
budget. Cases can be compressed using setup symmetries, with explicit
frame dispatch. This searches for easy recognition with substantial
simultaneous progress, rather than requiring every stage to solve one
identity.

There are two separate validity conditions. A permitted macro must map
any two states with the same observation to the same next observation.
For a strict stabilizer-chain stage, the goal fiber must also be a subgroup
of the current `H`. An invariant slot set and its full phase field supply
these guarantees directly. Arbitrary slot subsets can fail: an incoming
piece from an unobserved slot may bring an unknown phase. Enlarge the
observed set, restrict the permitted macros, or use a more general
controller with universally checked corrections. Invariance under only
the selected macros is sufficient for a controller, but does not by itself
make its goal a subgroup of a larger current `H`.

This construction extends to compatible bandaged block footprints using
the existing cyclic phases of orders 2, 3 and 4; order-one phases add no
orientation information. Legal root loops, previous feature preservation
and exact reachable phase constraints remain necessary. Selecting the
best pattern stages and order is an optimization problem; expressing and
certifying the proposed concepts is already practical.

## Choosing stages from the available algorithms

The full geometric actions can inform both the attributes in a stage and
their order. Each algorithm has a **preservation profile** describing the
solved conditions it retains, and a **repair profile** describing observations
it sends to the goal. Combine these profiles across small algorithm palettes.
The useful planning question is: what can we finish now that our useful later
algorithms will preserve?

These profiles distinguish placement, phase and regions. A fully fixed piece
needs both fixed placement and zero phase increment. Preserving a zero-phase
condition permits permutations within an invariant slot region, provided its
phase increments are zero. Preserving a region's selected occupants only
requires setwise preservation. Raw moved-piece support misses these distinctions.

### A probe that derives the regions from actions

The [algorithm-informed target probe](algorithm-informed-targets-probe.json)
starts with the previous illustrative palette `A = F R U R' U' F'` and the
three U turns. It does not receive a top-slot region. From their permutation
actions it recovers one active four-slot orbit for edges and another for
corners. The common fully fixed slots are precisely the first two layers.
This suggests solving those layers before using this palette, and observing
top-edge or top-corner attributes separately during its use.

The probe proposes phase and placement observations on each active orbit,
then constructs their weighted correction graphs. It checks coverage against
every observation possible in the full first-two-layer stabilizer, rather
than only the observations this small palette happens to reach.

| Candidate attribute | Covered / possible observations | Isolated stage mean HTM |
| --- | ---: | ---: |
| Top-edge phases | 8 / 8 | 10.375 |
| Top-corner phases | 27 / 27 | 15.185 |
| Top-edge placement | 24 / 24 | 7.417 |
| Top-corner placement | 8 / 24 | Incomplete |

The phase and placement candidates permit changes to all ignored top-layer
attributes. Their costs are alternatives at the same starting subgroup,
not successive stage costs that can simply be added. In particular, the
palette's restricted corner-permutation action prevents a complete ending
for arbitrary last-layer states. Complete phase coverage does not imply a
complete cube method. All 332 proposed observation transitions and 67 covered
case recipes receive independent native witness replays; the earlier
edge-phase probe also retains its exhaustive 62,208 hidden-state validation.

```sh
v2/.venv/bin/python v2/research/probe_algorithm_informed_targets.py
```

The same record separately extracts exact profiles of the saved guide's seven
long bodies. `M18`, `M19`, `M20` and `M22` fix every corner fully; these are a
palette worth testing for an ending after corner completion. Only `M20`
preserves globally zero edge phases as an individual body. `M22` is a pure
two-edge flip with all placements fixed, whereas the six-turn `M16` couples
two flips with unfinished placement and corner changes. These facts propose
different orders and grouped targets; they do not establish which order is
best. Profiles of setup/body/undo variants can differ, and such variants must
also be assessed. The illustrative `A` palette is separate from the saved
seven-body vocabulary.

### Forward repair and backward preservation

A practical candidate search can proceed as follows:

1. Extract slot permutations, cyclic phase increments, physical costs and
   legal witnesses for the current bodies and reusable setup variants.
   Include short compositions that restore earlier goals at their boundaries.
2. Cluster palettes by shared fixed pieces, invariant regions and phase
   preservation. Their common invariants suggest earlier goals; their
   coordinated effects suggest attributes to correct together.
3. Compute observation transitions. Applying an algorithm's inverse action
   to the goal identifies the exact input observation the forward algorithm
   repairs. This uses inverse effects for analysis and does not require
   teaching or executing inverse bodies.
4. Search the full current-group observation orbit. Reject any candidate
   with missing cases. Measure weighted distances and compress recognition
   using valid setup symmetries, retaining the setup frame.
5. Check the entire remaining subgroup and score the continuation under
   the fixed long-body budget. More cases and longer recipes still carry
   recognition and execution costs.

An individual body that violates a finished goal need not be discarded:
compositions of existing bodies can restore that goal at recipe boundaries.
Their endpoint actions then belong to the required stabilizer without
introducing another learned body. Bounded recipe search supplies cheap
candidates; a separate subgroup certificate checks full residual coverage.

There is also a precise backward construction. For a promising late palette
`T`, let `K = <T>`. Find simple geometric attributes that remain solved under
every element of `K`, and let their goal stabilizer be `K_F` inside the current
group `H`. Then `K <= K_F <= H`. Those attributes propose an entry stage for
the late palette, but generally leave more freedom than it can solve.
Compare `K` and `K_F` explicitly. A nontrivial index identifies missing
residual components requiring more protected recipes or a stronger entry
goal. Even equality guarantees coverage, not short physical paths.

### Mining phase attributes algebraically

For a compatible class, write each slot-phase action as `q' = P_a q + b_a`.
An observation `z = L q` has an induced transition if the transported phase
information depends only on `z`. Over the edge and corner phase fields, a
convenient matrix test is

```text
L P_a = N_a L,
z' = N_a z + L b_a.
```

The algorithm preserves the goal `z = 0` when `L b_a = 0`. This can propose
invariant slot groups, selected orientation patterns and modular sums,
extending beyond individual slot fields. Discard properties already constant
on all of `H`, such as the ordinary cube's total edge-flip parity. For order-four
phases, use exact modular calculations on the attainable observation module,
rather than assuming vector-space arithmetic.

For a strict chain, certify the observation action under the whole current
`H`; certification under a selected palette alone supplies only that palette's
controller. The required deterministic-coordinate condition is precisely that
states sharing an observation have the same successor observation.
[Kociemba, Move tables](https://kociemba.org/math/movetables.htm).

Algorithm-informed base choice has a direct precedent. Egner and Püschel
first find short words with many fixed points, retain short conjugates grouped
by moved-point support, and then choose a base adapted to those supports.
Their Section 5.2 aims to distribute short words across stabilizer levels and
explicitly treats the choice as heuristic. Extending that idea to attribute
preservation, case coverage and a fixed taught-body budget is the proposed
direction here. [Solving Puzzles with Permutation Groups, author's paper page](https://people.inf.ethz.ch/markusp/examples/puzzles/puzzles.html).

## Transfer between bandage refinements

Let `P` be a coarser bandage and `Q` a refinement obtained by splitting its
blocks. From matching colored configurations, every move word legal for `P`
is legal for `Q`: removing bonds cannot introduce a new layer obstruction.
Thus coarse trajectories and their raw word witnesses transfer to the
refinement. The endpoint must still be checked against the finer shape.

Root isotropy groups do **not** always nest. Take `P` with fused pairs
`(UFR, UR)` and `(UBL, UL)`, and let `Q` split the second pair. `U2` is legal
for both and exchanges the two coarse pairs. It returns `P` to its root
shape, but moves `Q`'s sole fused pair to the other slot. Therefore `U2` is
a loop in `H_P` and an open arrow for `Q`, rather than an element of `H_Q`.
Even a one-bond refinement can have this behavior because shape blocks are
canonicalized without persistent block names.

The precise relation retains the refinement alongside the coarse shape.
Transport the fine pattern along coarse arrows and form the groupoid of
synchronized pairs. Over a coarse root, `H_P` acts on the transported fine
patterns. The stabilizer of the selected pattern is the common loop group

```text
K = { h in H_P : Q acted on by h equals Q } = H_P intersect H_Q.
```

The orbit size is `[H_P : K]`. This is a derivation for the repository's
faithful permutation groupoids. It counts transported fine patterns, not
extra algorithms or physical moves. `K` need not be normal, and this orbit
does not describe all additional states reachable only after refinement.
If every coarse loop preserves that fine pattern, then
`H_P` is contained in `H_Q`; full unbandaging is an important such case.
Forgetting the coarse parent grouping loses the information required for
a general shape-to-shape map. The construction is an action groupoid
whose projection to the coarse groupoid is a covering with unique lifts.
[Brown, groupoid actions
and coverings, section 3](https://groupoids.org.uk/pdffiles/relHurdim1xxx.pdf).

Coarse loops can be reused as open fine templates while tracking the coarse
parent grouping. For a fine colored state that is also coarse-reachable,
a complete coarse solution still solves all colors and restores the fine
shape at the end. It need not restore that fine shape after each coarse
loop. Solving the entire refined puzzle additionally requires coverage of
states that the coarse puzzle could not reach.

The [refinement probe](bandage-refinement-transfer.json) independently
checks the one-bond example with native shape replay, faithful colored replay
and compiled obstruction certificates. Reproduce it with
`v2/.venv/bin/python v2/research/probe_bandage_refinement.py`.

Several transfer mechanisms follow:

| Transfer | What can be reused | What must be established |
| --- | --- | --- |
| Same shape component, different root | Conjugated group, feature action and templates | Legal transport and its physical cost |
| Spatially equivalent bandages | Face-renamed witnesses and rotated features | Matching specification and allowed feature symmetry |
| Coarse bandage to a refinement | Every coarse legal raw word | Fine endpoint closure or extra pattern restoration |
| Refinement to a coarser bandage | Proposed effects and words | Full coarser legality; some words become blocked |
| Ordinary cube to a bandage | Algebraic subgroup features, lower bounds, candidate templates | Legal witnesses and complete reachable subgroup coverage |

The implementation already has a particularly useful transfer primitive:
[compiled word obstructions](../python/python/bce_v2/familiar_algorithm_catalog.py).
For a fixed raw word `w`, a 54-bit forbidden-bond mask `F_w` checks legality
against a saturated full-grid bond mask `B` with `B & F_w == 0`. Its allowed
bond destination map also checks the final shape. The
[independent probe](../research/probe_algorithm_obstructions.py) validates
this representation, including invisible core bonds. Cache those word
certificates across the atlas; recompute closure and stabilizer membership
for each new root. Words with identical ordinary-cube effects can have
different obstruction masks, so effect equality alone is an insufficient
transfer key.

Removing bond restrictions also gives admissible distance lower bounds in
the larger legal graph, with the goal projected consistently. This supports
pattern databases or quotient heuristics shared across refinements. Adding
bonds can disconnect the reachable component, so small geometric changes
do not guarantee similar group orders, a small refinement orbit or a
reusable complete solving method.

## Production implementation

The [first implemented increment](algorithm-informed-stage-implementation.md)
adds exact grouped orientation goals, algorithm-informed discovery and bounded
whole-chain selection in both backends, with portable execution and recognition
diagrams. It records exhaustive Alcatraz comparison and the ordinary-cube
control measurement. The priorities below remain the broader optimization
programme.

## Implementation priorities and evaluation

1. **Measure chain freedom and the expensive tail.** Publish per-stage
   physical costs, legal free faces, surviving short-word coverage, macro
   applications and the precise learned-body count. Allocate discovery work
   toward measured bottlenecks such as the late DBL stage.
2. **Add compact candidate chains and real chain search.** Use face/block
   incidence and buffer rules to propose candidates; evaluate completed
   continuations with swaps, insertions and bounded beams. Compare on one
   shared physical dictionary before allowing dictionary adaptation.
3. **Couple vocabulary and physical policy.** Search corrections in the
   actually taught grammar, enforce at most seven long masters, and retain
   recognition/recipe limits. Simplify and replay Schreier proposals before
   their physical lengths influence ranking. Use protected-observation
   collisions to replenish useful late-stage words. Evaluate short prefix
   trials as a source of explainable state-dependent choice rules.
4. **Add relative and invariant features.** Start with corner-edge pairs,
   compact regions and class orientation. Preserve exact action, stabilizer,
   orbit, parity and final-identity certificates.
5. **Reuse witnessed words and workspace paths across bandages.** Use
   compiled obstructions, conjugation within components, and synchronized
   coarse/fine patterns. Recompute physical availability and subgroup
   coverage whenever the bandage changes.

Evaluate successive changes on the ordinary cube, the singleton-rich
edge/corner bandage, and small reference groups where complete replay is
practical. Include puzzles with few immediately free faces and asymmetric
blocks. Hold the taught-long-body budget and search budgets fixed; report
the Pareto frontier of mean moves, worst moves and recognition complexity.
For uniform additive comparisons use exact stage costs. For cancellation
and adaptive cases use the same history-free imported states, with the
sampling distribution and seed recorded.

The first useful target is a demonstrated improvement over 216.92 HTM at
the current seven-long-body budget across several bandages. A 60-move
ordinary-cube goal is motivated by existing methods, but achieving it here
also requires suitable subgoals and correction recipes; preserving free
faces alone does not establish that result.
