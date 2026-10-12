"""Witnessed palette admission, complete setup recipes and execution signs."""

from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.algorithm_palette import AlgorithmPalette, AlgorithmPaletteBody, AlgorithmPaletteSetup
from bce_v2.symbolic_chain_search import _compile_dictionary_policy, _SEARCH_DEFAULTS


def algorithms_for(loops, words):
    library = c.AlgorithmLibrary(loops, (), (), ())
    leaves = {g.turn_sequence: c.LoopExpression.loop(g.id) for g in loops.generators}
    result = {}
    for identifier, word in words.items():
        parts = []
        for token in word.split():
            leaf = leaves[token[0]]
            parts.append(c.LoopExpression.power(leaf, 2 if token.endswith("2") else
                                               -1 if token.endswith("'") else 1))
        result[identifier] = replace(library.build_algorithm(c.LoopExpression.sequence(*parts)),
                                     id=identifier)
    return result


class AlgorithmPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loops = c.isotropy_loops(c.Shape())
        cls.algorithms = algorithms_for(cls.loops, {
            "EO": "F R U R' U' F'", "Sune": "R U R' U R U2 R'",
            "Tperm": "R U R' U' R' F R2 U' R' U' R U R' F'",
            "Ua": "R U' R U R U R U' R' U' R2",
            "U": "U", "U2": "U2", "U'": "U'"})

    def palette(self, *, inverse=False):
        bodies = tuple(AlgorithmPaletteBody(name, self.algorithms[name], inverse)
                       for name in ("EO", "Sune", "Tperm", "Ua"))
        setups = tuple(AlgorithmPaletteSetup(name, self.algorithms[name])
                       for name in ("U", "U2", "U'"))
        return AlgorithmPalette(bodies, setups=setups, adjustments=setups)

    def test_full_conjugates_are_built_before_endpoint_preservation(self):
        with patch("subprocess.run", side_effect=AssertionError("palette construction is offline")):
            palette = self.palette()
            self.assertEqual((len(palette.bodies), len(palette.recipes)), (4, 19))
            records = {record["id"]: record for record in palette.recipe_records}
            corners = list(range(8))
            self.assertNotEqual(c.State().apply("U").corners, corners)
            conjugates = [algorithm for algorithm in palette.recipes
                          if records[algorithm.id]["body_id"] == "Ua"]
            self.assertEqual(len(conjugates), 4)
            for algorithm in conjugates:
                effect = c.State().apply(algorithm.turn_sequence)
                self.assertEqual(effect.corners, corners)
                self.assertEqual(algorithm.expression.evaluate(palette.generators),
                                 algorithm.permutation)
                self.assertEqual(palette.recipe_body_ids[algorithm.id], ("Ua",))
            self.assertTrue(palette.metadata["setup_undo_variants_built_before_preservation_filter"])

    def test_inverse_and_standalone_setup_permissions_are_explicit(self):
        body = AlgorithmPaletteBody("known", self.algorithms["Ua"], False)
        setup = AlgorithmPaletteSetup("align", self.algorithms["U"])
        restricted = AlgorithmPalette((body,), setups=(setup,))
        self.assertEqual(len(restricted.recipes), 2)
        self.assertEqual({record["exponent"] for record in restricted.recipe_records}, {1})
        self.assertTrue(all(record["body_id"] == "known" for record in restricted.recipe_records))
        admitted = AlgorithmPalette((replace(body, allow_inverse=True),), setups=(setup,),
                                   adjustments=(setup,))
        self.assertEqual(len(admitted.recipes), 5)
        self.assertEqual({record["exponent"] for record in admitted.recipe_records}, {1, -1})
        self.assertEqual(admitted.metadata["body_count"], 1)
        self.assertEqual({ids for ids in admitted.recipe_body_ids.values()}, {(), ("known",)})
        self.assertEqual([record["additive_htm"] for record in admitted.recipe_records
                          if record["setup_id"] is not None], [13, 13])
        with self.assertRaises(TypeError):
            admitted.recipe_body_ids["other"] = ("known",)
        bare_body = restricted.recipes[0].expression
        self.assertEqual(bare_body.kind, "turns")
        repeated = c.LoopExpression.sequence(bare_body, bare_body)
        self.assertEqual((repeated.children[0].kind, repeated.children[0].exponent), ("power", 2))
        self.assertEqual(repeated.children[0].children[0], bare_body)

    def test_stable_declaration_ids_survive_reordering_and_external_mutation(self):
        original = self.palette()
        reordered = AlgorithmPalette(tuple(reversed(original.bodies)),
                                     tuple(reversed(original.setups)), original.adjustments)
        self.assertEqual(dict(original.recipe_body_ids), dict(reordered.recipe_body_ids))
        record = original.recipe_records[0]
        record["body_id"] = "tampered"
        self.assertNotEqual(original.recipe_records[0]["body_id"], "tampered")
        self.assertFalse(original.metadata["coverage_claim"])

    def test_invalid_witnesses_and_references_are_rejected_offline(self):
        with patch("subprocess.run", side_effect=AssertionError("bad palettes cannot prepare groups")):
            with self.assertRaisesRegex(ValueError, "expression word"):
                AlgorithmPalette.from_algorithms((replace(self.algorithms["Ua"], turn_sequence="U"),))
            with self.assertRaisesRegex(ValueError, "expression word"):
                AlgorithmPalette.from_algorithms((replace(self.algorithms["Ua"],
                                                         turn_sequence="U U U U " + self.algorithms["Ua"].turn_sequence),))
            with self.assertRaisesRegex(ValueError, "original-loop action"):
                AlgorithmPalette.from_algorithms((replace(self.algorithms["Ua"],
                                                         permutation=self.algorithms["U"].permutation),))
            with self.assertRaisesRegex(ValueError, "different reference shape"):
                self.palette().validate(inventory=c.BlockInventory(c.Shape([1]*27)))
            with self.assertRaisesRegex(ValueError, "unique"):
                AlgorithmPalette((AlgorithmPaletteBody("same", self.algorithms["EO"]),
                                  AlgorithmPaletteBody("same", self.algorithms["Ua"])))
            with self.assertRaises(TypeError):
                AlgorithmPaletteBody("body", self.algorithms["EO"], allow_inverse=1)
            with self.assertRaisesRegex(TypeError, "LoopAlgorithm"):
                AlgorithmPalette.from_algorithms(("U",))
            for entrypoint in (c.select_human_chain, c.template_human_repertoire):
                with self.assertRaisesRegex(TypeError, "AlgorithmPalette"):
                    entrypoint(c.Shape(), backend="auto", palette=object())


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the small certified chain")
class AlgorithmPalettePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shape = c.Shape([1]*9 + [2]*18)
        cls.analysis = c.analyze_isotropy(cls.shape, timeout=30)
        cls.plan = c.plan_human_stages(cls.analysis, backend="symbolic", timeout=30)
        cls.palette = AlgorithmPalette.from_algorithms(
            algorithms_for(cls.analysis.loops, {"clockwise": "U"}).values(), allow_inverse=False)

    def test_direct_policy_repeats_allowed_sign_instead_of_inverting_body(self):
        from bce_v2.human_methods import _compile_plan
        baseline = _compile_plan(self.plan)
        # Equivalent longer fallback words make selection of the palette
        # corrections observable even for this four-state face-turn group.
        baseline = replace(baseline, algorithms=tuple(replace(a,
            turn_sequence="U U U U " + a.turn_sequence) for a in baseline.algorithms))
        with patch("subprocess.run", side_effect=AssertionError("prepared policy compilation is offline")):
            _, method, stats = _compile_dictionary_policy(self.plan, self.palette.recipes,
                {**_SEARCH_DEFAULTS, "max_word_length": 4, "max_states": 32},
                baseline=baseline, direct_corrections=True)
            self.assertGreater(stats["cases_improved"], 0)
            for algorithm in method.algorithms:
                def check(expression):
                    if expression.kind == "power":
                        self.assertGreaterEqual(expression.exponent, 0)
                    for child in expression.children:
                        check(child)
                check(algorithm.expression)
            for word in ("", "U", "U2", "U'"):
                self.assertTrue(method.apply(c.State(self.shape).apply(word)).state.is_solved)

    def test_palette_is_admitted_before_policy_selection_and_bypasses_mining_cap(self):
        with patch("bce_v2.symbolic_chain_search._compile_dictionary_policy",
                   wraps=_compile_dictionary_policy) as compile_policy:
            search = c.select_human_chain(self.analysis, backend="symbolic", palette=self.palette,
                max_expansions=0, max_methods=0, discovery_options={"max_candidates": 0}, timeout=30)
        self.assertEqual(search.metadata["palette"]["admitted_recipe_count"], 1)
        self.assertTrue(search.metadata["palette"]["admitted_before_policy_selection"])
        self.assertFalse(search.metadata["palette"]["strict_vocabulary"])
        for call in compile_policy.call_args_list:
            self.assertTrue(call.kwargs["direct_corrections"])
            self.assertEqual(call.args[1], self.palette.recipes)
        self.assertEqual(search.method.terminal_order, 1)

    def test_template_api_forwards_palette_to_preselection(self):
        with patch("bce_v2.human_chain_search.select_human_chain", wraps=c.select_human_chain) as select:
            repertoire = c.template_human_repertoire(self.analysis, backend="symbolic", palette=self.palette,
                max_chain_expansions=0, max_chain_methods=0, max_trials=0,
                discovery_options={"max_candidates": 0}, timeout=30)
        self.assertIs(select.call_args.kwargs["palette"], self.palette)
        self.assertEqual(repertoire.method.terminal_order, 1)

    def test_prepared_dictionary_route_is_preserved_with_a_palette(self):
        dictionary = c.discover_symbolic_dictionary(self.analysis, max_candidates=0, rounds=0,
            max_conjugates=0, max_familiar_candidates=0, timeout=30)
        saved = dictionary.to_json()
        with patch("bce_v2.symbolic_dictionary.discover_symbolic_dictionary",
                   side_effect=AssertionError("prepared dictionaries are not rediscovered")):
            search = c.select_human_chain(self.analysis, backend="symbolic", dictionary=dictionary,
                palette=self.palette, max_expansions=0, max_methods=0,
                discovery_options={"max_candidates": 0}, timeout=30)
        self.assertEqual(dictionary.to_json(), saved)
        self.assertEqual(search.metadata["discovery"], dictionary.metadata)
        self.assertEqual(search.metadata["palette"]["admitted_recipe_count"], 1)

    def test_forced_composite_goal_reaches_adaptive_planner(self):
        from bce_v2.symbolic_chain_search import _adaptive_plan
        cells = tuple(cell for block in self.analysis.block_inventory.blocks for cell in block.cells)
        goal = c.BlockFeature("solve_blocks", cells)
        plan, _, _ = _adaptive_plan(self.analysis, self.palette.recipes, kind=2,
            preference="execution", max_expansions=0, beam_width=1,
            forced_features=(goal,), max_schreier=0, timeout=30)
        self.assertEqual(plan.stages[0].feature, goal)
        self.assertEqual(plan.stages[0].order_after, 1)


if __name__ == "__main__":
    unittest.main()
