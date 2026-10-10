# Human-method research results

The minimal [ordinary-cube notebook](../examples/Unbandaged3x3.ipynb) mirrors
`BandagedPocketCube`: shape input, group sizes, shape graph and a complete
staged guide. Its symbolic compiler handles 43 quintillion colored states
without enumerating them. Comparisons and replay experiments are saved here.
The [symbolic measurement record](unbandaged3x3-symbolic.json) retains exact
additive costs and selected imported-scramble replays. Full-block and
placement/orientation policies have 18/35 stages and 257/153 cases respectively.
Bounded dictionary improvement lowers the full-block additive mean/worst HTM
from 1,227.41/1,777 to 886.62/1,294; these costs exclude boundary cancellation.
The [implementation sequence](../../docs/symbolic-human-methods-plan.md) records
completed increments and remaining work.
The [orientation span probe](unbandaged3x3-orientation-span.json) checks a useful
next target: one twist-pair word and one flip-pair word, conjugated by legal
setups of at most two face turns, generate the entire orientation kernel.

The [dictionary and chain record](unbandaged3x3-dictionary-chain.json) retains
the exact orientation span, all candidate feature orders and additive costs,
bounded Schreier refinement metadata, and imported-scramble replays. Its
costs have the same pre-cancellation scope as the first symbolic comparison.
Selected methods retain portable subgroup certificates and original-loop
witnesses; dictionary reachability is measured separately from method coverage.
Adaptive full-block ordering reduces the exact additive mean/worst to
**225.60/400 HTM**, compared with 301.33/527 for the same shared dictionary on
the fixed full-block chain and 886.62/1,294 in the first bounded improvement.
The [singleton-rich optimizer check](singleton-rich-symbolic-optimization.json)
also verifies all 209 cases of a fused edge/corner bandage with a group of
order 75,090,283,462,656,000, including offline reload and legal replay.

Shared-template compilation now also supports symbolic policies. The
[ordinary-cube template record](unbandaged3x3-template-repertoire.json) measures
reusable algorithm bodies, typed shared chunks and case recipes, with exact
additive physical costs and offline replay checks. The
[singleton-rich template record](singleton-rich-template-repertoire.json)
checks the same machinery on the fused edge/corner bandage. Reproduce the
ordinary-cube measurements with
`v2/.venv/bin/python v2/research/evaluate_unbandaged_template_repertoire.py`.
Portable repertoires can be saved with `--save-repertoire`; the small measurement
records omit the full subgroup certificates and guarded chunk paths.

The [Pocket Cube solution comparison and loop research](pocket-cube-loop-research.md)
compares the 2015 human templates with the current notebook, measures the
vocabulary rebuild and symmetry effects over all 432 reference states, and
proposes reusable shape paths and local-loop discovery. Its implemented
follow-up now teaches two templates, averaging 83.72 HTM with a worst case of
142, compared with the previous notebook's 126.94/247. The
[implementation comparison](pocket-template-comparison.json) and independently
loadable [template repertoire](pocket-template-repertoire.json) retain exhaustive
432-state replay checks. Four reproduction scripts retain exact policy, action,
shared-chunk and implementation measurements.

Delivery 5's [repertoire and rule comparison](human-repertoire-compression.md)
measures taught master definitions, compressed rule families and complete
execution costs. Its artifacts distinguish computational memory proxies from
the human review scheduled for Delivery 6.

Delivery 4's [algorithm-aware chain comparison](human-chain-selection.md)
retains original BFS and pool-based automatic controls, mixed-feature
candidates and their Pareto tradeoffs in execution, recognition and
original-loop definitions. Its
deterministic [comparison report](human-chain-comparison.json) and separate
[machine measurements](human-chain-selection-measurements.json) record the
shared discovery pool and explicit search bounds.

The independently explored [recognition comparison](human-chain-recognition-comparison.json)
has separate [timings](human-chain-recognition-measurements.json). Both runs
use the same configured budgets. Persisted Alcatraz examples provide the
[execution guide](alcatraz-execution-method.md) and
[recognition guide](alcatraz-recognition-method.md), with loadable
[execution JSON](alcatraz-execution-method.json) and
[recognition JSON](alcatraz-recognition-method.json).

Delivery 3's [stage-aware algorithm comparison](human-algorithms.md) records
complete-method execution costs, definition tradeoffs and reproducible search
settings. Its deterministic results and machine timings are retained alongside
the initial chain investigation below. Human review remains Delivery 6.

## Chain baselines

Delivery 0 records exact reference-group and block-feature-chain experiments.
These are chain structures, without correction policies or a human algorithm
repertoire. See [the method contract](../../docs/human-methods.md).

Reproduce the deterministic results using the installed v2 Python environment
and GAP:

```sh
v2/.venv/bin/python v2/research/probe_human_chains.py \
  --output /tmp/human-chain-baseline.json \
  --measurements /tmp/human-chain-measurements.json
```

The committed baseline keeps mathematical results separate from machine-specific
timing and process high-water RSS. Measurements include shape/GAP preparation,
block-structure analysis, permutation enumeration, action validation, and chain
validation. RSS is cumulative when several puzzles run in one invocation.

Use repeated `--puzzle` options to select references. Most Signatures Cube is a
research alias with the same reference labels used by its existing notebook and
block-solver tests, rather than a newly added public fixture. An optional
`--max-group-elements` checks the certified order before group enumeration;
exceeding it produces `limit_reached`, empty chains, and exit code 2. There is no
default cap. This limit does not cap shape exploration or GAP preparation.

The retained run on 8 October 2026 completed all four references and checked
every recovered action, every selected generator transition, and every stage
fiber against its exact right coset. The report includes complete inventories
and the legally replayed reduced original-loop witnesses. Raw case counts
include the already-solved observation; no recognition compression or correction
policy is claimed.

| Reference | H | P | K | Shapes | Reduced loops |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alcatraz | 324 | 18 | 18 | 1,449 | 5 |
| Bicube Fuse | 60 | 60 | 1 | 121 | 2 |
| Shark Fin Soup | 36 | 12 | 3 | 1,938 | 2 |
| Most Signatures Cube | 10,368 | 144 | 72 | 92,176 | 4 |

The initial explicit-group backend is validated through **10,368 elements**.
This is the largest fully validated experiment, not a demonstrated performance
limit or a guarantee for every group of that order. The public stage planner
and research script preserve the repository's opt-in resource limits: neither
has an implicit enumeration cap. Examples explicitly select 10,368. Larger
groups can use the symbolic backend above; its algorithm quality and additive
cost scope are measured separately from exhaustive physical costs.

For Most Signatures Cube, reducing 3,336 extracted loops to four certified
generators leaves seven distinct generator/inverse actions. This keeps group
closure small; block-action recovery and validation are more expensive than
closure on this example. Future resource decisions should consider the selected
alphabet and action/feature workload as well as group order.
