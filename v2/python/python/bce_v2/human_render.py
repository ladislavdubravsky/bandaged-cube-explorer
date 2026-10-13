"""A concrete initial guide for certified computational human-method baselines."""

import re

from .block_actions import _CELL_POINTS, _POINTS, cell_name
from .human_move_notation import structured_move_notation


_FACES = {(0, 0, 1): "U", (1, 0, 0): "R", (0, -1, 0): "F",
          (0, 0, -1): "D", (-1, 0, 0): "L", (0, 1, 0): "B"}


def recognition_wording(text):
    """Use familiar reader terms without changing policy selection or image bytes.

    Internal observer labels retain their existing lengths: they participate in
    the certified procedure's deterministic tie-breaking. Only presentation is
    translated, including code-styled recognition cues. Native API identifiers
    containing underscores and embedded image data remain intact.
    """
    words = {"footprint": "location", "footprints": "locations",
             "phase": "orientation", "phases": "orientations",
             "structure": "algorithm", "marker": "sticker", "markers": "stickers",
             "facet": "sticker", "facets": "stickers"}

    def replace(match):
        word = match.group()
        replacement = words[word.lower()]
        if word.isupper():
            return replacement.upper()
        return replacement.capitalize() if word[0].isupper() else replacement

    def reader_text(part):
        part = re.sub(r"\bCommit to\s+([a-z])", lambda match: match[1].upper(), part)
        # Both terms name the same sticker; translating them separately would
        # produce the redundant expression "sticker stickers".
        part = re.sub(r"\b(phase|orientation)-marker facets?\b", r"\1 stickers", part)
        part = re.sub(r"\b(?:marker facets?|facet markers?)\b", "stickers", part)
        return re.sub(r"\b(?:footprints?|phases?|structure|markers?|facets?)\b",
                      replace, part, flags=re.IGNORECASE)

    sections = re.split(r"(data:image/[^\s;,]+;base64,[A-Za-z0-9+/=]+)", text)
    return "".join(part if index % 2 else reader_text(part)
                   for index, part in enumerate(sections))


def _sticker(point):
    cell, normal = _POINTS[point]
    return f"{cell_name(cell)}/{_FACES[normal]}"


def _feature_name(feature, inventory):
    if feature.kind == "orient_slots":
        names = (block.name for block in inventory.blocks if set(block.cells).issubset(feature.cells))
        return "orient occupants of " + ", ".join(names)
    if feature.kind in ("place_blocks", "solve_blocks", "occupy_slots", "place_blocks_up_to_alignment", "solve_blocks_up_to_actions"):
        names = (block.name for block in inventory.blocks if set(block.cells).issubset(feature.cells))
        verb = {"place_blocks": "place together ", "solve_blocks": "fully solve together ",
                "occupy_slots": "retain in their home region ",
                "place_blocks_up_to_alignment": "place together up to the allowed alignment ",
                "solve_blocks_up_to_actions": "prepare full poses for the remaining action family "}[feature.kind]
        return verb + ", ".join(names)
    slot = next(block for block in inventory.blocks if block.cells == feature.cells)
    return ("place " if feature.kind == "place_block" else "fully solve ") + slot.name


