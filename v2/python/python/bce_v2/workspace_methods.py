"""Adaptive constructive entry followed by a certified palette suffix.

The suffix's preservation-derived workspace guides the entry target. Small
connected collections are chosen from the current physical arrangement; their
corrections may disturb earlier commitments internally and restore them at the
endpoint. Entry is bounded search, with no whole-scramble coverage claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
import json
from pathlib import Path

from . import State
from ._moves import _simplified_moves
from .algorithm_palette import AlgorithmPalette
from .coarse_methods import CoarseMethod, _load_palette, _palette_record
from .human_chains import BlockFeature, _feature_indices
from .palette_policies import recipe_taught_ids


def _limit(value, name, minimum=0):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _merge_palettes(first, second):
    def merge(name):
        found = {}
        for declaration in (*getattr(first, name), *getattr(second, name)):
            prior = found.get(declaration.id)
            if prior is not None:
                if (prior.algorithm.turn_sequence != declaration.algorithm.turn_sequence or
                        prior.algorithm.permutation != declaration.algorithm.permutation or
                        (name == "bodies" and prior.allow_inverse != declaration.allow_inverse)):
                    raise ValueError("entry and suffix disagree on a shared palette declaration")
            else:
                found[declaration.id] = declaration
        return tuple(found[key] for key in sorted(found))
    return AlgorithmPalette(merge("bodies"), merge("setups"), merge("adjustments"))


@dataclass(frozen=True)
class WorkspaceMethodApplication:
    status: str
    state: State
    entry_steps: tuple = ()
    suffix_application: object | None = None
    reason: str | None = None
    _metadata_json: str = field(default="{}", repr=False)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    @property
    def turn_sequence(self):
        words = [step.turn_sequence for step in self.entry_steps]
        if self.suffix_application is not None:
            words.append(self.suffix_application.turn_sequence)
        return _simplified_moves(" ".join(words).split())

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())


@dataclass(frozen=True)
class WorkspaceMethod:
    suffix: CoarseMethod
    entry_palette: AlgorithmPalette
    _settings_json: str = field(repr=False)

    @property
    def settings(self):
        return json.loads(self._settings_json)

    @property
    def reference_shape(self):
        return self.suffix.reference_shape

    @property
    def inventory(self):
        return self.suffix.inventory

    @cached_property
    def controller(self):
        from .workspace_entry import ConstructiveEntryController
        return ConstructiveEntryController(self.suffix.ambient_method,
            palette=self.entry_palette, **self.settings["controller_options"])

    @cached_property
    def target_indices(self):
        indices = set()
        for feature in self.suffix.domain_features:
            if feature.kind not in ("solve_block", "solve_blocks"):
                raise ValueError("adaptive entry currently requires full-pose component domain goals")
            indices.update(_feature_indices(self.inventory, feature))
        return tuple(sorted(indices))

    @cached_property
    def palette(self):
        """Combined declarations for canonical shared teaching identities.

        Execution stays in the entry and suffix palettes. Re-mining derived
        actions on the union could evict an already certified operation under
        the bounded candidate cap, so this registry supplies base calls only.
        """
        return _merge_palettes(self.suffix.palette, self.entry_palette)

    @cached_property
    def taught_definition_ids(self):
        taught = recipe_taught_ids(self.palette, self.settings["max_short_setup_htm"])
        from .palette_render import expanded_recipe_path
        calls = (*expanded_recipe_path(self.entry_palette,
                    (recipe.id for recipe in self.entry_palette.recipes)),
                 *expanded_recipe_path(self.suffix.palette,
                    (identifier for _, _, path in self.suffix.case_recipes for identifier in path)))
        return tuple(sorted({identifier for call in calls for identifier in taught[call]}))

    @property
    def coverage_scope(self):
        return "bounded_constructive_entry_then_certified_domain_suffix"

    @property
    def human_method_complete(self):
        return False

    @cached_property
    def assemblies(self):
        from .assembly_goals import propose_relative_assemblies
        cells = tuple(cell for index in self.target_indices for cell in self.inventory.blocks[index].cells)
        if not cells or self.settings["max_components"] < 2:
            return ()
        return propose_relative_assemblies(self.inventory, eligible_cells=cells,
            max_components=self.settings["max_components"],
            max_candidates=self.settings["max_proposals"]).goals

    @cached_property
    def anchors(self):
        from .workspace_goals import propose_workspace_anchors
        cells = tuple(cell for index in self.target_indices for cell in self.inventory.blocks[index].cells)
        if not cells:
            return ()
        return propose_workspace_anchors(self.inventory, cells,
            max_candidates=self.settings["max_candidates"]).features

    def validate(self):
        # The suffix supplies the exact original-loop and ambient certificates.
        self.entry_palette.validate(inventory=self.inventory, generators=self.suffix.generators,
                                    group=self.suffix.ambient_method._symbolic_chain.group)
        self.target_indices
        if len(self.taught_definition_ids) > self.settings["max_taught_bodies"]:
            raise ValueError("entry alphabet and suffix exceed the global taught-definition budget")
        self.controller
        return self

    def _solved_indices(self, state):
        action = self.inventory.action(state)
        return {index for index in self.target_indices
                if action.destinations[index] == index and action.phases[index] == 0}

    def _candidates(self, state, committed, anchor):
        from .assembly_goals import observe_relative_assembly
        remaining = set(self.target_indices) - committed
        if anchor is None:
            anchors = tuple(feature for feature in self.anchors
                            if not set(_feature_indices(self.inventory, feature)).issubset(committed))
            if anchors:
                return anchors
        result = []
        for goal in self.assemblies:
            indices = set(_feature_indices(self.inventory, BlockFeature("solve_blocks", goal.cells)))
            new = indices & remaining
            if not new:
                continue
            observed = observe_relative_assembly(self.inventory, state, goal)
            # A joined pair or a convenient expansion is tried before an
            # unassembled collection. Existing commitments are observed too.
            rank = (not observed.assembled, -len(new), not bool(indices & committed),
                    -observed.matched_component_count, goal.cells)
            result.append((rank, BlockFeature("solve_blocks", goal.cells)))
        singles = []
        for index in sorted(remaining):
            cells = self.inventory.blocks[index].cells
            singles.append(((True, 0, True, 0, cells), BlockFeature("solve_block", cells)))
        result.extend(singles)
        result.sort(key=lambda row: row[0])
        # Distinct collections may share all new members but differ in an
        # already fixed neighbor. Keep those choices: they express expansions.
        count = self.settings["max_candidates"]
        selected = [feature for _, feature in result[:count]]
        if count > 1 and singles and not any(feature.kind == "solve_block" for feature in selected):
            selected[-1] = singles[0][1]
        return tuple(selected)

    def apply(self, state):
        if not isinstance(state, State):
            raise TypeError("workspace method requires a colored State")
        settings = self.settings
        metadata = {"coverage_scope": self.coverage_scope,
                    "entry_coverage_certified": False,
                    "taught_definition_ids": list(self.taught_definition_ids),
                    "entry_candidates_tried": 0, "entry_nodes_expanded": 0,
                    "entry_stop_reasons": [], "adaptive_choices": []}
        steps, current = [], state
        def result(status, reason=None, suffix=None):
            return WorkspaceMethodApplication(status, current, tuple(steps), suffix, reason,
                                              json.dumps(metadata, sort_keys=True))
        if state.specification != self.reference_shape:
            return result("wrong_reference", "state has another reference specification")
        if state.shape != self.reference_shape:
            return result("shape_not_restored", "restore the reference shape before constructive entry")
        if state.sticker_permutation not in self.suffix.ambient_method._symbolic_chain.group:
            return result("outside_reference_group", "state is outside the certified reference group")
        initially_solved = self._solved_indices(current)
        committed = set()
        anchor = next((feature for feature in self.anchors
                       if set(_feature_indices(self.inventory, feature)).issubset(initially_solved)), None)
        if anchor is not None:
            committed.update(_feature_indices(self.inventory, anchor))
        for _ in range(settings["max_stages"] + 1):
            recognition = self.suffix.recognize(current)
            if recognition.status in ("ready", "solved"):
                application = self.suffix.apply(current)
                current = application.state
                return result(application.status, application.reason, application)
            if len(steps) >= settings["max_stages"]:
                metadata["entry_stop_reasons"].append("stage_limit")
                return result("entry_limit", "constructive entry reached its stage limit")
            protected = tuple(BlockFeature("solve_block", self.inventory.blocks[index].cells)
                              for index in sorted(committed))
            candidates = self._candidates(current, committed, anchor)
            chosen = None
            for feature in candidates:
                remaining_nodes = settings["max_entry_nodes"] - metadata["entry_nodes_expanded"]
                if remaining_nodes <= 0:
                    metadata["entry_stop_reasons"].append("total_node_limit")
                    break
                correction = self.controller.plan_step(current, feature, protected_features=protected,
                    max_nodes=min(settings["controller_options"]["max_nodes"], remaining_nodes))
                metadata["entry_candidates_tried"] += 1
                metadata["entry_nodes_expanded"] += correction.metrics["expanded_nodes"]
                if correction.status in ("ready", "already_satisfied"):
                    chosen = correction
                    break
                metadata["entry_stop_reasons"].append(correction.status)
            if chosen is None:
                return result("entry_limit", "no proposed collection has a correction within the entry bounds")
            current = chosen.after
            next_committed = committed | set(_feature_indices(self.inventory, chosen.feature))
            if not next_committed.issubset(self._solved_indices(current)) or next_committed == committed:
                raise ValueError("constructive entry failed cumulative component progress")
            steps.append(chosen)
            if anchor is None and chosen.feature in self.anchors:
                anchor = chosen.feature
            metadata["adaptive_choices"].append(chosen.feature.to_dict())
            committed = next_committed
        raise AssertionError("unreachable entry stage loop")

    def write_guide(self, path=None):
        from .palette_render import (execution_vocabulary, execution_vocabulary_lines,
                                     expanded_recipe_path, palette_method_guide,
                                     recipe_structure)

        # The combined palette is a declaration registry. Expand each
        # execution palette's derived operations in its own registry first;
        # merged base declarations then supply one consistent set of names.
        entry_calls = expanded_recipe_path(self.entry_palette,
                        (action.id for action in self.entry_palette.recipes))
        suffix_calls = expanded_recipe_path(self.suffix.palette,
                         (identifier for _, _, recipe in self.suffix.case_recipes
                          for identifier in recipe))
        declarations, aliases = execution_vocabulary(self.palette, (entry_calls, suffix_calls))
        names = [self.inventory.blocks[index].compact_name for index in self.target_indices]
        lines = ["# Constructive workspace entry", "",
                 "Start with the reference bandage shape restored. The entry controller "
                 "operates on legal loops returning to that shape.", "",
                 "Build the following region before following the certified continuation:", "",
                 ", ".join(names) or "The continuation already accepts the whole reference group.", "",
                 "Choose a joined nearby collection or expand a completed collection. "
                 "Track the target pieces together with every previously completed piece. "
                 "Find a short sequence whose endpoint completes the target and restores those earlier pieces. "
                 "Temporary displacement within that sequence is allowed. Repeat until the region is complete.", "",
                 "The current controller searches for these sequences within declared depth and work bounds. "
                 "It provides verified corrections for successful inputs; a complete human entry policy "
                 "has not yet been certified.", ""]
        lines.extend(execution_vocabulary_lines(declarations))
        lines.extend(["## Available entry operations", "",
                      "Entry and continuation use the same letters above. Each row is one complete "
                      "permitted operation; temporary displacement is allowed inside it.", "",
                      "| Structure | Turn sequence | Block action |", "| --- | --- | --- |"])
        for action in self.controller.actions:
            structure = recipe_structure(self.entry_palette, (action.id,), aliases)
            lines.append(f"| `{structure}` | `{action.turn_sequence}` | `{action.block_action.notation}` |")
        lines.extend(["", f"Global taught definitions: **{len(self.taught_definition_ids)} / "
                      f"{self.settings['max_taught_bodies']}**, shared by entry and continuation.", "",
                      "## Certified continuation", "", palette_method_guide(self.suffix,
                        declarations=declarations, aliases=aliases, include_vocabulary=False)])
        guide = "\n".join(lines)
        if path is not None:
            Path(path).write_text(guide, encoding="utf-8")
        return guide

    def to_dict(self):
        from .human_method_io import _fingerprint
        record = {"format": "bce-v2-workspace-method", "version": 1,
                  "coverage_scope": self.coverage_scope,
                  "human_method_complete": False,
                  "settings": self.settings, "suffix": self.suffix.to_dict(),
                  "entry_palette": _palette_record(self.entry_palette),
                  "taught_definition_ids": list(self.taught_definition_ids)}
        record["fingerprint"] = _fingerprint(record)
        return record

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path):
        self.to_json(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, record):
        from .human_method_io import _fields, _fingerprint
        _fields(record, {"format", "version", "coverage_scope", "human_method_complete", "settings",
                         "suffix", "entry_palette", "taught_definition_ids", "fingerprint"},
                "workspace method")
        if (record["format"] != "bce-v2-workspace-method" or type(record["version"]) is not int or
                record["version"] != 1 or record["fingerprint"] != _fingerprint(record)):
            raise ValueError("unsupported or corrupted workspace-method record")
        suffix = CoarseMethod.from_dict(record["suffix"])
        result = compile_workspace_method(suffix,
            entry_palette=_load_palette(record["entry_palette"], suffix.ambient_method), **record["settings"])
        if result.to_dict() != record:
            raise ValueError("saved workspace-method claims disagree with validated settings and vocabulary")
        return result


def compile_workspace_method(suffix, *, entry_palette=None, max_taught_bodies=7,
                             max_short_setup_htm=4, max_candidates=6, max_components=2,
                             max_stages=24, max_proposals=128, max_entry_nodes=100_000,
                             controller_options=None):
    """Attach bounded adaptive entry to a preservation-derived continuation.

    Available entry operations and used suffix definitions share one hard
    vocabulary budget. No algorithm learned after chain selection can bypass
    that budget. Full-pose workspace domains are currently supported.
    """
    from .workspace_entry import ConstructiveEntryController
    if not isinstance(suffix, CoarseMethod):
        raise TypeError("suffix must be a certified CoarseMethod")
    for name, value, minimum in (("max_taught_bodies", max_taught_bodies, 0),
            ("max_short_setup_htm", max_short_setup_htm, 0), ("max_candidates", max_candidates, 1),
            ("max_components", max_components, 1), ("max_stages", max_stages, 0),
            ("max_proposals", max_proposals, 0), ("max_entry_nodes", max_entry_nodes, 0)):
        _limit(value, name, minimum)
    options = dict(max_pattern_observations=20_000, max_pattern_count=16,
                   max_pattern_components=3, max_depth=12, max_nodes=20_000)
    if controller_options is not None:
        if not isinstance(controller_options, dict):
            raise TypeError("controller_options must be a dictionary or None")
        options.update(controller_options)
    controller = ConstructiveEntryController(suffix.ambient_method, palette=entry_palette, **options)
    settings = dict(max_taught_bodies=max_taught_bodies, max_short_setup_htm=max_short_setup_htm,
        max_candidates=max_candidates, max_components=max_components, max_stages=max_stages,
        max_proposals=max_proposals, max_entry_nodes=max_entry_nodes, controller_options=options)
    result = WorkspaceMethod(suffix, controller.palette, json.dumps(settings, sort_keys=True))
    result.__dict__["controller"] = controller
    return result.validate()
