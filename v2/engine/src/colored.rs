use crate::{
    BondShape, Error, Face, Move, Partition,
    geometry::{CORNER_CELLS, EDGE_CELLS},
};

include!(concat!(env!("OUT_DIR"), "/colored_tables.rs"));

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
    fn shape_from_cube(&self, cube: &CubeState) -> Partition {
        let cells = cube.piece_cells();
        Partition::from_legacy(std::array::from_fn(|cell| {
            self.home.labels()[cells[cell] as usize]
        }))
        .expect("a state constructed by legal turns preserves block connectivity")
    }
}

/// Constructed at solved state and advanced only through legal turns.
/// Owns its specification so it can outlive the value used to construct it.
/// Arbitrary colored-state import needs an additional rigid-block validation API.
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
    pub fn is_turnable(&self, face: Face) -> bool {
        self.shape.is_turnable(face)
    }
    pub fn try_turn(&mut self, movement: Move) -> Result<(), Error> {
        let shape = self.shape.try_turn(movement)?;
        self.cube = self.cube.turn(movement);
        self.shape = shape;
        debug_assert_eq!(
            self.spec.shape_from_cube(&self.cube),
            self.shape.to_partition()
        );
        Ok(())
    }
    pub fn check_shape(&self) -> bool {
        self.spec.shape_from_cube(&self.cube) == self.shape.to_partition()
    }
}
