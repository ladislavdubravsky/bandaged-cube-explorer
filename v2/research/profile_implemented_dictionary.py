#!/usr/bin/env python3
"""Measure production bounded dictionary discovery without runtime patches."""

import argparse
import json
from pathlib import Path
import signal
from time import perf_counter

import bce_v2 as c

from profile_symbolic_basis import bandage_from_notebook


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--puzzle', default='FourPair')
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--output', type=Path,
                        default=base / 'research-results/staged-performance-implementation-dictionary.json')
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('seconds must be positive')
    bandage = bandage_from_notebook(base / 'examples' / (args.puzzle + '.ipynb'))
    settings = dict(max_candidates=12000, rounds=4, max_seed_loops=32,
                    max_original_loops=32, max_algorithms=1024, max_setup_depth=2,
                    max_setup_words=384, max_conjugates=12000,
                    max_htm_length=80, max_expanded_moves=400)
    record = dict(format='bce-v2-implemented-dictionary-performance', version=1,
                  puzzle=args.puzzle, settings=settings, budget_seconds=args.seconds,
                  scope='production dictionary only; no planner, repertoire or graph rendering',
                  runtime_patches=False, measurements=[])

    def expired(*_):
        raise TimeoutError('production dictionary probe wall-clock bound expired')

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(args.seconds)
    try:
        start = perf_counter()
        analysis = c.analyze_isotropy(bandage, timeout=min(30, args.seconds))
        record['measurements'].append(dict(phase='analysis', status='completed',
                                           wall_seconds=perf_counter() - start))
        record.update(group_order=analysis.group_order,
                      original_loop_count=len(analysis.loops),
                      algebra_basis_count=len(analysis.generators))
        start = perf_counter()
        dictionary = c.discover_symbolic_dictionary(analysis, timeout=min(60, args.seconds), **settings)
        record['measurements'].append(dict(phase='dictionary', status='completed',
                                           wall_seconds=perf_counter() - start))
        record['dictionary'] = dictionary.metadata
        start = perf_counter()
        dictionary.validate()
        record['measurements'].append(dict(phase='repeat_validation', status='completed',
                                           wall_seconds=perf_counter() - start))
        record['status'] = 'completed'
    except Exception as error:
        record.update(status='error', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
