"""Public research workflows, notation, and reproducible export contracts."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import bce_v2 as c
from bce_v2.graphics import _block_faces, _block_mesh
from bce_v2.persistence import puzzle_record, state_from_record


class ResearchTests(unittest.TestCase):
    def test_python_labels_and_named_cells(self):
        labels = [0] * 27
        labels[c.UBL] = labels[c.UB] = 10**30
        value = c.Shape(labels)
        self.assertEqual((c.F, c.DF, c.C), (16, 25, 13))
        self.assertEqual(value[c.UBL], value[c.UB])
        self.assertEqual(len(set(value)), 26)
        self.assertEqual(c.normalize(labels), list(value))
        self.assertEqual(c.normalize([0] * 27), list(range(1, 28)))
        self.assertEqual(value[:3], value.labels[:3])
        self.assertEqual(hash(value), hash(c.Shape(value.labels)))
        copy = value.labels
        copy[0] = 99
        self.assertNotEqual(copy, value.labels)
        with self.assertRaises(AttributeError):
            value._labels = (1,) * 27
        with self.assertRaises(AttributeError):
            del value._labels
        state = c.State(value)
        with self.assertRaises(AttributeError):
            state._moves = ()
        with self.assertRaises(AttributeError):
            del state._native

    def test_invalid_shapes(self):
        with self.assertRaises(ValueError):
            c.Shape([0] * 26)
        for invalid in (True, 1.5, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                c.Shape([invalid] + [0] * 26)
        with self.assertRaises(ValueError):
            c.Shape([-1] + [0] * 26)
        disconnected = [0] * 27
        disconnected[0] = disconnected[26] = 1
        with self.assertRaises(ValueError):
            c.Shape(disconnected)

    def test_fixture_baselines_and_replayable_paths(self):
        expected = {
            "Alcatraz": (1449, 2048, 16),
            "Bicube Fuse": (121, 168, 7),
            "Shark Fin Soup": (1938, 2968, 20),
        }
        self.assertEqual(set(c.fixture_names()), set(expected))
        for name, baseline in expected.items():
            with self.subTest(name=name):
                initial = c.fixture(name)
                graph = c.explore(initial.labels)
                distances = graph.distances(initial)
                self.assertTrue(graph.complete)
                self.assertEqual(graph.metric, "QTM")
                self.assertEqual((len(graph), len(graph.arcs), max(distances)), baseline)
                farthest = distances.index(max(distances))
                for vertex in (0, len(graph) // 2, farthest):
                    path = graph.shortest_path(graph[vertex], initial)
                    self.assertEqual(graph[vertex].apply(path), initial)
                    self.assertEqual(len(path.split()), distances[vertex])
                self.assertEqual(graph.vertex_id(initial), 0)

    def test_standard_back_and_down_directions(self):
        # Standard cubie permutation tables, independent of label normalization.
        back = c.State().apply("B")
        self.assertEqual(back.corners, [0, 1, 3, 7, 4, 5, 2, 6])
        self.assertEqual(back.twists, [0, 0, 1, 2, 0, 0, 2, 1])
        down = c.State().apply("D")
        self.assertEqual(down.corners, [0, 1, 2, 3, 5, 6, 7, 4])
        self.assertEqual(down.twists, [0] * 8)
        self.assertEqual(back.apply("B'").is_solved, True)
        self.assertEqual(down.apply("D'").is_solved, True)

    def test_blocked_replay_is_atomic(self):
        for value in (c.fixture("Alcatraz"), c.State(c.fixture("Alcatraz"))):
            first = value.legal_moves[0]
            after = value.apply(first)
            blocked = next(face for face in "URFDLB" if not after.is_turnable(face))
            original_shape = c.shape(value)
            original_state = value._key() if isinstance(value, c.State) else None
            with self.assertRaises(c.BlockedMoveError):
                value.apply(f"{first} {blocked}")
            self.assertEqual(c.shape(value), original_shape)
            if original_state is not None:
                self.assertEqual(value._key(), original_state)
                self.assertEqual(value.scramble, "")

    def test_unknown_notation_rejected(self):
        for moves in ("R garbage", "x", "M", "R3", "r"):
            with self.subTest(moves=moves), self.assertRaises(ValueError):
                c.do([0] * 27, moves)

    def test_shape_restoration_retains_colors(self):
        initial = c.State()
        scrambled = c.do(initial, "R U")
        graph = c.explore(initial)
        self.assertEqual(len(graph), 1)
        self.assertEqual(len(graph.arcs), 6)
        self.assertEqual(graph.shortest_path(scrambled), "")
        self.assertEqual(scrambled.shape, initial.shape)
        self.assertFalse(scrambled.is_solved)
        self.assertNotEqual(scrambled, initial)
        self.assertEqual(scrambled.apply("U' R'"), initial)
        self.assertEqual(scrambled.specification, initial.specification)
        self.assertEqual(len(scrambled.edges), 12)
        self.assertEqual(len(scrambled.flips), 12)

    def test_copying_a_state_preserves_specification_colors_and_witness(self):
        scrambled = c.State(c.fixture("Alcatraz")).apply("F R2")
        copied = c.State(scrambled)
        self.assertEqual(copied, scrambled)
        self.assertEqual(copied.specification, c.fixture("Alcatraz"))
        self.assertEqual(copied.scramble, "F R2")
        self.assertEqual(copied.corners, scrambled.corners)
        self.assertEqual(copied.twists, scrambled.twists)

    def test_qtm_and_htm_half_turn_costs(self):
        labels = [0] * 27
        labels[0] = labels[1] = 1
        initial = c.Shape(labels)
        target = initial.apply("U2")
        for metric, expected in (("QTM", 2), ("HTM", 1)):
            with self.subTest(metric=metric):
                graph = c.explore(initial, metric=metric)
                vertex = graph.vertex_id(target)
                self.assertEqual(graph.distances()[vertex], expected)
                path = graph.shortest_path(initial, target)
                self.assertEqual(initial.apply(path), target)
                self.assertEqual(len(path.split()), expected)

    def test_limits_and_graph_input_validation(self):
        graph = c.explore(c.fixture("Alcatraz"), max_vertices=3)
        self.assertFalse(graph.complete)
        self.assertEqual(len(graph), 3)
        self.assertTrue(all(a < 3 and b < 3 for a, b, _ in graph.arcs))
        self.assertTrue(c.explore(c.Shape(), max_vertices=1).complete)
        with self.assertRaises(ValueError):
            c.explore(c.Shape(), max_vertices=0)
        with self.assertRaises(ValueError):
            c.explore(c.Shape(), max_vertices=-1)
        for invalid in (True, 1.5, "3"):
            with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                c.explore(c.Shape(), max_vertices=invalid)
        with self.assertRaises(ValueError):
            c.explore(c.Shape(), metric="unknown")
        with self.assertRaises(IndexError):
            graph.shortest_path(-1)
        with self.assertRaises(IndexError):
            graph.distances(len(graph))
        with self.assertRaises(TypeError):
            graph.shortest_path(True)
        with self.assertRaises(ValueError):
            graph.vertex_id(c.Shape())

    def test_puzzle_persistence_preserves_colored_replay(self):
        state = c.State(c.fixture("Alcatraz")).apply("F R2")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "puzzle.json"
            record = c.save_puzzle(state, path, name="experiment", metric="HTM")
            first = path.read_bytes()
            loaded = c.load_puzzle(path)
            self.assertEqual(loaded, state)
            self.assertEqual(loaded.scramble, "F R2")
            self.assertEqual(record["labels"], state.specification.labels)
            self.assertEqual(record["metric"], "HTM")
            c.save_puzzle(loaded, path, name="experiment", metric="HTM")
            self.assertEqual(first, path.read_bytes())
            c.save_puzzle(state.shape, path)
            self.assertEqual(c.load_puzzle(path).shape, state.shape)
            self.assertTrue(c.load_puzzle(path).is_solved)

    def test_invalid_puzzle_records_rejected(self):
        record = puzzle_record(c.Shape())
        for field, value in (("version", 2), ("version", True), ("model", "shell-26"),
                             ("symmetry", "rotations"), ("notation", "legacy"),
                             ("metric", "unknown"), ("labels", [0] * 27),
                             ("scramble", "R invalid"), ("scramble", ["R"]),
                             ("name", 42)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                state_from_record({**record, field: value})
        with self.assertRaises(ValueError):
            state_from_record({**record, "complete": True})
        blocked = puzzle_record(c.Shape([1] * 27))
        with self.assertRaises(c.BlockedMoveError):
            state_from_record({**blocked, "scramble": "R"})

    def test_deterministic_graph_export_preserves_actions(self):
        for metric, count in (("QTM", 6), ("HTM", 18)):
            with self.subTest(metric=metric):
                graph = c.explore(c.Shape(), metric=metric)
                record = json.loads(graph.to_json())
                self.assertEqual(record["arcs"], [list(arc) for arc in graph.arcs])
                self.assertEqual(len(record["arcs"]), count)
                self.assertEqual(record["model"], "full-grid-27-fixed-centers")
                self.assertEqual(record["notation"], "Singmaster")
                self.assertEqual(record["symmetry"], "none")
                self.assertTrue(record["complete"])
                self.assertEqual(graph.to_json(), c.explore(c.Shape(), metric=metric).to_json())
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "graph.json"
                    self.assertEqual(graph.save(path), graph.to_dict())
                    self.assertEqual(path.read_text(), graph.to_json())
        partial = c.explore(c.fixture("Alcatraz"), max_vertices=2)
        self.assertFalse(partial.to_dict()["complete"])

    def test_noncuboid_surface_mesh(self):
        # Three fused cells form an L; the fourth cell of its box remains absent.
        indices = [0, 1, 3]
        self.assertEqual(len(list(_block_faces(indices))), 14)
        faces, _ = _block_mesh(indices, transparent=True)
        self.assertEqual(len(faces), 14)
        # Opaque views include only the three exterior faces facing the fixed
        # camera. Rear/bottom outlines must not show through the white surfaces.
        faces, outlines = _block_mesh(range(27), transparent=False)
        self.assertEqual(len(faces), 27)
        self.assertEqual(len(outlines), 27)
        planes = {(axis, face[0][axis]) for face in faces for axis in range(3)
                  if len({vertex[axis] for vertex in face}) == 1}
        self.assertEqual(planes, {(0, 3), (1, 0), (2, 3)})

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "optional plots extra")
    def test_matplotlib_gallery(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = [0] * 27
        labels[0] = labels[1] = labels[3] = 1
        figure = c.draw_cubes([c.Shape(labels), c.State()], alpha=0.3, ncol=2)
        self.assertEqual(len(figure.axes), 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gallery.png"
            figure.savefig(path)
            self.assertGreater(path.stat().st_size, 1000)
        plt.close(figure)

    @unittest.skipUnless(importlib.util.find_spec("networkx"), "optional graph extra")
    def test_networkx_views(self):
        import networkx as nx
        for metric in ("QTM", "HTM"):
            graph = c.explore(c.Shape(), metric=metric)
            directed = graph.to_networkx()
            self.assertIsInstance(directed, nx.MultiDiGraph)
            self.assertEqual(directed.number_of_edges(), 12 if metric == "QTM" else 18)
            self.assertEqual(directed[0][0]["R"]["move"], "R")
            self.assertEqual(directed[0][0]["R'"]["move"], "R'")
        graph = c.explore(c.fixture("Bicube Fuse"))
        projection = graph.to_networkx(undirected=True)
        reference = nx.single_source_shortest_path_length(projection, 0)
        self.assertEqual(graph.distances(), [reference[i] for i in range(len(graph))])


if __name__ == "__main__":
    unittest.main()
