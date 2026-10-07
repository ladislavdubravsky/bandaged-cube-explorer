use bandaged_cube_engine::{
    AxisMajor, BondLayout, BondShape, Face, LegacySparse, Move, Partition, Tuned,
    explore::{Metric, explore, explore_with_limit, explore_with_options},
    fixtures,
    geometry::{BONDS, destination},
    implicit::{CoreBonds, ImplicitClosureError, close_implicit, core_bond_mask, implicit_closure},
    parse_moves,
};
use std::collections::{HashSet, VecDeque};

fn windmill() -> Partition {
    let mut labels = [0; 27];
    labels[..9].copy_from_slice(&[1, 1, 4, 2, 5, 4, 2, 3, 3]);
    Partition::from_legacy(labels).unwrap()
}

/// Independent exhaustive identity-position search, avoiding shape quotient
/// transport and the bond permutation tables. This is small when only U and D
/// are mobile. Centers stay in place but still belong to their rotating layer.
fn identity_separation<L: BondLayout>(initial: Partition) -> (u64, usize) {
    let identity: [u8; 27] = std::array::from_fn(|i| i as u8);
    let mut visited = HashSet::from([identity]);
    let mut pending = VecDeque::from([identity]);
    let mut separated = 0;
    while let Some(positions) = pending.pop_front() {
        let mut labels = [0; 27];
        for (cubie, &position) in positions.iter().enumerate() {
            labels[position as usize] = initial.labels()[cubie];
        }
        let partition = Partition::from_legacy(labels).unwrap();
        for face in Face::ALL {
            if !partition.is_turnable(face) {
                continue;
            }
            for (bond, [a, b]) in BONDS.into_iter().enumerate() {
                if face.contains(positions[a as usize]) != face.contains(positions[b as usize]) {
                    separated |= 1 << L::POSITIONS[bond];
                }
            }
            let moved = positions.map(|position| destination(position, Move::clockwise(face)));
            if visited.insert(moved) {
                pending.push_back(moved);
            }
        }
    }
    (separated, visited.len())
}

fn check_projection<L: BondLayout>(partition: Partition, mode: CoreBonds) {
    let graph = explore(BondShape::<L>::from_partition(&partition));
    let closure = implicit_closure(&graph, mode).unwrap();
    for &(source, target, movement) in &graph.arcs {
        assert_eq!(
            closure.shapes[source].try_turn(movement).unwrap(),
            closure.shapes[target],
            "{}: closure must preserve the transport along {movement}",
            L::NAME,
        );
    }
    for (&original, &closed) in graph.vertices.iter().zip(&closure.shapes) {
        assert_eq!(closed.bits() & original.bits(), original.bits());
        assert!(BondShape::<L>::from_bits(closed.bits()).is_ok());
        for face in Face::ALL {
            assert_eq!(original.is_turnable(face), closed.is_turnable(face));
        }
    }
    let projected: HashSet<_> = closure.shapes.iter().copied().collect();
    let closed_graph = explore(closure.reference_shape());
    assert_eq!(
        closed_graph.vertices.into_iter().collect::<HashSet<_>>(),
        projected
    );
    assert_eq!(
        close_implicit(closure.reference_shape(), mode).unwrap(),
        closure.reference_shape(),
    );
}

#[test]
fn unbandaged_cube_has_no_implicit_bonds_despite_shape_self_loops() {
    for mode in [CoreBonds::Exclude, CoreBonds::Include] {
        let shape = BondShape::<AxisMajor>::from_partition(&Partition::singletons());
        let graph = explore(shape);
        assert_eq!(graph.vertices.len(), 1);
        assert_eq!(graph.arcs.len(), 6);
        let closure = implicit_closure(&graph, mode).unwrap();
        assert_eq!(closure.reference_shape(), shape);
        assert_eq!(closure.separable_bonds, vec![AxisMajor::USED_MASK]);
    }
}

#[test]
fn frozen_shell_merges_every_shell_cell_and_optionally_the_core() {
    let mut labels = [1; 27];
    labels[13] = 0;
    let partition = Partition::from_legacy(labels).unwrap();
    let shell = BondShape::<AxisMajor>::from_partition(&partition);
    let graph = explore(shell);
    assert!(graph.arcs.is_empty());
    let excluded = implicit_closure(&graph, CoreBonds::Exclude).unwrap();
    assert_eq!(excluded.reference_shape(), shell);
    assert_eq!(excluded.reference_shape().to_partition().block_count(), 2);
    let included = implicit_closure(&graph, CoreBonds::Include).unwrap();
    assert_eq!(
        included.reference_shape().to_partition(),
        Partition::fully_bandaged()
    );
    assert_eq!(included.separable_bonds, vec![0]);
}

