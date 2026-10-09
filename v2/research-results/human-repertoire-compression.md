# Shared repertoire and recognition rules: Delivery 5

Delivery 5 gives a complete fixed stage plan a shared vocabulary of witnessed
master algorithms. Case tables become verified instruction, power, and cycle
families. Every instruction preserves earlier features at its endpoint, and a
strictly decreasing rank proves that repeated instructions finish the stage.
The complete expanded case policy remains an ordinary version-one method.

The retained experiment covers the two Alcatraz methods from Delivery 4,
Bicube Fuse, and Shark Fin Soup. Default results preserve or improve both mean
and worst whole-method HTM. Explicit larger cost allowances demonstrate smaller
vocabularies with longer execution. Human usability remains unreviewed until
Delivery 6.

## Reproduction and retained artifacts

From the repository root, with the installed v2 Python environment and GAP:

```sh
v2/.venv/bin/python v2/research/compare_human_repertoires.py \
  --output /tmp/human-repertoire-comparison.json \
  --measurements /tmp/human-repertoire-measurements.json \
  --artifacts /tmp/human-repertoire-artifacts
```

The [driver](../research/compare_human_repertoires.py) loads the retained
[Alcatraz execution](alcatraz-execution-method.json) and
[recognition](alcatraz-recognition-method.json) methods. It prepares one exact
plan and default Delivery 4 chain selection for each other reference, using
the experiment's 10,368-element preparation cap. Stage features remain fixed
during repertoire optimization.

The [deterministic comparison](human-repertoire-comparison.json) retains source
fingerprints, all selected master words and original witnesses, complete
recipes, instructions, ranks, recognition families, candidate metrics, Pareto
membership, budget counts, and physical verification results. A second full
run reproduced the report byte for byte. The separate
[machine measurements](human-repertoire-measurements.json) are diagnostics;
variant order and shared-process caches affect these timings.

The selected strict Alcatraz artifacts are independently loadable without GAP:

- Execution: [portable repertoire](alcatraz-execution-repertoire.json) and
  [compressed guide](alcatraz-execution-repertoire.md).
- Recognition: [portable repertoire](alcatraz-recognition-repertoire.json) and
  [compressed guide](alcatraz-recognition-repertoire.md).

Both portable wrappers and guides reproduced identically after loading and
rendering with the final implementation. Wrapper loading independently checks
the embedded methods, master words, recipe transitions, whole case fibers,
ranks, family coverage, compiled projection, costs, and execution allowance.
The fingerprint detects accidental changes and is not itself a certificate.

## Search settings and controls

| Setting | Default |
| --- | ---: |
| `preference` | memory |
| `max_trials` | 64 |
| `max_recipes` | 2,000 |
| `max_power` | 4 |
| `max_extra_macros` | 16 |
| `max_setup_macros` | 16 |
| `allow_symmetry` | true |
| `max_cost_ratio` | 1.0 |

Three bounded searches use the same numeric trial and recipe settings, with
cost ratios 1.0, 1.1, and 1.25. Each runs independently on the same source
method. A fourth control sets trial, recipe, and extra-master budgets to zero.
That control still considers initial inverse-graph policies and is called the
**basic graph control**. It is not a pure physical-word alias operation.
Exact source costs and literal-inverse sharing are separately retained in
each variant's `baseline_metrics`.

The default execution guard compares complete mean and worst HTM against the
source method, after adjacent-turn simplification across the whole solution.
An explicitly larger ratio permits each cost to rise by that factor. Means
uniformly weight every element of H, including the solved state; this is not a
measured human scramble distribution. QTM is reported but is not guaranteed by
the HTM guard.

Recipe proposals include powers, setup/body/undo constructions, commutators,
and transfers through actual proper symmetries of the reference bandage.
Basic master/inverse edges and exact complete fallback recipes are outside
the bounded proposal count. Greedy deletion tests whether the remaining
vocabulary can still reach every stage's solved observation, then evaluates
completed policies and applies the cost guard.

The Pareto objectives are master count, total master-definition HTM, mean HTM,
worst HTM, and recognition-family count. Memory preference compares them in
that order. This is a measured representation tradeoff, not a minimum-memory
or globally optimal search.

## Exact action and progress checks

For a stage subgroup H_i, a whole instruction is eligible only if its full
effect belongs to H_i. Its action on the current feature must be constant on
every complete observation fiber. Reverse weighted paths on that observation
graph produce a positive integer progress rank and a next instruction for
every unsolved case. Following the instructions strictly decreases rank and
reaches the solved observation.

The eligibility unit is the complete instruction. A master can disturb an
earlier feature while its square restores it; a setup can disturb that feature
while the full setup/body/undo recipe restores it. No case decision is made
inside those instructions. All instructions also end at the reference shape.

No kernel-centrality assumption is used. Transitions are checked through the
faithful full sticker action, including coupled orientation and placement
effects. Cases are grouped only when the displayed instruction or power rule
expands to their verified transitions. A cycle label additionally requires one
admissible body whose observation cycle covers the whole stage and whose
listed powers solve every nontrivial case directly.

## Strict default results

