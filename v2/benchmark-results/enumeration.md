# Enumeration measurements

Measured 6 October 2026 on an Intel Core i7-7500U (2 cores / 4 threads), with
24 GiB RAM, release Rust builds and the portable default bond layout. These are
single-process baseline measurements; other local activity affects timings.

The default model is connected cuboid footprints on the 26-cell shell, with the
core omitted from every block. Quotients use the 24 proper rotations and legal
outer-face motion. The seed-scan measurements exclude reflections and dead-end
filtering; a separate complete postprocessing run is recorded below. See
[definitions and completeness arguments](../../docs/enumeration.md).

| Operation | Seeds | Raw components | Expanded vertices | Raw rotation keys | Closed rotation keys | Classes | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Generate prefix | 100,000 | — | — | — | — | — | 0.052126 |
| Scan prefix, no dynamic closure | 100,000 | 9,358 | 2,044,119 | 1,318,838 | 1,318,838 | 9,358 | 9.288128 |
| Scan prefix, dynamic closure | 100,000 | 9,358 | 2,044,119 | 1,318,838 | 1,252,150 | 1,540 | 16.476923 |
| Uniform spatial sample, dynamic closure | 10,000 | 7,535 | 6,536,780 | 4,074,519 | 3,964,494 | 2,056 | 59.036852 |
| **Complete scan, dynamic closure** | **312,238,908** | **3,498,007** | **16,184,768** | **13,016,719** | **4,998,868** | **7,073** | **822.819070** |

The four shorter rows have incomplete family coverage. The sample uses replacement,
SplitMix64 seed 1, and exact completion-count unranking; it samples spatial
partitions uniformly, not equivalence classes. The sample ran concurrently with
the complete scan, so its timing should not be compared as an isolated speed
ratio. Exact counts are independent of timing.

Prefix seed order is biased. The first 100,000 seeds explore 10.1% of all raw
rotation keys even though they comprise 0.032% of partitions. The full stream
contains 312,238,908 partitions and 13,016,719 raw rotation keys. A naive prefix
time extrapolation would predict 8.1 hours without closure or 14.3 hours with
closure; those predictions ignore global visited-component reuse. Pure
generation extrapolates to approximately 163 seconds. Complete scanning adds
canonicalization and lookups for every seed, while new components become rarer.

The complete run exhausted the stream and matches both independent spatial and
geometric-orbit totals. Its raw component counter is also the exhaustive count
without dynamic closure: **3,498,007** motion/rotation classes. It took 13 minutes
43 seconds, versus the naive 14.3-hour prefix extrapolation, and used 315,752 KiB
(308.35 MiB) peak RSS with no swaps. The largest raw fixed-frame component had
92,176 vertices. Early large components account for much of the total graph
work; the tail spends most of its time canonicalizing already visited seeds.

[The full representative CSV and summary](../enumeration-results/README.md)
retain all 7,073 closed classes. Independent validation checked every row's
labels, shell/core policy, connected box footprint, rotational minimum, and
unique sorted ID. Every closed representative admits recursive full-plane
cuts; exactly one has no legal face turn. Data validation does not independently
re-enumerate every motion component; exhaustive generation plus the verified
closure/component algorithm supplies that completeness argument.

Mirror matching and complete-component mobility analysis of all 7,073 closed
classes took **33.686617 s**, expanding **7,858,798** closed fixed-frame vertices.
Every reflected component maps to an existing class, the partner map is
involutive, and partner component sizes and mobility counts agree. The quotient
has 2,647 self-mirror classes and 2,213 mirror pairs, hence **4,860** classes.
Removing the three permanently frozen or one-axis classes gives **4,857**.
This reuses the completed atlas and does not regenerate spatial partitions.
The [analysis manifest](../enumeration-results/2026-10-06-shell-mirror-analysis.json)
preserves timing, filter counts, and checksums for the source, partner map, and
filtered output.

Exact-cover counting including Burnside takes 0.004671 s (shell), 0.007335 s
(core-inclusive), and 0.002928 s (strict singleton core) in the recorded runs.
It memoizes 21,933 / 35,325 / 13,537 nonempty occupancy masks respectively;
counting does not materialize those hundreds of millions of partitions.

Reproduce from `v2/`:

```sh
cargo build --release --bin enumerate
target/release/enumerate generate --max-seeds 100000
target/release/enumerate scan --max-seeds 100000
target/release/enumerate scan --max-seeds 100000 --implicit-bonds
target/release/enumerate sample --samples 10000 --random-seed 1 --implicit-bonds
target/release/enumerate scan --implicit-bonds --output /tmp/classes.csv
cargo run --release --bin analyze_atlas -- enumeration-results/2026-10-06-shell-puzzles.csv --dead-ends one-axis --output /tmp/filtered-classes.csv --summary /tmp/mirror-analysis.json --pairs /tmp/mirror-pairs.csv
```

Summary rows are preserved in [enumeration.csv](2026-10-06-enumeration.csv).
CSV exports start with a versioned metadata comment and contain canonical
representatives with originating seed labels; they remain usable for replay and
further exploration independently of optimized bit-layout choices.
