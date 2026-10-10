#!/usr/bin/env python3
"""Compare identical FourPair dictionary validation with runtime-only caches.

Run with v2/.venv/bin/python. The dictionary contains real original-loop
algorithms and the entire 4,968-root alphabet. Every version retains physical
replay, original expression and exact coordinate-span checks.
"""

import argparse
import json
from pathlib import Path

from bce_v2.gap_backend import analyze_generators
from bce_v2.loop_algorithms import AlgorithmLibrary, LoopExpression
import bce_v2.symbolic_dictionary as sd

from profile_fourpair_common import MoveReads, analysis_record, hoisted_validate, save, timed


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--algorithms', type=int, default=16)
    parser.add_argument('--seconds', type=float, default=45)
    parser.add_argument('--output', type=Path, default=base / 'research-results/fourpair-validation-performance.json')
    args = parser.parse_args()
    if args.algorithms < 1 or args.seconds <= 0:
        parser.error('algorithm count and time bound must be positive')
    report = {'format': 'bce-v2-fourpair-validation-performance', 'version': 1,
              'measurements': [], 'scope': 'identical dictionary; runtime signature hoist and native-word memo only'}
    original_validate = sd.SymbolicAlgorithmDictionary.validate
    with MoveReads() as reads:
        analysis = analysis_record(report, args.output, reads, args.seconds)
        builder = AlgorithmLibrary(analysis.loops, (), (), ())
        algorithms = tuple(builder.build_algorithm(LoopExpression.loop(g.id), max_expanded_moves=960)
                           for g in analysis.loops.generators[:args.algorithms])
        basis, span, _, independent = sd._basis(algorithms, analysis.block_inventory)
        projections = [tuple(g.block_action.destinations) +
                       tuple(range(len(analysis.block_inventory.blocks), 48)) for g in analysis.generators]
        quotient = analyze_generators(projections, timeout=args.seconds, prune=False).group_order
        target = analysis.group_order // quotient
        metadata = dict(settings={'max_htm_length': 960, 'max_expanded_moves': 960},
                        orientation_span_order=span, orientation_basis_independent=independent,
                        orientation_complete=span == target, orientation_target_order=target)
        dictionary = sd.SymbolicAlgorithmDictionary(analysis.loops, algorithms, basis, json.dumps(metadata))
        report['validation_fixture'] = {'algorithm_count': len(algorithms), 'quotient_order': quotient,
            'orientation_target_order': target, 'same_dictionary_all_checks_retained': True,
            'theoretical_signature_move_reads': 2*(len(algorithms)+1)*len(analysis.loops.generators)}
        try:
            timed(report, args.output, reads, 'original_validation', dictionary.validate, args.seconds)
            sd.SymbolicAlgorithmDictionary.validate = hoisted_validate()
            timed(report, args.output, reads, 'hoisted_signature_validation', dictionary.validate, args.seconds)
            reads.cached = True
            reads.cache.clear()
            timed(report, args.output, reads, 'hoisted_and_cached_validation_cold', dictionary.validate, args.seconds)
            timed(report, args.output, reads, 'hoisted_and_cached_validation_warm', dictionary.validate, args.seconds)
        finally:
            sd.SymbolicAlgorithmDictionary.validate = original_validate
    save(report, args.output)


if __name__ == '__main__':
    main()
