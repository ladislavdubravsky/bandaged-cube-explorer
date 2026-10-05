//! Dependency-free, calibrated, interleaved benchmark on real reachable states.
use bandaged_cube_engine::{
    AxisMajor, BondLayout, BondShape, Face, LegacySparse, Move, Tuned, explore::explore, fixtures,
};
use std::{
    fmt::Write,
    fs,
    hint::black_box,
    time::{Duration, Instant},
};

struct Case {
    name: String,
    workload: &'static str,
    units: usize,
    iterations: usize,
    samples: Vec<f64>,
    run: Box<dyn FnMut() -> u64>,
}

fn add<L: BondLayout>(cases: &mut Vec<Case>, corpus: &[BondShape<AxisMajor>]) {
    let shapes: Vec<_> = corpus.iter().map(|&s| s.reencode::<L>()).collect();
    let queries: Vec<_> = shapes
        .iter()
        .flat_map(|&s| Face::ALL.map(|f| (s.bits(), f)))
        .collect();
    let legal: Vec<_> = queries
        .iter()
        .copied()
        .filter(|&(bits, face)| bits & L::BLOCKERS[face.index()] == 0)
        .collect();
    let n = queries.len();
    cases.push(Case {
        name: L::NAME.into(),
        workload: "legality",
        units: n,
        iterations: 0,
        samples: Vec::new(),
        run: Box::new(move || {
            let mut out = 0;
            for &(bits, face) in black_box(&queries) {
                out += u64::from(bits & L::BLOCKERS[face.index()] == 0);
            }
            black_box(out)
        }),
    });
    let n = legal.len();
    let turns = legal.clone();
    cases.push(Case {
        name: L::NAME.into(),
        workload: "turn",
        units: n,
        iterations: 0,
        samples: Vec::new(),
        run: Box::new(move || {
            let mut out = 0u64;
            for &(bits, face) in black_box(&turns) {
                out = out.wrapping_add(L::permute(bits, Move::clockwise(face)));
            }
            black_box(out)
        }),
    });
    let n = shapes.len() * 6;
    cases.push(Case {
        name: L::NAME.into(),
        workload: "successors",
        units: n,
        iterations: 0,
        samples: Vec::new(),
        run: Box::new(move || {
            let mut out = 0u64;
            for &shape in black_box(&shapes) {
                for face in Face::ALL {
                    if let Ok(next) = shape.try_turn(Move::clockwise(face)) {
                        out = out.wrapping_add(next.bits());
                    }
                }
            }
            black_box(out)
        }),
    });
    let initial: Vec<_> = fixtures::legacy()
        .into_iter()
        .map(|f| BondShape::<L>::from_partition(&f.partition))
        .collect();
    let n = corpus.len();
    cases.push(Case {
        name: L::NAME.into(),
        workload: "bfs",
        units: n,
        iterations: 0,
        samples: Vec::new(),
        run: Box::new(move || {
            let mut out = 0;
            for &shape in black_box(&initial) {
                let graph = explore(shape);
                assert!(graph.complete);
                out += (graph.vertices.len() + graph.arcs.len()) as u64;
            }
            black_box(out)
        }),
    });
    let first = legal
        .iter()
        .find(|&&(bits, face)| face == Face::U && bits & L::MOVING[0] != 0)
        .unwrap()
        .0;
    cases.push(Case {
        name: L::NAME.into(),
        workload: "U-chain",
        units: 256,
        iterations: 0,
        samples: Vec::new(),
        run: Box::new(move || {
            let mut state = black_box(first);
            for _ in 0..256 {
                state = L::permute(black_box(state), Move::clockwise(Face::U));
            }
            black_box(state)
        }),
    });
    println!(
        "# {} displacement groups CW/half: {:?} / {:?}",
        L::NAME,
        Face::ALL.map(|f| L::SHIFT_GROUPS[f.index() * 3]),
        Face::ALL.map(|f| L::SHIFT_GROUPS[f.index() * 3 + 1])
    );
}

