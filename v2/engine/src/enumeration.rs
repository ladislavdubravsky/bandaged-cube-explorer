//! Exact covers by cuboid footprints, before and after legal-motion equivalence.
//!
//! The least uncovered cell determines the next block, so every spatial
//! partition is emitted once. The default domain has 26 physical shell cells:
//! a cuboid may surround the virtual core without bonding to it.
use crate::{
    AxisMajor, BondLayout, BondShape, DefaultLayout, Partition,
    explore::{Metric, explore_with_options},
    geometry::BONDS,
    implicit::{CoreBonds, implicit_closure},
    symmetry::{Rotation, canonical_key},
};
use std::collections::{HashMap, HashSet};

const ALL_CELLS: u32 = (1 << 27) - 1;
const CORE: u32 = 1 << 13;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum EnumerationModel {
    /// Connected rectangular footprints with the core omitted (26 cells).
    #[default]
    ShellCuboids,
    /// Ordinary cuboids on all 27 cells; invisible core bonds are admitted.
    FullCuboids,
    /// Comparison model: ordinary cuboids with the core forced singleton.
    StrictCoreSingletonCuboids,
}

impl EnumerationModel {
    pub const fn name(self) -> &'static str {
        match self {
            Self::ShellCuboids => "shell-cuboids",
            Self::FullCuboids => "full-cuboids",
            Self::StrictCoreSingletonCuboids => "strict-core-singleton-cuboids",
        }
    }

    pub const fn core_bonds(self) -> CoreBonds {
        match self {
            Self::FullCuboids => CoreBonds::Include,
            _ => CoreBonds::Exclude,
        }
    }

    fn domain(self) -> u32 {
        match self {
            Self::ShellCuboids => ALL_CELLS & !CORE,
            _ => ALL_CELLS,
        }
    }
}

#[derive(Debug, Clone)]
pub struct CuboidFamily {
    pub model: EnumerationModel,
    placements: Vec<u32>,
    choices: [Vec<usize>; 27],
    bonds: Vec<u64>,
}

fn connected(mask: u32) -> bool {
    let mut reached = 1 << mask.trailing_zeros();
    loop {
        let before = reached;
        for [a, b] in BONDS {
            let pair = (1 << a) | (1 << b);
            if mask & pair == pair && reached & pair != 0 {
                reached |= pair;
            }
        }
        if before == reached {
            return reached == mask;
        }
    }
}

fn count_covers(remaining: u32, choices: &[Vec<u32>; 27], memo: &mut HashMap<u32, u64>) -> u64 {
    if remaining == 0 {
        return 1;
    }
    if let Some(&count) = memo.get(&remaining) {
        return count;
    }
    let count = choices[remaining.trailing_zeros() as usize]
        .iter()
        .filter(|&&mask| remaining & mask == mask)
        .map(|&mask| count_covers(remaining ^ mask, choices, memo))
        .sum();
    memo.insert(remaining, count);
    count
}

