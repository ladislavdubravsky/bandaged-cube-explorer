#![forbid(unsafe_code)]
//! A verified outer-face move engine, retaining the legacy 27-cell geometry.

mod bonds;
mod colored;
pub mod explore;
pub mod fixtures;
pub mod geometry;
mod partition;

pub use bonds::{AxisMajor, BondLayout, BondShape, DefaultLayout, LegacySparse, Tuned};
pub use colored::{BandageSpec, BandagedState, CubeState};
pub use geometry::{Amount, Face, Move, parse_moves};
pub use partition::Partition;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    Blocked(Face),
    DisconnectedBlock(u8),
    InvalidBonds,
    InvalidColoredState(&'static str),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Blocked(face) => write!(f, "{face} is blocked by the bandaging"),
            Self::DisconnectedBlock(block) => {
                write!(f, "block {block} is disconnected in the 27-cell grid")
            }
            Self::InvalidBonds => {
                f.write_str("bond bits are unused or do not encode a closed connected partition")
            }
            Self::InvalidColoredState(reason) => write!(f, "invalid colored cube: {reason}"),
        }
    }
}
impl std::error::Error for Error {}
