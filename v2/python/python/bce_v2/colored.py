"""Results and graph access for exact colored search in the Rust engine."""

from dataclasses import asdict, dataclass
import json
from operator import index
from pathlib import Path

from . import State


@dataclass(frozen=True)
class SearchResult:
    """A shortest solution, an exhaustion proof, or an explicit resource cutoff."""

    status: str
    solution: str | None
    distance: int | None
    visited: int
    expanded: int
    stop_reason: str | None
    metric: str
    algorithm: str
    optimal: bool

    def to_dict(self):
        return asdict(self)


class ColoredGraph:
    """A fixed-specification colored component with all retained unit actions.

    QTM stores quarter and inverse actions; HTM also stores half turns. Vertex
    IDs are local to this exploration; State.hex_id is stable across graphs.
    Graph states have no replay witness;
    shortest_path() supplies executable transports within the retained graph.
    Integer/slice indexing fetches only selected states; states materializes
    the full Python state cache.
    """

    __slots__ = ("_native", "_states")

    def __init__(self, native):
        self._native = native
        self._states = None

    @property
    def states(self):
        if self._states is None:
            self._states = tuple(State._from_native(value, None) for value in self._native.states)
        return self._states

    @property
    def arcs(self):
        return self._native.arcs

    @property
    def metric(self):
        return self._native.metric

    @property
    def complete(self):
        return self._native.complete

    def __len__(self):
        return len(self._native)

    def __iter__(self):
        return iter(self.states)

    def __getitem__(self, vertex):
        if self._states is not None:
            return self._states[vertex]
        if isinstance(vertex, slice):
            return tuple(self[position] for position in range(*vertex.indices(len(self))))
        position = index(vertex)
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError("tuple index out of range")
        return State._from_native(self._native.state(position), None)

    def vertex_id(self, state):
        if not isinstance(state, State):
            raise TypeError("a colored graph vertex requires a State")
        return self._native.vertex_id(state._native)

    def _vertex(self, value):
        if isinstance(value, bool):
            raise TypeError("a vertex must be an integer ID or State")
        if isinstance(value, int):
            if not 0 <= value < len(self):
                raise IndexError("vertex ID out of range")
            return value
        return self.vertex_id(value)

    def distances(self, start=0):
        """Distances in the retained graph; None means no retained path."""
        return self._native.distances(self._vertex(start))

    def shortest_path(self, start=0, target=0):
        """A shortest retained path as a move string, or None if disconnected."""
        return self._native.shortest_path(self._vertex(start), self._vertex(target))

    def to_networkx(self, *, undirected=False):
        """Optional graph adapter; directed actions retain individual move labels."""
        import networkx as nx

        graph = nx.Graph() if undirected else nx.MultiDiGraph()
        graph.graph.update(metric=self.metric, complete=self.complete,
                           model="full-grid-27-fixed-centers", symmetry="none")
        graph.add_nodes_from((i, {"state": value}) for i, value in enumerate(self.states))
        for source, target, movement in self.arcs:
            graph.add_edge(source, target, **({} if undirected else {"key": movement, "move": movement}))
        return graph

    def to_dict(self):
        """Deterministic inspection export; completeness cannot be imported as proof."""
        return {
            "format": "bce-v2-colored-graph", "version": 1,
            "model": "full-grid-27-fixed-centers", "notation": "Singmaster",
            "metric": self.metric, "symmetry": "none", "complete": self.complete,
            "labels": self.states[0].specification.labels,
            "states": [{"corners": state.corners, "twists": state.twists,
                        "edges": state.edges, "flips": state.flips} for state in self.states],
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
