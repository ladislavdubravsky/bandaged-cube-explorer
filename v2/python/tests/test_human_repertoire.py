"""Shared vocabularies and compressed recognition retain exact human policies."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2._moves import _simplified_moves


IDENTITY = tuple(range(48))
RESULTS = Path(__file__).resolve().parents[2] / "research-results"
SMALL = dict(max_trials=8, max_recipes=256, max_extra_macros=4, max_setup_macros=4,
             allow_symmetry=False)


def then(first, second):
    return tuple(second[point] for point in first)


def inverse(permutation):
    result = [0] * len(permutation)
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


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


def costs(method, states):
    pairs = []
    for state in states:
        application = method.apply(state)
        if application.status != "solved" or not application.state.is_solved:
            raise AssertionError("repertoire policy does not solve every reference-group state")
        words = application.turn_sequence.split()
        pairs.append((len(words), sum(2 if word.endswith("2") else 1 for word in words)))
    return {"mean_htm": sum(pair[0] for pair in pairs) / len(pairs),
            "worst_htm": max(pair[0] for pair in pairs),
            "mean_qtm": sum(pair[1] for pair in pairs) / len(pairs),
            "worst_qtm": max(pair[1] for pair in pairs)}


@unittest.skipUnless(shutil.which("gap"), "GAP is required to prepare the small synthetic methods")
class HumanRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fused = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
                                             max_group_elements=4, timeout=45)
        cls.trivial = c.synthesize_human_method(c.Shape([1] * 27), max_group_elements=1, timeout=45)
        cls.partial = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
                                               max_group_elements=3, timeout=45)
        cls.sources, cls.repertoires, cls.states = {}, {}, {}
        with patch("subprocess.run", side_effect=AssertionError("portable repertoire work requires no GAP")):
            for label in ("execution", "recognition"):
                source = c.load_human_method(RESULTS / ("alcatraz-" + label + "-method.json"))
                cls.sources[label] = source
                cls.repertoires[label] = c.optimize_human_repertoire(source, **SMALL)
                cls.states[label] = tuple(imported(source.reference_shape, permutation)
                                          for permutation in sorted(source._permutations))
            cls.orientation = c.optimize_human_repertoire(
                cls.fused, max_trials=32, max_recipes=256, max_extra_macros=4,
                max_setup_macros=4, allow_symmetry=False)

    def test_every_imported_alcatraz_state_solves_by_commands_and_expanded_portable_policy_without_gap(self):
        repertoire = self.repertoires["execution"]
        with patch("subprocess.run", side_effect=AssertionError("repertoire application requires no GAP")):
            loaded = c.HumanRepertoire.from_dict(repertoire.to_dict())
            expanded = c.HumanMethod.from_dict(repertoire.method.to_dict())
            for index, state in enumerate(self.states["execution"]):
                with self.subTest(element=index):
                    self.assertIsNone(state.scramble)
                    reference = expanded.apply(state)
                    self.assertEqual(reference.status, "solved")
                    for label, policy in (("selected", repertoire), ("reloaded", loaded)):
                        result = policy.apply(state)
                        self.assertEqual(result.status, "solved", label)
                        self.assertTrue(result.state.is_solved)
                        self.assertEqual(result.state, reference.state)
                        self.assertEqual(result.turn_sequence, reference.turn_sequence)
                        current = state
                        for step in result.steps:
                            self.assertEqual(step.before, current)
                            self.assertEqual(step.after, current.apply(step.turn_sequence))
                            action = repertoire.method.inventory.action(step.after)
                            for earlier in repertoire.method.stages[:step.stage_number - 1]:
                                self.assertEqual(observe(action, earlier), earlier.solved_observation)
                            current = step.after

    def test_every_complete_recipe_and_first_instruction_correct_the_entire_actual_case_fiber(self):
        for label, repertoire in self.repertoires.items():
            method, current = repertoire.method, frozenset(repertoire.method._permutations)
            macros = {macro.id: macro for macro in repertoire.macros}
            actions = {permutation: method.inventory.action(permutation) for permutation in current}
            initial = c.State(method.reference_shape)
            algorithms = {algorithm.id: algorithm for algorithm in method.algorithms}
            for compressed, stage in zip(repertoire.stages, method.stages):
                self.assertEqual(compressed.number, stage.number)
                cases = {case.observation: case for case in compressed.cases}
                self.assertEqual(set(cases), set(stage.observations))
                target = frozenset(permutation for permutation in current
                                   if observe(actions[permutation], stage) == stage.solved_observation)
                for original in stage.cases:
                    case = cases[original.observation]
                    with self.subTest(policy=label, stage=stage.number, observation=case.observation):
                        expression = case.recipe.loop_expression(macros)
                        effect = expression.evaluate(method.generators)
                        fiber = frozenset(permutation for permutation in current
                                          if observe(actions[permutation], stage) == case.observation)
                        self.assertTrue(fiber)
                        self.assertIn(effect, current)
                        self.assertEqual(frozenset(then(permutation, effect) for permutation in fiber), target)
                        word = expression.expanded_moves(method.generators, max_expanded_moves=100_000)
                        replay = initial.apply(word)
                        self.assertEqual(replay.shape, initial.shape)
                        self.assertEqual(replay.sticker_permutation, effect)
                        if original.algorithm_id is None:
                            self.assertEqual(effect, IDENTITY)
                            self.assertIsNone(case.instruction)
                            self.assertEqual(case.rank, 0)
                            self.assertEqual(case.next_observation, stage.solved_observation)
                            continue
                        self.assertEqual(effect, algorithms[original.algorithm_id].permutation)
                        self.assertEqual(repertoire.recipe_for(stage.number, case.observation), case.recipe)
                        instruction = case.instruction.loop_expression(macros)
                        first = instruction.evaluate(method.generators)
                        self.assertIn(first, current)
                        next_fiber = frozenset(permutation for permutation in current
                                               if observe(actions[permutation], stage) == case.next_observation)
                        self.assertEqual(frozenset(then(permutation, first) for permutation in fiber), next_fiber)
                        self.assertGreater(case.rank, cases[case.next_observation].rank)
                current = target
            self.assertEqual(current, frozenset((IDENTITY,)))

    def test_compressed_rules_exactly_cover_unsolved_observations_and_expand_to_checked_instructions(self):
        for repertoire in (*self.repertoires.values(), self.orientation):
            macros = {macro.id: macro for macro in repertoire.macros}
            for compressed, stage in zip(repertoire.stages, repertoire.method.stages):
                cases = {case.observation: case for case in compressed.cases}
                covered = []
                for rule in compressed.rules:
                    self.assertEqual(rule.stage_number, stage.number)
                    self.assertIn(rule.kind, ("instruction", "powers", "cycle"))
                    self.assertEqual(len(rule.observations), len(rule.exponents))
                    covered.extend(rule.observations)
                    body = rule.recipe.loop_expression(macros)
                    for observation, exponent in zip(rule.observations, rule.exponents):
                        self.assertNotEqual(observation, stage.solved_observation)
                        self.assertEqual(c.LoopExpression.power(body, exponent).evaluate(repertoire.method.generators),
                                         cases[observation].instruction.loop_expression(macros).evaluate(
                                             repertoire.method.generators))
                    if rule.kind == "cycle":
                        self.assertEqual(set(rule.cycle), set(stage.observations))
                        self.assertEqual(len(rule.cycle), len(stage.observations))
                expected = set(stage.observations) - {stage.solved_observation}
                self.assertEqual(set(covered), expected)
                self.assertEqual(len(covered), len(expected))

    def test_a_four_case_orientation_stage_uses_one_learned_definition_with_inverse_and_powers(self):
        repertoire = self.orientation
        self.assertEqual(len(self.fused.algorithms), 3)
        self.assertEqual(len(repertoire.macros), 1)
        self.assertEqual(repertoire.metadata["selected_metrics"]["macro_count"], 1)
        self.assertEqual(len(repertoire.stages), 1)
        cases = repertoire.stages[0].cases
        self.assertEqual(len(cases), 4)
        self.assertTrue(any(abs(exponent) > 1 for rule in repertoire.stages[0].rules for exponent in rule.exponents))
        self.assertTrue(any(exponent < 0 for rule in repertoire.stages[0].rules for exponent in rule.exponents))
        for permutation in self.fused._permutations:
            state = imported(self.fused.reference_shape, permutation)
            self.assertTrue(repertoire.apply(state).state.is_solved)

    def test_displayed_definitions_generate_the_complete_reference_group_without_hidden_fallbacks(self):
        for repertoire in (*self.repertoires.values(), self.orientation):
            alphabet = tuple(effect for macro in repertoire.macros
                             for effect in (macro.algorithm.permutation, inverse(macro.algorithm.permutation)))
            generated, queue = {IDENTITY}, [IDENTITY]
            for permutation in queue:
                for effect in alphabet:
                    successor = then(permutation, effect)
                    if successor not in generated:
                        generated.add(successor)
                        queue.append(successor)
            self.assertEqual(generated, set(repertoire.method._permutations))
            identifiers = {macro.id for macro in repertoire.macros}
            for stage in repertoire.stages:
                for case in stage.cases:
                    self.assertLessEqual(set(case.recipe.macro_ids), identifiers)

    def test_strict_default_guard_and_reported_metrics_use_actual_complete_physical_words(self):
        with patch("subprocess.run", side_effect=AssertionError("measurement requires no GAP")):
            for label, repertoire in self.repertoires.items():
                before = costs(repertoire.baseline, self.states[label])
                after = costs(repertoire.method, self.states[label])
                for key, value in before.items():
                    self.assertEqual(repertoire.metadata["baseline_metrics"][key], value)
                for key, value in after.items():
                    self.assertEqual(repertoire.metadata["selected_metrics"][key], value)
                self.assertLessEqual(after["mean_htm"], before["mean_htm"])
                self.assertLessEqual(after["worst_htm"], before["worst_htm"])
                self.assertEqual(repertoire.baseline.to_json(), self.sources[label].to_json())
                selected = repertoire.metadata["selected_metrics"]
                self.assertEqual(selected["macro_count"], len(repertoire.macros))
                self.assertEqual(selected["macro_definition_htm"],
                                 sum(macro.algorithm.htm_length for macro in repertoire.macros))
                self.assertEqual(selected["rule_count"], sum(len(stage.rules) for stage in repertoire.stages))

    def test_finite_recipe_and_deletion_budgets_do_not_remove_complete_fallbacks(self):
        with patch("subprocess.run", side_effect=AssertionError("bounded repertoire search requires no GAP")):
            limited = c.optimize_human_repertoire(self.fused, max_trials=1, max_recipes=1,
                                                  max_extra_macros=0, max_setup_macros=0,
                                                  allow_symmetry=False)
            zero = c.optimize_human_repertoire(self.fused, max_trials=0, max_recipes=0,
                                               max_power=10**12,
                                               max_extra_macros=0, max_setup_macros=0,
                                               allow_symmetry=False)
        self.assertLessEqual(limited.metadata["trials_examined"], 1)
        self.assertLessEqual(limited.metadata["recipe_candidates_examined"], 1)
        self.assertEqual(zero.metadata["trials_examined"], 0)
        self.assertEqual(zero.metadata["recipe_candidates_examined"], 0)
        for repertoire in (limited, zero):
            self.assertEqual(repertoire.method.coverage, "certified")
            for permutation in self.fused._permutations:
                self.assertTrue(repertoire.apply(imported(self.fused.reference_shape, permutation)).state.is_solved)

    def test_trivial_group_exports_empty_vocabulary_and_recognition(self):
        with patch("subprocess.run", side_effect=AssertionError("trivial repertoire requires no GAP")):
            repertoire = c.optimize_human_repertoire(self.trivial, max_power=10**12, max_recipes=64)
            restored = c.HumanRepertoire.from_dict(repertoire.to_dict())
        self.assertEqual(repertoire.macros, ())
        self.assertEqual(repertoire.stages, ())
        self.assertEqual(restored.method.terminal_order, 1)
        self.assertEqual(restored.metadata["selected_metrics"]["macro_count"], 0)
        self.assertEqual(repertoire.metadata["recipe_candidates_examined"], 0)
        self.assertTrue(restored.apply(c.State(self.trivial.reference_shape)).state.is_solved)

    def test_artifact_roundtrips_deterministically_and_metadata_inspection_cannot_mutate_it(self):
        options = dict(max_trials=4, max_recipes=64, max_extra_macros=2,
                       max_setup_macros=2, allow_symmetry=False)
        with patch("subprocess.run", side_effect=AssertionError("portable artifact work requires no GAP")):
            first = c.optimize_human_repertoire(self.fused, **options)
            with patch.object(c.HumanMacroRecipe, "render", side_effect=AssertionError(
                    "search ordering must not depend on user-facing notation")):
                second = c.optimize_human_repertoire(self.fused, **options)
            self.assertEqual(first.to_json(), second.to_json())
            self.assertEqual(first.to_dict(), json.loads(first.to_json()))
            detached = first.metadata
            detached["accepted_deletions"] = -1
            self.assertGreaterEqual(first.metadata["accepted_deletions"], 0)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "repertoire.json"
                first.save(path)
                restored = c.load_human_repertoire(path)
                self.assertEqual(first.to_json(), path.read_text())
                self.assertEqual(restored.to_json(), first.to_json())

    def test_recipe_factories_retain_original_witnesses_and_check_noncentral_setup_undo(self):
        source = self.sources["execution"]
        by_id = {algorithm.id: algorithm for algorithm in source.algorithms}
        macros = {identifier: c.HumanRepertoireMacro(identifier, replace(by_id[algorithm], id=identifier))
                  for identifier, algorithm in (("M1", "A2"), ("M2", "A14"), ("M3", "A15"))}
        setup = c.HumanMacroRecipe.macro("M1")
        body = c.HumanMacroRecipe.macro("M2")
        conjugate = c.HumanMacroRecipe.conjugate(setup, body)
        expression = conjugate.loop_expression(macros)
        self.assertEqual(expression.evaluate(source.generators), by_id["A15"].permutation)
        self.assertNotEqual(expression.evaluate(source.generators), by_id["A14"].permutation)
        state = c.State(source.reference_shape)
        replay = state.apply(expression.expanded_moves(source.generators, max_expanded_moves=100_000))
        self.assertEqual(replay.shape, state.shape)
        self.assertEqual(replay.sticker_permutation, by_id["A15"].permutation)
        self.assertEqual(set(conjugate.macro_ids), {"M1", "M2"})
        self.assertEqual(c.HumanMacroRecipe.power(body, -1).loop_expression(macros).evaluate(source.generators),
                         inverse(by_id["A14"].permutation))
        commutator = c.HumanMacroRecipe.commutator(setup, body)
        self.assertEqual(commutator.loop_expression(macros).evaluate(source.generators),
                         then(by_id["A15"].permutation, inverse(by_id["A14"].permutation)))

    def test_invalid_options_and_partial_methods_fail_before_external_work(self):
        invalid = (({"preference": "unknown"}, ValueError), ({"max_trials": True}, TypeError),
                   ({"max_recipes": 1.0}, TypeError), ({"max_power": -1}, ValueError),
                   ({"max_extra_macros": -1}, ValueError), ({"allow_symmetry": 1}, TypeError),
                   ({"max_cost_ratio": 0.9}, ValueError), ({"max_cost_ratio": float("inf")}, ValueError))
        with patch("subprocess.run", side_effect=AssertionError("validation must not invoke GAP")):
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    c.optimize_human_repertoire(self.fused, **options)
            with self.assertRaises(TypeError):
                c.optimize_human_repertoire(object())
            with self.assertRaises(ValueError):
                c.optimize_human_repertoire(self.partial)

    def test_loading_rejects_corrupted_rule_semantics_even_with_recomputed_fingerprints(self):
        valid = self.orientation.to_dict()
        unsolved = next(index for index, case in enumerate(valid["stages"][0]["cases"]) if case["rank"])
        corruptions = []

        def changed(label, mutate):
            record = deepcopy(valid)
            mutate(record)
            corruptions.append((label, refingerprint(record)))

        changed("missing recognition rule", lambda record: record["stages"][0]["rules"].clear())
        changed("overlapping recognition rules", lambda record: record["stages"][0]["rules"].append(
            deepcopy(record["stages"][0]["rules"][0])))
        changed("incorrect recognition exponent", lambda record: record["stages"][0]["rules"][0]["exponents"].__setitem__(0, 0))
        changed("false progress rank", lambda record: record["stages"][0]["cases"][unsolved].__setitem__("rank", 0))
        changed("false next observation", lambda record: record["stages"][0]["cases"][unsolved].__setitem__(
            "next_observation", record["stages"][0]["cases"][unsolved]["observation"]))
        changed("identity correction recipe", lambda record: record["stages"][0]["cases"][unsolved].__setitem__(
            "recipe", c.HumanMacroRecipe.sequence().to_dict()))
        changed("unknown master reference", lambda record: record["stages"][0]["cases"][unsolved].__setitem__(
            "instruction", c.HumanMacroRecipe.macro("M999").to_dict()))
        changed("incorrect saved metric", lambda record: record["metadata"]["selected_metrics"].__setitem__("mean_htm", 0))
        changed("incorrect saved baseline metric", lambda record: record["metadata"]["baseline_metrics"].__setitem__("mean_htm", 0))
        changed("false integer metric type", lambda record: record["metadata"]["selected_metrics"].__setitem__("macro_count", True))
        changed("unsupported human review claim", lambda record: record["metadata"].__setitem__("human_reviewed", True))
        changed("unsupported exhaustive search claim", lambda record: record["metadata"].__setitem__("exhaustive_repertoire_search", True))
        changed("missing selected candidate", lambda record: record["metadata"].__setitem__("selected_id", "missing"))
        changed("missing selected frontier member", lambda record: record["metadata"].__setitem__("frontier", []))
        changed("inconsistent candidate metrics", lambda record: next(
            candidate for candidate in record["metadata"]["candidates"]
            if candidate["id"] == record["metadata"]["selected_id"])["metrics"].__setitem__("mean_htm", 0))
        changed("false convention", lambda record: record.__setitem__("preservation", "after_each_face_turn"))

        word = deepcopy(valid)
        word["macros"][0].update(turn_sequence="", htm_length=0, qtm_length=0)
        corruptions.append(("false master physical word", refingerprint(word)))
        witness = deepcopy(valid)
        witness["macros"][0]["expression"] = c.LoopExpression.power(
            self.orientation.macros[0].algorithm.expression, -1).to_dict()
        corruptions.append(("false original witness", refingerprint(witness)))
        cycle = deepcopy(valid)
        rule = next(rule for rule in cycle["stages"][0]["rules"] if rule["kind"] == "cycle")
        rule["cycle"][1], rule["cycle"][2] = rule["cycle"][2], rule["cycle"][1]
        corruptions.append(("false cycle order", refingerprint(cycle)))
        projection = deepcopy(valid)
        projection["method"]["stages"][0]["cases"].pop(unsolved)
        refingerprint(projection["method"])
        corruptions.append(("incomplete compiled projection", refingerprint(projection)))
        with patch("subprocess.run", side_effect=AssertionError("semantic load checks require no GAP")):
            for label, record in corruptions:
                with self.subTest(corruption=label), self.assertRaises((ValueError, c.GapError)):
                    c.HumanRepertoire.from_dict(record)

    def test_master_recipe_factories_reject_noninteger_exponents_and_use_actual_proper_symmetries(self):
        body = c.HumanMacroRecipe.macro(self.orientation.macros[0].id)
        for exponent in (True, 1.0):
            with self.subTest(exponent=exponent), self.assertRaises(TypeError):
                c.HumanMacroRecipe.power(body, exponent)
        rotations = c.bandage_symmetries(self.orientation.method.reference_shape)
        self.assertTrue(rotations)
        rotation = c.HumanMacroRecipe.rotated(rotations[0], body)
        expression = rotation.loop_expression(self.orientation.macros)
        replay = c.State(self.orientation.method.reference_shape).apply(expression.expanded_moves(
            self.orientation.method.generators, max_expanded_moves=100_000))
        self.assertEqual(replay.shape, self.orientation.method.reference_shape)
        self.assertEqual(replay.sticker_permutation, expression.evaluate(self.orientation.method.generators))

    def test_valid_physical_word_alternatives_retain_their_exact_source_policy_and_cost_guard(self):
        source = self.sources["execution"]
        generator = source.generators[0]
        element, order = generator.permutation, 1
        while element != IDENTITY:
            element = then(element, generator.permutation)
            order += 1
            self.assertLessEqual(order, source.group_order)
        identity_word = _simplified_moves(generator.turn_sequence.split() * order)
        self.assertTrue(identity_word)
        original = source.algorithms[0]
        padded_word = _simplified_moves([*original.turn_sequence.split(), *identity_word.split()])
        self.assertNotEqual(padded_word, original.turn_sequence)
        modified = replace(source, algorithms=(replace(original, turn_sequence=padded_word), *source.algorithms[1:]))
        with patch("subprocess.run", side_effect=AssertionError("alternate physical words require no GAP")):
            alternate = c.HumanMethod.from_dict(modified.to_dict())
            physical = c.State(source.reference_shape).apply(padded_word)
            self.assertEqual(physical.sticker_permutation, original.permutation)
            repertoire = c.optimize_human_repertoire(
                alternate, max_trials=0, max_recipes=0, max_extra_macros=0,
                max_setup_macros=0, allow_symmetry=False)
            self.assertEqual(repertoire.baseline.to_json(), alternate.to_json())
            before = costs(alternate, self.states["execution"])
            after = costs(repertoire.method, self.states["execution"])
            for key, expected in before.items():
                self.assertEqual(repertoire.metadata["baseline_metrics"][key], expected)
            self.assertLessEqual(after["mean_htm"], before["mean_htm"])
            self.assertLessEqual(after["worst_htm"], before["worst_htm"])
            self.assertEqual(c.HumanRepertoire.from_dict(repertoire.to_dict()).to_json(), repertoire.to_json())

    def test_valid_source_algorithm_names_cannot_collide_with_extra_original_loop_names(self):
        for label, source in (("orientation", self.fused), ("alcatraz", self.sources["execution"])):
            generator = source.generators[0]
            collision = f"L{generator.id}"
            original = next(algorithm for algorithm in source.algorithms
                            if algorithm.permutation != generator.permutation)
            renamed = replace(source,
                algorithms=tuple(replace(algorithm, id=collision) if algorithm.id == original.id else algorithm
                                 for algorithm in source.algorithms),
                stages=tuple(replace(stage, cases=tuple(
                    replace(case, algorithm_id=collision) if case.algorithm_id == original.id else case
                    for case in stage.cases)) for stage in source.stages))
            with self.subTest(reference=label), patch(
                    "subprocess.run", side_effect=AssertionError("valid arbitrary algorithm names require no GAP")):
                alternate = c.HumanMethod.from_dict(renamed.to_dict())
                repertoire = c.optimize_human_repertoire(
                    alternate, max_trials=0, max_recipes=0, max_setup_macros=0, allow_symmetry=False)
                self.assertEqual(repertoire.baseline.to_json(), alternate.to_json())
                stage = next(stage for stage in alternate.stages
                             if any(case.algorithm_id == collision for case in stage.cases))
                case = next(case for case in stage.cases if case.algorithm_id == collision)
                state = alternate.example_state(stage.number, case.observation)
                self.assertTrue(repertoire.apply(state).state.is_solved)
                self.assertEqual(c.HumanRepertoire.from_dict(repertoire.to_dict()).to_json(), repertoire.to_json())


if __name__ == "__main__":
    unittest.main()
