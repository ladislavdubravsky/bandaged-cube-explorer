#!/usr/bin/env python3
"""Bounded complete FourPair method, repertoire and replay on compact alphabets.

The selected alphabet retains legal original IDs. The resulting method is
independently certified against every omitted native loop. These baseline
physical words are completeness controls, not algorithm-quality improvements.
"""

import argparse
from dataclasses import replace
from pathlib import Path

import bce_v2 as c
from bce_v2.human_methods import _validate_method
from bce_v2.isotropy import LoopGenerators

from profile_fourpair_common import MoveReads, analysis_record, save, timed


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--short-loops', type=int, action='append',
                        help='add this many cheap originals to the certified reduced basis; repeat for comparison')
    parser.add_argument('--seconds', type=float, default=45)
    parser.add_argument('--include-original', action='store_true', help='also run the unchanged full-alphabet baseline')
    parser.add_argument('--output', type=Path, default=base / 'research-results/fourpair-performance.json')
    args = parser.parse_args()
    counts = args.short_loops if args.short_loops is not None else [0, 32]
    if args.seconds <= 0 or any(count < 0 for count in counts):
        parser.error('time bound must be positive; short-loop counts must be nonnegative')
    report = {'format': 'bce-v2-fourpair-method-performance', 'version': 1, 'measurements': [],
              'scope': 'complete certified baseline, minimal template compression and one legal reference scramble',
              'quality_claim': 'no word-quality search; costs are exact additive before stage boundary cancellation'}
    with MoveReads() as reads:
        analysis = analysis_record(report, args.output, reads, args.seconds)
        if args.include_original:
            timed(report, args.output, reads, 'fixed_full_block_synthesis_original',
                  lambda: c.synthesize_human_method(analysis, backend='symbolic',
                      strategy='fully_solve_each_block', timeout=args.seconds*.9), args.seconds)
        reads.cached = True
        for count in counts:
            loops = LoopGenerators(analysis.loops._native)
            sources = {g.id: g for g in (*analysis.loops.generators[:count], *analysis.generators)}
            selected = tuple(sorted(sources.values(), key=lambda g: (g.htm_length, g.qtm_length, g.id)))
            object.__setattr__(loops, '_generators', selected)
            object.__setattr__(loops, '_block_inventory', analysis.block_inventory)
            reduced = replace(analysis, loops=loops)
            label = str(len(selected)) + '_generators'
            baseline = timed(report, args.output, reads, 'fixed_full_block_synthesis_'+label,
                lambda: c.synthesize_human_method(reduced, backend='symbolic',
                    strategy='fully_solve_each_block', timeout=args.seconds*.9), args.seconds)
            if baseline is None:
                continue
            certified = timed(report, args.output, reads, 'certify_against_all_originals_'+label,
                              lambda: _validate_method(baseline, complete_loops=analysis.loops), args.seconds)
            report['quality_'+label] = {'costs': baseline.additive_costs(),
                'stage_count': len(baseline.stages), 'algorithm_count': len(baseline.algorithms),
                'case_count_sum': sum(s.case_count for s in baseline.stages),
                'all_original_generator_memberships_checked': len(analysis.loops.generators),
                'full_original_certificate_completed': certified is not None}
            repertoire = timed(report, args.output, reads, 'minimal_template_repertoire_'+label,
                lambda: c.template_human_repertoire(baseline, backend='symbolic', max_trials=0,
                    chunk_options={'max_chunks': 0, 'max_candidates': 0}), args.seconds)
            if repertoire is not None:
                report['repertoire_'+label] = repertoire.metadata['selected_metrics']
                state = c.State(analysis.loops.root_shape)
                for g in analysis.generators:
                    state = state.apply(g.turn_sequence)
                replay = timed(report, args.output, reads, 'legal_replay_'+label,
                               lambda: repertoire.apply(state), args.seconds)
                report['legal_replay_solved_'+label] = replay is not None and replay.state.is_solved
            save(report, args.output)


if __name__ == '__main__':
    main()
