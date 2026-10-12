#!/usr/bin/env python3
"""Compile an anonymous four-slot orientation stage from one learned body.

The goal is zero U-edge flips, with the first two layers preserved at recipe
endpoints. Top edge identities and all top corner information are ignored.
All 62,208 valid first-two-layer-solved configurations are replayed.
"""

import argparse
from collections import defaultdict
from heapq import heappop, heappush
from itertools import permutations, product
import json
from pathlib import Path
from time import perf_counter

import bce_v2 as c


ALGORITHM = "F R U R' U' F'"
WORDS = {"U": "U", "U2": "U2", "U'": "U'", "A": ALGORITHM}
SLOTS = ("UR", "UF", "UL", "UB")


def parity(values):
    return sum(values[i] > values[j] for i in range(len(values))
               for j in range(i + 1, len(values))) % 2


def preserves_first_two_layers(state):
    return (state.corners[4:] == list(range(4, 8)) and state.twists[4:] == [0] * 4
            and state.edges[4:] == list(range(4, 12)) and state.flips[4:] == [0] * 8)


def transition(mask, effect):
    # Native cubie arrays use destination slots, unlike BlockAction's sources.
    return tuple(mask[effect.edges[slot]] ^ effect.flips[slot] for slot in range(4))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]
                        / "research-results/slot-orientation-stage-probe.json")
    args = parser.parse_args()
    started = perf_counter()
    effects = {name: c.State().apply(word) for name, word in WORDS.items()}
    if not all(preserves_first_two_layers(effect) for effect in effects.values()):
        raise AssertionError("a proposed macro does not preserve the previous goal")
    masks = tuple(mask for mask in product((0, 1), repeat=4) if sum(mask) % 2 == 0)
    reverse = defaultdict(list)
    for mask in masks:
        for name, effect in effects.items():
            target = transition(mask, effect)
            if target not in masks:
                raise AssertionError("macro leaves the abstract orientation orbit")
            reverse[target].append((mask, name, len(WORDS[name].split())))

    # Weighted reverse orbit search produces a goal-directed controller.
    goal = (0, 0, 0, 0)
    distances, recipes, heap = {goal: 0}, {goal: ()}, [(0, goal)]
    while heap:
        cost, target = heappop(heap)
        if cost != distances[target]:
            continue
        for source, name, weight in reverse[target]:
            candidate = cost + weight
            if candidate < distances.get(source, 10**9):
                distances[source] = candidate
                recipes[source] = (name,) + recipes[target]
                heappush(heap, (candidate, source))
    if set(recipes) != set(masks):
        raise AssertionError("the existing taught vocabulary cannot cover this stage")
    physical = {mask: " ".join(WORDS[name] for name in recipes[mask]) for mask in masks}

    # Group raw observations by U-turn shape, retaining the frame separately.
    families = {}
    for mask in masks:
        orbit, current = [], mask
        for _ in range(4):
            orbit.append(current)
            current = transition(current, effects["U"])
        families[mask] = min(orbit)

    # Every edge permutation receives an independent transition replay check.
    edge_orders = tuple(permutations(range(4)))
    transition_checks = 0
    for order in edge_orders:
        corners = [1, 0, 2, 3, 4, 5, 6, 7] if parity(order) else list(range(8))
        for mask in masks:
            state = c.State.from_cubies(corners=corners, twists=[0] * 8,
                edges=list(order) + list(range(4, 12)), flips=list(mask) + [0] * 8)
            for name, word in WORDS.items():
                after = state.apply(word)
                if (tuple(after.flips[:4]) != transition(mask, effects[name])
                        or not preserves_first_two_layers(after)):
                    raise AssertionError("hidden identities alter the abstract transition")
                transition_checks += 1

    # Exhaustive hidden-state validation, without enumerating the full cube.
    policy_checks = 0
    for corner_order in permutations(range(4)):
        for edge_order in edge_orders:
            if parity(corner_order) != parity(edge_order):
                continue
            for first_three in product(range(3), repeat=3):
                twists = list(first_three) + [(-sum(first_three)) % 3] + [0] * 4
                for mask in masks:
                    state = c.State.from_cubies(
                        corners=list(corner_order) + list(range(4, 8)), twists=twists,
                        edges=list(edge_order) + list(range(4, 12)), flips=list(mask) + [0] * 8)
                    if state.scramble is not None:
                        raise AssertionError("a validation input retained move history")
                    after = state.apply(physical[mask])
                    if any(after.flips) or not preserves_first_two_layers(after):
                        raise AssertionError("anonymous-slot correction failed physical replay")
                    policy_checks += 1
    if policy_checks != 62208:
        raise AssertionError("last-layer configuration count changed")

    cases = [{"mask": "".join(map(str, mask)), "flipped_slots":
              [slot for slot, phase in zip(SLOTS, mask) if phase],
              "rotation_family": "".join(map(str, families[mask])),
              "recipe": list(recipes[mask]), "turn_sequence": physical[mask],
              "htm": len(physical[mask].split()),
              "transitions": {name: "".join(map(str, transition(mask, effect)))
                              for name, effect in effects.items()}}
             for mask in masks]
    record = {
        "format": "bce-v2-slot-orientation-stage-probe", "version": 1,
        "scope": "one ordinary-cube stage after solving the first two layers",
        "goal": "all U-edge slot phases zero; top identities and corners ignored",
        "slots": list(SLOTS), "learned_body": ALGORITHM, "learned_long_body_count": 1,
        "macro_moves": WORDS, "algorithm_inverse_used": False,
        "observation_count": len(masks), "rotation_family_count": len(set(families.values())),
        "mean_stage_htm": sum(case["htm"] for case in cases) / len(cases),
        "worst_stage_htm": max(case["htm"] for case in cases),
        "optimality_scope": "shortest additive paths in the declared four-macro graph",
        "transition_replays": transition_checks, "complete_hidden_state_replays": policy_checks,
        "all_prior_goals_preserved": True, "all_target_goals_achieved": True,
        "whole_cube_solved_claim": False, "production_integration": False,
        "wall_seconds": perf_counter() - started, "cases": cases,
    }
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in record.items() if key not in ("cases", "macro_moves")}))


if __name__ == "__main__":
    main()
