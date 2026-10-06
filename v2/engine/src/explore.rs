//! Exhaustive shape BFS, retaining distinct labeled arcs and self-loops.
//! Exploration runs to exhaustion unless a vertex limit is explicitly requested.
use crate::{Amount, BondLayout, BondShape, Move};
use std::collections::HashMap;

/// Cost convention for shortest shape paths.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Metric {
    /// Quarter turns and inverse quarter turns cost one; half turns cost two.
    Qtm,
    /// Every outer-face move, including a half turn, costs one.
    Htm,
}

impl Metric {
    fn exploration_moves(self) -> impl Iterator<Item = Move> {
        Move::ALL
            .into_iter()
            .filter(move |movement| self == Self::Htm || movement.amount == Amount::Clockwise)
    }

    fn unit_moves(self) -> impl Iterator<Item = Move> {
        Move::ALL
            .into_iter()
            .filter(move |movement| self == Self::Htm || movement.amount != Amount::Half)
    }
}

#[derive(Debug)]
pub struct ShapeGraph<L: BondLayout> {
    pub vertices: Vec<BondShape<L>>,
    /// QTM stores clockwise actions, whose reverse traversal is an inverse turn.
    /// HTM stores all 18 directed move actions.
    pub arcs: Vec<(usize, usize, Move)>,
    pub metric: Metric,
    /// Whether the entire reachable shape component was explored.
    pub complete: bool,
}

/// Explore the entire reachable shape component in QTM, without a vertex limit.
pub fn explore<L: BondLayout>(initial: BondShape<L>) -> ShapeGraph<L> {
    explore_with_options(initial, Metric::Qtm, None)
}

/// Explore in QTM with an explicit positive vertex limit.
///
/// If an additional vertex is reachable beyond the limit, the returned graph
/// has `complete == false`. Its counts and distances describe only that partial
/// graph; reaching the limit exactly does not imply an incomplete search.
pub fn explore_with_limit<L: BondLayout>(
    initial: BondShape<L>,
    max_vertices: usize,
) -> ShapeGraph<L> {
    explore_with_options(initial, Metric::Qtm, Some(max_vertices))
}

/// Explore with an explicit metric and an optional positive vertex limit.
/// QTM preserves the six clockwise arcs per shape used by the legacy baselines;
/// HTM retains every legal quarter, inverse, and half-turn action.
pub fn explore_with_options<L: BondLayout>(
    initial: BondShape<L>,
    metric: Metric,
    max_vertices: Option<usize>,
) -> ShapeGraph<L> {
    assert!(max_vertices != Some(0), "vertex limit must be positive");
    let mut vertices = vec![initial];
    let mut ids = HashMap::from([(initial, 0)]);
    let mut arcs = Vec::new();
    let mut cursor = 0;
    let mut complete = true;
    while cursor < vertices.len() {
        let shape = vertices[cursor];
        for movement in metric.exploration_moves() {
            if let Ok(next) = shape.try_turn(movement) {
                let target = if let Some(&id) = ids.get(&next) {
                    id
                } else {
                    if max_vertices == Some(vertices.len()) {
                        complete = false;
                        continue;
                    }
                    let id = vertices.len();
                    ids.insert(next, id);
                    vertices.push(next);
                    id
                };
                arcs.push((cursor, target, movement));
            }
        }
        cursor += 1;
    }
    ShapeGraph {
        vertices,
        arcs,
        metric,
        complete,
    }
}

impl<L: BondLayout> ShapeGraph<L> {
    /// Distances in this graph's declared metric. Unreachable vertices are None.
    /// An invalid start ID returns None for every vertex.
    /// For incomplete exploration, paths stay within the represented vertices.
    pub fn distances(&self, start: usize) -> Vec<Option<usize>> {
        self.traverse(start, self.metric, |_, _, _| true)
    }

    /// Explicit QTM distances, independently of the graph's declared metric.
    /// For incomplete exploration, quarter turns must stay within the represented
    /// vertices, even when a legal HTM half turn could skip an omitted shape.
    pub fn qtm_distances(&self, start: usize) -> Vec<Option<usize>> {
        self.traverse(start, Metric::Qtm, |_, _, _| true)
    }

    /// A shortest executable move sequence in the graph's declared metric.
    /// Returns None for an invalid ID or an unreachable target. A path from a
    /// vertex to itself is empty. Incomplete graphs only use represented vertices.
    pub fn shortest_path(&self, start: usize, target: usize) -> Option<Vec<Move>> {
        if start >= self.vertices.len() || target >= self.vertices.len() {
            return None;
        }
        if start == target {
            return Some(Vec::new());
        }
        let mut predecessors = vec![None; self.vertices.len()];
        self.traverse(start, self.metric, |source, next, movement| {
            predecessors[next] = Some((source, movement));
            next != target
        });
        let mut path = Vec::new();
        let mut cursor = target;
        while cursor != start {
            let (previous, movement) = predecessors[cursor]?;
            path.push(movement);
            cursor = previous;
        }
        path.reverse();
        Some(path)
    }

    fn traverse(
        &self,
        start: usize,
        metric: Metric,
        mut discover: impl FnMut(usize, usize, Move) -> bool,
    ) -> Vec<Option<usize>> {
        let mut distances = vec![None; self.vertices.len()];
        if start >= self.vertices.len() {
            return distances;
        }
        let ids: HashMap<_, _> = self
            .vertices
            .iter()
            .copied()
            .enumerate()
            .map(|(id, shape)| (shape, id))
            .collect();
        distances[start] = Some(0);
        let mut queue = vec![start];
        let mut cursor = 0;
        while cursor < queue.len() {
            let vertex = queue[cursor];
            let shape = self.vertices[vertex];
            for movement in metric.unit_moves() {
                let Ok(next_shape) = shape.try_turn(movement) else {
                    continue;
                };
                let Some(&next) = ids.get(&next_shape) else {
                    continue;
                };
                if distances[next].is_none() {
                    distances[next] = Some(distances[vertex].unwrap() + 1);
                    if !discover(vertex, next, movement) {
                        return distances;
                    }
                    queue.push(next);
                }
            }
            cursor += 1;
        }
        distances
    }
}
