# Symbolic staged methods for large cube groups

Agreed implementation sequence, 10 October 2026. This extends
[the human methods plan](human-methods-plan.md), especially Deliveries 7 and 8.
The first target is a complete, reusable method for `Unbandaged3x3`. The same
machinery must support bandages with many independent singleton blocks.

## Why the explicit pipeline stops

The ordinary cube has one reference shape and six short native face loops, but
its faithful colored group has 43,252,003,274,489,856,000 elements. GAP already
certifies its order and membership without enumerating these elements. The
human-method pipeline instead constructs every element, partitions every
subgroup into observation fibers, validates every residual and computes costs
over the whole group. Removing the notebook's enumeration cap would therefore
make the computation infeasible rather than supply a staged method.

The observations themselves are small. Fully solving one corner or edge gives
at most 24 cases. An experimental symbolic chain has 18 nontrivial stages and
257 cases in total, including the solved cases. Separating placement and
orientation gives 35 stages and 153 cases, with no stage exceeding 12 cases.
Both chains have index product equal to the full cube order and trivial final
stabilizer. These establish algebraic feasibility. The implementation results
below measure physical algorithms; human usability still needs improvement.

This also affects singleton-rich bandages. Complete shape exploration found
24 shapes for one fused edge/corner pair, but the reference-loop group still
has 75,090,283,462,656,000 elements. A small shape graph does not imply a small
colored group.

The algorithm dictionary had a separate limitation. Standalone mining omitted
equal-placement collision products and some mixed inverse commutators. Its
single support-ranked frontier crowded out edge algorithms after discovering
corner three-cycles. Increasing the budget alone did not fix these omissions.
Legal small effects do exist: replayed examples include an eight-turn corner
three-cycle, a sixteen-turn edge three-cycle, a fifteen-turn pair of opposite
corner twists and a thirty-six-turn pair of edge flips. They establish useful
search targets, not minimum lengths or availability under every bandage.

## Algebra and witness contract

Use the existing source-to-destination permutations and right actions in
execution order. At a stage let `H` fix all previous features and let `K` be the
stabilizer of the next solved feature. A representative `t_q` maps that solved
feature to observation `q`. Its fiber is the right coset `K t_q`, and applying
`t_q^-1` sends every residual in that fiber into `K`.

Prove the observation action, exact stabilizer, representative membership and
complete orbit coverage. Full-fiber enumeration is unnecessary. Check implied
fixed features on subgroup generators. Every exported word must retain an
expression in original legal root loops and pass physical replay. Open paths
and conjugating setups must respect the actual bandage; an arbitrary face
setup need not be legal.

Saved artifacts must load and apply without GAP or fresh factorization, as the
current small-group artifacts do. A portable strong generating certificate
must independently establish membership, order and stabilizer coverage. A
saved order or fingerprint is not a proof. Existing version-one artifacts and
explicit small-group backends remain supported.

## Implementation sequence

### 1. Witnessed symbolic subgroup backend

Introduce base and strong generating certificates, exact subgroup orders,
membership tests, small feature orbits and witnessed transversals. Integrate
them through planning, method compilation, validation, recognition, rendering
and persistence. No operation in this path may require an array of all group
elements. Retain the explicit backend for comparison on small fixtures.

The first delivery is a complete replayable ordinary-cube policy with compact
case tables and independently checked symbolic coverage. Its quality label
remains `computational_baseline` until short algorithms justify a stronger
claim. Both automatic feature strategies must terminate at identity.

### 2. Separate certificates from the physical repertoire

A small generating set serves efficient group calculations. Preserve cheap
redundant original loops, inverse turns, half turns and learned macros in the
physical dictionary. Dropping `B` from a sufficient cube generating set must
not force a long five-face representation of a one-turn algorithm. Generic
free-group preimages supply a complete fallback rather than a quality metric.

### 3. Discover local algorithms before method compilation

Add equal-placement and equal-protected-observation collisions `a b^-1`,
mixed inverse operands and distinct frontier quotas for corner, edge,
orientation and mixed effects. Keep useful early-stage actions alongside
sparse late-stage actions. Select short orientation generators with an exact
span check, rather than using an arbitrary abelian basis as the human
dictionary. Discovery must work from reference loops before a complete method
exists and keep explicit proposal, expansion and length budgets.

### 4. Choose the chain together with its dictionary

Score candidate next features using the short algorithms available in the
current stabilizer and their coverage of the small observation orbit. Preserve
buffers until their role is finished, admit useful legal setups, and reward
dictionary reuse. Use orbit searches instead of Dijkstra over all of `H`.
Retain a coupled odd corner/edge permutation bridge when parity requires it;
three-cycles and commutators alone cannot generate that bridge.

