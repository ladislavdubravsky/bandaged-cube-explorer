//! Search for a bit assignment that makes bond permutations cheaper to express.
//!
//! A layout assigns each of the 54 face-adjacent cell pairs in the 3x3x3 grid
//! (including core bonds) to a distinct bit position in a `u64`. Ten positions
//! remain unused. We search these assignments, rather than particular bandage
//! shapes: the resulting move kernels must work for every legal input shape.
//!
//! For each of the 18 outer-face moves (quarter, half, and inverse turns), let
//! `m(i)` be the destination bond of bond `i`, and let `p(i)` be its assigned bit
//! position. Bonds whose two cells lie in the moving layer are permuted; other
//! bonds stay in place. Bonds crossing the layer boundary must be absent for a
//! legal turn, which is checked separately by the engine.
//!
//! The objective to minimize is:
//!
//! ```text
//! score(p) = sum over moves m of |{ p(m(i)) - p(i) : m(i) != i }|
//! ```
//!
//! Here `|...|` counts distinct signed displacements, not the number of bonds.
//! Bonds sharing a displacement can share one mask-and-shift operation: all
//! bits moving by +4, for example, contribute `(bits & source_mask) << 4`.
//! The generated kernel ORs these groups together with the stationary bits.
//! The score counts only nonzero displacement groups and weights all 18 moves
//! equally, independent of puzzle shape or how often a move is actually legal.
//! It excludes legality checks and stationary-bit preservation, and is a proxy
//! for kernel complexity, not a CPU instruction count or a timing prediction.
//!
//! Simulated annealing tries swaps of two bit assignments, including swaps with
//! unused positions. Eight restarts alternate between the best layout found so
//! far (initially `LegacySparse`) and `AxisMajor`. A fixed random seed makes the
//! search reproducible; occasional uphill steps become less likely as it cools.
//! This heuristic does not establish that the best result is globally optimal.
//!
//! Run `layout_search [steps]` (default: 200,000 proposals, divided among the
//! restarts). Diagnostics go to stderr; stdout contains the best 54 bit positions
//! in `BONDS` order, suitable for `engine/layouts/tuned.txt`. The tool does not
//! modify that file. Test and benchmark a candidate before adopting it: compiler
//! choices, CPU costs, and the intended workload can change which layout wins.
use bandaged_cube_engine::{
    AxisMajor, BondLayout, LegacySparse, Move,
    geometry::{BONDS, bond_index, destination},
};

fn rng(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

fn main() {
    let steps = std::env::args()
        .nth(1)
        .map(|s| s.parse::<usize>().expect("iteration count"))
        .unwrap_or(200_000);
    let maps: [[usize; 54]; 18] = std::array::from_fn(|m| {
        let movement = Move::ALL[m];
        std::array::from_fn(|i| {
            let [a, b] = BONDS[i];
            if movement.face.contains(a) && movement.face.contains(b) {
                bond_index(destination(a, movement), destination(b, movement))
            } else {
                i
            }
        })
    });
    let score = |positions: &[u8; 64]| -> usize {
        maps.iter()
            .map(|map| {
                let mut seen = [false; 127];
                for i in 0..54 {
                    if i != map[i] {
                        let delta = positions[map[i]] as i16 - positions[i] as i16;
                        seen[(delta + 63) as usize] = true;
                    }
                }
                seen.into_iter().filter(|&b| b).count()
            })
            .sum()
    };
    fn extend(prefix: [u8; 54]) -> [u8; 64] {
        let mut result = [0; 64];
        result[..54].copy_from_slice(&prefix);
        let mut cursor = 54;
        for bit in 0..64 {
            if !prefix.contains(&bit) {
                result[cursor] = bit;
                cursor += 1;
            }
        }
        result
    }
    let mut best = extend(LegacySparse::POSITIONS);
    let mut best_score = score(&best);
    eprintln!(
        "uniform 18-move shared-shift score: axis={} legacy={best_score}",
        score(&extend(AxisMajor::POSITIONS))
    );
    let mut random = 0xa0761d6478bd642f;
    let restarts = 8;
    for restart in 0..restarts {
        let mut current = if restart % 2 == 0 {
            best
        } else {
            extend(AxisMajor::POSITIONS)
        };
        let mut current_score = score(&current);
        let per_restart = steps / restarts;
        for step in 0..per_restart {
            let a = (rng(&mut random) % 64) as usize;
            let b = (rng(&mut random) % 64) as usize;
            current.swap(a, b);
            let candidate = score(&current);
            let progress = step as f64 / per_restart.max(1) as f64;
            let temperature = 2.5 * (0.05f64 / 2.5).powf(progress);
            let uniform = (rng(&mut random) >> 11) as f64 / ((1u64 << 53) as f64);
            if candidate <= current_score
                || uniform < ((current_score as f64 - candidate as f64) / temperature).exp()
            {
                current_score = candidate;
                if candidate < best_score {
                    best = current;
                    best_score = candidate;
                }
            } else {
                current.swap(a, b);
            }
        }
        eprintln!("restart {}: best={best_score}", restart + 1);
    }
    eprintln!("best score={best_score}; heuristic only, not a global-optimality claim");
    println!(
        "{}",
        best[..54]
            .iter()
            .map(u8::to_string)
            .collect::<Vec<_>>()
            .join(" ")
    );
}
