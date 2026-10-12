#!/usr/bin/env python3
"""Time complete palette policies without adding notebook diagnostics."""

from __future__ import annotations

import argparse
import cProfile
import json
from time import perf_counter

import bce_v2 as c
from bce_v2.algorithm_profiles import discover_palette_profiles
from bce_v2.automatic_palette import automatic_algorithm_palette
from bce_v2.coarse_search import _features
from bce_v2.palette_policies import stage_policy_frontier
from bce_v2.symbolic_chains import plan_symbolic_stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="Alcatraz")
    parser.add_argument("--profile", help="Optional cProfile output file")
    parser.add_argument("--certify", action="store_true", help="Also time portable symbolic feature plans")
    arguments = parser.parse_args()
    started = perf_counter()
    analysis = c.analyze_isotropy(c.fixture(arguments.fixture), timeout=90)
    ambient = c.plan_human_stages(analysis, backend="symbolic", timeout=90)
    palette = automatic_algorithm_palette(analysis).palette.with_derived_actions()
    profiles = discover_palette_profiles(analysis.block_inventory, palette, ambient_group=ambient.group)
    print(json.dumps({"preparation_seconds": perf_counter()-started,
                      "recipes": len(palette.recipes), "bodies": len(palette.bodies)}), flush=True)
    profiler = cProfile.Profile()
    profiler.enable()
    finish = tuple(c.BlockFeature("solve_block", block.cells)
                   for block in analysis.block_inventory.blocks if block.corners or block.edges)
    for feature in _features(analysis.block_inventory, ambient.group, palette, profiles, 8, 16):
        started = perf_counter()
        policies = stage_policy_frontier(analysis.block_inventory, ambient.group, feature, palette,
            max_observations=128, max_taught_bodies=7, max_policy_labels=128, max_candidates=8)
        print(json.dumps({"feature": feature.to_dict(), "seconds": perf_counter()-started,
                          "status": policies.status, "observations": len(policies.observations),
                          "policies": len(policies.policies), "subsets": policies.evaluated_subsets}), flush=True)
        if arguments.certify and policies.policies:
            print(json.dumps({"certification_started": feature.to_dict()}), flush=True)
            started = perf_counter()
            plan = plan_symbolic_stages(analysis, strategy="manual", features=(feature, *finish),
                                        ambient_plan=ambient, timeout=90)
            print(json.dumps({"certification_seconds": perf_counter()-started,
                              "stage_orders": [[stage.order_before, stage.order_after]
                                               for stage in plan.stages]}), flush=True)
    profiler.disable()
    if arguments.profile:
        profiler.dump_stats(arguments.profile)


if __name__ == "__main__":
    main()
