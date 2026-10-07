//! Exact colored-state searches. Every successor is a legal bandaged move.
//!
//! The search key includes cubie identities and orientations. The bandage
//! specification stays fixed throughout a search, so the shape is derived from
//! that key and must not be used as a substitute for it.
use crate::{BandagedState, CubeState, Move, explore::Metric};
use std::collections::{HashMap, VecDeque};

type Traversal = (Vec<Option<usize>>, Vec<Option<(usize, Move)>>);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SearchAlgorithm {
    Bfs,
    Bidirectional,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SearchStatus {
    Solved,
    Unreachable,
    LimitReached,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SearchOptions {
    pub metric: Metric,
    pub algorithm: SearchAlgorithm,
    /// Maximum stored search records, counting both roots in a bidirectional
    /// search. None requests exhaustive search without an implicit state cap.
    pub max_states: Option<usize>,
    /// Maximum total solution distance in the selected metric.
    pub max_depth: Option<usize>,
}

impl Default for SearchOptions {
    fn default() -> Self {
        Self {
            metric: Metric::Qtm,
            algorithm: SearchAlgorithm::Bidirectional,
            max_states: None,
            max_depth: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SearchResult {
    pub status: SearchStatus,
    pub solution: Option<Vec<Move>>,
    pub distance: Option<usize>,
    pub visited: usize,
    pub expanded: usize,
    pub stop_reason: Option<&'static str>,
    pub metric: Metric,
    pub algorithm: SearchAlgorithm,
}

impl SearchResult {
    fn finished(
        options: SearchOptions,
        status: SearchStatus,
        solution: Option<Vec<Move>>,
        visited: usize,
        expanded: usize,
        stop_reason: Option<&'static str>,
    ) -> Self {
        Self {
            status,
            distance: solution.as_ref().map(Vec::len),
            solution,
            visited,
            expanded,
            stop_reason,
            metric: options.metric,
            algorithm: options.algorithm,
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct Node {
    state: BandagedState,
    depth: usize,
    predecessor: Option<(usize, Move)>,
}

fn root(state: BandagedState) -> Node {
    Node {
        state,
        depth: 0,
        predecessor: None,
    }
}

fn path(nodes: &[Node], mut target: usize) -> Vec<Move> {
    let mut result = Vec::with_capacity(nodes[target].depth);
    while let Some((previous, movement)) = nodes[target].predecessor {
        result.push(movement);
        target = previous;
    }
    result.reverse();
    result
}

fn inverse_path(nodes: &[Node], mut target: usize) -> Vec<Move> {
    let mut result = Vec::with_capacity(nodes[target].depth);
    while let Some((previous, movement)) = nodes[target].predecessor {
        result.push(movement.inverse());
        target = previous;
    }
    result
}

/// Find a shortest legal colored solution, or prove that the target is outside
/// the initial state's connected component. None selects the solved state of
/// the initial specification. Both inputs must have the same specification.
///
/// Limits are optional and explicit. A cutoff reports LimitReached, never
/// Unreachable. The state limit counts stored records; bidirectional search
/// requires two records for distinct roots. QTM returns quarter turns only.
pub fn solve(
    initial: BandagedState,
    target: Option<BandagedState>,
    options: SearchOptions,
) -> Result<SearchResult, &'static str> {
    if options.max_states == Some(0) {
        return Err("state limit must be positive");
    }
    let target = target.unwrap_or_else(|| initial.specification().solved_state());
    if initial.specification() != target.specification() {
        return Err("initial and target states have different bandage specifications");
    }
    if initial.cube() == target.cube() {
        return Ok(SearchResult::finished(
            options,
            SearchStatus::Solved,
            Some(Vec::new()),
            1,
            0,
            None,
        ));
    }
    Ok(match options.algorithm {
        SearchAlgorithm::Bfs => bfs(initial, target, options),
        SearchAlgorithm::Bidirectional => bidirectional(initial, target, options),
    })
}

fn bfs(initial: BandagedState, target: BandagedState, options: SearchOptions) -> SearchResult {
    let mut nodes = vec![root(initial)];
    let mut ids = HashMap::from([(*initial.cube(), 0)]);
    let mut cursor = 0;
    while cursor < nodes.len() {
        let source = nodes[cursor];
        for movement in options.metric.unit_moves() {
            let mut next = source.state;
            if next.try_turn(movement).is_err() || ids.contains_key(next.cube()) {
                continue;
            }
            if options.max_depth == Some(source.depth) {
                return SearchResult::finished(
                    options,
                    SearchStatus::LimitReached,
                    None,
                    nodes.len(),
                    cursor + 1,
                    Some("max_depth"),
                );
            }
            if options.max_states == Some(nodes.len()) {
                return SearchResult::finished(
                    options,
                    SearchStatus::LimitReached,
                    None,
                    nodes.len(),
                    cursor + 1,
                    Some("max_states"),
                );
            }
            let id = nodes.len();
            nodes.push(Node {
                state: next,
                depth: source.depth + 1,
                predecessor: Some((cursor, movement)),
            });
            ids.insert(*next.cube(), id);
            if next.cube() == target.cube() {
                return SearchResult::finished(
                    options,
                    SearchStatus::Solved,
                    Some(path(&nodes, id)),
                    nodes.len(),
                    cursor + 1,
                    None,
                );
            }
        }
        cursor += 1;
    }
    SearchResult::finished(
        options,
        SearchStatus::Unreachable,
        None,
        nodes.len(),
        cursor,
        None,
    )
}

fn bidirectional(
    initial: BandagedState,
    target: BandagedState,
    options: SearchOptions,
) -> SearchResult {
    if options.max_states == Some(1) {
        return SearchResult::finished(
            options,
            SearchStatus::LimitReached,
            None,
            1,
            0,
            Some("max_states"),
        );
    }
    let mut forward = vec![root(initial)];
    let mut backward = vec![root(target)];
    let mut forward_ids = HashMap::from([(*initial.cube(), 0)]);
    let mut backward_ids = HashMap::from([(*target.cube(), 0)]);
    let mut forward_frontier = vec![0];
    let mut backward_frontier = vec![0];
    let mut expanded = 0;
    loop {
        let visited = forward.len() + backward.len();
        if forward_frontier.is_empty() || backward_frontier.is_empty() {
            return SearchResult::finished(
                options,
                SearchStatus::Unreachable,
                None,
                visited,
                expanded,
                None,
            );
        }
        // At this boundary, the two visited sets are disjoint complete balls
        // of radii a and b. Thus the shortest distance is greater than a+b.
        // Expanding a whole layer preserves this invariant. The first meeting
        // during the next expansion has distance exactly a+b+1, even when we
        // choose the smaller frontier repeatedly rather than alternating sides.
        let covered_depth =
            forward[forward_frontier[0]].depth + backward[backward_frontier[0]].depth;
        if options
            .max_depth
            .is_some_and(|limit| covered_depth >= limit)
        {
            return SearchResult::finished(
                options,
                SearchStatus::LimitReached,
                None,
                visited,
                expanded,
                Some("max_depth"),
            );
        }
        let from_initial = forward_frontier.len() <= backward_frontier.len();
        let (nodes, ids, frontier, other_nodes, other_ids) = if from_initial {
            (
                &mut forward,
                &mut forward_ids,
                &mut forward_frontier,
                &backward,
                &backward_ids,
            )
        } else {
            (
                &mut backward,
                &mut backward_ids,
                &mut backward_frontier,
                &forward,
                &forward_ids,
            )
        };
        let mut next_frontier = Vec::new();
        for &source_id in frontier.iter() {
            let source = nodes[source_id];
            expanded += 1;
            for movement in options.metric.unit_moves() {
                let mut next = source.state;
                if next.try_turn(movement).is_err() {
                    continue;
                }
                if let Some(&other_id) = other_ids.get(next.cube()) {
                    let mut solution = if from_initial {
                        path(nodes, source_id)
                    } else {
                        path(other_nodes, other_id)
                    };
                    solution.push(if from_initial {
                        movement
                    } else {
                        movement.inverse()
                    });
                    solution.extend(if from_initial {
                        inverse_path(other_nodes, other_id)
                    } else {
                        inverse_path(nodes, source_id)
                    });
                    return SearchResult::finished(
                        options,
                        SearchStatus::Solved,
                        Some(solution),
                        nodes.len() + other_nodes.len(),
                        expanded,
                        None,
                    );
                }
                if ids.contains_key(next.cube()) {
                    continue;
                }
                if options.max_states == Some(nodes.len() + other_nodes.len()) {
                    // A partial layer would invalidate the complete-ball
                    // argument. Return immediately, without claiming a result.
                    return SearchResult::finished(
                        options,
                        SearchStatus::LimitReached,
                        None,
                        nodes.len() + other_nodes.len(),
                        expanded,
                        Some("max_states"),
                    );
                }
                let id = nodes.len();
                nodes.push(Node {
                    state: next,
                    depth: source.depth + 1,
                    predecessor: Some((source_id, movement)),
                });
                ids.insert(*next.cube(), id);
                next_frontier.push(id);
            }
        }
        *frontier = next_frontier;
    }
}

/// An exhaustively explored colored component, or an explicitly bounded part.
#[derive(Debug)]
pub struct ColoredGraph {
    pub states: Vec<BandagedState>,
    /// Every legal directed unit-cost move between represented states,
    /// including parallel actions and self-loops.
    pub arcs: Vec<(usize, usize, Move)>,
    pub metric: Metric,
    pub complete: bool,
}

/// Explore colored states without an implicit cap. A positive explicit cap
/// returns `complete == false` if additional reachable states are omitted.
/// Reaching the cap exactly does not by itself imply incompleteness.
pub fn explore_colored(
    initial: BandagedState,
    metric: Metric,
    max_states: Option<usize>,
) -> Result<ColoredGraph, &'static str> {
    if max_states == Some(0) {
        return Err("state limit must be positive");
    }
    let mut states = vec![initial];
    let mut ids = HashMap::<CubeState, usize>::from([(*initial.cube(), 0)]);
    let mut arcs = Vec::new();
    let mut cursor = 0;
    let mut complete = true;
    while cursor < states.len() {
        let state = states[cursor];
        for movement in metric.unit_moves() {
            let mut next = state;
            if next.try_turn(movement).is_err() {
                continue;
            }
            let target = if let Some(&id) = ids.get(next.cube()) {
                id
            } else {
                if max_states == Some(states.len()) {
                    complete = false;
                    continue;
                }
                let id = states.len();
                ids.insert(*next.cube(), id);
                states.push(next);
                id
            };
            arcs.push((cursor, target, movement));
        }
        cursor += 1;
    }
    Ok(ColoredGraph {
        states,
        arcs,
        metric,
        complete,
    })
}

impl ColoredGraph {
    /// Shortest distances using this graph's stored directed move actions.
    /// Invalid start IDs return None throughout; partial graphs stay inside the
    /// represented states.
    pub fn distances(&self, start: usize) -> Vec<Option<usize>> {
        self.traverse(start).0
    }

    pub fn shortest_path(&self, start: usize, target: usize) -> Option<Vec<Move>> {
        if start >= self.states.len() || target >= self.states.len() {
            return None;
        }
        let (distances, predecessors) = self.traverse(start);
        distances[target]?;
        let mut result = Vec::with_capacity(distances[target].unwrap());
        let mut cursor = target;
        while cursor != start {
            let (previous, movement) = predecessors[cursor]?;
            result.push(movement);
            cursor = previous;
        }
        result.reverse();
        Some(result)
    }

    fn traverse(&self, start: usize) -> Traversal {
        let mut distances = vec![None; self.states.len()];
        let mut predecessors = vec![None; self.states.len()];
        if start >= self.states.len() {
            return (distances, predecessors);
        }
        let mut adjacency = vec![Vec::new(); self.states.len()];
        for &(source, target, movement) in &self.arcs {
            adjacency[source].push((target, movement));
        }
        distances[start] = Some(0);
        let mut queue = VecDeque::from([start]);
        while let Some(source) = queue.pop_front() {
            for &(target, movement) in &adjacency[source] {
                if distances[target].is_none() {
                    distances[target] = Some(distances[source].unwrap() + 1);
                    predecessors[target] = Some((source, movement));
                    queue.push_back(target);
                }
            }
        }
        (distances, predecessors)
    }
}
