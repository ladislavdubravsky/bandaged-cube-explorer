"""Legal random-turn scrambles for ordinary and changing bandage shapes."""

from collections import deque
from random import Random

from . import State
from ._moves import _simplified_moves


def scramble(bandage=None, *, length=100, seed=None):
    """Return a legal Singmaster scramble from a bandage or current State.

    ``length`` counts random HTM steps, including half turns as one step.
    Adjacent same-face turns are combined, so the returned word can be shorter.
    The default starts solved; a supplied State instead receives a continuation
    from its current position. Neither the input nor the global RNG is changed.

    Legal moves are recomputed after every turn. Prefer leaving the last 32
    colored positions and changing faces, with fallback for narrow passages
    and single-face puzzles. A positive-length scramble always changes the
    supplied colored position; an immobile bandage raises ValueError.

    This is a random walk, not uniform sampling of reachable colored states or
    a guarantee of a particular optimal distance. Use an integer ``seed`` for
    reproducible generation. No shape graph, colored search or GAP is needed.
    """
    if isinstance(length, bool) or not isinstance(length, int):
        raise TypeError("length must be a nonnegative integer")
    if length < 0:
        raise ValueError("length must be a nonnegative integer")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise TypeError("seed must be an integer or None")
    initial = bandage if isinstance(bandage, State) else State(bandage)
    if length == 0:
        return ""
    if not initial.legal_moves:
        raise ValueError("this bandage has no legal turns and cannot be scrambled")

    rng = Random(seed)
    current, previous = initial, None
    initial_id = initial.hex_id
    recent = deque((initial_id,), maxlen=32)
    moves = []
    for step in range(length):
        candidates = [(move, current.apply(move)) for move in current.legal_moves]
        # A legal turn always has a legal inverse. All three nonidentity turns
        # of its face are available, so at least two endpoints differ from the
        # starting position, even on a puzzle with only four colored states.
        if step == length - 1:
            candidates = [(move, after) for move, after in candidates
                          if after.hex_id != initial_id]
        fresh = [(move, after) for move, after in candidates
                 if after.hex_id not in recent]
        candidates = fresh or candidates
        different_face = [(move, after) for move, after in candidates
                          if move[0] != previous]
        move, current = rng.choice(different_face or candidates)
        moves.append(move)
        previous = move[0]
        recent.append(current.hex_id)

    word = _simplified_moves(moves)
    if initial.apply(word) != current or current == initial:
        raise AssertionError("scramble failed its legal endpoint check")
    return word
