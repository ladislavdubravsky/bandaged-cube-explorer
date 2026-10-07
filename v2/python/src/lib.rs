//! Python bindings for immutable shapes, complete colored states, and shape search.
//!
//! Python supplies experiment inputs and consumes results. Exploration and graph
//! searches execute entirely in Rust while detached from the Python interpreter.

use std::{
    collections::HashMap,
    hash::{Hash, Hasher},
};

use bandaged_cube_engine::{
    BandageSpec, BandagedState, BondShape, CubeState, DefaultLayout, Error, Face, Move, Partition,
    colored_search::{ColoredGraph, SearchAlgorithm, SearchOptions, SearchStatus},
    enumeration::{CuboidFamily, EnumerationModel, ScanOptions},
    explore::{Metric, ShapeGraph, explore_with_options},
    fixtures,
    implicit::{CoreBonds, implicit_closure},
    parse_moves,
    symmetry::{Rotation, canonical_key, canonicalize, rotate},
};
use pyo3::{
    exceptions::PyValueError,
    prelude::*,
    types::{PyDict, PyList},
};

pyo3::create_exception!(_native, BlockedMoveError, PyValueError);

fn input_error(error: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(error.to_string())
}

fn engine_error(error: Error) -> PyErr {
    match error {
        Error::Blocked(_) => BlockedMoveError::new_err(error.to_string()),
        _ => input_error(error),
    }
}

fn partition(labels: Vec<u8>) -> PyResult<Partition> {
    let count = labels.len();
    let labels = labels
        .try_into()
        .map_err(|_| input_error(format!("expected 27 cell labels, received {count}")))?;
    Partition::from_legacy(labels).map_err(engine_error)
}

fn face(value: &str) -> PyResult<Face> {
    Face::ALL
        .into_iter()
        .find(|face| value.len() == 1 && value.starts_with(face.symbol()))
        .ok_or_else(|| input_error("expected one face: U, R, F, D, L, or B"))
}

fn legal_moves(shape: BondShape) -> Vec<String> {
    Move::ALL
        .into_iter()
        .filter(|movement| shape.is_turnable(movement.face))
        .map(|movement| movement.to_string())
        .collect()
}

/// A canonical connected bandage partition; every zero is a separate singleton.
#[pyclass(
    name = "Shape",
    module = "bce_v2._native",
    frozen,
    eq,
    hash,
    skip_from_py_object
)]
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
struct PyShape {
    inner: BondShape,
}

#[pymethods]
impl PyShape {
    #[new]
    fn new(labels: Vec<u8>) -> PyResult<Self> {
        Ok(Self {
            inner: BondShape::from_partition(&partition(labels)?),
        })
    }

    #[getter]
    fn labels<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        PyList::new(py, self.inner.to_partition().labels().iter().copied())
    }

    #[getter]
    fn legal_moves(&self) -> Vec<String> {
        legal_moves(self.inner)
    }

    fn is_turnable(&self, face: &str) -> PyResult<bool> {
        Ok(self.inner.is_turnable(crate::face(face)?))
    }

    /// Apply a standard outer-face sequence, returning a new shape atomically.
    fn apply(&self, moves: &str) -> PyResult<Self> {
        let movements = parse_moves(moves).map_err(input_error)?;
        let mut inner = self.inner;
        for movement in movements {
            inner = inner.try_turn(movement).map_err(engine_error)?;
        }
        Ok(Self { inner })
    }

    #[getter]
    fn rotation_key(&self) -> String {
        format!("{:014x}", canonical_key(self.inner))
    }

    fn canonical(&self) -> Self {
        Self {
            inner: canonicalize(self.inner).0.reencode(),
        }
    }

    fn rotated(&self, rotation: usize) -> PyResult<Self> {
        let rotation = Rotation::ALL
            .get(rotation)
            .copied()
            .ok_or_else(|| input_error("rotation index must be in 0..24"))?;
        Ok(Self {
            inner: rotate(self.inner, rotation),
        })
    }

    fn __repr__(&self) -> String {
        format!("Shape({:?})", self.inner.to_partition().labels())
    }
}

