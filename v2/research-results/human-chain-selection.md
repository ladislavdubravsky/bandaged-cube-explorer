# Algorithm-aware feature chains: Delivery 4

Delivery 4 varies the recognizable block-feature chain while reusing one
discovered word pool. Every published candidate is a complete method, with
exact observation cases and legally replayed original-loop witnesses. Earlier
features hold at whole-algorithm endpoints; effects on later blocks remain
free. These methods have not received the human review planned for Delivery 6.

The experiment finds a substantial execution improvement on Alcatraz, a small
improvement on Bicube Fuse, and a useful block-first control on Shark Fin Soup.
Alcatraz also shows a clear tradeoff: the faster method has larger recognition
tables and more original loop definitions.

## Reproduction and comparison scope

From the repository root, with the installed v2 Python environment and GAP:

```sh
v2/.venv/bin/python v2/research/compare_human_chains.py \
  --output /tmp/human-chain-comparison.json \
  --measurements /tmp/human-chain-selection-measurements.json
```

The [comparison driver](../research/compare_human_chains.py) prepares one exact
group per reference and passes that prepared plan to the chain selector. It
does not repeat GAP analysis for individual candidates. The experiment caps
preparation at 10,368 group elements; the public backend retains its optional
enumeration cap. Repeated `--puzzle` options select references.

The default uses `placement_then_orientation` as the origin of one structured
Delivery 3 discovery run. Its witnessed pool is frozen and shared across the
fixed chains, greedy search, and beam search. The pool retains candidate
effects that were not selected by the origin method. Each stage also has a
complete inverse-BFS correction fallback. The comparison includes both raw
BFS and pooled correction policies for placement-first and block-first chains.
Raw policies remain actual Pareto candidates: a shorter local correction can
affect later cases, boundary cancellation, or shared definition costs.

| Chain setting | Value |
| --- | ---: |
| `preference` | execution |
| `beam_width` | 4 |
| `max_expansions` | 64 |
| `max_methods` | 16 |

| Shared discovery setting | Value |
| --- | ---: |
| `mode` | structured |
| `max_seed_loops` | 32 |
| `max_candidates` | 3,000 |
| `max_word_length` | 3 |
| `rounds` | 1 |
| `max_states` | 2,000 |
| `max_stage_generators` | 24 |
| `max_alternatives` | 3 |
| `max_htm_length` | 120 |
| `max_expanded_moves` | 480 |

The script exposes these settings through options with hyphens, using
`--discovery-mode` for the discovery mode. Output aliases and invalid budgets
are rejected before reference preparation.

The [deterministic report](human-chain-comparison.json) retains every candidate's
features, subgroup orders, cases, expressions, physical words, used original
definitions, portable-method fingerprint, exact metrics, Pareto membership,
and preferred candidate IDs. A second run reproduced this report byte for byte.
[Machine timings](human-chain-selection-measurements.json)
are separate diagnostics. The compact comparison is an inspection artifact;
executable methods continue to use the existing version-one portable schema.

## Ranking and exact evaluation

Greedy and beam branches consider both placement and full-block features that
strictly reduce the current subgroup. Redundant features are skipped. Stage
policies are cached by subgroup and feature, while distinct prefixes reaching
the same subgroup remain eligible: their accumulated words and definitions
can differ.

Partial branches receive a deterministic complete, minimum-index full-block
rollout. Its additive mean stage HTM guides search. Under uniform initial H,
every stage maps each observation coset bijectively onto the next subgroup,
so residuals remain uniform. This makes additive mean stage execution exact
for that cost model. It is a proxy for the reported full physical solution:
adjacent turns can cancel across stage boundaries. A partial physical word's
length is not a lower bound on the final word.

Completed candidates are independently validated and evaluated on every
element of H, including the solved state, with uniform weight. Reported HTM
and QTM simplify adjacent turns across the whole solution. These weights
describe the experiment rather than a measured human scramble distribution.

The Pareto comparison uses eight dimensions: mean HTM, worst HTM, maximum
stage case count, sum of stage case counts, used original-loop count, total
original-loop definition HTM, total correction definition HTM, and stage
count. Execution preference compares those dimensions in that order;
recognition preference starts with maximum and summed case counts. Candidate
ID breaks exact ties. Distinct recognition features with equal metric vectors
can remain on the frontier.

