"""Bounded constructive entry using small, exact component observations.

Every accepted word fixes the requested goal and previous commitments at its
endpoint. Search may displace those components temporarily. Small pattern
databases are complete or explicitly discarded; the combined recognition
domain is never enumerated. A successful correction is uniform over its
observed fiber, but bounded search does not certify a complete method.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import combinations
from types import MappingProxyType

from . import State
from ._moves import _simplified_moves
from .algorithm_palette import AlgorithmPalette, AlgorithmPaletteSetup
from .block_actions import BlockInventory, _coordinates
from .human_chains import (BlockFeature, _ActionSummary, _feature_indices,
                           _inverse, _observation,
                           _resolve_feature, _then)
from .isotropy import LoopGenerators, isotropy_loops
from .loop_algorithms import AlgorithmLibrary, LoopExpression, _loops_from_records


_IDENTITY = tuple(range(48))


def _positive_integer(name, value, *, zero=False):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < (0 if zero else 1):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}")
    return value


def _reference(initial, generators):
    if isinstance(initial, BlockInventory):
        if generators is None:
            raise ValueError("a BlockInventory requires witnessed generators")
        return initial, _loops_from_records(tuple(generators))
    if generators is not None:
        raise ValueError("generators are only accepted with a BlockInventory")
    if isinstance(initial, LoopGenerators):
        return initial.block_inventory, initial
    inventory = getattr(initial, "inventory", None)
    records = getattr(initial, "generators", None)
    if inventory is not None and records is not None:
        return inventory, _loops_from_records(tuple(records))
    loops = getattr(initial, "loops", None)
    if loops is None:
        analysis = getattr(initial, "analysis", None)
        loops = getattr(analysis, "loops", None)
    if loops is None:
        loops = isotropy_loops(initial)
    return loops.block_inventory, loops


def _native_palette(loops):
    """Declare each witnessed loop, its inverse and square as adjustments."""
    builder = AlgorithmLibrary(loops, (), (), ())
    entries, best = [], {}
    for generator in loops.generators:
        for exponent in (1, -1, 2):
            expression = LoopExpression.power(LoopExpression.loop(generator.id), exponent)
            algorithm = builder.build_algorithm(expression)
            if algorithm.permutation == _IDENTITY:
                continue
            key = algorithm.htm_length, algorithm.turn_sequence
            existing = best.get(algorithm.permutation)
            if existing is None or key < existing[0]:
                best[algorithm.permutation] = key, generator.id, exponent, algorithm
    for _, identifier, exponent, algorithm in sorted(best.values(), key=lambda row: row[0]):
        entries.append(AlgorithmPaletteSetup(f"native-{identifier}^{exponent}", algorithm))
    return AlgorithmPalette((), adjustments=tuple(entries))


@dataclass(frozen=True)
class ConstructiveEntryCorrection:
    """A concrete, independently replayed correction or an explicit limit."""

    status: str
    feature: BlockFeature
    protected_features: tuple[BlockFeature, ...]
    observation: tuple[int, ...]
    action_ids: tuple[str, ...]
    turn_sequence: str
    before: State = field(repr=False, compare=False)
    after: State = field(repr=False, compare=False)
    metrics: object
    reason: str | None = None
    complete: bool = False

    @property
    def state(self):
        return self.after

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())

    @property
    def successful(self):
        return self.status in ("ready", "already_satisfied")


class ConstructiveEntryController:
    """Find endpoint-safe entry words over an explicitly declared palette.

    The default palette declares original witnessed loops and their powers as
    standalone adjustments. Supplying a palette instead restricts all search
    to exactly its complete recipes, including declared inverse permissions.
    ``max_depth`` bounds additive recipe HTM before boundary cancellation.
    ``max_nodes`` bounds expanded search nodes per call. Single-component
    patterns are always attempted; ``max_pattern_count`` bounds additional
    multi-component patterns. Cached complete patterns have a separate bound.
    """

    def __init__(self, initial, *, palette=None, generators=None,
                 max_pattern_observations=1024, max_pattern_count=16,
                 max_pattern_components=2, max_cached_patterns=64,
                 max_depth=12, max_nodes=2_000_000):
        self.inventory, loops = _reference(initial, generators)
        self.reference_shape = self.inventory.root_shape
        self.max_pattern_observations = _positive_integer(
            "max_pattern_observations", max_pattern_observations)
        self.max_pattern_count = _positive_integer("max_pattern_count", max_pattern_count, zero=True)
        self.max_pattern_components = _positive_integer("max_pattern_components", max_pattern_components)
        if self.max_pattern_components > 3:
            raise ValueError("max_pattern_components must be at most three")
        self.max_cached_patterns = _positive_integer("max_cached_patterns", max_cached_patterns)
        self.max_depth = _positive_integer("max_depth", max_depth, zero=True)
        self.max_nodes = _positive_integer("max_nodes", max_nodes, zero=True)
        if palette is None:
            palette = _native_palette(loops)
        if not isinstance(palette, AlgorithmPalette):
            raise TypeError("palette must be an AlgorithmPalette")
        palette.validate(inventory=self.inventory)
        self.palette = palette
        # Equal effects need only their cheapest permitted complete recipe.
        by_effect = {}
        for action in palette.recipes:
            if action.permutation == _IDENTITY:
                continue
            previous = by_effect.get(action.permutation)
            if previous is None or (action.htm_length, action.id) < (previous.htm_length, previous.id):
                by_effect[action.permutation] = action
        self.actions = tuple(sorted(by_effect.values(), key=lambda a: (a.htm_length, a.id)))
        self._effects = tuple(self.inventory.action(action.permutation) for action in self.actions)
        self._inverse_effects = tuple(self.inventory.action(_inverse(action.permutation))
                                      for action in self.actions)
        # A component pose has exactly one integer coordinate. Transition
        # tables use each source component's actual orientation order; no
        # ordinary-cube type or fixed phase modulus enters the search.
        self._pose_transitions = self._pose_tables(self._effects)
        self._inverse_pose_transitions = self._pose_tables(self._inverse_effects)
        self._patterns = OrderedDict()
        self._skip_pairs = set()
        costs = {a.permutation: a.htm_length for a in self.actions}
        for i, first in enumerate(self.actions):
            for j, second in enumerate(self.actions):
                product = _then(first.permutation, second.permutation)
                if (product == _IDENTITY or
                        costs.get(product, first.htm_length + second.htm_length + 1)
                        <= first.htm_length + second.htm_length or
                        (i > j and product == _then(second.permutation, first.permutation))):
                    self._skip_pairs.add((i, j))
        self._adjacent = set()
        for i, first in enumerate(self.inventory.blocks):
            for j, second in enumerate(self.inventory.blocks[:i]):
                if any(sum(abs(a-b) for a, b in zip(_coordinates(left), _coordinates(right))) == 1
                       for left in first.cells for right in second.cells):
                    self._adjacent.add(frozenset((i, j)))

    def _pose_tables(self, effects):
        orders = {block.orientation_order for block in self.inventory.blocks}
        return {order: tuple(tuple(effect.destinations[slot] * order +
                                  (phase + effect.phases[slot]) % order
                                  for slot in range(len(self.inventory.blocks))
                                  for phase in range(order)) for effect in effects)
                for order in orders}

    def _pattern_layout(self, feature):
        members = _feature_indices(self.inventory, feature)
        phase = feature.kind.startswith("solve")
        orders = tuple(self.inventory.blocks[index].orientation_order if phase else 1
                       for index in members)
        bases = tuple(len(self.inventory.blocks) * order for order in orders)
        strides, product = [], 1
        for base in bases:
            strides.append(product)
            product *= base
        return members, phase, orders, bases, tuple(strides)

    def _indices(self, features):
        indices = set()
        for feature in features:
            selected = _feature_indices(self.inventory, feature)
            indices.update(selected)
            if feature.kind == "orient_slots":
                # An occupant can enter the goal region from any compatible
                # physical slot; observe its identity pose to retain closure.
                slot = self.inventory.blocks[selected[0]]
                indices.update(index for index, block in enumerate(self.inventory.blocks)
                               if (block.template_cells, block.orientation_order) ==
                               (slot.template_cells, slot.orientation_order))
        return tuple(sorted(indices))

    def _pattern(self, feature):
        """Exact directed distances; None means the orbit exceeded its cap."""
        if feature in self._patterns:
            result = self._patterns.pop(feature)
            self._patterns[feature] = result
            return result
        members, phase, orders, bases, strides = self._pattern_layout(feature)
        goal = sum(index * order * stride for index, order, stride in zip(members, orders, strides))
        inverse_tables = (tuple(tuple(self._inverse_pose_transitions[order][action]
                                      for order in orders)
                                for action in range(len(self.actions)))
                          if phase else tuple(tuple(effect.destinations for _ in members)
                                             for effect in self._inverse_effects))
        costs = tuple(action.htm_length for action in self.actions)
        distances, queue = {goal: 0}, [(0, goal)]
        while queue:
            cost, destination = heappop(queue)
            if distances[destination] != cost:
                continue
            coordinates = tuple(destination // stride % base for stride, base in zip(strides, bases))
            for weight, tables in zip(costs, inverse_tables):
                source = sum(table[coordinate] * stride
                             for table, coordinate, stride in zip(tables, coordinates, strides))
                candidate = cost + weight
                if source not in distances:
                    if len(distances) >= self.max_pattern_observations:
                        result = None
                        self._patterns[feature] = result
                        while len(self._patterns) > self.max_cached_patterns:
                            self._patterns.popitem(last=False)
                        return result
                    distances[source] = candidate
                    heappush(queue, (candidate, source))
                elif candidate < distances[source]:
                    distances[source] = candidate
                    heappush(queue, (candidate, source))
        self._patterns[feature] = distances
        while len(self._patterns) > self.max_cached_patterns:
            self._patterns.popitem(last=False)
        return distances

    def _pattern_features(self, feature, protected):
        """Small absolute constraints, ranked by joint insertion relevance."""
        strengths = {}
        for goal in (*protected, feature):
            if goal.kind not in ("solve_block", "solve_blocks", "place_block", "place_blocks"):
                continue
            strength = 2 if goal.kind.startswith("solve") else 1
            for index in _feature_indices(self.inventory, goal):
                strengths[index] = max(strengths.get(index, 0), strength)
        singles = [BlockFeature("solve_block" if strength == 2 else "place_block",
                                self.inventory.blocks[index].cells)
                   for index, strength in sorted(strengths.items())]
        targets = set(_feature_indices(self.inventory, feature))
        candidates = []
        for size in range(2, self.max_pattern_components + 1):
            for members in combinations(sorted(strengths), size):
                # Pair/triple goals of different strengths retain the weaker
                # common placement promise. Singles still capture phases.
                kind = "solve_blocks" if all(strengths[i] == 2 for i in members) else "place_blocks"
                edges = sum(frozenset(pair) in self._adjacent for pair in combinations(members, 2))
                connected = edges >= size - 1
                overlap = len(targets.intersection(members))
                rank = (-int(connected), -overlap, -size, members)
                candidate = BlockFeature(kind, tuple(cell for i in members
                                                       for cell in self.inventory.blocks[i].cells))
                candidates.append((rank, candidate))
        selected = tuple(candidate for _, candidate in sorted(candidates)[:self.max_pattern_count])
        return tuple(singles) + selected

    def plan_step(self, state, feature, *, protected_features=(), max_depth=None, max_nodes=None):
        """Return one bounded, endpoint-safe correction from a colored state."""
        if not isinstance(state, State):
            raise TypeError("entry recognition requires a colored State")
        if not isinstance(feature, BlockFeature):
            raise TypeError("feature must be a BlockFeature")
        protected = tuple(protected_features)
        if any(not isinstance(goal, BlockFeature) for goal in protected):
            raise TypeError("protected_features must contain BlockFeature instances")
        features = (*protected, feature)
        blocks = tuple(_resolve_feature(self.inventory, goal) for goal in features)
        indices = self._indices(features)
        metrics = {"expanded_nodes": 0, "iterations": 0, "searched_htm_bound": 0,
                   "pattern_count": 0, "pattern_limits": 0,
                   "coverage": "concrete_observed_fiber_only", "complete": False}

        def result(status, observation=(), action_ids=(), word="", after=None, reason=None):
            return ConstructiveEntryCorrection(status, feature, protected, observation,
                       tuple(action_ids), word, state, state if after is None else after,
                       MappingProxyType(dict(metrics)), reason)

        if state.specification != self.reference_shape:
            return result("wrong_reference", reason="state has another reference specification")
        if state.shape != self.reference_shape:
            return result("shape_not_restored", reason="restore the reference shape first")
        action = self.inventory.action(state.sticker_permutation)
        solved = tuple(_observation(self.inventory.identity(), block, goal.kind)
                       for goal, block in zip(features, blocks))
        observed = tuple(_observation(action, block, goal.kind)
                         for goal, block in zip(features, blocks))
        observation = tuple(value for index in indices
                            for value in (action.destinations[index], action.phases[index]))
        if observed[:-1] != solved[:-1]:
            return result("commitment_not_satisfied", observation,
                          reason="a protected endpoint commitment is not satisfied")
        if observed == solved:
            return result("already_satisfied", observation)
        limit = self.max_depth if max_depth is None else _positive_integer("max_depth", max_depth, zero=True)
        node_limit = self.max_nodes if max_nodes is None else _positive_integer("max_nodes", max_nodes, zero=True)
        if not self.actions:
            return result("outside_action_orbit", observation, reason="declared actions contain no nonidentity correction")
        positions = {index: offset for offset, index in enumerate(indices)}
        pose_orders = tuple(self.inventory.blocks[index].orientation_order for index in indices)
        encoded = tuple(action.destinations[index] * order + action.phases[index]
                        for index, order in zip(indices, pose_orders))
        transitions = tuple(tuple(self._pose_transitions[order][action_index]
                                  for order in pose_orders)
                            for action_index in range(len(self.actions)))
        patterns = []
        for pattern in self._pattern_features(feature, protected):
            table = self._pattern(pattern)
            if table is None:
                metrics["pattern_limits"] += 1
                continue
            members, phase, _, _, strides = self._pattern_layout(pattern)
            offsets = tuple(positions[index] for index in members)
            divisors = (None if phase else
                        tuple(self.inventory.blocks[index].orientation_order for index in members))
            patterns.append((offsets, strides, divisors, table))
        metrics["pattern_count"] = len(patterns)

        # Common full-pose entry searches avoid generators, slices and tuple
        # allocation in every pattern lookup. Packed keys are exact products
        # of the physical coordinate ranges, not hashes of observations.
        singles, pairs, triples, placement_patterns = [], [], [], []
        for offsets, strides, divisors, table in patterns:
            if divisors is not None:
                placement_patterns.append((offsets, strides, divisors, table))
            elif len(offsets) == 1:
                singles.append((offsets[0], table))
            elif len(offsets) == 2:
                pairs.append((offsets[0], offsets[1], strides[1], table))
            else:
                triples.append((offsets[0], offsets[1], offsets[2], strides[1], strides[2], table))

        def heuristic(value):
            maximum = 0
            for offset, table in singles:
                distance = table.get(value[offset])
                if distance is None:
                    return None
                if distance > maximum:
                    maximum = distance
            for first, second, stride, table in pairs:
                distance = table.get(value[first] + value[second] * stride)
                if distance is None:
                    return None
                if distance > maximum:
                    maximum = distance
            for first, second, third, middle_stride, final_stride, table in triples:
                distance = table.get(value[first] + value[second] * middle_stride +
                                     value[third] * final_stride)
                if distance is None:
                    return None
                if distance > maximum:
                    maximum = distance
            for offsets, strides, divisors, table in placement_patterns:
                key = sum(value[offset] // divisor * stride
                          for offset, divisor, stride in zip(offsets, divisors, strides))
                distance = table.get(key)
                if distance is None:
                    return None
                if distance > maximum:
                    maximum = distance
            return maximum

        def general_satisfied(value):
            destinations = list(range(len(self.inventory.blocks)))
            phases = [0] * len(destinations)
            for index, offset in positions.items():
                destinations[index], phases[index] = divmod(value[offset], pose_orders[offset])
            summary = _ActionSummary(tuple(destinations), tuple(phases), self.inventory)
            if any(goal.kind == "orient_slots" for goal in features):
                # _observation reads phase by destination. Fill only observed
                # compatible occupants to avoid collisions with unobserved
                # identity placeholders.
                by_destination = {destinations[index]: phases[index] for index in indices}
                actual = tuple(tuple(by_destination[index] for index in block)
                               if goal.kind == "orient_slots" else
                               _observation(summary, block, goal.kind)
                               for goal, block in zip(features, blocks))
            else:
                actual = tuple(_observation(summary, block, goal.kind)
                               for goal, block in zip(features, blocks))
            return actual == solved

        if all(goal.kind in ("solve_block", "solve_blocks") for goal in features):
            goal_pose = tuple(index * order for index, order in zip(indices, pose_orders))

            def satisfied(value):
                return value == goal_pose
        else:
            satisfied = general_satisfied

        def successor(value, tables):
            return tuple(table[coordinate] for table, coordinate in zip(tables, value))

        initial_bound = heuristic(encoded)
        if initial_bound is None:
            return result("outside_action_orbit", observation,
                          reason="a complete component pattern has no directed correction")
        bound = initial_bound
        path, solution = [], None
        exceeded = False
        while bound <= limit:
            metrics["iterations"] += 1
            metrics["searched_htm_bound"] = bound
            seen = {}
            next_bound = float("inf")

            def visit(value, cost, previous, estimate):
                nonlocal next_bound, exceeded, solution
                total = cost + estimate
                if total > bound:
                    next_bound = min(next_bound, total)
                    return False
                if estimate == 0 and satisfied(value):
                    solution = tuple(path)
                    return True
                if metrics["expanded_nodes"] >= node_limit:
                    exceeded = True
                    return False
                # Include the previous action because exact two-call pruning
                # changes the available continuations at this node.
                key = value, previous
                if seen.get(key, cost + 1) <= cost:
                    return False
                seen[key] = cost
                metrics["expanded_nodes"] += 1
                children = []
                for index, (algorithm, tables) in enumerate(zip(self.actions, transitions)):
                    if (previous, index) in self._skip_pairs:
                        continue
                    image = successor(value, tables)
                    if image == value:
                        continue
                    estimate = heuristic(image)
                    if estimate is None:
                        continue
                    total = cost + algorithm.htm_length + estimate
                    if total > bound:
                        next_bound = min(next_bound, total)
                        continue
                    children.append((algorithm.htm_length + estimate, index, image, estimate))
                for _, index, image, estimate in sorted(children):
                    path.append(index)
                    if visit(image, cost + self.actions[index].htm_length, index, estimate):
                        return True
                    path.pop()
                    if exceeded:
                        return False
                return False

            if visit(encoded, 0, None, initial_bound):
                break
            if exceeded:
                return result("node_limit", observation, reason="entry node budget exhausted")
            if next_bound == float("inf"):
                return result("outside_action_orbit", observation,
                              reason="finite projected search found no declared-action correction")
            bound = next_bound
        if solution is None:
            return result("depth_limit", observation,
                          reason="no entry correction within the additive recipe HTM bound")
        chosen = tuple(self.actions[index] for index in solution)
        word = _simplified_moves(token for algorithm in chosen for token in algorithm.turn_sequence.split())
        after = state.apply(word)
        expected = state.sticker_permutation
        projected = encoded
        for index in solution:
            expected = _then(expected, self.actions[index].permutation)
            projected = successor(projected, transitions[index])
        after_action = self.inventory.action(after.sticker_permutation)
        after_observation = tuple(value for index in indices
                                  for value in (after_action.destinations[index], after_action.phases[index]))
        decoded = tuple(value for coordinate, order in zip(projected, pose_orders)
                        for value in divmod(coordinate, order))
        if (after.shape != self.reference_shape or after.sticker_permutation != expected or
                decoded != after_observation or not satisfied(projected)):
            raise ValueError("entry correction fails physical replay or cumulative endpoint goals")
        metrics["additive_recipe_htm"] = sum(algorithm.htm_length for algorithm in chosen)
        metrics["physical_htm"] = len(word.split())
        metrics["recognition_components"] = len(indices)
        return result("ready", observation, (algorithm.id for algorithm in chosen), word, after)

    def apply_step(self, state, feature, **kwargs):
        """Plan and replay one correction; identical to :meth:`plan_step`."""
        return self.plan_step(state, feature, **kwargs)
