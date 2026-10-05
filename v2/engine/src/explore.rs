//! Exhaustive shape BFS, retaining distinct labeled arcs and self-loops.
//! Exploration runs to exhaustion unless a vertex limit is explicitly requested.
use crate::{BondLayout, BondShape, Face, Move};
use std::collections::HashMap;

#[derive(Debug)]
pub struct ShapeGraph<L: BondLayout> {
    pub vertices: Vec<BondShape<L>>,
    pub arcs: Vec<(usize, usize, Move)>,
    /// Whether the entire reachable shape component was explored.
    pub complete: bool,
}

/// Explore the entire reachable shape component, without a vertex limit.
pub fn explore<L: BondLayout>(initial: BondShape<L>) -> ShapeGraph<L> {
    explore_inner(initial, None)
}

/// Explore with an explicit positive vertex limit.
///
/// If an additional vertex is reachable beyond the limit, the returned graph
/// has `complete == false`. Its counts and distances describe only that partial
/// graph; reaching the limit exactly does not imply an incomplete search.
pub fn explore_with_limit<L: BondLayout>(
    initial: BondShape<L>,
    max_vertices: usize,
) -> ShapeGraph<L> {
    assert!(max_vertices > 0, "vertex limit must be positive");
    explore_inner(initial, Some(max_vertices))
}

fn explore_inner<L: BondLayout>(
    initial: BondShape<L>,
    max_vertices: Option<usize>,
) -> ShapeGraph<L> {
    let mut vertices = vec![initial];
    let mut ids = HashMap::from([(initial, 0)]);
    let mut arcs = Vec::new();
    let mut cursor = 0;
    let mut complete = true;
    while cursor < vertices.len() {
        let shape = vertices[cursor];
        for face in Face::ALL {
            let movement = Move::clockwise(face);
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
        complete,
    }
}

impl<L: BondLayout> ShapeGraph<L> {
    /// QTM distances: every clockwise arc also supplies an inverse traversal.
    /// For incomplete exploration, these are distances within the partial graph.
    pub fn qtm_distances(&self, start: usize) -> Vec<Option<usize>> {
        let mut adjacency = vec![Vec::new(); self.vertices.len()];
        for &(a, b, _) in &self.arcs {
            adjacency[a].push(b);
            adjacency[b].push(a);
        }
        let mut distances = vec![None; self.vertices.len()];
        distances[start] = Some(0);
        let mut queue = vec![start];
        let mut cursor = 0;
        while cursor < queue.len() {
            let vertex = queue[cursor];
            for &next in &adjacency[vertex] {
                if distances[next].is_none() {
                    distances[next] = Some(distances[vertex].unwrap() + 1);
                    queue.push(next);
                }
            }
            cursor += 1;
        }
        distances
    }
}