#[cfg(target_arch = "x86_64")]
mod bmi2 {
    use super::*;
    use std::arch::x86_64::_pext_u64;

    struct Lookup<L: BondLayout> {
        tables: Vec<Box<[u64; 4096]>>,
        _layout: std::marker::PhantomData<L>,
    }
    impl<L: BondLayout> Lookup<L> {
        fn new() -> Option<Self> {
            if !std::is_x86_feature_detected!("bmi2") {
                return None;
            }
            let tables = Face::ALL
                .into_iter()
                .map(|face| {
                    let mask = L::MOVING[face.index()];
                    assert_eq!(mask.count_ones(), 12);
                    let mut table = Box::new([0; 4096]);
                    for (input, output) in table.iter_mut().enumerate() {
                        let mut source = 0;
                        let mut remaining = mask;
                        for bit in 0..12 {
                            let slot = remaining.trailing_zeros();
                            remaining &= remaining - 1;
                            source |= ((input as u64 >> bit) & 1) << slot;
                        }
                        *output = L::permute(source, Move::clockwise(face));
                    }
                    table
                })
                .collect();
            Some(Self {
                tables,
                _layout: std::marker::PhantomData,
            })
        }
        #[inline]
        fn turn(&self, bits: u64, face: Face) -> u64 {
            // SAFETY: constructor checks BMI2 once; no unchecked memory access.
            unsafe { permute::<L>(bits, face, &self.tables) }
        }
    }
    #[target_feature(enable = "bmi2")]
    #[inline]
    unsafe fn permute<L: BondLayout>(bits: u64, face: Face, tables: &[Box<[u64; 4096]>]) -> u64 {
        let mask = L::MOVING[face.index()];
        let index = _pext_u64(bits, mask) as usize;
        (bits & !mask) | tables[face.index()][index]
    }

    pub fn add<L: BondLayout>(cases: &mut Vec<Case>, corpus: &[BondShape<AxisMajor>]) {
        let Some(lookup) = Lookup::<L>::new() else {
            return;
        };
        let queries: Vec<_> = corpus
            .iter()
            .map(|&s| s.reencode::<L>())
            .flat_map(|s| {
                Face::ALL
                    .into_iter()
                    .filter(move |&f| s.is_turnable(f))
                    .map(move |f| (s.bits(), f))
            })
            .collect();
        for &(bits, face) in &queries {
            assert_eq!(
                lookup.turn(bits, face),
                L::permute(bits, Move::clockwise(face))
            );
        }
        cases.push(Case {
            name: format!("{}+PEXT-table", L::NAME),
            workload: "turn",
            units: queries.len(),
            iterations: 0,
            samples: Vec::new(),
            run: Box::new(move || {
                let mut out = 0u64;
                for &(bits, face) in black_box(&queries) {
                    out = out.wrapping_add(lookup.turn(bits, face));
                }
                black_box(out)
            }),
        });
    }
}

#[inline(never)]
fn axis_u(bits: u64) -> u64 {
    AxisMajor::permute(bits, Move::clockwise(Face::U))
}
#[inline(never)]
fn legacy_u(bits: u64) -> u64 {
    LegacySparse::permute(bits, Move::clockwise(Face::U))
}
#[inline(never)]
fn tuned_u(bits: u64) -> u64 {
    Tuned::permute(bits, Move::clockwise(Face::U))
}
#[inline(never)]
fn axis_u_legal(bits: u64) -> bool {
    bits & AxisMajor::BLOCKERS[0] == 0
}
#[inline(never)]
fn legacy_u_legal(bits: u64) -> bool {
    bits & LegacySparse::BLOCKERS[0] == 0
}

