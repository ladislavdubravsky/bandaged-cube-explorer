"""Subprocess protocol tests and optional independent, live GAP checks."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from bce_v2.gap_backend import (
    GapAnalysis, GapError, GapFactorization, GapTimeoutError, GapUnavailableError,
    analyze_generators, factor_permutation,
)


IDENTITY = tuple(range(48))
BEGIN = "__BCE_GAP_V1_BEGIN__"
END = "__BCE_GAP_V1_END__"
FACTOR_BEGIN = "__BCE_GAP_FACTOR_V1_BEGIN__"
FACTOR_END = "__BCE_GAP_FACTOR_V1_END__"


def cycle_images(*cycles):
    images = list(IDENTITY)
    for cycle in cycles:
        for source, target in zip(cycle, cycle[1:] + cycle[:1]):
            images[source] = target
    return tuple(images)


def protocol(order=4, indices="0", version="4.12.1"):
    return f"{BEGIN}\nversion={version}\norder={order}\nindices={indices}\n{END}\n"


def completed(output=None, *, status=0, stderr=""):
    return subprocess.CompletedProcess([], status, protocol() if output is None else output, stderr)


def factor_protocol(order=4, reachable="true", syllables="0:1", version="4.12.1"):
    return (f"{FACTOR_BEGIN}\nversion={version}\norder={order}\n"
            f"reachable={reachable}\nsyllables={syllables}\n{FACTOR_END}\n")


def compose(first, second):
    return tuple(second[point] for point in first)


def evaluate_syllables(permutations, syllables):
    """Small independent test evaluator using explicit positive/inverse steps."""
    product = IDENTITY
    for index, exponent in syllables:
        action = permutations[index]
        if exponent < 0:
            inverse = [0] * 48
            for point, image in enumerate(action):
                inverse[image] = point
            action = inverse
        for _ in range(abs(exponent)):
            product = compose(product, action)
    return product


class GapProtocolTests(unittest.TestCase):
    def test_launch_uses_validated_input_and_no_shell(self):
        executable = Path("/tmp/my gap launcher")
        quarter = cycle_images((0, 1, 2, 3))
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed()) as run:
            result = analyze_generators([quarter], gap_executable=executable, timeout=2.5, prune=False)
        self.assertEqual(result, GapAnalysis(4, (0,), "4.12.1"))
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], str(executable))
        self.assertIn("--quitonbreak", args[0])
        self.assertIn("-r", args[0])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 2.5)
        self.assertTrue(kwargs["capture_output"])
        self.assertIn("rec(random := 1000)", kwargs["input"])
        self.assertIn("BCEAnalyze([[2,3,4,1,5,6", kwargs["input"])
        self.assertIn(",false);;", kwargs["input"])
        with self.assertRaises(FrozenInstanceError):
            result.group_order = 7

    def test_trivial_result_and_non_protocol_startup_information(self):
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed("#I harmless info\n" + protocol(1, ""))):
            self.assertEqual(analyze_generators([]), GapAnalysis(1, (), "4.12.1"))

    def test_missing_executable_and_other_launch_errors(self):
        for error in (FileNotFoundError("not found"), PermissionError("not executable")):
            with self.subTest(error=error), patch("bce_v2.gap_backend.subprocess.run", side_effect=error):
                with self.assertRaisesRegex(GapUnavailableError, "Install GAP"):
                    analyze_generators([])

    def test_timeout_never_returns_partial_result(self):
        error = subprocess.TimeoutExpired("gap", 0.1, output=protocol(1, ""))
        with patch("bce_v2.gap_backend.subprocess.run", side_effect=error):
            with self.assertRaisesRegex(GapTimeoutError, "0.1-second"):
                analyze_generators([], timeout=0.1)

    def test_nonzero_exit_rejects_even_a_complete_result(self):
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(status=1, stderr="Error, test failure")):
            with self.assertRaisesRegex(GapError, "status 1: Error, test failure"):
                analyze_generators([IDENTITY])

    def test_malformed_results_never_return_counts(self):
        invalid = [
            "", protocol().replace(END, ""), protocol() + protocol(),
            f"{END}\n{BEGIN}\nversion=4.12.1\norder=4\nindices=0\n",
            protocol().replace("indices=0\n", "indices=0\nextra=1\n"),
            protocol(version=""), protocol(version="unknown"), protocol(order=0),
            protocol(order=-1), protocol(order="4e2"), protocol(order="04"),
            protocol(indices="0,0"), protocol(indices="1"), protocol(indices="-1"),
            protocol(indices="0,"), protocol(indices=""), protocol(1, "0"),
            protocol(order=10**100), protocol(order="9" * 5000),
            protocol(indices="9" * 5000),
        ]
        for output in invalid:
            with self.subTest(output=output), patch("bce_v2.gap_backend.subprocess.run", return_value=completed(output)):
                with self.assertRaises(GapError):
                    analyze_generators([IDENTITY])

    def test_indices_must_preserve_input_order(self):
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(protocol(indices="1,0"))):
            with self.assertRaisesRegex(GapError, "indices"):
                analyze_generators([IDENTITY, IDENTITY])

    def test_invalid_permutations_are_rejected_before_launch(self):
        invalid = [([], ValueError), (range(47), ValueError),
                   ([0] * 48, ValueError), (list(range(47)) + [48], ValueError),
                   (list(range(47)) + [-1], ValueError),
                   (list(range(47)) + [47.0], TypeError),
                   (list(range(47)) + [True], TypeError),
                   (list(range(47)) + ["47);QuitGap(0);"], TypeError),
                   (None, TypeError)]
        with patch("bce_v2.gap_backend.subprocess.run") as run:
            for permutation, error in invalid:
                with self.subTest(permutation=permutation), self.assertRaises(error):
                    analyze_generators([permutation])
            run.assert_not_called()

    def test_invalid_options_are_rejected_before_launch(self):
        invalid = [({"timeout": 0}, ValueError), ({"timeout": -1}, ValueError),
                   ({"timeout": float("inf")}, ValueError),
                   ({"timeout": float("nan")}, ValueError),
                   ({"timeout": True}, TypeError), ({"timeout": "1"}, TypeError),
                   ({"gap_executable": ""}, ValueError),
                   ({"gap_executable": "gap\x00bad"}, ValueError),
                   ({"gap_executable": b"gap"}, TypeError),
                   ({"prune": 1}, TypeError)]
        with patch("bce_v2.gap_backend.subprocess.run") as run:
            for options, error in invalid:
                with self.subTest(options=options), self.assertRaises(error):
                    analyze_generators([], **options)
            run.assert_not_called()


class GapFactorProtocolTests(unittest.TestCase):
    def test_launch_and_verified_original_generator_indices(self):
        quarter = cycle_images((0, 1, 2, 3))
        output = factor_protocol(syllables="1:-1")
        inverse = cycle_images((0, 3, 2, 1))
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(output)) as run:
            result = factor_permutation([IDENTITY, quarter], inverse,
                                        gap_executable=Path("/tmp/my gap"), timeout=2)
        self.assertEqual(result, GapFactorization(4, True, ((1, -1),), "4.12.1"))
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], "/tmp/my gap")
        self.assertIn("--quitonbreak", args[0])
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("GroupWithGenerators", kwargs["input"])
        self.assertIn("EpimorphismFromFreeGroup", kwargs["input"])
        self.assertIn("PreImagesRepresentative", kwargs["input"])
        self.assertNotIn("Factorization(", kwargs["input"])
        self.assertEqual(kwargs["timeout"], 2)
        with self.assertRaises(FrozenInstanceError):
            result.reachable = False

    def test_noncommuting_word_is_checked_in_execution_order(self):
        first, second = cycle_images((0, 1)), cycle_images((1, 2))
        target = compose(first, second)
        self.assertNotEqual(target, compose(second, first))
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(6, syllables="0:1,1:1"))):
            self.assertEqual(factor_permutation([first, second], target).syllables,
                             ((0, 1), (1, 1)))
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(6, syllables="1:1,0:1"))):
            with self.assertRaisesRegex(GapError, "verification"):
                factor_permutation([first, second], target)

    def test_identity_and_unreachable_results_have_no_word(self):
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(1, syllables=""))):
            self.assertEqual(factor_permutation([], IDENTITY),
                             GapFactorization(1, True, (), "4.12.1"))
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(1, "false", ""))):
            self.assertEqual(factor_permutation([], cycle_images((0, 1))),
                             GapFactorization(1, False, (), "4.12.1"))

    def test_malformed_or_incorrect_factorizations_are_rejected(self):
        quarter = cycle_images((0, 1, 2, 3))
        invalid = [
            "", factor_protocol().replace(FACTOR_END, ""),
            factor_protocol() + factor_protocol(),
            factor_protocol().replace(FACTOR_BEGIN, "unexpected"),
            factor_protocol().replace("order=4", "extra=1\norder=4"),
            factor_protocol(version=""), factor_protocol(order=0),
            factor_protocol(order="9" * 5000), factor_protocol(order=10**100),
            factor_protocol(reachable="True"), factor_protocol(reachable="false"),
            factor_protocol(syllables=""), factor_protocol(syllables="1:1"),
            factor_protocol(syllables="-1:1"), factor_protocol(syllables="0:0"),
            factor_protocol(syllables="0:+1"), factor_protocol(syllables="0:01"),
            factor_protocol(syllables="0:-0"), factor_protocol(syllables="0:1,"),
            factor_protocol(syllables="0:2"), factor_protocol(syllables="0:" + "9" * 5000),
            factor_protocol(order=1),
        ]
        for output in invalid:
            with self.subTest(output=output), patch("bce_v2.gap_backend.subprocess.run", return_value=completed(output)):
                with self.assertRaises(GapError):
                    factor_permutation([quarter], quarter)
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(1, "false", ""))):
            with self.assertRaises(GapError):
                factor_permutation([], IDENTITY)

    def test_launch_failures_and_timeout_are_inconclusive(self):
        cases = ((FileNotFoundError("missing"), GapUnavailableError),
                 (subprocess.TimeoutExpired("gap", 0.1), GapTimeoutError))
        for error, expected in cases:
            with self.subTest(error=error), patch("bce_v2.gap_backend.subprocess.run", side_effect=error):
                with self.assertRaises(expected):
                    factor_permutation([], IDENTITY, timeout=0.1)
        with patch("bce_v2.gap_backend.subprocess.run", return_value=completed(factor_protocol(1, syllables=""), status=1)):
            with self.assertRaises(GapError):
                factor_permutation([], IDENTITY)

    def test_target_and_options_are_validated_before_launch(self):
        cases = (([], {}, ValueError),
                 (list(range(47)) + [47.0], {}, TypeError),
                 (list(range(47)) + [True], {}, TypeError),
                 (list(range(47)) + [48], {}, ValueError),
                 (list(range(47)) + ["47);QuitGap(0);"], {}, TypeError),
                 (IDENTITY, {"timeout": float("inf")}, ValueError),
                 (IDENTITY, {"gap_executable": "gap\x00bad"}, ValueError))
        with patch("bce_v2.gap_backend.subprocess.run") as run:
            for target, options, expected in cases:
                with self.subTest(target=target, options=options), self.assertRaises(expected):
                    factor_permutation([], target, **options)
            with self.assertRaises(ValueError):
                factor_permutation([[0] * 48], IDENTITY)
            run.assert_not_called()


def cube_generators():
    """Independent geometric action on the 48 non-center cube stickers."""
    stickers = []
    for axis in range(3):
        for sign in (-1, 1):
            tangent = [index for index in range(3) if index != axis]
            for u in (-1, 0, 1):
                for v in (-1, 0, 1):
                    if u == v == 0:
                        continue
                    position, normal = [0] * 3, [0] * 3
                    position[axis] = normal[axis] = sign
                    position[tangent[0]], position[tangent[1]] = u, v
                    stickers.append((tuple(position), tuple(normal)))
    indices = {sticker: index for index, sticker in enumerate(stickers)}
    generators = []
    for axis in range(3):
        for sign in (-1, 1):
            def rotate(vector):
                result = list(vector)
                first, second = (axis + 1) % 3, (axis + 2) % 3
                result[first], result[second] = -vector[second], vector[first]
                return tuple(result)

            generators.append(tuple(indices[(rotate(position), rotate(normal))]
                                    if position[axis] == sign else index
                                    for index, (position, normal) in enumerate(stickers)))
    return generators


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external executable")
class LiveGapTests(unittest.TestCase):
    def test_empty_and_identity_groups(self):
        for permutations in ([], [IDENTITY], [IDENTITY, IDENTITY]):
            with self.subTest(permutations=permutations):
                result = analyze_generators(permutations, timeout=15)
                self.assertEqual(result.group_order, 1)
                self.assertEqual(result.generator_indices, ())

    def test_duplicate_inverse_and_later_redundancy(self):
        half = cycle_images((0, 2), (1, 3))
        quarter = cycle_images((0, 1, 2, 3))
        inverse = cycle_images((0, 3, 2, 1))
        candidates = [half, quarter, inverse, IDENTITY, quarter]
        streaming = analyze_generators(candidates, timeout=15, prune=False)
        pruned = analyze_generators(candidates, timeout=15)
        self.assertEqual(streaming.group_order, 4)
        self.assertEqual(streaming.generator_indices, (0, 1))
        self.assertEqual(pruned.group_order, 4)
        self.assertEqual(pruned.generator_indices, (1,))

    def test_ordinary_cube_order_without_enumeration(self):
        result = analyze_generators(cube_generators(), timeout=60)
        self.assertEqual(result.group_order, 43_252_003_274_489_856_000)
        self.assertGreater(len(result.generator_indices), 0)
        self.assertLessEqual(len(result.generator_indices), 6)


@unittest.skipUnless(shutil.which("gap"), "GAP is an optional external executable")
class LiveGapFactorTests(unittest.TestCase):
    def test_trivial_identity_and_nonmembers(self):
        for generators in ([], [IDENTITY], [cycle_images((0, 1))]):
            with self.subTest(generators=generators):
                result = factor_permutation(generators, IDENTITY, timeout=15)
                self.assertTrue(result.reachable)
                self.assertEqual(result.syllables, ())
                result = factor_permutation(generators, cycle_images((2, 3)), timeout=15)
                self.assertFalse(result.reachable)
                self.assertEqual(result.syllables, ())
                self.assertEqual(result.group_order, 2 if generators and generators[0] != IDENTITY else 1)

    def test_singleton_preference_beats_greedy_and_preserves_full_order(self):
        first, second = cycle_images((0, 1)), cycle_images((2, 3))
        target = compose(first, second)
        result = factor_permutation([first, second, target], target, timeout=15)
        self.assertEqual(result.group_order, 4)
        self.assertEqual(result.syllables, ((2, 1),))

    def test_greedy_removes_high_indices_and_unused_generators(self):
        first, second, unused = (cycle_images((0, 1)), cycle_images((2, 3)), cycle_images((4, 5)))
        generators = [IDENTITY, first, second, unused, first, second]
        target = compose(first, second)
        result = factor_permutation(generators, target, timeout=15)
        self.assertEqual(result.group_order, 8)
        self.assertEqual({index for index, _ in result.syllables}, {1, 2})
        self.assertEqual(evaluate_syllables(generators, result.syllables), target)

    def test_noncommuting_factorization_and_inverse_power(self):
        first, second = cycle_images((0, 1)), cycle_images((1, 2))
        target = compose(first, second)
        result = factor_permutation([first, second], target, timeout=15)
        self.assertEqual(result.group_order, 6)
        self.assertTrue(result.reachable)
        self.assertEqual(evaluate_syllables([first, second], result.syllables), target)
        quarter = cycle_images((0, 1, 2, 3))
        inverse = cycle_images((0, 3, 2, 1))
        result = factor_permutation([quarter], inverse, timeout=15)
        self.assertEqual(result.syllables, ((0, -1),))

    def test_cube_group_factoring_uses_full_order_without_enumeration(self):
        generators = cube_generators()
        target = compose(compose(generators[0], generators[0]), generators[0])
        result = factor_permutation(generators, target, timeout=60)
        self.assertEqual(result.group_order, 43_252_003_274_489_856_000)
        self.assertEqual(result.syllables, ((0, -1),))


if __name__ == "__main__":
    unittest.main()
