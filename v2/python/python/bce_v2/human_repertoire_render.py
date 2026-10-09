"""Concrete recognition cues and shared witnessed master definitions."""

from .block_actions import _CELL_POINTS
from .human_render import _feature_name, _sticker


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


def _rule_lines(rule, stage, method):
    """Present every instruction family with all its concrete case cues."""
    lines = [f"### {rule.id}", ""]
    if rule.kind == "cycle":
        lines.extend([f"These cases form one cycle under `{rule.recipe.render()}`. "
                      "Use the signed power below to reach this stage's solved observation.", "",
                      "Cycle in the fixed reference frame: "
                      + " → ".join(_cue(stage, observation, method) for observation in rule.cycle) + ".", ""])
    elif rule.kind == "powers":
        lines.extend([f"These cases share the master recipe `{rule.recipe.render()}`. "
                      "Choose its signed power using the block's concrete cue.", ""])
    else:
        lines.extend([f"For the following cues, execute `{rule.recipe.render()}` once, "
                      "then inspect this stage's block again.", ""])
    if rule.kind in ("powers", "cycle"):
        lines.extend(["| Current cue | Signed power |", "| --- | ---: |"])
        for observation, exponent in zip(rule.observations, rule.exponents):
            lines.append(f"| {_cue(stage, observation, method)} | {exponent} |")
    else:
        lines.extend(["| Current cue |", "| --- |"])
        lines.extend(f"| {_cue(stage, observation, method)} |" for observation in rule.observations)
    lines.append("")
    return lines


def repertoire_guide(repertoire, path=None):
    """Render full recognition coverage with shared masters and net commands.

    Original-loop provenance remains in the portable record. The taught words
    are the selected master definitions rather than the generating witness basis.
    """
    from pathlib import Path

    method, inventory = repertoire.method, repertoire.method.inventory
    lines = ["# Reference-shape method with a shared repertoire", "",
             f"This computational method covers all **{method.group_order:,} reachable colored states** "
             "whose bandage shape is already the declared reference shape.", "",
             "Every full case route, repeated instruction, and recognition family has been checked. "
             "Human memorability and ease of execution await the planned human review.", "",
             "## Before starting", "",
             "Restore the reference bandage shape first, and keep the fixed U/R/F/D/L/B face frame. "
             "Shape restoration is separate work.", "",
             "Identify each colored block by its reference cells and color pattern. "
             "A name such as UFR denotes the upper, front, right corner; UF denotes the upper front edge. "
             "A fused block name lists its reference member cells.", "",
             "A cue such as `UFR/U → UBR/R` identifies the U-face-colored sticker of the reference "
             "UFR cubie, currently on the R face at UBR. Use the reference color scheme to find it.", "",
             "Follow the stages in order. Match the current footprint or sticker cue, execute the "
             "listed instruction completely, and inspect the same stage again. Advance when its "
             "solved cue appears. Rank is a progress coordinate: it strictly decreases after each "
             "instruction, so repetition terminates.", "",
             "Make case decisions only at whole-instruction boundaries. A power or setup/body/undo "
             "recipe can temporarily disturb earlier solved blocks. Its complete instruction restores "
             "them and the reference shape. Do not inspect between repetitions inside a listed power "
             "or between pieces of a setup recipe.", "",
             "Master names such as M1 refer to the shared words below. A negative power executes the "
             "inverse word: reverse its turns and invert each turn. `[A, B]` means A B A⁻¹ B⁻¹; "
             "`conj(S, A)` means S A S⁻¹. A listed rotation transfers the word through the indicated "
             "regrip and undo; its face-only execution is already checked for this bandage. "
             "The whole-cube regrips x, y, and z turn the cube in the directions of R, U, and F "
             "respectively. `rotate(rho, M)` means regrip by rho, execute M in that frame, then "
             "undo the regrip.", ""]
    names = [next(block.name for block in inventory.blocks if block.cells == feature.cells)
             for feature in method.initial_features if feature.kind == "solve_block"]
    if names:
        lines.extend(["Blocks already forced to be solved in this reference shape: " + "; ".join(names) + ".", ""])
    if not method.stages:
        lines.extend(["The reference group is trivial. Every reachable colored state in this reference "
                      "shape is already solved; no master definitions are needed.", ""])
    for stage, policy in zip(method.stages, repertoire.stages):
        block = inventory.blocks[stage.block_index]
        placed = all(case.observation[0] == stage.block_index for case in stage.cases)
        verb = "Place" if stage.feature.kind == "place_block" else "Orient" if placed else "Solve"
        families = "instruction family" if len(policy.rules) == 1 else "instruction families"
        lines.extend([f"## Stage {stage.number}: {verb} {stage.block_name}", "",
                      f"This stage has {stage.case_count} exact cases and {len(policy.rules)} {families}. "
                      f"It reduces the remaining possibilities from {stage.order_before:,} "
                      f"to {stage.order_after:,}.", ""])
        if stage.feature.kind == "place_block":
            lines.extend(["Find this colored block's footprint. Ignore its sticker orientation for this stage.", ""])
        else:
            lines.extend(["Find this colored block's footprint and the named reference sticker. "
                          "The sticker cue distinguishes its observable orientations.", ""])
        for rule in policy.rules:
            lines.extend(_rule_lines(rule, stage, method))
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
            instruction = "Skip — already correct" if case.instruction is None else f"`{case.instruction.render()}`"
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
    if repertoire.macros:
        lines.extend(["## Shared master definitions", "",
                      "Learn these shared words. Singmaster notation uses U/R/F/D/L/B, an apostrophe "
                      "for an inverse turn, and 2 for a half turn. Each master starts and ends at "
                      "the reference shape. Its admissibility depends on the complete instruction "
                      "listed for the current stage.", ""])
        for macro in repertoire.macros:
            algorithm = macro.algorithm
            lines.extend([f"### {macro.id}", "",
                          f"{algorithm.htm_length} face turns (HTM), {algorithm.qtm_length} quarter turns (QTM).", "",
                          "```text", algorithm.turn_sequence or "(no moves)", "```", ""])
    if method.skipped_features:
        lines.extend(["Earlier constraints already force these requested redundant features: "
                      + "; ".join(_feature_name(feature, inventory) for feature in method.skipped_features) + ".", ""])
    lines.extend(["After the final stage every modeled corner and edge sticker is solved. "
                  "Unmarked center spin and independent virtual-core spin are outside this model.", "",
                  "## Witness provenance", "",
                  "The portable repertoire stores every master's original-loop expression, complete "
                  "expanded case routes, the generating witness basis, and the original baseline. "
                  "These records support independent replay and coverage checks; the shared words "
                  "above are the repertoire used by this guide.", ""])
    for macro in repertoire.macros:
        lines.append(f"- {macro.id}: `{macro.algorithm.expression.render()}`")
    lines.append("")
    guide = "\n".join(lines)
    if path is not None:
        Path(path).write_text(guide, encoding="utf-8")
    return guide
