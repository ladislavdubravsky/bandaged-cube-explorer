"""Human templates share witnessed bodies without expanding the reference group."""

from copy import deepcopy
import gc
import shutil
import unittest
from unittest.mock import patch
import weakref

import bce_v2 as c
from bce_v2.human_method_io import _fingerprint
from bce_v2.human_instruction_render import instruction_presentation
from bce_v2.loop_rotations import rotate_moves


class SymbolicTemplateArgumentTests(unittest.TestCase):
    def test_invalid_options_fail_before_external_work(self):
        invalid = ({"backend": "large"}, {"max_group_elements": 100},
            {"max_trials": True}, {"max_trials": -1}, {"max_applications": -1},
            {"max_word_candidates": 1.5}, {"max_word_frontier": 0}, {"beam_width": 0},
            {"max_chain_expansions": -1}, {"max_chain_methods": True},
            {"allow_symmetry": 0}, {"select_chain": "yes"}, {"preference": "fast"},
            {"max_cost_ratio": True}, {"max_cost_ratio": float("nan")},
            {"chunk_options": {"unknown": 1}}, {"chunk_options": {"max_chunks": True}},
            {"templates": ("U",)}, {"root": True}, {"discovery_options": []},
            {"dictionary_options": []}, {"dictionary": object()})
        with patch("subprocess.run", side_effect=AssertionError("invalid options must not prepare GAP groups")):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises((TypeError, ValueError)):
                    c.template_human_repertoire(c.Shape([0] * 27), backend=options.get("backend", "symbolic"),
                        **{k: v for k, v in options.items() if k != "backend"})


@unittest.skipUnless(shutil.which("gap"), "GAP prepares the certified test chain")
class SymbolicTemplateRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.method = c.synthesize_human_method(c.Shape([1] * 9 + [2] * 18),
            strategy="fully_solve_each_block", backend="symbolic", timeout=30)
        with patch("subprocess.run", side_effect=AssertionError("supplied symbolic methods are offline")):
            cls.repertoire = c.template_human_repertoire(cls.method, max_trials=4,
                max_word_candidates=128, max_word_frontier=32, chunk_options={"max_candidates": 0})

    def test_native_turns_use_singmaster_notation_and_exact_frames(self):
        repertoire = self.repertoire
        self.assertEqual(repertoire.metadata["construction"], "symbolic_template_search")
        self.assertEqual(repertoire.metadata["selected_metrics"]["learned_body_count"], 0)
        for stage in repertoire.stages:
            for case in stage.cases:
                if case.instruction is None:
                    continue
                presentation = instruction_presentation(case.instruction, repertoire,
                    rotate_diagram=False, preserve_templates=True)
                self.assertNotIn("M", presentation.identifier)
                self.assertNotIn("rotate", presentation.identifier)
                expression = case.recipe.loop_expression(repertoire.macros)
                physical = expression.expanded_moves(repertoire.method.generators)
                from bce_v2._moves import _simplified_moves
                self.assertEqual(presentation.turn_sequence, _simplified_moves(physical.split()))
                rotated = instruction_presentation(case.instruction, repertoire,
                    rotate_diagram=True, preserve_templates=True)
                self.assertEqual(rotate_moves(rotated.turn_sequence, rotated.rotation),
                                 presentation.turn_sequence)
        guide = repertoire.write_guide()
        self.assertIn("Stage 1", guide)
        self.assertNotIn("`M1:", guide)

    def test_supplied_method_roundtrip_remains_offline_and_complete(self):
        with patch("subprocess.run", side_effect=AssertionError("loading and solving use portable certificates")), \
             patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no reference-group closure")):
            loaded = c.HumanRepertoire.from_dict(self.repertoire.to_dict())
            self.assertEqual(loaded.to_json(), self.repertoire.to_json())
            for moves in ("", "U", "U2", "U'"):
                source = c.State(self.method.reference_shape).apply(moves)
                solved = loaded.apply(source)
                self.assertTrue(solved.state.is_solved)
                self.assertEqual(source.apply(solved.turn_sequence), solved.state)
        self.assertEqual(loaded.method.additive_costs(), self.method.additive_costs())

    def test_zero_quality_work_keeps_the_exact_fallback(self):
        repertoire = c.template_human_repertoire(self.method, max_trials=0,
            max_applications=0, max_word_candidates=0, chunk_options={"max_word_moves": 0})
        self.assertEqual(repertoire.metadata["selected_id"], "C1")
        self.assertEqual(repertoire.metadata["search"]["expression_nodes_examined"], 0)
        self.assertEqual(repertoire.metadata["search"]["accepted_shared_bodies"], 0)
        self.assertEqual(repertoire.method.additive_costs(), self.method.additive_costs())

    def test_expression_caches_release_their_method_context(self):
        from bce_v2.symbolic_template_repertoire import _Bodies
        context = _Bodies(self.method, True)
        expression = c.LoopExpression.loop(self.method.generators[0].id)
        context.word(expression)
        context.alias(expression)
        reference = weakref.ref(context)
        del context
        gc.collect()
        self.assertIsNone(reference())

    def test_saved_costs_and_search_ceilings_are_recomputed(self):
        changes = (
            lambda m: m["selected_metrics"].__setitem__("description_score", 0),
            lambda m: m["selected_metrics"].__setitem__("learned_body_count", 50),
            lambda m: m["selected_metrics"].__setitem__("instruction_symbols", 0),
            lambda m: m["search"].__setitem__("accepted_shared_bodies", 100),
            lambda m: m["search"].__setitem__("group_elements_enumerated", 1),
            lambda m: m.__setitem__("cost_scope", "sampled"),
            lambda m: m.__setitem__("rotations", []),
        )
        with patch("subprocess.run", side_effect=AssertionError("saved validation is offline")), \
             patch("bce_v2.human_chunks.extract_algorithm_chunks", side_effect=AssertionError("loading does not mine")):
            for change in changes:
                record = deepcopy(self.repertoire.to_dict())
                change(record["metadata"])
                record["fingerprint"] = _fingerprint(record)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    c.HumanRepertoire.from_dict(record)

    def test_public_symbolic_shape_api_prepares_a_certified_repertoire(self):
        with patch("bce_v2.human_chains._enumerate", side_effect=AssertionError("no group closure")), \
             patch("bce_v2.human_chain_search.select_human_chain", wraps=c.select_human_chain) as select:
            repertoire = c.template_human_repertoire(c.Shape([1] * 27), backend="symbolic",
                max_chain_expansions=0, max_chain_methods=0, max_word_candidates=0, timeout=30)
        self.assertEqual(repertoire.method.group_order, 1)
        self.assertEqual(repertoire.macros, ())
        self.assertEqual(select.call_args.kwargs["backend"], "symbolic")
        self.assertEqual(select.call_args.kwargs["dictionary_options"]["max_setup_words"], 384)
        self.assertEqual(repertoire.metadata["search"]["group_elements_enumerated"], 0)


if __name__ == "__main__":
    unittest.main()