def _feature_cue(feature, observation, inventory):
    from .human_chains import _resolve_feature

    block = _resolve_feature(inventory, feature)
    if feature.kind == "solve_blocks_up_to_actions":
        from .human_chains import _feature_indices
        indices = _feature_indices(inventory, feature)
        width = 2*len(indices)
        row = observation[:width]
        placements = "; ".join(f"`{inventory.blocks[index].compact_name}` → "
                               f"`{inventory.blocks[row[2*offset]].compact_name}`"
                               for offset, index in enumerate(indices))
        rows = [observation[offset:offset+width] for offset in range(0,len(observation),width)]
        if (all(pattern[::2] == rows[0][::2] for pattern in rows) and
                len({inventory.blocks[index].orientation_order for index in indices}) == 1 and
                len(rows) == inventory.blocks[indices[0]].orientation_order and
                all(len({(pattern[2*i+1]-rows[0][2*i+1]) % inventory.blocks[indices[i]].orientation_order
                         for i in range(len(indices))}) == 1 for pattern in rows)):
            order = inventory.blocks[indices[0]].orientation_order
            phases = "; ".join(f"phase({inventory.blocks[index].compact_name}) − "
                               f"phase({inventory.blocks[indices[0]].compact_name}) = "
                               f"{(row[2*i+1]-row[1]) % order} (mod {order})"
                               for i,index in enumerate(indices[1:],1))
            return placements + ("; " + phases if phases else "")
        patterns = ("; ".join(f"`{inventory.blocks[index].compact_name}` → "
                              f"`{inventory.blocks[pattern[2*i]].compact_name}`, phase {pattern[2*i+1]}"
                              for i,index in enumerate(indices)) for pattern in rows)
        return "Equivalent full poses: " + " / ".join(patterns)
    if feature.kind == "orient_slots":
        return "; ".join(f"`{inventory.blocks[index].compact_name}`: {phase}"
                         for index, phase in zip(block, observation))
    if feature.kind == "occupy_slots":
        return "Region: " + ", ".join(f"`{inventory.blocks[index].compact_name}`"
                                     for index in observation)
    if feature.kind == "place_blocks_up_to_alignment":
        from .human_chains import _feature_indices

        indices = _feature_indices(inventory, feature)
        width = len(indices)
        patterns = ("; ".join(
            f"`{inventory.blocks[index].compact_name}` → "
            f"`{inventory.blocks[destination].compact_name}`"
            for index, destination in zip(indices, observation[offset:offset+width]))
            for offset in range(0, len(observation), width))
        return "Equivalent placements: " + " / ".join(patterns)
    if feature.kind in ("place_blocks", "solve_blocks"):
        stride = 2 if feature.kind == "solve_blocks" else 1
        return "; ".join(
            f"`{inventory.blocks[index].compact_name}` → "
            f"`{inventory.blocks[observation[offset*stride]].compact_name}`" +
            (f", phase {observation[offset*stride+1]}" if stride == 2 else "")
            for offset, index in enumerate(block))
    return (f"`{inventory.blocks[block].compact_name}` → "
            f"`{inventory.blocks[observation[0]].compact_name}`" +
            (f", phase {observation[1]}" if feature.kind == "solve_block" else ""))


def _recognition_cue(stage, observation, inventory):
    from .human_methods import _recognition_spec, _observe

    offset, cues = 0, []
    identity = inventory.action(tuple(range(48)))
    for feature, block in _recognition_spec(inventory, stage):
        size = len(_observe(identity, block, feature.kind))
        cues.append(_feature_cue(feature, observation[offset:offset+size], inventory))
        offset += size
    return "; ".join(cues)


def _orientation_cue(stage, observation, inventory):
    return "; ".join(f"`{inventory.blocks[index].compact_name}`: {phase}"
                     for index, phase in zip(stage.block_index, observation))


def _orientation_explanation(stage, inventory):
    from .human_diagrams import _orientation_marker_points

    order = inventory.blocks[stage.block_index[0]].orientation_order
    markers = "; ".join(f"`{_sticker(point)}`"
                        for point in _orientation_marker_points(inventory, stage.block_index))
    return (f"Read the orientation of the occupant of each named slot, modulo {order}, "
            "in the declared reference frames. Match the complete pattern; piece identity "
            "and placement within this region do not choose the case. All-zero is oriented. "
            f"The reference marker facets are {markers}. Follow those facets on the current "
            "occupants: the diagrams mark them blue and hide the remaining facet colors. "
            "The marker's position distinguishes the orientation.")


