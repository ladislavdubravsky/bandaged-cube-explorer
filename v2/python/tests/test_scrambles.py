"""Scrambles are executable on changing shapes and constrained components."""

import random
import unittest

import bce_v2 as c


def inverse(word):
    return " ".join(move if move.endswith("2") else
                    move[:-1] if move.endswith("'") else move + "'"
                    for move in reversed(word.split()))


class ScrambleTests(unittest.TestCase):
    def assert_legal_scramble(self, initial, word):
        current = initial
        for move in word.split():
            self.assertIn(move, current.legal_moves)
            current = current.apply(move)
        self.assertNotEqual(current, initial)
        self.assertEqual(current.apply(inverse(word)), initial)
        return current

    def test_changing_bandages_have_replayable_nontrivial_scrambles(self):
        for name in c.fixture_names():
            reference = c.fixture(name)
            changed_legality = False
            for seed in range(12):
                with self.subTest(name=name, seed=seed):
                    initial = c.State(reference)
                    word = c.scramble(reference.labels, length=100, seed=seed)
                    self.assert_legal_scramble(initial, word)
                    self.assertLessEqual(len(word.split()), 100)
                    current = initial
                    for move in word.split():
                        changed_legality |= current.legal_moves != initial.legal_moves
                        current = current.apply(move)
                    self.assertTrue(initial.is_solved)
                    self.assertEqual(initial.scramble, "")
            self.assertTrue(changed_legality)

    def test_ordinary_cube_uses_colored_positions_instead_of_single_shape(self):
        word = c.scramble(length=100, seed=7)
        after = self.assert_legal_scramble(c.State(), word)
        self.assertEqual(after.shape, c.Shape())
        self.assertEqual(len(word.split()), 100)
        self.assertTrue(all(first[0] != second[0]
                            for first, second in zip(word.split(), word.split()[1:])))

    def test_imported_current_state_is_scrambled_from_its_current_shape(self):
        source = c.State(c.fixture("Alcatraz")).apply("F R2")
        imported = c.State.from_facelets(source.facelets, source.specification)
        self.assertNotEqual(imported.shape, imported.specification)
        word = c.scramble(imported, length=50, seed=11)
        self.assert_legal_scramble(imported, word)
        self.assertEqual(imported, source)
        self.assertIsNone(imported.scramble)

    def test_single_face_puzzle_falls_back_and_combines_turns(self):
        initial = c.State([1] * 9 + [2] * 18)
        seen = set()
        for length in (1, 2, 4, 32, 100):
            for seed in range(10):
                word = c.scramble(initial, length=length, seed=seed)
                self.assertIn(word, ("U", "U2", "U'"))
                seen.add(self.assert_legal_scramble(initial, word).hex_id)
        self.assertEqual(len(seen), 3)

    def test_seed_is_repeatable_without_changing_global_rng(self):
        before = random.getstate()
        word = c.scramble(c.fixture("Alcatraz"), seed=42)
        self.assertEqual(word, c.scramble(c.fixture("Alcatraz"), seed=42))
        self.assertNotEqual(word, c.scramble(c.fixture("Alcatraz"), seed=43))
        self.assertEqual(random.getstate(), before)

    def test_zero_length_and_immobile_puzzle(self):
        self.assertEqual(c.scramble(length=0), "")
        self.assertEqual(c.scramble([1] * 27, length=0), "")
        with self.assertRaisesRegex(ValueError, "no legal turns"):
            c.scramble([1] * 27)

    def test_parameter_types_and_bounds(self):
        for invalid in (True, 1.5, "10", None):
            with self.subTest(length=invalid), self.assertRaises(TypeError):
                c.scramble(length=invalid)
        with self.assertRaises(ValueError):
            c.scramble(length=-1)
        for invalid in (True, 1.5, "seed"):
            with self.subTest(seed=invalid), self.assertRaises(TypeError):
                c.scramble(seed=invalid)


if __name__ == "__main__":
    unittest.main()
