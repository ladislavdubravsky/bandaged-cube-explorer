"""Frame-neutral whole-cube regrips and exact bandage symmetries.

The standard convention is x like R, y like U and z like F (WCA 12a4,
https://www.worldcubeassociation.org/regulations/#12a4).  These are presentation
and geometry operations; the fixed-center engine still executes face turns
only.  In a display ``rho (moves) rho^-1``, rho changes the reader's frame, so
the executable face is the inverse spatial image of its displayed normal.
For example, ``x U x'`` executes F.

The conversion functions do not assert that a regrip preserves a particular
bandage.  Use ``bandage_symmetries`` before transferring a witnessed loop to
the same reference shape, and replay the resulting face-only word normally.
"""

from collections import deque
from functools import lru_cache
from numbers import Integral

from . import Shape, State, shape
from .block_actions import (
    _IDENTITY, _ROTATIONS, _compose, _inverse, _rotate, _NORMALS,
    _STICKER_IMAGES,
)


# Active rotations in the engine's x=R, y=B, z=U coordinates.  Each signed
# tuple gives output axes, as in block_actions._rotate.
_AXIS_ROTATIONS = {"x": (1, 3, -2), "y": (2, -1, 3), "z": (3, 2, -1)}
_TOKEN_ROTATIONS = {}
for _axis, _rotation in _AXIS_ROTATIONS.items():
    _TOKEN_ROTATIONS[_axis] = _rotation
    _TOKEN_ROTATIONS[_axis + "'"] = _inverse(_rotation)
    _TOKEN_ROTATIONS[_axis + "2"] = _compose(_rotation, _rotation)


def _canonical_words():
    """Shortest token words, with a fixed deterministic order for ties."""
    words = {_IDENTITY: ""}
    queue = deque([_IDENTITY])
    while queue:
        current = queue.popleft()
        for token, rotation in _TOKEN_ROTATIONS.items():
            following = _compose(rotation, current)
            if following not in words:
                words[following] = (words[current] + " " + token).strip()
                queue.append(following)
    if set(words) != set(_ROTATIONS):
        raise RuntimeError("standard rotations do not generate the cube rotations")
    return words


_CANONICAL_WORDS = _canonical_words()
_FACE_AT_NORMAL = {normal: face for face, normal in _NORMALS.items()}


def rotation_tuple(word):
    """Return the proper spatial rotation of a whitespace-separated x/y/z word.

    Tokens are x, y or z with an optional prime or 2.  They execute in written
    order; an empty string is the identity.  No face or slice turns are accepted.
    """
    if not isinstance(word, str):
        raise TypeError("rotation word must be a string")
    result = _IDENTITY
    for token in word.split():
        try:
            rotation = _TOKEN_ROTATIONS[token]
        except KeyError:
            raise ValueError(f"invalid whole-cube rotation token {token!r}") from None
        result = _compose(rotation, result)
    return result


def normalize_rotation(word):
    """Return a shortest standard x/y/z word for this orientation."""
    return _CANONICAL_WORDS[rotation_tuple(word)]


def inverse_rotation(word):
    """Return a shortest standard word undoing this rotation."""
    return _CANONICAL_WORDS[_inverse(rotation_tuple(word))]


def rotate_moves(moves, rotation_word):
    """Execute the frame-neutral display ``rotation_word (moves) inverse``.

    The returned word contains face turns only, with the same turn amounts.
    For example ``rotate_moves("U R2", "x") == "F R2"``.  No bandage legality
    or symmetry is assumed; callers replay this word on their reference shape.
    """
    if not isinstance(moves, str):
        raise TypeError("moves must be a face-turn string")
    inverse = _inverse(rotation_tuple(rotation_word))
    faces = {face: _FACE_AT_NORMAL[_rotate(inverse, normal)]
             for face, normal in _NORMALS.items()}
    result = []
    for token in moves.split():
        if not token or token[0] not in _NORMALS or token[1:] not in ("", "'", "2"):
            raise ValueError(f"invalid face-turn token {token!r}")
        result.append(faces[token[0]] + token[1:])
    return " ".join(result)


def rotate_permutation(permutation, rotation_word):
    """Conjugate a 48-sticker action exactly as ``rotate_moves`` does.

    Permutations are source-to-target image tuples in native sticker order.
    The result represents rho, then the displayed action, then rho inverse.
    """
    try:
        images = tuple(permutation)
    except TypeError:
        raise TypeError("permutation must contain 48 integer images") from None
    if (len(images) != 48 or any(isinstance(image, bool) or
                               not isinstance(image, Integral) for image in images)
            or set(images) != set(range(48))):
        raise ValueError("permutation must be a bijection of 0..47")
    rotation = rotation_tuple(rotation_word)
    before = _STICKER_IMAGES[rotation]
    after = _STICKER_IMAGES[_inverse(rotation)]
    return tuple(after[int(images[before[index]])] for index in range(48))


def bandage_symmetries(initial=None):
    """Return all nonidentity proper regrips preserving the exact root partition.

    Accept a Shape, State, full loop library, isotropy analysis, or solver with
    an ``analysis`` property.  State inputs use the specification and loop
    inputs use their actual root_shape.  Equality includes every connected
    block and genuine core bonds; normalized label names have no significance.
    Returned words are shortest and ordered deterministically.  The ordinary
    cube has 23 such nonidentity rotations.
    """
    if hasattr(initial, "analysis"):
        initial = initial.analysis
    if hasattr(initial, "loops"):
        initial = initial.loops
    if hasattr(initial, "root_shape"):
        initial = initial.root_shape
    if isinstance(initial, State):
        initial = initial.specification
    reference = Shape() if initial is None else shape(initial)
    return _shape_symmetries(reference)


@lru_cache(maxsize=128)
def _shape_symmetries(reference):
    """Cache only immutable exact shapes, never mutable adapter objects."""
    return tuple(word for rotation, word in _CANONICAL_WORDS.items()
                 if rotation != _IDENTITY
                 and reference.rotated(_ROTATIONS.index(rotation)) == reference)


__all__ = ["normalize_rotation", "rotation_tuple", "inverse_rotation",
           "rotate_moves", "rotate_permutation", "bandage_symmetries"]
