# Bond layout measurements on the development machine

Measured on 5 October 2026. Carefully assigning bond bits helps the current mask-and-shift engine on this machine. The old enumerator's layout is already a strong design: it substantially reduces dependent turn latency and improves complete shape exploration. Mixed legality checking sees essentially no gain.

The portable engine therefore defaults to the old sparse shell layout extended with six core bonds. A separate BMI2 lookup experiment is promising for isolated turns, but is not selected as the default from these measurements alone.

## Hardware and method

The environment reports an Intel Core i7-7500U, two cores/four threads, with AVX2 and BMI2. The compiler is rustc 1.98.1 with LLVM 22.1.8 on x86-64 Linux. Runs were pinned to logical CPU 1. Frequency scaling and background system activity were not disabled.

The harness calibrates repetition counts, warms the workloads, interleaves the cases across rounds, and reports sample medians. The native runs used nine samples per case with a target of 100 ms per sample. A portable-target run used nine samples at 70 ms. Results are timings of batches divided by the number of operations, not individually timestamped nanosecond operations.

Inputs are all 3,508 reachable shapes from Alcatraz, Bicube Fuse, and Shark Fin Soup. Each mixed-legality pass tests all six faces, yielding 21,048 queries. The turn corpus contains the 5,184 legal clockwise actions. Successor generation tests all faces and computes allowed successors; the BFS workload constructs all three complete graphs including labeled arcs and self-loops.

`Tuned` currently has exactly the same positions as `LegacySparse`: the heuristic did not improve its seed. Those rows serve as a duplicate control. They should not be interpreted as a third independent design.

## Native compilation results

The table uses the medians from the repeated native run. Speedup is the axis-major time divided by the sparse time. The successor rows divide by all face probes, including blocked ones.

| Workload | Axis-major layout | Sparse layout | Speedup |
| --- | ---: | ---: | ---: |
| Mixed legality query | 0.771 ns | 0.784 ns | Approximately equal |
| Mixed face turn on a known legal input | 8.193 ns | 7.174 ns | 1.14× |
| Complete successor generation per face probe | 1.017 ns | 0.421 ns | 2.41× |
| Dependent chain of U turns | 7.372 ns | 2.468 ns | 2.99× |
| Complete BFS of all three fixtures | 0.682 ms | 0.529 ms | 1.29× |

The earlier native run gave the same 1.29× BFS speedup and 2.99× U-chain speedup. Its mixed-turn ratio was 1.17× and successor ratio was 2.72×, so those throughput figures should be read as approximate. These are nine-sample medians, not confidence intervals or universal performance guarantees.

The generic target also favored the sparse layout: complete BFS took 0.666 ms versus 0.522 ms, and the dependent U chain took 7.009 ns versus 2.474 ns. Optimizing for this CPU did not remove the layout's advantage.

Raw samples:

- [Generic target](2026-10-05-generic.csv)
- [Native target](2026-10-05-native.csv)
- [Repeated native run](2026-10-05-native-repeat.csv)

## What the compiler actually emitted

For a fixed-U inspection function, the native compiler emitted **23 instructions** for the axis-major layout and **12** for the sparse layout, counting the return. The straightforward layout was vectorized with AVX2 but needed vector shifts, masks, and reduction back to a scalar key. The sparse function stayed scalar and combined only two nonzero displacement groups.

The compiler merged the identical `LegacySparse` and `Tuned` fixed-U functions, retaining the symbol `tuned_u`. [Recorded native assembly](2026-10-05-native-kernels.asm).

The fixed-U legality probes were three versus four instructions respectively: a convenient mask can avoid an extra constant load. Thus bit assignment can influence checking too, but the effect is small and can favor a different layout from the turn kernel. Mixed checks load a face-specific mask and were effectively equal in our timing corpus.

These are static counts for straight-line inspection probes. They do not count retired instructions inside the inlined successor or BFS kernels, and vector instructions can have different micro-operation costs. Hardware performance counters were unavailable under the environment's `perf_event_paranoid=4` policy; no system configuration was changed.

## What to optimize in the bit assignment

The code generator groups all bonds sharing one displacement into a common mask and shift. The current objective sums the number of distinct nonzero displacements over all 18 moves. It scores the axis-major layout at **184** and the old sparse layout at **66**. These are group counts, not machine instruction counts. In U/R/F/D/L/B order, clockwise sparse turns have 2/4/4/2/4/6 groups, compared with 12/12/11/12/12/11 for axis-major.

A deterministic simulated-annealing search with 400,000 proposals did not improve the old layout's score. This is evidence that the old assignment is useful, not proof that it is optimal.

For a workload-specific objective, account for both queries and legal actions:

```text
expected cost = expected legality cost
              + probability of an allowed turn * expected turn cost when allowed
```

Face and move-amount frequencies should come from the intended exploration or solver trace. The first search uses uniform weights across all 18 moves. Measured compiler and processor costs are a stronger objective than source-level operation counts, but are slower and noisier to evaluate during a large search. Use a cheap structural score to generate candidates, then benchmark the best candidates.

Dependencies, constant loads, branch prediction, vectorization, and register pressure all matter. The mixed-turn benchmark includes runtime face dispatch; the U chain folds the face at compile time; complete successor generation lets the compiler specialize all six faces. Their different speedups demonstrate why one small microbenchmark is insufficient.

## BMI2 lookup experiment

On this CPU, `PEXT` can extract a face's twelve internal bonds into a compact table index. Six tables of 4,096 `u64` entries contain the permuted moving bonds; the kernel combines one table entry with the unchanged complement. Table entries occupy **192 KiB**, plus small indexing metadata.

The repeated native run measured about **1.07 ns per isolated mixed face turn** for both axis-major and sparse encodings, compared with 8.19 and 7.17 ns for the mask-and-shift kernels. Table construction and CPU detection happen outside the timing loop. The experiment checks every legal corpus action against the corresponding permutation kernel before timing.

This strategy greatly reduces sensitivity to bit placement in this narrow benchmark. It has not been measured in complete BFS, colored search, or larger working sets. These fixtures exercise a limited set of table entries; cache behavior can change on other puzzles. BMI2 availability alone also does not guarantee good performance across processors: primary instruction measurements report substantially different `PEXT` throughput on Kaby Lake and older AMD Zen processors. [PEXT measurements](https://uops.info/html-instr/PEXT_R64_R64_R64.html).

A future kernel comparison should include BMI2 in complete exploration with larger components and account for table memory before selecting an architecture-specific implementation. The standard engine remains safe, portable mask-and-shift Rust.

## Reproduce or extend the measurements

Run from `v2/`:

```sh
taskset -c 1 cargo bench --bench layouts -- --samples 9 --sample-ms 70 --csv benchmark-results/local-generic.csv
RUSTFLAGS="-C target-cpu=native" taskset -c 1 cargo bench --bench layouts -- --samples 9 --sample-ms 100 --csv benchmark-results/local-native.csv
cargo run --release --bin layout_search -- 400000 > /tmp/candidate-layout.txt
```

These Linux commands pin one logical CPU; choose an available CPU on another machine. The layout search emits its diagnostics on stderr and its proposed positions on stdout. To test another assignment, put its 54 distinct positions in `engine/layouts/tuned.txt`, then run the tests and benchmark again. Changing the candidate does not automatically change the library default.

The current complete-search evidence concerns three small, warm components and one graph implementation. Larger enumeration and solving workloads can become dominated by hashing, memory access, or allocation. Revisit the choice using those workloads as they are implemented.
