//! The 24 proper spatial rotations of the cube, independent of legal face turns.
//!
//! Rotation keys use the axis-major bond order, so their values remain stable
//! when the move engine changes its optimized storage layout. Proper rotation
//! keys exclude reflections; separate helpers optionally identify mirror images.
//! A spatial symmetry changes the frame and also renames move faces.

use crate::{
    AxisMajor, BondLayout, BondShape, Face, Move,
    geometry::{BONDS, bond_index, cell_at, coordinates},
};

#[derive(Debug, Clone, Copy)]
struct RotationTable {
    axes: [u8; 3],
    signs: [i8; 3],
    cells: [u8; 27],
    bonds: [u8; 54],
    faces: [Face; 6],
}

const fn transform(p: [i8; 3], axes: [u8; 3], signs: [i8; 3]) -> [i8; 3] {
    [
        p[axes[0] as usize] * signs[0],
        p[axes[1] as usize] * signs[1],
        p[axes[2] as usize] * signs[2],
    ]
}

const TABLES: [RotationTable; 24] = {
    let empty = RotationTable {
        axes: [0, 1, 2],
        signs: [1; 3],
        cells: [0; 27],
        bonds: [0; 54],
        faces: [Face::U; 6],
    };
    let mut tables = [empty; 24];
    // Even permutations first; for each, the product of the signs must equal
    // its parity so that the resulting signed permutation has determinant +1.
    let permutations = [
        [0, 1, 2],
        [1, 2, 0],
        [2, 0, 1],
        [0, 2, 1],
        [2, 1, 0],
        [1, 0, 2],
    ];
    let mut p = 0;
    while p < 6 {
        let parity = if p < 3 { 1 } else { -1 };
        let mut s = 0;
        while s < 4 {
            let a = if s & 1 == 0 { 1 } else { -1 };
            let b = if s & 2 == 0 { 1 } else { -1 };
            let signs = [a, b, parity * a * b];
            let axes = permutations[p];
            let mut table = empty;
            table.axes = axes;
            table.signs = signs;
            let mut cell = 0;
            while cell < 27 {
                table.cells[cell] = cell_at(transform(coordinates(cell as u8), axes, signs));
                cell += 1;
            }
            let mut bond = 0;
            while bond < 54 {
                table.bonds[bond] = bond_index(
                    table.cells[BONDS[bond][0] as usize],
                    table.cells[BONDS[bond][1] as usize],
                ) as u8;
                bond += 1;
            }
            let mut face = 0;
            while face < 6 {
                let normal = transform(Face::ALL[face].normal(), axes, signs);
                let mut target = 0;
                while target < 6 {
                    let candidate = Face::ALL[target].normal();
                    if normal[0] == candidate[0]
                        && normal[1] == candidate[1]
                        && normal[2] == candidate[2]
                    {
                        table.faces[face] = Face::ALL[target];
                        break;
                    }
                    target += 1;
                }
                face += 1;
            }
            tables[p * 4 + s] = table;
            s += 1;
        }
        p += 1;
    }
    tables
};

/// A proper cube rotation, with a stable index in the precomputed table.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Rotation(u8);

impl Rotation {
    pub const IDENTITY: Self = Self(0);
    pub const ALL: [Self; 24] = {
        let mut result = [Self::IDENTITY; 24];
        let mut i = 0;
        while i < 24 {
            result[i] = Self(i as u8);
            i += 1;
        }
        result
    };

    pub const fn index(self) -> usize {
        self.0 as usize
    }

    pub const fn map_vector(self, vector: [i8; 3]) -> [i8; 3] {
        let table = TABLES[self.index()];
        transform(vector, table.axes, table.signs)
    }

    /// Transform a cell index in the existing 27-cell coordinate convention.
    pub const fn map_cell(self, cell: u8) -> u8 {
        TABLES[self.index()].cells[cell as usize]
    }

    pub const fn map_face(self, face: Face) -> Face {
        TABLES[self.index()].faces[face.index()]
    }

    /// Conjugate a face turn into the rotated frame. Proper rotations preserve
    /// the clockwise/half/counterclockwise amount.
    pub const fn map_move(self, movement: Move) -> Move {
        Move::new(self.map_face(movement.face), movement.amount)
    }

