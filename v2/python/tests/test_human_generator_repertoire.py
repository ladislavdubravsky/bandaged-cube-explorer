"""Reduced-generator guides retain complete stabilizer policies and witnesses."""

from contextlib import ExitStack
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
RESULTS = Path(__file__).resolve().parents[2] / "research-results"


def then(first, second):
    return tuple(second[point] for point in first)


def observe(action, stage):
    return ((action.destinations[stage.block_index],) if stage.feature.kind == "place_block" else
            (action.destinations[stage.block_index], action.phases[stage.block_index]))


def imported(reference, permutation):
    solved = "".join(face * 9 for face in "URFDLB")
    facelets = list(solved)
    points = tuple(point for point in range(54) if point % 9 != 4)
    for source, destination in enumerate(permutation):
        facelets[points[destination]] = solved[points[source]]
    return c.State.from_facelets("".join(facelets), reference)


def refingerprint(record):
    payload = {key: value for key, value in record.items() if key != "fingerprint"}
    record["fingerprint"] = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return record


def recipe_nodes(recipe):
    yield recipe
    for child in recipe.children:
        yield from recipe_nodes(child)


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare a complete method")
class HumanGeneratorPreparedMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trivial = c.synthesize_human_method(c.Shape([1] * 27),
                                                max_group_elements=1, timeout=45)
        # Only U turns are legal, and the asymmetric top layer has four
        # distinct shapes. Its only root loops are identities, so a nonzero
        # retained graph root exercises the generator-free branch faithfully.
        cls.nonzero_root = c.synthesize_human_method(
            c.Shape([1, 1, 2, 1, 1, 2, 3, 3, 0] + [4] * 18),
            root=1, max_group_elements=1, timeout=45)

    def test_invalid_limits_and_roots_on_prepared_methods_fail_before_gap(self):
        invalid = (({"max_group_elements": True}, TypeError),
                   ({"max_group_elements": 1.5}, TypeError),
                   ({"max_group_elements": "1"}, TypeError),
                   ({"max_group_elements": 0}, ValueError),
                   ({"max_group_elements": -1}, ValueError),
                   ({"root": True}, TypeError), ({"root": 1.5}, TypeError),
                   ({"root": "0"}, TypeError), ({"root": 1}, ValueError))
        with patch("subprocess.run", side_effect=AssertionError("invalid options must not invoke GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    c.generator_human_repertoire(self.trivial, **options)

    def test_generator_free_method_retains_its_saved_root_and_accepts_a_matching_root(self):
        method = self.nonzero_root
        self.assertEqual(method.root_vertex, 1)
        self.assertEqual(method.generators, ())
        with patch("subprocess.run", side_effect=AssertionError("portable method loading requires no GAP")):
            method = c.HumanMethod.from_dict(method.to_dict())
            with self.assertRaises(ValueError):
                c.generator_human_repertoire(method, root=0)
        for root in (None, 1):
            with self.subTest(root=root):
                repertoire = c.generator_human_repertoire(method, root=root,
                                                          max_group_elements=1, timeout=45)
                self.assertEqual(repertoire.baseline.root_vertex, 1)
                self.assertEqual(repertoire.method.root_vertex, 1)
                self.assertEqual(repertoire.to_dict()["root_vertex"], 1)
                self.assertEqual(repertoire.macros, ())
                with patch("subprocess.run", side_effect=AssertionError("portable repertoire loading requires no GAP")):
                    restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
                    self.assertEqual(restored.method.root_vertex, 1)
                    self.assertTrue(restored.apply(c.State(method.reference_shape)).state.is_solved)


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare reduced generator bases")
class HumanGeneratorRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fused_shape = c.Shape([1] * 9 + [2] * 18)
        cls.fused_analysis = c.analyze_isotropy(cls.fused_shape, timeout=45)
        cls.fused_method = c.synthesize_human_method(cls.fused_analysis,
                                                     max_group_elements=4, timeout=45)
        cls.partial = c.synthesize_human_method(cls.fused_analysis,
                                                max_group_elements=3, timeout=45)
        cls.fused = c.generator_human_repertoire(cls.fused_analysis,
                                                 max_group_elements=4, timeout=45)
        cls.trivial = c.generator_human_repertoire(c.Shape([1] * 27),
                                                   max_group_elements=1, timeout=45)
        cls.source = c.load_human_method(RESULTS / "alcatraz-execution-method.json")
        cls.analysis = c.analyze_isotropy(cls.source.reference_shape, timeout=45)
        # Cached improved methods can retain extra discovered witnesses. The
        # teaching vocabulary must still come from the reduced isotropy basis.
        cls.repertoire = c.generator_human_repertoire(cls.source,
                                                      max_group_elements=324, timeout=45)
        cls.states = tuple(imported(cls.source.reference_shape, permutation)
                           for permutation in sorted(cls.source._permutations))

    def test_masters_are_the_exact_reduced_generators_in_order_and_orientation(self):
        for repertoire, analysis in ((self.fused, self.fused_analysis),
                                     (self.repertoire, self.analysis)):
            self.assertEqual(len(repertoire.macros), len(analysis.generators))
            self.assertEqual(repertoire.metadata["generator_ids"], list(analysis.generator_ids))
            self.assertEqual(repertoire.metadata["basis"], "reduced_generators")
            self.assertEqual(repertoire.metadata["construction"], "original_loop_bfs")
            self.assertEqual(repertoire.metadata["coverage"], "certified")
            self.assertIs(repertoire.metadata["human_reviewed"], False)
            self.assertIs(repertoire.metadata["exhaustive_repertoire_search"], False)
            for index, (macro, generator) in enumerate(zip(repertoire.macros, analysis.generators), 1):
                with self.subTest(group=analysis.group_order, master=index):
                    self.assertEqual(macro.id, f"M{index}")
                    self.assertEqual(macro.algorithm.id, macro.id)
                    self.assertEqual(macro.algorithm.expression, c.LoopExpression.loop(generator.id))
                    self.assertEqual(macro.algorithm.turn_sequence, generator.turn_sequence)
                    self.assertEqual(macro.algorithm.permutation, generator.permutation)
                    self.assertEqual(macro.algorithm.block_action, generator.block_action)

    def test_every_case_uses_only_master_sequences_and_powers_and_solves_in_one_instruction(self):
        for repertoire in (self.fused, self.repertoire):
            identifiers = {macro.id for macro in repertoire.macros}
            for policy, stage in zip(repertoire.stages, repertoire.method.stages):
                self.assertEqual(tuple(case.observation for case in policy.cases), stage.observations)
                for case in policy.cases:
                    with self.subTest(stage=stage.number, observation=case.observation):
                        self.assertLessEqual(set(case.recipe.macro_ids), identifiers)
                        self.assertTrue(all(node.kind in ("macro", "sequence", "power")
                                            for node in recipe_nodes(case.recipe)))
                        self.assertEqual(case.next_observation, stage.solved_observation)
                        if case.observation == stage.solved_observation:
                            self.assertIsNone(case.instruction)
                            self.assertEqual(case.rank, 0)
                            continue
                        self.assertEqual(case.instruction, case.recipe)
                        word = case.recipe.loop_expression(repertoire.macros).expanded_moves(
                            repertoire.method.generators, max_expanded_moves=100_000)
                        self.assertEqual(case.rank, len(word.split()))
                        self.assertGreater(case.rank, 0)
                for rule in policy.rules:
                    self.assertLessEqual(set(rule.recipe.macro_ids), identifiers)
                    self.assertTrue(all(node.kind in ("macro", "sequence", "power")
                                        for node in recipe_nodes(rule.recipe)))

    def test_supplied_method_retains_its_entire_stage_chain_even_with_a_wider_witness_pool(self):
        selected = self.repertoire.method
        self.assertLess(len(self.repertoire.macros), len(self.source.generators))
        self.assertEqual(selected.strategy, self.source.strategy)
        self.assertEqual(selected.initial_features, self.source.initial_features)
        self.assertEqual(selected.skipped_features, self.source.skipped_features)
        self.assertEqual(selected.reference_shape, self.source.reference_shape)
        self.assertEqual(selected.root_vertex, self.source.root_vertex)
        self.assertEqual(selected._permutations, self.source._permutations)
        for actual, original in zip(selected.stages, self.source.stages):
            self.assertEqual((actual.number, actual.feature, actual.block_index, actual.block_name,
                              actual.order_before, actual.order_after, actual.solved_observation,
                              actual.implied_features, actual.observations),
                             (original.number, original.feature, original.block_index, original.block_name,
                              original.order_before, original.order_after, original.solved_observation,
                              original.implied_features, original.observations))
        self.assertEqual(len(selected.stages), len(self.source.stages))

    def test_whole_case_fibers_are_corrected_and_prior_blocks_may_move_between_master_calls(self):
        repertoire, method = self.repertoire, self.repertoire.method
        current = frozenset(method._permutations)
        actions = {permutation: method.inventory.action(permutation) for permutation in current}
        temporarily_moved = False
        for policy, stage in zip(repertoire.stages, method.stages):
            target = frozenset(permutation for permutation in current
                               if observe(actions[permutation], stage) == stage.solved_observation)
            for case in policy.cases:
                effect = case.recipe.loop_expression(repertoire.macros).evaluate(method.generators)
                fiber = frozenset(permutation for permutation in current
                                  if observe(actions[permutation], stage) == case.observation)
                with self.subTest(stage=stage.number, observation=case.observation):
                    self.assertIn(effect, current)
                    self.assertEqual(frozenset(then(permutation, effect) for permutation in fiber), target)
                    state = method.example_state(stage.number, case.observation)
                    expression = case.recipe.loop_expression(repertoire.macros)
                    # Each generator call is a legal root loop. Its boundary
                    # need not fix previously solved blocks; the full case must.
                    for identifier, exponent in expression.loop_steps(max_syllables=100_000):
                        word = c.LoopExpression.power(c.LoopExpression.loop(identifier),
                            1 if exponent > 0 else -1).expanded_moves(method.generators)
                        for _ in range(abs(exponent)):
                            state = state.apply(word)
                            self.assertEqual(state.shape, method.reference_shape)
                            action = method.inventory.action(state)
                            if any(observe(action, earlier) != earlier.solved_observation
                                   for earlier in method.stages[:stage.number - 1]):
                                temporarily_moved = True
                    action = method.inventory.action(state)
                    for completed in method.stages[:stage.number]:
                        self.assertEqual(observe(action, completed), completed.solved_observation)
            current = target
        self.assertEqual(current, frozenset((IDENTITY,)))
        self.assertTrue(temporarily_moved, "fixture must exercise restoration across multiple master calls")

    def test_every_reference_state_and_portable_roundtrip_solve_without_gap(self):
        with patch("subprocess.run", side_effect=AssertionError("loading and applying require no GAP")):
            restored = c.HumanRepertoire.from_dict(self.repertoire.to_dict())
            self.assertEqual(restored.to_json(), self.repertoire.to_json())
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "generator-repertoire.json"
                self.repertoire.save(path)
                self.assertEqual(c.load_human_repertoire(path).to_json(), self.repertoire.to_json())
            for index, state in enumerate(self.states):
                with self.subTest(element=index):
                    self.assertIsNone(state.scramble)
                    for repertoire in (self.repertoire, restored):
                        result = repertoire.apply(state)
                        self.assertEqual(result.status, "solved")
                        self.assertTrue(result.state.is_solved)
                        self.assertEqual(state.apply(result.turn_sequence), result.state)
                        for step in result.steps:
                            self.assertEqual(step.after, step.before.apply(step.turn_sequence))
                            self.assertEqual(step.rank_after, 0)
                            action = repertoire.method.inventory.action(step.after)
                            for completed in repertoire.method.stages[:step.stage_number]:
                                self.assertEqual(observe(action, completed), completed.solved_observation)

    def test_reported_metrics_measure_the_actual_full_solution_words(self):
        for name, method in (("baseline_metrics", self.repertoire.baseline),
                             ("selected_metrics", self.repertoire.method)):
            pairs = []
            for state in self.states:
                result = method.apply(state)
                self.assertEqual(result.status, "solved")
                words = result.turn_sequence.split()
                pairs.append((len(words), sum(2 if word.endswith("2") else 1 for word in words)))
            measured = self.repertoire.metadata[name]
            self.assertEqual(measured["mean_htm"], sum(pair[0] for pair in pairs) / len(pairs))
            self.assertEqual(measured["worst_htm"], max(pair[0] for pair in pairs))
            self.assertEqual(measured["mean_qtm"], sum(pair[1] for pair in pairs) / len(pairs))
            self.assertEqual(measured["worst_qtm"], max(pair[1] for pair in pairs))
        selected = self.repertoire.metadata["selected_metrics"]
        self.assertEqual(selected["macro_count"], len(self.repertoire.macros))
        self.assertEqual(selected["macro_definition_htm"],
                         sum(macro.algorithm.htm_length for macro in self.repertoire.macros))
        self.assertEqual(selected["rule_count"], sum(len(stage.rules) for stage in self.repertoire.stages))

    def test_constructor_bypasses_the_human_search_optimizers_and_leaves_existing_default_available(self):
        targets = ("bce_v2.improve_human_method", "bce_v2.select_human_chain",
                   "bce_v2.optimize_human_repertoire", "bce_v2.human_algorithms.improve_human_method",
                   "bce_v2.human_chain_search.select_human_chain",
                   "bce_v2.human_repertoire.optimize_human_repertoire")
        with ExitStack() as stack:
            for target in targets:
                stack.enter_context(patch(target, side_effect=AssertionError("human search is shelved")))
            direct = c.generator_human_repertoire(self.fused_analysis,
                                                   max_group_elements=4, timeout=45)
        self.assertEqual(direct.to_json(), self.fused.to_json())
        with patch("subprocess.run", side_effect=AssertionError("existing optimizer requires no GAP")):
            old = c.optimize_human_repertoire(self.fused_method, max_trials=0, max_recipes=0,
                                               max_extra_macros=0, max_setup_macros=0,
                                               allow_symmetry=False)
            c.HumanRepertoire.from_dict(old.to_dict())
        self.assertNotIn("basis", old.metadata)
        self.assertEqual(old.metadata["settings"]["preference"], "memory")
        self.assertEqual(old.metadata["trials_examined"], 0)
        self.assertTrue(old.apply(c.State(self.fused_shape).apply("U")).state.is_solved)

    def test_orientation_powers_and_trivial_group_need_no_extra_definitions(self):
        self.assertEqual(len(self.fused.macros), 1)
        self.assertEqual(len(self.fused.stages), 1)
        self.assertEqual(len(self.fused.stages[0].cases), 4)
        self.assertTrue(any(node.kind == "power" and abs(node.exponent) > 1
                            for case in self.fused.stages[0].cases
                            for node in recipe_nodes(case.recipe)))
        for moves in ("", "U", "U2", "U'"):
            self.assertTrue(self.fused.apply(imported(self.fused_shape,
                c.State(self.fused_shape).apply(moves).sticker_permutation)).state.is_solved)
        self.assertEqual(self.trivial.macros, ())
        self.assertEqual(self.trivial.stages, ())
        self.assertEqual(self.trivial.metadata["generator_ids"], [])
        with patch("subprocess.run", side_effect=AssertionError("trivial load requires no GAP")):
            restored = c.HumanRepertoire.from_dict(self.trivial.to_dict())
            self.assertTrue(restored.apply(c.State(restored.method.reference_shape)).state.is_solved)

    def test_partial_methods_and_group_limits_never_export_an_incomplete_certified_guide(self):
        with self.assertRaises(ValueError):
            c.generator_human_repertoire(self.partial)
        with self.assertRaises(ValueError):
            c.generator_human_repertoire(self.fused_analysis, max_group_elements=3, timeout=45)
        invalid = (({"strategy": "unknown"}, ValueError), ({"max_group_elements": True}, TypeError),
                   ({"max_group_elements": 0}, ValueError), ({"max_group_elements": 1.5}, TypeError),
                   ({"features": ()}, ValueError), ({"root": True}, TypeError))
        with patch("subprocess.run", side_effect=AssertionError("option validation must precede GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    c.generator_human_repertoire(self.fused_analysis, **options)

    def test_loading_rejects_false_generator_metadata_and_metrics_with_new_fingerprints(self):
        valid = self.repertoire.to_dict()
        corruptions = (
            ("false basis", lambda metadata: metadata.__setitem__("basis", "optimized")),
            ("false construction", lambda metadata: metadata.__setitem__("construction", "human_search")),
            ("missing generator", lambda metadata: metadata["generator_ids"].pop()),
            ("reordered generators", lambda metadata: metadata["generator_ids"].reverse()),
            ("false generator ID", lambda metadata: metadata["generator_ids"].__setitem__(0, -1)),
            ("false coverage", lambda metadata: metadata.__setitem__("coverage", "partial")),
            ("unverified human review", lambda metadata: metadata.__setitem__("human_reviewed", True)),
            ("false exhaustive search", lambda metadata: metadata.__setitem__("exhaustive_repertoire_search", True)),
            ("false mean HTM", lambda metadata: metadata["selected_metrics"].__setitem__("mean_htm", 0)),
            ("false baseline HTM", lambda metadata: metadata["baseline_metrics"].__setitem__("mean_htm", 0)),
            ("Boolean master count", lambda metadata: metadata["selected_metrics"].__setitem__("macro_count", True)),
        )
        with patch("subprocess.run", side_effect=AssertionError("artifact validation requires no GAP")):
            for label, mutate in corruptions:
                record = deepcopy(valid)
                mutate(record["metadata"])
                refingerprint(record)
                with self.subTest(corruption=label), self.assertRaises(ValueError):
                    c.HumanRepertoire.from_dict(record)


if __name__ == "__main__":
    unittest.main()
