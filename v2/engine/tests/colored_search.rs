use bandaged_cube_engine::{
    Amount, BandageSpec, BandagedState, CubeState, Face, Move, Partition,
    colored_search::{SearchAlgorithm, SearchOptions, SearchStatus, explore_colored, solve},
    explore::Metric,
    fixtures,
    geometry::CORNER_CELLS,
};
use std::collections::{HashMap, HashSet, VecDeque};

fn one_face(face: Face) -> BandageSpec {
    BandageSpec::new(
        Partition::from_legacy(std::array::from_fn(|cell| {
            if face.contains(cell as u8) { 1 } else { 2 }
        }))
        .unwrap(),
    )
}

fn one_axis() -> BandageSpec {
    BandageSpec::new(
        Partition::from_legacy(std::array::from_fn(|cell| (cell / 9 + 1) as u8)).unwrap(),
    )
}

fn options(metric: Metric, algorithm: SearchAlgorithm) -> SearchOptions {
    SearchOptions {
        metric,
        algorithm,
        max_states: None,
        max_depth: None,
    }
}

fn replay(mut state: BandagedState, movements: &[Move]) -> BandagedState {
    for &movement in movements {
        state.try_turn(movement).unwrap();
    }
    state
}

/// Independent ordinary-cube BFS for puzzles whose permitted faces are fixed.
/// It never calls the production search or its shape legality logic.
fn ordinary_oracle(
    initial: CubeState,
    faces: &[Face],
    metric: Metric,
) -> HashMap<CubeState, usize> {
    let mut distances = HashMap::from([(initial, 0)]);
    let mut queue = VecDeque::from([initial]);
    while let Some(source) = queue.pop_front() {
        for movement in Move::ALL {
            if !faces.contains(&movement.face)
                || (metric == Metric::Qtm && movement.amount == Amount::Half)
            {
                continue;
            }
            let target = source.turn(movement);
            if !distances.contains_key(&target) {
                distances.insert(target, distances[&source] + 1);
                queue.push_back(target);
            }
        }
    }
    distances
}

#[test]
fn all_pairs_match_independent_colored_oracle_and_replay() {
    for (spec, faces, expected_size) in [
        (one_face(Face::F), vec![Face::F], 4),
        (one_axis(), vec![Face::U, Face::D], 16),
    ] {
        for metric in [Metric::Qtm, Metric::Htm] {
            let graph = explore_colored(spec.solved_state(), metric, None).unwrap();
            assert!(graph.complete);
            assert_eq!(graph.states.len(), expected_size);
            assert_eq!(
                graph.arcs.len(),
                expected_size * faces.len() * if metric == Metric::Qtm { 2 } else { 3 }
            );
            for (start, &initial) in graph.states.iter().enumerate() {
                for face in Face::ALL {
                    assert_eq!(initial.is_turnable(face), faces.contains(&face));
                }
                let expected = ordinary_oracle(*initial.cube(), &faces, metric);
                assert_eq!(expected.len(), expected_size);
                let graph_distances = graph.distances(start);
                for (target_id, &target) in graph.states.iter().enumerate() {
                    let distance = expected[target.cube()];
                    assert_eq!(graph_distances[target_id], Some(distance));
                    let graph_path = graph.shortest_path(start, target_id).unwrap();
                    assert_eq!(graph_path.len(), distance);
                    assert_eq!(replay(initial, &graph_path), target);
                    for algorithm in [SearchAlgorithm::Bfs, SearchAlgorithm::Bidirectional] {
                        let result =
                            solve(initial, Some(target), options(metric, algorithm)).unwrap();
                        assert_eq!(result.status, SearchStatus::Solved);
                        assert_eq!(result.distance, Some(distance));
                        assert_eq!(result.metric, metric);
                        assert_eq!(result.algorithm, algorithm);
                        assert_eq!(result.stop_reason, None);
                        let path = result.solution.unwrap();
                        assert_eq!(path.len(), distance);
                        assert_eq!(replay(initial, &path), target);
                        if metric == Metric::Qtm {
                            assert!(path.iter().all(|m| m.amount != Amount::Half));
                        }
                    }
                }
            }
            assert_eq!(graph.shortest_path(graph.states.len(), 0), None);
            assert_eq!(graph.shortest_path(0, graph.states.len()), None);
            assert!(
                graph
                    .distances(graph.states.len())
                    .iter()
                    .all(Option::is_none)
            );
        }
    }
}

