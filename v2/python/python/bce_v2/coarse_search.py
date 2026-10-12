"""Bounded palette-led workspace and multi-stage method discovery.

Preservation suggests start domains. Exact ambient stabilizers define their
coverage, and complete palette policies define edges of the method frontier.
The frontier carries the union of learned definitions across every stage.
Neither palette generation nor a search cutoff establishes coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
import json
from math import log2
from pathlib import Path
from time import perf_counter

from .algorithm_palette import AlgorithmPalette
from .algorithm_profiles import discover_palette_profiles, propose_palette_goals
from .coarse_methods import _compile_coarse_plan, _domain_ladder
from .computation import checkpoint, report_progress
from .gap_backend import analyze_generators
from .human_chains import BlockFeature, _feature_indices, _then
from .palette_policies import recipe_taught_ids, stage_policy_frontier
from .preparation import prepare_analysis
from .symbolic_chains import plan_symbolic_stages


_IDENTITY = tuple(range(48))


def _limit(value, name, minimum=0):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True)
class CoarseMethodCandidate:
    id: str
    domain_features: tuple[BlockFeature, ...]
    features: tuple[BlockFeature, ...]
    taught_definition_ids: frozenset[str]
    mean_recipe_htm: Fraction
    worst_recipe_htm: int
    case_counts: tuple[int, ...]
    domain_order: int
    subgroup_orders: tuple[int, ...]
    _plan: object = field(repr=False, compare=False)
    _policies: tuple = field(repr=False, compare=False)

    def to_dict(self):
        return {"id": self.id,
                "domain_features": [feature.to_dict() for feature in self.domain_features],
                "features": [feature.to_dict() for feature in self.features],
                "taught_definition_ids": sorted(self.taught_definition_ids),
                "taught_definition_count": len(self.taught_definition_ids),
                "mean_recipe_htm": float(self.mean_recipe_htm),
                "mean_recipe_htm_numerator": self.mean_recipe_htm.numerator,
                "mean_recipe_htm_denominator": self.mean_recipe_htm.denominator,
                "worst_recipe_htm": self.worst_recipe_htm,
                "case_counts": list(self.case_counts), "domain_order": str(self.domain_order),
                "subgroup_orders": [str(order) for order in self.subgroup_orders],
                "coverage": "complete_palette_policies_over_exact_start_domain",
                "cost_scope": "uniform_domain_additive_palette_recipes_before_cancellation"}


@dataclass(frozen=True)
class CoarseMethodSearch:
    method: object | None
    candidates: tuple[CoarseMethodCandidate, ...]
    selected_id: str | None
    _metadata_json: str = field(repr=False)

    @property
    def status(self):
        return "completed" if self.method is not None else "no_method_found"

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    def select_candidate(self, candidate_id):
        """Compile a retained alternative without rerunning method discovery.

        The chosen recipe tables and the original global teaching budget are
        preserved. The original search result remains unchanged.
        """
        candidate = next((candidate for candidate in self.candidates
                          if candidate.id == candidate_id), None)
        if candidate is None:
            raise ValueError("unknown coarse-method candidate ID: " + repr(candidate_id))
        if self.method is None:
            raise ValueError("candidate selection requires the original palette context")
        metadata = self.metadata
        settings = metadata["settings"]
        method = _compile_candidate(candidate, self.method.palette,
                                    max_taught_bodies=settings["max_taught_bodies"],
                                    max_short_setup_htm=settings["max_short_setup_htm"])
        unrestricted = method.group_order == method.ambient_group_order
        metadata.update(all_reference_group_states=unrestricted,
                        whole_scramble_method_claim=bool(unrestricted and
                                                        metadata["reference_shape_count"] == 1),
                        entry_required_at_reference_shape=not unrestricted)
        return replace(self, method=method, selected_id=candidate.id,
                       _metadata_json=json.dumps(metadata, sort_keys=True))

    def to_dict(self, *, include_method=True):
        record = {"format": "bce-v2-coarse-method-search", "version": 1,
                  "status": self.status, "selected_id": self.selected_id,
                  "candidates": [candidate.to_dict() for candidate in self.candidates],
                  "metadata": self.metadata}
        if include_method:
            record["method"] = None if self.method is None else self.method.to_dict()
        return record

    def to_json(self, path=None, *, include_method=True):
        text = json.dumps(self.to_dict(include_method=include_method), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text


@dataclass(frozen=True)
class _Node:
    domain: tuple[BlockFeature, ...]
    features: tuple[BlockFeature, ...]
    policies: tuple
    taught: frozenset[str]
    plan: object
    group: object
    domain_order: int
    orders: tuple[int, ...]
    mean: Fraction = Fraction()
    worst: int = 0
    counts: tuple[int, ...] = ()
    continuation_basis_htm: int | None = None


def _compile_candidate(candidate, palette, *, max_taught_bodies, max_short_setup_htm):
    """Retain one complete policy and check its actual global vocabulary."""
    _limit(max_taught_bodies, "max_taught_bodies")
    method = _compile_coarse_plan(candidate._plan, palette, candidate.domain_features,
                                 stage_recipes=tuple(policy.case_recipes
                                                     for policy in candidate._policies))
    taught = recipe_taught_ids(palette, max_short_setup_htm)
    actual = frozenset(identifier for _, _, path in method.case_recipes
                       for recipe in path for identifier in taught[recipe])
    if actual != candidate.taught_definition_ids or len(actual) > max_taught_bodies:
        raise ValueError("compiled method changed the global taught-definition commitment")
    return method


def _dominates(first, second):
    return (first.taught.issubset(second.taught) and first.mean <= second.mean
            and first.worst <= second.worst
            and max(first.counts, default=0) <= max(second.counts, default=0)
            and sum(first.counts) <= sum(second.counts)
            # The shorter history has more stages left in the bounded search.
            and len(first.features) <= len(second.features))


def _rank(node, preference, *, partial=False):
    mean = node.mean
    if partial:
        resolved = log2(node.domain_order / node.group.order) if node.group.order else 0
        mean = mean / max(1, resolved)
    if preference == "recognition":
        # A tiny observation can leave a continuation requiring expensive
        # restoring compounds. A bounded endpoint basis estimates that
        # procedural burden before greedy selection commits to the goal.
        future = ((node.mean + node.continuation_basis_htm,)
                  if partial and node.continuation_basis_htm is not None else ())
        return (*future, max(node.counts, default=0), sum(node.counts), mean,
                len(node.taught), node.worst, len(node.features),
                tuple(json.dumps(feature.to_dict(), sort_keys=True) for feature in node.features))
    return (mean, node.worst, max(node.counts, default=0), sum(node.counts),
            len(node.taught), len(node.features),
            tuple(json.dumps(feature.to_dict(), sort_keys=True) for feature in node.features))


def _continuation_basis_htm(group, palette, *, maximum_order=512):
    """Small-group action-family complexity, used only to rank proposals.

    A shortest-first independent endpoint basis exposes commitments that
    force long restoring repetitions or mixed-body operations. Closure is
    bounded by an already certified group order; it proves no policy and
    grants no execution permission. Larger groups retain the coarse score.
    """
    if group.order > maximum_order:
        return None
    basis, closure, total = [], {_IDENTITY}, 0
    for recipe in sorted(palette.recipes, key=lambda value: (value.htm_length, value.id)):
        if recipe.permutation in closure or recipe.permutation not in group:
            continue
        basis.append(recipe.permutation)
        total += recipe.htm_length
        queue = list(closure)
        for element in queue:
            for generator in basis:
                image = _then(element, generator)
                if image not in closure:
                    closure.add(image)
                    queue.append(image)
        if len(closure) > group.order:
            raise ValueError("continuation basis exceeds its certified group")
        if len(closure) == group.order:
            return total
    return total


def _alignment_group(palette, group, maximum):
    """Bounded closure of the explicitly supplied standalone adjustments."""
    generators = tuple(adjustment.algorithm.permutation for adjustment in palette.adjustments
                       if adjustment.algorithm.permutation in group)
    found, queue = {_IDENTITY}, [_IDENTITY]
    for element in queue:
        for generator in generators:
            image = _then(element, generator)
            if image not in found:
                if len(found) >= maximum:
                    return ()
                found.add(image)
                queue.append(image)
    return tuple(sorted(found)) if len(found) > 1 else ()


def _features(inventory, group, palette, profiles, maximum, alignment_limit):
    proposals = propose_palette_goals(inventory, group, palette, discovery=profiles,
                                      max_candidates=maximum)
    result = [proposal.feature for proposal in proposals]
    # Small action families describe a remaining task, rather than a new
    # taught body. Build their full finite endpoint groups before testing
    # preservation; the full-pose orbit retains relative orientation phases.
    residuals = []
    for recipe in palette.recipes:
        if alignment_limit < 2 or recipe.permutation not in group:
            continue
        element, closure = _IDENTITY, []
        for _ in range(alignment_limit):
            closure.append(element)
            element = _then(element, recipe.permutation)
            if element == _IDENTITY:
                break
        if element != _IDENTITY or len(closure) < 2:
            continue
        action = inventory.action(recipe.permutation)
        support = tuple(index for index, destination in enumerate(action.destinations)
                        if destination != index or action.phases[index])
        # Compatible footprint classes keep the recognition region small;
        # a family's complete support remains useful for mixed components.
        regions = {tuple(sorted(cell for index in support for cell in inventory.blocks[index].cells))}
        classes = {}
        for index in support:
            block = inventory.blocks[index]
            classes.setdefault((block.template_cells, block.orientation_order), []).append(index)
        for indices in classes.values():
            if {action.destinations[index] for index in indices} == set(indices):
                regions.add(tuple(sorted(cell for index in indices for cell in inventory.blocks[index].cells)))
        for cells in sorted(regions):
            if cells:
                feature = BlockFeature("solve_blocks_up_to_actions", cells,
                                       alignment_permutations=tuple(closure))
                if feature not in residuals:
                    residuals.append(feature)
    # Keep relative-pose variants beside the same geometric regions. In a
    # small bound, prefer a proper residual family that fixes placements:
    # it describes phase preparation with an observable finishing action.
    def uniform_phase_family(feature):
        indices = _feature_indices(inventory, feature)
        return (len({(inventory.blocks[index].template_cells, inventory.blocks[index].orientation_order)
                     for index in indices}) == 1 and
                all(len({inventory.action(p).phases[index] for index in indices}) == 1
                    for p in feature.alignment_permutations))
    residuals.sort(key=lambda feature: (
        not uniform_phase_family(feature),
        not all(inventory.action(p).destinations[index] == index
                for p in feature.alignment_permutations
                for index in _feature_indices(inventory, feature)),
        -len(_feature_indices(inventory, feature)), len(feature.alignment_permutations),
        feature.cells, feature.alignment_permutations))
    if residuals:
        unique = {}
        from .human_chains import _resolve_feature
        for feature in residuals:
            unique.setdefault((feature.cells, _resolve_feature(inventory, feature)), feature)
        residuals = list(unique.values())
        primary = result[:max(1, maximum//2)]
        result = [*primary, *residuals, *result[len(primary):]]
    alignments = _alignment_group(palette, group, alignment_limit) if alignment_limit > 1 else ()
    if alignments:
        regions = [feature.cells for feature in result if feature.kind == "place_blocks"]
        active = tuple(cell for index, block in enumerate(inventory.blocks)
                       if any(inventory.action(generator.permutation).destinations[index] != index
                              or inventory.action(generator.permutation).phases[index]
                              for generator in group.strong_generators)
                       for cell in block.cells)
        if active:
            regions.append(active)
        aligned = []
        for cells in dict.fromkeys(regions):
            try:
                feature = BlockFeature("place_blocks_up_to_alignment", cells,
                                       alignment_permutations=alignments)
                _feature_indices(inventory, feature)
                # Resolve also verifies that each permitted alignment retains
                # this component region, independently of the current group.
                from .human_chains import _resolve_feature
                _resolve_feature(inventory, feature)
            except ValueError:
                continue
            aligned.append(feature)
        # Keep each grouped placement beside its aligned variant so a tight
        # proposal bound does not discard all alignment-aware continuations.
        main = [feature for feature in result if feature.kind in ("orient_slots", "place_blocks")]
        other = [feature for feature in result if feature not in main]
        aligned_by_cells = {feature.cells: feature for feature in aligned}
        paired = []
        for feature in main:
            paired.append(feature)
            if feature.kind == "place_blocks" and feature.cells in aligned_by_cells:
                paired.append(aligned_by_cells[feature.cells])
        result = [*paired, *aligned, *other]
    return tuple(dict.fromkeys(result))[:maximum]


def discover_coarse_method(initial, *, palette, domain_features=None,
                           max_taught_bodies=7, beam_width=12, max_expansions=64,
                           max_stages=8, max_candidates=24, max_observations=128,
                           max_policy_labels=128, max_policies=8, max_workspaces=1,
                           max_alignment_order=16, max_short_setup_htm=4,
                           preference="recognition", gap_executable="gap", timeout=None):
    """Discover a protected workspace and a complete multi-stage suffix.

    Omitting ``domain_features`` asks palette preservation to propose the
    starting workspace. It is an entry contract, not evidence of a cheap full
    scramble solution. The output certifies every reachable state satisfying
    that contract. Finite beam/proposal/subset bounds limit discovery quality;
    they never weaken the returned method's complete physical coverage.
    """
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    if palette.max_derived_recipes == 0:
        palette = palette.with_derived_actions()
    if preference not in ("recognition", "execution"):
        raise ValueError("preference must be recognition or execution")
    for name, value, minimum in (("max_taught_bodies", max_taught_bodies, 0),
            ("beam_width", beam_width, 1), ("max_expansions", max_expansions, 0),
            ("max_stages", max_stages, 0), ("max_candidates", max_candidates, 0),
            ("max_observations", max_observations, 0), ("max_policy_labels", max_policy_labels, 0),
            ("max_policies", max_policies, 0), ("max_workspaces", max_workspaces, 0),
            ("max_alignment_order", max_alignment_order, 0),
            ("max_short_setup_htm", max_short_setup_htm, 0)):
        _limit(value, name, minimum)
    started = perf_counter()
    analysis = prepare_analysis(initial, gap_executable=gap_executable, timeout=timeout)
    inventory = analysis.block_inventory
    finish = tuple(BlockFeature("solve_block", block.cells) for block in inventory.blocks)
    ambient = plan_symbolic_stages(analysis, strategy="manual", features=finish,
                                   gap_executable=gap_executable, timeout=timeout)
    palette.validate(inventory=inventory, generators=analysis.loops.generators, group=ambient.group)
    profiles = discover_palette_profiles(inventory, palette, ambient_group=ambient.group,
                                        max_candidates=max_candidates, max_clusters=max_candidates)
    if domain_features is not None:
        declared = tuple(domain_features)
        if any(not isinstance(feature, BlockFeature) for feature in declared):
            raise TypeError("domain_features must contain BlockFeature instances")
        domains = (declared,)
    else:
        # A shared commitment supports a workspace suffix. In its absence,
        # begin at the full reference group instead of inventing an entry
        # assumption from whichever individual preserver ranks first.
        domains = (((),) if profiles.common_workspace is None and max_workspaces else
                   tuple((workspace.feature,) for workspace in profiles.workspaces[:max_workspaces]))
        if not domains and max_workspaces:
            domains = ((),)
    # A cached complete scaffold supplies ambient containment and exact
    # feature stabilizers. Only requested prefix stages are used in search.
    cache = {}
    def certified(domain, features):
        key = domain, features
        if key not in cache:
            prefix = (*_domain_ladder(inventory, domain), *features)
            plan = plan_symbolic_stages(analysis, strategy="manual", features=(*prefix, *finish),
                                        gap_executable=gap_executable, timeout=timeout,
                                        ambient_plan=ambient)
            count = sum(stage.feature in prefix for stage in plan.stages)
            current = plan.stages[count-1].group_after if count else plan.group
            cache[key] = plan, current
        return cache[key]
    continuation_cache = {}
    basis_cache = {}
    def basis_cost(group):
        if ambient.group.order > 512:
            return None
        key = tuple(generator.permutation for generator in group.strong_generators)
        if key not in basis_cache:
            basis_cache[key] = _continuation_basis_htm(group, palette)
        return basis_cache[key]
    def continuation_covers(group):
        permutations = tuple(sorted({recipe.permutation for recipe in palette.recipes
                                     if recipe.permutation in group}))
        if not permutations:
            return group.order == 1
        if permutations not in continuation_cache:
            continuation_cache[permutations] = analyze_generators(
                permutations, prune=False, gap_executable=gap_executable, timeout=timeout).group_order
        return continuation_cache[permutations] == group.order
    frontier, completed = [], []
    for domain in domains:
        plan, group = certified(domain, ())
        frontier.append(_Node(domain, (), (), frozenset(), plan, group, group.order, (group.order,)))
    expanded, transitions, orbit_rejections, missing_policies, policy_cutoffs = 0, 0, 0, 0, 0
    beam_discards, horizon_rejections, expansion_rejections, continuation_rejections = 0, 0, 0, 0
    stop_reasons = set()
    if (domain_features is None and profiles.common_workspace is not None and
            len(profiles.workspaces) > max_workspaces):
        stop_reasons.add("workspace_limit")
    seen = []
    for depth in range(max_stages + 1):
        next_frontier = []
        for node in frontier:
            if node.group.order == 1:
                completed.append(node)
                continue
            if depth == max_stages:
                horizon_rejections += 1
                stop_reasons.add("depth_limit")
                continue
            if expanded >= max_expansions:
                expansion_rejections += 1
                stop_reasons.add("expansion_limit")
                continue
            expanded += 1
            report_progress("coarse_method_frontier", depth=depth, expanded=expanded,
                            subgroup_order=node.group.order, taught_definitions=len(node.taught),
                            case_counts=list(node.counts),
                            features=[dict(kind=feature.kind, reference_cells=list(feature.cells),
                                           alignment_order=len(feature.alignment_permutations))
                                      for feature in node.features])
            for feature in _features(inventory, node.group, palette, profiles,
                                     max_candidates, max_alignment_order):
                checkpoint("coarse_method_proposal")
                policy_frontier = stage_policy_frontier(inventory, node.group, feature, palette,
                    already_taught=node.taught, max_taught_bodies=max_taught_bodies,
                    max_observations=max_observations, max_policy_labels=max_policy_labels,
                    max_candidates=max_policies, max_short_setup_htm=max_short_setup_htm)
                if policy_frontier.status == "orbit_limit":
                    orbit_rejections += 1
                if not policy_frontier.complete_search:
                    policy_cutoffs += 1
                    stop_reasons.update("policy_" + reason for reason in policy_frontier.stop_reasons)
                if not policy_frontier.policies:
                    missing_policies += 1
                    continue
                if len(policy_frontier.observations) <= 1:
                    continue
                features = (*node.features, feature)
                plan, group = certified(node.domain, features)
                if group.order * len(policy_frontier.observations) != node.group.order:
                    raise ValueError("proposed observer orbit disagrees with its exact stabilizer")
                if group.order > 1 and not continuation_covers(group):
                    # If all declared preserving recipes generate only a
                    # proper subgroup, some residual states cannot reach
                    # identity in this planner's endpoint action alphabet.
                    # Bounded derived operations have already been admitted
                    # and profiled; test only their complete endpoints here.
                    continuation_rejections += 1
                    continue
                for policy in policy_frontier.policies:
                    transitions += 1
                    child = _Node(node.domain, features, (*node.policies, policy), policy.total_body_ids,
                                  plan, group, node.domain_order, (*node.orders, group.order),
                                  node.mean + policy.mean_htm, node.worst + policy.worst_htm,
                                  (*node.counts, policy.case_count), basis_cost(group))
                    # Orders alone never identify a subgroup. Prove equality
                    # by generator containment before applying state dominance.
                    peers = [prior for prior in seen if prior.domain == child.domain
                             and prior.group.order == group.order
                             and all(generator.permutation in prior.group
                                     for generator in group.strong_generators)]
                    if any(_dominates(prior, child) for prior in peers):
                        continue
                    dominated = {id(prior) for prior in peers if _dominates(child, prior)}
                    seen = [prior for prior in seen if id(prior) not in dominated]
                    next_frontier = [prior for prior in next_frontier if id(prior) not in dominated]
                    completed = [prior for prior in completed if id(prior) not in dominated]
                    seen.append(child)
                    if group.order == 1:
                        completed.append(child)
                    else:
                        next_frontier.append(child)
        ordered = sorted(next_frontier, key=lambda node: _rank(node, preference, partial=True))
        frontier = ordered[:beam_width]
        if len(ordered) > beam_width:
            beam_discards += len(ordered) - beam_width
            stop_reasons.add("beam_limit")
            discarded = {id(node) for node in ordered[beam_width:]}
            # A discarded history supplies no continuation. Keeping it as a
            # dominance witness can suppress a later route that is retained.
            seen = [node for node in seen if id(node) not in discarded]
        if not frontier:
            break
    # Retain complete nondominated methods over each exact workspace separately.
    best = []
    for node in sorted(completed, key=lambda node: _rank(node, preference)):
        if not any(prior.domain == node.domain and _dominates(prior, node) for prior in best):
            best.append(node)
    candidates = tuple(CoarseMethodCandidate(f"C{number}", node.domain, node.features,
        node.taught, node.mean, node.worst, node.counts, node.domain_order, node.orders,
        node.plan, node.policies) for number, node in enumerate(best, 1))
    selected, method = (candidates[0] if candidates else None), None
    if selected is not None:
        method = _compile_candidate(selected, palette, max_taught_bodies=max_taught_bodies,
                                    max_short_setup_htm=max_short_setup_htm)
    unrestricted_reference = bool(method is not None and
                                  method.group_order == method.ambient_group_order)
    metadata = {"goals_seeded": False, "workspace_seeded": domain_features is not None,
        "reference_shape_count": analysis.loops.shape_count,
        "all_reference_group_states": unrestricted_reference,
        "whole_scramble_method_claim": bool(unrestricted_reference and analysis.loops.shape_count == 1),
        "entry_policy_discovered": False,
        "entry_required_at_reference_shape": None if method is None else not unrestricted_reference,
        "entry_scope": "start-domain contract; entry coverage is not inferred from preservers",
        "profile_evidence": profiles.to_dict(), "bounded_search": True, "exhaustive_method_search": False,
        "expanded_frontier_nodes": expanded, "complete_policy_edges": transitions,
        "orbit_limit_rejections": orbit_rejections, "proposals_without_complete_policy": missing_policies,
        "bounded_policy_searches": policy_cutoffs, "certified_prefixes": len(cache),
        "beam_discarded_nodes": beam_discards, "stage_horizon_rejections": horizon_rejections,
        "expansion_limit_rejections": expansion_rejections,
        "palette_continuation_order_rejections": continuation_rejections,
        "continuation_subgroup_checks": len(continuation_cache),
        "partial_rank_heuristic": "small_certified_group_shortest_independent_endpoint_basis_htm",
        "continuation_order_scope": "necessary reachability bound; complete stage policies certify coverage",
        "continuation_alphabet_scope": "complete_declared_recipes_individually_preserving_committed_subgroup",
        "stop_reasons": sorted(stop_reasons),
        "settings": dict(max_taught_bodies=max_taught_bodies, beam_width=beam_width,
            max_expansions=max_expansions, max_stages=max_stages, max_candidates=max_candidates,
            max_observations=max_observations, max_policy_labels=max_policy_labels,
            max_policies=max_policies, max_workspaces=max_workspaces,
            max_alignment_order=max_alignment_order, max_short_setup_htm=max_short_setup_htm,
            preference=preference), "wall_seconds": perf_counter()-started}
    return CoarseMethodSearch(method, candidates, None if selected is None else selected.id,
                              json.dumps(metadata, sort_keys=True))