fn choices_for(masks: &[u32]) -> [Vec<u32>; 27] {
    std::array::from_fn(|cell| {
        masks
            .iter()
            .copied()
            .filter(|mask| mask & (1 << cell) != 0)
            .collect()
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PartitionCount {
    pub partitions: u64,
    pub rotation_classes: u64,
    pub fixed_by_rotation: [u64; 24],
    pub placements: usize,
    /// Occupancy masks memoized for the identity count; excludes the empty mask.
    pub memo_states: usize,
}

impl CuboidFamily {
    pub fn new(model: EnumerationModel) -> Self {
        let mut placements = Vec::new();
        for z0 in 0..3 {
            for z1 in z0 + 1..=3 {
                for y0 in 0..3 {
                    for y1 in y0 + 1..=3 {
                        for x0 in 0..3 {
                            for x1 in x0 + 1..=3 {
                                let mut mask = 0u32;
                                for z in z0..z1 {
                                    for y in y0..y1 {
                                        for x in x0..x1 {
                                            mask |= 1 << (9 * z + 3 * y + x);
                                        }
                                    }
                                }
                                match model {
                                    EnumerationModel::ShellCuboids => mask &= !CORE,
                                    EnumerationModel::StrictCoreSingletonCuboids
                                        if mask & CORE != 0 && mask != CORE =>
                                    {
                                        continue;
                                    }
                                    _ => {}
                                }
                                if mask != 0 && connected(mask) {
                                    placements.push(mask);
                                }
                            }
                        }
                    }
                }
            }
        }
        // Numeric mask order is deterministic and independent of block names.
        placements.sort_unstable();
        placements.dedup();
        let choices = std::array::from_fn(|cell| {
            (0..placements.len())
                .filter(|&i| placements[i] & (1 << cell) != 0)
                .collect()
        });
        let bonds = placements
            .iter()
            .map(|&mask| {
                BONDS.iter().enumerate().fold(0, |bits, (i, &[a, b])| {
                    if mask & (1 << a) != 0 && mask & (1 << b) != 0 {
                        bits | (1 << DefaultLayout::POSITIONS[i])
                    } else {
                        bits
                    }
                })
            })
            .collect();
        Self {
            model,
            placements,
            choices,
            bonds,
        }
    }

    pub fn placements(&self) -> &[u32] {
        &self.placements
    }

    /// Burnside count, using disjoint placement orbits as exact-cover tiles.
    pub fn count(&self) -> PartitionCount {
        let mut identity_states = 0;
        let fixed_by_rotation = std::array::from_fn(|r| {
            let rotation = Rotation::ALL[r];
            let mut seen = HashSet::new();
            let mut orbit_tiles = Vec::new();
            for &start in &self.placements {
                if seen.contains(&start) {
                    continue;
                }
                let mut mask = start;
                let mut occupied = 0;
                let mut disjoint = true;
                loop {
                    seen.insert(mask);
                    disjoint &= occupied & mask == 0;
                    occupied |= mask;
                    mask = rotate_mask(mask, rotation);
                    if mask == start {
                        break;
                    }
                }
                if disjoint {
                    orbit_tiles.push(occupied);
                }
            }
            // Distinct orbits with the same union are distinct tilings and must
            // retain multiplicity in the recurrence.
            let choices = choices_for(&orbit_tiles);
            let mut memo = HashMap::new();
            let count = count_covers(self.model.domain(), &choices, &mut memo);
            if rotation == Rotation::IDENTITY {
                identity_states = memo.len();
            }
            count
        });
        let sum: u64 = fixed_by_rotation.iter().sum();
        assert_eq!(sum % 24, 0, "Burnside sum must be divisible by 24");
        PartitionCount {
            partitions: fixed_by_rotation[Rotation::IDENTITY.index()],
            rotation_classes: sum / 24,
            fixed_by_rotation,
            placements: self.placements.len(),
            memo_states: identity_states,
        }
    }

    pub fn partitions(&self) -> CuboidPartitions<'_> {
        CuboidPartitions {
            family: self,
            stack: vec![Frame {
                remaining: self.model.domain(),
                bits: 0,
                choice: 0,
            }],
        }
    }

    /// Index the stream by exact completion counts, allowing reproducible
    /// uniform sampling without walking earlier partitions.
    pub fn index(&self) -> PartitionIndex<'_> {
        let choices = choices_for(&self.placements);
        let mut memo = HashMap::new();
        let total = count_covers(self.model.domain(), &choices, &mut memo);
        memo.insert(0, 1);
        PartitionIndex {
            family: self,
            memo,
            total,
        }
    }

    pub fn contains(&self, partition: &Partition) -> bool {
        if self.model != EnumerationModel::FullCuboids
            && partition
                .footprints()
                .iter()
                .any(|&mask| mask & CORE != 0 && mask != CORE)
        {
            return false;
        }
        partition.footprints().into_iter().all(|mask| {
            (self.model == EnumerationModel::ShellCuboids && mask == CORE)
                || self.placements.binary_search(&mask).is_ok()
        })
    }
}

pub struct PartitionIndex<'a> {
    family: &'a CuboidFamily,
    memo: HashMap<u32, u64>,
    pub total: u64,
}

