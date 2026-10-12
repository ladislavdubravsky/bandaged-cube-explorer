# Algorithm-informed orientation stages: first production increment

The subsequent [fresh architecture review](method-architecture-review.md)
explains why this increment alone cannot discover a CFOP- or Petrus-like method,
and gives the broader goal, recognition and palette-search changes needed.

The staged solver can now choose an anonymous orientation goal on several
compatible slots, using the algorithms available at the current subgroup.
This is a production feature in both backends, including portable methods,
template repertoires and recognition diagrams. It is a first increment toward
shorter methods with a small learned repertoire, rather than a completed
optimization of that repertoire constraint.

## What was implemented

`BlockFeature("orient_slots", cells)` observes the phase of the occupant of
each named destination slot. It ignores occupant identities and permits
placement to remain unsolved. The cells must form complete reference blocks
of one compatible geometric footprint class with nontrivial cyclic
orientation. The slot region must be invariant under the entire preceding
subgroup. These restrictions make the observation a well-defined group action
and its solved condition an exact subgroup stabilizer.

The symbolic planner lifts each block action to phase ports:
`(slot, q) -> (destination, q + phase mod orientation_order)`. It stabilizes
the selected zero-phase ports as a set, retaining original legal root-loop
witnesses and portable subgroup certificates. The explicit planner verifies
the corresponding observation fibers against exact right cosets. Recognition
reads the destination phase field in inventory order. Diagrams display one
intrinsic facet marker per occupant, making phases visible without revealing
piece identities.

`discover_algorithm_targets(inventory, group, algorithms)` derives invariant
slot orbits from the current subgroup and proposes unions of orbits whose
phases a physical algorithm changes together. It enumerates the full reachable
phase domain under that subgroup, then computes forward correction recipes
using the available palette. Its report includes repair costs, uncovered
cases and algorithms preserving the all-zero condition. Oversized domains
are discarded, never truncated into a false coverage claim. Missing cases
receive no finite mean cost.

