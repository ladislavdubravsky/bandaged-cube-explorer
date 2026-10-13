#!/usr/bin/env python3
"""Audit and preview the case diagrams of three portable action-family methods.

Load archived certificates without GAP or discovery. Check every observation,
replay the existing instructions natively, and replay all 324 archived Alcatraz
reference states. Render each guide once, reusing its embedded PNGs for previews.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from statistics import mean
from unittest.mock import patch


V2 = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(V2 / ".cache" / "matplotlib"))

import bce_v2 as c
from bce_v2.human_chains import _observation, _resolve_feature
from bce_v2.human_methods import (_stage_observation, _state_for_permutation,
                                _then)
from bce_v2.palette_render import certified_procedure
from bce_v2.stage_diagrams import stage_case_diagrams, stage_recognition_diagrams


_GALLERIES = re.compile(r"### Diagrammatic guide:\n.*?(?=## Stage |The \d+ learned bodies)",
                        re.DOTALL)
_IMAGES = re.compile(r"!\[Stage (\d+) recognition pattern\]\(data:image/png;base64,([A-Za-z0-9+/=]+)\)")


def _preserved(method, stage, state):
    """Check the entry domain and every prior stage at an operation endpoint."""
    inventory, action = method.inventory, method.inventory.action(state)
    identity = inventory.identity()
    assert state.shape == method.reference_shape
    for feature in method.domain_features:
        handle = _resolve_feature(inventory, feature)
        assert _observation(action, handle, feature.kind) == _observation(identity, handle, feature.kind)
    for previous in method.stages[:stage.number - 1]:
        assert _observation(action, previous.block_index, previous.feature.kind) == previous.solved_observation


def _instruction(method, stage, procedure, observation, state):
    """Replay complete permitted operations, preserving earlier goals each time."""
    algorithms = {algorithm.id: algorithm for algorithm in method.palette.recipes}
    group = method.ambient_method._symbolic_chain.stages[
        method.prefix_stage_count + stage.number - 1].group_before
    recipe = procedure.instruction_for(observation)
    ranks = dict(zip(procedure.observations, procedure.ranks))
    htm = qtm = 0
    for identifier in recipe:
        algorithm = algorithms[identifier]
        assert algorithm.permutation in group
        previous = state.sticker_permutation
        # Native apply checks legal physical turns, including intermediate
        # shape changes and displacement inside a complete operation.
        state = state.apply(algorithm.turn_sequence)
        assert state.sticker_permutation == _then(previous, algorithm.permutation)
        assert state.sticker_permutation in group
        _preserved(method, stage, state)
        htm += algorithm.htm_length
        qtm += algorithm.qtm_length
    successor = _stage_observation(method.inventory.action(state), stage, method.inventory)
    if observation == procedure.solved_observation:
        assert not recipe
    else:
        assert recipe and ranks[successor] < ranks[observation]
    return state, successor, htm, qtm, len(recipe)


def _check_case(method, stage, procedure, picture, *, allowed_observations=None):
    inventory = method.inventory
    group = method.ambient_method._symbolic_chain.stages[
        method.prefix_stage_count + stage.number - 1].group_before
    assert picture.stage_number == stage.number
    assert picture.observation in stage.observations and picture.variants
    allowed = ({picture.observation} if allowed_observations is None else
               set(allowed_observations))
    assert picture.observation in allowed and allowed <= set(stage.observations)
    assert picture.ready == (picture.observation == procedure.solved_observation)
    assert picture.cue and not re.search(r"\b(?:footprints?|phases?|markers?|facets?|structure|commit to)\b",
                                       picture.cue + " " + " ".join(picture.notes), re.IGNORECASE)
    for variant in picture.variants:
        state, action = variant.state, inventory.action(variant.state)
        assert state.specification == method.reference_shape
        assert state.sticker_permutation in group
        observation = _stage_observation(action, stage, inventory)
        assert observation in allowed
        assert procedure.instruction_for(observation) == procedure.instruction_for(picture.observation)
        _preserved(method, stage, state)
        count = len(inventory.blocks)
        for indices in (variant.full_blocks, variant.location_blocks, variant.solved_blocks):
            assert indices == tuple(sorted(set(indices)))
            assert all(type(index) is int and 0 <= index < count for index in indices)
        assert not set(variant.full_blocks).intersection(variant.location_blocks)
        assert all(0 <= sticker < 54 and sticker % 9 != 4 for sticker in variant.reference_stickers)
        for source, label in variant.piece_labels:
            assert label == inventory.blocks[source].compact_name
        for slot, label in variant.slot_labels:
            assert label == inventory.blocks[slot].compact_name
        source_at = {cell: source for source, destination in enumerate(action.destinations)
                     for cell in inventory.blocks[destination].cells}
        from bce_v2.stage_diagram_render import _facelet_cell
        for sticker, reading in variant.orientation_labels:
            assert sticker in variant.reference_stickers
            assert reading == str(action.phases[source_at[_facelet_cell(sticker)]])
        for region in variant.regions:
            assert region == tuple(sorted(set(region)))
            assert all(0 <= cell < 27 for cell in region)
        for source in variant.solved_blocks:
            assert action.destinations[source] == source and action.phases[source] == 0
        _instruction(method, stage, procedure, observation, state)


def _check_recognition_rows(method, stage, procedure, rows):
    """Prove every observation selects the original recipe by first match."""
    observations, assigned = set(stage.observations), set()
    assert rows
    for row in rows:
        assert row.observations and row.matching_observations
        domain, matches = set(row.observations), set(row.matching_observations)
        assert len(domain) == len(row.observations)
        assert len(matches) == len(row.matching_observations)
        assert domain <= matches <= observations
        assert not assigned.intersection(domain)
        assigned.update(domain)
        assert row.diagram.observation in domain
        assert row.cue == row.diagram.cue
        _check_case(method, stage, procedure, row.diagram, allowed_observations=row.observations)
        for observation in domain:
            assert row.recipe == procedure.instruction_for(observation)
    assert assigned == observations
    for observation in stage.observations:
        first = next(row for row in rows if observation in row.matching_observations)
        assert observation in first.observations
        assert first.recipe == procedure.instruction_for(observation)


def _render_guide(method, *, face_colors=None):
    """Audit the actual figures while reusing their PNGs for guide previews."""
    import matplotlib.pyplot as plt
    from bce_v2 import stage_diagram_render

    render = stage_diagram_render.stage_case_figure

    def without_footer_notes(*args, **kwargs):
        figure = render(*args, **kwargs)
        try:
            assert len(figure.texts) == 1
            assert figure.texts[0] is figure._suptitle
            assert all(axis.name == "3d" and axis._focal_length == float("inf")
                       for axis in figure.axes)
        except BaseException:
            plt.close(figure)
            raise
        return figure

    before = plt.get_fignums()
    with patch("bce_v2.stage_diagram_render.stage_case_figure", side_effect=without_footer_notes):
        guide = method.write_guide(recognition_diagrams=True, face_colors=face_colors)
    assert plt.get_fignums() == before
    return guide


def _alcatraz_exhaustive(method):
    """Replay archived states rather than constructing or enumerating a group."""
    complete = c.load_human_method(V2 / "research-results" / "alcatraz-execution-method.json")
    assert len(complete._permutations) == 324
    procedures = certified_procedure(method)
    htm_costs, qtm_costs, operations, stage_inputs = [], [], 0, [0] * len(method.stages)
    for permutation in complete._permutations:
        state = _state_for_permutation(method.reference_shape, permutation)
        htm = qtm = 0
        for stage, procedure in zip(method.stages, procedures):
            certified = method.ambient_method._symbolic_chain.stages[
                method.prefix_stage_count + stage.number - 1]
            assert state.sticker_permutation in certified.group_before
            _preserved(method, stage, state)
            observation = _stage_observation(method.inventory.action(state), stage, method.inventory)
            stage_inputs[stage.number - 1] += 1
            repetitions = 0
            while observation != procedure.solved_observation:
                state, observation, stage_htm, stage_qtm, count = _instruction(
                    method, stage, procedure, observation, state)
                htm += stage_htm
                qtm += stage_qtm
                operations += count
                repetitions += 1
                assert repetitions <= procedure.maximum_repetitions
            assert state.sticker_permutation in certified.group_after
        assert state.is_solved
        htm_costs.append(htm)
        qtm_costs.append(qtm)
    return {"reference_states_replayed": len(htm_costs),
            "native_complete_operations": operations,
            "stage_boundary_inputs": stage_inputs,
            "every_stage_boundary_preserved": True,
            "all_states_solved": True,
            "physical_costs_before_between_operation_cancellation": {
                "htm": {"mean": mean(htm_costs), "worst": max(htm_costs)},
                "qtm": {"mean": mean(qtm_costs), "worst": max(qtm_costs)}}}


def validate(output_directory, *, face_colors=None):
    output_directory.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for name, load in (("alcatraz", c.load_coarse_method),
                       ("unbandaged", c.WorkspaceMethod.load),
                       ("shark-fin-soup", c.load_coarse_method)):
        print(f"Validating {name}: loading portable cases and checking native instructions...", flush=True)
        artifact = V2 / "research-results" / f"compact-{name}.method.json"
        method = load(artifact)
        suffix = method.suffix if isinstance(method, c.WorkspaceMethod) else method
        certificate, costs = method.to_dict(), suffix.additive_costs()
        taught = tuple(suffix.taught_body_ids)
        procedures = certified_procedure(suffix)
        stages = []
        for stage, procedure in zip(suffix.stages, procedures):
            pictures = stage_case_diagrams(suffix, stage.number)
            assert tuple(picture.observation for picture in pictures) == stage.observations
            for picture in pictures:
                _check_case(suffix, stage, procedure, picture)
            recognition = stage_recognition_diagrams(suffix, stage.number, procedure)
            _check_recognition_rows(suffix, stage, procedure, recognition)
            stages.append({"stage": stage.number, "goal_kind": stage.feature.kind,
                           "observations": len(pictures),
                           "exact_physical_variants": sum(len(picture.variants) for picture in pictures),
                           "recognition_case_count": len(recognition),
                           "rendered_variants": sum(len(row.diagram.variants) for row in recognition),
                           "physical_variants": sum(len(row.diagram.variants) for row in recognition),
                           "ready_patterns": sum(picture.ready for picture in pictures),
                           "instruction_forms": procedure.instruction_family_count,
                           "maximum_repetitions": procedure.maximum_repetitions,
                           "recognition_and_prior_guarantees_checked": True,
                           "ordered_first_match_checked": True,
                           "effective_recognition_domains_cover_all_observations": True,
                           "recognition_cases": [{"case": number, "cue": row.cue,
                                                  "observations": len(row.observations),
                                                  "matching_observations": len(row.matching_observations),
                                                  "ready": row.diagram.ready}
                                                 for number, row in enumerate(recognition, 1)],
                           "native_instructions_checked": True})
        exhaustive = _alcatraz_exhaustive(suffix) if name == "alcatraz" else None
        print(f"Rendering {name}: {sum(row['recognition_case_count'] for row in stages)} "
              f"recognition diagrams cover {sum(row['observations'] for row in stages)} observations...", flush=True)
        plain = method.write_guide()
        illustrated = _render_guide(method, face_colors=face_colors)
        assert _GALLERIES.sub("", illustrated) == plain
        assert illustrated.count("### Diagrammatic guide:") == len(stages)
        assert "Recognition notation examples" not in illustrated
        assert method.to_dict() == certificate and suffix.additive_costs() == costs
        assert tuple(suffix.taught_body_ids) == taught
        assert certified_procedure(suffix) == procedures
        guide = output_directory / f"{name}.md"
        guide.write_text(illustrated, encoding="utf-8")
        images = {}
        for stage_number, encoded in _IMAGES.findall(illustrated):
            png = base64.b64decode(encoded, validate=True)
            assert png.startswith(b"\x89PNG\r\n\x1a\n")
            images.setdefault(int(stage_number), []).append(png)
        assert sum(len(pngs) for pngs in images.values()) == sum(row["recognition_case_count"] for row in stages)
        for row in stages:
            pngs = images[row["stage"]]
            assert len(pngs) == row["recognition_case_count"]
            # Ready appears first; choose the first nonready pattern when one
            # exists. Reuse guide bytes, avoiding a second render.
            preview = output_directory / f"{name}-stage-{row['stage']}.png"
            preview.write_bytes(pngs[min(1, len(pngs) - 1)])
            row["preview"] = str(preview.relative_to(output_directory))
        fixture = {"puzzle": name, "artifact": str(artifact.relative_to(V2)),
                   "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                   "stages": stages,
                   "observations_checked": sum(row["observations"] for row in stages),
                   "recognition_case_count": sum(row["recognition_case_count"] for row in stages),
                   "case_diagrams": sum(row["recognition_case_count"] for row in stages),
                   "rendered_variants": sum(row["rendered_variants"] for row in stages),
                   "physical_variants": sum(row["physical_variants"] for row in stages),
                   "learned_bodies": len(taught), "instructions_byte_identical_without_galleries": True,
                   "portable_certificate_unchanged": True, "physical_costs_unchanged": True,
                   "ordered_first_match_checked": True,
                   "no_footer_notes_in_rendered_figures": True,
                   "saved_policy_costs": costs,
                   "procedure_costs_before_between_operation_cancellation": {
                       metric: {"mean": sum(mean(getattr(procedure, metric + "_costs"))
                                             for procedure in procedures),
                                "worst": sum(max(getattr(procedure, metric + "_costs"))
                                             for procedure in procedures)}
                       for metric in ("htm", "qtm")},
                   "guide_preview": guide.name}
        if isinstance(method, c.WorkspaceMethod):
            fixture["global_taught_definitions"] = len(method.taught_definition_ids)
            fixture["scope"] = "Certified suffix diagrams; constructive workspace entry remains bounded computation."
        else:
            fixture["scope"] = "Complete reference-shape method; no shape-restoration human strategy is claimed."
        if exhaustive:
            fixture["exhaustive_native_replay"] = exhaustive
        fixtures.append(fixture)
        print(f"Passed {name}: {fixture['case_diagrams']} diagrams, {len(taught)} suffix bodies.", flush=True)
    return {"all_checks_passed": True, "gap_used": False, "discovery_used": False,
            "new_ambient_group_enumeration_used": False,
            "observations_checked": sum(row["observations_checked"] for row in fixtures),
            "recognition_case_count": sum(row["recognition_case_count"] for row in fixtures),
            "case_diagrams": sum(row["case_diagrams"] for row in fixtures),
            "rendered_variants": sum(row["rendered_variants"] for row in fixtures),
            "physical_variants": sum(row["physical_variants"] for row in fixtures),
            "face_colors": face_colors,
            "ordered_first_match_checked": True,
            "no_footer_notes_in_rendered_figures": True,
            "views": "Opposite-corner orthographic 3D views UFR and BLD.",
            "coverage": "Every exact certified observation selects the original instruction using the first "
                "matching diagrammed recognition case, including ready cases. A partial recognition diagram "
                "can cover several observations when its visible test selects their shared instruction.",
            "alternative_arrangements": "Small declared families are combined and filtered by the whole observation. "
                "For overlapping noncommuting families or coupled extra observers, pictures are witnessed alternatives; "
                "written equivalent-pattern conditions specify all accepted arrangements. "
                "The archived fixtures use complete ordered recognition cases with certified partial display masks.",
            "fixtures": fixtures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=V2 / ".cache" / "stage-diagrams")
    parser.add_argument("--report", type=Path, default=V2 / "research-results" / "stage-diagrams.json")
    parser.add_argument("--yellow-up", action="store_true",
                        help="draw U stickers yellow and D stickers white in the preview guides")
    args = parser.parse_args()
    # Initial font discovery may invoke fontconfig. Initialize plotting before
    # forbidding external analysis processes; the rendering itself stays local.
    import matplotlib.pyplot  # noqa: F401

    with patch("subprocess.run", side_effect=AssertionError("portable validation must not launch GAP")), \
            patch("bce_v2.discover_method", side_effect=AssertionError("no method discovery")), \
            patch("bce_v2.analyze_isotropy", side_effect=AssertionError("no fresh group analysis")):
        report = validate(args.output_dir, face_colors={"U": "yellow", "D": "white"}
                          if args.yellow_up else None)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": True, "case_diagrams": report["case_diagrams"],
                      "previews": str(args.output_dir), "report": str(args.report)}, indent=2))


if __name__ == "__main__":
    main()