The default report's two preferred IDs are chosen from the same
execution-ranked candidate set and frontier. A second comparison below runs
`preference="recognition"` during exploration, changing branch ranking.
Discovery starts from one placement-first chain in each run, so the available
pool can favor that origin. Equal configured budgets and exact coverage do not
establish global optimality.

## Complete-method execution costs

| Reference | Policy | Mean HTM | Worst HTM | Stages | Maximum / summed cases |
| --- | --- | ---: | ---: | ---: | ---: |
| Alcatraz, H=324 | Raw placement-first | 54.86 | 94 | 6 | 3 / 16 |
| | Raw block-first | 49.59 | 92 | 5 | 9 / 19 |
| | Pooled placement-first | 50.40 | 86 | 6 | 3 / 16 |
| | Pooled block-first | 44.75 | 77 | 5 | 9 / 19 |
| | Greedy | 38.76 | 61 | 4 | 9 / 19 |
| | Selected beam, execution | 38.76 | 61 | 4 | 9 / 19 |
| Bicube Fuse, H=60 | Raw placement/block-first | 29.00 | 57 | 3 | 6 / 13 |
| | Pooled placement/block-first | 26.70 | 49 | 3 | 6 / 13 |
| | Greedy | 26.25 | 49 | 3 | 6 / 13 |
| | Selected beam, execution | 26.03 | 49 | 3 | 6 / 13 |
| Shark Fin Soup, H=36 | Raw placement-first | 50.28 | 89 | 3 | 4 / 10 |
| | Raw block-first | 47.97 | 96 | 3 | 4 / 10 |
| | Pooled placement-first | 22.67 | 35 | 3 | 4 / 10 |
| | Pooled block-first, selected | 21.78 | 34 | 3 | 4 / 10 |
| | Greedy | 21.78 | 34 | 3 | 4 / 10 |

Alcatraz's execution-selected chain fully solves Edge UR, Corner UFR, Corner
UBR, then Pair BR-DBR. Its indexes are 4, 9, 3, 3. These stages also imply
other fixed features, and the terminal subgroup is the identity. Greedy
already reaches the best observed execution costs; beam finds tied variants.
Within the execution-ranked frontier, the recognition-preferred choice remains
pooled placement-first, with indexes 2, 3, 3, 2, 3, 3 and no stage exceeding
three cases.

Bicube's selected chain places Pair UBR-UR, places Pair FL-DFL, then fully
solves Pair UBL-UB. Its index profile remains 6, 5, 2. Beam improves whole-word
mean HTM from greedy's 26.25 to 26.03 despite equal additive mean stage HTM
of 27.07, demonstrating why final evaluation must include boundary effects.
Execution and recognition preferences choose the same retained candidate.

Shark's pooled block-first control fully solves Corner UFR, Pair UBR-UR, then
Pair UFL-UF. Greedy and beam add no better observed execution policy. Both
preferences choose the pooled block-first control. Its index profile is
3, 4, 3 rather than placement-first's 4, 3, 3.

QTM also improves for the selected policies in this experiment. Selected
mean/worst QTM are 45.69/74 for Alcatraz, 29.60/56 for Bicube, and 26.00/40
for Shark. QTM is reported but is not a Pareto objective here.

## Recognition-directed comparison

The second comparison changes branch ranking while retaining every numeric
chain and discovery budget above:

```sh
v2/.venv/bin/python v2/research/compare_human_chains.py \
  --preference recognition \
  --output /tmp/human-chain-recognition-comparison.json \
  --measurements /tmp/human-chain-recognition-measurements.json
```

The [recognition-directed report](human-chain-recognition-comparison.json) and
[separate machine timings](human-chain-recognition-measurements.json) retain
this run independently. A second recognition-directed run reproduced its
report byte for byte. Each selector call performs its own discovery and
chain search, with the same configured limits and placement-first discovery
origin. The three discovery metadata records match their execution-run
counterparts. A single combined budget across both comparisons is not claimed.

| Reference | Recognition choice | Mean HTM | Worst HTM | Maximum / summed cases |
| --- | --- | ---: | ---: | ---: |
| Alcatraz | From execution-run frontier | 50.40 | 86 | 3 / 16 |
| | Recognition-directed beam | 49.01 | 84 | 3 / 16 |
| Bicube Fuse | Either comparison | 26.03 | 49 | 6 / 13 |
| Shark Fin Soup | Either comparison | 21.78 | 34 | 4 / 10 |

