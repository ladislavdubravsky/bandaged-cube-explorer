"""Bounded nearby-shape transport keeps exact replay and original proofs."""

import json
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.familiar_algorithm_catalog import FamiliarAlgorithm, FamiliarAlgorithmCatalog
from bce_v2.familiar_algorithm_transport import discover_familiar_algorithms
from bce_v2.human_witnesses import stored_loop_generators


COMMUTATOR = "R U R' U'"
FOUR_PAIR = [0, 0, 0, 0, 0, 0, 0, 0, 0,
             1, 0, 2, 0, 0, 0, 3, 0, 4,
             1, 0, 2, 0, 0, 0, 3, 0, 4]


def catalog(*words):
    entries = tuple(FamiliarAlgorithm.from_word(word, id=f"word{index}", family=family)
                    for index, (family, word) in enumerate(words))
    return FamiliarAlgorithmCatalog(entries, entries)


def metadata(library):
    return library.metadata["familiar_transport"]


def inverse(word):
    return " ".join(move if move.endswith("2") else move[:-1] if move.endswith("'")
                    else move + "'" for move in reversed(word.split()))


class FamiliarTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        labels = [0] * 27
        labels[c.FR] = labels[c.DFR] = 1
        cls.pair = c.Shape(labels)
        cls.pair_loops = c.isotropy_loops(cls.pair)
        cls.ordinary_loops = c.isotropy_loops(c.Shape())
        cls.four_pair_loops = c.isotropy_loops(c.Shape(FOUR_PAIR))
        cls.comm_catalog = catalog(("commutator", COMMUTATOR))

    def discover(self, initial, **kwargs):
        return discover_familiar_algorithms(initial, catalog=self.comm_catalog,
                                            max_seconds=None, **kwargs)

    def assert_transports(self, library):
        records = metadata(library)["algorithms"]
        self.assertEqual(set(records), {algorithm.id for algorithm in library.algorithms})
        for algorithm in library.algorithms:
            with self.subTest(algorithm=algorithm.id):
                record = records[algorithm.id]
                self.assertEqual(algorithm.expression.kind, "turns")
                setup_shape = library.loops.root_shape.apply(record["setup"])
                self.assertEqual(setup_shape.apply(record["body"]), setup_shape)
                raw = " ".join((record["setup"], record["body"], record["undo"]))
                physical = c.State(library.loops.root_shape).apply(raw)
                self.assertEqual(physical.shape, library.loops.root_shape)
                self.assertEqual(physical.sticker_permutation, algorithm.permutation)
                self.assertEqual(c.State(library.loops.root_shape).apply(algorithm.moves), physical)
                # Independently execute the retained original-loop child;
                # it can be much longer than the literal physical witness.
                proof_state = c.State(library.loops.root_shape)
                witness = algorithm.expression.children[0]
                for identifier, power in witness.loop_steps():
                    word = library.loops.generator_records[identifier].moves
                    for _ in range(abs(power)):
                        proof_state = proof_state.apply(word if power > 0 else inverse(word))
                self.assertEqual(proof_state, physical)
                self.assertEqual(record["conjugate"], algorithm.moves)

    def test_open_root_commutator_is_found_at_a_different_shape_without_gap(self):
        self.assertNotEqual(self.pair.apply(COMMUTATOR), self.pair)
        with patch("bce_v2.gap_backend.analyze_generators", side_effect=AssertionError("GAP called")):
            library = self.discover(self.pair_loops, max_setup_depth=1)
        self.assertIs(library.loops, self.pair_loops)
        self.assertTrue(any(a.moves == "F R U R' U' F'" for a in library.algorithms))
        self.assertTrue(any(a.moves == "F U R U' R' F'" for a in library.algorithms))
        self.assert_transports(library)
        self.assertEqual(metadata(library)["available_words"], 1)
        self.assertEqual(metadata(library)["setup_metric"], "HTM")

    def test_legality_without_closure_is_not_an_algorithm(self):
        library = self.discover(self.pair_loops, max_setup_depth=0)
        self.assertFalse(library.algorithms)
        self.assertEqual(metadata(library)["legal_occurrences"], 1)
        self.assertEqual(metadata(library)["closed_occurrences"], 0)
        self.assertTrue(metadata(library)["limit_reached"]["depth"])

    def test_temporary_extraction_does_not_require_all_faces_free_initially(self):
        labels = [0] * 27
        labels[c.UR] = labels[c.R] = 1
        root = c.Shape(labels)
        self.assertFalse(root.is_turnable("U"))
        word = "R U R' D R U' R' D'"
        library = discover_familiar_algorithms(root, catalog=catalog(("nested", word)),
                                               max_seconds=None, max_setup_depth=0)
        self.assertEqual(len(library.algorithms), 2)
        self.assertTrue(all(record["setup"] == "" for record in metadata(library)["algorithms"].values()))
        self.assert_transports(library)

    def test_half_turn_setup_is_shortest_htm_and_can_shorten_body_boundaries(self):
        word = "R U' R U R U R U' R' U' R2"
        library = discover_familiar_algorithms(self.four_pair_loops,
                                               catalog=catalog(("edge_cycle", word)),
                                               max_setup_depth=1, max_seconds=None,
                                               max_htm_length=10, max_expanded_moves=10)
        self.assertEqual(len(library.algorithms), 2)
        records = metadata(library)["algorithms"].values()
        self.assertTrue(all(record["setup"] == "R2" and record["setup_htm"] == 1
                            and record["body_htm"] == 11 for record in records))
        self.assertTrue(all(algorithm.htm_length == 10 for algorithm in library.algorithms))
        self.assertTrue(any(algorithm.moves == "R' U' R U R U R U' R' U'"
                            for algorithm in library.algorithms))
        self.assert_transports(library)

    def test_provenance_budget_is_independent_of_the_short_physical_word(self):
        library = self.discover(self.pair_loops, max_setup_depth=1,
                                max_expanded_moves=6, max_htm_length=6, max_proof_moves=12)
        record = next(record for record in metadata(library)["algorithms"].values()
                      if record["conjugate"] == "F R U R' U' F'")
        self.assertEqual(record["proof_qtm"], 12)
        pruned = self.discover(self.pair_loops, max_setup_depth=1,
                               max_expanded_moves=6, max_proof_moves=11)
        self.assertTrue(metadata(pruned)["proof_pruned_count"])
        self.assertFalse(any(a.moves == "F R U R' U' F'" for a in pruned.algorithms))
        self.assertIs(pruned.loops, self.pair_loops)

    def test_work_shape_candidate_and_length_caps_return_certified_partial_results(self):
        limited = self.discover(self.pair_loops, max_work=100, max_candidates=1)
        self.assertLessEqual(metadata(limited)["work"], 100)
        self.assertEqual(metadata(limited)["candidates_examined"], 1)
        self.assertTrue(metadata(limited)["limit_reached"]["candidates"])
        self.assert_transports(limited)
        single_shape = self.discover(self.pair_loops, max_shapes=1)
        self.assertEqual(metadata(single_shape)["shapes_seen"], 1)
        self.assertEqual(metadata(single_shape)["shapes_scanned"], 1)
        self.assertFalse(single_shape.algorithms)
        self.assertTrue(metadata(single_shape)["limit_reached"]["shapes"])
        too_long = self.discover(self.pair_loops, max_htm_length=3)
        self.assertFalse(too_long.algorithms)
        self.assertTrue(metadata(too_long)["length_pruned_count"])
        self.assertEqual(metadata(too_long)["available_words"], 1)

    def test_shortlist_reserves_distinct_body_families(self):
        words = catalog(("commutator", COMMUTATOR),
                        ("edge_cycle", "R2 U R U R' U' R' U' R' U R'"),
                        ("OLL", "R U R' U R U2 R'"))
        library = discover_familiar_algorithms(self.ordinary_loops, catalog=words,
                                               max_seconds=None, max_candidates=6)
        self.assertEqual({record["family"] for record in metadata(library)["algorithms"].values()},
                         {"commutator", "edge_cycle", "OLL"})
        self.assert_transports(library)

    def test_zero_budgets_and_deadline_skip_work_without_losing_the_native_library(self):
        for limit in ("max_work", "max_shapes", "max_candidates"):
            with self.subTest(limit=limit):
                library = self.discover(self.ordinary_loops, **{limit: 0})
                self.assertFalse(library.algorithms)
                self.assertIs(library.loops, self.ordinary_loops)
                self.assertEqual(metadata(library)["work"], 0)
                self.assertEqual(metadata(library)["stop_reason"], limit)
        with patch("bce_v2.familiar_algorithm_transport.monotonic", side_effect=[0, 1, 1]):
            library = discover_familiar_algorithms(self.ordinary_loops, catalog=self.comm_catalog,
                                                   max_seconds=.5)
        self.assertFalse(library.algorithms)
        self.assertTrue(metadata(library)["limit_reached"]["time"])

    def test_existing_library_candidates_and_portable_native_fallback_are_retained(self):
        base = c.discover_loop_algorithms(self.ordinary_loops, rounds=0, max_seed_loops=1)
        library = self.discover(base)
        self.assertIs(library.loops, base.loops)
        self.assertTrue({a.permutation for a in base.algorithms}.issubset(
            {a.permutation for a in library.algorithms}))
        records = self.ordinary_loops.to_dict()["generators"]
        generators = stored_loop_generators(records, self.ordinary_loops.block_inventory,
                                            0, self.ordinary_loops)
        portable_base = c.discover_loop_algorithms(generators[0]._library, rounds=0, max_seed_loops=1)
        skipped = self.discover(portable_base)
        self.assertEqual(skipped.algorithms, portable_base.algorithms)
        self.assertIs(skipped.loops, portable_base.loops)
        self.assertEqual(metadata(skipped)["stop_reason"], "native_certification_unavailable")
        self.assertEqual(metadata(skipped)["work"], 0)

    def test_repeated_unlimited_discovery_has_deterministic_serialization(self):
        first = self.discover(self.pair_loops, max_setup_depth=1)
        second = self.discover(self.pair_loops, max_setup_depth=1)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(json.loads(first.to_json())["metadata"]["familiar_transport"], metadata(first))

    def test_invalid_limits_and_unverified_catalog_are_rejected_before_exploration(self):
        for kwargs, error in (({"max_work": -1}, ValueError),
                              ({"max_setup_depth": True}, TypeError),
                              ({"max_seconds": float("nan")}, ValueError),
                              ({"max_seconds": "fast"}, TypeError),
                              ({"max_proof_moves": -1}, ValueError),
                              ({"catalog": object(), "max_work": 0}, TypeError)):
            with self.subTest(kwargs=kwargs), patch(
                    "bce_v2.familiar_algorithm_transport._reference",
                    side_effect=AssertionError("reference prepared before limit validation")):
                with self.assertRaises(error):
                    discover_familiar_algorithms(self.pair, **kwargs)


if __name__ == "__main__":
    unittest.main()
