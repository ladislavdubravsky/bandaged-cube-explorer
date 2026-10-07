"""Colored imports and exact constrained search through the public API.

The one-face puzzle has a four-state colored component but only one shape.
It supplies a small exhaustive oracle without relying on the search engine.
"""

from collections import deque
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

import bce_v2 as c
from bce_v2.__main__ import main
from bce_v2.persistence import puzzle_record, state_from_record


SOLVED_FACELETS = "".join(face * 9 for face in "URFDLB")
R_FACELETS = "UUF" * 3 + "R" * 9 + "FFD" * 3 + "DDB" * 3 + "L" * 9 + "UBB" * 3


def one_face_puzzle():
    # The entire lower two layers form one block anchored to the virtual core.
    return c.Shape([0] * 9 + [1] * 18)


def imported(state, **overrides):
    arrays = {name: getattr(state, name) for name in ("corners", "twists", "edges", "flips")}
    arrays.update(overrides)
    return c.State.from_cubies(state.specification, **arrays)


def unit_moves(state, metric):
    suffixes = ("", "'") if metric == "QTM" else ("", "'", "2")
    return [face + suffix for face in "URFDLB" if state.is_turnable(face)
            for suffix in suffixes]


def shallow_oracle(initial, metric, depth):
    """Independent Python BFS using only checked State transitions."""
    records = {initial: (0, "")}
    queue = deque([initial])
    while queue:
        current = queue.popleft()
        distance, witness = records[current]
        if distance == depth:
            continue
        for move in unit_moves(current, metric):
            after = current.apply(move)
            if after not in records:
                records[after] = distance + 1, (witness + " " + move).strip()
                queue.append(after)
    return records