/// A fixed-center colored cube tied to immutable solved bandage membership.
#[pyclass(
    name = "State",
    module = "bce_v2._native",
    frozen,
    eq,
    hash,
    skip_from_py_object
)]
#[derive(Clone, PartialEq, Eq)]
struct PyState {
    inner: BandagedState,
}

impl Hash for PyState {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.inner.specification().home().hash(state);
        self.inner.cube().hash(state);
    }
}

#[pymethods]
impl PyState {
    #[new]
    fn new(labels: Vec<u8>) -> PyResult<Self> {
        Ok(Self {
            inner: BandageSpec::new(partition(labels)?).solved_state(),
        })
    }

    #[staticmethod]
    fn from_cubies(
        labels: Vec<u8>,
        corners: Vec<u8>,
        twists: Vec<u8>,
        edges: Vec<u8>,
        flips: Vec<u8>,
    ) -> PyResult<Self> {
        fn array<const N: usize>(values: Vec<u8>, name: &str) -> PyResult<[u8; N]> {
            values
                .try_into()
                .map_err(|_| input_error(format!("{name} requires {N} entries")))
        }
        let cube = CubeState::try_new(
            array(corners, "corners")?,
            array(twists, "twists")?,
            array(edges, "edges")?,
            array(flips, "flips")?,
        )
        .map_err(engine_error)?;
        Ok(Self {
            inner: BandageSpec::new(partition(labels)?)
                .state_from_cube(cube)
                .map_err(engine_error)?,
        })
    }

    #[staticmethod]
    fn from_facelets(labels: Vec<u8>, facelets: &str) -> PyResult<Self> {
        let cube = CubeState::from_facelets(facelets).map_err(engine_error)?;
        Ok(Self {
            inner: BandageSpec::new(partition(labels)?)
                .state_from_cube(cube)
                .map_err(engine_error)?,
        })
    }

    #[getter]
    fn facelets(&self) -> String {
        self.inner.cube().to_facelets()
    }

    #[getter]
    fn hex_id(&self) -> String {
        self.inner.hex_id()
    }

    #[getter]
    fn shape(&self) -> PyShape {
        PyShape {
            inner: self.inner.shape(),
        }
    }

    #[getter]
    fn specification(&self) -> PyShape {
        PyShape {
            inner: BondShape::from_partition(self.inner.specification().home()),
        }
    }

    #[getter]
    fn corners<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        PyList::new(py, self.inner.cube().corners().iter().copied())
    }

    #[getter]
    fn twists<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        PyList::new(py, self.inner.cube().twists().iter().copied())
    }

    #[getter]
    fn edges<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        PyList::new(py, self.inner.cube().edges().iter().copied())
    }

    #[getter]
    fn flips<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        PyList::new(py, self.inner.cube().flips().iter().copied())
    }

    #[getter]
    fn is_solved(&self) -> bool {
        self.inner.cube().is_solved()
    }

    #[getter]
    fn legal_moves(&self) -> Vec<String> {
        legal_moves(self.inner.shape())
    }

    fn is_turnable(&self, face: &str) -> PyResult<bool> {
        Ok(self.inner.is_turnable(crate::face(face)?))
    }

    /// Replay legal turns with full cubie identities and orientations retained.
    fn apply(&self, moves: &str) -> PyResult<Self> {
        let movements = parse_moves(moves).map_err(input_error)?;
        let mut inner = self.inner;
        for movement in movements {
            inner.try_turn(movement).map_err(engine_error)?;
        }
        Ok(Self { inner })
    }

    fn __repr__(&self) -> String {
        format!(
            "State(shape={:?}, corners={:?}, twists={:?}, edges={:?}, flips={:?})",
            self.inner.shape().to_partition().labels(),
            self.inner.cube().corners(),
            self.inner.cube().twists(),
            self.inner.cube().edges(),
            self.inner.cube().flips(),
        )
    }
}

fn search_metric(metric: &str) -> PyResult<Metric> {
    match metric.to_ascii_uppercase().as_str() {
        "QTM" => Ok(Metric::Qtm),
        "HTM" => Ok(Metric::Htm),
        _ => Err(input_error("metric must be QTM or HTM")),
    }
}

