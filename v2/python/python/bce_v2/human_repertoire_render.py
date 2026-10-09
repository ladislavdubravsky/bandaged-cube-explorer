"""Concrete recognition cues and shared witnessed master definitions."""

from .block_actions import _CELL_POINTS
from .human_render import _algorithm_table, _feature_name, _sticker
from .human_diagram_modes import DiagramMode
from .human_instruction_render import instruction_presentation


def _guide_instructions(repertoire, *, rotate_diagram):
    """Collect exact case words and any additional definitions before teaching."""
    from dataclasses import replace

    presentations, additional = {}, []
    words = {macro.algorithm.turn_sequence: macro.id for macro in repertoire.macros}
    identifiers = {macro.id for macro in repertoire.macros}
    for stage in repertoire.stages:
        recipes = [case.instruction for case in stage.cases if case.instruction is not None]
        if not rotate_diagram:
            recipes.extend(rule.recipe for rule in stage.rules)
        for recipe in recipes:
            if recipe in presentations:
                continue
            presentation = instruction_presentation(recipe, repertoire, rotate_diagram=rotate_diagram)
            if presentation.requires_definition:
                word = presentation.turn_sequence
                if word not in words:
                    number = 1
                    while f"A{number}" in identifiers:
                        number += 1
                    identifier = f"A{number}"
                    identifiers.add(identifier)
                    words[word] = identifier
                    additional.append((identifier, word, presentation.rotation))
                presentation = replace(presentation, identifier=words[word])
            presentations[recipe] = presentation
    return presentations, additional


def _instruction(presentation):
    return f"`{presentation.identifier}: {presentation.turn_sequence or '(no moves)'}`"


def _additional_algorithm_action(method, word, rotation):
    """Describe an additional definition in its pictured execution frame."""
    from . import State
    from .block_actions import BlockInventory, _ROTATIONS
    from .loop_rotations import rotation_tuple

    reference = method.reference_shape.rotated(_ROTATIONS.index(rotation_tuple(rotation)))
    inventory = BlockInventory(reference)
    return inventory.action(State().apply(word).sticker_permutation)


def _cue(stage, observation, method):
    block = method.inventory.blocks[stage.block_index]
    destination = method.inventory.blocks[observation[0]]
    footprint = f"`{destination.compact_name}`"
    if stage.feature.kind == "place_block":
        return footprint
    points = tuple(point for cell in block.cells for point in _CELL_POINTS[cell])
    case = next(case for case in stage.cases if case.observation == observation)
    sticker = (f"`{_sticker(points[0])} → {_sticker(case.representative[points[0]])}`"
               if points else "Unmarked")
    return f"{footprint}; {sticker}"


def _rule_lines(rule, stage, method, presentations):
    """Present every instruction family with all its concrete case cues."""
    lines = [f"### {rule.id}", ""]
    if rule.kind == "cycle":
        lines.extend([f"These cases form one cycle under {_instruction(presentations[rule.recipe])}. "
                      "Use the signed power below to reach this stage's solved observation.", "",
                      "Cycle in the fixed reference frame: "
                      + " → ".join(_cue(stage, observation, method) for observation in rule.cycle) + ".", ""])
    elif rule.kind == "powers":
        lines.extend([f"These cases share {_instruction(presentations[rule.recipe])}. "
                      "Choose its signed power using the block's concrete cue.", ""])
    else:
        lines.extend([f"For the following cues, execute {_instruction(presentations[rule.recipe])} once.", ""])
    if rule.kind in ("powers", "cycle"):
        lines.extend(["| Current cue | Signed power |", "| --- | ---: |"])
        for observation, exponent in zip(rule.observations, rule.exponents):
            lines.append(f"| {_cue(stage, observation, method)} | {exponent} |")
    else:
        lines.extend(["| Current cue |", "| --- |"])
        lines.extend(f"| {_cue(stage, observation, method)} |" for observation in rule.observations)
    lines.append("")
    return lines


