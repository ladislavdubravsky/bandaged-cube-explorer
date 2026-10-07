use crate::{
    AxisMajor, BondShape, Error, Face, Move, Partition,
    geometry::{CORNER_CELLS, CORNER_FACES, EDGE_CELLS, EDGE_FACES},
    symmetry::Rotation,
};
use std::fmt::Write;

include!(concat!(env!("OUT_DIR"), "/colored_tables.rs"));

// Standard URFDLB facelet order: each face is read row by row while viewed
// from outside the cube. Entries follow the matching CORNER/EDGE_FACES order.
const CORNER_FACELETS: [[usize; 3]; 8] = [
    [8, 9, 20],
    [6, 18, 38],
    [0, 36, 47],
    [2, 45, 11],
    [29, 26, 15],
    [27, 44, 24],
    [33, 53, 42],
    [35, 17, 51],
];
const EDGE_FACELETS: [[usize; 2]; 12] = [
    [5, 10],
    [7, 19],
    [3, 37],
    [1, 46],
    [32, 16],
    [28, 25],
    [30, 43],
    [34, 52],
    [23, 12],
    [21, 41],
    [50, 39],
    [48, 14],
];

/// Standard fixed-center cube state, using Kociemba corner/edge ordering.
/// Center markings and center spin are deliberately outside this model.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct CubeState {
    corners: [u8; 8],
    twists: [u8; 8],
    edges: [u8; 12],
    flips: [u8; 12],
}

impl CubeState {
    pub const SOLVED: Self = Self {
        corners: [0, 1, 2, 3, 4, 5, 6, 7],
        twists: [0; 8],
        edges: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        flips: [0; 12],
    };
    pub fn try_new(
        corners: [u8; 8],
        twists: [u8; 8],
        edges: [u8; 12],
        flips: [u8; 12],
    ) -> Result<Self, Error> {
        let value = Self {
            corners,
            twists,
            edges,
            flips,
        };
        value.validate()?;
        Ok(value)
    }
    pub const fn corners(&self) -> &[u8; 8] {
        &self.corners
    }
    pub const fn twists(&self) -> &[u8; 8] {
        &self.twists
    }
    pub const fn edges(&self) -> &[u8; 12] {
        &self.edges
    }
    pub const fn flips(&self) -> &[u8; 12] {
        &self.flips
    }
    pub fn is_solved(&self) -> bool {
        *self == Self::SOLVED
    }

    /// Import exactly 54 uppercase URFDLB facelets in standard face order.
    /// Centers must match the fixed reference frame. Ordinary cube invariants
    /// are checked here; a bandage specification validates rigid blocks later.
    pub fn from_facelets(facelets: &str) -> Result<Self, Error> {
        let facelets = facelets.as_bytes();
        if facelets.len() != 54 {
            return Err(Error::InvalidColoredState("expected exactly 54 facelets"));
        }
        let mut counts = [0; 6];
        for &color in facelets {
            let Some(index) = b"URFDLB".iter().position(|&candidate| candidate == color) else {
                return Err(Error::InvalidColoredState(
                    "facelets must use uppercase URFDLB colors",
                ));
            };
            counts[index] += 1;
        }
        if counts != [9; 6] {
            return Err(Error::InvalidColoredState(
                "each facelet color must appear nine times",
            ));
        }
        for face in Face::ALL {
            if facelets[face.index() * 9 + 4] != face.symbol() as u8 {
                return Err(Error::InvalidColoredState(
                    "center colors do not match the fixed URFDLB frame",
                ));
            }
        }
        let mut result = Self::SOLVED;
        for (slot, indices) in CORNER_FACELETS.into_iter().enumerate() {
            let found = (0..8).find_map(|piece| {
                (0..3).find_map(|twist| {
                    (0..3)
                        .all(|sticker| {
                            facelets[indices[(sticker + twist) % 3]]
                                == CORNER_FACES[piece][sticker].symbol() as u8
                        })
                        .then_some((piece as u8, twist as u8))
                })
            });
            let Some((piece, twist)) = found else {
                return Err(Error::InvalidColoredState(
                    "unrecognized or mirrored corner colors",
                ));
            };
            result.corners[slot] = piece;
            result.twists[slot] = twist;
        }
        for (slot, indices) in EDGE_FACELETS.into_iter().enumerate() {
            let found = (0..12).find_map(|piece| {
                (0..2).find_map(|flip| {
                    (0..2)
                        .all(|sticker| {
                            facelets[indices[(sticker + flip) % 2]]
                                == EDGE_FACES[piece][sticker].symbol() as u8
                        })
                        .then_some((piece as u8, flip as u8))
                })
            });
            let Some((piece, flip)) = found else {
                return Err(Error::InvalidColoredState("unrecognized edge colors"));
            };
            result.edges[slot] = piece;
            result.flips[slot] = flip;
        }
        result.validate()?;
        Ok(result)
    }