fn move_string(path: Vec<Move>) -> String {
    path.into_iter()
        .map(|movement| movement.to_string())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Exact shortest colored solution, retaining explicit cutoff outcomes.
#[pyfunction]
#[pyo3(signature = (state, target = None, metric = "QTM", algorithm = "bidirectional",
                    max_states = None, max_depth = None))]
fn solve_colored<'py>(
    py: Python<'py>,
    state: &PyState,
    target: Option<&PyState>,
    metric: &str,
    algorithm: &str,
    max_states: Option<usize>,
    max_depth: Option<usize>,
) -> PyResult<Bound<'py, PyDict>> {
    let metric = search_metric(metric)?;
    let algorithm = match algorithm.to_ascii_lowercase().as_str() {
        "bfs" => SearchAlgorithm::Bfs,
        "bidirectional" => SearchAlgorithm::Bidirectional,
        _ => return Err(input_error("algorithm must be bfs or bidirectional")),
    };
    positive_limit(max_states, "max_states")?;
    let initial = state.inner;
    let target = target.map(|value| value.inner);
    let result = py
        .detach(|| {
            bandaged_cube_engine::colored_search::solve(
                initial,
                target,
                SearchOptions {
                    metric,
                    algorithm,
                    max_states,
                    max_depth,
                },
            )
        })
        .map_err(input_error)?;
    let output = PyDict::new(py);
    output.set_item(
        "status",
        match result.status {
            SearchStatus::Solved => "solved",
            SearchStatus::Unreachable => "unreachable",
            SearchStatus::LimitReached => "limit_reached",
        },
    )?;
    output.set_item("solution", result.solution.map(move_string))?;
    output.set_item("distance", result.distance)?;
    output.set_item("visited", result.visited)?;
    output.set_item("expanded", result.expanded)?;
    output.set_item("stop_reason", result.stop_reason)?;
    output.set_item(
        "metric",
        match metric {
            Metric::Qtm => "QTM",
            Metric::Htm => "HTM",
        },
    )?;
    output.set_item(
        "algorithm",
        match algorithm {
            SearchAlgorithm::Bfs => "bfs",
            SearchAlgorithm::Bidirectional => "bidirectional",
        },
    )?;
    output.set_item("optimal", result.status == SearchStatus::Solved)?;
    Ok(output)
}

#[pyclass(name = "ColoredGraph", module = "bce_v2._native", frozen)]
struct PyColoredGraph {
    inner: ColoredGraph,
    ids: HashMap<CubeState, usize>,
}

impl PyColoredGraph {
    fn check_vertex(&self, vertex: usize) -> PyResult<()> {
        if vertex < self.inner.states.len() {
            Ok(())
        } else {
            Err(input_error("vertex ID is outside this colored graph"))
        }
    }
}

#[pymethods]
impl PyColoredGraph {
    fn state(&self, vertex: usize) -> PyResult<PyState> {
        self.check_vertex(vertex)?;
        Ok(PyState {
            inner: self.inner.states[vertex],
        })
    }

    #[getter]
    fn states(&self) -> Vec<PyState> {
        self.inner
            .states
            .iter()
            .map(|&inner| PyState { inner })
            .collect()
    }

    #[getter]
    fn arcs(&self) -> Vec<(usize, usize, String)> {
        self.inner
            .arcs
            .iter()
            .map(|&(source, target, movement)| (source, target, movement.to_string()))
            .collect()
    }

    #[getter]
    fn complete(&self) -> bool {
        self.inner.complete
    }

    #[getter]
    fn metric(&self) -> &'static str {
        match self.inner.metric {
            Metric::Qtm => "QTM",
            Metric::Htm => "HTM",
        }
    }

    fn __len__(&self) -> usize {
        self.inner.states.len()
    }

    fn vertex_id(&self, state: &PyState) -> PyResult<usize> {
        if state.inner.specification() != self.inner.states[0].specification() {
            return Err(input_error("state has a different bandage specification"));
        }
        self.ids
            .get(state.inner.cube())
            .copied()
            .ok_or_else(|| input_error("state is absent from this colored graph"))
    }

    fn distances(&self, py: Python<'_>, start: usize) -> PyResult<Vec<Option<usize>>> {
        self.check_vertex(start)?;
        Ok(py.detach(|| self.inner.distances(start)))
    }

    fn shortest_path(
        &self,
        py: Python<'_>,
        start: usize,
        target: usize,
    ) -> PyResult<Option<String>> {
        self.check_vertex(start)?;
        self.check_vertex(target)?;
        Ok(py
            .detach(|| self.inner.shortest_path(start, target))
            .map(move_string))
    }
}

