"""A concrete initial guide for certified computational human-method baselines."""

from .block_actions import _CELL_POINTS, _POINTS, cell_name


_FACES = {(0, 0, 1): "U", (1, 0, 0): "R", (0, -1, 0): "F",
          (0, 0, -1): "D", (-1, 0, 0): "L", (0, 1, 0): "B"}


def _sticker(point):
    cell, normal = _POINTS[point]
    return f"{cell_name(cell)}/{_FACES[normal]}"


def _feature_name(feature, inventory):
    slot = next(block for block in inventory.blocks if block.cells == feature.cells)
    return ("place " if feature.kind == "place_block" else "fully solve ") + slot.name


def method_guide(method):
    """Render stage recognition, complete case tables and physical algorithms.

    Full-block cases include a concrete sticker cue, computed in the fixed
    reference frame. Placement cases deliberately ignore sticker orientation.
    The guide claims computational coverage, without claiming human review.
    """
    lines = ["# Reference-shape solving method", ""]
    if method.status != "completed":
        lines.extend(["Generation stopped before a complete method was available.", "",
                      f"Reason: `{method.reason}`. The reported reference-group order is "
                      f"{method.group_order:,}; the requested element limit is "
                      f"{method.max_group_elements}.", "",
                      "This artifact has no correction algorithms or case-coverage claim.", ""])
        return "\n".join(lines)
    inventory = method.inventory
    lines.extend([
        f"This computational baseline covers all **{method.group_order:,} reachable colored states** "
        "whose bandage shape is already the declared reference shape.", "",
        "The stage policies and physical algorithms have been checked exhaustively. "
        "Human memorability and ease of execution have not been reviewed; some algorithms may be long.", "",
        "## Before starting", "",
        "Restore the reference bandage shape first. Shape restoration is separate work. "
        "Keep the fixed U/R/F/D/L/B face frame throughout the method.", "",
        "Identify each colored block by its reference member cells and color pattern. "
        "A cell name such as UFR means the upper, front, right corner; UF means the upper front edge. "
        "A fused block name lists all of its reference member cells.", "",
        "A sticker label such as `UFR/U` means the U-face-colored sticker on the reference UFR cubie. "
        "An orientation cue such as `UFR/U → UBR/R` says that this same colored sticker is "
        "currently on the R face at the UBR corner. Use the reference color scheme to identify it.", "",
        "Follow the stages in order. At each stage inspect only its named block, match the case, "
        "and execute the listed algorithm completely. A solved case needs no moves.", "",
        "Algorithms may disturb earlier solved blocks and the reference shape internally. "
        "They restore both at the end of the whole correction. Make the next case decision only then.", "",
    ])
    if method.initial_features:
        names = [next(block.name for block in inventory.blocks if block.cells == feature.cells)
                 for feature in method.initial_features if feature.kind == "solve_block"]
        if names:
            lines.extend(["Blocks already forced to be solved in this reference shape: "
                          + "; ".join(names) + ".", ""])
    if not method.stages:
        lines.extend(["The reference group is trivial: every reachable colored state in this "
                      "reference shape is already solved. No algorithms are needed.", ""])
        return "\n".join(lines)
    for stage in method.stages:
        block = inventory.blocks[stage.block_index]
        placed = all(case.observation[0] == stage.block_index for case in stage.cases)
        verb = ("Place" if stage.feature.kind == "place_block" else
                "Orient" if placed else "Solve")
        lines.extend([f"## Stage {stage.number}: {verb} {stage.block_name}", "",
                      f"There are {stage.case_count} cases. This stage reduces the remaining "
                      f"possibilities from {stage.order_before:,} to {stage.order_after:,}.", ""])
        if stage.feature.kind == "place_block":
            lines.extend(["Find the footprint occupied by this colored block. Ignore its orientation "
                          "while choosing the case.", "",
                          "| Current footprint | Correction |", "| --- | --- |"])
        else:
            lines.extend(["Find the footprint and the named reference sticker. The sticker cue "
                          "distinguishes the observable orientations at that footprint.", "",
                          "| Current footprint | Reference sticker currently at | Phase | Correction |",
                          "| --- | --- | --- | --- |"])
        points = tuple(point for cell in block.cells for point in _CELL_POINTS[cell])
        anchor = points[0] if points else None
        for case in stage.cases:
            destination = inventory.blocks[case.observation[0]]
            correction = "Skip — already correct" if case.algorithm_id is None else f"`{case.algorithm_id}`"
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
    lines.extend(["## Shared correction algorithms", "",
                  "Singmaster notation uses U/R/F/D/L/B face turns, an apostrophe for the inverse, "
                  "and 2 for a half turn. Execute each complete expanded word below.", "",
                  "Expressions retain original-loop provenance. `[A, B]` means A B A⁻¹ B⁻¹; "
                  "`conj(S, A)` means S A S⁻¹. A power repeats the enclosed word. "
                  "The expanded face turns are authoritative for execution.", ""])
    for algorithm in method.algorithms:
        lines.extend([f"### {algorithm.id}", "",
                      f"{algorithm.htm_length} face turns (HTM), {algorithm.qtm_length} quarter turns (QTM).", "",
                      f"Expression: `{algorithm.expression.render()}`", "",
                      "```text", algorithm.turn_sequence or "(no moves)", "```", ""])
    lines.extend(["## Original loop definitions", "",
                  "These definitions make every provenance expression self-contained. "
                  "Each loop starts and ends at the reference shape.", ""])
    for generator in method.generators:
        lines.extend([f"### L{generator.id}", "", "```text",
                      generator.turn_sequence or "(no moves)", "```", ""])
    if method.skipped_features:
        lines.extend(["Requested redundant features were omitted because earlier constraints already "
                      "force them: " + "; ".join(_feature_name(feature, inventory)
                                               for feature in method.skipped_features) + ".", ""])
    lines.extend(["After the final stage, every modeled corner and edge sticker is solved. "
                  "Unmarked center spin and independent virtual-core spin are outside this model.", ""])
    return "\n".join(lines)