#[test]
fn shape_restoration_does_not_solve_colors_or_orientations() {
    let solved = one_face(Face::F).solved_state();
    let scrambled = replay(solved, &[Move::clockwise(Face::F)]);
    assert_eq!(scrambled.shape(), solved.shape());
    assert_ne!(scrambled.cube(), solved.cube());
    assert!(scrambled.cube().twists().iter().any(|&twist| twist != 0));
    assert!(scrambled.cube().flips().iter().any(|&flip| flip != 0));
    for algorithm in [SearchAlgorithm::Bfs, SearchAlgorithm::Bidirectional] {
        let result = solve(scrambled, None, options(Metric::Qtm, algorithm)).unwrap();
        assert_eq!(result.distance, Some(1));
        assert_eq!(replay(scrambled, &result.solution.unwrap()), solved);
    }
    let graph = explore_colored(solved, Metric::Qtm, None).unwrap();
    assert_eq!(
        graph
            .states
            .iter()
            .map(|s| s.shape())
            .collect::<HashSet<_>>()
            .len(),
        1
    );
    assert_eq!(
        graph
            .states
            .iter()
            .map(|s| *s.cube())
            .collect::<HashSet<_>>()
            .len(),
        4
    );

    // Equal cubie positions still do not imply equal colors: two compensating
    // corner twists are ordinary-cube valid and must remain in the search key.
    let spec = BandageSpec::new(Partition::singletons());
    let mut twists = [0; 8];
    twists[0] = 1;
    twists[1] = 2;
    let oriented = CubeState::try_new(
        *CubeState::SOLVED.corners(),
        twists,
        *CubeState::SOLVED.edges(),
        [0; 12],
    )
    .unwrap();
    let initial = spec.state_from_cube(oriented).unwrap();
    assert_eq!(initial.shape(), spec.solved_state().shape());
    assert_eq!(
        initial.cube().corners(),
        spec.solved_state().cube().corners()
    );
    assert_eq!(initial.cube().edges(), spec.solved_state().cube().edges());
    for algorithm in [SearchAlgorithm::Bfs, SearchAlgorithm::Bidirectional] {
        let mut limited = options(Metric::Qtm, algorithm);
        limited.max_depth = Some(0);
        assert_eq!(
            solve(initial, None, limited).unwrap().status,
            SearchStatus::LimitReached
        );
    }
}

#[test]
fn explicit_limits_never_claim_unreachable_or_exceed_storage() {
    let solved = one_face(Face::F).solved_state();
    let scrambled = replay(solved, &[Move::new(Face::F, Amount::Half)]);
    for algorithm in [SearchAlgorithm::Bfs, SearchAlgorithm::Bidirectional] {
        for metric in [Metric::Qtm, Metric::Htm] {
            let mut limited = options(metric, algorithm);
            limited.max_states = Some(1);
            let result = solve(scrambled, None, limited).unwrap();
            assert_eq!(result.status, SearchStatus::LimitReached);
            assert_eq!(result.stop_reason, Some("max_states"));
            assert_eq!(result.visited, 1);
            assert_eq!(result.solution, None);
            assert_eq!(result.distance, None);
            limited.max_states = Some(0);
            assert!(solve(scrambled, None, limited).is_err());
            limited.max_states = None;
            limited.max_depth = Some(0);
            let result = solve(scrambled, None, limited).unwrap();
            assert_eq!(result.status, SearchStatus::LimitReached);
            assert_eq!(result.stop_reason, Some("max_depth"));
            limited.max_depth = Some(1);
            let result = solve(scrambled, None, limited).unwrap();
            if metric == Metric::Qtm {
                assert_eq!(result.status, SearchStatus::LimitReached);
            } else {
                assert_eq!(result.status, SearchStatus::Solved);
                assert_eq!(result.distance, Some(1));
            }
            limited.max_depth = Some(2);
            let result = solve(scrambled, None, limited).unwrap();
            assert_eq!(result.status, SearchStatus::Solved);
            assert_eq!(
                result.distance,
                Some(if metric == Metric::Qtm { 2 } else { 1 })
            );
            limited.max_states = Some(1);
            limited.max_depth = Some(0);
            let result = solve(solved, None, limited).unwrap();
            assert_eq!(result.status, SearchStatus::Solved);
            assert_eq!(result.distance, Some(0));
            assert_eq!(result.solution, Some(Vec::new()));
            assert_eq!(result.visited, 1);
            assert_eq!(result.expanded, 0);
        }
        let mut limited = options(Metric::Qtm, algorithm);
        limited.max_states = Some(3);
        let result = solve(scrambled, None, limited).unwrap();
        assert_eq!(result.status, SearchStatus::LimitReached);
        assert!(result.visited <= 3);
        limited.max_states = Some(4);
        assert_eq!(solve(scrambled, None, limited).unwrap().distance, Some(2));
    }
}