fn run_batch(case: &mut Case, count: usize) -> Duration {
    let start = Instant::now();
    for _ in 0..count {
        black_box((case.run)());
    }
    start.elapsed()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let option = |key| {
        args.windows(2)
            .find(|pair| pair[0] == key)
            .map(|pair| pair[1].clone())
    };
    let rounds: usize = option("--samples").map(|s| s.parse().unwrap()).unwrap_or(9);
    let target_ms: u64 = option("--sample-ms")
        .map(|s| s.parse().unwrap())
        .unwrap_or(70);
    assert!(rounds > 0 && target_ms > 0);
    let corpus: Vec<_> = fixtures::legacy()
        .into_iter()
        .flat_map(|fixture| {
            let graph = explore(BondShape::<AxisMajor>::from_partition(&fixture.partition));
            assert!(graph.complete);
            assert_eq!(graph.vertices.len(), fixture.shapes);
            assert_eq!(graph.arcs.len(), fixture.clockwise_arcs);
            graph.vertices
        })
        .collect();
    for kernel in [axis_u as fn(u64) -> u64, legacy_u, tuned_u] {
        black_box(kernel(black_box(0)));
    }
    for test in [axis_u_legal as fn(u64) -> bool, legacy_u_legal] {
        black_box(test(black_box(0)));
    }
    let mut cases = Vec::new();
    if Tuned::POSITIONS == LegacySparse::POSITIONS {
        println!(
            "# Tuned matches LegacySparse: it is a duplicate control, not a third distinct layout"
        );
    }
    add::<AxisMajor>(&mut cases, &corpus);
    add::<LegacySparse>(&mut cases, &corpus);
    add::<Tuned>(&mut cases, &corpus);
    #[cfg(target_arch = "x86_64")]
    {
        println!("# BMI2 detected: {}", std::is_x86_feature_detected!("bmi2"));
        bmi2::add::<AxisMajor>(&mut cases, &corpus);
        bmi2::add::<LegacySparse>(&mut cases, &corpus);
        bmi2::add::<Tuned>(&mut cases, &corpus);
    }
    println!(
        "# {} real shapes; {rounds} samples, target {target_ms} ms; interleaved layouts",
        corpus.len()
    );
    for case in &mut cases {
        let mut n = 1;
        loop {
            let elapsed = run_batch(case, n);
            if elapsed >= Duration::from_millis(12) {
                case.iterations = ((target_ms as f64 * 1_000_000.0 / elapsed.as_nanos() as f64)
                    * n as f64)
                    .max(1.0) as usize;
                break;
            }
            n *= 2;
        }
    }
    let mut csv = String::from(
        "layout,workload,sample,iterations,units_per_iteration,elapsed_ns,ns_per_unit\n",
    );
    for round in 0..rounds {
        for offset in 0..cases.len() {
            let index = (offset + round * 5) % cases.len();
            let case = &mut cases[index];
            let elapsed = run_batch(case, case.iterations);
            let ns_per_unit = elapsed.as_nanos() as f64 / (case.iterations * case.units) as f64;
            case.samples.push(ns_per_unit);
            writeln!(
                csv,
                "{},{},{},{},{},{},{:.6}",
                case.name,
                case.workload,
                round,
                case.iterations,
                case.units,
                elapsed.as_nanos(),
                ns_per_unit
            )
            .unwrap();
        }
    }
    println!("layout,workload,median_ns_per_unit,min_ns_per_unit,max_ns_per_unit");
    for case in &mut cases {
        case.samples.sort_by(f64::total_cmp);
        println!(
            "{},{},{:.3},{:.3},{:.3}",
            case.name,
            case.workload,
            case.samples[rounds / 2],
            case.samples[0],
            case.samples[rounds - 1]
        );
    }
    if let Some(path) = option("--csv") {
        // Cargo runs a bench from its package directory. Relative result paths
        // are defined against the workspace so invocation from v2 is intuitive.
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap();
        let path = root.join(path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, csv).unwrap();
    }
}
