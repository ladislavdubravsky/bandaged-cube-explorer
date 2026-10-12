#!/usr/bin/env python3
"""A seeded four-stage ordinary-cube last-layer acceptance oracle.

This is an isolated research controller, not automatic method discovery.
The prescribed goals are edge orientation, corner orientation, corner
placement and edge placement, in that order, after the first two layers.
Four supplied long bodies plus U adjustments generate protected macros.
Every one of the 62,208 valid last-layer states is replayed physically.
"""

import argparse
from collections import defaultdict
from heapq import heappop, heappush
from itertools import permutations, product
import json
from pathlib import Path
from time import perf_counter

import bce_v2 as c
from probe_slot_orientation_stage import parity, preserves_first_two_layers


# The sequences occur on the Feliks Zemdegs / Andy Klise four-look sheet.
SOURCE = "https://www.cubeskills.com/uploads/pdf/tutorials/4-look-last-layer.pdf"
BODIES = {
    "EO": "F R U R' U' F'",
    "Sune": "R U R' U R U2 R'",
    "Tperm": "R U R' U' R' F R2 U' R' U' R U R' F'",
    "Ua": "R U' R U R U R U' R' U' R2",
}
ADJUSTMENTS = ("", "U", "U2", "U'")
ADJUSTMENT_INVERSES = ("", "U'", "U2", "U")
STAGES = (
    ("edge_orientation", "flips", 2),
    ("corner_orientation", "twists", 3),
    ("corner_placement", "corners", None),
    ("edge_placement", "edges", None),
)


def top_observation(state, attribute):
    return tuple(getattr(state, attribute)[:4])


def phase_transition(observation, effect, placements, phases, modulus):
    return tuple((observation[getattr(effect, placements)[slot]]
                  + getattr(effect, phases)[slot]) % modulus for slot in range(4))


def transition(observation, effect, attribute, modulus):
    if modulus:
        placements = "edges" if attribute == "flips" else "corners"
        return phase_transition(observation, effect, placements, attribute, modulus)
    return tuple(observation[getattr(effect, attribute)[slot]] for slot in range(4))


def protected(effect, stage_number):
    if not preserves_first_two_layers(effect):
        return False
    if stage_number >= 1 and any(effect.flips):
        return False
    if stage_number >= 2 and any(effect.twists):
        return False
    if stage_number >= 3 and effect.corners != list(range(8)):
        return False
    return True


def macros():
    result = {}
    for adjustment in ADJUSTMENTS[1:]:
        result[adjustment] = {"word": adjustment, "body": None, "setup": ""}
    # Build setup/body/undo BEFORE testing protection. At edge placement U
    # alone breaks corner placement, but each U^k Ua U^-k preserves it.
    for name, body in BODIES.items():
        for setup, undo in zip(ADJUSTMENTS, ADJUSTMENT_INVERSES):
            identifier = name if not setup else f"{setup} [{name}] {undo}"
            word = " ".join(part for part in (setup, body, undo) if part)
            result[identifier] = {"word": word, "body": name, "setup": setup}
    for entry in result.values():
        entry["effect"] = c.State().apply(entry["word"])
        entry["htm"] = len(entry["word"].split())
        if not preserves_first_two_layers(entry["effect"]):
            raise AssertionError("a supplied long body breaks the seeded F2L goal")
    return result


def witness(observation, attribute, modulus):
    arrays = dict(corners=list(range(8)), twists=[0] * 8,
                  edges=list(range(12)), flips=[0] * 12)
    arrays[attribute][:4] = observation
    if modulus is None and parity(observation):
        other = "edges" if attribute == "corners" else "corners"
        arrays[other][:2] = [1, 0]
    return c.State.from_cubies(**arrays)


def compile_stage(stage_number, macro_catalog):
    name, attribute, modulus = STAGES[stage_number]
    if modulus:
        observations = tuple(value for value in product(range(modulus), repeat=4)
                             if sum(value) % modulus == 0)
        goal = (0,) * 4
    else:
        observations = tuple(permutations(range(4)))
        if attribute == "edges":
            observations = tuple(value for value in observations if parity(value) == 0)
        goal = tuple(range(4))
    domain, reverse = set(observations), defaultdict(list)
    available = {key: entry for key, entry in macro_catalog.items()
                 if protected(entry["effect"], stage_number)}
    for value in observations:
        for identifier, entry in available.items():
            image = transition(value, entry["effect"], attribute, modulus)
            if image not in domain:
                raise AssertionError("protected macro leaves exact stage domain")
            reverse[image].append((value, identifier, entry["htm"]))
    distances, recipes, heap = {goal: 0}, {goal: ()}, [(0, goal)]
    while heap:
        cost, destination = heappop(heap)
        if distances[destination] != cost:
            continue
        for source, identifier, weight in reverse[destination]:
            candidate = cost + weight
            if candidate < distances.get(source, 10**9):
                distances[source] = candidate
                recipes[source] = (identifier,) + recipes[destination]
                heappush(heap, (candidate, source))
    if set(recipes) != domain:
        raise AssertionError(f"supplied palette does not cover {name}")
    words = {value: " ".join(available[key]["word"] for key in recipe)
             for value, recipe in recipes.items()}
    transition_checks = 0
    for value in observations:
        initial = witness(value, attribute, modulus)
        for identifier, entry in available.items():
            after = initial.apply(entry["word"])
            expected = transition(value, entry["effect"], attribute, modulus)
            if (top_observation(after, attribute) != expected
                    or not protected(after, stage_number)):
                raise AssertionError("native witness transition/protection mismatch")
            transition_checks += 1
        after = initial.apply(words[value])
        if top_observation(after, attribute) != goal:
            raise AssertionError("compiled stage recipe misses its goal")
    record = {
        "name": name, "observed_native_array": attribute,
        "observation_count": len(observations), "complete": True,
        "available_protected_macros": list(available),
        "protected_macro_count": len(available),
        "mean_additive_htm": sum(distances.values()) / len(observations),
        "worst_additive_htm": max(distances.values()),
        "transition_replays": transition_checks,
        "goal": list(goal),
        "cases": [{"observation": list(value), "recipe": list(recipes[value]),
                   "turn_sequence": words[value], "additive_htm": distances[value]}
                  for value in observations],
    }
    return record, recipes, words, distances


