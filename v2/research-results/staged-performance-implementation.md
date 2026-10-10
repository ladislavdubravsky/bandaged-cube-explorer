# Implemented staged-solution performance changes

The recommendations in [the performance investigation](staged-solution-performance.md)
are now implemented in the production Python and Rust code. BeltRoad,
MostSignaturesCube and FourPair use automatic backend routing, optional graph
cells and a shared 120-second quality-search allowance. The ordinary-cube
notebook retains its existing richer optimization settings and unlimited overall
quality allowance.

## Updated notebook results

All three previously cancelled puzzles now finish through the production notebook
API, including a rendered guide:

| Puzzle | Analysis | Solver and validation | Guide rendering | Total | Expected / worst HTM |
| --- | ---: | ---: | ---: | ---: | ---: |
| BeltRoad | 16.43 s | 147.25 s | 49.62 s | 213.29 s | 140.17 / 295 |
| MostSignaturesCube | 3.85 s | 59.91 s | 9.26 s | 73.03 s | 79.88 / 135 |
| FourPair | 3.20 s | 112.06 s | 28.96 s | 144.22 s | 222.76 / 384 |

These measurements use `backend="auto"`, `preference="memory"`, a shared
120-second optimization allowance and the notebooks' actual diagram settings.
HTM counts each face turn, including a half turn, as one move. Expected costs
are exact additive expectations across the certified stage cases, rather than
averages of the three replay samples. BeltRoad reaches its quality cutoff and
returns the improved method retained before it; the other two complete their
quality passes within the allowance. Initial certification and required final
validation account for solver time outside that allowance.

Each result retains full native-generator membership coverage and solves three
history-free root-loop states with verified legal replay. FourPair's adaptive
method improves the initial fallback from 6,632.75 expected HTM to 222.76.
The runs overlap regression tests, and BeltRoad's guide includes cold Matplotlib
font-cache setup. Optional graph rendering is excluded. Wall times depend on
machine load; the earlier cancelled attempts do not establish an exact speedup
ratio. [End-to-end measurements](staged-performance-implementation-repertoires.json)
include progress, costs and replay results; the
[reproducer](../research/profile_implemented_repertoires.py) calls production APIs
without runtime patches.

## Graph rendering

`draw_bandage_graph` and `ShapeGraph.draw` accept `view="auto"`, `"summary"`,
`"local"` and `"full"`. Automatic rendering draws full graphs through
`max_vertices=1000`; larger components receive a small summary without layout,
NetworkX construction or shape-object materialization. Local rendering draws a
quarter-turn neighborhood around `start`, bounded by `radius` and `max_vertices`.
It keeps original vertex IDs and induced clockwise action edges. Full rendering
remains an explicit option, and `bandage_graph_layout` still requests full layout.
Cycle detection now scans arcs once. Large explicit drawings use a spatial index
for image clearance rather than constructing a dense pairwise distance matrix.

Ten staged example notebooks separate analysis, guide compilation and optional
graph rendering. All graph settings live in the third code cell, which users
can leave unevaluated. Graph work can no longer prevent the guide cell from
running. The three affected default summary drawings completed in 1.06, 0.51
and 0.19 seconds respectively, including
canvas rendering and excluding imports. None materialized the complete shape
list. [Graph measurements](staged-performance-implementation-graphs.json) retain
the sizes and settings.

## Reduced algebra and full coverage

Symbolic stage planning and adaptive chain search use the certified reduced
original-loop basis: five generators for BeltRoad, four for MostSignaturesCube
and three for FourPair. GAP no longer receives a free-group alphabet with
19,473, 3,336 or 4,968 generators for these operations. Returned words are remapped
to the original native generator IDs.

Full 48-sticker certificates retain every native root permutation. Membership
checks still prove coverage of every original generator. Portable validation
also proves that the declared reduced basis generates that full group before
using its smaller placement projection. Imported witnesses receive independent
legal physical replay; an already-validated immutable owner can reuse its proof.
Legacy artifacts without the new optional basis declaration still roundtrip.

Production control plans, including full certificates, completed as follows:

| Puzzle | Planning | Executable compilation |
| --- | ---: | ---: |
| BeltRoad | 9.61 s | 0.79 s |
| MostSignaturesCube | 1.93 s | 0.14 s |
| FourPair | 17.96 s | 3.13 s |

These are diagnostic timings with concurrent jobs, excluding initial analysis,
graph rendering and quality optimization. Each method covered all native loops
and solved three history-free root-loop samples with legal replay. The raw
control words remain long; these timings measure the certified fallback, not
the final optimized guide. [Plan measurements](staged-performance-implementation-plans.json)
and [their reproducer](../research/profile_implemented_symbolic_plans.py) retain
the exact cost scope and results.

## Caches and bounded physical discovery

The algebra basis and physical algorithm pool have distinct roles. Dictionary
discovery keeps all required reduced generators plus up to 32 redundant short
original loops by default. A small QTM-sorted window selects additional HTM-short
seeds without expanding the whole witness library. Required coverage witnesses
remain available independently of discovery caps. The six ordinary-cube face
generators remain in the physical pool.

Original/inverse/power admission now consumes a positive candidate budget;
commutator mining uses the remaining allowance. Setup words and conjugates keep
their own bounded counts. Metadata records original proposals, physical seed
counts, mining counts and admission cutoffs. Setting the candidate budget to
zero preserves the bounded original-only mode.