#[pyfunction]
#[pyo3(signature = (state, metric = "QTM", max_states = None))]
fn explore_colored(
    py: Python<'_>,
    state: &PyState,
    metric: &str,
    max_states: Option<usize>,
) -> PyResult<PyColoredGraph> {
    let metric = search_metric(metric)?;
    positive_limit(max_states, "max_states")?;
    let initial = state.inner;
    py.detach(|| {
        let inner =
            bandaged_cube_engine::colored_search::explore_colored(initial, metric, max_states)
                .map_err(input_error)?;
        let ids = inner
            .states
            .iter()
            .enumerate()
            .map(|(id, state)| (*state.cube(), id))
            .collect();
        Ok(PyColoredGraph { inner, ids })
    })
}

/// A reachable shape component with labeled moves and an explicit search metric.
#[pyclass(name = "ShapeGraph", module = "bce_v2._native", frozen)]
struct PyShapeGraph {
    inner: ShapeGraph<DefaultLayout>,
    ids: HashMap<BondShape, usize>,
}

impl PyShapeGraph {
    fn check_vertex(&self, vertex: usize) -> PyResult<()> {
        if vertex < self.inner.vertices.len() {
            Ok(())
        } else {
            Err(input_error(format!(
                "vertex {vertex} is outside this graph of {} shapes",
                self.inner.vertices.len()
            )))
        }
    }
}

#[pymethods]
impl PyShapeGraph {
    #[getter]
    fn shapes(&self) -> Vec<PyShape> {
        self.inner
            .vertices
            .iter()
            .map(|&inner| PyShape { inner })
            .collect()
    }

    #[getter]
    fn arcs(&self) -> Vec<(usize, usize, String)> {
        self.inner
            .arcs
            .iter()
            .map(|&(source, target, movement)| (source, target, movement.to_string()))
            .collect()
    }

    #[getter]
    fn complete(&self) -> bool {
        self.inner.complete
    }

    #[getter]
    fn metric(&self) -> &'static str {
        match self.inner.metric {
            Metric::Qtm => "QTM",
            Metric::Htm => "HTM",
        }
    }

    fn __len__(&self) -> usize {
        self.inner.vertices.len()
    }

    fn vertex_id(&self, shape: &PyShape) -> PyResult<usize> {
        self.ids
            .get(&shape.inner)
            .copied()
            .ok_or_else(|| input_error("shape is absent from this graph"))
    }

    fn distances(&self, py: Python<'_>, start: usize) -> PyResult<Vec<Option<usize>>> {
        self.check_vertex(start)?;
        Ok(py.detach(|| self.inner.distances(start)))
    }

    fn shortest_path(&self, py: Python<'_>, start: usize, target: usize) -> PyResult<String> {
        self.check_vertex(start)?;
        self.check_vertex(target)?;
        let path = py
            .detach(|| self.inner.shortest_path(start, target))
            .ok_or_else(|| input_error("no path between these vertices in this graph"))?;
        Ok(path
            .into_iter()
            .map(|movement| movement.to_string())
            .collect::<Vec<_>>()
            .join(" "))
    }

    fn __repr__(&self) -> String {
        format!(
            "ShapeGraph(shapes={}, arcs={}, metric={:?}, complete={})",
            self.inner.vertices.len(),
            self.inner.arcs.len(),
            self.metric(),
            self.complete(),
        )
    }
}

/// Explore with a positive optional vertex limit; partial results stay explicit.
#[pyfunction]
#[pyo3(signature = (shape, metric = "QTM", max_vertices = None))]
fn explore(
    py: Python<'_>,
    shape: &PyShape,
    metric: &str,
    max_vertices: Option<usize>,
) -> PyResult<PyShapeGraph> {
    let metric = match metric.to_ascii_uppercase().as_str() {
        "QTM" => Metric::Qtm,
        "HTM" => Metric::Htm,
        _ => return Err(input_error("metric must be QTM or HTM")),
    };
    if max_vertices == Some(0) {
        return Err(input_error("max_vertices must be positive"));
    }
    let initial = shape.inner;
    Ok(py.detach(|| {
        let inner = explore_with_options(initial, metric, max_vertices);
        let ids = inner
            .vertices
            .iter()
            .enumerate()
            .map(|(id, &shape)| (shape, id))
            .collect();
        PyShapeGraph { inner, ids }
    }))
}

