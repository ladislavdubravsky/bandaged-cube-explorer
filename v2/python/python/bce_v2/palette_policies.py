"""Complete stage policies with alternative global taught-body commitments.

Shortest paths for one unrestricted palette lose the distinction between
reusing known bodies and teaching a faster new body. This module searches
bounded subsets of declared body IDs and keeps their Pareto frontier. Setup,
inverse and repetition permissions retain the palette's original taught ID.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from itertools import combinations
from math import comb
from types import MappingProxyType

from .algorithm_palette import AlgorithmPalette
from .block_actions import BlockInventory
from .computation import checkpoint
from .human_chains import (BlockFeature, _check_alignment_membership, _feature_successor,
                           _observation, _resolve_feature)
from .symbolic_groups import PermutationGroupCertificate


_IDENTITY = tuple(range(48))


def _limit(value, name):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def recipe_taught_ids(palette, max_short_setup_htm=4):
    """Count long setup/adjustment words as learned definitions too.

    Short setups and adjustments are elementary handling. A longer word uses
    a stable ``setup:<id>`` or ``adjustment:<id>`` teaching ID, shared when the
    same physical word is declared several times. An identical declared body
    supplies that word's existing body ID instead. Recipe inverse permission
    does not create a second teaching unit. Name collisions with body IDs are
    rejected instead of silently undercounting the repertoire.
    """
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    _limit(max_short_setup_htm, "max_short_setup_htm")
    body_ids = {body.id for body in palette.bodies}
    words = {}
    for body in sorted(palette.bodies, key=lambda item: item.id):
        words.setdefault(body.algorithm.turn_sequence, body.id)
    declared = sorted((kind, item.id, item.algorithm.turn_sequence)
                      for kind, items in (("setup", palette.setups),
                                          ("adjustment", palette.adjustments))
                      for item in items if item.algorithm.htm_length > max_short_setup_htm)
    # Prefer setup names when an adjustment and setup teach the same word.
    declared.sort(key=lambda value: (value[0] != "setup", value[1]))
    definitions = {}
    for kind, identifier, word in declared:
        if word not in words:
            taught_id = f"{kind}:{identifier}"
            if taught_id in body_ids:
                raise ValueError("long setup/adjustment teaching ID collides with a body ID")
            words[word] = taught_id
        definitions[kind, identifier] = words[word]
    mapping = {}
    for record in palette.recipe_records:
        identifiers = set(palette.recipe_body_ids[record["id"]])
        for kind, key in (("setup", "setup_ids"), ("adjustment", "adjustment_ids")):
            for declaration_id in record[key]:
                if (kind, declaration_id) in definitions:
                    identifiers.add(definitions[kind, declaration_id])
        mapping[record["id"]] = frozenset(identifiers)
    return MappingProxyType(mapping)


@dataclass(frozen=True)
class StagePalettePolicy:
    """One complete directed policy over a certified feature orbit.

    ``recipes`` and ``costs`` align with ``observations``. ``used_body_ids``
    counts taught definitions used anywhere in the stage, including long
    setup/adjustment words; ``total_body_ids`` also includes the caller's
    previous commitments. Costs sum physical HTM
    of palette recipes before cancellation between successive calls.
    """

    feature: BlockFeature
    block_index: int | tuple[int, ...]
    observations: tuple[tuple[int, ...], ...]
    solved_observation: tuple[int, ...]
    recipes: tuple[tuple[str, ...], ...]
    costs: tuple[int, ...]
    used_body_ids: frozenset[str]
    total_body_ids: frozenset[str]
    eligible_recipe_ids: tuple[str, ...]
    used_setup_ids: frozenset[str]
    used_adjustment_ids: frozenset[str]
    setup_calls: tuple[int, ...]
    body_calls: tuple[int, ...]
    declared_body_ids: frozenset[str]
    long_definition_ids: frozenset[str]

    @property
    def complete(self):
        return True

    @property
    def case_count(self):
        return len(self.observations)

    @property
    def mean_htm(self):
        return Fraction(sum(self.costs), self.case_count)

    @property
    def worst_htm(self):
        return max(self.costs)

    @property
    def case_recipes(self):
        return dict(zip(self.observations, self.recipes))

    @property
    def rank_key(self):
        return (len(self.total_body_ids), self.mean_htm, self.worst_htm,
                tuple(sorted(self.total_body_ids)), self.recipes)

    def to_dict(self):
        return {"feature": self.feature.to_dict(),
                "observations": [list(value) for value in self.observations],
                "solved_observation": list(self.solved_observation),
                "recipes": [list(recipe) for recipe in self.recipes],
                "costs": list(self.costs), "case_count": self.case_count,
                "complete": True, "used_body_ids": sorted(self.used_body_ids),
                "total_body_ids": sorted(self.total_body_ids),
                "declared_body_ids": sorted(self.declared_body_ids),
                "long_definition_ids": sorted(self.long_definition_ids),
                "eligible_recipe_ids": list(self.eligible_recipe_ids),
                "used_setup_ids": sorted(self.used_setup_ids),
                "used_adjustment_ids": sorted(self.used_adjustment_ids),
                "mean_setup_calls": float(Fraction(sum(self.setup_calls), self.case_count)),
                "mean_body_calls": float(Fraction(sum(self.body_calls), self.case_count)),
                "mean_htm": float(self.mean_htm),
                "mean_htm_numerator": self.mean_htm.numerator,
                "mean_htm_denominator": self.mean_htm.denominator,
                "worst_htm": self.worst_htm,
                "cost_scope": "additive palette recipe HTM before boundary cancellation"}


@dataclass(frozen=True)
class StagePolicyFrontier:
    """Complete returned policies and explicit quality-search diagnostics.

    ``complete_search`` means every admitted body subset was evaluated and
    every nondominated policy was retained. It does not assert that any
    palette policy exists. A bounded search never exposes a partial policy.
    """

    policies: tuple[StagePalettePolicy, ...]
    status: str
    complete_search: bool
    observations: tuple[tuple[int, ...], ...]
    solved_observation: tuple[int, ...]
    evaluated_subsets: int
    total_subsets: int
    covered_subsets: int
    eligible_recipe_ids: tuple[str, ...]
    stop_reasons: tuple[str, ...] = ()

    def to_dict(self):
        return {"status": self.status, "complete_search": self.complete_search,
                "case_count": len(self.observations),
                "evaluated_subsets": self.evaluated_subsets,
                "total_subsets": self.total_subsets,
                "covered_subsets": self.covered_subsets,
                "eligible_recipe_ids": list(self.eligible_recipe_ids),
                "stop_reasons": list(self.stop_reasons),
                "policies": [policy.to_dict() for policy in self.policies]}


def _orbit(inventory, group, block, kind, maximum):
    solved = _observation(inventory.action(_IDENTITY), block, kind)
    if maximum == 0:
        return solved, None
    actions = tuple(inventory.action(generator.permutation)
                    for generator in group.strong_generators)
    found, queue = {solved}, deque([solved])
    while queue:
        checkpoint("palette_policy_orbit")
        observation = queue.popleft()
        for action in actions:
            image = _feature_successor(observation, action, inventory, block, kind)
            if image not in found:
                if len(found) >= maximum:
                    return solved, None
                found.add(image)
                queue.append(image)
    return solved, tuple(sorted(found))


def _shortest_paths(observations, solved, transitions, allowed):
    reverse = defaultdict(list)
    for identifier, body_ids, weight, mapping in transitions:
        if not body_ids.issubset(allowed):
            continue
        for source, destination in zip(observations, mapping):
            if source != destination:
                reverse[destination].append((source, identifier, weight))
    best, queue = {solved: (0, ())}, [(0, (), solved)]
    while queue:
        checkpoint("palette_policy_paths")
        cost, path, destination = heappop(queue)
        if best[destination] != (cost, path):
            continue
        for source, identifier, weight in reverse[destination]:
            candidate = cost + weight, (identifier, *path)
            if source not in best or candidate < best[source]:
                best[source] = candidate
                heappush(queue, (*candidate, source))
    return best if len(best) == len(observations) else None


def _nondominated_transitions(transitions):
    """Keep exact observer actions with incomparable teaching commitments.

    A complete operation may have a different physical endpoint from another
    while inducing the same action on this stage's entire certified orbit.
    The cheaper operation with a subset of teaching dependencies can replace
    it in every policy. No state, observation fiber or permission is inferred
    from this reduction; all input maps have already been checked exactly.
    """
    by_mapping = defaultdict(list)
    for transition in transitions:
        identifier, dependencies, weight, mapping = transition
        previous = by_mapping[mapping]
        if any(ids.issubset(dependencies) and cost <= weight and
               (ids != dependencies or cost != weight or name <= identifier)
               for name, ids, cost, _ in previous):
            continue
        by_mapping[mapping] = [value for value in previous
                              if not (dependencies.issubset(value[1]) and weight <= value[2])]
        by_mapping[mapping].append(transition)
    return tuple(sorted((value for values in by_mapping.values() for value in values),
                        key=lambda value: value[0]))


def _dominates(first, second):
    return (first.total_body_ids.issubset(second.total_body_ids)
            and first.mean_htm <= second.mean_htm
            and first.worst_htm <= second.worst_htm)


def stage_policy_frontier(inventory, group_before, feature, palette, *, already_taught=(),
                          max_observations=512, max_taught_bodies=7,
                          max_policy_labels=4096, max_candidates=128,
                          max_short_setup_htm=4):
    """Find complete stage policies without prematurely committing new bodies.

    The observation domain comes from the entire certified preceding group,
    independently of the palette. Only complete declared recipes belonging
    to that group can be correction edges. Dijkstra follows reversed directed
    edges and therefore never grants undeclared inverse permission.

    ``max_policy_labels`` bounds the number of body subsets evaluated, rather
    than the number of intermediate shortest-path vertices. Subsets are tried
    by increasing number of new bodies. ``max_candidates`` bounds the returned
    Pareto frontier. Either cutoff sets ``complete_search=False``. Exceeding
    ``max_observations`` returns ``status='orbit_limit'`` with no policy; it
    never treats a partial domain as certified coverage.
    Long setups and adjustments consume taught-body budget according to
    ``recipe_taught_ids``; their physical word may reuse an existing body ID.
    """
    if not isinstance(inventory, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    if not isinstance(group_before, PermutationGroupCertificate) or group_before.degree != 48:
        raise TypeError("group_before must be a 48-point PermutationGroupCertificate")
    if not isinstance(feature, BlockFeature):
        raise TypeError("feature must be a BlockFeature")
    if not isinstance(palette, AlgorithmPalette):
        raise TypeError("palette must be an AlgorithmPalette")
    for name, value in (("max_observations", max_observations),
                        ("max_taught_bodies", max_taught_bodies),
                        ("max_policy_labels", max_policy_labels),
                        ("max_candidates", max_candidates),
                        ("max_short_setup_htm", max_short_setup_htm)):
        _limit(value, name)
    teaching = recipe_taught_ids(palette, max_short_setup_htm)
    declared_body_ids = frozenset(body.id for body in palette.bodies)
    all_teaching_ids = declared_body_ids | frozenset(identifier for ids in teaching.values()
                                                   for identifier in ids)
    already = frozenset(already_taught)
    if any(not isinstance(identifier, str) for identifier in already):
        raise TypeError("already_taught must contain body ID strings")
    if not already.issubset(all_teaching_ids):
        raise ValueError("already_taught contains undeclared palette teaching IDs")
    if len(already) > max_taught_bodies:
        raise ValueError("already_taught exceeds max_taught_bodies")
    palette.validate(inventory=inventory)
    block = _resolve_feature(inventory, feature)
    _check_alignment_membership(feature, group_before.contains)
    solved, observations = _orbit(inventory, group_before, block, feature.kind,
                                  max_observations)
    if observations is None:
        return StagePolicyFrontier((), "orbit_limit", False, (), solved, 0, 0, 0, (),
                                   ("max_observations",))

    eligible = tuple(sorted((algorithm for algorithm in palette.recipes
                             if algorithm.permutation in group_before), key=lambda a: a.id))
    eligible_ids = tuple(algorithm.id for algorithm in eligible)
    domain, transitions = set(observations), []
    for algorithm in eligible:
        checkpoint("palette_policy_transitions")
        action = inventory.action(algorithm.permutation)
        mapping = tuple(_feature_successor(value, action, inventory, block, feature.kind)
                        for value in observations)
        if not set(mapping).issubset(domain):
            raise ValueError("a protected palette action leaves the certified feature orbit")
        transitions.append((algorithm.id, teaching[algorithm.id],
                            algorithm.htm_length, mapping))
    transitions = _nondominated_transitions(transitions)
    available_bodies = frozenset(identifier for _, ids, _, _ in transitions for identifier in ids)
    new_bodies = tuple(sorted(available_bodies - already))
    remaining = min(max_taught_bodies - len(already), len(new_bodies))
    total_subsets = sum(comb(len(new_bodies), size) for size in range(remaining + 1))
    records = {record["id"]: record for record in palette.recipe_records}
    frontier, evaluated, covered = [], 0, 0
    for size in range(remaining + 1):
        for addition in combinations(new_bodies, size):
            if evaluated >= max_policy_labels:
                break
            checkpoint("palette_policy_subsets")
            evaluated += 1
            best = _shortest_paths(observations, solved, transitions, already | frozenset(addition))
            if best is None:
                continue
            covered += 1
            recipes = tuple(best[value][1] for value in observations)
            used = frozenset(identifier for recipe in recipes for step in recipe
                             for identifier in teaching[step])
            declared_used = used & declared_body_ids
            used_records = tuple(records[step] for recipe in recipes for step in recipe)
            policy = StagePalettePolicy(
                feature, block, observations, solved, recipes,
                tuple(best[value][0] for value in observations), used, already | used,
                tuple(identifier for identifier, ids, _, _ in transitions
                      if ids.issubset(already | frozenset(addition))),
                frozenset(identifier for record in used_records for identifier in record["setup_ids"]),
                frozenset(identifier for record in used_records for identifier in record["adjustment_ids"]),
                tuple(sum(records[step]["setup_calls"] for step in recipe)
                      for recipe in recipes),
                tuple(sum(records[step]["body_calls"] for step in recipe) for recipe in recipes),
                declared_used, used - declared_body_ids)
            if any(_dominates(existing, policy) for existing in frontier):
                continue
            frontier = [existing for existing in frontier if not _dominates(policy, existing)]
            frontier.append(policy)
        if evaluated >= max_policy_labels:
            break
    reasons = []
    if evaluated < total_subsets:
        reasons.append("max_policy_labels")
    frontier.sort(key=lambda policy: policy.rank_key)
    if len(frontier) > max_candidates:
        frontier = frontier[:max_candidates]
        reasons.append("max_candidates")
    status = ("bounded" if reasons else "completed" if frontier else "uncovered")
    return StagePolicyFrontier(tuple(frontier), status, not reasons, observations, solved,
                               evaluated, total_subsets, covered, eligible_ids, tuple(reasons))
