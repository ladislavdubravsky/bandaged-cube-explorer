"""Dictionary-aware chains retain complete controls and portable correctness."""

from dataclasses import replace
import json
import shutil
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.symbolic_chain_search import select_symbolic_human_chain


def imported(state):
    return c.State.from_cubies(state.specification,corners=state.corners,twists=state.twists,
                              edges=state.edges,flips=state.flips)


class SymbolicChainArgumentTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gap"), "GAP is required for a trivial prepared control")
    def test_automatic_dictionary_defaults_include_commutator_discovery(self):
        with patch("bce_v2.symbolic_dictionary.discover_symbolic_dictionary",
                   wraps=c.discover_symbolic_dictionary) as discover:
            search = c.select_human_chain(c.Shape([1] * 27), backend="symbolic",
                                           max_expansions=0, max_methods=0, timeout=30)
        self.assertEqual(discover.call_args.kwargs["rounds"], 4)
        self.assertEqual(search.method.terminal_order, 1)

    def test_invalid_arguments_are_rejected_before_group_preparation(self):
        with patch("subprocess.run",side_effect=AssertionError("invalid options must not start GAP")):
            for kwargs in ({"dictionary":object()},{"dictionary_options":[]},
                           {"dictionary_options":{"unknown":2}},
                           {"discovery_options":{"max_candidates":True}},
                           {"max_expansions":-1},{"max_methods":True}):
                with self.subTest(kwargs=kwargs),self.assertRaises((TypeError,ValueError)):
                    select_symbolic_human_chain(c.Shape([0]*27),**kwargs)


@unittest.skipUnless(shutil.which("gap"),"GAP is required to prepare adaptive feature chains")
class SymbolicChainSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = c.analyze_isotropy(c.fixture("Alcatraz"),timeout=30)
        cls.explicit = c.plan_human_stages(cls.analysis,timeout=30)
        cls.dictionary = c.discover_symbolic_dictionary(
            cls.analysis,max_candidates=512,rounds=2,max_algorithms=128,
            max_setup_words=32,max_conjugates=256)
        with patch("bce_v2.human_chains._enumerate",side_effect=AssertionError("no full-group enumeration")):
            cls.search = c.select_human_chain(
                cls.analysis,backend="symbolic",dictionary=cls.dictionary,
                max_expansions=4,max_methods=1,beam_width=1,
                discovery_options={"max_candidates":2000,"max_states":2000,"max_word_length":8},
                timeout=45)

    def test_selection_preserves_complete_controls_and_exact_cost_scope(self):
        search = self.search
        self.assertEqual(search.status,"completed")
        sources = {candidate.source for candidate in search.candidates}
        for strategy in ("fully_solve_each_block","placement_then_orientation"):
            self.assertIn("fallback:"+strategy,sources)
            self.assertIn("dictionary:"+strategy,sources)
        self.assertIn("dictionary:adaptive:1",sources)
        self.assertLessEqual(search.method.additive_costs()["htm"]["mean"],
                             search.baseline.additive_costs()["htm"]["mean"])
        self.assertLessEqual(search.metadata["nodes_expanded"],4)
        self.assertLessEqual(search.metadata["adaptive_schreier_proposals"],
                             2000-len(self.dictionary.algorithms))
        self.assertIn("before_boundary_cancellation",search.method.additive_costs()["scope"])
        self.assertEqual(search.method.terminal_order,1)

    def test_every_small_group_element_solves_and_selected_artifact_is_offline(self):
        with patch("subprocess.run",side_effect=AssertionError("application and artifact loading are offline")):
            method = c.HumanMethod.from_dict(self.search.method.to_dict())
            for permutation in self.explicit.group.permutations:
                moves = self.explicit.group.witness(permutation).expanded_moves(self.explicit.group.generators)
                source = imported(c.State(method.reference_shape).apply(moves))
                solved = method.apply(source)
                self.assertEqual(solved.status,"solved")
                self.assertTrue(solved.state.is_solved)
                self.assertEqual(source.apply(solved.turn_sequence),solved.state)

    def test_zero_work_still_keeps_both_complete_fallback_controls(self):
        search = select_symbolic_human_chain(
            self.analysis,dictionary=self.dictionary,max_expansions=0,max_methods=0,
            discovery_options={"max_candidates":0,"max_states":0},timeout=30)
        self.assertEqual(search.method.terminal_order,1)
        self.assertEqual(len(search.candidates),4)
        self.assertFalse(search.metadata["adaptive_chains"])
        self.assertEqual(search.metadata["adaptive_schreier_proposals"],0)

    def test_dictionary_target_orders_are_checked_against_exact_certificates(self):
        metadata = self.dictionary.metadata
        metadata["quotient_order"] *= 2
        corrupted = replace(self.dictionary,_metadata_json=json.dumps(metadata))
        with self.assertRaisesRegex(ValueError,"exact-order metadata"):
            select_symbolic_human_chain(self.analysis,dictionary=corrupted,
                                        max_expansions=0,max_methods=0,timeout=30)


if __name__ == "__main__":
    unittest.main()