def last_layer_states():
    orders = tuple(permutations(range(4)))
    flips = tuple(mask for mask in product(range(2), repeat=4) if sum(mask) % 2 == 0)
    twists = tuple(tuple(first) + ((-sum(first)) % 3,)
                   for first in product(range(3), repeat=3))
    for corner_order in orders:
        for edge_order in orders:
            if parity(corner_order) != parity(edge_order):
                continue
            for twist in twists:
                for flip in flips:
                    yield c.State.from_cubies(
                        corners=list(corner_order) + list(range(4, 8)),
                        twists=list(twist) + [0] * 4,
                        edges=list(edge_order) + list(range(4, 12)),
                        flips=list(flip) + [0] * 8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]
                        / "research-results/standard-last-layer-oracle.json")
    args = parser.parse_args()
    started, macro_catalog = perf_counter(), macros()
    compiled = [compile_stage(index, macro_catalog) for index in range(4)]
    records = [row[0] for row in compiled]
    if [row["observation_count"] for row in records] != [8, 27, 24, 12]:
        raise AssertionError("raw last-layer goal domains changed")
    count, total_cost, worst_cost = 0, 0, 0
    stage_costs, stage_visits, used_bodies = [0] * 4, [defaultdict(int) for _ in range(4)], set()
    solved = c.State()
    for initial in last_layer_states():
        if initial.scramble is not None:
            raise AssertionError("validation input retained move history")
        current, cost = initial, 0
        for index, ((name, attribute, modulus), (_, recipes, words, distances)) in enumerate(
                zip(STAGES, compiled)):
            observation = top_observation(current, attribute)
            stage_visits[index][observation] += 1
            for identifier in recipes[observation]:
                if macro_catalog[identifier]["body"]:
                    used_bodies.add(macro_catalog[identifier]["body"])
            current = current.apply(words[observation])
            stage_costs[index] += distances[observation]
            cost += distances[observation]
            if not protected(current, index + 1):
                raise AssertionError("a stage fails its cumulative endpoint goals")
        if current != solved:
            raise AssertionError("four-stage last-layer controller fails physical replay")
        count += 1
        total_cost += cost
        worst_cost = max(worst_cost, cost)
    if count != 62208:
        raise AssertionError("exact last-layer state count changed")
    for index, record in enumerate(records):
        visits = stage_visits[index]
        if len(set(visits.values())) != 1:
            raise AssertionError("residual observation distribution is not uniform")
        record["complete_hidden_state_endpoint_replays"] = count
        record["native_replay_mean_additive_htm"] = stage_costs[index] / count
        record["states_per_observation_during_full_replay"] = next(iter(visits.values()))
        if record["mean_additive_htm"] != record["native_replay_mean_additive_htm"]:
            raise AssertionError("additive stage expectation differs from exhaustive replay")
    record = {
        "format": "bce-v2-standard-last-layer-oracle", "version": 1,
        "scope": "seeded ordinary 3x3 last layer after the first two layers are solved",
        "seeded_goals": [row[0] for row in STAGES],
        "seeded_regions": {"edges": ["UR", "UF", "UL", "UB"],
                           "corners": ["URF", "UFL", "ULB", "UBR"]},
        "goal_discovery_performed": False, "production_integration": False,
        "whole_scramble_method_claim": False, "comparison_to_production_method": None,
        "one_algorithm_per_look_claim": False,
        "inverse_body_variants_used": False,
        "physical_body_source": SOURCE, "supplied_long_bodies": BODIES,
        "supplied_long_body_count": len(BODIES), "used_long_body_count": len(used_bodies),
        "used_long_bodies": sorted(used_bodies),
        "short_adjustments": list(ADJUSTMENTS[1:]), "catalog_macro_count": len(macro_catalog),
        "protected_macros": {identifier: {key: value for key, value in entry.items()
                              if key != "effect"} for identifier, entry in macro_catalog.items()},
        "setup_undo_variants_built_before_protection_filter": True,
        "all_case_domains_complete": True, "all_cumulative_endpoint_goals_preserved": True,
        "complete_physical_state_replays": count, "all_complete_states_solved": True,
        "mean_last_layer_additive_htm": total_cost / count,
        "worst_last_layer_additive_htm": worst_cost,
        "optimality_scope": "each declared protected-macro graph, with additive HTM weights",
        "move_count_scope": "all face-turn tokens, including setups; no boundary cancellation",
        "stage_reports": records, "wall_seconds": perf_counter() - started,
    }
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in record.items()
                      if key not in ("stage_reports", "protected_macros", "supplied_long_bodies")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
