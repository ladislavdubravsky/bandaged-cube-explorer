"""Exact quotient/kernel protocol and live nonsplit-extension checks."""

from dataclasses import FrozenInstanceError
import shutil
import subprocess
import unittest
from unittest.mock import patch

from bce_v2.block_gap import (
    GapBlockStructure, GapKernelFactorization, GapKernelGenerator,
    analyze_block_structure, factor_block_permutation, factor_kernel,
)
from bce_v2.gap_backend import GapError, GapTimeoutError, GapUnavailableError


IDENTITY = tuple(range(48))


def cycle(*points):
    images = list(IDENTITY)
    for source, target in zip(points, points[1:] + points[:1]):
        images[source] = target
    return tuple(images)


QUARTER = cycle(0, 1, 2, 3)
HALF = tuple(QUARTER[point] for point in QUARTER)


def structure_protocol(*, order=4, quotient=2, kernel=2, basis_order=2,
                       permutation=HALF, word="0:2", version="4.12.1"):
    return ("__BCE_GAP_BLOCK_V1_BEGIN__\n" + f"version={version}\norder={order}\n"
            + f"quotient_order={quotient}\nkernel_order={kernel}\nbasis_count=1\n"
            + f"basis={basis_order}|{','.join(map(str,permutation))}|{word}\n"
            + "__BCE_GAP_BLOCK_V1_END__\n")


def kernel_protocol(*, order=2, reachable="true", exponents="1"):
    return ("__BCE_GAP_KERNEL_V1_BEGIN__\nversion=4.12.1\n"
            + f"order={order}\nreachable={reachable}\nexponents={exponents}\n"
            + "__BCE_GAP_KERNEL_V1_END__\n")


def completed(output):
    return subprocess.CompletedProcess([], 0, output, "")


