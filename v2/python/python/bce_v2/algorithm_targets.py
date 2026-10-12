"""Algorithm-informed anonymous phase targets on certified subgroup orbits.

Only observation patterns are enumerated. The current subgroup supplies the
full case domain; the available physical algorithms supply correction edges
and preservation profiles. Missing cases never receive a finite stage mean.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from heapq import heappop, heappush
from math import log2

from . import State
from .block_actions import BlockInventory
from .computation import checkpoint
from .human_chains import BlockFeature, _feature_successor
from .loop_algorithms import LoopAlgorithm
from .symbolic_groups import PermutationGroupCertificate


@dataclass(frozen=True)
class AlgorithmTarget:
    """An invariant slot-phase goal and its available-repertoire coverage.

    ``recipes`` aligns with ``observations`` and contains algorithm IDs in
    execution order. None denotes an uncovered case; the solved recipe is ().
    Costs are additive HTM in the supplied palette, before cancellation.
    """

    feature: BlockFeature
    block_indices: tuple[int, ...]
    observations: tuple[tuple[int, ...], ...]
    solved_observation: tuple[int, ...]
    recipes: tuple[tuple[str, ...] | None, ...]
    costs: tuple[int | None, ...]
    preserving_algorithm_ids: tuple[str, ...]
    available_algorithm_ids: tuple[str, ...]
    proposal_sources: tuple[str, ...]

    @property
    def case_count(self):
        return len(self.observations)

    @property
    def covered_count(self):
        return sum(cost is not None for cost in self.costs)

    @property
    def complete(self):
        return self.covered_count == self.case_count

    @property
    def mean_htm(self):
        return sum(self.costs) / self.case_count if self.complete else None

    @property
    def worst_htm(self):
        return max(self.costs) if self.complete else None

    @property
    def rank_key(self):
        return (not self.complete,
                self.mean_htm / log2(self.case_count) if self.complete else float("inf"),
                -len(self.preserving_algorithm_ids), self.case_count, self.feature.cells)

    def to_dict(self):
        return {"feature": self.feature.to_dict(), "block_indices": list(self.block_indices),
                "observations": [list(value) for value in self.observations],
                "solved_observation": list(self.solved_observation),
                "recipes": [None if recipe is None else list(recipe) for recipe in self.recipes],
                "costs": list(self.costs), "case_count": self.case_count,
                "covered_count": self.covered_count, "complete": self.complete,
                "mean_htm": self.mean_htm, "worst_htm": self.worst_htm,
                "preserving_algorithm_ids": list(self.preserving_algorithm_ids),
                "available_algorithm_ids": list(self.available_algorithm_ids),
                "proposal_sources": list(self.proposal_sources),
                "cost_scope": "additive palette HTM before boundary cancellation"}


def _limit(value, name):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _prepare_algorithm_catalog(inventory, group, algorithms):
    """Validate public physical inputs once, then reuse their exact effects."""
    if not isinstance(inventory, BlockInventory):
        raise TypeError("inventory must be a BlockInventory")
    if not isinstance(group, PermutationGroupCertificate) or group.degree != 48:
        raise TypeError("group must be a 48-point PermutationGroupCertificate")
    algorithms = tuple(algorithms)
    if any(not isinstance(algorithm, LoopAlgorithm) for algorithm in algorithms):
        raise TypeError("algorithms must contain witnessed LoopAlgorithm instances")
    identifiers = [algorithm.id for algorithm in algorithms]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("algorithm IDs must be unique")
    initial, catalog = State(inventory.root_shape), []
    for algorithm in algorithms:
        checkpoint("algorithm_target_catalog")
        if algorithm._inventory.root_shape != inventory.root_shape:
            raise ValueError("algorithm uses another reference shape")
        replay = initial.apply(algorithm.turn_sequence)
        if replay.shape != initial.shape or tuple(replay.sticker_permutation) != algorithm.permutation:
            raise ValueError("algorithm has an invalid legal root-loop witness")
        if algorithm.permutation not in group:
            continue
        catalog.append((algorithm, inventory.action(algorithm.permutation)))
    return tuple(catalog)


def _slot_orbits(inventory, actions):
    """Current-group placement orbits, including orientation-only singletons."""
    unseen, orbits = set(range(len(inventory.blocks))), []
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
        if (inventory.blocks[start].orientation_order > 1
                and any(action.phases[slot] for action in actions for slot in found)):
            orbits.append(tuple(sorted(found)))
    return tuple(orbits)


def _bounded_phase_orbit(inventory, slots, actions, maximum):
    solved = (0,) * len(slots)
    found, queue = {solved}, deque([solved])
    while queue:
        checkpoint("algorithm_target_orbit")
        observation = queue.popleft()
        for action in actions:
            image = _feature_successor(observation, action, inventory, slots, "orient_slots")
            if image not in found:
                if len(found) >= maximum:
                    return None
                found.add(image)
                queue.append(image)
    return tuple(sorted(found))


def _target(inventory, slots, observations, catalog, sources):
    solved, reverse = (0,) * len(slots), defaultdict(list)
    # Equal induced actions only need their cheapest physical representative.
    induced = {}
    for algorithm, action in catalog:
        checkpoint("algorithm_target_edges")
        mapping = tuple(_feature_successor(value, action, inventory, slots, "orient_slots")
                        for value in observations)
        key = algorithm.htm_length, algorithm.qtm_length, algorithm.id
        if mapping not in induced or key < induced[mapping][0]:
            induced[mapping] = key, algorithm
    for mapping, (_, algorithm) in induced.items():
        for source, destination in zip(observations, mapping):
            reverse[destination].append((source, algorithm.id, algorithm.htm_length))
    distances, recipes, heap = {solved: 0}, {solved: ()}, [(0, solved)]
    while heap:
        checkpoint("algorithm_target_search")
        cost, destination = heappop(heap)
        if distances[destination] != cost:
            continue
        for source, identifier, weight in reverse[destination]:
            candidate = cost + weight
            if candidate < distances.get(source, float("inf")):
                distances[source] = candidate
                recipes[source] = (identifier, *recipes[destination])
                heappush(heap, (candidate, source))
    feature = BlockFeature("orient_slots", tuple(cell for slot in slots
                                                 for cell in inventory.blocks[slot].cells))
    return AlgorithmTarget(
        feature, slots, observations, solved,
        tuple(recipes.get(value) for value in observations),
        tuple(distances.get(value) for value in observations),
        tuple(algorithm.id for algorithm, action in catalog
              if all(action.phases[slot] == 0 for slot in slots)),
        tuple(algorithm.id for algorithm, _ in catalog), tuple(sorted(sources)))


def _discover_algorithm_targets(inventory, group, catalog, *, max_observations, max_candidates):
    if max_observations < 2 or max_candidates == 0:
        return ()
    actions = tuple(inventory.action(generator.permutation) for generator in group.strong_generators)
    catalog = tuple((algorithm, action) for algorithm, action in catalog
                    if algorithm.permutation in group)
    return _discover_targets_from_actions(inventory, actions, catalog,
                                          max_observations=max_observations,
                                          max_candidates=max_candidates)


def _discover_targets_from_actions(inventory, actions, catalog, *, max_observations, max_candidates):
    """Shared exact-domain discovery for certified or exhaustive subgroup actions."""
    if max_observations < 2 or max_candidates == 0:
        return ()
    if not catalog:
        return ()
    orbits = _slot_orbits(inventory, actions)
    by_slot = {slot: orbit for orbit in orbits for slot in orbit}
    proposals = defaultdict(set)
    for orbit in orbits:
        proposals[orbit].add("current_subgroup_slot_orbit")
    for algorithm, action in catalog:
        # Coordinated phase changes can join multiple placement orbits.
        by_class = defaultdict(set)
        for slot, phase in enumerate(action.phases):
            if phase and slot in by_slot:
                block = inventory.blocks[slot]
                by_class[block.template_cells, block.orientation_order].update(by_slot[slot])
        for slots in by_class.values():
            proposals[tuple(sorted(slots))].add("algorithm:" + algorithm.id)
    candidates = []
    # Small regions are evaluated first; an oversized orbit is never published
    # as a partial observation domain or mistaken for full repertoire coverage.
    for slots, sources in sorted(proposals.items(), key=lambda item: (len(item[0]), item[0]))[:max_candidates]:
        checkpoint("algorithm_target_patterns", slots=len(slots))
        observations = _bounded_phase_orbit(inventory, slots, actions, max_observations)
        if observations is not None and len(observations) > 1:
            candidates.append(_target(inventory, slots, observations, catalog, sources))
    return tuple(sorted(candidates, key=lambda candidate: candidate.rank_key))


def discover_algorithm_targets(inventory, group, algorithms, *, max_observations=128,
                               max_candidates=32):
    """Propose invariant orientation regions from a physical algorithm palette.

    The entire current subgroup defines invariance and possible patterns.
    Algorithm effects propose coordinated unions and supply correction paths;
    incomplete coverage is retained explicitly. ``max_observations`` bounds
    exact pattern enumeration and drops oversized targets, never truncating
    their case domains. This function does not claim a complete cube method.
    """
    _limit(max_observations, "max_observations")
    _limit(max_candidates, "max_candidates")
    catalog = _prepare_algorithm_catalog(inventory, group, algorithms)
    return _discover_algorithm_targets(inventory, group, catalog,
                                      max_observations=max_observations, max_candidates=max_candidates)
