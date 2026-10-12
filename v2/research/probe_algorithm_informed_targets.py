#!/usr/bin/env python3
"""Derive candidate observations from a small palette's exact cubie actions.

The illustrative palette is the previous orientation probe's A and U turns.
No slot region is supplied: permutation orbits and common fixed slots are
recovered from those actions. Coverage is checked against every observation
possible after solving the first two layers, not just the palette's orbit.
The saved guide's seven long bodies receive separate preservation profiles.
"""

import argparse
from collections import defaultdict
from hashlib import sha256
from heapq import heappop, heappush
from itertools import permutations, product
import json
from pathlib import Path

import bce_v2 as c
from probe_slot_orientation_stage import WORDS, parity, preserves_first_two_layers


SLOTS = {
    "corners": ("UFR", "UFL", "UBL", "UBR", "DFR", "DFL", "DBL", "DBR"),
    "edges": ("UR", "UF", "UL", "UB", "DR", "DF", "DL", "DB", "FR", "FL", "BL", "BR"),
}
PHASES = {"corners": ("twists", 3), "edges": ("flips", 2)}


def slot_orbits(effects, kind):
    unseen, result = set(range(len(SLOTS[kind]))), []
    while unseen:
        orbit, pending = set(), [min(unseen)]
        while pending:
            slot = pending.pop()
            if slot in orbit:
                continue
            orbit.add(slot)
            pending.extend(getattr(effect, kind)[slot] for effect in effects.values())
        unseen.difference_update(orbit)
        result.append(tuple(sorted(orbit)))
    return result


def action_profile(effect):
    profile = {}
    for kind, slots in SLOTS.items():
        phase_name, modulus = PHASES[kind]
        placement, phase = getattr(effect, kind), getattr(effect, phase_name)
        profile[kind] = {
            "destination_sources": dict(zip(slots, (slots[source] for source in placement))),
            "phase_increments": dict(zip(slots, phase)),
            "phase_modulus": modulus,
            "fully_fixed_slots": [slot for index, slot in enumerate(slots)
                                  if placement[index] == index and phase[index] == 0],
            "zero_phase_goal_preserved_globally": not any(phase),
            "placement_goal_preserved_globally": placement == list(range(len(slots))),
        }
    return profile