class BlockGapProtocolTests(unittest.TestCase):
    def test_paired_projection_preserves_full_order_kernel_witness(self):
        with patch("bce_v2.gap_backend.subprocess.run",
                   return_value=completed(structure_protocol())) as run:
            result = analyze_block_structure([QUARTER], [(1, 0)], timeout=2)
        self.assertEqual(result, GapBlockStructure(4, 2, 2,
                         (GapKernelGenerator(HALF, 2, ((0, 2),)),), "4.12.1"))
        program = run.call_args.kwargs["input"]
        self.assertIn("GroupHomomorphismByImages(H, P, permutations, projections)", program)
        self.assertNotIn("GroupHomomorphismByImagesNC", program)
        self.assertIn("rec(random := 1000)", program)
        self.assertIn("IndependentGeneratorsOfAbelianGroup(K)", program)
        self.assertIn("PreImagesRepresentative(epi, generator)", program)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        with self.assertRaises(FrozenInstanceError):
            result.kernel_order = 3

    def test_corrupt_structure_or_witness_is_inconclusive(self):
        good = structure_protocol()
        invalid = ["", good + good, good.replace("__BCE_GAP_BLOCK_V1_END__", ""),
                   good.replace("basis_count=1", "basis_count=0"),
                   structure_protocol(order=5), structure_protocol(quotient=3),
                   structure_protocol(kernel=4), structure_protocol(basis_order=3),
                   structure_protocol(word="0:1"), structure_protocol(word="1:2"),
                   structure_protocol(word="0:0"), structure_protocol(permutation=IDENTITY),
                   structure_protocol(permutation=(0,) * 48),
                   structure_protocol(version="bad"), structure_protocol(order="9" * 5000)]
        for output in invalid:
            with self.subTest(output=output[:100]), patch("bce_v2.gap_backend.subprocess.run",
                    return_value=completed(output)):
                with self.assertRaises(GapError):
                    analyze_block_structure([QUARTER], [(1, 0)])
        # The sticker witness alone is insufficient: its block image must fix
        # every footprint, including separate fixed center/core slots.
        with patch("bce_v2.gap_backend.subprocess.run",
                   return_value=completed(structure_protocol(quotient=4, order=8))):
            with self.assertRaises(GapError):
                analyze_block_structure([QUARTER], [(1, 2, 3, 0)])

    def test_input_validation_and_subprocess_failures(self):
        invalid = [([QUARTER], [], ValueError), ([QUARTER], [(0, 0)], ValueError),
                   ([QUARTER], [(False, 1)], TypeError),
                   ([QUARTER, QUARTER], [(0, 1), (0,)], ValueError),
                   ([QUARTER], [tuple(range(49))], ValueError)]
        with patch("bce_v2.gap_backend.subprocess.run") as run:
            for images, blocks, expected in invalid:
                with self.subTest(blocks=blocks), self.assertRaises(expected):
                    analyze_block_structure(images, blocks)
            run.assert_not_called()
        for error, expected in [(FileNotFoundError("missing"), GapUnavailableError),
                                (subprocess.TimeoutExpired("gap", 0.1), GapTimeoutError)]:
            with patch("bce_v2.gap_backend.subprocess.run", side_effect=error):
                with self.assertRaises(expected):
                    analyze_block_structure([], [], timeout=0.1)

    def test_dependent_kernel_bases_with_valid_words_are_rejected(self):
        first, second, third = cycle(0, 1), cycle(2, 3), cycle(4, 5)
        combined = tuple(second[point] for point in first)
        cases = [([first, second], [(first, "0:1"), (first, "0:1")]),
                 ([first, second, third],
                  [(first, "0:1"), (second, "1:1"), (combined, "0:1,1:1")])]
        for images, basis in cases:
            order = 2 ** len(images)
            output = ("__BCE_GAP_BLOCK_V1_BEGIN__\nversion=4.12.1\n"
                      + f"order={order}\nquotient_order=1\nkernel_order={order}\n"
                      + f"basis_count={len(basis)}\n"
                      + "".join("basis=2|" + ",".join(map(str, permutation)) + "|" + word + "\n"
                                for permutation, word in basis)
                      + "__BCE_GAP_BLOCK_V1_END__\n")
            with self.subTest(basis=basis), patch("bce_v2.gap_backend.subprocess.run",
                    return_value=completed(output)):
                with self.assertRaisesRegex(GapError, "dependent"):
                    analyze_block_structure(images, [(0,)] * len(images))
        # A valid coefficient product alone cannot certify independence.
        with patch("bce_v2.gap_backend.subprocess.run",
                   return_value=completed(kernel_protocol(order=4, exponents="1,0"))):
            with self.assertRaisesRegex(GapError, "invalid independent"):
                factor_kernel([first, first], first)

    def test_large_independent_basis_is_checked_without_group_enumeration(self):
        images = [cycle(point, point + 1) for point in range(0, 48, 2)]
        order = 2 ** len(images)
        output = ("__BCE_GAP_BLOCK_V1_BEGIN__\nversion=4.12.1\n"
                  + f"order={order}\nquotient_order=1\nkernel_order={order}\n"
                  + f"basis_count={len(images)}\n"
                  + "".join("basis=2|" + ",".join(map(str, permutation)) + f"|{index}:1\n"
                            for index, permutation in enumerate(images))
                  + "__BCE_GAP_BLOCK_V1_END__\n")
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(output)):
            result = analyze_block_structure(images, [(0,)] * len(images))
        self.assertEqual((result.group_order, result.kernel_order), (order, order))
        self.assertEqual(len(result.basis), 24)

    def test_kernel_coefficients_are_checked_against_supplied_basis(self):
        with patch("bce_v2.gap_backend.subprocess.run",
                   return_value=completed(kernel_protocol())) as run:
            result = factor_kernel([HALF], HALF)
        self.assertEqual(result, GapKernelFactorization(True, (1,), 2, "4.12.1"))
        self.assertIn("SetIndependentGeneratorsOfAbelianGroup(K, basis)", run.call_args.kwargs["input"])
        self.assertIn("IndependentGeneratorExponents(K, target)", run.call_args.kwargs["input"])
        invalid = ["", kernel_protocol() + kernel_protocol(), kernel_protocol(order=3),
                   kernel_protocol(exponents=""), kernel_protocol(exponents="0"),
                   kernel_protocol(exponents="1,1"), kernel_protocol(exponents="2"),
                   kernel_protocol(exponents="01"), kernel_protocol(reachable="false"),
                   kernel_protocol(exponents="9" * 5000)]
        for output in invalid:
            with self.subTest(output=output[:100]), patch("bce_v2.gap_backend.subprocess.run",
                    return_value=completed(output)):
                with self.assertRaises(GapError):
                    factor_kernel([HALF], HALF)
        with patch("bce_v2.gap_backend.subprocess.run",
                   return_value=completed(kernel_protocol(reachable="false", exponents=""))):
            self.assertFalse(factor_kernel([HALF], QUARTER).reachable)
            with self.assertRaises(GapError):
                factor_kernel([HALF], IDENTITY)


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external executable")
class LiveBlockGapTests(unittest.TestCase):
    def test_nonsplit_cyclic_extension_and_literal_quotient_lift(self):
        structure = analyze_block_structure([QUARTER], [(1, 0)], timeout=15)
        self.assertEqual((structure.group_order, structure.quotient_order, structure.kernel_order),
                         (4, 2, 2))
        self.assertEqual(structure.basis[0].permutation, HALF)
        self.assertEqual(structure.basis[0].syllables, ((0, 2),))
        # An element with sticker order four has image of order two. Its
        # inverse quotient solution lifts to QUARTER, leaving HALF in K.
        quotient = factor_block_permutation([(1, 0)], (1, 0), timeout=15)
        self.assertEqual(quotient.syllables, ((0, 1),))
        kernel = factor_kernel([structure.basis[0].permutation], HALF, timeout=15)
        self.assertEqual(kernel.exponents, (1,))

    def test_noncentral_abelian_kernel(self):
        first, second = cycle(0, 1, 2), cycle(0, 1)
        structure = analyze_block_structure([first, second], [(0, 1, 2), (1, 0, 2)], timeout=15)
        self.assertEqual((structure.group_order, structure.quotient_order, structure.kernel_order),
                         (6, 2, 3))
        basis = [generator.permutation for generator in structure.basis]
        inverse = tuple(basis[0].index(point) for point in range(48))
        self.assertEqual(factor_kernel(basis, inverse, timeout=15).exponents, (-1,))
        self.assertFalse(factor_kernel(basis, second, timeout=15).reachable)

    def test_fixed_slots_empty_and_identity_groups(self):
        for images, blocks in [([], []), ([IDENTITY], [(0, 1, 2)]), ([IDENTITY], [()])]:
            with self.subTest(images=images):
                result = analyze_block_structure(images, blocks, timeout=15)
                self.assertEqual((result.group_order, result.quotient_order, result.kernel_order), (1, 1, 1))
                self.assertEqual(result.basis, ())
        self.assertEqual(factor_kernel([], IDENTITY, timeout=15).exponents, ())
        self.assertFalse(factor_kernel([], QUARTER, timeout=15).reachable)
        self.assertEqual(factor_block_permutation([], (), timeout=15).syllables, ())

    def test_invalid_homomorphism_or_kernel_basis_raises(self):
        for images, blocks in [([IDENTITY], [(1, 0)]), ([cycle(0, 1, 2)], [(1, 0)])]:
            with self.subTest(images=images), self.assertRaises(GapError):
                analyze_block_structure(images, blocks, timeout=15)
        for basis in [[HALF, HALF], [cycle(0, 1), cycle(1, 2)], [IDENTITY],
                      [cycle(0, 1, 2, 3, 4, 5)]]:
            with self.subTest(basis=basis), self.assertRaises(GapError):
                factor_kernel(basis, IDENTITY, timeout=15)


if __name__ == "__main__":
    unittest.main()
