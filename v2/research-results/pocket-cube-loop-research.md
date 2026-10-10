# Pocket cube human solution comparison and loop research

The 2015 solution points toward a better human-method objective: find a shared
language of shape paths, local loops and regrips, then build stage instructions
from that language. Counting complete generators misses this structure.
Experiments on the current notebook puzzle also expose an immediate execution
problem: its selected corrections are discarded when the guide is rebuilt
using the reduced generator basis.

These results concern the fully colored bandaged Pocket Cube, with 580 reachable
shapes and 432 colored states in the reference shape. They exclude shape
restoration. The initial research left the production solver unchanged. The
implemented follow-up and updated notebook are described at the end of this report.

## Measured comparison

Every mean below weights all 432 reference states equally, including solved.
HTM counts a half turn as one face move. Whole-cube regrips have zero face-turn
cost; the complete fixed-frame move word is simplified across algorithm and
stage boundaries. Recognition, ergonomics and memory are separate criteria.

| Policy | Taught vocabulary | Mean HTM | Worst HTM |
| --- | --- | ---: | ---: |
| Current notebook guide | 3 current generators | 126.94 | 247 |
| Current selected policy before basis rebuild | Corrections using 11 original loops | 70.52 | 118 |
| Cheapest complete historical fixed-frame triple, same chain and BFS compiler | 3 algorithms, 41 HTM of definitions | 123.15 | 238 |
| Historical templates with threefold regrips, same chain and BFS compiler | 3 templates and their rotated forms | 91.10 | 173 |
| Policy synthesized from the historical stage recipes | 3 templates, regrips, squares and triple combinations | 89.46 | 146 |
| Current basis, bounded correction search | Same 3 generators | 119.20 | 219 |
| Current basis with symmetry, bounded correction search | 2 templates and their rotated forms | 99.24 | 182 |

