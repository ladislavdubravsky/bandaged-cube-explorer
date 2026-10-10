use bandaged_cube_engine::{
    Amount, BandageSpec, BondShape, CubeState, Face, LoopGenerators, Move, Partition,
    StickerPermutation,
    colored_search::explore_colored,
    explore::{Metric, ShapeGraph, explore, explore_with_limit, explore_with_options},
    fixtures, parse_moves,
};
use std::collections::{HashMap, HashSet};

fn one_face(face: Face) -> BandageSpec {
    BandageSpec::new(
        Partition::from_legacy(std::array::from_fn(|cell| {
            if face.contains(cell as u8) { 1 } else { 2 }
        }))
        .unwrap(),
    )
}

fn top_block(cells: &[usize]) -> BandageSpec {
    BandageSpec::new(
        Partition::from_legacy(std::array::from_fn(|cell| {
            if cell >= 9 {
                26
            } else if cells.contains(&cell) {
                20
            } else {
                cell as u8
            }
        }))
        .unwrap(),
    )
}

fn closure(generators: &[StickerPermutation]) -> HashSet<StickerPermutation> {
    let mut found = HashSet::from([StickerPermutation::IDENTITY]);
    let mut queue = vec![StickerPermutation::IDENTITY];
    let mut cursor = 0;
    while cursor < queue.len() {
        for &generator in generators {
            let next = queue[cursor].then(generator);
            if found.insert(next) {
                assert!(found.len() <= 1000, "test puzzle must have a small group");
                queue.push(next);
            }
        }
        cursor += 1;
    }
    found
}

#[test]
fn indexed_original_ids_keep_witnesses_when_public_records_are_reordered() {
    let graph = explore(BondShape::from_partition(&Partition::singletons()));
    let mut loops = LoopGenerators::from_graph(&graph, 0).unwrap();
    let expected: Vec<_> = loops
        .generators
        .iter()
        .map(|generator| (generator.id, loops.generator_moves(generator.id).unwrap()))
        .collect();
    loops.generators.reverse();
    for (id, word) in expected {
        assert_eq!(loops.generator_moves(id), Some(word));
    }
    assert_eq!(loops.generator_moves(usize::MAX), None);
}

#[test]
fn sticker_actions_retain_orientations_and_compose_in_execution_order() {
    assert_eq!(
        CubeState::SOLVED.sticker_permutation(),
        StickerPermutation::IDENTITY
    );
    let mut twists = [0; 8];
    twists[0] = 1;
    twists[1] = 2;
    let mut flips = [0; 12];
    flips[0] = 1;
    flips[1] = 1;
    let oriented = CubeState::try_new(
        *CubeState::SOLVED.corners(),
        twists,
        *CubeState::SOLVED.edges(),
        flips,
    )
    .unwrap();
    assert!(!oriented.sticker_permutation().is_identity());
    assert_eq!(oriented.piece_cells(), CubeState::SOLVED.piece_cells());
    let mut state = oriented;
    let mut action = oriented.sticker_permutation();
    for i in 0..300 {
        let movement = Move::ALL[(i * 7 + i / 11) % 18];
        let next = CubeState::SOLVED.turn(movement).sticker_permutation();
        state = state.turn(movement);
        action = action.then(next);
        assert_eq!(action, state.sticker_permutation());
        assert_eq!(action.then(action.inverse()), StickerPermutation::IDENTITY);
        assert_eq!(action.inverse().then(action), StickerPermutation::IDENTITY);
        let mut colors = [b'?'; 48];
        for (origin, &destination) in action.images().iter().enumerate() {
            colors[destination as usize] = b"URFDLB"[origin / 8];
        }
        let expected: Vec<_> = state
            .to_facelets()
            .bytes()
            .enumerate()
            .filter_map(|(i, color)| (i % 9 != 4).then_some(color))
            .collect();
        assert_eq!(colors.as_slice(), expected);
    }
    for movement in Move::ALL {
        assert_eq!(
            CubeState::SOLVED
                .turn(movement)
                .sticker_permutation()
                .inverse(),
            CubeState::SOLVED
                .turn(movement.inverse())
                .sticker_permutation(),
        );
    }
    let mut invalid = *StickerPermutation::IDENTITY.images();
    invalid[47] = 0;
    assert!(StickerPermutation::try_new(invalid).is_err());
    invalid[47] = 48;
    assert!(StickerPermutation::try_new(invalid).is_err());
}