    /// Compose rotations by applying `self` first, followed by `next`.
    pub fn then(self, next: Self) -> Self {
        let basis = [
            next.map_vector(self.map_vector([1, 0, 0])),
            next.map_vector(self.map_vector([0, 1, 0])),
            next.map_vector(self.map_vector([0, 0, 1])),
        ];
        Self::ALL
            .into_iter()
            .find(|rotation| {
                rotation.map_vector([1, 0, 0]) == basis[0]
                    && rotation.map_vector([0, 1, 0]) == basis[1]
                    && rotation.map_vector([0, 0, 1]) == basis[2]
            })
            .expect("proper rotations are closed under composition")
    }

    pub fn inverse(self) -> Self {
        Self::ALL
            .into_iter()
            .find(|rotation| self.then(*rotation) == Self::IDENTITY)
            .expect("every proper rotation has an inverse")
    }
}

fn rotated_bits<L: BondLayout, T: BondLayout>(shape: BondShape<L>, rotation: Rotation) -> u64 {
    let destinations = TABLES[rotation.index()].bonds;
    let mut result = 0;
    let bits = shape.bits();
    for (source, target) in destinations.into_iter().enumerate() {
        result |= ((bits >> L::POSITIONS[source]) & 1) << T::POSITIONS[target as usize];
    }
    result
}

/// Rotate a connected partition while retaining its declared bond layout.
pub fn rotate<L: BondLayout>(shape: BondShape<L>, rotation: Rotation) -> BondShape<L> {
    BondShape::from_valid_bits(rotated_bits::<L, L>(shape, rotation))
}

/// Return the least axis-major bond encoding and a rotation transporting the
/// input to that representative. Equal minima choose the earliest table index.
pub fn canonicalize<L: BondLayout>(shape: BondShape<L>) -> (BondShape<AxisMajor>, Rotation) {
    let mut minimum = u64::MAX;
    let mut witness = Rotation::IDENTITY;
    for rotation in Rotation::ALL {
        let bits = rotated_bits::<L, AxisMajor>(shape, rotation);
        if bits < minimum {
            minimum = bits;
            witness = rotation;
        }
    }
    (BondShape::from_valid_bits(minimum), witness)
}

/// A layout-independent proper-rotation key for enumeration and persistence.
pub fn canonical_key<L: BondLayout>(shape: BondShape<L>) -> u64 {
    canonicalize(shape).0.bits()
}

/// Reflect a cell across the plane x = 0, exchanging the right and left faces.
pub const fn reflect_cell(cell: u8) -> u8 {
    let [x, y, z] = coordinates(cell);
    cell_at([-x, y, z])
}

const REFLECTED_BONDS: [u8; 54] = {
    let mut bonds = [0; 54];
    let mut index = 0;
    while index < 54 {
        bonds[index] =
            bond_index(reflect_cell(BONDS[index][0]), reflect_cell(BONDS[index][1])) as u8;
        index += 1;
    }
    bonds
};

/// Reflect a connected partition while retaining its declared bond layout.
/// Together with the 24 proper rotations, this generates all 48 cube symmetries.
pub fn reflect<L: BondLayout>(shape: BondShape<L>) -> BondShape<L> {
    let mut result = 0;
    let bits = shape.bits();
    for (source, target) in REFLECTED_BONDS.into_iter().enumerate() {
        result |= ((bits >> L::POSITIONS[source]) & 1) << L::POSITIONS[target as usize];
    }
    BondShape::from_valid_bits(result)
}

/// Conjugate a face turn through the x = 0 reflection. A reflection reverses
/// handedness, so clockwise and counterclockwise exchange on every face.
pub const fn reflect_move(movement: Move) -> Move {
    let face = match movement.face {
        Face::R => Face::L,
        Face::L => Face::R,
        face => face,
    };
    Move::new(face, movement.inverse().amount)
}

/// A layout-independent key up to all 48 spatial symmetries, including mirrors.
/// This canonicalizes one shape, not its whole legal-turn component.
pub fn canonical_key_with_reflections<L: BondLayout>(shape: BondShape<L>) -> u64 {
    canonical_key(shape).min(canonical_key(reflect(shape)))
}