class ColoredImportTests(unittest.TestCase):
    def test_hex_id_encodes_reference_membership_and_full_colored_state(self):
        solved = c.State()
        self.assertEqual(solved.hex_id, "00000000000000" + "000306090c0f1215"
                         + "00020406080a0c0e10121416")
        replayed = c.State(c.fixture("Alcatraz")).apply("F R2")
        self.assertRegex(replayed.hex_id, r"^[0-9a-f]{54}$")
        self.assertEqual(imported(replayed).hex_id, replayed.hex_id)
        self.assertEqual(c.State.from_facelets(replayed.facelets, replayed).hex_id,
                         replayed.hex_id)

        twisted = imported(solved, twists=[1, 2] + [0] * 6)
        flipped = imported(solved, flips=[1, 1] + [0] * 10)
        for state in (twisted, flipped):
            self.assertEqual(state.corners, solved.corners)
            self.assertEqual(state.edges, solved.edges)
            self.assertEqual(state.shape, solved.shape)
        self.assertEqual(len({solved.hex_id, twisted.hex_id, flipped.hex_id}), 3)

        labels = [0] * 27
        labels[c.UBL] = labels[c.UB] = 1
        same_membership = labels.copy()
        same_membership[c.UBL] = same_membership[c.UB] = 10**30
        bandaged = c.State(c.Shape(labels))
        self.assertNotEqual(bandaged.hex_id, solved.hex_id)
        self.assertEqual(bandaged.hex_id, c.State(c.Shape(same_membership)).hex_id)

    def test_standard_facelets_and_ordinary_roundtrips(self):
        self.assertEqual(c.State().facelets, SOLVED_FACELETS)
        self.assertEqual(c.State().apply("R").facelets, R_FACELETS)
        for moves in ("", "R", "F R U2 B' L D2", "R U R' U'"):
            with self.subTest(moves=moves):
                replayed = c.State().apply(moves)
                from_cubies = imported(replayed)
                from_facelets = c.State.from_facelets(replayed.facelets)
                self.assertEqual(from_cubies, replayed)
                self.assertEqual(from_facelets, replayed)
                self.assertEqual(from_cubies.facelets, replayed.facelets)
                self.assertIsNone(from_cubies.scramble)
                self.assertIsNone(from_facelets.scramble)
                self.assertIsNone(from_facelets.apply("R").scramble)
                self.assertEqual(from_cubies.apply("R"), replayed.apply("R"))
                self.assertEqual(c.State(from_cubies), replayed)
                self.assertIsNone(c.State(from_cubies).scramble)
                self.assertEqual(hash(from_cubies), hash(replayed))

    def test_named_import_preserves_reference_membership_and_moves(self):
        replayed = c.State(c.fixture("Alcatraz")).apply("F R2")
        for state in (imported(replayed),
                      c.State.from_facelets(replayed.facelets, replayed.specification),
                      c.State.from_facelets(replayed.facelets, replayed),
                      c.State.from_cubies(replayed, corners=replayed.corners,
                                          twists=replayed.twists, edges=replayed.edges,
                                          flips=replayed.flips)):
            with self.subTest(state=state):
                self.assertEqual(state, replayed)
                self.assertEqual(state.shape, replayed.shape)
                self.assertEqual(state.specification, c.fixture("Alcatraz"))
                self.assertEqual(state.legal_moves, replayed.legal_moves)
                self.assertIsNone(state.scramble)
                self.assertTrue(state.apply("R2 F'").is_solved)
                self.assertIsNone(state.apply("R2 F'").scramble)

    def test_ordinary_cube_invalidity_is_rejected(self):
        solved = c.State()
        invalid = (
            {"corners": [0] * 8},
            {"corners": list(range(7)) + [8]},
            {"corners": [1, 0] + list(range(2, 8))},
            {"twists": [1] + [0] * 7},
            {"twists": [3] + [0] * 7},
            {"edges": [0] * 12},
            {"edges": [1, 0] + list(range(2, 12))},
            {"flips": [1] + [0] * 11},
            {"flips": [2] + [0] * 11},
            {"corners": list(range(7))},
            {"flips": [0] * 13},
        )
        for arrays in invalid:
            with self.subTest(arrays=arrays), self.assertRaises(ValueError):
                imported(solved, **arrays)

    def test_cubie_values_require_integer_arrays(self):
        for invalid in (True, 0.5, "0"):
            with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                imported(c.State(), twists=[invalid] + [0] * 7)
        with self.assertRaises(ValueError):
            imported(c.State(), corners=[-1] + list(range(1, 8)))

    def test_facelet_format_and_cube_validity_are_checked(self):
        rotated_centers = list(SOLVED_FACELETS)
        rotated_centers[4], rotated_centers[13] = rotated_centers[13], rotated_centers[4]
        changed_count = "R" + SOLVED_FACELETS[1:]
        for facelets in ("", SOLVED_FACELETS[:-1], SOLVED_FACELETS + "U",
                         "X" + SOLVED_FACELETS[1:], changed_count,
                         "".join(rotated_centers)):
            with self.subTest(facelets=facelets), self.assertRaises(ValueError):
                c.State.from_facelets(facelets)
        with self.assertRaises(TypeError):
            c.State.from_facelets(list(SOLVED_FACELETS))
        # Swap the two stickers of UF: all color counts and fixed centers survive,
        # but a single flipped edge is impossible on an ordinary cube.
        flipped = list(SOLVED_FACELETS)
        flipped[7], flipped[19] = flipped[19], flipped[7]
        with self.assertRaises(ValueError):
            c.State.from_facelets("".join(flipped))

    def test_ordinary_valid_states_must_preserve_rigid_bandages(self):
        turned = c.State().apply("R")
        frozen = c.Shape([1] * 27)
        with self.assertRaises(ValueError):
            c.State.from_facelets(turned.facelets, frozen)
        with self.assertRaises(ValueError):
            c.State.from_cubies(frozen, corners=turned.corners, twists=turned.twists,
                               edges=turned.edges, flips=turned.flips)
        # Positions alone are insufficient: balanced twists preserve the partition
        # and ordinary-cube twist sum, but twist pieces inside the glued cube.
        with self.assertRaises(ValueError):
            imported(c.State(frozen), twists=[1, 2] + [0] * 6)

    def test_persistence_roundtrips_imports_without_inventing_a_witness(self):
        replayed = c.State(c.fixture("Alcatraz")).apply("F R2")
        state = imported(replayed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "imported.json"
            record = c.save_puzzle(state, path, name="imported", metric="HTM")
            self.assertEqual(record["version"], 2)
            self.assertEqual(record["labels"], state.specification.labels)
            first = path.read_bytes()
            loaded = c.load_puzzle(path)
            self.assertEqual(loaded, state)
            self.assertIsNone(loaded.scramble)
            c.save_puzzle(loaded, path, name="imported", metric="HTM")
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(state_from_record(record), state)
            replay_record = puzzle_record(replayed)
            self.assertEqual(replay_record["version"], 1)
            self.assertEqual(replay_record["scramble"], "F R2")
            self.assertEqual(state_from_record(replay_record), replayed)

    def test_imported_persistence_records_validate_their_colored_data(self):
        record = puzzle_record(imported(c.State()))
        cubies = record["cubies"]
        invalid = (
            {**record, "scramble": ""},
            {**record, "version": 1},
            {**record, "cubies": []},
            {**record, "cubies": {**cubies, "extra": []}},
            {**record, "cubies": {**cubies, "corners": [0] * 8}},
            {**record, "cubies": {**cubies, "twists": [True] + [0] * 7}},
            {**record, "cubies": {**cubies, "flips": [1] + [0] * 11}},
        )
        for value in invalid:
            with self.subTest(record=value), self.assertRaises(ValueError):
                state_from_record(value)


class ColoredGraphTests(unittest.TestCase):
    def test_indexing_materializes_only_requested_states(self):
        initial = c.State(one_face_puzzle())
        graph = c.explore_colored(initial)
        first = graph[0]
        last = graph[-1]
        prefix = graph[:2]
        reverse = graph[::-1]
        self.assertIsNone(graph._states)
        self.assertEqual(first, initial)
        self.assertIsInstance(prefix, tuple)
        self.assertEqual(len(prefix), 2)
        self.assertEqual(len(reverse), len(graph))
        self.assertEqual(graph[-len(graph)], first)
        self.assertEqual(graph[False], first)
        for key in (len(graph), -len(graph) - 1):
            with self.subTest(key=key), self.assertRaises(IndexError):
                graph[key]
        for key in (1.5, "0", (0, 1)):
            with self.subTest(key=key), self.assertRaises(TypeError):
                graph[key]
        with self.assertRaises(ValueError):
            graph[::0]
        self.assertIsNone(graph._states)
        states = graph.states
        self.assertEqual(last, states[-1])
        self.assertEqual(prefix, states[:2])
        self.assertEqual(reverse, states[::-1])
        self.assertIs(graph[0], states[0])

    def test_shape_self_loops_retain_four_distinct_colored_states(self):
        initial = c.State(one_face_puzzle())
        self.assertEqual(len(c.explore(initial)), 1)
        for metric, arc_count, distances in (("QTM", 8, [0, 1, 1, 2]),
                                             ("HTM", 12, [0, 1, 1, 1])):
            with self.subTest(metric=metric):
                graph = c.explore_colored(initial, metric=metric)
                self.assertIsInstance(graph, c.ColoredGraph)
                self.assertTrue(graph.complete)
                self.assertEqual(graph.metric, metric)
                self.assertEqual(len(graph), 4)
                self.assertEqual(len(graph.states), 4)
                self.assertEqual(len(set(graph.states)), 4)
                self.assertEqual(len(graph.arcs), arc_count)
                self.assertEqual(sorted(graph.distances()), distances)
                self.assertEqual(graph.vertex_id(initial), 0)
                self.assertEqual(graph[0], initial)
                for source, target, move in graph.arcs:
                    self.assertEqual(graph[source].apply(move), graph[target])
                for vertex, state in enumerate(graph.states):
                    self.assertEqual(state.shape, initial.shape)
                    path = graph.shortest_path(state, initial)
                    self.assertEqual(state.apply(path), initial)
                    self.assertEqual(len(path.split()), graph.distances()[vertex])
                # Hitting the cap exactly must still prove a complete component.
                exact = c.explore_colored(initial, metric=metric, max_states=4)
                self.assertTrue(exact.complete)
                self.assertEqual(exact.to_dict(), graph.to_dict())

    def test_unbandaged_outgoing_actions_preserve_both_quarter_turns(self):
        initial = c.State()
        for metric, count in (("QTM", 12), ("HTM", 18)):
            with self.subTest(metric=metric):
                graph = c.explore_colored(initial, metric=metric, max_states=count + 1)
                self.assertFalse(graph.complete)
                self.assertEqual(len(graph), count + 1)
                outgoing = [(target, move) for source, target, move in graph.arcs if source == 0]
                self.assertEqual({move for _, move in outgoing}, set(unit_moves(initial, metric)))
                self.assertEqual(len(outgoing), count)
                for target, move in outgoing:
                    self.assertEqual(graph[target], initial.apply(move))

    def test_truncated_graph_has_only_valid_retained_arcs(self):
        initial = c.State(one_face_puzzle())
        graph = c.explore_colored(initial, max_states=2)
        self.assertFalse(graph.complete)
        self.assertEqual(len(graph), 2)
        for source, target, move in graph.arcs:
            self.assertLess(source, 2)
            self.assertLess(target, 2)
            self.assertEqual(graph[source].apply(move), graph[target])
        with self.assertRaises(ValueError):
            graph.vertex_id(initial.apply("U2"))

    def test_graph_exports_are_deterministic_and_keep_state_identity(self):
        initial = imported(c.State(one_face_puzzle()).apply("U"))
        graph = c.explore_colored(initial)
        self.assertEqual(graph[0], initial)
        record = graph.to_dict()
        self.assertEqual(record["format"], "bce-v2-colored-graph")
        self.assertEqual(record["metric"], "QTM")
        self.assertEqual(record["symmetry"], "none")
        self.assertEqual(record["model"], "full-grid-27-fixed-centers")
        self.assertTrue(record["complete"])
        self.assertEqual(record["arcs"], [list(arc) for arc in graph.arcs])
        self.assertEqual(json.loads(graph.to_json()), record)
        self.assertEqual(graph.to_json(), c.explore_colored(initial).to_json())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colored.json"
            self.assertEqual(graph.save(path), record)
            self.assertEqual(path.read_text(), graph.to_json())

    def test_graph_lookup_and_options_reject_invalid_values(self):
        graph = c.explore_colored(c.State(one_face_puzzle()))
        with self.assertRaises(ValueError):
            graph.vertex_id(c.State())
        with self.assertRaises(TypeError):
            graph.distances(True)
        with self.assertRaises(IndexError):
            graph.shortest_path(-1)
        with self.assertRaises(IndexError):
            graph.distances(len(graph))
        with self.assertRaises(ValueError):
            c.explore_colored(c.State(), metric="unknown", max_states=1)
        for limit in (0, -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                c.explore_colored(c.State(), max_states=limit)
        for limit in (True, 1.5, "3"):
            with self.subTest(limit=limit), self.assertRaises(TypeError):
                c.explore_colored(c.State(), max_states=limit)


class ColoredSearchTests(unittest.TestCase):
    def assert_solution(self, result, source, target, distance, metric, algorithm):
        self.assertIsInstance(result, c.SearchResult)
        self.assertEqual(result.status, "solved")
        self.assertEqual(result.distance, distance)
        self.assertEqual(source.apply(result.solution), target)
        self.assertEqual(len(result.solution.split()), distance)
        self.assertEqual(result.metric, metric)
        self.assertEqual(result.algorithm, algorithm)
        self.assertTrue(result.optimal)
        self.assertGreaterEqual(result.visited, 1)
        self.assertGreaterEqual(result.expanded, 0)
        self.assertIsNone(result.stop_reason)
        self.assertEqual(result.to_dict()["solution"], result.solution)
        self.assertEqual(result.to_dict()["status"], "solved")

    def test_all_four_states_have_exact_qtm_and_htm_solutions(self):
        initial = c.State(one_face_puzzle())
        for metric in ("QTM", "HTM"):
            oracle = shallow_oracle(initial, metric, 2)
            self.assertEqual(len(oracle), 4)
            for algorithm in ("bfs", "bidirectional"):
                for state, (distance, _) in oracle.items():
                    with self.subTest(metric=metric, algorithm=algorithm, state=state):
                        result = c.solve_colored(imported(state), metric=metric, algorithm=algorithm)
                        self.assert_solution(result, state, initial, distance, metric, algorithm)

    def test_named_legal_scrambles_match_independent_shallow_bfs(self):
        for name in c.fixture_names():
            initial = c.State(c.fixture(name))
            for metric in ("QTM", "HTM"):
                oracle = shallow_oracle(initial, metric, 2)
                # Include different end states from each nonzero depth without
                # making runtime depend on a fixture's branching factor.
                sample = []
                for distance in (1, 2):
                    sample.extend([state for state, record in oracle.items()
                                   if record[0] == distance][:4])
                for state in sample:
                    for algorithm in ("bfs", "bidirectional"):
                        with self.subTest(name=name, metric=metric, algorithm=algorithm,
                                          scramble=state.scramble):
                            result = c.solve_colored(state, metric=metric, algorithm=algorithm,
                                                     max_depth=2)
                            self.assert_solution(result, state, initial, oracle[state][0],
                                                 metric, algorithm)

    def test_exact_non_solved_target_and_zero_depth_identity(self):
        initial = c.State(one_face_puzzle())
        source, target = initial.apply("U"), initial.apply("U2")
        for algorithm in ("bfs", "bidirectional"):
            result = c.solve_colored(source, target=target, algorithm=algorithm)
            self.assert_solution(result, source, target, 1, "QTM", algorithm)
            identity = c.solve_colored(source, target=imported(source), algorithm=algorithm,
                                       max_states=1, max_depth=0)
            self.assert_solution(identity, source, source, 0, "QTM", algorithm)
            self.assertEqual(identity.solution, "")

    def test_limit_results_are_distinct_from_proven_unreachable(self):
        initial = c.State(one_face_puzzle())
        source = initial.apply("U2")
        for algorithm in ("bfs", "bidirectional"):
            for options in ({"max_states": 1}, {"max_depth": 1}, {"max_depth": 0}):
                with self.subTest(algorithm=algorithm, options=options):
                    result = c.solve_colored(source, algorithm=algorithm, **options)
                    self.assertEqual(result.status, "limit_reached")
                    self.assertIsNone(result.solution)
                    self.assertIsNone(result.distance)
                    self.assertIsNotNone(result.stop_reason)
                    self.assertFalse(result.optimal)
                    self.assertGreaterEqual(result.visited, 1)
            reached = c.solve_colored(source, algorithm=algorithm, max_depth=2)
            self.assert_solution(reached, source, initial, 2, "QTM", algorithm)

    def test_valid_colored_state_can_be_proven_unreachable(self):
        initial = c.State(one_face_puzzle())
        # Even corner 3-cycle: ordinary-cube valid, and every fused piece remains
        # fixed. Only U turns are legal, so this is outside the four-state orbit.
        source = imported(initial, corners=[1, 2, 0, 3, 4, 5, 6, 7])
        self.assertFalse(source.is_solved)
        self.assertEqual(source.shape, initial.shape)
        for algorithm in ("bfs", "bidirectional"):
            with self.subTest(algorithm=algorithm):
                result = c.solve_colored(source, algorithm=algorithm)
                self.assertEqual(result.status, "unreachable")
                self.assertIsNone(result.solution)
                self.assertIsNone(result.distance)
                self.assertFalse(result.optimal)
                self.assertIsNone(result.stop_reason)

    def test_frozen_valid_import_is_unreachable_with_one_state(self):
        labels = [0] * 27
        for cell in (c.U, c.R, c.F, c.D, c.L, c.B, c.C):
            labels[cell] = 1
        specification = c.Shape(labels)
        source = c.State.from_facelets(R_FACELETS, specification)
        self.assertFalse(source.is_solved)
        self.assertEqual(source.legal_moves, [])
        graph = c.explore_colored(source, max_states=1)
        self.assertTrue(graph.complete)
        self.assertEqual(len(graph), 1)
        self.assertEqual(graph.arcs, [])
        for algorithm in ("bfs", "bidirectional"):
            result = c.solve_colored(source, algorithm=algorithm)
            self.assertEqual(result.status, "unreachable")

    def test_search_result_is_immutable(self):
        result = c.solve_colored(c.State())
        with self.assertRaises(AttributeError):
            result.status = "unreachable"
        with self.assertRaises(AttributeError):
            del result.solution
        record = result.to_dict()
        record["status"] = "unreachable"
        self.assertEqual(result.status, "solved")

    def test_search_options_and_reference_specifications_are_checked(self):
        state = c.State(one_face_puzzle())
        with self.assertRaises(ValueError):
            c.solve_colored(state, target=c.State())
        for options in ({"metric": "unknown"}, {"algorithm": "unknown"},
                        {"max_states": 0}, {"max_states": -1}, {"max_depth": -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                c.solve_colored(state, **options)
        for name in ("max_states", "max_depth"):
            for value in (True, 1.5, "3"):
                with self.subTest(name=name, value=value), self.assertRaises(TypeError):
                    c.solve_colored(state, **{name: value})


class ColoredCommandTests(unittest.TestCase):
    def invoke(self, *arguments):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(list(arguments))
        return status, output.getvalue(), errors.getvalue()

    def test_solve_colored_named_fixture_and_metric(self):
        status, output, errors = self.invoke("solve-colored", "Alcatraz", "F R2",
                                              "--metric", "HTM", "--max-depth", "2")
        self.assertEqual((status, errors), (0, ""))
        result = json.loads(output)
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["metric"], "HTM")
        self.assertTrue(result["optimal"])
        self.assertTrue(c.State(c.fixture("Alcatraz")).apply("F R2").apply(result["solution"]).is_solved)

    def test_imported_file_default_moves_and_colored_graph_export(self):
        state = imported(c.State(one_face_puzzle()).apply("U2"))
        with tempfile.TemporaryDirectory() as directory:
            puzzle = Path(directory) / "puzzle.json"
            exported = Path(directory) / "graph.json"
            c.save_puzzle(state, puzzle)
            status, output, errors = self.invoke("solve-colored", str(puzzle),
                                                  "--algorithm", "bfs", "--metric", "HTM")
            self.assertEqual((status, errors), (0, ""))
            result = json.loads(output)
            self.assertEqual(result["distance"], 1)
            self.assertTrue(state.apply(result["solution"]).is_solved)
            target = imported(c.State(one_face_puzzle()).apply("U"))
            target_path = Path(directory) / "target.json"
            c.save_puzzle(target, target_path)
            status, output, errors = self.invoke("solve-colored", str(puzzle),
                                                  "--target", str(target_path))
            self.assertEqual((status, errors), (0, ""))
            self.assertEqual(state.apply(json.loads(output)["solution"]), target)
            status, output, errors = self.invoke("explore-colored", str(puzzle),
                                                  "--output", str(exported))
            self.assertEqual((status, errors), (0, ""))
            summary = json.loads(output)
            self.assertEqual(summary["states"], 4)
            self.assertEqual(summary["arcs"], 8)
            self.assertTrue(summary["complete"])
            record = json.loads(exported.read_text())
            self.assertEqual(record["format"], "bce-v2-colored-graph")
            self.assertTrue(record["complete"])

    def test_cli_limit_and_unreachable_exit_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "puzzle.json"
            initial = c.State(one_face_puzzle())
            c.save_puzzle(initial.apply("U2"), path)
            status, output, errors = self.invoke("solve-colored", str(path), "--max-depth", "1")
            self.assertEqual((status, errors), (2, ""))
            self.assertEqual(json.loads(output)["status"], "limit_reached")
            status, output, errors = self.invoke("explore-colored", str(path), "--max-states", "2")
            self.assertEqual((status, errors), (2, ""))
            self.assertFalse(json.loads(output)["complete"])
            c.save_puzzle(imported(initial, corners=[1, 2, 0, 3, 4, 5, 6, 7]), path)
            status, output, errors = self.invoke("solve-colored", str(path))
            self.assertEqual((status, errors), (3, ""))
            self.assertEqual(json.loads(output)["status"], "unreachable")


if __name__ == "__main__":
    unittest.main()
