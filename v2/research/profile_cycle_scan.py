#!/usr/bin/env python3
"""Compare deterministic cycle decomposition without graph layout or rendering.

Run with v2/.venv/bin/python. CPU timings distinguish the quadratic repeated
minimum scan from an ordered linear scan. Both produce identical ordered cycles.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter, process_time

from bce_v2.graph_render import _cycles


def linear_cycles(permutation):
    visited = bytearray(len(permutation))
    result = []
    for first in range(len(permutation)):
        if visited[first]:
            continue
        cycle = []
        vertex = first
        while not visited[vertex]:
            visited[vertex] = 1
            cycle.append(vertex)
            vertex = permutation[vertex]
        result.append(cycle)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=(1000, 2000, 4000, 8000, 16000))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'research-results/graph-cycle-performance.json')
    args = parser.parse_args()
    if any(size <= 0 or size % 4 for size in args.sizes):
        parser.error('sizes must be positive multiples of four')
    records = []
    for size in args.sizes:
        permutations = {
            'identity': tuple(range(size)),
            'involution': tuple(i ^ 1 for i in range(size)),
            'four_cycles': tuple((i // 4) * 4 + (i + 1) % 4 for i in range(size)),
        }
        for kind, permutation in permutations.items():
            results = []
            row = {'size': size, 'kind': kind}
            for name, function in [('current', _cycles), ('linear', linear_cycles)]:
                start, cpu_start = perf_counter(), process_time()
                result = function(permutation)
                row[name + '_wall_seconds'] = perf_counter() - start
                row[name + '_cpu_seconds'] = process_time() - cpu_start
                results.append(result)
            assert results[0] == results[1]
            row['same_ordered_cycles'] = True
            row['cycle_count'] = len(results[0])
            records.append(row)
            print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps({
        'format': 'bce-v2-graph-cycle-performance', 'version': 1,
        'scope': 'Synthetic cycle permutations; exact ordered decomposition equivalence, no graph layout or rendering',
        'timing_note': 'CPU time is preferable when other experiments share a core',
        'measurements': records,
    }, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
