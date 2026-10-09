# Stage-aware algorithm discovery: Delivery 3

Delivery 3 improves complete shape-only methods while keeping their feature
chains fixed. Every selected correction restores earlier features at its
endpoint and corrects the current observation. Effects on later blocks are
unrestricted. The original complete policy remains available as a fallback.

The retained experiment uses Alcatraz, Bicube Fuse and Shark Fin Soup. All
three selected methods retain certified coverage of their entire reference
groups. Human usability has not been reviewed.

## Reproduction and scope

From the repository root, with the installed v2 Python environment and GAP:

```sh
v2/.venv/bin/python v2/research/compare_human_algorithms.py \
  --output /tmp/human-algorithm-comparison.json \
  --measurements /tmp/human-algorithm-measurements.json
```

The [comparison script](../research/compare_human_algorithms.py) compiles one
complete baseline per reference, then compares three discovery modes with the
same configured limits. It explicitly caps baseline group enumeration at
10,368 elements; this is the experiment's scope, not a new public default.
Repeated `--puzzle` options select references. Every search setting below has
a corresponding command-line option, replacing underscores with hyphens.

| Setting | Value |
| --- | ---: |
| `max_seed_loops` | 32 |
| `max_candidates` | 3,000 |
| `max_word_length` | 3 |
| `rounds` | 1 |
| `max_states` | 2,000 |
| `max_stage_generators` | 24 |
| `max_alternatives` | 3 |
| `max_htm_length` | 120 |
| `max_expanded_moves` | 480 |

`original` adds native loop witnesses and inverses to the reduced baseline
library. `shallow` also explores short combinations and bounded macro paths.
`structured` adds powers, commutators, conjugates, protected-coset word
quotients, witnessed Schreier words, and searches within stage stabilizers.
The same limits apply to all modes, but modes may use less than their budget.

Proposal counts include identities, duplicates and pruned expressions.
Settled macro-search states share one budget across the run. Word length
bounds shallow words and macro paths; structured trees have separate physical
expansion limits. Complete reference preparation, final certification and
whole-group quality evaluation are outside the quality-search budget.
Additive macro costs guide discovery and do not prove shortest physical words.
These are bounded candidate searches, not complete strong-generator routines.

The [deterministic report](human-algorithm-comparison.json) retains reference
labels, H/P/K, GAP version, baseline and selected-method fingerprints, chain
features, exact physical words, expression trees, leaf definitions, case
policies, counts and quality metrics. A second run reproduced it byte for
byte. [Machine timings](human-algorithm-measurements.json) are separate; they
are diagnostics rather than performance guarantees. Memory was not measured
in this experiment.

## Complete-method execution costs

These means include every element of H, including the solved state, with
uniform weight. Costs are measured after simplifying adjacent turns across
the entire physical solution, so they include interactions between stages.
HTM counts a half turn as one move; QTM counts it as two.

| Reference | Policy | Mean HTM | Worst HTM | Mean QTM | Worst QTM |
| --- | --- | ---: | ---: | ---: | ---: |
| Alcatraz (H=324) | Baseline | 54.86 | 94 | 64.85 | 112 |
| | Original | 50.40 | 86 | 57.66 | 100 |
| | Shallow | 50.40 | 86 | 57.66 | 100 |
| | Structured | 50.40 | 86 | 57.66 | 100 |
| Bicube Fuse (H=60) | Baseline | 29.00 | 57 | 32.67 | 64 |
| | Original | 27.17 | 50 | 30.67 | 56 |
| | Shallow | 26.70 | 49 | 30.40 | 56 |
| | Structured | 26.70 | 49 | 30.40 | 56 |
| Shark Fin Soup (H=36) | Baseline | 50.28 | 89 | 59.11 | 104 |
| | Original | 22.67 | 35 | 27.61 | 42 |
| | Shallow | 22.67 | 35 | 27.61 | 42 |
| | Structured | 22.67 | 35 | 27.61 | 42 |

All proposals pass the full-method mean/worst HTM guard. QTM also improves in
this experiment, but that is not a guarantee of the guard. If a locally
shorter policy makes the complete method's mean or worst HTM worse, the API
returns the baseline and reports the rejected proposal separately.

On Shark Fin Soup, the last two correction definitions shrink from 48 and 50
HTM to 19 each. Another correction shrinks from 18 HTM to the native six-turn
loop `U F2 D' U' F2 D`. These improvements need no extra structured discovery:
the reduced generating set was adequate for completeness but omitted useful
short native loops. Keeping witnesses beyond a minimal generating set is
therefore valuable for method quality.

## Definition and reuse tradeoffs

The selected structured policies have these definition costs. Original-loop
definitions are a reuse proxy, not a measured human memory cost. A visible
literal or rotated expression may introduce a different remembered definition;
the JSON also reports visible-leaf counts.

| Reference | Corrections, before/after | Total correction HTM, before/after | Used original loops, before/after | Original-loop definition HTM, before/after |
| --- | ---: | ---: | ---: | ---: |
| Alcatraz | 10 / 10 | 168 / 154 | 5 / 5 | 55 / 56 |
| Bicube Fuse | 10 / 10 | 145 / 126 | 2 / 3 | 14 / 21 |
| Shark Fin Soup | 7 / 7 | 180 / 76 | 2 / 4 | 26 / 41 |

Shorter execution can require more original definitions. The current choice
prioritizes physical HTM, QTM and local expression cost; it does not optimize
the shared vocabulary. A strict complete chain has one direct correction per
nontrivial observation, so this search does not reduce that case count.
Inverse/power rules and shared-vocabulary policies belong to Delivery 5.

## Search work and conclusions

| Reference | Mode | Proposed expressions | Settled states |
| --- | --- | ---: | ---: |
| Alcatraz | Original | 62 | 0 |
| | Shallow | 1,385 | 324 |
| | Structured | 2,400 | 538 |
| Bicube Fuse | Original | 6 | 0 |
| | Shallow | 312 | 55 |
| | Structured | 1,723 | 125 |
| Shark Fin Soup | Original | 36 | 0 |
| | Shallow | 1,071 | 36 |
| | Structured | 2,056 | 60 |

Original-loop selection supplies most gains, and shallow search improves
Bicube further. Structured mode finds no additional execution saving on these
three fixed chains at this budget, despite exercising its candidate families
and stage searches. This does not establish that such constructions are
unhelpful on other chains or groups. The next comparison should vary the
feature chain while reusing the discovered words, rather than assuming that
more discovery rounds are the best next investment.

The local GAP installation lacks `orb`; no new package dependency is added.
Core operations and the witnessed explicit-group backend suffice for this
delivery. Symbolic scaling and a short-subgroup-generator package comparison
remain later experiments.

## Validation

The 13 dedicated algorithm tests exhaustively apply both improved and
reloaded methods to all 420 root states across these references, legally
replay retained alternatives, and check their effects on entire stage fibers.
They cover composite words whose factors disturb protected blocks, exact
whole-method metrics, deterministic export, zero/restrictive budgets,
duplicate accounting, nonzero roots, repeated improvement, and baseline
fallback after a whole-method regression. The existing method and CLI
regressions also pass.

Selected methods retain the version-one portable schema and are independently
loadable without GAP. Search inspection reports include extra candidates and
alternatives; they are separate from executable method artifacts. See the
[public method documentation](../../docs/human-methods.md) for the API and CLI.