def _algorithm_table(definitions):
    """Render exact turn words, their physical action, and their structure."""
    lines = ["| Turn sequence | Block action | Structure |", "| --- | --- | --- |"]
    for definition in definitions:
        identifier, word, action, *structure = definition
        notation = structure[0] if structure else structured_move_notation(word)
        lines.append(f"| `{identifier}: {word or '(no moves)'}` | `{action.notation}` | "
                     f"`{notation}` |")
    return [*lines, ""]


def method_guide(method, *, domain_features=None, algorithm_structures=None):
    """Render stage recognition, complete case tables and physical algorithms.

    Full-block cases include a concrete sticker cue, computed in the fixed
    reference frame. Placement cases deliberately ignore sticker orientation.
    Anonymous slot cases use complete destination-indexed orientation patterns.
    The guide claims computational coverage, without claiming human review.
    """
    lines = ["# Solving from reference shape", ""]
    if method.status != "completed":
        lines.extend(["Generation stopped before a complete method was available.", "",
                      f"Reason: `{method.reason}`. The reported reference-group order is "
                      f"{method.group_order:,}; the requested element limit is "
                      f"{method.max_group_elements}.", "",
                      "This artifact has no correction algorithms or case-coverage claim.", ""])
        return recognition_wording("\n".join(lines))
    inventory = method.inventory
    scope = (f"This computational baseline covers all **{method.group_order:,} reachable colored states** "
             "whose bandage shape is already the declared reference shape.")
    if domain_features is not None:
        requirements = "; ".join(_feature_name(feature, inventory) for feature in domain_features)
        scope = (f"This method covers all **{method.group_order:,} reachable colored states** "
                 "in the declared reference shape satisfying the starting conditions: "
                 f"{requirements or 'no additional conditions'}. "
                 "Application checks these conditions before executing the stages.")
    lines.extend([
        scope, "",
        ("The stage policies have exact symbolic subgroup and orbit certificates; "
         "every physical algorithm has been replayed. " if method.backend == "symbolic" else
         "The stage policies and physical algorithms have been checked exhaustively. ") +
        "Human memorability and ease of execution have not been reviewed; some algorithms may be long.", "",
    ])
    if method.algorithms:
        notation_help = (
            "The Structure column composes the named execution-vocabulary operations, "
            "read from left to right."
            if algorithm_structures is not None else
            "Structured notation preserves the same turn order: "
            "`S^A` means A⁻¹ S A, `[A, B]` means A B A⁻¹ B⁻¹, and `(A)n` repeats A "
            "n times." + (" `[S: A]` means S A S⁻¹." if method.backend == "symbolic" else ""))
        lines.extend(["## Algorithms", "",
                      "Singmaster notation uses U/R/F/D/L/B face turns, an apostrophe for the inverse, "
                      "and 2 for a half turn. " + notation_help, ""])
        if algorithm_structures is not None:
            definitions = ((algorithm.id, algorithm.turn_sequence, algorithm.block_action,
                            algorithm_structures[algorithm.id]) for algorithm in method.algorithms)
        elif method.backend == "symbolic":
            definitions = ((algorithm.id, algorithm.turn_sequence, algorithm.block_action,
                            algorithm.expression.render_moves(method.generators))
                           for algorithm in method.algorithms)
        else:
            definitions = ((algorithm.id, algorithm.turn_sequence, algorithm.block_action)
                           for algorithm in method.algorithms)
        lines.extend(_algorithm_table(definitions))
    if not method.stages:
        lines.extend(["The reference group is trivial: every reachable colored state in this "
                      "reference shape is already solved. No algorithms are needed.", ""])
        return recognition_wording("\n".join(lines))
    for stage in method.stages:
        orientation = stage.feature.kind == "orient_slots"
        general = bool(stage.recognition_features) or stage.feature.kind in (
            "place_blocks", "solve_blocks", "occupy_slots", "place_blocks_up_to_alignment", "solve_blocks_up_to_actions")
        block = None if orientation or general else inventory.blocks[stage.block_index]
        placed = all(case.observation[0] == stage.block_index for case in stage.cases)
        verb = ("Prepare remaining actions" if stage.feature.kind == "solve_blocks_up_to_actions" else
                "Place up to alignment" if stage.feature.kind == "place_blocks_up_to_alignment" else
                "Place" if stage.feature.kind in ("place_block", "place_blocks") else
                "Retain region" if stage.feature.kind == "occupy_slots" else
                "Orient slots" if orientation else "Orient" if placed else "Solve")
        lines.extend([f"## Stage {stage.number}: {verb} {stage.block_name}", "",
                      f"There are {stage.case_count} cases. This stage reduces the remaining "
                      f"possibilities from {stage.order_before:,} to {stage.order_after:,}.", ""])
        if general:
            lines.extend(["Commit to " + _feature_name(stage.feature, inventory) + ". "
                          "Match all listed observations to choose the correction. "
                          "Destinations identify reference footprints; phases use their declared frames.", "",
                          "| Recognition pattern | Correction |", "| --- | --- |"])
        elif orientation:
            lines.extend([_orientation_explanation(stage, inventory), "",
                          "| Slot orientations | Correction |", "| --- | --- |"])
        elif stage.feature.kind == "place_block":
            lines.extend(["Find the footprint occupied by this colored block. Ignore its orientation "
                          "while choosing the case.", "",
                          "| Current footprint | Correction |", "| --- | --- |"])
        else:
            lines.extend(["Find the footprint and the named reference sticker. The sticker cue "
                          "distinguishes the observable orientations at that footprint.", "",
                          "| Current footprint | Reference sticker currently at | Phase | Correction |",
                          "| --- | --- | --- | --- |"])
        points = (() if block is None else
                  tuple(point for cell in block.cells for point in _CELL_POINTS[cell]))
        anchor = points[0] if points else None
        for case in stage.cases:
            algorithm = next((algorithm for algorithm in method.algorithms
                              if algorithm.id == case.algorithm_id), None)
            skip = "Skip — already placed" if stage.feature.kind == "place_block" else "Skip — already correct"
            correction = (skip if case.algorithm_id is None else
                          f"`{case.algorithm_id}: {algorithm.turn_sequence or '(no moves)'}`")
            if general:
                lines.append(f"| {_recognition_cue(stage, case.observation, inventory)} | {correction} |")
                continue
            if orientation:
                lines.append(f"| {_orientation_cue(stage, case.observation, inventory)} | {correction} |")
                continue
            destination = inventory.blocks[case.observation[0]]
            footprint = f"`{destination.compact_name}`"
            if stage.feature.kind == "place_block":
                lines.append(f"| {footprint} | {correction} |")
            else:
                cue = (f"`{_sticker(anchor)} → {_sticker(case.representative[anchor])}`"
                       if anchor is not None else "Unmarked")
                phase = case.observation[1]
                lines.append(f"| {footprint} | {cue} | {phase} (mod {block.orientation_order}) | {correction} |")
        lines.append("")
        if stage.feature.kind == "solve_block":
            lines.extend([f"Phase is a coordinate modulo {block.orientation_order} in the declared "
                          "reference and destination frames. Phase 0 at the reference footprint is solved. "
                          "The concrete sticker cue is the recognition rule; a phase number is not "
                          "an instruction to twist this block independently.", ""])
        if stage.implied_features:
            lines.extend(["Also correct automatically after this stage: "
                          + "; ".join(_feature_name(feature, inventory)
                                      for feature in stage.implied_features) + ".", ""])
    if method.skipped_features:
        lines.extend(["Requested redundant features were omitted because earlier constraints already "
                      "force them: " + "; ".join(_feature_name(feature, inventory)
                                               for feature in method.skipped_features) + ".", ""])
    lines.extend(["After the final stage, every modeled corner and edge sticker is solved. "
                  "Unmarked center spin and independent virtual-core spin are outside this model.", ""])
    return recognition_wording("\n".join(lines))