### 5. Keep completeness and human quality separate

For every final method verify original-loop provenance, legal replay, exact
subgroup membership, every observation correction, stage index products and
terminal triviality. Compare symbolic and explicit results on existing small
fixtures. Exercise the ordinary cube and singleton-rich bandages with imported
colored states whose histories are unavailable. Samples test execution;
symbolic certificates prove complete coverage.

### 6. Report costs with their actual scope

For complete deterministic coset tables under the uniform group distribution,
the exact additive mean is the sum of stage case means, and the exact additive
worst is the sum of stage maxima. These measure words before cancellation
between stages. Compute the cancellation-aware total through a suitable
dynamic program, or report sampled costs and bounds explicitly. Do not label
samples as exact group-wide statistics.

## Validation and continuation

The first increment must pass existing small-group method regressions,
symbolic certificate corruption tests, independent offline save/load tests,
both ordinary-cube chain strategies and legal application to imported
scrambles. Include at least one singleton-rich bandage with a huge colored
group. Keep large generated method artifacts under research results only when
their size and reproducibility justify checking them in. Following the user's
notebook requirement, `Unbandaged3x3` mirrors `BandagedPocketCube`: shape input,
group sizes, shape graph and the staged solution in one code cell. Comparisons,
search measurements and replay experiments belong in the research records.

Update this file with completed increments, actual commands and measured
results. Later work follows the sequence above; a working generic baseline is
not completion of chain/dictionary optimization or a classic layer method.

## Research foundations

