"""Complete reusable method policies, physical replay, and offline artifacts."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c


IDENTITY = tuple(range(48))
REFERENCE_ORDERS = (("Alcatraz", 324), ("Bicube Fuse", 60), ("Shark Fin Soup", 36))


def then(first, second):
    return tuple(second[point] for point in first)


def imported(state):
    return c.State.from_cubies(
        state.specification, corners=state.corners, twists=state.twists,
        edges=state.edges, flips=state.flips)


def observe(action, block, kind):
    return ((action.destinations[block],) if kind == "place_block" else
            (action.destinations[block], action.phases[block]))


def refingerprint(record):
    payload = {key: value for key, value in record.items() if key != "fingerprint"}
    record["fingerprint"] = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return record


@unittest.skipUnless(shutil.which("gap"), "GAP is required to compile reference methods")
class HumanMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.plans, cls.methods, cls.loaded, cls.states = {}, {}, {}, {}
        for name, order in REFERENCE_ORDERS:
            shape = c.fixture(name)
            # Delivery 1 is used only as an independent complete input generator.
            plan = c.plan_human_stages(shape, max_group_elements=order, timeout=45)
            cls.plans[name] = plan
            method = c.synthesize_human_method(shape, max_group_elements=order, timeout=45)
            cls.methods[name] = method
            path = Path(cls.directory.name) / (name.replace(" ", "-") + ".json")
            method.save(path)
            with patch("subprocess.run", side_effect=AssertionError("loading requires no GAP")):
                cls.loaded[name] = c.load_human_method(path)
            initial = c.State(shape)
            cls.states[name] = tuple(imported(initial.apply(
                plan.group.witness(permutation).expanded_moves(plan.group.generators)))
                for permutation in plan.group.permutations)
        cls.fused_shape = c.Shape([1] * 9 + [2] * 18)
        cls.fused = c.synthesize_human_method(cls.fused_shape, max_group_elements=4, timeout=45)

    def assert_application(self, method, source):
        self.assertIsNone(source.scramble)
        recognition = method.recognize(source)
        self.assertEqual(recognition.status, "solved" if source.is_solved else "ready")
        first = method.next_step(source)
        application = method.apply(source)
        self.assertEqual(application.status, "solved")
        self.assertTrue(application.state.is_solved)
        self.assertEqual(application.state.specification, source.specification)
        self.assertEqual(source.apply(application.turn_sequence), application.state)
        if source.is_solved:
            self.assertIsNone(first)
            self.assertEqual(application.steps, ())
            return
        self.assertIsNotNone(first)
        self.assertEqual((first.stage_number, first.algorithm_id),
                         (application.steps[0].stage_number, application.steps[0].algorithm_id))
        previous_number, current = 0, source
        algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
        for step in application.steps:
            self.assertGreater(step.stage_number, previous_number)
            self.assertEqual(step.before, current)
            self.assertEqual(current.apply(step.turn_sequence), step.after)
            algorithm = algorithms[step.algorithm_id]
            self.assertEqual(step.expression.evaluate(method.generators), algorithm.permutation)
            action = method.inventory.action(step.after)
            for stage in method.stages:
                if stage.number <= step.stage_number:
                    self.assertEqual(observe(action, stage.block_index, stage.feature.kind),
                                     stage.solved_observation)
            previous_number, current = step.stage_number, step.after
        self.assertEqual(current, application.state)

    def test_all_420_imported_reference_states_solve_with_compiled_and_reloaded_methods(self):
        with patch("subprocess.run", side_effect=AssertionError("application requires no GAP")):
            for name, order in REFERENCE_ORDERS:
                self.assertEqual(len(self.states[name]), order)
                for origin, method in (("compiled", self.methods[name]),
                                       ("reloaded", self.loaded[name])):
                    self.assertEqual(method.status, "completed")
                    self.assertEqual(method.group_order, order)
                    self.assertEqual(method.coverage, "certified")
                    self.assertEqual(method.quality, "computational_baseline")
                    for index, source in enumerate(self.states[name]):
                        with self.subTest(puzzle=name, origin=origin, element=index):
                            self.assert_application(method, source)

    def test_every_algorithm_has_a_legal_full_action_and_original_loop_expression(self):
        for name, _ in REFERENCE_ORDERS:
            for method in (self.methods[name], self.loaded[name]):
                initial = c.State(method.reference_shape)
                original_ids = {generator.id for generator in method.generators}
                for algorithm in method.algorithms:
                    with self.subTest(puzzle=name, algorithm=algorithm.id):
                        self.assertTrue(set(algorithm.expression.base_ids) <= original_ids)
                        self.assertEqual(algorithm.expression.evaluate(method.generators),
                                         algorithm.permutation)
                        physical = initial.apply(algorithm.turn_sequence)
                        self.assertEqual(physical.shape, method.reference_shape)
                        self.assertEqual(tuple(physical.sticker_permutation), algorithm.permutation)
                        expression = initial.apply(
                            algorithm.expression.expanded_moves(method.generators))
                        self.assertEqual(expression, physical)

    def test_all_case_fibers_are_corrected_while_preserving_earlier_stages(self):
        for name, _ in REFERENCE_ORDERS:
            group = self.plans[name].group
            permutations = group.permutations
            actions = {p: group.inventory.action(p) for p in permutations}
            for method in (self.methods[name], self.loaded[name]):
                algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
                current = set(permutations)
                for stage in method.stages:
                    with self.subTest(puzzle=name, stage=stage.number):
                        fibers = {}
                        for permutation in current:
                            value = observe(actions[permutation], stage.block_index, stage.feature.kind)
                            fibers.setdefault(value, set()).add(permutation)
                        target = fibers[stage.solved_observation]
                        self.assertEqual(stage.order_before, len(current))
                        self.assertEqual(stage.order_after, len(target))
                        self.assertEqual(stage.index, len(fibers))
                        self.assertEqual(stage.case_count, len(fibers))
                        self.assertEqual({case.observation for case in stage.cases}, set(fibers))
                        self.assertEqual(len(stage.cases), len(fibers))
                        for case in stage.cases:
                            self.assertIn(case.representative, fibers[case.observation])
                            if case.algorithm_id is None:
                                self.assertEqual(case.observation, stage.solved_observation)
                                correction = IDENTITY
                            else:
                                correction = algorithms[case.algorithm_id].permutation
                                self.assertIn(correction, current)
                            for permutation in fibers[case.observation]:
                                self.assertIn(then(permutation, correction), target)
                        current = target
                self.assertEqual(current, {IDENTITY})

    def test_case_examples_retain_the_declared_physical_representative(self):
        method = self.loaded["Alcatraz"]
        with patch("subprocess.run", side_effect=AssertionError("examples require no GAP")):
            for stage in method.stages:
                for case in stage.cases:
                    example = method.example_state(stage.number, case.observation)
                    self.assertEqual(example.specification, method.reference_shape)
                    self.assertEqual(example.shape, method.reference_shape)
                    self.assertEqual(tuple(example.sticker_permutation), case.representative)
                    self.assertEqual(observe(method.inventory.action(example), stage.block_index,
                                             stage.feature.kind), case.observation)

    def test_unrestored_shapes_and_different_reference_roots_are_distinct(self):
        method = self.loaded["Alcatraz"]
        initial = c.State(method.reference_shape)
        unrestored = next(initial.apply(move) for move in initial.legal_moves
                          if initial.apply(move).shape != method.reference_shape)
        other_reference = c.State(unrestored.shape)
        with patch("subprocess.run", side_effect=AssertionError("recognition requires no GAP")):
            for source, expected in ((imported(unrestored), "shape_not_restored"),
                                     (other_reference, "wrong_reference")):
                with self.subTest(status=expected):
                    self.assertEqual(method.recognize(source).status, expected)
                    application = method.apply(source)
                    self.assertEqual(application.status, expected)
                    self.assertEqual(application.state, source)
                    self.assertEqual(application.steps, ())
                    with self.assertRaises(ValueError):
                        method.next_step(source)

    def test_valid_root_shape_can_still_be_outside_the_loop_group(self):
        shape = c.Shape([0] * 9 + [1] * 18)
        method = c.synthesize_human_method(shape, max_group_elements=4, timeout=45)
        source = c.State.from_cubies(
            shape, corners=list(range(8)), twists=[1, 2] + [0] * 6,
            edges=list(range(12)), flips=[0] * 12)
        self.assertEqual(source.shape, shape)
        with patch("subprocess.run", side_effect=AssertionError("membership requires no GAP")):
            self.assertEqual(method.recognize(source).status, "unreachable")
            application = method.apply(source)
            self.assertEqual(application.status, "unreachable")
            self.assertEqual(application.state, source)
            self.assertEqual(application.steps, ())
            with self.assertRaises(ValueError):
                method.next_step(source)

    def test_fixed_footprint_orientation_and_trivial_group_methods(self):
        orientation = c.HumanMethod.from_dict(self.fused.to_dict())
        self.assertEqual((orientation.group_order, orientation.quotient_order,
                          orientation.kernel_order), (4, 1, 4))
        self.assertEqual(len(orientation.stages), 1)
        self.assertEqual({case.observation[1] for case in orientation.stages[0].cases},
                         {0, 1, 2, 3})
        trivial = c.synthesize_human_method(c.Shape([1] * 27), max_group_elements=1, timeout=45)
        with patch("subprocess.run", side_effect=AssertionError("application requires no GAP")):
            for moves in ("", "U", "U2", "U'"):
                self.assert_application(orientation, imported(c.State(self.fused_shape).apply(moves)))
            self.assertEqual(trivial.group_order, 1)
            self.assertEqual(trivial.stages, ())
            self.assertEqual(trivial.algorithms, ())
            self.assert_application(trivial, imported(c.State(trivial.reference_shape)))

    def test_limit_never_presents_an_incomplete_policy_as_certified(self):
        method = c.synthesize_human_method(self.fused_shape, max_group_elements=3, timeout=45)
        self.assertEqual(method.status, "limit_reached")
        self.assertEqual(method.group_order, 4)
        self.assertNotEqual(method.coverage, "certified")
        self.assertEqual(method.stages, ())
        self.assertEqual(method.algorithms, ())
        source = c.State(self.fused_shape)
        with patch("subprocess.run", side_effect=AssertionError("incomplete methods require no GAP")):
            self.assertEqual(method.recognize(source).status, "method_incomplete")
            application = method.apply(source)
            self.assertEqual(application.status, "method_incomplete")
            self.assertEqual(application.state, source)
            self.assertEqual(application.steps, ())
            with self.assertRaises(ValueError):
                method.next_step(source)

    def test_artifacts_roundtrip_deterministically_without_external_tools(self):
        for name, _ in REFERENCE_ORDERS:
            method, loaded = self.methods[name], self.loaded[name]
            self.assertEqual(method.to_dict(), json.loads(method.to_json()))
            self.assertEqual(method.to_json(), loaded.to_json())
            with patch("subprocess.run", side_effect=AssertionError("loading requires no GAP")):
                restored = c.HumanMethod.from_dict(method.to_dict())
            self.assertEqual(restored.to_json(), method.to_json())
            path = Path(self.directory.name) / "roundtrip.json"
            loaded.save(path)
            self.assertEqual(path.read_text(), loaded.to_json())

    def test_nonzero_root_artifact_preserves_its_original_witness_library(self):
        graph = c.explore(c.fixture("Bicube Fuse"))
        method = c.synthesize_human_method(graph, root=1, max_group_elements=60, timeout=45)
        self.assertEqual(method.root_vertex, 1)
        self.assertEqual(method.reference_shape, graph[1])
        with patch("subprocess.run", side_effect=AssertionError("loading requires no GAP")):
            loaded = c.HumanMethod.from_dict(method.to_dict())
            self.assertEqual(loaded.root_vertex, 1)
            self.assertEqual(loaded.to_json(), method.to_json())
            stage = loaded.stages[0]
            case = next(case for case in stage.cases if case.algorithm_id is not None)
            self.assert_application(loaded, imported(loaded.example_state(stage.number, case.observation)))

    def test_persistence_rejects_corruption_even_with_a_recomputed_fingerprint(self):
        original = self.fused.to_dict()
        corruptions = []
        expression = deepcopy(original)
        expression["algorithms"][0]["expression"] = {"kind": "sequence", "children": []}
        corruptions.append(("expression", expression))
        declaration = deepcopy(original)
        declaration["algorithms"][0]["expression"] = c.LoopExpression.turns(
            "", self.fused.algorithms[0].expression).to_dict()
        corruptions.append(("false literal declaration", declaration))
        moves = deepcopy(original)
        moves["algorithms"][0]["turn_sequence"] = ""
        corruptions.append(("moves", moves))
        reference = deepcopy(original)
        reference["reference_shape"] = c.Shape([2] * 18 + [1] * 9).labels
        corruptions.append(("reference", reference))
        frame = deepcopy(original)
        frame["frame"] = "rotating"
        corruptions.append(("frame", frame))
        coverage = deepcopy(original)
        coverage["stages"][0]["cases"].pop()
        corruptions.append(("case coverage", coverage))
        with patch("subprocess.run", side_effect=AssertionError("validation requires no GAP")):
            for name, record in corruptions:
                with self.subTest(corruption=name), self.assertRaises((ValueError, c.GapError)):
                    c.HumanMethod.from_dict(refingerprint(record))

    def test_fingerprint_mismatch_is_rejected(self):
        record = deepcopy(self.fused.to_dict())
        record["frame"] = "rotating"
        with self.assertRaises((ValueError, c.GapError)):
            c.HumanMethod.from_dict(record)


if __name__ == "__main__":
    unittest.main()