The historical stage policy uses the algorithms and stage macros from the
[2015 article](https://ladislavdubravsky.wordpress.com/2015/03/21/justin-pocket-cube-colored/).
Its complete case choices are synthesized, because the article does not specify
a unique exhaustive policy. The 89.46/146 result therefore measures a concrete
method built from those rules, rather than the author's actual choice on every
scramble. The two bounded current-basis experiments enumerate words through six
master applications, choose corrections for entire case fibers, and measure
the resulting whole solves; they do not establish shortest physical solutions.

Replacing the current fixed-frame triple with a cheaper historical triple buys
only a modest improvement. Using symmetry and better case policies supplies much
larger gains. A separate unrestricted additive-macro search gives 70.00/119 for
the current fixed-frame basis and 44.01/74 for the historical templates with
regrips. Those are machine factorization controls, not staged human methods or
shortest face-word results.

## What is already shared with the historical method

All three historical algorithms replay legally and restore the reference shape.
After compiling their internal rotations, their lengths are 13, 23 and 15 HTM
(16, 25 and 15 QTM). Two are literally existing current masters in a different
grip: historical algorithm 1 equals a regripped M3, and algorithm 3 equals a
regripped M2, with regrip `x' z'` in the notebook convention.

Three remembered templates and three fixed-frame group generators are different
vocabularies. The historical three literal words in one grip generate 144
states; their threefold regripped variants generate all 432. The current three
fixed-frame generators already generate 432 without that extra alphabet.
Allowing actual reference-shape symmetries, either current pair M1/M3 or M2/M3
also generates all 432. Two templates require 28 HTM of expanded definitions,
versus 43 for the current three. This proves coverage, not that two templates
give the easiest instructions to remember.

The coarse stage structure is already the same:

    432 → 18 → 3 → 1
    small edges → big edges → corners

The current notebook splits the first two families into individual block
features, producing indices 6, 4, 3, 2, 3. Its five stages do not represent five
different high-level ideas. Grouping the instructions around those three
families could improve recognition without changing the underlying chain.

One small historical action correction: algorithm 2 twists the two free corners
in place in the engine; it does not exchange them. Its square still gives the
claimed pure corner twist. The square of algorithm 3 gives a pure big-edge
three-cycle, and the three regripped algorithm-2 combination gives a pure
big-edge transposition. Their simplified costs are 46, 30 and 51 HTM.

## The current generators have a reusable grammar

Define three open five-turn paths in the notebook frame:

    K = F' U L F U'
    P = U F' L' F U'
    J = R' F D' F' R
    rho = x y

The current master definitions are exactly:

    M1 = K rotate(rho, K) J
    M2 = P K rotate(rho, K)
    M3 = (P U' R) B2 (P U' R)^-1

Here `rotate(rho, K)` means the frame-neutral presentation
`rho K rho^-1`. Expanding these formulas and simplifying adjacent turns
reproduces the existing physical words exactly. P belongs to the same rotation
family as the historical `R F' U' F R'` chunk. All three masters therefore
share small pieces already; the current expression model does not expose them
as a common learned vocabulary.

The existing move formatter recognizes literal conjugations and repetitions
within one algorithm. The repertoire optimizer also supports proper rotations
of whole reference loops. The missing capability is a dictionary of open
paths shared across algorithms, with rotations inside those paths.

## Local loops and transports

For a path P from reference S to another shape q, and a loop C at q, the legal
reference loop is:

    P C P^-1

The loop supplies the nontrivial action, while the transport determines which
reference pieces that action affects. In particular, M3 already has a one-HTM
local body B2, reached by the six-HTM setup `U F' L' F U2 R`. Its long root word
comes from the access path, not a complicated local mechanism.

The current fundamental-loop extraction already spans every legal reference
action. It uses one BFS tree and words `T_u a T_v^-1`, then retains short
representatives by sticker action modulo inversion. Mining elsewhere improves
candidate geometry and descriptions; it does not repair incomplete coverage.

Rerooting extraction at all 580 shapes found 12,489 local witnesses. Lifting
them back using the original reference transports produced 199 distinct
nonidentity action classes modulo inverse, compared with the current 14 native
classes. All 199 retained words replay legally. None shortened the 14 existing
native actions in this experiment. Twelve remote one-HTM half-turn loops lift
to just three 13-HTM root actions, already present in the native library.

Thus, short remote loops are useful discovery primitives, but root-word
shortening is not automatic. Their most immediate benefit here is exposing
structure and retaining useful alternatives.

## Changes to prioritize

1. **Choose policies in the vocabulary actually taught.** The notebook calls
   `select_human_chain` using a larger witnessed word pool, then calls
   `generator_human_repertoire(selection.method)`, which retains the features
   and rebuilds the corrections using generator-count BFS. The resulting mean
   grows from 70.52 to 126.94 HTM. Chain search should use the chosen template
   dictionary, including its valid rotated variants, or report the rebuilt
   policy's actual score when making its choice. Correct a case into its next
   stabilizer, with later pieces free, rather than requiring one fixed full
   permutation as its correction target.

2. **Represent shape paths separately from reference loops.** Add a typed
   expression carrying source shape, target shape, frame, physical moves and
   faithful sticker action. Composition must check endpoints. Inverse reverses
   the endpoints; rotation transforms both endpoints and the frame. A transport
   and a local loop can form a checked reference loop. Keep the existing
   original-loop certificate as proof provenance while retaining the path
   expression for teaching and scoring. The existing
   `LoopExpression.turns(word, witness)` can validate a compiled closed word;
   an open chunk must not become a reference-loop leaf.

3. **Mine short loops and short paths at multiple shapes.** Start with one-turn
   HTM loops, short cycle searches and shape collisions along legal walks.
   Retain multiple witnesses for an effect when their shared-chunk descriptions
   differ. Canonicalize geometric cycles under inverse, cyclic phase and proper
   rotations, keeping the transformations needed to recover each occurrence.
   Preserve move labels, parallel arcs and frame data.

4. **Optimize a shared dictionary and stage instructions together.** Score
   definition symbols across the whole dictionary, recipe complexity, rotation
   cues, observation families and complete solve costs. Inverses and rotated
   references can reuse a definition. Compare several Pareto choices; these
   costs remain proxies pending human feedback. A small irredundant generating
   set is useful for coverage but can have long or awkward correction recipes.
   SEQUITUR supplies a useful model for extracting repeated phrases into a
   hierarchical grammar; adapting it to typed paths and rotation-equivalent
   phrases is a proposed extension, not a result of that paper.
   [Nevill-Manning and Witten, 1997](https://arxiv.org/abs/cs/9709102).

5. **Teach families of effects.** Preserve the small-edge, big-edge and corner
   landmarks. Compress concrete cases into verified rules about a swapped pair,
   flipped pair, three-cycle or twist direction, with explicit grip cues and
   termination checks. Compare historical templates as pinned choices before
   asking a discovery search to replace them. Algorithm-informed word chains
   have precedent in
   [Egner and Püschel's puzzle work](https://people.inf.ethz.ch/markusp/examples/puzzles/puzzles.html);
   their published erratum matters if using the original word-chain lemma.
   For harder stage searches, pattern databases can guide macro discovery,
   as demonstrated by
   [Hernádvölgyi, 2000](https://cdn.aaai.org/AAAI/2000/AAAI00-158.pdf).

## Correctness details for the path search

Changing the start of a cycle changes its ordered nonabelian action by
conjugation. If `C = Q C_shift Q^-1`, its transport must change from T to TQ
to preserve the same reference algorithm. Likewise, replacing a transport with
another path to the same shape can change the colored effect. Preserve the
discovery transport as an alternative and recompute the action for every new
one.

Shared access paths can cancel across consecutive algorithms:

    (P C1 P^-1)(P C2 P^-1) = P C1 C2 P^-1

Score the expanded complete recipe after simplification. Additive macro
Dijkstra is a useful search heuristic but can miss these savings.

The full 24 cube rotations should not be treated as free identifications inside
this fixed-frame component. Its reachable shapes intersect 194 global rotation
classes: 193 intersections of size three and the reference singleton. A
rotation quotient needs frame transports and stabilizers; simply collapsing
vertices and finding cycles would lose the necessary lifting information.

## Reproduction and validation

From the repository root, using the installed v2 environment and GAP:

    v2/.venv/bin/python v2/research/compare_pocket_human_solution.py --output /tmp/pocket-human-comparison.json
    v2/.venv/bin/python v2/research/compare_pocket_generator_policies.py --output /tmp/pocket-generator-policies.json
    v2/.venv/bin/python v2/research/probe_pocket_local_cycles.py --output /tmp/pocket-local-cycles.json

Retained records:

- [Historical comparison](pocket-human-comparison.json): compiled algorithms,
  action checks, fixed-frame basis comparisons, historical stage policies and
  unrestricted macro controls.
- [Current vocabulary comparison](pocket-generator-policies.json): actual
  notebook costs, symmetry closure, six-application search settings,
  correction words and full-fiber checks. All five policies round-trip through
  the portable format and solve all 432 imported reference states with checked
  physical replay, totaling 2,160 applications.
- [Local loop probe](pocket-local-cycles.json): all 199 retained transported
  actions and legal witnesses, original-word comparisons, local half-turn
  loops and the checked shared-chunk grammar.

## Implemented follow-up

The public `c.template_human_repertoire` compiler and the Pocket Cube notebook
now implement the four requested changes:

1. `ShapePath` records checked source/target shapes, presentation frames, moves
   and faithful actions. Open pieces compose only at matching endpoints. Local
   loops can be transported through a setup and its inverse; closed reference
   paths compile only with a matching original-loop certificate.
2. Valid reference-bandage symmetry variants enter the vocabulary before
   template selection. They reuse a taught definition with explicit regrips.
3. Complete case corrections target the next stabilizer with later features
   free. Both automatic strategies and bounded mixed chains are scored in the
   vocabulary actually taught. Additive complete fallbacks and bounded
   physical-word search preserve coverage while exploiting cancellations.
4. `ChunkDictionary` extracts shared open pieces, inverse/rotation instances and
   setup/local-loop/undo structures. Dictionary and whole-case instruction
   symbols participate in the Pareto comparison alongside actual execution and
   recognition costs. Portable loading verifies recorded grammars and costs
   independently, without repeating the quality search.

Default notebook results, measured over all 432 reference states:

| Policy | Taught templates | Definition HTM | Mean solve HTM | Worst solve HTM |
| --- | ---: | ---: | ---: | ---: |
| Previous notebook | 3 | 43 | 126.94 | 247 |
| Implemented template compiler | 2 | 28 | 83.72 | 142 |

This is a 34% reduction in mean HTM and a 43% reduction in worst HTM. The
selected six-stage chain has indices `3, 2, 3, 2, 4, 3`, with 17 total cases
including solved cases and at most four cases in a stage. It places and orients
a small edge, solves two large pairs, solves the remaining edge, and finishes
corner orientation. Its shared three-move piece is `U F' L'`; the second
template visibly retains a transported local `B2` loop. The full three-generator
dictionary test independently recovers the earlier five-move K/P structure.

The retained [comparison](pocket-template-comparison.json) records settings,
physical replay costs, stages, formulas and search counters. The
[portable repertoire](pocket-template-repertoire.json) includes complete
proofs, both selected and fallback grammars, policies and Pareto metadata.
Reproduce both using:

    v2/.venv/bin/python v2/research/evaluate_pocket_template_repertoire.py

All selected corrections are checked on their entire observation fibers. The
comparison independently reloads and legally applies both old and new policies
to every imported reference state. New tests also cover nontrivial nonzero
roots, all 24 path rotations, incompatible endpoints, illegal canceled words,
corrupted portable claims, literal quality fallbacks, and both diagram frame
modes. The notebook cell has been re-executed and its recognition diagrams
inspected. These remain bounded computational results pending human solving
feedback; no minimum-dictionary or shortest-solution claim is made.
