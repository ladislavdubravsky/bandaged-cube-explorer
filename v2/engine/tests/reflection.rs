use std::collections::HashSet;

use bandaged_cube_engine::{
    Amount, AxisMajor, BondShape, Face, LegacySparse, Move, Partition,
    geometry::{BONDS, coordinates},
    symmetry::{
        Rotation, canonical_key, canonical_key_with_reflections, reflect, reflect_cell,
        reflect_move, rotate,
    },
};

fn independent_reflection(shape: BondShape<AxisMajor>) -> Partition {
    let original = shape.to_partition();
    let mut labels = [0; 27];
    for cell in 0..27 {
        // Each three-cell row runs from left to right in the legacy convention.
        let destination = cell / 3 * 3 + 2 - cell % 3;
        labels[destination] = original.labels()[cell];
    }
    Partition::from_legacy(labels).unwrap()
}

#[test]
fn reflection_and_rotations_generate_all_48_cube_symmetries() {
    let mut permutations = HashSet::new();
    for rotation in Rotation::ALL {
        permutations.insert(std::array::from_fn::<_, 27, _>(|cell| {
            rotation.map_cell(cell as u8)
        }));
        permutations.insert(std::array::from_fn::<_, 27, _>(|cell| {
            rotation.map_cell(reflect_cell(cell as u8))
        }));
    }
    assert_eq!(permutations.len(), 48);
    for cell in 0..27 {
        let [x, y, z] = coordinates(cell);
        assert_eq!(coordinates(reflect_cell(cell)), [-x, y, z]);
        assert_eq!(reflect_cell(reflect_cell(cell)), cell);
    }
    assert_eq!(reflect_cell(13), 13);
}

fn check_move_conjugacy(shape: BondShape<AxisMajor>) {
    let mirrored = reflect(shape);
    assert_eq!(mirrored.to_partition(), independent_reflection(shape));
    assert_eq!(reflect(mirrored), shape);
    assert_eq!(
        reflect(shape.reencode::<LegacySparse>()).reencode::<AxisMajor>(),
        mirrored
    );
    for movement in Move::ALL {
        let reflected_move = reflect_move(movement);
        assert_eq!(reflect_move(reflected_move), movement);
        assert_eq!(
            shape.is_turnable(movement.face),
            mirrored.is_turnable(reflected_move.face)
        );
        match shape.try_turn(movement) {
            Ok(next) => assert_eq!(reflect(next), mirrored.try_turn(reflected_move).unwrap()),
            Err(_) => assert!(mirrored.try_turn(reflected_move).is_err()),
        }
    }
}

#[test]
fn all_54_bonds_reflect_in_both_layouts_and_conjugate_all_18_moves() {
    for [a, b] in BONDS {
        let mut labels = [0; 27];
        labels[a as usize] = 1;
        labels[b as usize] = 1;
        let shape =
            BondShape::<AxisMajor>::from_partition(&Partition::from_legacy(labels).unwrap());
        check_move_conjugacy(shape);
    }
}

#[test]
fn noncuboid_and_core_blocks_reflect_and_conjugate_all_move_amounts() {
    let mut labels = [0; 27];
    for cell in [0, 1, 4] {
        labels[cell] = 1;
    }
    for cell in [10, 13] {
        labels[cell] = 2;
    }
    for cell in [20, 23, 26] {
        labels[cell] = 3;
    }
    let shape = BondShape::<AxisMajor>::from_partition(&Partition::from_legacy(labels).unwrap());
    check_move_conjugacy(shape);
    for face in Face::ALL {
        let expected = match face {
            Face::R => Face::L,
            Face::L => Face::R,
            face => face,
        };
        assert_eq!(
            reflect_move(Move::new(face, Amount::Clockwise)),
            Move::new(expected, Amount::Counterclockwise)
        );
        assert_eq!(
            reflect_move(Move::new(face, Amount::Half)),
            Move::new(expected, Amount::Half)
        );
    }
}

#[test]
fn mirror_keys_identify_a_chiral_shape_and_preserve_layout_independence() {
    let mut labels = [0; 27];
    for (index, block) in [[0, 1], [5, 8], [19, 22], [15, 16]].into_iter().enumerate() {
        for cell in block {
            labels[cell] = index as u8 + 1;
        }
    }
    let shape = BondShape::<AxisMajor>::from_partition(&Partition::from_legacy(labels).unwrap());
    let mirror = reflect(shape);
    assert_ne!(canonical_key(shape), canonical_key(mirror));
    let minimum = canonical_key(shape).min(canonical_key(mirror));
    for rotation in Rotation::ALL {
        for transformed in [rotate(shape, rotation), rotate(mirror, rotation)] {
            assert_eq!(canonical_key_with_reflections(transformed), minimum);
            assert_eq!(
                canonical_key_with_reflections(transformed.reencode::<LegacySparse>()),
                minimum
            );
        }
    }
}