`select_human_chain` now considers these targets automatically. Explicit
greedy and beam searches compare them with block features. Symbolic search
scans bounded certified prefixes, forces shortlisted phase goals, refines
recipes inside their stabilizers and chooses the remaining block goals
adaptively. It compares complete methods and retains both existing control
chains. Original target recipes and newly refined graph paths compete under
the same physical word limits. Pattern, proposal, prefix and method limits
bound this pass; existing shared optimization cutoffs retain certified
coverage. The public API and limits are documented in
[human-methods.md](../../docs/human-methods.md#select-an-algorithm-aware-chain-delivery-four).

## Measured results

The [Alcatraz record](algorithm-informed-alcatraz.json) compares enabled and
disabled targets at the same search settings. Both saved methods were loaded
independently and physically replayed on all 324 group states.

| Alcatraz method | Exact physical mean HTM |
| --- | ---: |
| Best pooled fixed block-chain control | 46.9167 |
| Existing block-only adaptive search | 43.3704 |
| Adaptive search with orientation targets | 43.2407 |

The new selected chain fully solves one block, orients the occupants of three
corner slots together, then places the remaining blocks. Its improvement is
7.8% over the pooled fixed controls and 0.3% over the same-budget existing
adaptive search. The latter is the appropriate measure of this increment's
additional benefit on this fixture.

The subsequent [four-example comparison](orientation-target-example-comparison.json)
also finds a gain on **BandagedPocketCube**. Each arm uses the same explicit
backend, dictionary-discovery limits, eight search expansions and two additional
method slots. Independently loaded methods solve every group state in both
arms: 324 Alcatraz, 60 Bicube Fuse, 36 Shark Fin Soup and 432 Pocket states.

| Example | Mean physical HTM, disabled → enabled | Search seconds, disabled → enabled |
| --- | ---: | ---: |
| Alcatraz | 43.3704 → 43.2407 | 0.651 → 0.797 |
| Bicube Fuse | 26.2500 → 26.2500 | 0.171 → 0.172 |
| Shark Fin Soup | 21.7778 → 21.7778 | 0.133 → 0.142 |
| BandagedPocketCube | 89.4769 → 79.9236 | 1.378 → 1.329 |

Pocket improves by 10.7% in mean length, and its worst length falls from 169
to 134 HTM. These are comparisons with the same-budget block-only search,
rather than older notebook guides or hand-designed template policies.
Bicube has no proposed phase targets; Shark's proposed targets yield no
whole-method saving at these limits.

The search times are medians of three sequential runs per arm with alternating
run order. They include dictionary discovery and complete-method scoring and
validation, and exclude the shared initial group preparation, template
compilation, portable reload and exhaustive replay. Preparation was measured
separately: approximately 2–3.4 seconds per puzzle. Short-run timing variation
is visible in the raw record, so Pocket's apparent 3.5% speedup should be
treated as essentially unchanged runtime. Alcatraz adds about 0.15 seconds
and Shark about 0.009 seconds. Time directly inside phase-target analysis is
only about 19, 1, 5 and 17 milliseconds respectively; changes to the candidate
chains and their scoring account for additional work elsewhere.

The [ordinary-cube comparison](algorithm-informed-stage-implementation.json)
uses the same witnessed dictionary, search settings and seeded imported
scrambles. At the recorded bounded search budget, the selector retains the
existing method: **216.9199 additive mean HTM and seven taught bodies longer
than four moves**. Both the method and its independently loaded template
repertoire solve all 32 sampled states; physical mean HTM is 209.7188. The
best new orientation continuation averages 225.1008 additive HTM, so it does
not improve the whole method. This implementation establishes the stage
machinery and algorithm-informed search; it has not yet reduced the ordinary-cube
solution length.

Its broader benchmark time increases from 156.53 to 179.37 seconds, about
14.6%. That timer includes chain selection, method saving, template
compilation, portable method/repertoire validation and 64 sampled solves plus
physical replay. Isotropy analysis and initial dictionary preparation are
outside it. The enabled search evaluates two additional complete phase
designs, increasing candidates from eight to twelve, with additional
Schreier refinement and policy compilation. The control measurement was
reused from an earlier run, so this is an indicative whole-benchmark overhead,
rather than an isolated or repeated timing of phase discovery. Repeated
runtime comparisons for FourPair, BeltRoad and BlockClockPair are not yet
recorded.

The target discovery pass introduces no new bodies into its supplied palette.
Whole-method refinement and template compression can still alter the final
learned repertoire. There is **no hard seven-long-body constraint** in the
chain selector yet. Recognition cost is bounded by exact pattern counts,
rather than a learned human case-recognition model. Placement-set goals,
general linear phase attributes, backward palette-preservation synthesis and
knowledge transfer between bandage refinements remain further increments.

## Validation and reproduction

Focused tests cover exact explicit and symbolic orientation stabilizers,
ordinary edge/corner phases, rigid bandaged blocks with orientation orders two
and four, full-domain discovery, incomplete palette coverage, physical
witness validation, portable loading, native case replay, template factoring,
phase markers, disabled search limits and recipe replacement during
refinement. Alcatraz methods and repertoires are replayed over all 324 states
in the integration suites. An additional 62 regression tests pass across
command-line preparation, symbolic template compilation and computation
budgets/routing.

Run from the repository root with the installed v2 Python package and GAP:

```sh
PYTHONPATH=v2/python/python python3 v2/research/evaluate_algorithm_informed_alcatraz.py
PYTHONPATH=v2/python/python python3 v2/research/evaluate_algorithm_informed_stages.py
PYTHONPATH=v2/python/python python3 v2/research/compare_orientation_target_examples.py
PYTHONPATH=v2/python/python python3 -m unittest discover -s v2/python/tests -p 'test_algorithm_target_search.py'
```

The ordinary-cube script caches its prepared dictionary in `/tmp` and records
its SHA-256. `--reuse-control PATH` reuses a measured control only after checking
the dictionary hash, search settings and exact scramble list, allowing a
target-only change to be measured without rebuilding the unchanged control.