Alcatraz's recognition-directed chain places Corner UFR, places Pair BR-DBR,
then fully solves Pair FL-DFL, Edge UR, Corner UBR, and Corner UFL. Its indexes
are 3, 3, 2, 2, 3, 3. It retains six stages and small tables while improving
execution over the default report's recognition choice. Its correction
definitions total 152 HTM, with six original loops totaling 66 HTM. This is
more original vocabulary than the pooled placement-first method's five loops
and 56 HTM. Selected mean/worst QTM are 56.50/98.

Recognition-directed greedy gives 51.88/88 HTM on Alcatraz, so beam provides
the useful saving in this experiment. The search evaluates the full limit of
16 additional methods; this bounds the conclusion. Bicube and Shark choose
the same retained policies as the execution-directed comparison.

## Definition and recognition tradeoffs

| Reference | Policy | Corrections | Correction definition HTM | Used original loops | Original-loop definition HTM |
| --- | --- | ---: | ---: | ---: | ---: |
| Alcatraz | Pooled placement-first | 10 | 154 | 5 | 56 |
| | Execution-selected | 15 | 211 | 9 | 105 |
| | Recognition-directed selected | 10 | 152 | 6 | 66 |
| Bicube Fuse | Pooled placement-first | 10 | 126 | 3 | 21 |
| | Execution-selected | 10 | 112 | 3 | 21 |
| Shark Fin Soup | Pooled placement-first | 7 | 76 | 4 | 41 |
| | Execution-selected | 7 | 74 | 4 | 40 |

Alcatraz's lower execution cost requires more correction definitions and nearly
twice the original-loop definition HTM. The raw Alcatraz policies also remain
on the frontier because they use only 55 HTM of original definitions. Bicube's
and Shark's raw policies retain a smaller original vocabulary while requiring
longer execution. These quantities are memory proxies, not measured learning
costs. Shared vocabulary and inverse/power rules remain Delivery 5 work.

A strict chain needs one correction per nontrivial observation, giving
`sum(index - 1)` corrections. Every complete chain's index product is |H|;
the maximum and sum of its indexes can still differ. Stage count alone does
not capture recognition or repertoire cost.

## Faithful point-chain structural control

The driver independently builds a minimum-nontrivial-orbit stabilizer chain
on the 48 noncenter sticker points, breaking ties by point index. It validates
every observation fiber as an exact right coset and checks identity termination
and the index product. This control has `coverage_scope: chain_structure_only`
and `human_method_complete: false`. No correction or human recognition policy
is compiled for abstract point observations.

| Reference | Point-chain indexes | Stages | Maximum / summed cases |
| --- | --- | ---: | ---: |
| Alcatraz | 3, 2, 2, 9, 3 | 5 | 9 / 19 |
| Bicube Fuse | 6, 5, 2 | 3 | 6 / 13 |
| Shark Fin Soup | 3, 4, 3 | 3 | 4 / 10 |

The Alcatraz point chain resembles block-first structurally, while its
placement-first block chain keeps recognition tables smaller. This is a
control for the choice of action and features, not evidence of human quality.

## Search work and next experiments

| Reference | Search preference | Expanded branching nodes | Additional completed methods | Evaluated stage edges | Shared effects / retained words |
| --- | --- | ---: | ---: | ---: | ---: |
| Alcatraz | Execution | 17 | 13 | 506 | 323 / 901 |
| | Recognition | 19 | 16 | 710 | 323 / 901 |
| Bicube Fuse | Either | 12 | 11 | 309 | 57 / 171 |
| Shark Fin Soup | Either | 12 | 11 | 180 | 35 / 105 |

The fixed controls are outside the additional-method budget. Branching node
counts and cached stage-edge/rollout work are separate measurements. Alcatraz's
recognition-directed search reaches the 16-additional-method limit. The other
runs reach neither that limit nor the 64-node limit, but beam width and
discovery bounds still prune possibilities. A report with no exhausted counter
is not an exhaustive chain or word search.

Delivery 5 should explore the execution/definition tradeoff with a shared
vocabulary policy, retaining Alcatraz's small-table methods as useful controls.
The remaining selection experiments include different discovery origins,
larger recognition-directed search budgets, and larger groups. Thorough human
review remains planned for Delivery 6.