#[test]
fn colored_graph_caps_are_explicit_and_exact_closure_is_complete() {
    let initial = one_face(Face::F).solved_state();
    assert!(explore_colored(initial, Metric::Qtm, Some(0)).is_err());
    for metric in [Metric::Qtm, Metric::Htm] {
        let exact = explore_colored(initial, metric, Some(4)).unwrap();
        assert!(exact.complete);
        for cap in 1..4 {
            let graph = explore_colored(initial, metric, Some(cap)).unwrap();
            assert!(!graph.complete);
            assert_eq!(graph.states.len(), cap);
            assert!(graph.arcs.iter().all(|&(a, b, _)| a < cap && b < cap));
            for source in 0..cap {
                for target in 0..cap {
                    if let Some(path) = graph.shortest_path(source, target) {
                        assert_eq!(replay(graph.states[source], &path), graph.states[target]);
                    }
                }
            }
        }
    }
    let frozen = BandageSpec::new(Partition::fully_bandaged()).solved_state();
    let graph = explore_colored(frozen, Metric::Qtm, Some(1)).unwrap();
    assert!(graph.complete);
    assert_eq!(graph.states.len(), 1);
    assert!(graph.arcs.is_empty());
}

#[test]
fn ordinary_valid_rigid_coloring_can_be_proven_unreachable() {
    // All edges, centers and the core form an immovable connected block. The
    // eight corners are singletons, so a three-cycle is physically consistent
    // and ordinary-cube valid, while this bandaging permits no turns at all.
    let labels = std::array::from_fn(|cell| {
        if CORNER_CELLS.contains(&(cell as u8)) {
            0
        } else {
            1
        }
    });
    let spec = BandageSpec::new(Partition::from_legacy(labels).unwrap());
    let mut corners = *CubeState::SOLVED.corners();
    corners[0] = 1;
    corners[1] = 2;
    corners[2] = 0;
    let cube = CubeState::try_new(corners, [0; 8], *CubeState::SOLVED.edges(), [0; 12]).unwrap();
    let initial = spec.state_from_cube(cube).unwrap();
    for face in Face::ALL {
        assert!(!initial.is_turnable(face));
    }
    for algorithm in [SearchAlgorithm::Bfs, SearchAlgorithm::Bidirectional] {
        let result = solve(initial, None, options(Metric::Qtm, algorithm)).unwrap();
        assert_eq!(result.status, SearchStatus::Unreachable);
        assert_eq!(result.solution, None);
        assert_eq!(result.distance, None);
        assert_eq!(result.stop_reason, None);
    }
}

#[test]
fn target_specifications_must_match() {
    let initial = one_face(Face::F).solved_state();
    let target = one_face(Face::U).solved_state();
    assert!(solve(initial, Some(target), SearchOptions::default()).is_err());
}

#[test]
fn short_legal_fixture_scrambles_have_shortest_replayable_solutions() {
    for fixture in fixtures::legacy() {
        let solved = BandageSpec::new(fixture.partition).solved_state();
        let mut initial = solved;
        let mut previous = None;
        for _ in 0..3 {
            let movement = Move::ALL
                .into_iter()
                .filter(|m| m.amount == Amount::Clockwise && initial.is_turnable(m.face))
                .find(|m| Some(m.face) != previous)
                .unwrap_or_else(|| {
                    Move::ALL
                        .into_iter()
                        .find(|m| initial.is_turnable(m.face))
                        .unwrap()
                });
            initial.try_turn(movement).unwrap();
            previous = Some(movement.face);
        }
        for metric in [Metric::Qtm, Metric::Htm] {
            let mut bfs = options(metric, SearchAlgorithm::Bfs);
            bfs.max_depth = Some(3);
            let baseline = solve(initial, None, bfs).unwrap();
            assert_eq!(baseline.status, SearchStatus::Solved, "{}", fixture.name);
            assert_eq!(replay(initial, baseline.solution.as_ref().unwrap()), solved);
            let mut bidirectional = options(metric, SearchAlgorithm::Bidirectional);
            bidirectional.max_depth = Some(3);
            let result = solve(initial, None, bidirectional).unwrap();
            assert_eq!(result.status, SearchStatus::Solved, "{}", fixture.name);
            assert_eq!(result.distance, baseline.distance);
            assert_eq!(replay(initial, result.solution.as_ref().unwrap()), solved);
        }
    }
}
