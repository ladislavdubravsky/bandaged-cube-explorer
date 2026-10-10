//! Root loops in a complete shape graph, with faithful colored actions.
//!
//! A breadth-first spanning tree supplies transports T_v from the selected
//! root. Each non-tree clockwise arc u --a--> v supplies T_u a T_v^-1. These
//! fundamental loops generate every colored action returning to the root
//! shape. Their permutations can be passed to a permutation-group backend
//! without enumerating colored states. Move witnesses expand only on request.

use crate::{
    Amount, BondShape, CubeState, DefaultLayout, Move,
    colored::{CORNER_FACELETS, EDGE_FACELETS},
    explore::{Metric, ShapeGraph},
};
use std::collections::{HashMap, HashSet};

/// A permutation of the 48 non-center facelets in URFDLB row-major order.
///
/// Images are zero-based, omitting each face's center: image[i] is the
/// destination of the sticker whose solved position is i. GAP uses the same
/// source-to-destination convention, with one added to every image.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct StickerPermutation {
    images: [u8; 48],
}

impl StickerPermutation {
    pub const IDENTITY: Self = Self {
        images: [
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
            24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
            46, 47,
        ],
    };

    pub fn try_new(images: [u8; 48]) -> Result<Self, IsotropyError> {
        let mut seen = [false; 48];
        for image in images {
            if image >= 48 || seen[image as usize] {
                return Err(IsotropyError("sticker images must permute 0 through 47"));
            }
            seen[image as usize] = true;
        }
        Ok(Self { images })
    }

    pub const fn images(&self) -> &[u8; 48] {
        &self.images
    }

    /// The unique sticker action specified by this complete cubie state.
    pub fn from_cube(cube: &CubeState) -> Self {
        // Map a 54-facelet index to its compact non-center index.
        fn compact(facelet: usize) -> usize {
            facelet / 9 * 8 + facelet % 9 - usize::from(facelet % 9 > 4)
        }
        let mut result = Self::IDENTITY;
        for (slot, destinations) in CORNER_FACELETS.iter().enumerate() {
            let piece = cube.corners()[slot] as usize;
            for sticker in 0..3 {
                result.images[compact(CORNER_FACELETS[piece][sticker])] =
                    compact(destinations[(sticker + cube.twists()[slot] as usize) % 3]) as u8;
            }
        }
        for (slot, destinations) in EDGE_FACELETS.iter().enumerate() {
            let piece = cube.edges()[slot] as usize;
            for sticker in 0..2 {
                result.images[compact(EDGE_FACELETS[piece][sticker])] =
                    compact(destinations[(sticker + cube.flips()[slot] as usize) % 2]) as u8;
            }
        }
        result
    }

    /// Compose in execution order: perform self, then next.
    pub fn then(self, next: Self) -> Self {
        Self {
            images: std::array::from_fn(|i| next.images[self.images[i] as usize]),
        }
    }

    pub fn inverse(self) -> Self {
        let mut result = Self::IDENTITY;
        for (source, destination) in self.images.into_iter().enumerate() {
            result.images[destination as usize] = source as u8;
        }
        result
    }