Loop words, simplified turn sequences, lengths and block actions are cached on
immutable generator owners. Expression builders share generator maps,
expansions and literal proofs, and cached expansions still check each caller's
size cap. Rotation tables and a bounded block-action cache avoid repeated frame
recovery. Dictionary and plan validation can reuse completed proofs for the same
immutable objects; changed copies and fresh imports validate independently.
Compilation reuses provenance owners and leaf-length tables. Native generator
lookup uses an ID index instead of scanning the entire generator vector.
Recipe compilation and guide instructions also reuse the exact declared witness
owner, record map, expansions and length table. Full tuple identity avoids
rescanning thousands of records for each recipe; reduced method alphabets still
reject undeclared leaves. [Focused fallback profiles](staged-performance-fallback-profiles.json)
locate this repeated work and retain qualified before/after measurements; the
[fallback reproducer](../research/profile_symbolic_fallback.py) uses current
production code.

Generous production dictionary settings completed on both measured puzzles:

| Puzzle | Dictionary time | Physical seeds / original roots | Algorithms | Orientation span |
| --- | ---: | ---: | ---: | ---: |
| MostSignaturesCube | 40.52 s | 36 / 3,336 | 877 | 72 / 72 |
| FourPair | 54.14 s | 35 / 4,968 | 1,024 | 3,456 / 3,456 |

Both runs used 12,000 original/mining proposals and at most 12,000 conjugates.
FourPair's ten independent orientation algorithms total 184 HTM, with maximum
36 HTM. MostSignaturesCube's five total 132 HTM, with maximum 37 HTM. These
establish complete orientation coverage without promising globally shortest
algorithms. [FourPair](staged-performance-implementation-dictionary.json) and
[MostSignaturesCube](staged-performance-implementation-most-dictionary.json)
records include concurrent-load qualifications; the
[dictionary reproducer](../research/profile_implemented_dictionary.py) uses
production code without runtime patches.

## Routing, progress and shared budgets

`backend="auto"` is available on the stage planner, method compiler, chain
selector and template repertoire compiler. `preparation_profile(analysis)`
exposes group order, graph size, loop counts, total/maximum witness lengths and
estimated explicit block-action entries. Explicit enumeration is recommended
only within the conservative envelope of group order 20,000, 250,000 block
entries, 256 original loops and 512 reduced QTM. Larger workloads use symbolic
preparation. An explicit backend request is preserved; passing an explicit
enumeration cap also expresses that intent. All three affected puzzles route to
symbolic preparation, including MostSignaturesCube whose small group alone
would hide its large loop and graph workload. These are inspectable heuristics,
not calibrated universal performance boundaries.

`template_human_repertoire` and `select_human_chain` accept
`optimization_seconds`, `max_optimization_work` and `progress`. One context
shares time and work across dictionary mining, algorithm improvement, adaptive
chains, template trials and chunk parsing. Nested calls cannot reset the
allowance. Work units count instrumented checkpoints and proposals; they are
not CPU instruction counts. GAP search retains its existing internal limits.
Progress events report phases, certified baselines, retained methods
and repertoires, cutoffs and final certification. Execution metadata records the
budget settings, work used, stop reason, elapsed time and routing profile.
The notebooks use `progress=None`; set `progress=print` to display these events.
These diagnostics are opt-in through budgets, progress or performed automatic
routing; default explicit/symbolic calls retain deterministic artifact metadata.

The first complete method is certified before the quality clock starts. Every
retained method has passed complete coverage and witness checks. Completed
template passes can publish validated repertoire snapshots, so a later cutoff
keeps the best complete guide found so far. Before any repertoire completes,
cutoff finalizes a retained certified method without new dictionary, chain or
chunk mining. Retained method comparison uses additive execution cost, or case
counts first for a recognition preference; repertoire comparison uses its
requested preference and exact measured metrics.

The optimization allowance excludes initial certification and mandatory final
fallback construction/validation. It therefore does not promise a hard total
wall-clock deadline. `timeout` remains a separate per-GAP limit, with optional
quality subprocesses additionally clamped to the remaining shared time. An
interrupted initial proof is never relabeled complete. Budgets default to
`None`, preserving unlimited quality work for existing callers.

## Reproduction and validation

Use the rebuilt release extension and project environment:

```sh
v2/.venv/bin/python v2/research/profile_implemented_repertoires.py
v2/.venv/bin/python -m unittest discover -s v2/python/tests -v
cargo test --locked --manifest-path v2/engine/Cargo.toml
```

The repertoire reproducer times analysis, the updated notebook solver and actual
guide rendering separately, records progress and exact additive costs, checks
every native generator and replays three history-free states per puzzle. Graph
rendering is measured separately. The stronger ordinary-cube and singleton-rich
optimizer paths remain covered by the existing regression suites. New checks
exercise reduced/full basis equivalence, noncontiguous generator IDs, omitted
coverage roots, altered portable basis declarations, warm-cache expansion caps,
rehashed witness corruption, shared nested budgets, certified cutoff fallbacks,
GAP timeout behavior and public graph modes.

The full Python sweep ran 538 tests: 535 passed and one was skipped. Two
compatibility failures were corrected while the sweep was running with its
previously imported code: deterministic default chain reports and zero local
template-budget metadata. Both exact tests passed in a fresh rerun. A fresh
40-test repertoire run, 18 computation tests, 10 cache tests and 30 graph tests
also passed. The Rust engine tests, clippy with warnings denied and formatting
checks passed, and the release Python extension was rebuilt. Final syntax
checks parsed 100 Python files and all 30 code cells in the ten staged notebooks;
report links and benchmark records were checked. No known failures remain.

This change does not add familiar 3×3 algorithm transport discovery to production.
That separate [investigation](familiar-algorithm-transport.md) remains a possible
next quality improvement.
