//! Exact adjacent implicit bonds over a complete fixed-frame shape component.
//!
//! A missing adjacency is implicit when no legal word ever moves one of its
//! cubies without the other. Mark the adjacencies separated by an immediately
//! legal face turn, then pull those marks backwards through every labeled arc
//! until reaching a fixed point. This includes alternate paths and self-loops:
//! one traversal of an unlabeled shape graph does not retain their transports.

use crate::{BondLayout, BondShape, Error, Face, Move, explore::ShapeGraph, geometry::BONDS};
use std::collections::VecDeque;

/// Whether the virtual core participates in the bandage partition.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum CoreBonds {
    /// The core is an independent ghost cell; only shell adjacencies are added.
    #[default]
    Exclude,
    /// Core-to-center adjacencies may be explicit or implicit bonds.
    Include,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ImplicitClosureError {
    IncompleteGraph,
    EmptyGraph,
    ExplicitCoreBonds,
    InvalidGraph,
    InvalidClosure(Error),
}

impl std::fmt::Display for ImplicitClosureError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::IncompleteGraph => {
                formatter.write_str("implicit bonds require complete exploration")
            }
            Self::EmptyGraph => {
                formatter.write_str("implicit bonds require a nonempty shape graph")
            }
            Self::ExplicitCoreBonds => {
                formatter.write_str("the excluded-core model requires an independent core cell")
            }
            Self::InvalidGraph => {
                formatter.write_str("shape graph arcs do not cover its legal clockwise moves")
            }
            Self::InvalidClosure(error) => {
                write!(formatter, "invalid implicit-bond closure: {error}")
            }
        }
    }
}

impl std::error::Error for ImplicitClosureError {}

/// Closure and separation evidence indexed like the input graph's vertices.
#[derive(Debug)]
pub struct ImplicitClosure<L: BondLayout> {
    /// Connected partitions after adding all admitted implicit adjacencies.
    /// Different original vertices can have the same closed shape.
    pub shapes: Vec<BondShape<L>>,
    /// Bonds for which some legal word separates the endpoints. These masks
    /// include all 54 geometric adjacencies, also in the excluded-core model.
    pub separable_bonds: Vec<u64>,
    pub core_bonds: CoreBonds,
}

impl<L: BondLayout> ImplicitClosure<L> {
    /// The closure of the reference shape used to begin exploration.
    pub fn reference_shape(&self) -> BondShape<L> {
        self.shapes[0]
    }
}

/// Layout-specific mask of the six core-to-center adjacencies.
pub fn core_bond_mask<L: BondLayout>() -> u64 {
    BONDS
        .iter()
        .enumerate()
        .filter(|(_, pair)| pair.contains(&13))
        .fold(0, |mask, (index, _)| mask | (1 << L::POSITIONS[index]))
}

/// Explore without a resource cap and close the reference shape.
pub fn close_implicit<L: BondLayout>(
    initial: BondShape<L>,
    core_bonds: CoreBonds,
) -> Result<BondShape<L>, ImplicitClosureError> {
    if core_bonds == CoreBonds::Exclude && initial.bits() & core_bond_mask::<L>() != 0 {
        return Err(ImplicitClosureError::ExplicitCoreBonds);
    }
    implicit_closure(&crate::explore::explore(initial), core_bonds)
        .map(|closure| closure.reference_shape())
}

/// Compute all adjacent implicit bonds without enumerating colored states.
///
/// Completeness and labeled move coverage are checked before interpreting
/// absent separation evidence. The closed partition preserves every legal
/// word of the original puzzle. In this outer-face model its blocks are cuboid
/// footprints (with the core omitted when excluded); its shape graph can have
/// fewer vertices after newly rigid blocks merge.
pub fn implicit_closure<L: BondLayout>(
    graph: &ShapeGraph<L>,
    core_bonds: CoreBonds,
) -> Result<ImplicitClosure<L>, ImplicitClosureError> {
    if !graph.complete {
        return Err(ImplicitClosureError::IncompleteGraph);
    }
    if graph.vertices.is_empty() {
        return Err(ImplicitClosureError::EmptyGraph);
    }
    let core_mask = core_bond_mask::<L>();
    if core_bonds == CoreBonds::Exclude
        && graph
            .vertices
            .iter()
            .any(|shape| shape.bits() & core_mask != 0)
    {
        return Err(ImplicitClosureError::ExplicitCoreBonds);
    }

    let count = graph.vertices.len();
    let mut predecessors: Vec<Vec<(usize, Move)>> = vec![Vec::new(); count];
    let mut outgoing = vec![0_u32; count];
    for &(source, target, movement) in &graph.arcs {
        if source >= count
            || target >= count
            || graph.vertices[source].try_turn(movement) != Ok(graph.vertices[target])
        {
            return Err(ImplicitClosureError::InvalidGraph);
        }
        predecessors[target].push((source, movement));
        outgoing[source] |= 1 << movement.index();
    }

    let mut separable = vec![0; count];
    for (vertex, &shape) in graph.vertices.iter().enumerate() {
        for face in Face::ALL {
            if shape.is_turnable(face) {
                if outgoing[vertex] & (1 << Move::clockwise(face).index()) == 0 {
                    return Err(ImplicitClosureError::InvalidGraph);
                }
                separable[vertex] |= L::BLOCKERS[face.index()];
            }
        }
    }

    let mut pending: VecDeque<_> = (0..count).collect();
    let mut queued = vec![true; count];
    while let Some(target) = pending.pop_front() {
        queued[target] = false;
        for &(source, movement) in &predecessors[target] {
            // Boundary edges are already marked at every state where this
            // move is legal. Remove them before using the permutation kernel,
            // which only transports edges whose endpoints move together.
            let transported = L::permute(
                separable[target] & !L::BLOCKERS[movement.face.index()],
                movement.inverse(),
            );
            let updated = separable[source] | transported;
            if updated != separable[source] {
                separable[source] = updated;
                if !queued[source] {
                    queued[source] = true;
                    pending.push_back(source);
                }
            }
        }
    }

    let candidates = match core_bonds {
        CoreBonds::Exclude => L::USED_MASK & !core_mask,
        CoreBonds::Include => L::USED_MASK,
    };
    let shapes = graph
        .vertices
        .iter()
        .zip(&separable)
        .map(|(&shape, &bad)| {
            BondShape::<L>::from_bits(shape.bits() | (candidates & !bad))
                .map_err(ImplicitClosureError::InvalidClosure)
        })
        .collect::<Result<_, _>>()?;
    Ok(ImplicitClosure {
        shapes,
        separable_bonds: separable,
        core_bonds,
    })
}
