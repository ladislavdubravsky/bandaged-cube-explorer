//! Spatial conventions and move geometry for the 3x3 cube.
//!
//! The 27 cells include the virtual core. Cell indices preserve the legacy
//! ordering `down * 9 + front * 3 + right`, with each component in `0..=2`.
//! Physical coordinates are centered at zero, in `-1..=1`, with axes
//! x = right, y = back, z = up.
//!
//! Outer-face moves use standard Singmaster notation; clockwise is viewed from
//! outside the face. Helpers identify face layers and transform cell positions
//! and direction vectors through turns.
//!
//! Cell adjacency and corner/edge reference tables provide a shared geometric
//! basis for bond layouts and colored-cubie representations. Bandage types use
//! this geometry to check whether a move is legal for a particular shape.

use std::{fmt, str::FromStr};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(u8)]
pub enum Face {
    U,
    R,
    F,
    D,
    L,
    B,
}

impl Face {
    pub const ALL: [Self; 6] = [Self::U, Self::R, Self::F, Self::D, Self::L, Self::B];
    pub const fn index(self) -> usize {
        self as usize
    }
    pub const fn normal(self) -> [i8; 3] {
        match self {
            Self::U => [0, 0, 1],
            Self::R => [1, 0, 0],
            Self::F => [0, -1, 0],
            Self::D => [0, 0, -1],
            Self::L => [-1, 0, 0],
            Self::B => [0, 1, 0],
        }
    }
    pub const fn contains(self, cell: u8) -> bool {
        let p = coordinates(cell);
        let n = self.normal();
        p[0] * n[0] + p[1] * n[1] + p[2] * n[2] == 1
    }
    pub const fn layer_mask(self) -> u32 {
        let mut mask = 0;
        let mut cell = 0;
        while cell < 27 {
            if self.contains(cell) {
                mask |= 1 << cell;
            }
            cell += 1;
        }
        mask
    }
    pub const fn symbol(self) -> char {
        match self {
            Self::U => 'U',
            Self::R => 'R',
            Self::F => 'F',
            Self::D => 'D',
            Self::L => 'L',
            Self::B => 'B',
        }
    }
}

impl fmt::Display for Face {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.symbol())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(u8)]
pub enum Amount {
    Clockwise = 1,
    Half = 2,
    Counterclockwise = 3,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Move {
    pub face: Face,
    pub amount: Amount,
}

impl Move {
    pub const fn new(face: Face, amount: Amount) -> Self {
        Self { face, amount }
    }
    pub const fn clockwise(face: Face) -> Self {
        Self::new(face, Amount::Clockwise)
    }
    pub const fn index(self) -> usize {
        self.face.index() * 3 + self.amount as usize - 1
    }
    pub const fn inverse(self) -> Self {
        Self::new(
            self.face,
            match self.amount {
                Amount::Clockwise => Amount::Counterclockwise,
                Amount::Half => Amount::Half,
                Amount::Counterclockwise => Amount::Clockwise,
            },
        )
    }
    pub const fn qtm_cost(self) -> u8 {
        match self.amount {
            Amount::Half => 2,
            _ => 1,
        }
    }
    /// Legacy B and D quarter turns run opposite to standard Singmaster.
    pub const fn legacy_to_standard(self) -> Self {
        match self.face {
            Face::B | Face::D => self.inverse(),
            _ => self,
        }
    }
    pub const ALL: [Self; 18] = {
        let mut result = [Self::clockwise(Face::U); 18];
        let mut i = 0;
        while i < 6 {
            result[3 * i] = Self::new(Face::ALL[i], Amount::Clockwise);
            result[3 * i + 1] = Self::new(Face::ALL[i], Amount::Half);
            result[3 * i + 2] = Self::new(Face::ALL[i], Amount::Counterclockwise);
            i += 1;
        }
        result
    };
}

impl fmt::Display for Move {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}{}",
            self.face,
            match self.amount {
                Amount::Clockwise => "",
                Amount::Half => "2",
                Amount::Counterclockwise => "'",
            }
        )
    }
}

