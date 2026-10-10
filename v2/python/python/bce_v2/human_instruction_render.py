"""Exact teaching words in the starting frame shown by a recognition diagram.

This module changes presentation only. A ``rotated(rho, recipe)`` instruction
can be taught as the original recipe with the cube diagram actively rotated
by rho. Its displayed face turns execute the same physical instruction in
that frame; no regrip or undo turns enter the fixed-center solver.
"""

from dataclasses import dataclass
from collections.abc import Mapping

from ._moves import _simplified_moves
from .human_chains import _inverse_moves
from .human_repertoire import HumanMacroRecipe
from .loop_rotations import inverse_rotation, normalize_rotation, rotate_moves


@dataclass(frozen=True)
class HumanInstructionPresentation:
    """A whole instruction, its exact local word, and its diagram orientation.

    ``rotation`` uses the active geometry convention of ``rotation_tuple``.
    Rotating ``turn_sequence`` back with ``rotate_moves(word, rotation)``
    recovers the original physical instruction in the reference face frame.
    A recipe with several local regrips can retain its template names when
    ``preserve_templates`` is enabled. Otherwise it requires a separately
    named definition and ``identifier`` is None.
    """

    identifier: str | None
    turn_sequence: str
    rotation: str
    recipe: HumanMacroRecipe
    requires_definition: bool


def _leaf_frames(recipe, frame=""):
    if recipe.kind == "macro":
        return (frame,)
    if recipe.kind == "power" and not recipe.exponent:
        return ()
    if recipe.kind == "rotated":
        # Written regrips execute in order. For nested frame substitutions,
        # outer rho followed by inner sigma has spatial matrix sigma*rho.
        frame = normalize_rotation((frame + " " + recipe.rotation).strip())
    return tuple(rotation for child in recipe.children
                 for rotation in _leaf_frames(child, frame))


def _outer_frame(recipe):
    """Factor rotations through outer powers without splitting an instruction."""
    frame = ""
    while recipe.kind in ("rotated", "power"):
        if recipe.kind == "rotated":
            frame = normalize_rotation((frame + " " + recipe.rotation).strip())
        elif not recipe.exponent:
            return ""
        recipe = recipe.children[0]
    return frame


def _local_recipe(recipe, frame, displayed_frame):
    if recipe.kind == "power" and not recipe.exponent:
        return HumanMacroRecipe.sequence()
    if recipe.kind == "rotated":
        following = normalize_rotation((frame + " " + recipe.rotation).strip())
        return _local_recipe(recipe.children[0], following, displayed_frame)
    if recipe.kind == "macro":
        relative = normalize_rotation((inverse_rotation(displayed_frame) + " " + frame).strip())
        return HumanMacroRecipe.rotated(relative, recipe) if relative else recipe
    children = tuple(_local_recipe(child, frame, displayed_frame) for child in recipe.children)
    return HumanMacroRecipe(recipe.kind, children, exponent=recipe.exponent)


def _has_rotation(recipe):
    return recipe.kind == "rotated" or any(_has_rotation(child) for child in recipe.children)


def _named_notation(recipe, records=None):
    """Render exact regrips around learned masters without adding definitions."""
    from .human_move_notation import _conjugation_notation

    if records is not None:
        body = recipe
        while body.kind in ("power", "rotated"):
            body = body.children[0]
        if body.kind == "macro" and len(records[body.macro_id].algorithm.turn_sequence.split()) == 1:
            return _expand(recipe, records, 100000) or "()"

    if recipe.kind == "macro":
        return recipe.macro_id
    if recipe.kind == "sequence":
        return " ".join(_named_notation(child, records) for child in recipe.children) or "()"
    if recipe.kind == "power":
        if not recipe.exponent:
            return "()"
        child = recipe.children[0]
        body = _named_notation(child, records)
        if recipe.exponent == 1:
            return body
        if child.kind != "macro":
            body = f"({body})"
        return f"{body}^{recipe.exponent}"
    if recipe.kind == "rotated":
        body = _named_notation(recipe.children[0], records)
        if not recipe.rotation:
            return body
        return f"{recipe.rotation} ({body}) {_inverse_moves(recipe.rotation)}"
    if recipe.kind == "commutator":
        return f"[{_named_notation(recipe.children[0], records)}, {_named_notation(recipe.children[1], records)}]"
    setup, body = recipe.children
    exponent = HumanMacroRecipe.power(setup, -1)
    return _conjugation_notation(
        _named_notation(body, records), _named_notation(exponent, records),
        body_is_atom=body.kind in ("macro", "commutator"),
        exponent_is_atom=exponent.kind == "macro",
    )


