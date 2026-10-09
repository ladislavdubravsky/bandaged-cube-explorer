"""Teaching notation preserves the literal, noncommuting physical word."""

from itertools import product
import re
import unittest

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.human_move_notation import structured_move_notation


def expand_move_notation(text):
    """Independent parser: S^A expands to A^-1 S A in written order."""
    position = 0

    def inverse(word):
        return [move if move.endswith("2") else move[:-1] if move.endswith("'")
                else move + "'" for move in reversed(word)]

    def spaces():
        nonlocal position
        while position < len(text) and text[position].isspace():
            position += 1

    def sequence(stops):
        result = []
        while True:
            spaces()
            if position == len(text) or text[position] in stops:
                return result
            result.extend(atom())

    def atom():
        nonlocal position
        spaces()
        if position >= len(text):
            raise ValueError("missing expression")
        symbol = text[position]
        if symbol in "URFDLB":
            match = re.match(r"[URFDLB](?:2|')?", text[position:])
            position += len(match.group())
            word = [match.group()]
        elif symbol == "(":
            position += 1
            word = sequence(")")
            if position >= len(text) or text[position] != ")":
                raise ValueError("unterminated group")
            position += 1
        elif symbol == "[":
            position += 1
            first = sequence(",")
            if position >= len(text) or text[position] != ",":
                raise ValueError("missing commutator separator")
            position += 1
            second = sequence("]")
            if position >= len(text) or text[position] != "]":
                raise ValueError("unterminated commutator")
            position += 1
            word = first + second + inverse(first) + inverse(second)
        else:
            raise ValueError(f"unexpected notation at {position}")
        while position < len(text):
            if text[position].isdigit():
                match = re.match(r"\d+", text[position:])
                position += len(match.group())
                word *= int(match.group())
            elif text[position] == "^":
                position += 1
                numeric = re.match(r"-?\d+", text[position:])
                if numeric is not None:
                    position += len(numeric.group())
                    power = int(numeric.group())
                    word = (word if power >= 0 else inverse(word)) * abs(power)
                else:
                    exponent = atom()
                    word = inverse(exponent) + word + exponent
            else:
                break
        return word

    return " ".join(sequence(""))


class HumanMoveNotationTests(unittest.TestCase):
    def check_expansion(self, word, expected=None):
        formatted = structured_move_notation(word)
        if expected is not None:
            self.assertEqual(formatted, expected)
        expanded = expand_move_notation(formatted)
        self.assertEqual(_simplified_moves(expanded.split()), _simplified_moves(word.split()))
        return formatted

    def test_master_example_shows_setup_body_undo(self):
        self.check_expansion("R U' B' U R'", "B'^(U R')")
        self.check_expansion("R U' B U R'", "B^(U R')")

    def test_commutator_operand_order_is_not_commuted(self):
        self.check_expansion("R U R' U'", "[R, U]")
        self.check_expansion("U R U' R'", "[U, R]")
        first = c.State().apply("R U R' U'")
        second = c.State().apply("U R U' R'")
        self.assertNotEqual(first, second)
        self.check_expansion("R U F U' R' F'", "[R U, F]")

    def test_powers_of_literal_and_structured_words(self):
        self.check_expansion("R U R U R U", "(R U)3")
        self.check_expansion("U' R' U' R'", "(U' R')2")
        self.check_expansion("R U R' U' R U R' U'", "([R, U])2")
        self.check_expansion("R U F R' R U F R'", "((U F)2)^R'")

    def test_nested_constructions_and_mixed_sequences(self):
        self.check_expansion("F R U R' U' F'", "[R, U]^F'")
        self.check_expansion("R U R' U' F R U' B' U R'",
                             "[R, U] F B'^(U R')")

    def test_compound_conjugating_exponents_and_bases_are_grouped(self):
        self.check_expansion("R U F B F' U' R'", "B^(F' U' R')")
        self.check_expansion("R U F R'", "(U F)^R'")
        self.check_expansion("R F R' U R F' R'", "U^(F'^R')")

    def test_master_recipe_conjugation_preserves_setup_body_undo(self):
        macro = c.HumanMacroRecipe.macro
        sequence = c.HumanMacroRecipe.sequence
        power = c.HumanMacroRecipe.power
        conjugate = c.HumanMacroRecipe.conjugate
        first, second, third, fourth = (macro(f"M{number}") for number in range(1, 5))
        samples = (
            (conjugate(first, second), "M2^(M1^-1)", "R U R'"),
            (conjugate(sequence(first, second), sequence(third, fourth)),
             "(M3 M4)^((M1 M2)^-1)", "R U F B U' R'"),
            (conjugate(power(first, -1), second), "M2^M1", "R' U R"),
            (conjugate(first, power(second, 2)), "(M2^2)^(M1^-1)", "R U U R'"),
            (conjugate(first, conjugate(second, third)),
             "(M3^(M2^-1))^(M1^-1)", "R U F U' R'"),
        )
        aliases = {"M1": "R", "M2": "U", "M3": "F", "M4": "B"}
        for recipe, expected, physical in samples:
            with self.subTest(recipe=recipe):
                self.assertEqual(recipe.render(), expected)
                turns = re.sub(r"M[1-4]", lambda match: aliases[match.group()], expected)
                expanded = expand_move_notation(turns)
                self.assertEqual(_simplified_moves(expanded.split()),
                                 _simplified_moves(physical.split()))

    def test_same_face_reduction_and_identity(self):
        for word, expected in (("", "()"), ("R R'", "()"),
                               ("R R", "R2"), ("R2 R2", "()"),
                               ("R U U' R' F", "F"),
                               (" R\n U\t R' ", "U^R'")):
            with self.subTest(word=word):
                self.check_expansion(word, expected)

    def test_inputs_are_literal_face_turns(self):
        for value in (None, True, 3, ["R", "U"]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    structured_move_notation(value)
        for value in ("[R, U]", "x R x'", "r", "R3", "R2'", "R,U"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    structured_move_notation(value)

    def test_long_words_have_bounded_literal_fallback(self):
        word = " ".join(("R", "U") * 64)
        self.check_expansion(word, word)

    def test_many_short_words_retain_exact_written_order(self):
        for size in range(1, 7):
            for moves in product(("R", "U'", "F2"), repeat=size):
                self.check_expansion(" ".join(moves))


if __name__ == "__main__":
    unittest.main()