#[pyfunction]
fn fixture_names() -> Vec<&'static str> {
    fixtures::legacy()
        .into_iter()
        .map(|entry| entry.name)
        .collect()
}

#[pyfunction]
fn fixture(name: &str) -> PyResult<PyShape> {
    fixtures::legacy()
        .into_iter()
        .find(|entry| entry.name == name)
        .map(|entry| PyShape {
            inner: BondShape::from_partition(&entry.partition),
        })
        .ok_or_else(|| input_error(format!("unknown fixture {name:?}")))
}

fn enumeration_model(core_bonds: bool, strict_core_singleton: bool) -> PyResult<EnumerationModel> {
    if core_bonds && strict_core_singleton {
        return Err(input_error(
            "core_bonds and strict_core_singleton cannot both be true",
        ));
    }
    Ok(if core_bonds {
        EnumerationModel::FullCuboids
    } else if strict_core_singleton {
        EnumerationModel::StrictCoreSingletonCuboids
    } else {
        EnumerationModel::ShellCuboids
    })
}

fn positive_limit(limit: Option<usize>, name: &str) -> PyResult<()> {
    if limit == Some(0) {
        return Err(input_error(format!("{name} must be positive")));
    }
    Ok(())
}

/// Count the entire chosen cuboid family and its proper-rotation orbits.
#[pyfunction]
#[pyo3(signature = (core_bonds = false, strict_core_singleton = false))]
fn count_partitions(
    py: Python<'_>,
    core_bonds: bool,
    strict_core_singleton: bool,
) -> PyResult<Bound<'_, PyDict>> {
    let model = enumeration_model(core_bonds, strict_core_singleton)?;
    let count = py.detach(|| CuboidFamily::new(model).count());
    let result = PyDict::new(py);
    result.set_item("model", model.name())?;
    result.set_item("core_bonds", core_bonds)?;
    result.set_item("strict_core_singleton", strict_core_singleton)?;
    result.set_item("symmetry", "proper-rotations")?;
    result.set_item("partitions", count.partitions)?;
    result.set_item("rotation_classes", count.rotation_classes)?;
    result.set_item("fixed_by_rotation", count.fixed_by_rotation.to_vec())?;
    result.set_item("placements", count.placements)?;
    result.set_item("memo_states", count.memo_states)?;
    Ok(result)
}

/// Collect an explicitly bounded, deterministic prefix of cuboid partitions.
#[pyfunction]
#[pyo3(signature = (limit, core_bonds = false, strict_core_singleton = false))]
fn cuboid_partitions(
    py: Python<'_>,
    limit: usize,
    core_bonds: bool,
    strict_core_singleton: bool,
) -> PyResult<Vec<PyShape>> {
    positive_limit(Some(limit), "limit")?;
    let model = enumeration_model(core_bonds, strict_core_singleton)?;
    Ok(py.detach(|| {
        CuboidFamily::new(model)
            .partitions()
            .take(limit)
            .map(|inner| PyShape { inner })
            .collect()
    }))
}

/// Scan without implicit resource limits; explicit limits return partial reports.
#[pyfunction]
#[pyo3(signature = (core_bonds = false, implicit_bonds = false, max_seeds = None,
                    max_component_vertices = None, strict_core_singleton = false))]