    pub fn is_identity(&self) -> bool {
        *self == Self::IDENTITY
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IsotropyError(pub &'static str);

impl std::fmt::Display for IsotropyError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}

impl std::error::Error for IsotropyError {}

/// One fundamental loop, identified by its original graph arc index.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoopGenerator {
    pub id: usize,
    pub source: usize,
    pub target: usize,
    pub permutation: StickerPermutation,
    /// Length of the executable tree-path witness in quarter turns.
    pub qtm_length: usize,
    movement: Move,
}

#[derive(Debug, Clone, Copy)]
struct Parent {
    vertex: usize,
    movement: Move,
}

/// A complete generating family after identity and inverse-duplicate removal.
///
/// This is not yet an algebraically reduced generating set. The private tree
/// occupies O(number of shapes), rather than storing every expanded loop.
#[derive(Debug)]
pub struct LoopGenerators {
    pub root_shape: BondShape<DefaultLayout>,
    pub root_vertex: usize,
    pub shape_count: usize,
    /// Clockwise arcs, even when the input graph uses HTM.
    pub arc_count: usize,
    /// Fundamental loops before removing identity actions or duplicates.
    pub candidate_count: usize,
    /// Fundamental loops with nonidentity action, before duplicate removal.
    pub nonidentity_count: usize,
    /// Ordered by witness length and then original arc ID.
    pub generators: Vec<LoopGenerator>,
    generator_indices: HashMap<usize, usize>,
    parents: Vec<Option<Parent>>,
}

impl LoopGenerators {
    /// Extract a complete isotropy generating family in QTM.
    ///
    /// The input must be the full fixed-frame component. Publicly constructed
    /// graphs are checked for legal, correctly targeted, complete move arcs,
    /// unique vertices, and connectivity. QTM retains clockwise arcs; an HTM
    /// graph's extra actions are validated and then omitted as redundant.
    pub fn from_graph(
        graph: &ShapeGraph<DefaultLayout>,
        root: usize,
    ) -> Result<Self, IsotropyError> {
        validate_graph(graph, root)?;
        let n = graph.vertices.len();
        let mut adjacency = vec![Vec::new(); n];
        let mut arc_count = 0;
        for (id, &(source, target, movement)) in graph.arcs.iter().enumerate() {
            if movement.amount == Amount::Clockwise {
                adjacency[source].push((target, movement, id));
                adjacency[target].push((source, movement.inverse(), id));
                arc_count += 1;
            }
        }
        // Match the engine's standard URFDLB, clockwise/inverse move order.
        for neighbors in &mut adjacency {
            neighbors.sort_unstable_by_key(|&(_, movement, id)| (movement.index(), id));
        }
        let move_actions: [_; 18] = std::array::from_fn(|i| {
            StickerPermutation::from_cube(&CubeState::SOLVED.turn(Move::ALL[i]))
        });
        let mut parents = vec![None; n];
        let mut depths = vec![usize::MAX; n];
        let mut transports = vec![StickerPermutation::IDENTITY; n];
        let mut tree_arcs = vec![false; graph.arcs.len()];
        let mut queue = vec![root];
        depths[root] = 0;
        let mut cursor = 0;
        while cursor < queue.len() {
            let source = queue[cursor];
            for &(target, movement, id) in &adjacency[source] {
                if depths[target] == usize::MAX {
                    parents[target] = Some(Parent {
                        vertex: source,
                        movement,
                    });
                    depths[target] = depths[source] + 1;
                    transports[target] = transports[source].then(move_actions[movement.index()]);
                    tree_arcs[id] = true;
                    queue.push(target);
                }
            }
            cursor += 1;
        }
        if queue.len() != n {
            return Err(IsotropyError(
                "shape graph contains vertices outside the root component",
            ));
        }
        let candidate_count = arc_count + 1 - n;
        let mut nonidentity_count = 0;
        let mut unique: HashMap<StickerPermutation, LoopGenerator> = HashMap::new();
        for (id, &(source, target, movement)) in graph.arcs.iter().enumerate() {
            if movement.amount != Amount::Clockwise || tree_arcs[id] {
                continue;
            }
            let permutation = transports[source]
                .then(move_actions[movement.index()])
                .then(transports[target].inverse());
            if permutation.is_identity() {
                continue;
            }
            nonidentity_count += 1;
            let generator = LoopGenerator {
                id,
                source,
                target,
                permutation,
                qtm_length: depths[source] + 1 + depths[target],
                movement,
            };
            // Canonicalize only the duplicate key. The retained action keeps
            // its original direction, so its witness needs no extra inversion.
            let key = permutation.min(permutation.inverse());
            match unique.entry(key) {
                std::collections::hash_map::Entry::Vacant(entry) => {
                    entry.insert(generator);
                }
                std::collections::hash_map::Entry::Occupied(mut entry) => {
                    let previous = entry.get();
                    if (generator.qtm_length, generator.id) < (previous.qtm_length, previous.id) {
                        entry.insert(generator);
                    }
                }
            }
        }
        let mut generators: Vec<_> = unique.into_values().collect();
        generators.sort_unstable_by_key(|generator| (generator.qtm_length, generator.id));
        let generator_indices = generators
            .iter()
            .enumerate()
            .map(|(index, generator)| (generator.id, index))
            .collect();
        Ok(Self {
            root_shape: graph.vertices[root],
            root_vertex: root,
            shape_count: n,
            arc_count,
            candidate_count,
            nonidentity_count,
            generators,
            generator_indices,
            parents,
        })
    }

