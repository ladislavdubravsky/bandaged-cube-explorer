# Discovering human cube methods: a fresh architecture review

The implementation now provides witnessed pre-selection
palettes, fixed collection/membership goals, independent recognition contracts,
alignment-aware endpoints, palette preservation profiles and bounded multi-stage
search carrying a global taught-definition budget. The
[API and scope](../../docs/human-methods.md#supplied-palettes-and-a-strict-coarse-stage-compiler)
and [production acceptance probe](../research/probe_compiled_last_layer.py)
describe the compiler foundations. The
[discovery API](../../docs/human-methods.md#palette-led-workspace-and-method-discovery)
infers protected starting regions and complete suffix ladders without seeded
goals. Its [retained acceptance](discovered-last-layer.json) solves all 62,208
states in the independently inferred F2L domain with four taught bodies and
case counts `8, 6, 27, 4, 4, 3`. Generic constructive entry now derives a
workspace anchor from geometry, recognizes relative assemblies away from home
slots, and chooses subsequent collections by the current scramble. Its
[retained native sample](workspace-entry.json) solves eight 20-turn scrambles
with a mean 29 HTM entry and 75.75 HTM complete execution, retaining four taught
bodies. Entry is bounded, and successful observed-fiber corrections do not
certify complete human entry rules. Joint entry/continuation selection and
guarded choices of relative block frames remain work. The discussion below
records the motivating architecture before these increments.

The main obstacle is the planner's representation and search space. Fixed-frame
CFOP and Petrus stage boundaries can largely be expressed as stabilizer chains.
Our ordinary-cube planner does not currently propose their assembled blocks,
paired goals, or successive grouped last-layer coordinates. Having the physical
algorithms available does not fill those gaps automatically.

The previous orientation-stage increment supplied useful mathematical and
execution machinery. Its symbolic automatic search inserts one grouped phase
goal into an existing chain and finishes with individual physical-block goals.
That is insufficient to discover an entire human method. The recommendations
below replace that narrow search with goal and policy synthesis, while retaining
exact subgroup certification and legal physical witnesses.

The saved ordinary-cube guide gives a concrete warning about local scoring:
it solves opposite corners UBR and DFL first. After only the second stage,
every face touches a protected piece. The two stages themselves average about
three moves together, but remove all individually usable face turns from the
endpoint stabilizer. Later recipes must restore those corners through longer
combinations. Temporary displacement remains allowed; inexpensive endpoint
actions have become scarcer. The previous same-dictionary compact-block probes
lowered mean length but increased the taught repertoire, so geometry alone
did not meet the seven-body objective.
[Saved-guide audit](unbandaged3x3-current-guide-audit.json),
[geometric comparisons](stabilizer-chain-optimization.md).

## What standard methods actually require

| Method | Main committed goals | What the solver recognizes or chooses |
| --- | --- | --- |
| Beginner layer by layer | Cross, first-layer corners, middle edges, then grouped last-layer orientation and permutation | Several slots at once; often repeat a body with U adjustments; distinguish orientation from identity |
| CFOP / Fridrich | Cross; four corner-and-edge pairs; orientation of all last-layer pieces; their permutation | A corner and its matching edge together, including their relative arrangement; setup-normalized last-layer patterns |
| CFOP with a four-look last layer | Cross and pairs; edge orientation; corner orientation; corner permutation; edge permutation, with alignment adjustments | Each attribute is finished collectively; several cases share one body |
| Petrus | A 2×2×2 block; expand to 2×2×3; orient remaining edges; finish two layers; last-layer placement/orientation goals | Choose a convenient block and expansion; recognize relative assemblies; define edge orientation with respect to the two remaining free faces |
| Roux | Two opposite 1×2×3 blocks; remaining corners; last six edges | Ignore slice edges during corner solving; retain corner arrangement up to U alignment; jointly orient or place several edges |
| ZZ | Orient all edges and place a two-edge line; build two blocks; solve the last layer with EO already finished | Choose an early attribute reduction because it enables a cheap L/R/U continuation |

Fridrich explicitly describes solving a corner and middle-layer edge
simultaneously, followed by collective last-layer orientation and permutation.
Her description also emphasizes using the particular scramble and available
workspace when building the early structure.
[Fridrich's original method](https://ws.binghamton.edu/fridrich/system.html).

Petrus first joins pieces into a temporary block, chooses an easy expansion,
then classifies the seven remaining edges by whether the two free faces can
place them correctly. This is a continuation-dependent definition of
orientation. His advanced block expansion permits temporarily breaking and
restoring the built block.
[2×2×2 construction](https://lar5.com/cube/fas1.html),
[2×2×3 expansion](https://lar5.com/cube/fas2.html),
[edge orientation](https://lar5.com/cube/fas3.html).

Four-look last-layer teaching commonly uses three edge-orientation bodies,
seven corner-orientation bodies, two corner-permutation bodies and four
edge-permutation bodies. These are taught algorithm counts, not raw coordinate
domain sizes. Repeating fewer bodies is possible, with a cost in moves and
recognition procedures.
[J Perm's last-layer overview](https://www.jperm.net/3x3/cfop/ll),
[CubeSkills four-look sheet](https://www.cubeskills.com/uploads/pdf/tutorials/4-look-last-layer.pdf).
We should not promise ordinary CFOP efficiency with our existing seven-body
budget merely because these methods have a similar number of stages.

Roux additionally shows why “solved” may mean relative arrangement rather
than absolute slots: its last-six-edge stage permits U alignment while keeping
the top corners correct relative to each other. It later solves UL/UR together,
and advanced variants combine their placement with six-edge orientation.
[Scheopner's Roux outline](https://www.scheopner.com/cube/),
[his last-six-edge analysis](https://www.scheopner.com/cube/lse.php).
Our move parser currently excludes slice, wide and rotation tokens. A Roux
benchmark therefore needs witnessed face-turn translation and a working frame,
or new move support; slice-turn counts cannot be compared directly with HTM.

ZZ orients all edges and fixes DF/DB, enabling F2L construction with L/R/U.
This chooses an attribute because of the continuation it makes cheap.
[Rider's ZZ tutorial](https://rider.biz/cube/zz.php).
Our raw-domain calculation gives 2,048 global EO patterns and 270,336 combined
EO+Line observations. Unlike a split last-layer OLL, this early reduction
exceeds today's phase bound and needs constructive or compressed recognition.

Kociemba provides a useful computational comparison: phase one jointly fixes
edge orientation, corner orientation and slice-edge membership, reaching
`<U,D,R2,L2,F2,B2>`. Its search can try several entries into that subgroup to
improve total solution cost. Joint attributes and useful continuation groups
are already workable computational concepts; translating them into a small
human repertoire adds a separate objective.
[Kociemba's two-phase method](https://kociemba.org/math/twophase.htm).

## What the current code can and cannot express

### Supplied templates do not drive symbolic planning

`symbolic_template_human_repertoire` selects the method in `_prepare` before
using supplied `templates`. Its policy scope explicitly retains the selected
physical case words. Consequently, this argument provides definitions for
compressing an already chosen policy, rather than algorithms that may change
its chain or physical recipes.
[Selection](../python/python/bce_v2/symbolic_template_repertoire.py#L298),
[template processing](../python/python/bce_v2/symbolic_template_repertoire.py#L363).

There are existing routes into planning: a prepared `dictionary=` supplies
witnessed algorithms before selection, and familiar-algorithm mining also runs
while constructing dictionaries. The defect is specifically that the template
API does not mean what an algorithm-supplied method search would require. Add a
clear, pre-selection palette input; distinguish algorithms available for search
from bodies ultimately taught to the human.

### A physical bandage block is not an assembled human block

`place_block` and `solve_block` name exactly one component in the reference
inventory. Solving a fused bandage already solves its constituent cubies
together. But a Fridrich corner-and-edge pair consists of two independent
components, and a Petrus block consists of several components assembled during
the solution. Neither is one inventory block.
[Feature resolution](../python/python/bce_v2/human_chains.py#L94).

We need goals for jointly solving arbitrary collections, grouping placement
attributes, constraining membership of a region, and matching an assembly up
to a permitted frame or alignment. An anchored complete region is simply an
intersection of existing full-pose stabilizers; no new group theory is needed.
Its efficient observation and policy compiler are new work.

Relative assembly anywhere is a further capability. A pair may already be
joined but located outside its final slot. Such an intermediate condition is
usually a set of states or several framed branches, rather than one chosen
root subgroup. It can initially live inside a controller whose endpoint is an
ordinary anchored subgroup goal.

### The symbolic automatic search cannot select a last-layer ladder

The adaptive symbolic selector normally considers placement or full solution
of one physical block, with bounded one-step lookahead. Its attribute pass
examines prefixes of existing chains, inserts one proposed orientation goal,
and calls the same individual-block continuation.
[Ordinary proposals](../python/python/bce_v2/symbolic_chain_search.py#L148),
[orientation insertion](../python/python/bce_v2/symbolic_chain_search.py#L673).

It does not recursively propose EO → CO → grouped corner permutation → grouped
edge permutation, or build an earlier coherent two-layer workspace to make
that suffix available. Increasing its beam width or prefix budget cannot
introduce absent goal types.

This limitation is specific to automatic symbolic search. Manual feature
chains can already contain multiple orientation goals. The explicit backend
can propose orientation goals at successive subgroups, but also lacks the
assembled-collection and grouped-permutation goal language.

### Recognition is tied to the committed goal

Runtime observation is derived from `stage.feature`. A corner-only goal cannot
inspect its matching edge and choose an insertion that solves both efficiently.
[Runtime recognition](../python/python/bce_v2/human_methods.py#L280).

We need a separate recognition specification: observe a pair, relative
geometry, a region pattern, or an alignment, while committing only the desired
endpoint attributes. The committed coordinate should be recoverable from this
richer observation. A recipe must work for every reachable hidden state in the
observation fiber and preserve previous goals at its endpoint.
For future controllers that reinspect between instructions, the observer need
only identify rule applicability and goal termination, with certified fiber
transitions and progress; recovering the entire committed coordinate is a
sufficient initial contract for fixed-word case tables.

Existing repertoire code already has multi-instruction progress rules,
repeated bodies, and whole-fiber validation. The missing feature is independent
recognition and its certified relationship to the endpoint goal, rather than
multi-instruction execution itself.

### The learned-body constraint is applied too late

Chain selection scores physical moves and raw observation counts. Shared-body
compression follows afterward. There is no hard limit of seven long bodies
in the chain search. A method can therefore have attractive local corrections
whose union is a poor repertoire, or reject a larger recognition coordinate
that admits very cheap repeated use of already learned bodies.

The search state must retain the union of taught bodies used by its policies.
Canonical case patterns, legal setups, repetitions and recognition rules
should have separate costs. Raw orbit size, number of human case families and
number of taught algorithms are three different quantities.

## An executable check: the complete last layer is already tractable

The new [research oracle](../research/probe_standard_last_layer.py) starts with
the first two layers solved and seeds four exact goals: EO, CO, absolute corner
placement and absolute edge placement. It supplies four long bodies from the
CubeSkills sheet—edge orientation, Sune, T-perm and Ua—plus U, U2 and U′.
No inverse-body variants are used. It builds setup/body/undo variants, computes
weighted correction policies, and replays all valid native last-layer states.

| Seeded stage | Raw observations | Mean additive HTM |
| --- | ---: | ---: |
| Edge orientation | 8 | 10.3750 |
| Corner orientation | 27 | 17.0370 |
| Absolute corner placement | 24 | 15.4167 |
| Absolute edge placement | 12 | 18.5000 |

All **62,208** states solve, and every stage preserves all earlier goals at its
endpoint. Total last-layer mean is **61.3287 HTM**, worst **99**, counting setup
turns and excluding boundary cancellation. The recorded exhaustive run took
about 4.77 seconds. Policies may repeat a supplied body. This is an existence
and correctness check, not an efficient complete scramble method, a claim of
one algorithm per look, or automatic goal discovery.
[Full record](standard-last-layer-oracle.json).

The strict fixed-slot subgroup ladder has orders

`62,208 → 7,776 → 288 → 12 → 1`,

with successive indices `8, 27, 24, 12`. Combined OLL has 216 raw observations;
splitting it into EO and CO gives domains already below the phase discovery
default of 128. Thus that bound cannot explain an inability to represent a
two-step OLL suffix.

Human corner permutation is often solved up to a final U adjustment. An
alignment-aware ladder can instead have indices `8, 27, 6, 12, 4`; this is a
different intermediate goal, followed by final alignment. The 24 in the oracle
is an exact absolute-placement coordinate, not 24 human corner-PLL algorithms
or recognized case families. Generic matching up to a permitted frame should
support this distinction. Such matching requires an explicit allowed alignment
group and a certified subgroup/action construction. An arbitrary union of
framed predicates need not be a subgroup; keep separate guarded branches when
that certification fails.

There is also an important recipe-ordering detail. Once corner placement is
fixed, U alone is disallowed at the next endpoint. Nevertheless,
`U^k Ua U^-k` preserves it and is useful. Generate complete setup/body/undo
recipes before testing endpoint preservation. Filtering the component moves
first loses those recipes. Existing stabilizer semantics already permit
temporary disruption inside a physical word.

Reproduce from the repository root:

```sh
PYTHONPATH=v2/python/python python3 v2/research/probe_standard_last_layer.py
```

## How algorithms should suggest the method itself

Current phase discovery mostly asks which available algorithms repair a
proposed observation at an existing prefix. We also need the backward question:
**which useful conditions must we finish so that a family of short algorithms
becomes available afterward?**

Compute geometric preservation profiles for each witnessed algorithm:

- fully fixed poses and collectively fixed constellations;
- invariant slot regions and phase fields it preserves;
- relative arrangements and membership predicates it preserves;
- permitted frame/alignment actions;
- legality and shape endpoints for its complete physical recipe.

Cluster bodies and recipes by common preservation. A family of last-layer
algorithms has a common fixed two-layer region, suggesting that region as an
earlier goal. Within that family, nested EO-, CO- and permutation-preserving
subfamilies suggest the last-layer ladder. This can reveal a useful suffix
before a forward singleton chain happens to reach it.

If `K` is generated by a palette cluster, it is evidence for a candidate
continuation, not proof that the cluster covers the full physical state domain.
Derive a readable geometric goal `F`, compute its full stabilizer `K_F` inside
the current subgroup `H`, and certify both preservation and complete entry
coverage under `H`. Keep the entry policy, using recipes in `H`, separate from
the protected continuation palette in `K_F`: preservers alone cannot move a
state outside `K_F` into it. Even `K = K_F` would prove reachability within the
continuation domain, not cheap entry, short word distance or easy recognition.

Combine these backward continuation contracts with forward geometric
proposals: connected compact regions, adjacent compatible components, and
collections whose completion leaves several cheap legal actions available.
Physical footprint adjacency proposes candidates; measured policy and suffix
costs decide whether they are useful. Corner orientation order three versus
edge order two is not a sufficient ordering rule: connectivity, current
locations, palette coverage and continuation costs matter together.

## Geometry, orientation and generality

The ordinary-cube phase conventions are already aligned with native cubie
twists and flips: singleton frames explicitly use the ordered reference faces.
There is no ordinary OLL phase-convention bug to fix.
[Frame construction](../python/python/bce_v2/block_actions.py#L243).

Petrus-style orientation depends on the intended cheap continuation moves.
For other frames or bandage footprints, candidate phase conventions can be
derived from those moves. With source-to-destination action `a` and frame
offsets `s_i`, the phase increment changes as

`phi'_a(i) = phi_a(i) + s_{a(i)} - s_i (mod m)`.

Solve these modular constraints to seek a convention preserved by a proposed
cheap continuation palette. Inconsistent cycle constraints certify that the
requested convention is impossible. Frame changes must be applied coherently
to both source and destination descriptions, not just to displayed slot values.

The current full-subgroup invariance requirement for anonymous phase regions
is mathematically sound. If an unobserved piece can enter the region, its phase
cannot generally be predicted from the local field alone. Relaxing that check
does not provide a valid general observer. The last layer after F2L, and the
remaining edges after an anchored Petrus block, do form invariant regions.
More general conditional observers need richer observations or explicit
guards and domains.

For bandaged cubes, propose regions from whole fused inventory components and
their observable constituent attributes; build adjacency from actual
footprints; use their actual orientation orders and legal witnessed recipes.
A corner/edge pair or U-face cross is then an instance of a geometric goal,
not a special production rule. Only symmetries valid for the puzzle and its
goals may identify cases or transport algorithms.

Transfer across bandage refinements should reuse goal descriptions, geometric
profiles and candidate recipes, then recertify legality, observations and
coverage. A word legal on a coarser bandage is also legal on its refinement
along the corresponding path, but returning the coarse shape does not imply
returning the refined shape. Hence isotropy-group inclusion does not follow
from path legality alone. Conditional shape paths and guarded conjugation are
a later extension, building on the existing
[transfer investigation](stabilizer-chain-optimization.md).

## Avoid replacing singleton tables with enormous joint tables

These are our exact fixed-frame combinatorial calculations, rather than human
recognition counts. An ordinary solved cross has index 190,080. After it, the
successive fully solved corner-and-edge pairs have indices
384, 294, 216 and 150. Their product leaves the 62,208-element F2L stabilizer.
A specified Petrus first block has index 253,440; its specified expansion has
index 6,048. After expansion, orientation of the seven remaining edges has
only 64 patterns.

A compiler that enumerates every observation as a flat teaching case would
misrepresent early human stages and can be expensive. Reusing the 128 phase
bound as a universal bound on future composite goals would reject even the
first F2L pair. Current production does not yet apply that bound to F2L pairs;
those goals are absent. Use lazy orbit traversal, factored observations,
canonical setup classes, and short local controllers, while keeping exact
coverage certification separate from presentation.

Fixed-chain uniform-subgroup additive costs remain useful controls. Once the
method chooses a block or pair from the current scramble, or uses overlapping
observations for opportunistic progress, propagate the resulting state
distribution or evaluate the complete policy on exhaustive/sampled native
states. Do not silently reuse the old sum of uniform-stage means.

## Recommended implementation order and acceptance criteria

1. **Admit a witnessed palette before selection.** Give each body a stable
   identity and explicit setup/rotation/inverse teaching rules. Preserve the
   existing dictionary route; make the template route's scope clear. Search
   should know both its available recipes and its allowed taught vocabulary.

2. **Generalize goals and separate recognition.** Add grouped pose completion,
   grouped placement, region membership, and pattern matching up to an allowed
   frame. Start with fixed subgroup endpoints. Observation transitions and
   recipes must be certified over complete reachable fibers, with portable
   serialization and native replay.

3. **Compile several grouped stages in succession.** Bring the seeded
   last-layer oracle into the generic production compiler, including
   alignment-aware variants. Supply the region and palette but no special
   3×3 policy logic. Require all 62,208 last-layer states to solve through
   independently loaded methods and repertoires. This tests the machinery
   before testing discovery.

4. **Discover the suffix and its required workspace from palette profiles.**
   Remove the seeded LL goals: common preservation should propose them and
   their order. Add connected-region and adjacent-pair completion proposals;
   solve useful joint goals with the same body vocabulary. Keep a budgeted
   method frontier carrying subgroup, goal/observer contracts, suffix coverage,
   taught-body union, recognized rule families and total execution estimates.
   A true method beam must extend multiple coarse goals, not splice one phase
   feature into a fixed individual-block continuation.

5. **Add relative assembly and state-dependent choices.** Let controllers
   recognize a prebuilt pair, choose an easy initial block or next expansion,
   and opportunistically complete more than the committed goal. Add inferred
   phase frames and guarded shape transport where useful. These capabilities
   explain much of early Petrus/F2L efficiency, but should follow a correct
   fixed-goal implementation.

Track complete-scramble physical HTM, taught long-body union, normalized case
families, worst recognition burden, legality/coverage, and separate preparation,
planning and application times. Compare both a fixed seven-body budget and
larger supplied palettes. Keep ordinary 3×3 as a structural regression oracle;
repeat the same generic search on Alcatraz, Pocket, Bicube, Shark, FourPair,
BeltRoad and a large singleton-rich bandage. Budgets and certified fallbacks
must keep new analyses from making every example expensive.

The next production increment should therefore center on composite goal and
recognition contracts, pre-selection palettes, and successive coarse-stage
search. More dictionary mining or singleton-chain ordering can improve current
controls, but cannot substitute for those capabilities.