    /// Export 54 uppercase facelets in standard fixed-center URFDLB order.
    pub fn to_facelets(&self) -> String {
        let mut facelets = [b'U'; 54];
        for face in Face::ALL {
            facelets[face.index() * 9 + 4] = face.symbol() as u8;
        }
        for (slot, indices) in CORNER_FACELETS.into_iter().enumerate() {
            for sticker in 0..3 {
                facelets[indices[(sticker + self.twists[slot] as usize) % 3]] =
                    CORNER_FACES[self.corners[slot] as usize][sticker].symbol() as u8;
            }
        }
        for (slot, indices) in EDGE_FACELETS.into_iter().enumerate() {
            for sticker in 0..2 {
                facelets[indices[(sticker + self.flips[slot] as usize) % 2]] =
                    EDGE_FACES[self.edges[slot] as usize][sticker].symbol() as u8;
            }
        }
        facelets.into_iter().map(char::from).collect()
    }

    pub fn validate(&self) -> Result<(), Error> {
        fn valid<const N: usize>(values: &[u8; N]) -> bool {
            let mut used = [false; N];
            for &v in values {
                if v as usize >= N || used[v as usize] {
                    return false;
                }
                used[v as usize] = true;
            }
            true
        }
        fn parity(values: &[u8]) -> usize {
            values
                .iter()
                .enumerate()
                .map(|(i, v)| values[i + 1..].iter().filter(|w| *w < v).count())
                .sum::<usize>()
                % 2
        }
        let reason = if !valid(&self.corners) || !valid(&self.edges) {
            Some("duplicate or out-of-range cubie identity")
        } else if self.twists.iter().any(|&o| o >= 3) || self.flips.iter().any(|&o| o >= 2) {
            Some("orientation out of range")
        } else if self.twists.iter().sum::<u8>() % 3 != 0 {
            Some("corner twist sum is not zero modulo three")
        } else if self.flips.iter().sum::<u8>() % 2 != 0 {
            Some("edge flip sum is odd")
        } else if parity(&self.corners) != parity(&self.edges) {
            Some("corner and edge permutation parities differ")
        } else {
            None
        };
        reason.map_or(Ok(()), |reason| Err(Error::InvalidColoredState(reason)))
    }

    /// Ordinary-cube move; bandage legality is checked by BandagedState.
    pub fn turn(self, movement: Move) -> Self {
        let mut result = self;
        let index = movement.index();
        for source in 0..8 {
            let dest = CORNER_DEST[index][source] as usize;
            result.corners[dest] = self.corners[source];
            result.twists[dest] = (self.twists[source] + CORNER_DELTA[index][source]) % 3;
        }
        for source in 0..12 {
            let dest = EDGE_DEST[index][source] as usize;
            result.edges[dest] = self.edges[source];
            result.flips[dest] = self.flips[source] ^ EDGE_DELTA[index][source];
        }
        result
    }

    /// Reference home-cell identity at every current cell; centers/core are fixed.
    pub fn piece_cells(&self) -> [u8; 27] {
        let mut result = std::array::from_fn(|i| i as u8);
        for (slot, cell) in CORNER_CELLS.into_iter().enumerate() {
            result[cell as usize] = CORNER_CELLS[self.corners[slot] as usize];
        }
        for (slot, cell) in EDGE_CELLS.into_iter().enumerate() {
            result[cell as usize] = EDGE_CELLS[self.edges[slot] as usize];
        }
        result
    }
}

/// Immutable membership by solved home-cell identity, including the virtual core.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BandageSpec {
    home: Partition,
}

impl BandageSpec {
    pub const fn new(home: Partition) -> Self {
        Self { home }
    }
    pub const fn home(&self) -> &Partition {
        &self.home
    }
    pub fn solved_state(&self) -> BandagedState {
        BandagedState {
            spec: *self,
            cube: CubeState::SOLVED,
            shape: BondShape::from_partition(&self.home),
        }
    }