def target_probe(kind, region, attribute, effects):
    phase_name, modulus = PHASES[kind]
    local = {slot: index for index, slot in enumerate(region)}
    if attribute == "phase":
        observations = tuple(mask for mask in product(range(modulus), repeat=len(region))
                             if sum(mask) % modulus == 0)
        goal = (0,) * len(region)
    else:
        observations = tuple(permutations(range(len(region))))
        goal = tuple(range(len(region)))

    def transition(observation, effect):
        sources, phases = getattr(effect, kind), getattr(effect, phase_name)
        return tuple((observation[local[sources[slot]]] + phases[slot]) % modulus
                     if attribute == "phase" else observation[local[sources[slot]]]
                     for slot in region)

    reverse, domain = defaultdict(list), set(observations)
    for observation in observations:
        for name, effect in effects.items():
            target = transition(observation, effect)
            if target not in domain:
                raise AssertionError("candidate observation is not closed")
            reverse[target].append((observation, name, len(WORDS[name].split())))
    distances, recipes, heap = {goal: 0}, {goal: ()}, [(0, goal)]
    while heap:
        cost, target = heappop(heap)
        if distances[target] != cost:
            continue
        for source, name, weight in reverse[target]:
            candidate = cost + weight
            if candidate < distances.get(source, 10**9):
                distances[source] = candidate
                recipes[source] = (name,) + recipes[target]
                heappush(heap, (candidate, source))

    # Independent native witnesses for every observation, including failures.
    transition_checks, policy_checks = 0, 0
    for observation in observations:
        arrays = dict(corners=list(range(8)), twists=[0] * 8,
                      edges=list(range(12)), flips=[0] * 12)
        if attribute == "phase":
            arrays[phase_name][:4] = observation
        else:
            arrays[kind][:4] = observation
            if parity(observation):
                other = "edges" if kind == "corners" else "corners"
                arrays[other][:2] = [1, 0]
        state = c.State.from_cubies(**arrays)
        if state.scramble is not None or not preserves_first_two_layers(state):
            raise AssertionError("invalid history-free witness")
        for name, effect in effects.items():
            after = state.apply(WORDS[name])
            actual = getattr(after, phase_name if attribute == "phase" else kind)
            if tuple(actual[slot] for slot in region) != transition(observation, effect):
                raise AssertionError("native transition does not match observation action")
            transition_checks += 1
        if observation in recipes:
            after = state.apply(" ".join(WORDS[name] for name in recipes[observation]))
            actual = getattr(after, phase_name if attribute == "phase" else kind)
            if (tuple(actual[slot] for slot in region) != goal
                    or not preserves_first_two_layers(after)):
                raise AssertionError("recipe failed native replay")
            policy_checks += 1

    complete = len(distances) == len(observations)
    return {
        "kind": kind, "slots": [SLOTS[kind][slot] for slot in region],
        "attribute": attribute, "full_current_group_observation_count": len(observations),
        "covered_observation_count": len(distances), "complete_stage": complete,
        "mean_stage_htm": sum(distances.values()) / len(observations) if complete else None,
        "worst_stage_htm": max(distances.values()) if complete else None,
        "conditional_covered_mean_htm": sum(distances.values()) / len(distances),
        "transition_replays": transition_checks, "policy_replays": policy_checks,
        "cases": [{"observation": list(observation), "covered": observation in recipes,
                   "recipe": list(recipes[observation]) if observation in recipes else None,
                   "htm": distances.get(observation)} for observation in observations],
    }


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=base / "research-results/algorithm-informed-targets-probe.json")
    args = parser.parse_args()
    effects = {name: c.State().apply(word) for name, word in WORDS.items()}
    orbits = {kind: slot_orbits(effects, kind) for kind in SLOTS}
    profiles = {name: action_profile(effect) for name, effect in effects.items()}
    common_fixed = {kind: [slot for slot in SLOTS[kind] if all(
        slot in profile[kind]["fully_fixed_slots"] for profile in profiles.values())]
                    for kind in SLOTS}
    candidates = []
    for kind in SLOTS:
        active = [orbit for orbit in orbits[kind] if len(orbit) > 1 or any(
            getattr(effect, PHASES[kind][0])[orbit[0]] for effect in effects.values())]
        if len(active) != 1 or len(active[0]) != 4 or active[0] != tuple(range(4)):
            raise AssertionError("the inferred palette region changed")
        for attribute in ("phase", "placement"):
            candidates.append(target_probe(kind, active[0], attribute, effects))
    lookup = {(row["kind"], row["attribute"]): row for row in candidates}
    if (lookup["edges", "phase"]["mean_stage_htm"] != 10.375
            or lookup["corners", "placement"]["covered_observation_count"] != 8
            or lookup["corners", "placement"]["full_current_group_observation_count"] != 24):
        raise AssertionError("independent orientation result or coverage contrast changed")

    guide_path = base / "research-results/unbandaged3x3-current-guide-audit.json"
    guide = json.loads(guide_path.read_text())
    guide_bodies = [body for body in guide["displayed_nontrivial_macros"] if body["htm"] > 4]
    guide_profiles = [{**body, "action": action_profile(c.State().apply(body["turn_sequence"]))}
                      for body in guide_bodies]
    if len(guide_profiles) != 7:
        raise AssertionError("the recorded taught-body budget changed")
    record = {
        "format": "bce-v2-algorithm-informed-targets-probe", "version": 1,
        "scope": "attribute proposals and isolated-stage coverage, not a full method",
        "illustrative_palette": WORDS,
        "palette_is_saved_guide_vocabulary": False,
        "current_group": "ordinary cube with first two layers fixed",
        "current_group_order": 62208,
        "inferred_slot_orbits": {kind: [[SLOTS[kind][slot] for slot in orbit]
                                      for orbit in rows] for kind, rows in orbits.items()},
        "inferred_common_fully_fixed_slots": common_fixed,
        "illustrative_algorithm_profiles": profiles, "candidate_targets": candidates,
        "saved_guide_profiles": guide_profiles,
        "saved_guide_profile_source": str(guide_path.relative_to(base.parent)),
        "saved_guide_profile_source_sha256": sha256(guide_path.read_bytes()).hexdigest(),
        "saved_guide_notebook_sha256_at_audit": guide["source_sha256"],
        "native_transition_replays": sum(row["transition_replays"] for row in candidates),
        "native_policy_replays": sum(row["policy_replays"] for row in candidates),
        "optimality_scope": "additive shortest paths in the declared four-macro graph",
        "full_method_coverage_claim": False, "production_integration": False,
    }
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"common_fixed_slots": common_fixed, "candidates": [
        {key: value for key, value in row.items() if key != "cases"} for row in candidates],
        "saved_guide_long_body_count": len(guide_profiles)}))


if __name__ == "__main__":
    main()
