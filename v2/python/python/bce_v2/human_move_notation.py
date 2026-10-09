"""Recognize exact physical-turn constructions for teaching master words.

This is a display formatter, independent of a loop's group-theoretic witness.
It never commutes turns, inserts regrips, or replaces a word by another word
with the same cube action. Notation expansion reproduces the supplied word
after adjacent same-face simplification, in its original written order.
"""

from dataclasses import dataclass
from functools import lru_cache
import re

from ._moves import _simplified_moves


_MOVE = re.compile(r"[URFDLB](?:2|')?")
_MAX_STRUCTURED_MOVES = 96


def _conjugation_notation(body, exponent, *, body_is_atom=False, exponent_is_atom=False):
    """Format S^A with the caller supplying A under A^-1 S A semantics.

    The caller knows whether each operand is a single atom in its notation;
    grouping prevents sequences or numeric powers from binding ambiguously.
    """
    base = body if body_is_atom else f"({body})"
    power = exponent if exponent_is_atom else f"({exponent})"
    return f"{base}^{power}"


def _inverse(word):
    return tuple(move if move.endswith("2") else move[:-1] if move.endswith("'")
                 else move + "'" for move in reversed(word))


@dataclass(frozen=True)
class _Notation:
    text: str
    displayed_moves: int
    constructions: int = 0
    kind: str = "literal"

    @property
    def score(self):
        # Prefer fewer physical turns to learn, then fewer construction layers.
        # Literal length and spelling make equal-cost choices deterministic.
        return self.displayed_moves, self.constructions, len(self.text), self.text


def structured_move_notation(turn_sequence):
    """Render literal outer-face turns using powers and conjugation notation.

    ``S^A`` means ``A^-1 S A`` and ``[A, B]`` means
    ``A B A^-1 B^-1``. Compound conjugating exponents use parentheses,
    as in ``S^(X Y Z)``. ``(A)n`` repeats A in the written order.
    The formatter recognizes these exact substring patterns recursively;
    it does not perform a group search or claim a shortest description.

    Input uses the same whitespace-separated outer-face Singmaster turns as
    ``State.apply``. Adjacent turns of the same face are simplified first.
    Empty words display as ``()``. To bound presentation work, words longer
    than 96 simplified turns retain their expanded literal notation.
    """
    if not isinstance(turn_sequence, str):
        raise TypeError("turn_sequence must be a Singmaster string")
    tokens = turn_sequence.split()
    if any(_MOVE.fullmatch(move) is None for move in tokens):
        raise ValueError("turn_sequence must use outer-face Singmaster notation")
    simplified = _simplified_moves(tokens)
    word = tuple(simplified.split())
    size = len(word)
    if not size:
        return "()"
    if size > _MAX_STRUCTURED_MOVES:
        return simplified

    @lru_cache(maxsize=None)
    def format_segment(segment):
        length = len(segment)
        best = _Notation(" ".join(segment), length,
                         kind="literal" if length == 1 else "sequence")

        def consider(text, displayed_moves, constructions, kind):
            nonlocal best
            candidate = _Notation(text, displayed_moves, constructions, kind)
            if candidate.score < best.score:
                best = candidate

        # Exact repeated words, including repetitions of a bracket expression.
        for period in range(1, length // 2 + 1):
            if length % period:
                continue
            exponent = length // period
            if segment != segment[:period] * exponent:
                continue
            body = format_segment(segment[:period])
            consider(f"({body.text}){exponent}", body.displayed_moves,
                     body.constructions + 1, "power")

        # A^-1 S A. The setup need not itself be a legal reference-shape loop;
        # this notation describes the already-verified full physical word.
        for setup_length in range(1, (length - 1) // 2 + 1):
            if segment[-setup_length:] != _inverse(segment[:setup_length]):
                continue
            exponent = format_segment(_inverse(segment[:setup_length]))
            body = format_segment(segment[setup_length:-setup_length])
            text = _conjugation_notation(
                body.text, exponent.text,
                body_is_atom=body.kind in ("literal", "commutator"),
                exponent_is_atom=_MOVE.fullmatch(exponent.text) is not None)
            consider(text,
                     exponent.displayed_moves + body.displayed_moves,
                     exponent.constructions + body.constructions + 1, "conjugate")

        # A B A^-1 B^-1, with arbitrary nonempty A and B. Keeping their order
        # is essential: swapping operands gives the inverse commutator.
        if length % 2 == 0:
            half = length // 2
            for first_length in range(1, half):
                first_word = segment[:first_length]
                second_word = segment[first_length:half]
                if (segment[half:half + first_length] != _inverse(first_word)
                        or segment[half + first_length:] != _inverse(second_word)):
                    continue
                first = format_segment(first_word)
                second = format_segment(second_word)
                consider(f"[{first.text}, {second.text}]",
                         first.displayed_moves + second.displayed_moves,
                         first.constructions + second.constructions + 1, "commutator")

        # Preserve useful constructions occurring inside a longer master.
        for split in range(1, length):
            first, second = format_segment(segment[:split]), format_segment(segment[split:])
            consider(f"{first.text} {second.text}",
                     first.displayed_moves + second.displayed_moves,
                     first.constructions + second.constructions, "sequence")
        return best

    return format_segment(word).text