    /// Expand a shortest QTM tree transport from the root to a shape vertex.
    pub fn transport(&self, mut vertex: usize) -> Option<Vec<Move>> {
        if vertex >= self.shape_count {
            return None;
        }
        let mut moves = Vec::new();
        while let Some(parent) = self.parents[vertex] {
            moves.push(parent.movement);
            vertex = parent.vertex;
        }
        moves.reverse();
        Some(moves)
    }

    /// Expand the legal root-loop witness of a retained original arc ID.
    pub fn generator_moves(&self, id: usize) -> Option<Vec<Move>> {
        let generator = self
            .generator_indices
            .get(&id)
            .and_then(|&index| self.generators.get(index))
            .filter(|generator| generator.id == id)
            // The public vector can be edited by native callers. Keep that
            // API valid while indexing the normal immutable extracted family.
            .or_else(|| self.generators.iter().find(|generator| generator.id == id))?;
        let mut moves = self.transport(generator.source)?;
        moves.push(generator.movement);
        let mut vertex = generator.target;
        while let Some(parent) = self.parents[vertex] {
            moves.push(parent.movement.inverse());
            vertex = parent.vertex;
        }
        Some(moves)
    }
}

fn validate_graph(graph: &ShapeGraph<DefaultLayout>, root: usize) -> Result<(), IsotropyError> {
    if !graph.complete {
        return Err(IsotropyError(
            "isotropy extraction requires a complete shape graph",
        ));
    }
    if root >= graph.vertices.len() {
        return Err(IsotropyError("root shape vertex is out of range"));
    }
    let mut vertices = HashSet::with_capacity(graph.vertices.len());
    for &shape in &graph.vertices {
        if !vertices.insert(shape) {
            return Err(IsotropyError("shape graph contains duplicate vertices"));
        }
    }
    let mut actions = HashSet::with_capacity(graph.arcs.len());
    for &(source, target, movement) in &graph.arcs {
        if source >= graph.vertices.len() || target >= graph.vertices.len() {
            return Err(IsotropyError("shape arc endpoint is out of range"));
        }
        if graph.metric == Metric::Qtm && movement.amount != Amount::Clockwise {
            return Err(IsotropyError(
                "QTM shape graph must store clockwise arcs only",
            ));
        }
        if graph.vertices[source].try_turn(movement) != Ok(graph.vertices[target]) {
            return Err(IsotropyError(
                "shape arc is blocked or has the wrong target",
            ));
        }
        if !actions.insert((source, movement)) {
            return Err(IsotropyError(
                "shape graph repeats a move arc at one vertex",
            ));
        }
    }
    for (source, &shape) in graph.vertices.iter().enumerate() {
        for movement in Move::ALL {
            if graph.metric == Metric::Qtm && movement.amount != Amount::Clockwise {
                continue;
            }
            if shape.is_turnable(movement.face) && !actions.contains(&(source, movement)) {
                return Err(IsotropyError("shape graph omits a legal move arc"));
            }
        }
    }
    Ok(())
}