[Egner and Püschel, Solving Puzzles Related to Permutation Groups](https://people.inf.ethz.ch/markusp/examples/puzzles/puzzles.html)
describe short commutator words, conjugation, bases adapted to small supports
and orbit transversals. [Korf, A Program That Learns to Solve Rubik's Cube](https://cdn.aaai.org/AAAI/1982/AAAI82-039.pdf)
learns macro operators from equal-image collisions and chooses component
orders that preserve useful operators. These support discovering the
dictionary and adapting the chain together.

[GAP group actions](https://gap-system.github.io/gap/doc/ref/chap41.html) and
[stabilizers](https://gap-system.github.io/gap/doc/ref/chap43_mj.html) supply
exact subgroup machinery. [GAP factorization documentation](https://gap-system.github.io/gap/doc/ref/chap39_mj.html)
distinguishes free-group preimages from `Factorization`, which enumerates the
group. The existing backend already uses free-group preimages; changing that
call alone cannot repair the surrounding explicit pipeline or optimize the
human dictionary.

## Progress

- 10 October 2026: sequence agreed and recorded. Symbolic certificates,
  feature-chain witnesses and localized discovery implementation started.
- First implementation delivered: `backend="symbolic"` in stage planning and
  method synthesis, portable version-two method certificates, offline
  recognition/application/loading, recognition diagrams and CLI support.
  Certificates check both the faithful group and the placement image. Existing
  explicit behavior and version-one artifacts remain available.
- The method witness library retains all original loops, including `B` on the
  ordinary cube. Standalone mining now includes inverse operands and placement
  collisions, with distinct effect families in its frontier. A bounded symbolic
  improvement path searches feature orbits and preserves complete fallbacks.
- The [executed ordinary-cube notebook](../v2/examples/Unbandaged3x3.ipynb) and
  [measurement record](../v2/research-results/unbandaged3x3-symbolic.json) contain
  both certified chains and an improved full-block policy. All three policies
  solved and legally replayed every selected imported scramble. The full-block
  chain's exact additive mean/worst went from 1,227.41/1,777 to 886.62/1,294 HTM.
  These costs exclude cancellation between stages and remain far above a useful
  classic human method. The solved, one-turn `R`, one-turn `B` and two-turn cases
  are handled in 0, 1, 1 and 2 physical turns by the full-block policies.
- Dedicated checks passed for both cube strategies, every stored case example,
  offline loading and tampering, exhaustive agreement on small fixtures, and a
  one-pair bandage with a reference group of order 75,090,283,462,656,000.
  The regression command is
  `v2/.venv/bin/python -m unittest discover -s v2/python/tests -v`.
  Its 465-test run had one existing missing-artifact skip and four assertions
  against code imported before fixes made during that run: three CLI call
  assertions and a boolean stage-number validation check. Fresh CLI and chain
  runs passed all 17 and 7 tests respectively; the other regression tests passed.
  The final fresh symbolic method run passed all eight tests, including a
  re-fingerprinted mismatch between outer and embedded GAP-version records.
  Focused suites can be rerun with the same command and, for example,
  `-p 'test_symbolic_human_methods.py'`.
- Shared template/repertoire optimization now supports symbolic groups; the
  third increment below records reusable bodies, recipes and diagrams.
  Further work is human review of the generated instructions, simplification
  of common setup/power families and joint chain selection using the taught
  recipe costs, rather than physical HTM alone.
  Cancellation-aware group-wide costs remain separate work. Bounded symmetry
  closure of the sparse seed bodies can also improve dictionary definition
  costs; existing setup closure already certifies orientation coverage.
- The [orientation span probe](../v2/research-results/unbandaged3x3-orientation-span.json)
  narrows that next step. At 1,800 proposals the mined dictionary spans all seven
  corner-twist dimensions but only two of eleven edge-flip dimensions. At
  12,000 proposals it spans the full orientation kernel of order 4,478,976.
  Conjugating one discovered sixteen-turn twist pair and one thirty-turn flip
  pair by legal setup words of at most two face turns also spans that kernel.
  An exact reduction selects eighteen sparse pair algorithms, totaling 465 HTM
  of definitions, with maximum length 33 HTM. This is a basis feasibility result,
  not a claim about full solution costs or a minimum dictionary.
  Rotations alone of this twist pair miss one corner dimension: its face-diagonal
  supports stay within the two vertex color classes. A face-turn setup connects
  those classes. Symmetry coverage therefore needs an exact span check.

### Second increment: dictionary and chain optimization

`discover_symbolic_dictionary` now discovers a rich physical pool before
choosing a chain, without hardcoded classic-cube algorithms. It retains native
signed/half turns, corner and edge permutation families, pure orientations and
bounded conjugates by legal original-loop setups. Exact prime-power coordinate
elimination checks orientation span, including carries for fused order-four
blocks. The selected sparse basis spans all retained pure orientations; its
independence and the actual kernel target are checked separately. Dictionaries
save and reload original-loop expressions offline. A consuming method compares
their declared group/quotient/kernel orders with independent certificates.

`select_human_chain(..., backend="symbolic")` compares both automatic controls
and bounded dictionary-aware feature orders. Small observation paths guide
feature selection. One-step lookahead scores the surviving short dictionary;
bounded Schreier words carry generators into the exact next stabilizer and
retain coupled odd permutation bridges. The implementation keeps a short exact
generating subset when available, reports its order, and preserves certified
generic corrections whenever the bounded pool is incomplete. Fixed-chain
improvement can reuse the same dictionary offline.

The [executed notebook](../v2/examples/Unbandaged3x3.ipynb) and
[dictionary/chain measurement record](../v2/research-results/unbandaged3x3-dictionary-chain.json)
retain the following exact additive costs before stage-boundary cancellation:

| Ordinary-cube method | Mean HTM | Worst HTM | Stages | Cases including solved |
| --- | ---: | ---: | ---: | ---: |
| Initial symbolic full-block baseline | 1,227.41 | 1,777 | 18 | 257 |
| First bounded improvement | 886.62 | 1,294 | 18 | 257 |
| Shared dictionary, fixed full-block order | 301.33 | 527 | 18 | 257 |
| Shared dictionary, adaptive full-block order | 225.60 | 400 | 18 | 257 |

The new dictionary retains 1,024 effects. Its eighteen independent orientation
pair algorithms span the full kernel of order 4,478,976 and total 455 HTM of
definitions, with maximum length 33. The selected adaptive method improves
231 case words and expands 284 observation-search states. Every stage's GAP
working pool spans its exact preceding subgroup, and no exported words were
lost to witness-expansion filtering in this run. The dictionary took 51.05
seconds and the full eight-candidate comparison/compilation 175.69 seconds on
this machine with concurrent checks; these are measured timings, not limits.
All eight selected imported scrambles and twenty-four seeded 25-turn imports
passed offline application and legal replay. The solved, `R`, `B`, `R U` and
four-turn commutator examples solve in 0, 1, 1, 2 and 4 physical turns. These
sample costs are separate from the exact additive group statistics.

The [singleton-rich bandage check](../v2/research-results/singleton-rich-symbolic-optimization.json)
fuses `UFR` with `UR` and leaves other blocks independent. Its certified group
has order 75,090,283,462,656,000. Bounded optimization produces sixteen stages
and 209 cases, with exact additive mean/worst 358.68/630 HTM. All 209 case
examples and twelve imported legal loop compositions solve after offline
reload. Its smaller dictionary spans fourteen of sixteen preceding working
subgroups; certified fallbacks cover the remaining stages.

Budget scopes are explicit in the search metadata: mining, setup conjugates
and adaptive Schreier proposals are separate phases. `max_expansions` bounds
optimized feature-prefix decisions; complete continuation and certification
remain available. `beam_width` limits a lookahead shortlist, capped at four;
at most two additional adaptive kinds are compared. State and word bounds
apply to each compiled candidate. Search is heuristic, and algorithm quality
remains `computational_baseline` until human review and shared-rule compression.

All 95 focused checks passed. Verification uses the Python unittest suites for symbolic dictionaries, chain
search, fixed-chain improvement, stage certificates and portable methods, plus
the existing explicit selector/improver, CLI and notebook regression suites.
For example:

```sh
v2/.venv/bin/python -m unittest discover -s v2/python/tests -p 'test_symbolic_dictionary.py' -v
v2/.venv/bin/python -m unittest discover -s v2/python/tests -p 'test_symbolic_chain_search.py' -v
```

### Third increment: shared symbolic templates and a minimal notebook

`template_human_repertoire(..., backend="symbolic")` now prepares a physical
dictionary and a certified feature chain, then compares complete whole-word
definitions with shared witnessed expression bodies. Legal rotations, inverses,
commutators, setups and powers retain exact original-loop witnesses. Existing
symbolic methods compile offline with their physical case words unchanged.
The shared policy compiler verifies transitions on entire observation fibers
using subgroup certificates, with finite progress ranks. Portable version-two
repertoires independently recheck those proofs, recipes and cost scope without
GAP or dictionary mining. Version-one explicit artifacts remain supported.

The guide teaches shared bodies once and repeats each named recipe's complete
turn sequence beside its case diagram and in the text guide's rule families and
cue lookup, so executing a case does not require scrolling to a definition.
Native face turns use ordinary Singmaster notation; they do not require
an extra memorized algorithm or a regrip around each individual turn. Diagrams
rotate only the presentation frame, with the physical instruction checked in
the fixed reference frame. Instance-local expression caches release their
method certificates after compilation; a lifetime regression covers this.

The notebook now has only a title and one code cell, matching
`BandagedPocketCube`: editable shape and drawing options, the group-size table,
the shape graph and the staged guide. It contains no solver comparisons,
discovery measurements, candidate tables or scramble experiments. Those live in
the research records and the reproduction script
`v2/research/evaluate_unbandaged_template_repertoire.py`.

Two ordinary-cube runs distinguish notation compression from chain choice:

| Source policy | Stages / cases | Learned bodies | Total definition HTM including native turns | Longest body HTM | Exact additive mean / worst HTM |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous optimized policy, compiled offline | 18 / 257 | 16 | 109 | 17 | 225.60 / 400 |
| Fresh minimal notebook with default preparation | 18 / 256 | 16 | 127 | 15 | 246.25 / 420 |

The first run compresses 124 inverse/symmetry-shared whole-word definitions to
22 macros: sixteen nontrivial bodies and six ordinary face turns. Definition
HTM falls from 1,691 to 109; the combined description score falls from 2,115
to 1,819. All physical case words remain identical. The fresh notebook uses
the public template defaults, including a lookahead shortlist of three rather
than the previous two. Bounded chain selection is heuristic; the larger
shortlist produces a different chain and does not guarantee lower HTM. Its
separate result is retained in the
[template measurement record](../v2/research-results/unbandaged3x3-template-repertoire.json).
All 256 stored case examples and 32 history-free selected/seeded imports pass
offline application and physical replay. The fresh guide has five shared
physical chunks and 223 instruction families. Some recipes remain elaborate:
the largest has 92 instruction symbols despite short learned bodies.
The first run's independently checked 257 case presentations include 478
instruction-frame checks and all 22 macro physical replays.

The [singleton-rich template record](../v2/research-results/singleton-rich-template-repertoire.json)
checks the fused `UR`/`UFR` bandage. It reduces definitions from 159 macros and
3,410 HTM to 29 macros and 112 HTM; the longest definition falls from 107 to
7 HTM. Offline reload, every one of the 209 case examples, twelve imported
legal loop compositions and 386 instruction-frame checks pass. Exact additive
physical costs remain 358.68/630 HTM. Definition compression lengthens some
case recipes, so these measurements are computational memory proxies rather
than a completed human-usability review.

All 79 focused checks pass: shared repertoire and generator/CLI regressions,
the explicit template compiler and root guards, symbolic repertoire/template
corruption and offline checks, instruction renderers and notebook refreshes.
Cancellation-aware group-wide costs remain separate work; all group-wide
physical costs above have the exact additive pre-cancellation scope.

The inline turn-sequence restoration passes all 22 focused instruction-renderer,
symbolic-template and notebook-refresh checks. The saved minimal notebook repeats
the turns for all 238 nontrivial cases; each sequence agrees with its diagram's
presentation frame, and all 256 case pictures are preserved.
