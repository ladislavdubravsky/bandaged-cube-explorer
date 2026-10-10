"""Independent certification, portable loading and large-group membership."""

from copy import deepcopy
import itertools
import json
import math
import unittest
from unittest.mock import patch

from bce_v2.symbolic_groups import (
    PermutationGroupCertificate, StabilizerLevel, StrongGenerator,
)


def symmetric_certificate(degree):
    roots = []
    for point in range(degree - 1):
        permutation = list(range(degree))
        permutation[point], permutation[point + 1] = point + 1, point
        roots.append(tuple(permutation))
    strong = tuple(StrongGenerator(permutation, ((index, 1),))
                   for index, permutation in enumerate(roots))
    levels = tuple(StabilizerLevel(point, tuple(range(point, degree - 1)))
                   for point in range(degree - 1))
    return PermutationGroupCertificate(tuple(roots), strong, levels, degree=degree)


class SymbolicGroupTests(unittest.TestCase):
    def test_exact_small_group_against_independent_permutation_listing(self):
        certificate = symmetric_certificate(3)
        self.assertEqual(certificate.order, 6)
        self.assertEqual(certificate.base, (0, 1))
        self.assertEqual(certificate.orbit_sizes, (3, 2))
        for permutation in itertools.permutations(range(3)):
            self.assertIn(permutation, certificate)
            self.assertEqual(certificate.sift(permutation), (0, 1, 2))

    def test_proper_subgroup_membership_and_signed_witness(self):
        cycle, transposition = (1, 2, 0), (1, 0, 2)
        inverse = (2, 0, 1)
        certificate = PermutationGroupCertificate(
            (cycle, transposition),
            (StrongGenerator(inverse, ((0, -1),)),),
            (StabilizerLevel(0, (0,)),),
            input_generators=(cycle,),
        )
        self.assertEqual(certificate.order, 3)
        self.assertIn(cycle, certificate)
        self.assertNotIn(transposition, certificate)
        self.assertNotEqual(certificate.sift(transposition), (0, 1, 2))
        # The default checks the complete ambient input library, so a subgroup
        # cannot silently masquerade as a full-group certificate.
        with self.assertRaisesRegex(ValueError, "input generator"):
            PermutationGroupCertificate(
                (cycle, transposition), certificate.strong_generators,
                certificate.levels,
            )

    def test_noncommuting_witness_uses_execution_order(self):
        roots = ((1, 0, 2), (0, 2, 1))
        cycle = (2, 0, 1)
        certificate = PermutationGroupCertificate(
            roots, (StrongGenerator(cycle, ((0, 1), (1, 1))),),
            (StabilizerLevel(0, (0,)),), input_generators=(cycle,),
        )
        self.assertEqual(certificate.order, 3)
        with self.assertRaisesRegex(ValueError, "wrong effect"):
            PermutationGroupCertificate(
                roots, (StrongGenerator((1, 2, 0), ((0, 1), (1, 1))),),
                certificate.levels, input_generators=(cycle,),
            )

    def test_large_group_has_tiny_certificate_and_offline_membership(self):
        certificate = symmetric_certificate(12)
        self.assertEqual(certificate.order, math.factorial(12))
        self.assertGreater(certificate.order, 100_000_000)
        self.assertEqual(len(certificate.strong_generators), 11)
        self.assertEqual(sum(certificate.orbit_sizes), 77)
        encoded = json.loads(json.dumps(certificate.to_dict()))
        with patch("subprocess.run", side_effect=AssertionError("must work offline")):
            restored = PermutationGroupCertificate.from_dict(encoded)
            self.assertIn(tuple(reversed(range(12))), restored)
            self.assertIn(tuple(range(1, 12)) + (0,), restored)
        self.assertEqual(restored.order, certificate.order)

    def test_trivial_group_has_no_base_and_no_nonidentity_members(self):
        certificate = PermutationGroupCertificate((), (), (), degree=4)
        self.assertEqual(certificate.order, 1)
        self.assertEqual(certificate.orbit_sizes, ())
        self.assertIn((0, 1, 2, 3), certificate)
        self.assertNotIn((1, 0, 2, 3), certificate)
        self.assertEqual(PermutationGroupCertificate.from_dict(certificate.to_dict()).order, 1)

    def test_incomplete_strong_generators_fail_schreier_closure(self):
        # The two generators move every base point, so none enter the alleged
        # first stabilizer.  The omitted (1 2) Schreier generator proves the
        # claimed order-three chain incomplete, although terminal checks pass.
        roots = ((1, 2, 0), (1, 0, 2))
        with self.assertRaisesRegex(ValueError, "Schreier generator"):
            PermutationGroupCertificate(
                roots,
                tuple(StrongGenerator(permutation, ((index, 1),))
                      for index, permutation in enumerate(roots)),
                (StabilizerLevel(0, (0, 1)),),
            )

    def test_false_witness_and_nontrivial_terminal_stabilizer_are_rejected(self):
        root = (1, 0, 2)
        with self.assertRaisesRegex(ValueError, "wrong effect"):
            PermutationGroupCertificate(
                (root,), (StrongGenerator((0, 2, 1), ((0, 1),)),),
                (StabilizerLevel(1, (0,)),),
            )
        with self.assertRaisesRegex(ValueError, "terminal stabilizer"):
            PermutationGroupCertificate((root,), (StrongGenerator(root, ((0, 1),)),), ())

    def test_saved_certificate_tampering_is_detected_without_gap(self):
        data = symmetric_certificate(3).to_dict()
        corruptions = [
            (lambda value: value.__setitem__("order", "3"), "order"),
            (lambda value: value["strong_generators"][0]["syllables"].__setitem__(0, [1, 1]),
             "wrong effect"),
            (lambda value: value["levels"][0].__setitem__("generator_indices", [0]),
             "all strong generators"),
            (lambda value: value["levels"][1].__setitem__("generator_indices", [0, 1]),
             "all strong generators"),
            (lambda value: value.__setitem__("levels", value["levels"][:1]),
             "terminal stabilizer"),
            (lambda value: value.__setitem__("degree", True), "integer"),
            (lambda value: value.__setitem__("unexpected", 1), "fields"),
        ]
        for corrupt, message in corruptions:
            with self.subTest(message=message):
                changed = deepcopy(data)
                corrupt(changed)
                with self.assertRaisesRegex((TypeError, ValueError), message):
                    PermutationGroupCertificate.from_dict(changed)

    def test_bad_target_is_distinct_from_valid_nonmembership(self):
        certificate = symmetric_certificate(3)
        for invalid in ((0, 0, 1), (0, 1), (False, 1, 2), (0.0, 1, 2)):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                certificate.contains(invalid)


if __name__ == "__main__":
    unittest.main()
