use crate::{Error, Face, Move, Partition, geometry::BONDS};
use std::marker::PhantomData;

mod sealed {
    pub trait Sealed {}
}

/// A compile-time encoding of all 54 bonds. Raw words are layout-specific.
pub trait BondLayout:
    sealed::Sealed + Copy + Eq + std::hash::Hash + std::fmt::Debug + 'static
{
    /// Human-readable layout name.
    const NAME: &'static str;
    /// Bit position in the raw word for each bond in `geometry::BONDS` order.
    const POSITIONS: [u8; 54];
    /// Mask of all 54 assigned bit positions; all other bits must be zero.
    const USED_MASK: u64;
    /// Bonds crossing each face's layer boundary, indexed by `Face::index`; any set bit blocks a turn.
    const BLOCKERS: [u64; 6];
    /// Bonds wholly inside each rotating face layer, indexed by `Face::index`.
    const MOVING: [u64; 6];
    /// Destination bit position for each bond after each `Move::index`; boundary bonds stay in place.
    const DESTINATIONS: [[u8; 54]; 18];
    /// Number of distinct nonzero bit shifts per `Move::index`; not a CPU instruction count.
    const SHIFT_GROUPS: [usize; 18];
    /// Raw permutation kernel. Boundary bonds must be zero for this face.
    /// This returns a raw word, not a validated shape.
    fn permute(bits: u64, movement: Move) -> u64;
}

include!(concat!(env!("OUT_DIR"), "/bond_tables.rs"));

/// Portable shared-shift layout selected by the initial measured workloads.
pub type DefaultLayout = LegacySparse;

/// Eight-byte shape key. Equality includes the layout at the type level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct BondShape<L: BondLayout = DefaultLayout> {
    bits: u64,
    layout: PhantomData<L>,
}

impl<L: BondLayout> BondShape<L> {
    /// Internal construction after a transformation proven to preserve partitions.
    pub(crate) fn from_valid_bits(bits: u64) -> Self {
        debug_assert!(Self::from_bits(bits).is_ok());
        Self {
            bits,
            layout: PhantomData,
        }
    }

    pub fn from_partition(partition: &Partition) -> Self {
        let mut bits = 0;
        for (i, [a, b]) in BONDS.into_iter().enumerate() {
            if partition.labels()[a as usize] == partition.labels()[b as usize] {
                bits |= 1 << L::POSITIONS[i];
            }
        }
        Self {
            bits,
            layout: PhantomData,
        }
    }

    /// Reject unused bits and unsaturated bond sets (different encodings of one partition).
    pub fn from_bits(bits: u64) -> Result<Self, Error> {
        if bits & !L::USED_MASK != 0 {
            return Err(Error::InvalidBonds);
        }
        let candidate = Self {
            bits,
            layout: PhantomData,
        };
        if Self::from_partition(&candidate.to_partition()).bits != bits {
            return Err(Error::InvalidBonds);
        }
        Ok(candidate)
    }

    pub const fn bits(self) -> u64 {
        self.bits
    }
    #[inline]
    pub fn is_turnable(self, face: Face) -> bool {
        self.bits & L::BLOCKERS[face.index()] == 0
    }
    #[inline]
    pub fn try_turn(self, movement: Move) -> Result<Self, Error> {
        if !self.is_turnable(movement.face) {
            return Err(Error::Blocked(movement.face));
        }
        Ok(Self {
            bits: L::permute(self.bits, movement),
            layout: PhantomData,
        })
    }

    pub fn to_partition(self) -> Partition {
        let mut labels: [u8; 27] = std::array::from_fn(|i| i as u8 + 1);
        for (i, [a, b]) in BONDS.into_iter().enumerate() {
            if self.bits & (1 << L::POSITIONS[i]) != 0 {
                let old = labels[b as usize];
                let new = labels[a as usize];
                for value in &mut labels {
                    if *value == old {
                        *value = new;
                    }
                }
            }
        }
        Partition::from_legacy(labels).expect("components of adjacency bonds are connected")
    }

    /// Explicit encoding conversion; never reinterpret a different layout's bits.
    pub fn reencode<T: BondLayout>(self) -> BondShape<T> {
        let mut bits = 0;
        for i in 0..54 {
            bits |= ((self.bits >> L::POSITIONS[i]) & 1) << T::POSITIONS[i];
        }
        BondShape {
            bits,
            layout: PhantomData,
        }
    }
}
