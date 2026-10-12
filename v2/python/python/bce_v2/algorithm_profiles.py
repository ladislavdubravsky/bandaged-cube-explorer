"""Generic endpoint preservation evidence and bounded coarse goal proposals.

An algorithm palette suggests useful workspaces and attributes; it does not
certify that its actions cover their ambient orbits. Profiles use only actual
reference components, footprint classes and endpoint block actions. A current
group certificate is required before an anonymous orientation region may be
offered to a stage planner.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
from types import MappingProxyType

from .algorithm_palette import AlgorithmPalette
from .block_actions import BlockInventory, _coordinates
from .computation import checkpoint
from .human_chains import BlockFeature, _observation, _resolve_feature
from .symbolic_groups import PermutationGroupCertificate


def _limit(value, label):
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _group_actions(inventory, group):
    if not isinstance(group, PermutationGroupCertificate) or group.degree != 48:
        raise TypeError("group must be a 48-point PermutationGroupCertificate")
    return tuple(inventory.action(generator.permutation) for generator in group.strong_generators)


def _cells(inventory, indices):
    return tuple(sorted(cell for index in indices for cell in inventory.blocks[index].cells))


def _identifier(prefix, feature):
    return prefix + ":" + json.dumps([feature.kind, feature.cells], separators=(",", ":"))


def _slot_orbits(indices, actions):
    """Exact placement orbits of a permutation-generating action collection."""
    unseen, result = set(indices), []
    while unseen:
        start = min(unseen)
        found, queue = {start}, deque([start])
        while queue:
            slot = queue.popleft()
            for action in actions:
                destination = action.destinations[slot]
                if destination not in found:
                    found.add(destination)
                    queue.append(destination)
        unseen.difference_update(found)
        result.append(tuple(sorted(found)))
    return tuple(result)


def _adjacent(inventory, left, right):
    # Contacts between actual constituent cells, never bounding-box completion.
    return any(sum(abs(a - b) for a, b in zip(_coordinates(first), _coordinates(second))) == 1
               for first in inventory.blocks[left].cells for second in inventory.blocks[right].cells)


def _connected_components(inventory, indices):
    unseen, result = set(indices), []
    while unseen:
        found, queue = {min(unseen)}, deque([min(unseen)])
        unseen.difference_update(found)
        while queue:
            source = queue.popleft()
            neighbors = tuple(index for index in sorted(unseen) if _adjacent(inventory, source, index))
            unseen.difference_update(neighbors)
            found.update(neighbors)
            queue.extend(neighbors)
        result.append(tuple(sorted(found)))
    return tuple(result)


def _compatible_classes(inventory, indices):
    classes = defaultdict(list)
    for index in indices:
        block = inventory.blocks[index]
        classes[block.template_cells, block.orientation_order].append(index)
    return tuple(tuple(values) for _, values in sorted(classes.items()))


def _preserves(action, inventory, feature, indices):
    if feature.kind == "orient_slots" and {action.destinations[index] for index in indices} != set(indices):
        return False
    return _observation(action, indices, feature.kind) == _observation(inventory.identity(), indices, feature.kind)


@dataclass(frozen=True)
class AlgorithmPreservationProfile:
    """Exact endpoint facts for one complete setup/body/undo recipe.

    ``zero_phase_indices`` refers to source-to-destination frame increments;
    it alone is not a claim about an invariant orientation region. The cycles
    are disjoint minimal invariant slot sets for this recipe's placement.
    """

    recipe_id: str
    body_ids: tuple[str, ...]
    destinations: tuple[int, ...]
    phases: tuple[int, ...]
    fixed_pose_indices: tuple[int, ...]
    fixed_placement_indices: tuple[int, ...]
    zero_phase_indices: tuple[int, ...]
    invariant_slot_sets: tuple[tuple[int, ...], ...]

    def to_dict(self):
        return {"recipe_id": self.recipe_id, "body_ids": list(self.body_ids),
                "destinations": list(self.destinations), "phases": list(self.phases),
                "fixed_pose_indices": list(self.fixed_pose_indices),
                "fixed_placement_indices": list(self.fixed_placement_indices),
                "zero_phase_indices": list(self.zero_phase_indices),
                "invariant_slot_sets": [list(values) for values in self.invariant_slot_sets]}


@dataclass(frozen=True)
class PaletteWorkspaceCandidate:
    """An anchored assembly preserved by a shared algorithm family."""

    id: str
    feature: BlockFeature
    block_indices: tuple[int, ...]
    preserving_recipe_ids: tuple[str, ...]
    body_ids: tuple[str, ...]
    adjacency_components: tuple[tuple[int, ...], ...]
    proposal_sources: tuple[str, ...]

    def to_dict(self):
        return {"id": self.id, "feature": self.feature.to_dict(),
                "block_indices": list(self.block_indices),
                "preserving_recipe_ids": list(self.preserving_recipe_ids),
                "body_ids": list(self.body_ids),
                "adjacency_components": [list(values) for values in self.adjacency_components],
                "proposal_sources": list(self.proposal_sources), "coverage_claim": False}


@dataclass(frozen=True)
class PaletteGoalCandidate:
    """A coarse goal proposal, with preservation evidence and no case policy."""

    id: str
    feature: BlockFeature
    block_indices: tuple[int, ...]
    preserving_recipe_ids: tuple[str, ...]
    repairing_recipe_ids: tuple[str, ...]
    proposal_sources: tuple[str, ...]

    def to_dict(self):
        return {"id": self.id, "feature": self.feature.to_dict(),
                "block_indices": list(self.block_indices),
                "preserving_recipe_ids": list(self.preserving_recipe_ids),
                "repairing_recipe_ids": list(self.repairing_recipe_ids),
                "proposal_sources": list(self.proposal_sources), "coverage_claim": False}


@dataclass(frozen=True)
class PaletteProfileDiscovery:
    """Immutable evidence and bounded proposals from a witnessed palette."""

    reference_shape: object = field(repr=False)
    recipe_ids: tuple[str, ...]
    profiles: tuple[AlgorithmPreservationProfile, ...]
    workspaces: tuple[PaletteWorkspaceCandidate, ...]
    goals: tuple[PaletteGoalCandidate, ...]
    globally_fixed_pose_indices: tuple[int, ...]
    active_block_indices: tuple[int, ...]
    diagnostics: object

    @property
    def common_workspace(self):
        """The maximal active region fixed by every recipe, when nonempty."""
        return next((workspace for workspace in self.workspaces
                     if "all_palette_recipes" in workspace.proposal_sources), None)

    def to_dict(self):
        return {"format": "bce-v2-palette-preservation-profiles", "version": 1,
                "recipe_ids": list(self.recipe_ids),
                "profiles": [profile.to_dict() for profile in self.profiles],
                "workspaces": [workspace.to_dict() for workspace in self.workspaces],
                "goals": [goal.to_dict() for goal in self.goals],
                "globally_fixed_pose_indices": list(self.globally_fixed_pose_indices),
                "active_block_indices": list(self.active_block_indices),
                "diagnostics": dict(self.diagnostics), "coverage_claim": False}


def _catalog(inventory, palette, group=None):
    if not isinstance(inventory, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    palette.validate(inventory=inventory, group=group)
    return tuple((recipe, inventory.action(recipe.permutation))
                 for recipe in sorted(palette.recipes, key=lambda recipe: recipe.id))


def _candidate(inventory, feature, catalog, sources):
    indices = _resolve_feature(inventory, feature)
    preserving = tuple(recipe.id for recipe, action in catalog if _preserves(action, inventory, feature, indices))
    repairing = tuple(recipe.id for recipe, action in catalog
                      if recipe.id not in preserving and
                      (feature.kind != "orient_slots" or
                       {action.destinations[index] for index in indices} == set(indices)))
    return PaletteGoalCandidate(_identifier("goal", feature), feature, indices,
                                preserving, repairing, tuple(sorted(sources)))


def _goal_rank(goal):
    sources = goal.proposal_sources
    priority = (0 if "common_workspace_residual" in sources else
                1 if "current_group_slot_orbit" in sources else
                2 if "palette_slot_orbit" in sources else
                3 if "preservation_cluster" in sources else
                4 if "adjacent_components" in sources else 5)
    kind = {"orient_slots": 0, "place_blocks": 1, "occupy_slots": 2, "solve_blocks": 3}[goal.feature.kind]
    return (not bool(goal.repairing_recipe_ids), priority, len(goal.block_indices) == 1,
            kind, -len(goal.preserving_recipe_ids), len(goal.block_indices), goal.id)


def _add_region(proposals, inventory, indices, source, *, kinds=("orient_slots", "place_blocks", "occupy_slots")):
    if not indices:
        return
    for kind in kinds:
        if kind == "orient_slots":
            if (any(inventory.blocks[index].orientation_order == 1 for index in indices) or
                    len(_compatible_classes(inventory, indices)) != 1):
                continue
        proposals[BlockFeature(kind, _cells(inventory, indices))].add(source)


def _geometric_proposals(proposals, inventory, indices, maximum):
    count = 0
    for offset, left in enumerate(indices):
        if count >= maximum:
            break
        for right in indices[offset + 1:]:
            if count >= maximum:
                break
            if _adjacent(inventory, left, right):
                _add_region(proposals, inventory, (left, right), "adjacent_components",
                            kinds=("solve_blocks", "place_blocks"))
                count += 1
    for connected in _connected_components(inventory, indices):
        if len(connected) > 2:
            _add_region(proposals, inventory, connected, "connected_components",
                        kinds=("solve_blocks", "place_blocks"))


def discover_palette_profiles(inventory, palette, *, ambient_group=None,
                              max_candidates=64, max_clusters=64):
    """Find shared endpoint workspaces and attribute goals without cube cases.

    A supplied ambient certificate identifies globally immovable components,
    so their permanently fixed poses do not inflate proposed assemblies.
    Without it, only geometry-certified immobile components are excluded.
    Support signatures, individual recipes and bounded pairwise intersections
    supply families; arbitrary exponential subsets are never searched.
    """
    _limit(max_candidates, "max_candidates")
    _limit(max_clusters, "max_clusters")
    if not isinstance(inventory, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    ambient_actions = None if ambient_group is None else _group_actions(inventory, ambient_group)
    catalog = _catalog(inventory, palette, ambient_group)
    indices = tuple(range(len(inventory.blocks)))
    globally_fixed = tuple(index for index in indices
                           if (all(action.destinations[index] == index and action.phases[index] == 0
                                   for action in ambient_actions) if ambient_actions is not None else
                               not inventory.blocks[index].movable))
    active = tuple(index for index in indices if index not in globally_fixed)
    profiles = tuple(AlgorithmPreservationProfile(
        recipe.id, palette.recipe_body_ids[recipe.id], action.destinations, action.phases,
        tuple(index for index in indices if action.destinations[index] == index and action.phases[index] == 0),
        tuple(index for index in indices if action.destinations[index] == index),
        tuple(index for index in indices if action.phases[index] == 0), _slot_orbits(indices, (action,)))
        for recipe, action in catalog)
    all_recipes = tuple(recipe.id for recipe, _ in catalog)
    support_sets = {all_recipes} if catalog else set()
    support_sets.update((recipe.id,) for recipe, _ in catalog)
    for attribute in ("fixed_pose_indices", "fixed_placement_indices", "zero_phase_indices"):
        support_sets.update(tuple(profile.recipe_id for profile in profiles if index in getattr(profile, attribute))
                            for index in active)
    support_sets.discard(())
    initial_supports = tuple(sorted(support_sets, key=lambda values: (-len(values), values)))
    # At most a quadratic, explicitly bounded family refinement.
    for offset, left in enumerate(initial_supports):
        for right in initial_supports[offset + 1:]:
            if len(support_sets) >= max_clusters:
                break
            intersection = tuple(sorted(set(left).intersection(right)))
            if intersection:
                support_sets.add(intersection)
        if len(support_sets) >= max_clusters:
            break
    supports = tuple(sorted(support_sets, key=lambda values: (-len(values), values)))[:max_clusters]
    workspace_sources, proposals = defaultdict(set), defaultdict(set)
    for support in supports:
        checkpoint("palette_preservation_clusters")
        actions = tuple(action for recipe, action in catalog if recipe.id in support)
        fixed = tuple(index for index in active
                      if all(action.destinations[index] == index and action.phases[index] == 0 for action in actions))
        source = "all_palette_recipes" if support == all_recipes else "shared_fixed_poses"
        if fixed:
            workspace_sources[fixed].add(source)
        for compatible in _compatible_classes(inventory, active):
            placed = tuple(index for index in compatible if all(action.destinations[index] == index for action in actions))
            _add_region(proposals, inventory, placed, "preservation_cluster")
            for orbit in _slot_orbits(compatible, actions):
                _add_region(proposals, inventory, orbit, "palette_slot_orbit")
    workspaces = []
    for fixed, sources in workspace_sources.items():
        feature = BlockFeature("solve_blocks", _cells(inventory, fixed))
        preserving = tuple(recipe.id for recipe, action in catalog if _preserves(action, inventory, feature, fixed))
        bodies = tuple(sorted({body for identifier in preserving for body in palette.recipe_body_ids[identifier]}))
        workspaces.append(PaletteWorkspaceCandidate(
            _identifier("workspace", feature), feature, fixed, preserving, bodies,
            _connected_components(inventory, fixed), tuple(sorted(sources))))
        remaining = tuple(index for index in active if index not in fixed)
        source = "common_workspace_residual" if "all_palette_recipes" in sources else "workspace_residual"
        for compatible in _compatible_classes(inventory, remaining):
            _add_region(proposals, inventory, compatible, source)
    _geometric_proposals(proposals, inventory, active, max_candidates)
    goals = tuple(sorted((_candidate(inventory, feature, catalog, sources)
                          for feature, sources in proposals.items()), key=_goal_rank))[:max_candidates]
    workspaces.sort(key=lambda workspace: ("all_palette_recipes" not in workspace.proposal_sources,
                                           -len(workspace.preserving_recipe_ids), -len(workspace.block_indices), workspace.id))
    diagnostics = MappingProxyType({"ambient_group_supplied": ambient_group is not None,
                                    "recipe_count": len(catalog), "cluster_count": len(supports),
                                    "cluster_limit_reached": bool(support_sets) and len(support_sets) >= max_clusters,
                                    "candidate_count_before_limit": len(proposals),
                                    "candidates_bounded": len(proposals) > max_candidates,
                                    "coverage_claim": False,
                                    "scope": "endpoint preservation and proposals; ambient orbit coverage requires policy certification"})
    return PaletteProfileDiscovery(inventory.root_shape, all_recipes, profiles, tuple(workspaces), goals,
                                   globally_fixed, active, diagnostics)


def propose_palette_goals(inventory, current_group, palette, *, discovery=None, max_candidates=64):
    """Propose current-subgroup coarse goals, checking full-group invariance.

    Palette support ranks the proposals; the entire certified subgroup defines
    orientation slot closure and nontriviality. No orbit is inferred from the
    palette, and no bounded proposal list is a complete method search claim.
    """
    _limit(max_candidates, "max_candidates")
    if not isinstance(inventory, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    actions = _group_actions(inventory, current_group)
    full_catalog = _catalog(inventory, palette)
    catalog = tuple((recipe, action) for recipe, action in full_catalog if recipe.permutation in current_group)
    if not catalog or max_candidates == 0:
        return ()
    if discovery is None:
        discovery = discover_palette_profiles(inventory, palette)
    if (not isinstance(discovery, PaletteProfileDiscovery) or discovery.reference_shape != inventory.root_shape or
            tuple((profile.recipe_id, profile.destinations, profile.phases) for profile in discovery.profiles) !=
            tuple((recipe.id, action.destinations, action.phases) for recipe, action in full_catalog)):
        raise ValueError("discovery refers to a different inventory or palette")
    proposals = defaultdict(set)
    for goal in discovery.goals:
        proposals[goal.feature].update(goal.proposal_sources)
    active = tuple(index for index in range(len(inventory.blocks))
                   if any(action.destinations[index] != index or action.phases[index] != 0 for action in actions))
    by_class = defaultdict(list)
    for orbit in _slot_orbits(active, actions):
        _add_region(proposals, inventory, orbit, "current_group_slot_orbit")
        block = inventory.blocks[orbit[0]]
        by_class[block.template_cells, block.orientation_order].extend(orbit)
    for values in by_class.values():
        _add_region(proposals, inventory, tuple(sorted(values)), "current_group_compatible_class")
    _geometric_proposals(proposals, inventory, active, max_candidates)
    for index in active:
        _add_region(proposals, inventory, (index,), "singleton_fallback", kinds=("solve_blocks", "place_blocks"))
    result = []
    for feature, sources in proposals.items():
        indices = _resolve_feature(inventory, feature)
        if feature.kind == "orient_slots" and any(
                {action.destinations[index] for index in indices} != set(indices) for action in actions):
            continue
        if all(_preserves(action, inventory, feature, indices) for action in actions):
            continue
        result.append(_candidate(inventory, feature, catalog, sources))
    return tuple(sorted(result, key=_goal_rank))[:max_candidates]