#[test]
fn loop_group_and_shape_fibers_match_complete_small_colored_components() {
    let axis = BandageSpec::new(
        Partition::from_legacy(std::array::from_fn(|cell| (cell / 9) as u8)).unwrap(),
    );
    for (spec, shapes, order, retained) in [
        (BandageSpec::new(Partition::fully_bandaged()), 1, 1, 0),
        (one_face(Face::F), 1, 4, 1),
        (axis, 1, 16, 2),
        (top_block(&[0, 1]), 4, 1, 0),
        (top_block(&[1, 4, 7]), 2, 2, 1),
    ] {
        let solved = spec.solved_state();
        let colored = explore_colored(solved, Metric::Qtm, None).unwrap();
        let mut fibers = HashMap::<_, usize>::new();
        for state in &colored.states {
            *fibers.entry(state.shape()).or_default() += 1;
        }
        assert_eq!(fibers.len(), shapes);
        assert_eq!(colored.states.len(), shapes * order);
        assert!(fibers.values().all(|&size| size == order));
        for metric in [Metric::Qtm, Metric::Htm] {
            let graph = explore_with_options(solved.shape(), metric, None);
            for root in 0..graph.vertices.len() {
                let loops = LoopGenerators::from_graph(&graph, root).unwrap();
                assert_eq!(loops.generators.len(), retained);
                assert_eq!(loops.candidate_count, loops.arc_count + 1 - shapes);
                assert_eq!(loops.root_shape, graph.vertices[root]);
                let actions: Vec<_> = loops.generators.iter().map(|g| g.permutation).collect();
                assert_eq!(closure(&actions).len(), order);
                let mut root_state = solved;
                for movement in graph.shortest_path(0, root).unwrap() {
                    root_state.try_turn(movement).unwrap();
                }
                for generator in &loops.generators {
                    let witness = loops.generator_moves(generator.id).unwrap();
                    assert_eq!(witness.len(), generator.qtm_length);
                    let mut state = root_state;
                    for movement in witness {
                        state.try_turn(movement).unwrap();
                    }
                    assert_eq!(state.shape(), root_state.shape());
                    assert_eq!(
                        state.cube().sticker_permutation(),
                        root_state
                            .cube()
                            .sticker_permutation()
                            .then(generator.permutation),
                    );
                }
                for target in 0..graph.vertices.len() {
                    let path = loops.transport(target).unwrap();
                    assert_eq!(path.len(), graph.qtm_distances(root)[target].unwrap());
                    let mut state = root_state;
                    for movement in path {
                        state.try_turn(movement).unwrap();
                    }
                    assert_eq!(state.shape(), graph.vertices[target]);
                }
                assert_eq!(loops.transport(graph.vertices.len()), None);
                assert_eq!(loops.generator_moves(graph.arcs.len()), None);
            }
        }
    }
}

#[test]
fn fundamental_loops_preserve_self_loops_parallel_actions_and_stable_witnesses() {
    let graph = explore(BondShape::from_partition(&Partition::singletons()));
    let loops = LoopGenerators::from_graph(&graph, 0).unwrap();
    assert_eq!(loops.shape_count, 1);
    assert_eq!(loops.arc_count, 6);
    assert_eq!(loops.candidate_count, 6);
    assert_eq!(loops.nonidentity_count, 6);
    assert_eq!(loops.generators.len(), 6);
    for (id, generator) in loops.generators.iter().enumerate() {
        assert_eq!(generator.id, id);
        assert_eq!(generator.source, 0);
        assert_eq!(generator.target, 0);
        assert_eq!(
            loops.generator_moves(id),
            Some(vec![Move::clockwise(Face::ALL[id])])
        );
    }
    // U and D are different actions with the same endpoint, not duplicates.
    assert_ne!(
        loops.generators[0].permutation,
        loops.generators[3].permutation
    );
}