    /// Import an ordinary-cube state whose bandage members form rigid blocks.
    ///
    /// Every block must have one proper spatial rotation carrying all its home
    /// positions and colored sticker directions to their current values. This
    /// includes singleton and noncuboid blocks. Centers have fixed positions
    /// and unmarked stickers (normal only); the virtual core has no orientation.
    ///
    /// This checks geometric compatibility, not reachability by legal turns.
    /// A constrained solver must determine reachability separately.
    pub fn state_from_cube(&self, cube: CubeState) -> Result<BandagedState, Error> {
        cube.validate()?;
        let partition = self.shape_from_cube(&cube)?;
        let pieces = cube.piece_cells();
        let mut current = [0u8; 27];
        for (cell, piece) in pieces.into_iter().enumerate() {
            current[piece as usize] = cell as u8;
        }
        for block in self.home.footprints() {
            let rigid = Rotation::ALL.into_iter().any(|rotation| {
                (0..27)
                    .filter(|&home| block & (1 << home) != 0)
                    .all(|home| {
                        let cell = current[home];
                        if rotation.map_cell(home as u8) != cell {
                            return false;
                        }
                        if let Some(piece) = CORNER_CELLS.iter().position(|&c| c as usize == home) {
                            // The cell map already guarantees that `cell` is a corner.
                            let slot = CORNER_CELLS.iter().position(|&c| c == cell).unwrap();
                            (0..3).all(|sticker| {
                                rotation.map_face(CORNER_FACES[piece][sticker])
                                    == CORNER_FACES[slot]
                                        [(sticker + cube.twists[slot] as usize) % 3]
                            })
                        } else if let Some(piece) =
                            EDGE_CELLS.iter().position(|&c| c as usize == home)
                        {
                            let slot = EDGE_CELLS.iter().position(|&c| c == cell).unwrap();
                            (0..2).all(|sticker| {
                                rotation.map_face(EDGE_FACES[piece][sticker])
                                    == EDGE_FACES[slot][(sticker + cube.flips[slot] as usize) % 2]
                            })
                        } else {
                            // Center position equals its sticker normal; preserving
                            // that position imposes precisely the unmarked-center
                            // constraint. A fixed core imposes no spin constraint.
                            true
                        }
                    })
            });
            if !rigid {
                return Err(Error::InvalidBandagedState(
                    "block positions or sticker orientations do not share one proper rotation",
                ));
            }
        }
        Ok(BandagedState {
            spec: *self,
            cube,
            shape: BondShape::from_partition(&partition),
        })
    }

    fn shape_from_cube(&self, cube: &CubeState) -> Result<Partition, Error> {
        let cells = cube.piece_cells();
        Partition::from_legacy(std::array::from_fn(|cell| {
            self.home.labels()[cells[cell] as usize]
        }))
    }
}

/// A colored state compatible with its immutable rigid-block specification.
/// Owns its specification so it can outlive the value used to construct it.
/// Imported states are geometrically valid but are not assumed reachable.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BandagedState {
    spec: BandageSpec,
    cube: CubeState,
    shape: BondShape,
}

impl BandagedState {
    pub const fn specification(&self) -> &BandageSpec {
        &self.spec
    }
    pub const fn cube(&self) -> &CubeState {
        &self.cube
    }
    pub const fn shape(&self) -> BondShape {
        self.shape
    }

    /// Stable, collision-free identifier for the fixed reference bandages and
    /// complete colored state, independent of replay witnesses and graph IDs.
    ///
    /// The format is exactly 54 lowercase hexadecimal characters: 14 for the
    /// home partition's AxisMajor bond bits (fixed frame, without rotation
    /// canonicalization), then eight bytes `3 * corner + twist` and twelve
    /// bytes `2 * edge + flip`, in Kociemba slot order. Block label names and
    /// the engine's optimized bond layout do not affect the identifier.
    pub fn hex_id(&self) -> String {
        let home = BondShape::<AxisMajor>::from_partition(self.spec.home());
        let mut result = String::with_capacity(54);
        write!(result, "{:014x}", home.bits()).unwrap();
        for (&corner, &twist) in self.cube.corners.iter().zip(&self.cube.twists) {
            write!(result, "{:02x}", 3 * corner + twist).unwrap();
        }
        for (&edge, &flip) in self.cube.edges.iter().zip(&self.cube.flips) {
            write!(result, "{:02x}", 2 * edge + flip).unwrap();
        }
        result
    }

    pub fn is_turnable(&self, face: Face) -> bool {
        self.shape.is_turnable(face)
    }
    pub fn try_turn(&mut self, movement: Move) -> Result<(), Error> {
        let shape = self.shape.try_turn(movement)?;
        self.cube = self.cube.turn(movement);
        self.shape = shape;
        debug_assert_eq!(
            self.spec.shape_from_cube(&self.cube),
            Ok(self.shape.to_partition())
        );
        Ok(())
    }
    pub fn check_shape(&self) -> bool {
        self.spec.shape_from_cube(&self.cube) == Ok(self.shape.to_partition())
    }
}