impl FromStr for Move {
    type Err = String;
    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let face = match value.as_bytes().first() {
            Some(b'U') => Face::U,
            Some(b'R') => Face::R,
            Some(b'F') => Face::F,
            Some(b'D') => Face::D,
            Some(b'L') => Face::L,
            Some(b'B') => Face::B,
            _ => {
                return Err(format!(
                    "invalid move {value:?}; expected U R F D L B with optional 2 or '"
                ));
            }
        };
        let amount = match value.get(1..) {
            Some("") => Amount::Clockwise,
            Some("2") => Amount::Half,
            Some("'") => Amount::Counterclockwise,
            _ => return Err(format!("invalid move {value:?}")),
        };
        Ok(Self::new(face, amount))
    }
}

pub fn parse_moves(sequence: &str) -> Result<Vec<Move>, String> {
    sequence.split_whitespace().map(str::parse).collect()
}

pub const fn coordinates(cell: u8) -> [i8; 3] {
    [
        (cell % 3) as i8 - 1,
        1 - ((cell / 3) % 3) as i8,
        1 - (cell / 9) as i8,
    ]
}

pub const fn cell_at(p: [i8; 3]) -> u8 {
    ((1 - p[2]) * 9 + (1 - p[1]) * 3 + p[0] + 1) as u8
}

pub const fn rotate_vector(p: [i8; 3], face: Face) -> [i8; 3] {
    // Clockwise as viewed from outside: -90 degrees around the outward normal.
    let n = face.normal();
    let dot = p[0] * n[0] + p[1] * n[1] + p[2] * n[2];
    [
        n[0] * dot - (n[1] * p[2] - n[2] * p[1]),
        n[1] * dot - (n[2] * p[0] - n[0] * p[2]),
        n[2] * dot - (n[0] * p[1] - n[1] * p[0]),
    ]
}

pub const fn destination(cell: u8, movement: Move) -> u8 {
    if !movement.face.contains(cell) {
        return cell;
    }
    let mut p = coordinates(cell);
    let mut i = 0;
    while i < movement.amount as u8 {
        p = rotate_vector(p, movement.face);
        i += 1;
    }
    cell_at(p)
}

/// Axis-major adjacency order: strides 9, 3, 1; ascending source cell per axis.
pub const BONDS: [[u8; 2]; 54] = {
    let mut result = [[0; 2]; 54];
    let strides = [9, 3, 1];
    let mut axis = 0;
    let mut bond = 0;
    while axis < 3 {
        let mut cell = 0;
        while cell < 27 {
            if (cell / strides[axis]) % 3 < 2 {
                result[bond] = [cell, cell + strides[axis]];
                bond += 1;
            }
            cell += 1;
        }
        axis += 1;
    }
    result
};

pub const fn bond_index(a: u8, b: u8) -> usize {
    let mut i = 0;
    while i < 54 {
        if (BONDS[i][0] == a && BONDS[i][1] == b) || (BONDS[i][0] == b && BONDS[i][1] == a) {
            return i;
        }
        i += 1;
    }
    panic!("cells are not adjacent")
}

pub const CORNER_CELLS: [u8; 8] = [8, 6, 0, 2, 26, 24, 18, 20];
pub const EDGE_CELLS: [u8; 12] = [5, 7, 3, 1, 23, 25, 21, 19, 17, 15, 9, 11];
pub const CORNER_FACES: [[Face; 3]; 8] = [
    [Face::U, Face::R, Face::F],
    [Face::U, Face::F, Face::L],
    [Face::U, Face::L, Face::B],
    [Face::U, Face::B, Face::R],
    [Face::D, Face::F, Face::R],
    [Face::D, Face::L, Face::F],
    [Face::D, Face::B, Face::L],
    [Face::D, Face::R, Face::B],
];
pub const EDGE_FACES: [[Face; 2]; 12] = [
    [Face::U, Face::R],
    [Face::U, Face::F],
    [Face::U, Face::L],
    [Face::U, Face::B],
    [Face::D, Face::R],
    [Face::D, Face::F],
    [Face::D, Face::L],
    [Face::D, Face::B],
    [Face::F, Face::R],
    [Face::F, Face::L],
    [Face::B, Face::L],
    [Face::B, Face::R],
];
