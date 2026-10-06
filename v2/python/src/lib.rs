//! Python bindings for immutable shapes, complete colored states, and shape search.
//!
//! Python supplies experiment inputs and consumes results. Exploration and graph
//! searches execute entirely in Rust while detached from the Python interpreter.

use std::{
    collections::HashMap,
    hash::{Hash, Hasher},
};

use bandaged_cube_engine::{
    BandageSpec, BandagedState, BondShape, DefaultLayout, Error, Face, Move, Partition,
    explore::{Metric, ShapeGraph, explore_with_options},
    fixtures, parse_moves,
};
use pyo3::{exceptions::PyValueError, prelude::*, types::PyList};

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

#[pymodule(gil_used = false)]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyShape>()?;
    module.add_class::<PyState>()?;
    module.add_class::<PyShapeGraph>()?;
    module.add(
        "BlockedMoveError",
        module.py().get_type::<BlockedMoveError>(),
    )?;
    module.add_function(wrap_pyfunction!(explore, module)?)?;
    module.add_function(wrap_pyfunction!(fixture_names, module)?)?;
    module.add_function(wrap_pyfunction!(fixture, module)?)?;
    Ok(())
}