#[test]
fn windmill_closure_matches_complete_identified_transport_search() {
    let partition = windmill();
    let (expected, identities) = identity_separation::<AxisMajor>(partition);
    assert_eq!(identities, 16);
    let graph = explore(BondShape::<AxisMajor>::from_partition(&partition));
    // Rotating the pinwheel permutes its identical dominoes, so all sixteen
    // identified transports project to a single shape with U and D loops.
    assert_eq!(graph.vertices.len(), 1);
    for mode in [CoreBonds::Exclude, CoreBonds::Include] {
        let closure = implicit_closure(&graph, mode).unwrap();
        assert_eq!(closure.separable_bonds[0], expected);
        let closed = closure.reference_shape().to_partition();
        assert!(
            closed.labels()[..9]
                .iter()
                .all(|&label| label == closed.labels()[0])
        );
        assert_eq!(
            closed.block_count(),
            if mode == CoreBonds::Include { 3 } else { 4 }
        );
        assert_eq!(
            closure.reference_shape().bits() & core_bond_mask::<AxisMajor>(),
            if mode == CoreBonds::Include {
                core_bond_mask::<AxisMajor>() & !expected
            } else {
                0
            },
        );
        check_projection::<AxisMajor>(partition, mode);
        check_projection::<LegacySparse>(partition, mode);
        check_projection::<Tuned>(partition, mode);
    }
}

#[test]
fn legacy_components_preserve_all_legal_words_and_closure_is_idempotent() {
    for fixture in fixtures::legacy() {
        check_projection::<AxisMajor>(fixture.partition, CoreBonds::Include);
    }
}

#[test]
fn qtm_and_htm_produce_the_same_implicit_partition() {
    let shape = BondShape::<AxisMajor>::from_partition(&windmill());
    let qtm = explore_with_options(shape, Metric::Qtm, None);
    let htm = explore_with_options(shape, Metric::Htm, None);
    assert_eq!(
        implicit_closure(&qtm, CoreBonds::Include)
            .unwrap()
            .reference_shape(),
        implicit_closure(&htm, CoreBonds::Include)
            .unwrap()
            .reference_shape(),
    );
}

#[test]
fn alternate_transport_into_a_visited_shape_can_separate_an_adjacency() {
    // A single DFS traversal of shape vertices, carrying a candidate-bond mask
    // along its spanning tree, incorrectly retained the (9, 18) bond here. A
    // shape reached earlier can hide a different arrangement of its cubies.
    let labels = [
        0, 0, 1, 0, 0, 1, 0, 0, 1, 2, 2, 2, 3, 4, 5, 6, 6, 5, 7, 7, 7, 3, 8, 5, 9, 10, 5,
    ]
    .map(|label| label + 1);
    let partition = Partition::from_legacy(labels).unwrap();
    let initial = BondShape::<AxisMajor>::from_partition(&partition);
    let graph = explore(initial);
    assert_eq!(graph.vertices.len(), 5);
    let closure = implicit_closure(&graph, CoreBonds::Exclude).unwrap();
    let edge = BONDS.iter().position(|&pair| pair == [9, 18]).unwrap();
    assert_eq!(closure.reference_shape().bits() & (1 << edge), 0);
    assert_ne!(closure.separable_bonds[0] & (1 << edge), 0);

    // Independent cell-position witness for separation, including the legal
    // final U turn that the incorrectly added bond would have prohibited.
    let moves = parse_moves("U U U B B U").unwrap();
    let mut pair = [9, 18];
    let mut reference = partition;
    for &movement in &moves[..5] {
        assert_eq!(
            movement.face.contains(pair[0]),
            movement.face.contains(pair[1])
        );
        reference = reference.try_turn(movement).unwrap();
        pair = pair.map(|cell| destination(cell, movement));
    }
    let final_move = moves[5];
    assert_ne!(
        final_move.face.contains(pair[0]),
        final_move.face.contains(pair[1])
    );
    assert!(reference.try_turn(final_move).is_ok());
    let mut falsely_fused = labels;
    falsely_fused[18] = falsely_fused[9];
    let mut falsely_fused = Partition::from_legacy(falsely_fused).unwrap();
    for &movement in &moves[..5] {
        falsely_fused = falsely_fused.try_turn(movement).unwrap();
    }
    assert!(falsely_fused.try_turn(final_move).is_err());
    check_projection::<AxisMajor>(partition, CoreBonds::Exclude);
    check_projection::<AxisMajor>(partition, CoreBonds::Include);
}

#[test]
fn incomplete_graph_or_missing_moves_cannot_establish_implicit_bonds() {
    let shape = BondShape::<AxisMajor>::from_partition(&windmill());
    let partial = explore_with_limit(
        BondShape::<AxisMajor>::from_partition(&fixtures::legacy()[0].partition),
        1,
    );
    assert_eq!(
        implicit_closure(&partial, CoreBonds::Include).unwrap_err(),
        ImplicitClosureError::IncompleteGraph,
    );
    let mut graph = explore(shape);
    graph.arcs.pop();
    assert_eq!(
        implicit_closure(&graph, CoreBonds::Include).unwrap_err(),
        ImplicitClosureError::InvalidGraph,
    );
    let fused = BondShape::<AxisMajor>::from_partition(&Partition::fully_bandaged());
    assert_eq!(
        close_implicit(fused, CoreBonds::Exclude).unwrap_err(),
        ImplicitClosureError::ExplicitCoreBonds,
    );
    assert_eq!(close_implicit(fused, CoreBonds::Include).unwrap(), fused);
}
