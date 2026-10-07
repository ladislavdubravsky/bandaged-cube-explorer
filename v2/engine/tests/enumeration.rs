use bandaged_cube_engine::{
    BondShape, Partition,
    enumeration::{CuboidFamily, EnumerationModel, ScanOptions, enumerate, sample},
    geometry::Face,
};
use std::collections::HashSet;

#[test]
fn exact_counts_and_burnside_match_independent_layer_transfer() {
    for (model, partitions, rotation_classes, placements) in [
        (EnumerationModel::ShellCuboids, 312_238_908, 13_016_719, 206),
        (EnumerationModel::FullCuboids, 701_898_882, 29_255_694, 216),
        (
            EnumerationModel::StrictCoreSingletonCuboids,
            170_204_427,
            7_095_461,
            153,
        ),
    ] {
        let counts = CuboidFamily::new(model).count();
        assert_eq!(counts.partitions, partitions);
        assert_eq!(counts.rotation_classes, rotation_classes);
        assert_eq!(counts.placements, placements);
        assert_eq!(
            counts.fixed_by_rotation.iter().sum::<u64>(),
            24 * rotation_classes
        );
    }
}

#[test]
fn deterministic_generator_emits_unique_closed_admitted_partitions_and_legal_successors() {
    for model in [
        EnumerationModel::ShellCuboids,
        EnumerationModel::FullCuboids,
        EnumerationModel::StrictCoreSingletonCuboids,
    ] {
        let family = CuboidFamily::new(model);
        let mut seen = HashSet::new();
        for shape in family.partitions().take(5000) {
            assert!(seen.insert(shape));
            assert!(family.contains(&shape.to_partition()));
            assert_eq!(BondShape::from_bits(shape.bits()).unwrap(), shape);
            for face in Face::ALL {
                if let Ok(next) = shape.try_turn(bandaged_cube_engine::Move::clockwise(face)) {
                    assert!(family.contains(&next.to_partition()));
                }
            }
        }
        assert_eq!(seen.len(), 5000);
        assert_eq!(
            family.partitions().next(),
            Some(BondShape::from_partition(&Partition::singletons()))
        );
    }
}

#[test]
fn shell_family_admits_corner_block_without_invisible_bonds() {
    let mut labels = [0; 27];
    for cell in [0, 1, 3, 4, 9, 10, 12] {
        labels[cell] = 1;
    }
    let shell = Partition::from_legacy(labels).unwrap();
    assert!(CuboidFamily::new(EnumerationModel::ShellCuboids).contains(&shell));
    assert!(!CuboidFamily::new(EnumerationModel::StrictCoreSingletonCuboids).contains(&shell));
    labels[13] = 1;
    let full = Partition::from_legacy(labels).unwrap();
    assert!(CuboidFamily::new(EnumerationModel::FullCuboids).contains(&full));
    assert!(!CuboidFamily::new(EnumerationModel::ShellCuboids).contains(&full));
}

#[test]
fn unranking_matches_stream_and_samples_are_reproducible() {
    for model in [
        EnumerationModel::ShellCuboids,
        EnumerationModel::FullCuboids,
        EnumerationModel::StrictCoreSingletonCuboids,
    ] {
        let family = CuboidFamily::new(model);
        let index = family.index();
        for (rank, shape) in family.partitions().take(300).enumerate() {
            assert_eq!(index.partition(rank as u64), Some(shape));
        }
        assert_eq!(index.partition(index.total), None);
        assert!(family.contains(&index.partition(index.total - 1).unwrap().to_partition()));
        let samples: Vec<_> = index.samples(1).take(200).collect();
        assert_eq!(samples, index.samples(1).take(200).collect::<Vec<_>>());
        assert!(
            samples
                .iter()
                .all(|shape| family.contains(&shape.to_partition()))
        );
    }
    let family = CuboidFamily::new(EnumerationModel::ShellCuboids);
    let result = sample(&family, ScanOptions::default(), 20, 1, |_| {});
    assert!(!result.complete);
    assert_eq!(result.stop_reason, Some("sample"));
    assert_eq!(result.progress.seeds_scanned, 20);
}

#[test]
fn bounded_scan_never_claims_complete_or_credits_incomplete_components() {
    let family = CuboidFamily::new(EnumerationModel::ShellCuboids);
    let stopped = enumerate(
        &family,
        ScanOptions {
            max_seeds: Some(20),
            ..ScanOptions::default()
        },
        |_| {},
    );
    assert!(!stopped.complete);
    assert_eq!(stopped.stop_reason, Some("seed-limit"));
    assert_eq!(stopped.progress.seeds_scanned, 20);
    assert_eq!(stopped.progress.classes, stopped.representatives.len());
    let limited = enumerate(
        &family,
        ScanOptions {
            max_seeds: Some(20),
            max_component_vertices: Some(1),
            ..ScanOptions::default()
        },
        |_| {},
    );
    assert!(!limited.complete);
    assert_eq!(limited.stop_reason, Some("component-limit"));
    assert_eq!(limited.progress.classes, 1); // The unbandaged cube has one complete shape vertex.
}

#[test]
fn implicit_quotient_coarsens_same_prefix_without_changing_exact_seed_coverage() {
    let family = CuboidFamily::new(EnumerationModel::ShellCuboids);
    let raw = enumerate(
        &family,
        ScanOptions {
            max_seeds: Some(100),
            ..ScanOptions::default()
        },
        |_| {},
    );
    let closed = enumerate(
        &family,
        ScanOptions {
            max_seeds: Some(100),
            implicit_bonds: true,
            ..ScanOptions::default()
        },
        |_| {},
    );
    assert_eq!(raw.progress.seeds_scanned, closed.progress.seeds_scanned);
    assert_eq!(
        raw.progress.raw_rotation_keys_seen,
        closed.progress.raw_rotation_keys_seen
    );
    assert!(closed.progress.classes <= raw.progress.classes);
}
