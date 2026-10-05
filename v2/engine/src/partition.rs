use crate::{
    Error, Face, Move,
    geometry::{BONDS, destination},
};

/// Connected partition of all 27 cells, with canonical labels 1..=block_count.
/// The virtual core is retained; cuboid blocks are not required.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Partition([u8; 27]);

impl Partition {
    /// Every input zero is an independent singleton, as in the legacy format.
    pub fn from_legacy(input: [u8; 27]) -> Result<Self, Error> {
        let mut labels = [0; 27];
        let mut assigned = [0; 256];
        let mut next = 1;
        for (cell, value) in input.into_iter().enumerate() {
            if value == 0 {
                labels[cell] = next;
                next += 1;
            } else {
                if assigned[value as usize] == 0 {
                    assigned[value as usize] = next;
                    next += 1;
                }
                labels[cell] = assigned[value as usize];
            }
        }
        let result = Self(labels);
        result.validate_connectivity()?;
        Ok(result)
    }

    pub fn singletons() -> Self {
        Self(std::array::from_fn(|i| i as u8 + 1))
    }
    pub fn fully_bandaged() -> Self {
        Self([1; 27])
    }
    pub const fn labels(&self) -> &[u8; 27] {
        &self.0
    }
    pub fn block_count(&self) -> usize {
        *self.0.iter().max().unwrap() as usize
    }

    pub fn footprints(&self) -> Vec<u32> {
        let mut blocks = vec![0; self.block_count()];
        for (cell, block) in self.0.into_iter().enumerate() {
            blocks[block as usize - 1] |= 1 << cell;
        }
        blocks
    }

    fn validate_connectivity(&self) -> Result<(), Error> {
        for (block, mask) in self.footprints().into_iter().enumerate() {
            let mut reached = 1 << mask.trailing_zeros();
            loop {
                let before = reached;
                for [a, b] in BONDS {
                    let pair = (1 << a) | (1 << b);
                    if pair & mask == pair && pair & reached != 0 {
                        reached |= pair;
                    }
                }
                if before == reached {
                    break;
                }
            }
            if reached != mask {
                return Err(Error::DisconnectedBlock(block as u8 + 1));
            }
        }
        Ok(())
    }

    /// Independent reference legality test, without adjacency masks.
    pub fn is_turnable(&self, face: Face) -> bool {
        let mut inside = [false; 28];
        let mut outside = [false; 28];
        for cell in 0..27 {
            let block = self.0[cell] as usize;
            if face.contains(cell as u8) {
                inside[block] = true;
            } else {
                outside[block] = true;
            }
        }
        !(1..=self.block_count()).any(|block| inside[block] && outside[block])
    }

    pub fn try_turn(&self, movement: Move) -> Result<Self, Error> {
        if !self.is_turnable(movement.face) {
            return Err(Error::Blocked(movement.face));
        }
        let mut result = [0; 27];
        for cell in 0..27 {
            result[destination(cell, movement) as usize] = self.0[cell as usize];
        }
        // A legal rigid turn preserves connectivity; only label names change.
        let mut remap = [0; 28];
        let mut next = 1;
        for value in &mut result {
            if remap[*value as usize] == 0 {
                remap[*value as usize] = next;
                next += 1;
            }
            *value = remap[*value as usize];
        }
        Ok(Self(result))
    }
}