fn enumerate_puzzles(
    py: Python<'_>,
    core_bonds: bool,
    implicit_bonds: bool,
    max_seeds: Option<usize>,
    max_component_vertices: Option<usize>,
    strict_core_singleton: bool,
) -> PyResult<Bound<'_, PyDict>> {
    positive_limit(max_seeds, "max_seeds")?;
    positive_limit(max_component_vertices, "max_component_vertices")?;
    let model = enumeration_model(core_bonds, strict_core_singleton)?;
    let options = ScanOptions {
        implicit_bonds,
        max_seeds,
        max_component_vertices,
    };
    let scan = py.detach(|| {
        bandaged_cube_engine::enumeration::enumerate(&CuboidFamily::new(model), options, |_| {})
    });
    let result = PyDict::new(py);
    result.set_item("model", model.name())?;
    result.set_item("core_bonds", core_bonds)?;
    result.set_item("strict_core_singleton", strict_core_singleton)?;
    result.set_item("implicit_bonds", implicit_bonds)?;
    result.set_item("symmetry", "proper-rotations")?;
    result.set_item("equivalence", "legal-motion-and-rotation")?;
    result.set_item("max_seeds", max_seeds)?;
    result.set_item("max_component_vertices", max_component_vertices)?;
    result.set_item("complete", scan.complete)?;
    result.set_item("stop_reason", scan.stop_reason)?;
    let progress = PyDict::new(py);
    progress.set_item("seeds_scanned", scan.progress.seeds_scanned)?;
    progress.set_item(
        "raw_components_explored",
        scan.progress.raw_components_explored,
    )?;
    progress.set_item(
        "expanded_shape_vertices",
        scan.progress.expanded_shape_vertices,
    )?;
    progress.set_item(
        "raw_rotation_keys_seen",
        scan.progress.raw_rotation_keys_seen,
    )?;
    progress.set_item(
        "closed_rotation_keys_seen",
        scan.progress.closed_rotation_keys_seen,
    )?;
    progress.set_item("classes", scan.progress.classes)?;
    progress.set_item("largest_component", scan.progress.largest_component)?;
    result.set_item("progress", progress)?;
    let representatives = PyList::empty(py);
    for class in scan.representatives {
        let record = PyDict::new(py);
        record.set_item("id", format!("{:014x}", class.representative.bits()))?;
        record.set_item(
            "labels",
            PyList::new(
                py,
                class.representative.to_partition().labels().iter().copied(),
            )?,
        )?;
        record.set_item(
            "seed_labels",
            PyList::new(py, class.seed.to_partition().labels().iter().copied())?,
        )?;
        record.set_item("raw_component_vertices", class.raw_component_vertices)?;
        representatives.append(record)?;
    }
    result.set_item("representatives", representatives)?;
    Ok(result)
}

/// Add every implicit adjacency after complete fixed-frame exploration.
#[pyfunction]
#[pyo3(signature = (shape, core_bonds = false, max_vertices = None))]
fn close_implicit(
    py: Python<'_>,
    shape: &PyShape,
    core_bonds: bool,
    max_vertices: Option<usize>,
) -> PyResult<PyShape> {
    positive_limit(max_vertices, "max_vertices")?;
    let initial = shape.inner;
    let core_bonds = if core_bonds {
        CoreBonds::Include
    } else {
        CoreBonds::Exclude
    };
    py.detach(|| {
        let graph = explore_with_options(initial, Metric::Qtm, max_vertices);
        implicit_closure(&graph, core_bonds)
            .map(|closed| PyShape {
                inner: closed.reference_shape(),
            })
            .map_err(input_error)
    })
}

#[pymodule(gil_used = false)]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyShape>()?;
    module.add_class::<PyState>()?;
    module.add_class::<PyShapeGraph>()?;
    module.add_class::<PyColoredGraph>()?;
    module.add(
        "BlockedMoveError",
        module.py().get_type::<BlockedMoveError>(),
    )?;
    module.add_function(wrap_pyfunction!(explore, module)?)?;
    module.add_function(wrap_pyfunction!(explore_colored, module)?)?;
    module.add_function(wrap_pyfunction!(solve_colored, module)?)?;
    module.add_function(wrap_pyfunction!(fixture_names, module)?)?;
    module.add_function(wrap_pyfunction!(fixture, module)?)?;
    module.add_function(wrap_pyfunction!(count_partitions, module)?)?;
    module.add_function(wrap_pyfunction!(cuboid_partitions, module)?)?;
    module.add_function(wrap_pyfunction!(enumerate_puzzles, module)?)?;
    module.add_function(wrap_pyfunction!(close_implicit, module)?)?;
    Ok(())
}