impl PartitionIndex<'_> {
    /// Zero-based deterministic rank in `CuboidFamily::partitions()` order.
    pub fn partition(&self, mut rank: u64) -> Option<BondShape> {
        if rank >= self.total {
            return None;
        }
        let mut remaining = self.family.model.domain();
        let mut bits = 0;
        while remaining != 0 {
            for &placement in &self.family.choices[remaining.trailing_zeros() as usize] {
                let mask = self.family.placements[placement];
                if remaining & mask != mask {
                    continue;
                }
                let count = self.memo[&(remaining ^ mask)];
                if rank < count {
                    remaining ^= mask;
                    bits |= self.family.bonds[placement];
                    break;
                }
                rank -= count;
            }
        }
        Some(BondShape::from_valid_bits(bits))
    }

    /// Deterministic pseudorandom ranks with replacement, using rejection to
    /// avoid modulo bias. Each rank identifies one distinct spatial partition.
    pub fn samples(&self, seed: u64) -> PartitionSamples<'_, '_> {
        PartitionSamples {
            index: self,
            state: seed,
        }
    }
}

pub struct PartitionSamples<'a, 'b> {
    index: &'a PartitionIndex<'b>,
    state: u64,
}

impl Iterator for PartitionSamples<'_, '_> {
    type Item = BondShape;
    fn next(&mut self) -> Option<Self::Item> {
        let threshold = self.index.total.wrapping_neg() % self.index.total;
        loop {
            self.state = self.state.wrapping_add(0x9e3779b97f4a7c15);
            let mut value = self.state;
            value = (value ^ (value >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
            value = (value ^ (value >> 27)).wrapping_mul(0x94d049bb133111eb);
            value ^= value >> 31;
            if value >= threshold {
                return self.index.partition(value % self.index.total);
            }
        }
    }
}

fn rotate_mask(mask: u32, rotation: Rotation) -> u32 {
    let mut result = 0;
    for cell in 0..27 {
        if mask & (1 << cell) != 0 {
            result |= 1 << rotation.map_cell(cell);
        }
    }
    result
}

#[derive(Debug)]
struct Frame {
    remaining: u32,
    bits: u64,
    choice: usize,
}

pub struct CuboidPartitions<'a> {
    family: &'a CuboidFamily,
    stack: Vec<Frame>,
}

impl Iterator for CuboidPartitions<'_> {
    type Item = BondShape;
    fn next(&mut self) -> Option<Self::Item> {
        while let Some(frame) = self.stack.last_mut() {
            if frame.remaining == 0 {
                let bits = self.stack.pop().unwrap().bits;
                // Disjoint connected footprints give a saturated partition.
                return Some(BondShape::from_valid_bits(bits));
            }
            let choices = &self.family.choices[frame.remaining.trailing_zeros() as usize];
            if frame.choice == choices.len() {
                self.stack.pop();
                continue;
            }
            let placement = choices[frame.choice];
            frame.choice += 1;
            let mask = self.family.placements[placement];
            if frame.remaining & mask == mask {
                let next = Frame {
                    remaining: frame.remaining ^ mask,
                    bits: frame.bits | self.family.bonds[placement],
                    choice: 0,
                };
                self.stack.push(next);
            }
        }
        None
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct ScanOptions {
    pub implicit_bonds: bool,
    /// Explicit prefix limit; None scans the entire family.
    pub max_seeds: Option<usize>,
    /// Explicit per-component limit; encountering an incomplete component stops
    /// the scan without crediting that component as a class.
    pub max_component_vertices: Option<usize>,
}

#[derive(Debug, Clone, Default)]
pub struct ScanProgress {
    pub seeds_scanned: usize,
    pub raw_components_explored: usize,
    pub expanded_shape_vertices: usize,
    pub raw_rotation_keys_seen: usize,
    pub closed_rotation_keys_seen: usize,
    pub classes: usize,
    pub largest_component: usize,
}

#[derive(Debug, Clone)]
pub struct PuzzleClass {
    /// Minimum AxisMajor key over the motion component and all rotations.
    pub representative: BondShape<AxisMajor>,
    pub seed: BondShape,
    /// Fixed-frame raw component size, before closure or rotations.
    pub raw_component_vertices: usize,
}

#[derive(Debug, Clone)]
pub struct EnumerationScan {
    pub model: EnumerationModel,
    pub options: ScanOptions,
    pub progress: ScanProgress,
    pub representatives: Vec<PuzzleClass>,
    pub complete: bool,
    pub stop_reason: Option<&'static str>,
}

/// Classify an exact-cover stream by legal face turns and proper rotations.
/// Implicit closure additionally identifies specifications with identical legal
/// words from a common reference placement. Partial components never enter the
/// visited sets. The optional progress callback runs after every seed.
pub fn enumerate(
    family: &CuboidFamily,
    options: ScanOptions,
    report: impl FnMut(&ScanProgress),
) -> EnumerationScan {
    classify_seeds(family, options, family.partitions(), report)
}

/// Classify a uniformly sampled spatial seed stream. Counts apply only to the
/// sample; coverage is always incomplete even when every sampled component is
/// explored completely. Sampling is with replacement and a fixed random seed.
pub fn sample(
    family: &CuboidFamily,
    options: ScanOptions,
    sample_count: usize,
    random_seed: u64,
    report: impl FnMut(&ScanProgress),
) -> EnumerationScan {
    assert!(sample_count > 0, "sample count must be positive");
    let index = family.index();
    let mut result = classify_seeds(
        family,
        options,
        index.samples(random_seed).take(sample_count),
        report,
    );
    result.complete = false;
    result.stop_reason = result.stop_reason.or(Some("sample"));
    result
}

fn classify_seeds(
    family: &CuboidFamily,
    options: ScanOptions,
    seeds: impl Iterator<Item = BondShape>,
    mut report: impl FnMut(&ScanProgress),
) -> EnumerationScan {
    assert!(options.max_seeds != Some(0), "seed limit must be positive");
    assert!(
        options.max_component_vertices != Some(0),
        "component limit must be positive"
    );
    let mut result = EnumerationScan {
        model: family.model,
        options,
        progress: ScanProgress::default(),
        representatives: Vec::new(),
        complete: true,
        stop_reason: None,
    };
    let mut raw_seen = HashSet::new();
    let mut closed_seen = HashSet::new();
    for seed in seeds {
        if options.max_seeds == Some(result.progress.seeds_scanned) {
            result.complete = false;
            result.stop_reason = Some("seed-limit");
            break;
        }
        result.progress.seeds_scanned += 1;
        if !raw_seen.contains(&canonical_key(seed)) {
            let graph = explore_with_options(seed, Metric::Qtm, options.max_component_vertices);
            if !graph.complete {
                result.complete = false;
                result.stop_reason = Some("component-limit");
                report(&result.progress);
                break;
            }
            result.progress.raw_components_explored += 1;
            result.progress.expanded_shape_vertices += graph.vertices.len();
            result.progress.largest_component =
                result.progress.largest_component.max(graph.vertices.len());
            let keys: Vec<u64> = if options.implicit_bonds {
                implicit_closure(&graph, family.model.core_bonds())
                    .expect("enumeration supplies a complete graph in the admitted core model")
                    .shapes
                    .iter()
                    .copied()
                    .map(canonical_key)
                    .collect()
            } else {
                graph.vertices.iter().copied().map(canonical_key).collect()
            };
            // Closed projections have the same legal words and their image is
            // a complete connected component; any overlap identifies the class.
            if !keys.iter().any(|key| closed_seen.contains(key)) {
                let representative = BondShape::from_bits(*keys.iter().min().unwrap())
                    .expect("canonical keys are valid AxisMajor shapes");
                result.representatives.push(PuzzleClass {
                    representative,
                    seed,
                    raw_component_vertices: graph.vertices.len(),
                });
            }
            closed_seen.extend(keys);
            raw_seen.extend(graph.vertices.into_iter().map(canonical_key));
            result.progress.raw_rotation_keys_seen = raw_seen.len();
            result.progress.closed_rotation_keys_seen = closed_seen.len();
            result.progress.classes = result.representatives.len();
        }
        report(&result.progress);
    }
    result
        .representatives
        .sort_unstable_by_key(|class| class.representative.bits());
    result
}
