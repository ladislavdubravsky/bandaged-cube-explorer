# Human-method research results

Delivery 3's [stage-aware algorithm comparison](human-algorithms.md) records
complete-method execution costs, definition tradeoffs and reproducible search
settings. Its deterministic results and machine timings are retained alongside
the initial chain investigation below.

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
inputs will need additional measurements or the planned symbolic backend.

For Most Signatures Cube, reducing 3,336 extracted loops to four certified
generators leaves seven distinct generator/inverse actions. This keeps group
closure small; block-action recovery and validation are more expensive than
closure on this example. Future resource decisions should consider the selected
alphabet and action/feature workload as well as group order.
