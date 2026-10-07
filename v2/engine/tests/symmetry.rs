use std::collections::HashSet;

use bandaged_cube_engine::{
    AxisMajor, BondShape, Face, LegacySparse, Move, Partition,
    geometry::{BONDS, cell_at, coordinates},
    symmetry::{Rotation, canonical_key, canonicalize, rotate},
};

#[test]
fn rotations_form_the_proper_cube_group() {
    let mut permutations = HashSet::new();
    for rotation in Rotation::ALL {
        let cells: [u8; 27] = std::array::from_fn(|i| rotation.map_cell(i as u8));
        assert!(permutations.insert(cells));
        assert_eq!(cells.into_iter().collect::<HashSet<_>>().len(), 27);
        assert_eq!(rotation.map_cell(13), 13);

        let x = rotation.map_vector([1, 0, 0]);
        let y = rotation.map_vector([0, 1, 0]);
        let z = rotation.map_vector([0, 0, 1]);
        let cross = [
            x[1] * y[2] - x[2] * y[1],
            x[2] * y[0] - x[0] * y[2],
            x[0] * y[1] - x[1] * y[0],
        ];
        assert_eq!(cross, z, "reflections must be excluded");
        for cell in 0..27 {
            assert_eq!(
                coordinates(rotation.map_cell(cell)),
                rotation.map_vector(coordinates(cell))
            );
            assert_eq!(rotation.inverse().map_cell(rotation.map_cell(cell)), cell);
        }
        for [a, b] in BONDS {
            let [x, y] = [rotation.map_cell(a), rotation.map_cell(b)];
            assert!(BONDS.contains(&[x, y]) || BONDS.contains(&[y, x]));
        }
        for next in Rotation::ALL {
            let composed = rotation.then(next);
            for cell in 0..27 {
                assert_eq!(
                    composed.map_cell(cell),
                    next.map_cell(rotation.map_cell(cell))
                );
            }
        }
    }
    assert_eq!(permutations.len(), 24);
}

fn independent_rotation(shape: BondShape<AxisMajor>, rotation: Rotation) -> Partition {
    let before = shape.to_partition();
    let mut labels = [0; 27];
    for cell in 0..27 {
        let destination = cell_at(rotation.map_vector(coordinates(cell as u8)));
        labels[destination as usize] = before.labels()[cell];
    }
    Partition::from_legacy(labels).unwrap()
}

#[test]
fn rotations_transport_partitions_legality_and_all_move_amounts() {
    // Includes noncuboid blocks and a core bond, so all 54 bond positions matter.
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
    for rotation in Rotation::ALL {
        let rotated = rotate(shape, rotation);
        assert_eq!(
            rotated.to_partition(),
            independent_rotation(shape, rotation)
        );
        assert_eq!(rotate(rotated, rotation.inverse()), shape);
        assert_eq!(
            rotate(shape.reencode::<LegacySparse>(), rotation).reencode::<AxisMajor>(),
            rotated
        );
        for face in Face::ALL {
            assert_eq!(
                shape.is_turnable(face),
                rotated.is_turnable(rotation.map_face(face))
            );
        }
        for movement in Move::ALL {
            match shape.try_turn(movement) {
                Ok(next) => assert_eq!(
                    rotate(next, rotation),
                    rotated.try_turn(rotation.map_move(movement)).unwrap()
                ),
                Err(_) => assert!(rotated.try_turn(rotation.map_move(movement)).is_err()),
            }
        }
    }
}

#[test]
fn every_bond_position_transports_in_both_layouts() {
    for [a, b] in BONDS {
        let mut labels = [0; 27];
        labels[a as usize] = 1;
        labels[b as usize] = 1;
        let shape =
            BondShape::<AxisMajor>::from_partition(&Partition::from_legacy(labels).unwrap());
        for rotation in Rotation::ALL {
            let reference = independent_rotation(shape, rotation);
            assert_eq!(rotate(shape, rotation).to_partition(), reference);
            assert_eq!(
                rotate(shape.reencode::<LegacySparse>(), rotation).to_partition(),
                reference
            );
        }
    }
}

#[test]
fn canonical_keys_ignore_corner_placement_and_storage_layout() {
    let mut labels = [0; 27];
    for z in 0..2 {
        for y in 0..2 {
            for x in 0..2 {
                labels[z * 9 + y * 3 + x] = 1;
            }
        }
    }
    let shape = BondShape::<AxisMajor>::from_partition(&Partition::from_legacy(labels).unwrap());
    let (canonical, witness) = canonicalize(shape);
    assert_eq!(rotate(shape, witness), canonical);
    let mut placements = HashSet::new();
    for rotation in Rotation::ALL {
        let rotated = rotate(shape, rotation);
        placements.insert(rotated);
        assert_eq!(canonical_key(rotated), canonical.bits());
        assert_eq!(
            canonical_key(rotated.reencode::<LegacySparse>()),
            canonical.bits()
        );
    }
    assert_eq!(placements.len(), 8);
    assert_eq!(canonicalize(canonical).0, canonical);
    assert_eq!(
        canonicalize(BondShape::<AxisMajor>::from_partition(
            &Partition::singletons()
        ))
        .1,
        Rotation::IDENTITY
    );
}