| Source method | Source correction words / total HTM | Literal-inverse masters / HTM | Selected masters / HTM | Selected families | Mean HTM, source → selected | Worst HTM, source → selected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Alcatraz execution | 15 / 211 | 11 / 156 | 9 / 118 | 10 | 38.76 → 38.67 | 61 → 60 |
| Alcatraz recognition | 10 / 152 | 7 / 97 | 7 / 97 | 7 | 49.01 → 49.01 | 84 → 84 |
| Bicube Fuse | 10 / 112 | 7 / 84 | 7 / 84 | 7 | 26.03 → 26.03 | 49 → 49 |
| Shark Fin Soup | 7 / 74 | 4 / 40 | 4 / 40 | 4 | 21.78 → 21.69 | 34 → 34 |

Alcatraz execution gains beyond literal inverse sharing: the strict vocabulary
uses nine master definitions totaling 118 HTM. The zero-proposal basic control
already finds the same 38.67/60 execution costs using ten masters and 137 HTM;
the default search removes another definition without worsening those costs.
Its late two stages each use a verified three-case cycle with a master and its
inverse.

Alcatraz recognition retains the exact physical baseline under the strict
guard, while seven shared definitions replace ten independently listed
correction words. Five of its six stages have verified cycle rules. Bicube's
strict search also retains the exact physical baseline. Shark's basic graph
control supplies its small mean-HTM improvement; further default deletion is
rejected by reachability or the cost guard.

The stage observation counts remain 19, 16, 13, and 10 respectively. These
include solved cases. Compression reduces the instruction descriptions and
shared definition catalog, rather than changing the stabilizer indexes.

Master-definition HTM counts words taught as separate definitions in the new
guide. Source correction-definition HTM counts the previously listed expanded
correction words. A solver who already recognizes their original-loop
factorizations may learn fewer words than that source catalog suggests.
Original-witness vocabulary is reported separately: strict Alcatraz execution
still uses nine original loops totaling 105 HTM, and recognition uses six
totaling 66 HTM. These proxies do not measure learning time, operator knowledge,
regrip difficulty, or human recognition effort.

## Explicit execution and vocabulary tradeoffs

| Source method | Allowed ratio | Masters / definition HTM | Families | Mean HTM | Worst HTM |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alcatraz execution | 1.0 | 9 / 118 | 10 | 38.67 | 60 |
| | 1.1 | 7 / 87 | 8 | 40.05 | 67 |
| | 1.25 | 6 / 74 | 8 | 45.29 | 73 |
| Alcatraz recognition | 1.0 | 7 / 97 | 7 | 49.01 | 84 |
| | 1.1 | 6 / 78 | 7 | 49.62 | 86 |
| | 1.25 | 5 / 67 | 7 | 53.49 | 96 |
| Bicube Fuse | 1.0 | 7 / 84 | 7 | 26.03 | 49 |
| | 1.1 | 2 / 28 | 5 | 26.53 | 49 |
| | 1.25 | 2 / 28 | 5 | 30.53 | 60 |
| Shark Fin Soup | 1.0 | 4 / 40 | 4 | 21.69 | 34 |
| | 1.1 | 4 / 40 | 4 | 21.69 | 34 |
| | 1.25 | 2 / 26 | 4 | 27.11 | 42 |

Bicube's two-master policies use genuine reference-bandage symmetry transfers;
the 1.1 policy reuses one master under `x y` and `x' z'`. Shark's 1.25 policy
also uses a certified transfer, under `x2 y`. The resulting face-only words
and whole-fiber effects are checked. Setup and commutator candidates are
exercised, but none is selected by these retained policies.

The larger allowance does not guarantee a better selected point. Bicube's
1.25 run follows a different greedy deletion path and returns the same master
count, definition HTM, and family count as its 1.1 run, with worse execution.
Across these retained runs, the 1.1 point therefore dominates it under the
stated objectives. Candidate-family choices, word boundaries, ties, and
deletion order can change the outcome. More available recipes also do not
guarantee that an additive graph policy improves complete physical costs.

## Work, validation, and next delivery

| Source method | Strict trials | Recipe proposals | Accepted deletions | Selected rule kinds |
| --- | ---: | ---: | ---: | --- |
| Alcatraz execution | 31 | 720 | 6 | instructions, powers, cycles |
| Alcatraz recognition | 8 | 216 | 0 | instructions, cycles |
| Bicube Fuse | 7 | 182 | 0 | instructions, powers, cycles |
| Shark Fin Soup | 4 | 64 | 0 | instructions, powers, cycles |

None of the three bounded searches for any reference reaches the configured
64-trial or 2,000-proposal limit. Greedy stopping, template families, powers,
and local path choices still restrict exploration; this is not exhaustive
repertoire search. The basic control intentionally has zero work caps and
reports those zero caps as reached.

For all sixteen selected variants, the driver independently imports every
reference-group state without scramble provenance, reloads the portable
wrapper, applies its recognition instructions, checks every rank decrease,
and legally replays the complete solution word. All **2,976 applications**
solve, and their recomputed HTM/QTM totals and worst cases match the reported
metrics. Thirteen early option/path checks reject invalid work budgets,
nonfinite ratios or timeouts, output aliases, and source-method overwrites
before preparation. The core repertoire and CLI regression suites also pass.

Delivery 6 should review the actual master words, orientation cues, powers,
regrips, and whole-instruction boundaries. The Alcatraz execution and
small-table recognition guides provide distinct controls for that review.
Further experiments can revise path tie-breaking, deletion order, or joint
selection when the measured gains and human feedback justify it.