def repertoire_guide(repertoire, path=None, *, diagram_mode: DiagramMode | None = None,
                     face_colors=None):
    """Render full recognition coverage with shared masters and net commands.

    Original-loop provenance remains in the portable record. The taught words
    are the selected master definitions rather than the generating witness basis.
    """
    from pathlib import Path

    if diagram_mode is not None:
        from .human_diagram_render import (recognition_diagram_image, validate_diagram_mode,
                                           validate_face_colors)
        from .human_diagrams import recognition_stage_diagrams
        diagram_mode = validate_diagram_mode(diagram_mode)
        face_colors = validate_face_colors(face_colors)

    method, inventory = repertoire.method, repertoire.method.inventory
    presentations, additional = _guide_instructions(repertoire, rotate_diagram=diagram_mode is not None)
    lines = ["# Reference-shape method with a shared repertoire", "",
             f"This computational method covers all **{method.group_order:,} reachable colored states** "
             "whose bandage shape is already the declared reference shape.", ""]
    if repertoire.macros or additional:
        lines.extend(["## Algorithms", "",
                      "Singmaster notation uses U/R/F/D/L/B, an apostrophe "
                      "for an inverse turn, and 2 for a half turn. Each algorithm starts and ends at "
                      "the reference shape. Structured notation: "
                      "`S^A` means A⁻¹ S A, `[A, B]` means A B A⁻¹ B⁻¹, and `(A)n` repeats A "
                      "n times.", ""])
        definitions = [(macro.id, macro.algorithm.turn_sequence, macro.algorithm.block_action)
                       for macro in repertoire.macros]
        definitions.extend((identifier, word, _additional_algorithm_action(method, word, rotation))
                           for identifier, word, rotation in additional)
        lines.extend(_algorithm_table(definitions))
    if not method.stages:
        lines.extend(["The reference group is trivial. Every reachable colored state in this reference "
                      "shape is already solved; no algorithms are needed.", ""])
    for stage, policy in zip(method.stages, repertoire.stages):
        block = inventory.blocks[stage.block_index]
        placed = all(case.observation[0] == stage.block_index for case in stage.cases)
        verb = "Place" if stage.feature.kind == "place_block" else "Orient" if placed else "Solve"
        families = "instruction family" if len(policy.rules) == 1 else "instruction families"
        lines.extend([f"## Stage {stage.number}: {verb} {stage.block_name}", "",
                      f"This stage has {stage.case_count} exact cases and {len(policy.rules)} {families}. "
                      f"It reduces the remaining possibilities from {stage.order_before:,} "
                      f"to {stage.order_after:,}.", ""])
        if diagram_mode is not None:
            pictures = recognition_stage_diagrams(method, stage.number)
            for index, case in enumerate(policy.cases, 1):
                presentation = None if case.instruction is None else presentations[case.instruction]
                instruction = ("Skip — already correct" if presentation is None else
                               f"Execute {_instruction(presentation)}.")
                variants = pictures[case.observation]
                lines.extend([f"### Case {index}", "", instruction, ""])
                if variants[0].orientation_independent:
                    lines.extend(["Any shown sticker orientation belongs to this case.", ""])
                image = recognition_diagram_image(variants, diagram_mode=diagram_mode,
                                                  face_colors=face_colors,
                                                  rotation="" if presentation is None else presentation.rotation)
                lines.extend([f'![Stage {stage.number}, case {index}: {stage.block_name}]({image})', ""])
            if stage.implied_features:
                lines.extend(["Also correct automatically after this stage: "
                              + "; ".join(_feature_name(feature, inventory) for feature in stage.implied_features)
                              + ".", ""])
            continue
        for rule in policy.rules:
            lines.extend(_rule_lines(rule, stage, method, presentations))
        lines.extend(["### Complete cue lookup", "",
                      "Use these instructions until the solved case appears. Each row gives the next "
                      "whole instruction rather than a new word to memorize.", ""])
        if stage.feature.kind == "place_block":
            lines.extend(["| Current footprint | Instruction | Rank |", "| --- | --- | ---: |"])
        else:
            lines.extend(["| Current footprint | Reference sticker currently at | Phase | Instruction | Rank |",
                          "| --- | --- | --- | --- | ---: |"])
        points = tuple(point for cell in block.cells for point in _CELL_POINTS[cell])
        anchor = points[0] if points else None
        representatives = {case.observation: case.representative for case in stage.cases}
        for case in policy.cases:
            destination = inventory.blocks[case.observation[0]]
            footprint = f"`{destination.compact_name}`"
            instruction = ("Skip — already correct" if case.instruction is None else
                           _instruction(presentations[case.instruction]))
            if stage.feature.kind == "place_block":
                lines.append(f"| {footprint} | {instruction} | {case.rank} |")
            else:
                cue = (f"`{_sticker(anchor)} → {_sticker(representatives[case.observation][anchor])}`"
                       if anchor is not None else "Unmarked")
                lines.append(f"| {footprint} | {cue} | {case.observation[1]} "
                             f"(mod {block.orientation_order}) | {instruction} | {case.rank} |")
        lines.append("")
        if stage.feature.kind == "solve_block":
            lines.extend([f"Phase is a coordinate modulo {block.orientation_order} in the declared "
                          "reference and destination frames. Phase 0 at the reference footprint is solved. "
                          "Use the concrete sticker cue to choose the instruction; the phase number "
                          "does not prescribe an independent twist of this block.", ""])
        if stage.implied_features:
            lines.extend(["Also correct automatically after this stage: "
                          + "; ".join(_feature_name(feature, inventory) for feature in stage.implied_features)
                          + ".", ""])
    if method.skipped_features:
        lines.extend(["Earlier constraints already force these requested redundant features: "
                      + "; ".join(_feature_name(feature, inventory) for feature in method.skipped_features) + ".", ""])
    lines.extend(["After the final stage every modeled corner and edge sticker is solved. "
                  "Unmarked center spin and independent virtual-core spin are outside this model.", ""])
    guide = "\n".join(lines)
    if path is not None:
        Path(path).write_text(guide, encoding="utf-8")
    return guide