def _expand(recipe, records, maximum):
    """Expand named physical words, preserving order and all nested frames."""
    if recipe.kind == "macro":
        try:
            word = records[recipe.macro_id].algorithm.turn_sequence
        except KeyError:
            raise ValueError(f"unknown master ID {recipe.macro_id}") from None
        # The identity frame validates outer-face tokens without changing them.
        word = rotate_moves(word, "")
    elif recipe.kind == "power" and not recipe.exponent:
        return ""
    else:
        words = tuple(_expand(child, records, maximum) for child in recipe.children)
        if recipe.kind == "rotated":
            word = rotate_moves(words[0], recipe.rotation)
        elif recipe.kind == "sequence":
            word = " ".join(words)
        elif recipe.kind == "power":
            body = words[0] if recipe.exponent > 0 else _inverse_moves(words[0])
            if len(body.split()) * abs(recipe.exponent) > maximum:
                raise ValueError("instruction expansion exceeds max_expanded_moves")
            word = " ".join([body] * abs(recipe.exponent)) if body else ""
        else:
            first, second = words
            word = " ".join((first, second, _inverse_moves(first)))
            if recipe.kind == "commutator":
                word += " " + _inverse_moves(second)
    if len(word.split()) > maximum:
        raise ValueError("instruction expansion exceeds max_expanded_moves")
    return _simplified_moves(word.split())


def instruction_presentation(recipe, repertoire, *, rotate_diagram=True,
                             preserve_templates=False, max_expanded_moves=100_000):
    """Return an exact instruction and a convenient starting diagram frame.

    ``repertoire`` may be a HumanRepertoire, its macro tuple, or a macro map.
    Common rotations are factored across powers and across a whole recipe
    whose leaves share one frame. The remaining local expression retains its
    named master identifier when possible. If differently rotated masters
    cannot share a frame, the caller should define a new algorithm using the
    returned exact local word and give it its own identifier.

    With ``rotate_diagram=False``, turns remain in the reference frame. Any
    remaining rotated expression likewise requires a new named definition.
    The input recipe and all solver records remain unchanged.

    With preserve_templates=True, mixed frames are presented as explicit
    x/y/z regrips around the learned master names. They need no new algorithm
    definition; the accompanying physical word remains exactly checked.
    """
    if not isinstance(recipe, HumanMacroRecipe):
        raise TypeError("recipe must be a HumanMacroRecipe")
    if not isinstance(rotate_diagram, bool):
        raise TypeError("rotate_diagram must be a boolean")
    if not isinstance(preserve_templates, bool):
        raise TypeError("preserve_templates must be a boolean")
    if isinstance(max_expanded_moves, bool) or not isinstance(max_expanded_moves, int):
        raise TypeError("max_expanded_moves must be an integer")
    if max_expanded_moves < 1:
        raise ValueError("max_expanded_moves must be positive")
    macros = getattr(repertoire, "macros", repertoire)
    try:
        records = dict(macros) if isinstance(macros, Mapping) else {macro.id: macro for macro in macros}
    except (TypeError, AttributeError):
        raise TypeError("repertoire must supply named algorithm macros") from None
    frames = _leaf_frames(recipe)
    rotation = ""
    if rotate_diagram and frames:
        rotation = frames[0] if len(set(frames)) == 1 else _outer_frame(recipe)
    local = _local_recipe(recipe, "", rotation)
    requires_definition = _has_rotation(local) and not preserve_templates
    turns = _expand(local, records, max_expanded_moves)
    native = (records if getattr(getattr(repertoire, "method", None), "backend", None) == "symbolic" else None)
    identifier = _named_notation(local, native) if preserve_templates else local.render()
    return HumanInstructionPresentation(None if requires_definition else identifier,
                                        turns, rotation, local, requires_definition)


__all__ = ["HumanInstructionPresentation", "instruction_presentation"]
