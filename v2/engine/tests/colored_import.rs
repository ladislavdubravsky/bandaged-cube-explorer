use bandaged_cube_engine::{
    BandageSpec, CubeState, Error, Face, Move, Partition, fixtures,
    geometry::{cell_at, destination, rotate_vector},
};

const SOLVED_FACELETS: &str = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB";

fn random(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

fn block(cells: &[usize]) -> BandageSpec {
    let mut labels = [0; 27];
    for &cell in cells {
        labels[cell] = 1;
    }
    BandageSpec::new(Partition::from_legacy(labels).unwrap())
}

#[test]
fn colored_hex_id_has_a_stable_solved_encoding_and_reference_frame() {
    let solved = BandageSpec::new(Partition::singletons()).solved_state();
    assert_eq!(
        solved.hex_id(),
        concat!(
            "00000000000000",
            "000306090c0f1215",
            "00020406080a0c0e10121416"
        )
    );
    assert_eq!(
        BandageSpec::new(Partition::fully_bandaged())
            .solved_state()
            .hex_id(),
        concat!(
            "3fffffffffffff",
            "000306090c0f1215",
            "00020406080a0c0e10121416"
        )
    );
    assert_eq!(solved.hex_id().len(), 54);
    assert!(
        solved
            .hex_id()
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    );

    // Two rotated copies of a reference dimer must retain different IDs.
    let horizontal = block(&[0, 1]).solved_state();
    let vertical = block(&[0, 3]).solved_state();
    assert_eq!(horizontal.cube(), vertical.cube());
    assert_ne!(horizontal.hex_id(), vertical.hex_id());
    assert_eq!(
        bandaged_cube_engine::symmetry::canonical_key(horizontal.shape()),
        bandaged_cube_engine::symmetry::canonical_key(vertical.shape())
    );

    // Relabeling blocks does not change the encoded membership.
    let mut relabeled = [0; 27];
    relabeled[0] = 255;
    relabeled[1] = 255;
    assert_eq!(
        horizontal.hex_id(),
        BandageSpec::new(Partition::from_legacy(relabeled).unwrap())
            .solved_state()
            .hex_id()
    );
}

#[test]
fn colored_hex_id_matches_imports_and_distinguishes_twists_and_flips() {
    let spec = BandageSpec::new(fixtures::legacy()[0].partition);
    let mut replayed = spec.solved_state();
    for movement in bandaged_cube_engine::parse_moves("F R2").unwrap() {
        replayed.try_turn(movement).unwrap();
    }
    let imported = spec.state_from_cube(*replayed.cube()).unwrap();
    let facelets = spec
        .state_from_cube(CubeState::from_facelets(&replayed.cube().to_facelets()).unwrap())
        .unwrap();
    assert_eq!(replayed.hex_id(), imported.hex_id());
    assert_eq!(replayed.hex_id(), facelets.hex_id());

    let spec = BandageSpec::new(Partition::singletons());
    let solved = spec.solved_state();
    let cube = *solved.cube();
    let mut twists = [0; 8];
    twists[0] = 1;
    twists[1] = 2;
    let twisted = spec
        .state_from_cube(
            CubeState::try_new(*cube.corners(), twists, *cube.edges(), [0; 12]).unwrap(),
        )
        .unwrap();
    let mut flips = [0; 12];
    flips[0] = 1;
    flips[1] = 1;
    let flipped = spec
        .state_from_cube(CubeState::try_new(*cube.corners(), [0; 8], *cube.edges(), flips).unwrap())
        .unwrap();
    assert_eq!(solved.shape(), twisted.shape());
    assert_eq!(solved.shape(), flipped.shape());
    assert_ne!(solved.hex_id(), twisted.hex_id());
    assert_ne!(solved.hex_id(), flipped.hex_id());
    assert_ne!(twisted.hex_id(), flipped.hex_id());
    assert_eq!(&twisted.hex_id()[14..18], "0105");
    assert_eq!(&flipped.hex_id()[30..34], "0103");
}

#[test]
fn ordinary_cube_validation_remains_distinct_from_bandage_geometry() {
    let solved = CubeState::SOLVED;
    let mut corners = *solved.corners();
    corners[1] = corners[0];
    assert!(matches!(
        CubeState::try_new(corners, [0; 8], *solved.edges(), [0; 12]),
        Err(Error::InvalidColoredState(_))
    ));
    let mut twists = [0; 8];
    twists[0] = 1;
    assert!(CubeState::try_new(*solved.corners(), twists, *solved.edges(), [0; 12]).is_err());
    twists[0] = 3;
    assert!(CubeState::try_new(*solved.corners(), twists, *solved.edges(), [0; 12]).is_err());
    let mut flips = [0; 12];
    flips[0] = 1;
    assert!(CubeState::try_new(*solved.corners(), [0; 8], *solved.edges(), flips).is_err());
    flips[0] = 2;
    assert!(CubeState::try_new(*solved.corners(), [0; 8], *solved.edges(), flips).is_err());
    let mut edges = *solved.edges();
    edges.swap(0, 1);
    assert!(CubeState::try_new(*solved.corners(), [0; 8], edges, [0; 12]).is_err());
}

#[test]
fn rigid_blocks_require_colored_orientations_in_addition_to_piece_positions() {
    // URF corner and UR edge are adjacent. Their positions and hence the entire
    // shape remain solved in both examples; only the colored orientations vary.
    let spec = block(&[8, 5]);
    let solved = CubeState::SOLVED;
    let mut twists = [0; 8];
    twists[0] = 1;
    twists[1] = 2;
    let twisted = CubeState::try_new(*solved.corners(), twists, *solved.edges(), [0; 12]).unwrap();
    assert_eq!(twisted.piece_cells(), solved.piece_cells());
    assert!(matches!(
        spec.state_from_cube(twisted),
        Err(Error::InvalidBandagedState(_))
    ));

    let mut flips = [0; 12];
    flips[0] = 1;
    flips[1] = 1;
    let flipped = CubeState::try_new(*solved.corners(), [0; 8], *solved.edges(), flips).unwrap();
    assert_eq!(flipped.piece_cells(), solved.piece_cells());
    assert!(matches!(
        spec.state_from_cube(flipped),
        Err(Error::InvalidBandagedState(_))
    ));

    // Both are perfectly valid when each piece is an independent block.
    let ordinary = BandageSpec::new(Partition::singletons());
    assert!(ordinary.state_from_cube(twisted).is_ok());
    assert!(ordinary.state_from_cube(flipped).is_ok());
}

#[test]
fn disconnected_and_connected_but_distorted_blocks_are_rejected_without_panicking() {
    let solved = CubeState::SOLVED;
    let mut corners = *solved.corners();
    let mut edges = *solved.edges();
    corners.swap(0, 1);
    edges.swap(1, 2); // Match parity without moving the bandaged UR edge.
    let cube = CubeState::try_new(corners, [0; 8], edges, [0; 12]).unwrap();
    assert!(matches!(
        block(&[8, 5]).state_from_cube(cube),
        Err(Error::DisconnectedBlock(_))
    ));

    // The corner moves from URF to URB, still adjacent to UR. Adding the fixed
    // R center fixes the frame: no common rotation maps all three members.
    let mut corners = *solved.corners();
    corners.swap(0, 3);
    let cube = CubeState::try_new(corners, [0; 8], edges, [0; 12]).unwrap();
    assert!(matches!(
        block(&[8, 5, 14]).state_from_cube(cube),
        Err(Error::InvalidBandagedState(_))
    ));
}

#[test]
fn centers_are_unmarked_and_core_constrains_position_without_a_spin() {
    let u = Move::clockwise(Face::U);
    let cube = CubeState::SOLVED.turn(u);
    // Turning a center-bearing block around that center's normal is valid.
    let centered = block(&[4, 7]);
    assert!(centered.state_from_cube(cube).is_ok());

    // Core and both opposite centers can share that same rigid rotation. The
    // core has no orientation, so it must not spuriously force identity.
    let anchored = block(&[13, 4, 22, 7]);
    let imported = anchored.state_from_cube(cube).unwrap();
    assert!(imported.check_shape());
    assert!(!anchored.solved_state().is_turnable(Face::U));
    assert!(!anchored.solved_state().is_turnable(Face::D));

    // Import asserts rigid geometry only. Even when every face is blocked,
    // geometrically compatible singleton corner permutations can be imported.
    let mut labels = [1; 27];
    for cell in bandaged_cube_engine::geometry::CORNER_CELLS {
        labels[cell as usize] = 0;
    }
    let frozen = BandageSpec::new(Partition::from_legacy(labels).unwrap());
    let mut corners = *CubeState::SOLVED.corners();
    corners[..3].rotate_left(1);
    let cube = CubeState::try_new(corners, [0; 8], *CubeState::SOLVED.edges(), [0; 12]).unwrap();
    let imported = frozen.state_from_cube(cube).unwrap();
    assert!(
        Face::ALL
            .into_iter()
            .all(|face| !imported.is_turnable(face))
    );
    assert!(!imported.cube().is_solved());
}

fn legal_walk(spec: BandageSpec, rng: &mut u64, steps: usize) {
    let mut state = spec.solved_state();
    for _ in 0..steps {
        let moves: Vec<_> = Move::ALL
            .into_iter()
            .filter(|m| state.is_turnable(m.face))
            .collect();
        if moves.is_empty() {
            break;
        }
        state
            .try_turn(moves[random(rng) as usize % moves.len()])
            .unwrap();
        let cube = *state.cube();
        let imported = spec.state_from_cube(cube).unwrap();
        assert_eq!(imported, state);
        assert!(imported.check_shape());
        assert_eq!(CubeState::from_facelets(&cube.to_facelets()).unwrap(), cube);
    }
}

#[test]
fn long_fixture_walks_and_noncuboid_core_blocks_import_exactly() {
    let mut rng = 0x9617_fe62_8901;
    for fixture in fixtures::legacy() {
        legal_walk(BandageSpec::new(fixture.partition), &mut rng, 800);
    }
    legal_walk(block(&[0, 1, 4]), &mut rng, 800); // Noncuboid L block.
    legal_walk(block(&[4, 13, 22]), &mut rng, 800); // Core anchor.
    legal_walk(BandageSpec::new(Partition::singletons()), &mut rng, 800);
    assert_eq!(
        BandageSpec::new(Partition::fully_bandaged())
            .state_from_cube(CubeState::SOLVED)
            .unwrap(),
        BandageSpec::new(Partition::fully_bandaged()).solved_state()
    );
}

// An independent description of face viewing coordinates checks the facelet
// convention against spatial moves, rather than only roundtripping a codec.
fn facelet_location(index: usize) -> (u8, Face) {
    let face = Face::ALL[index / 9];
    let row = (index % 9 / 3) as i8;
    let column = (index % 3) as i8;
    let point = match face {
        Face::U => [column - 1, 1 - row, 1],
        Face::R => [1, column - 1, 1 - row],
        Face::F => [column - 1, -1, 1 - row],
        Face::D => [column - 1, row - 1, -1],
        Face::L => [-1, 1 - column, 1 - row],
        Face::B => [1 - column, 1, 1 - row],
    };
    (cell_at(point), face)
}

fn turn_facelets(facelets: &str, movement: Move) -> String {
    let mut result = [b'?'; 54];
    for (source, color) in facelets.bytes().enumerate() {
        let (cell, face) = facelet_location(source);
        let target_cell = destination(cell, movement);
        let mut normal = face.normal();
        if movement.face.contains(cell) {
            for _ in 0..movement.amount as u8 {
                normal = rotate_vector(normal, movement.face);
            }
        }
        let target = (0..54)
            .find(|&index| {
                let (candidate, face) = facelet_location(index);
                candidate == target_cell && face.normal() == normal
            })
            .unwrap();
        result[target] = color;
    }
    result.into_iter().map(char::from).collect()
}

#[test]
fn facelets_match_standard_spatial_convention_for_every_move_and_random_words() {
    assert_eq!(CubeState::SOLVED.to_facelets(), SOLVED_FACELETS);
    assert_eq!(
        CubeState::from_facelets(SOLVED_FACELETS).unwrap(),
        CubeState::SOLVED
    );
    for movement in Move::ALL {
        let expected = turn_facelets(SOLVED_FACELETS, movement);
        assert_eq!(CubeState::SOLVED.turn(movement).to_facelets(), expected);
        assert_eq!(
            CubeState::from_facelets(&expected).unwrap(),
            CubeState::SOLVED.turn(movement)
        );
    }
    let mut rng = 0x0c01_04ed;
    let mut cube = CubeState::SOLVED;
    let mut facelets = SOLVED_FACELETS.to_owned();
    for _ in 0..1_000 {
        let movement = Move::ALL[random(&mut rng) as usize % 18];
        cube = cube.turn(movement);
        facelets = turn_facelets(&facelets, movement);
        assert_eq!(cube.to_facelets(), facelets);
        assert_eq!(CubeState::from_facelets(&facelets).unwrap(), cube);
    }
}

fn facelets_with_mutation(mut mutate: impl FnMut(&mut [u8])) -> String {
    let mut facelets = SOLVED_FACELETS.as_bytes().to_vec();
    mutate(&mut facelets);
    String::from_utf8(facelets).unwrap()
}

#[test]
fn facelet_import_rejects_invalid_input_and_impossible_cube_invariants() {
    let invalid = [
        "".to_owned(),
        SOLVED_FACELETS[..53].to_owned(),
        format!("{SOLVED_FACELETS}U"),
        SOLVED_FACELETS.to_lowercase(),
        facelets_with_mutation(|f| f[0] = b'R'), // Wrong counts.
        facelets_with_mutation(|f| f.swap(4, 13)), // Mismatched fixed centers.
        facelets_with_mutation(|f| f.swap(9, 20)), // Mirrored corner.
        facelets_with_mutation(|f| {
            f.swap(8, 9);
            f.swap(9, 20);
        }), // Lone twist.
        facelets_with_mutation(|f| f.swap(5, 10)), // Lone flip.
        facelets_with_mutation(|f| {
            f.swap(5, 7);
            f.swap(10, 19);
        }), // Odd edge permutation.
        "é".repeat(27),
    ];
    for facelets in invalid {
        assert!(
            matches!(
                CubeState::from_facelets(&facelets),
                Err(Error::InvalidColoredState(_))
            ),
            "{facelets}"
        );
    }
}
