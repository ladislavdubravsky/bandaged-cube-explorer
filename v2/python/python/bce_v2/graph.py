"""Ergonomic graph access; search remains in the Rust library."""

import json
from pathlib import Path

from . import Shape, shape


class ShapeGraph:
    """A labeled shape graph with stable dense vertex IDs for this exploration."""

    __slots__ = ("_native", "_shapes")

    def __init__(self, native):
        self._native = native
        self._shapes = None

    @property
    def shapes(self):
        if self._shapes is None:
            self._shapes = tuple(Shape(value) for value in self._native.shapes)
        return self._shapes

    @property
    def arcs(self):
        """Stored (source ID, target ID, move) actions, including self-loops."""
        return self._native.arcs

    @property
    def complete(self):
        return self._native.complete

    @property
    def metric(self):
        return self._native.metric

    def __len__(self):
        return len(self._native)

    def __iter__(self):
        return iter(self.shapes)

    def __getitem__(self, vertex):
        return self.shapes[vertex]

    def vertex_id(self, value):
        return self._native.vertex_id(shape(value)._native)

    def _vertex(self, value):
        if isinstance(value, bool):
            raise TypeError("a vertex must be an integer ID or shape")
        if isinstance(value, int):
            if not 0 <= value < len(self):
                raise IndexError("vertex ID out of range")
            return value
        return self.vertex_id(value)

    def distances(self, start=0):
        """Distances indexed by vertex ID; None means no retained path."""
        return self._native.distances(self._vertex(start))

    def shortest_path(self, source, target=0):
        """A checked executable move string between vertex IDs or shapes."""
        return self._native.shortest_path(self._vertex(source), self._vertex(target))

    def isotropy_loops(self, root=0):
        """Extract faithful witnessed generators; requires a complete graph."""
        from .isotropy import isotropy_loops
        return isotropy_loops(self, root=self._vertex(root))

    def to_networkx(self, *, undirected=False):
        """Build an optional NetworkX view of this graph.

        The default MultiDiGraph preserves distinct move actions and supplies
        inverse traversals. The undirected Graph is a distance/statistics view
        in the declared metric; its edges do not represent individual actions.
        """
        try:
            import networkx as nx
        except ImportError as error:
            raise ImportError("install bandaged-cube-explorer-v2[graph] to use NetworkX") from error
        graph = nx.Graph() if undirected else nx.MultiDiGraph()
        graph.graph.update(metric=self.metric, complete=self.complete,
                           model="full-grid-27-fixed-centers", symmetry="none")
        graph.add_nodes_from((i, {"shape": value}) for i, value in enumerate(self.shapes))
        for source, target, movement in self.arcs:
            graph.add_edge(source, target, **({} if undirected else {"key": movement, "move": movement}))
            if not undirected and self.metric == "QTM":
                inverse = movement if movement.endswith("2") else (
                    movement[:-1] if movement.endswith("'") else movement + "'")
                graph.add_edge(target, source, key=inverse, move=inverse)
        return graph

    def to_dict(self):
        """A versioned deterministic export, preserving the native arc records."""
        return {
            "format": "bce-v2-shape-graph", "version": 1,
            "model": "full-grid-27-fixed-centers", "notation": "Singmaster",
            "metric": self.metric, "symmetry": "none", "complete": self.complete,
            "shapes": [value.labels for value in self.shapes],
            "arcs": [list(arc) for arc in self.arcs],
        }

    def to_json(self, path=None):
        result = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(result, encoding="utf-8")
        return result

    def save(self, path):
        self.to_json(path)
        return self.to_dict()