#[test]
fn named_fixture_loop_witnesses_are_complete_legal_and_orientation_faithful() {
    for (fixture, expected_candidates, expected_retained) in fixtures::legacy()
        .into_iter()
        .zip([(600, 31), (48, 3), (1031, 18)])
        .map(|(fixture, (candidates, retained))| (fixture, candidates, retained))
    {
        let solved = BandageSpec::new(fixture.partition).solved_state();
        let graph = explore(solved.shape());
        let loops = LoopGenerators::from_graph(&graph, 0).unwrap();
        assert_eq!(
            loops.candidate_count, expected_candidates,
            "{}",
            fixture.name
        );
        assert_eq!(
            loops.generators.len(),
            expected_retained,
            "{}",
            fixture.name
        );
        let mut keys = HashSet::new();
        for generator in &loops.generators {
            assert!(!generator.permutation.is_identity());
            assert!(keys.insert(generator.permutation.min(generator.permutation.inverse())));
            let witness = loops.generator_moves(generator.id).unwrap();
            assert_eq!(witness.len(), generator.qtm_length);
            let mut state = solved;
            for movement in witness {
                state.try_turn(movement).unwrap();
            }
            assert_eq!(state.shape(), solved.shape());
            assert_eq!(state.cube().sticker_permutation(), generator.permutation);
        }
        let htm = explore_with_options(solved.shape(), Metric::Htm, None);
        let htm_loops = LoopGenerators::from_graph(&htm, 0).unwrap();
        assert_eq!(htm_loops.candidate_count, expected_candidates);
        assert_eq!(
            htm_loops
                .generators
                .iter()
                .map(|g| g.permutation.min(g.permutation.inverse()))
                .collect::<HashSet<_>>(),
            loops
                .generators
                .iter()
                .map(|g| g.permutation.min(g.permutation.inverse()))
                .collect::<HashSet<_>>(),
        );
    }
}

#[test]
fn invalid_and_incomplete_public_shape_graphs_are_rejected() {
    let shape = top_block(&[1, 4, 7]).solved_state().shape();
    assert!(LoopGenerators::from_graph(&explore(shape), 2).is_err());
    assert!(LoopGenerators::from_graph(&explore_with_limit(shape, 1), 0).is_err());
    let empty = ShapeGraph {
        vertices: vec![],
        arcs: vec![],
        metric: Metric::Qtm,
        complete: true,
    };
    assert!(LoopGenerators::from_graph(&empty, 0).is_err());
    let mut graph = explore(shape);
    graph.arcs.pop();
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph.arcs.push(graph.arcs[0]);
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph.arcs[0].1 = 10;
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph.arcs[0].1 = 0;
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph.arcs[0].2.amount = Amount::Half;
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph.vertices.push(shape);
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(shape);
    graph
        .vertices
        .push(BondShape::from_partition(&Partition::fully_bandaged()));
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore(BondShape::from_partition(&Partition::fully_bandaged()));
    graph.arcs.push((0, 0, Move::clockwise(Face::U)));
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
    let mut graph = explore_with_options(shape, Metric::Htm, None);
    graph
        .arcs
        .retain(|&(_, _, movement)| movement.amount == Amount::Clockwise);
    assert!(LoopGenerators::from_graph(&graph, 0).is_err());
}

#[test]
fn noncommuting_move_actions_use_gap_source_to_destination_convention() {
    let movements = parse_moves("R U R' U'").unwrap();
    let mut cube = CubeState::SOLVED;
    let mut permutation = StickerPermutation::IDENTITY;
    for movement in movements {
        cube = cube.turn(movement);
        permutation = permutation.then(CubeState::SOLVED.turn(movement).sticker_permutation());
    }
    assert_eq!(cube.sticker_permutation(), permutation);
    assert!(!permutation.is_identity());
}
