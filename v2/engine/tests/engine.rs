use bandaged_cube_engine::{
    Amount, AxisMajor, BandageSpec, BondLayout, BondShape, CubeState, Face, LegacySparse, Move,
    Partition, Tuned,
    explore::explore,
    fixtures,
    geometry::{BONDS, CORNER_CELLS, CORNER_FACES, EDGE_CELLS, EDGE_FACES, coordinates},
    parse_moves,
};
use std::{
    collections::{HashSet, VecDeque},
    mem::size_of,
};

fn random(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

#[test]
fn normalized_input_and_connectivity() {
    assert_eq!(
        Partition::from_legacy([0; 27]).unwrap(),
        Partition::singletons()
    );
    assert_eq!(
        Partition::from_legacy([255; 27]).unwrap(),
        Partition::fully_bandaged()
    );
    let mut disconnected = [0; 27];
    disconnected[0] = 1;
    disconnected[26] = 1;
    assert!(Partition::from_legacy(disconnected).is_err());
    let mut noncuboid = [0; 27];
    noncuboid[0] = 1;
    noncuboid[1] = 1;
    noncuboid[4] = 1;
    assert!(Partition::from_legacy(noncuboid).is_ok());
    let mut anchored = [0; 27];
    anchored[4] = 1;
    anchored[13] = 1;
    anchored[22] = 1;
    let anchored = Partition::from_legacy(anchored).unwrap();
    let shape = BondShape::<AxisMajor>::from_partition(&anchored);
    assert!(!shape.is_turnable(Face::U));
    assert!(!shape.is_turnable(Face::D));
    assert!(shape.is_turnable(Face::R));
    assert_eq!(shape.to_partition(), anchored);
    assert_eq!(size_of::<BondShape>(), 8);
    assert_eq!(size_of::<CubeState>(), 40);
}

#[test]
fn bonds_require_closure_and_used_bits() {
    assert!(BondShape::<AxisMajor>::from_bits(1 << 63).is_err());
    // Three sides of a square connect four cells; its fourth adjacency must be set too.
    let mut bits = 0;
    for (i, pair) in BONDS.into_iter().enumerate() {
        if [[0, 1], [0, 3], [1, 4]].contains(&pair) {
            bits |= 1 << i;
        }
    }
    assert!(BondShape::<AxisMajor>::from_bits(bits).is_err());
}

fn differential<L: BondLayout>(partition: Partition) {
    let initial = BondShape::<L>::from_partition(&partition);
    assert_eq!(initial.to_partition(), partition);
    assert_eq!(BondShape::<L>::from_bits(initial.bits()).unwrap(), initial);
    for movement in Move::ALL {
        assert_eq!(
            initial.is_turnable(movement.face),
            partition.is_turnable(movement.face)
        );
        match partition.try_turn(movement) {
            Ok(reference) => {
                let moved = initial.try_turn(movement).unwrap();
                assert_eq!(moved.to_partition(), reference, "{} {movement}", L::NAME);
                assert_eq!(moved.try_turn(movement.inverse()).unwrap(), initial);
                let cw = Move::clockwise(movement.face);
                let mut repeated = initial;
                for _ in 0..movement.amount as u8 {
                    repeated = repeated.try_turn(cw).unwrap();
                }
                assert_eq!(repeated, moved);
            }
            Err(_) => assert!(initial.try_turn(movement).is_err()),
        }
    }
}

#[test]
fn exhaustive_legacy_components_match_independent_partition_bfs() {
    for fixture in fixtures::legacy() {
        let mut seen = HashSet::from([fixture.partition]);
        let mut queue = VecDeque::from([fixture.partition]);
        let mut arcs = 0;
        while let Some(partition) = queue.pop_front() {
            differential::<AxisMajor>(partition);
            differential::<LegacySparse>(partition);
            differential::<Tuned>(partition);
            for face in Face::ALL {
                if let Ok(next) = partition.try_turn(Move::clockwise(face)) {
                    arcs += 1;
                    if seen.insert(next) {
                        queue.push_back(next);
                    }
                }
            }
        }
        assert_eq!(seen.len(), fixture.shapes, "{}", fixture.name);
        assert_eq!(arcs, fixture.clockwise_arcs);
        let graph = explore(
            BondShape::<AxisMajor>::from_partition(&fixture.partition),
            100_000,
        );
        assert!(graph.complete);
        assert_eq!(graph.vertices.len(), fixture.shapes);
        assert_eq!(graph.arcs.len(), fixture.clockwise_arcs);
        assert_eq!(
            graph.qtm_distances(0).into_iter().flatten().max().unwrap(),
            fixture.eccentricity_qtm
        );
        assert_eq!(
            graph
                .vertices
                .into_iter()
                .map(|s| s.to_partition())
                .collect::<HashSet<_>>(),
            seen
        );
    }
}

#[test]
fn connected_random_partitions_and_layout_conversions() {
    let mut rng = 123456789;
    for density in [1, 4, 12, 32, 64, 96] {
        for _ in 0..80 {
            let mut labels = std::array::from_fn(|i| i as u8 + 1);
            for [a, b] in BONDS {
                if random(&mut rng) % 100 < density {
                    let old = labels[b as usize];
                    let new = labels[a as usize];
                    for label in &mut labels {
                        if *label == old {
                            *label = new;
                        }
                    }
                }
            }
            let partition = Partition::from_legacy(labels).unwrap();
            differential::<AxisMajor>(partition);
            differential::<LegacySparse>(partition);
            differential::<Tuned>(partition);
            let natural = BondShape::<AxisMajor>::from_partition(&partition);
            assert_eq!(
                natural.reencode::<LegacySparse>().reencode::<AxisMajor>(),
                natural
            );
            assert_eq!(natural.reencode::<Tuned>().to_partition(), partition);
        }
    }
}

#[test]
fn distinct_unbandaged_loops_and_resource_limit() {
    let graph = explore(
        BondShape::<AxisMajor>::from_partition(&Partition::singletons()),
        1,
    );
    assert!(graph.complete);
    assert_eq!(graph.vertices.len(), 1);
    assert_eq!(graph.arcs.len(), 6);
    for &(a, b, movement) in &graph.arcs {
        assert_eq!((a, b), (0, 0));
        assert!(!CubeState::SOLVED.turn(movement).is_solved());
    }
    let graph = explore(
        BondShape::<AxisMajor>::from_partition(&fixtures::legacy()[0].partition),
        1,
    );
    assert!(!graph.complete);
    assert_eq!(graph.vertices.len(), 1);
    for face in Face::ALL {
        assert!(
            !BondShape::<AxisMajor>::from_partition(&Partition::fully_bandaged()).is_turnable(face)
        );
    }
}

#[test]
fn notation_and_legacy_directions() {
    for movement in Move::ALL {
        assert_eq!(movement.to_string().parse::<Move>().unwrap(), movement);
        assert_eq!(movement.inverse().inverse(), movement);
    }
    assert_eq!(parse_moves("  R U2 F' ").unwrap().len(), 3);
    for invalid in ["X", "r", "R3", "R2'", "R garbage", "", "é"] {
        assert!(invalid.parse::<Move>().is_err());
    }
    assert_eq!(
        Move::clockwise(Face::B).legacy_to_standard(),
        Move::new(Face::B, Amount::Counterclockwise)
    );
    assert_eq!(
        Move::clockwise(Face::U).legacy_to_standard(),
        Move::clockwise(Face::U)
    );
    // Independent legacy 3x3 matrix rotation. Explicitly map B/D to standard inverses.
    for face in Face::ALL {
        let mut cell_labels: [u8; 27] = std::array::from_fn(|i| i as u8);
        let selected: Vec<usize> = (0..27).filter(|&i| face.contains(i as u8)).collect();
        let source = selected.iter().map(|&i| cell_labels[i]).collect::<Vec<_>>();
        let order = if face == Face::R {
            [2, 5, 8, 1, 4, 7, 0, 3, 6]
        } else {
            [6, 3, 0, 7, 4, 1, 8, 5, 2]
        };
        for (dest, &index) in selected.iter().zip(&order) {
            cell_labels[*dest] = source[index];
        }
        for (dest, &home) in cell_labels.iter().enumerate() {
            assert_eq!(
                bandaged_cube_engine::geometry::destination(
                    home,
                    Move::clockwise(face).legacy_to_standard()
                ) as usize,
                dest
            );
        }
    }
}

#[test]
fn colored_known_quarter_turns_and_invalid_input() {
    // Independent standard tables: kociemba.org/math/CubeDefs.htm.
    let cp = [
        [3, 0, 1, 2, 4, 5, 6, 7],
        [4, 1, 2, 0, 7, 5, 6, 3],
        [1, 5, 2, 3, 0, 4, 6, 7],
        [0, 1, 2, 3, 5, 6, 7, 4],
        [0, 2, 6, 3, 4, 1, 5, 7],
        [0, 1, 3, 7, 4, 5, 2, 6],
    ];
    let co = [
        [0; 8],
        [2, 0, 0, 1, 1, 0, 0, 2],
        [1, 2, 0, 0, 2, 1, 0, 0],
        [0; 8],
        [0, 1, 2, 0, 0, 2, 1, 0],
        [0, 0, 1, 2, 0, 0, 2, 1],
    ];
    for face in Face::ALL {
        let state = CubeState::SOLVED.turn(Move::clockwise(face));
        assert_eq!(*state.corners(), cp[face.index()]);
        assert_eq!(*state.twists(), co[face.index()]);
        state.validate().unwrap();
        for movement in Move::ALL.into_iter().filter(|m| m.face == face) {
            assert_eq!(state.turn(movement).turn(movement.inverse()), state);
        }
    }
    let solved = CubeState::SOLVED;
    let mut twists = *solved.twists();
    twists[0] = 1;
    assert!(
        CubeState::try_new(*solved.corners(), twists, *solved.edges(), *solved.flips()).is_err()
    );
    let mut flips = *solved.flips();
    flips[0] = 1;
    assert!(
        CubeState::try_new(*solved.corners(), *solved.twists(), *solved.edges(), flips).is_err()
    );
    let mut corners = *solved.corners();
    corners.swap(0, 1);
    assert!(
        CubeState::try_new(corners, *solved.twists(), *solved.edges(), *solved.flips()).is_err()
    );
    corners[0] = 255;
    assert!(
        CubeState::try_new(corners, *solved.twists(), *solved.edges(), *solved.flips()).is_err()
    );
}

#[test]
fn colored_random_walk_matches_independent_sticker_rotation() {
    #[derive(Clone, Copy)]
    struct Sticker {
        pos: [i8; 3],
        normal: [i8; 3],
        color: Face,
    }
    fn rotate([x, y, z]: [i8; 3], face: Face) -> [i8; 3] {
        match face {
            Face::U => [y, -x, z],
            Face::R => [x, z, -y],
            Face::F => [z, y, -x],
            Face::D => [-y, x, z],
            Face::L => [x, -z, y],
            Face::B => [-z, y, x],
        }
    }
    let mut stickers = Vec::new();
    for (slot, cell) in CORNER_CELLS.into_iter().enumerate() {
        for color in CORNER_FACES[slot] {
            stickers.push(Sticker {
                pos: coordinates(cell),
                normal: color.normal(),
                color,
            });
        }
    }
    for (slot, cell) in EDGE_CELLS.into_iter().enumerate() {
        for color in EDGE_FACES[slot] {
            stickers.push(Sticker {
                pos: coordinates(cell),
                normal: color.normal(),
                color,
            });
        }
    }
    let mut cube = CubeState::SOLVED;
    let mut rng = 987654321;
    for _ in 0..1200 {
        let movement = Move::ALL[(random(&mut rng) % 18) as usize];
        cube = cube.turn(movement);
        cube.validate().unwrap();
        let n = movement.face.normal();
        for sticker in &mut stickers {
            if sticker.pos.iter().zip(n).map(|(p, n)| p * n).sum::<i8>() == 1 {
                for _ in 0..movement.amount as u8 {
                    sticker.pos = rotate(sticker.pos, movement.face);
                    sticker.normal = rotate(sticker.normal, movement.face);
                }
            }
        }
        for (slot, cell) in CORNER_CELLS.into_iter().enumerate() {
            for (direction, face) in CORNER_FACES[slot].into_iter().enumerate() {
                let observed = stickers
                    .iter()
                    .find(|s| s.pos == coordinates(cell) && s.normal == face.normal())
                    .unwrap()
                    .color;
                let original_direction = (direction + 3 - cube.twists()[slot] as usize) % 3;
                assert_eq!(
                    observed,
                    CORNER_FACES[cube.corners()[slot] as usize][original_direction]
                );
            }
        }
        for (slot, cell) in EDGE_CELLS.into_iter().enumerate() {
            for (direction, face) in EDGE_FACES[slot].into_iter().enumerate() {
                let observed = stickers
                    .iter()
                    .find(|s| s.pos == coordinates(cell) && s.normal == face.normal())
                    .unwrap()
                    .color;
                assert_eq!(
                    observed,
                    EDGE_FACES[cube.edges()[slot] as usize]
                        [direction ^ cube.flips()[slot] as usize]
                );
            }
        }
    }
}

#[test]
fn bandaged_colored_walk_cache_and_inverse_replay() {
    let mut rng = 111222333;
    for fixture in fixtures::legacy() {
        let spec = BandageSpec::new(fixture.partition);
        let mut state = spec.solved_state();
        let mut path = Vec::new();
        for _ in 0..600 {
            let moves = Move::ALL
                .into_iter()
                .filter(|m| state.is_turnable(m.face))
                .collect::<Vec<_>>();
            let movement = moves[(random(&mut rng) % moves.len() as u64) as usize];
            state.try_turn(movement).unwrap();
            path.push(movement);
            assert!(state.check_shape());
            state.cube().validate().unwrap();
            for face in Face::ALL {
                if !state.is_turnable(face) {
                    let before = state;
                    assert!(state.try_turn(Move::clockwise(face)).is_err());
                    assert_eq!(state, before);
                }
            }
        }
        for movement in path.into_iter().rev() {
            state.try_turn(movement.inverse()).unwrap();
        }
        assert!(state.cube().is_solved());
        assert_eq!(state.shape().to_partition(), fixture.partition);
    }
}
