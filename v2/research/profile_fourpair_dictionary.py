#!/usr/bin/env python3
"""Bounded FourPair dictionary-only timing and optional call profiling.

Default budgets reproduce template preparation's dictionary settings. Optional
compact alphabets and caches are runtime research experiments. The notebook
is parsed for its bandage, never executed. No plotting or group enumeration.
"""

import argparse
import cProfile
from dataclasses import replace
from pathlib import Path
import pstats

import bce_v2 as c
from bce_v2.isotropy import LoopGenerators
import bce_v2.symbolic_dictionary as sd

from profile_fourpair_common import MoveReads, analysis_record, hoisted_validate, save, timed


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=90)
    parser.add_argument('--short-loops', type=int, help='use the reduced basis plus this many cheap originals')
    parser.add_argument('--cache', action='store_true')
    parser.add_argument('--hoist', action='store_true')
    parser.add_argument('--no-profile', action='store_true')
    parser.add_argument('--output', type=Path, default=base / 'research-results/fourpair-dictionary-performance.json')
    args = parser.parse_args()
    if args.seconds <= 0 or (args.short_loops is not None and args.short_loops < 0):
        parser.error('time bound must be positive; short-loop count must be nonnegative')
    report = {'format': 'bce-v2-fourpair-dictionary-performance', 'version': 1, 'measurements': [],
              'scope': 'dictionary discovery and validation only; no planner, templates or graph',
              'settings': {'short_loops': args.short_loops, 'native_word_cache': args.cache,
                           'signature_hoist': args.hoist, 'cprofile': not args.no_profile}}
    original_validate = sd.SymbolicAlgorithmDictionary.validate
    captured = {}
    with MoveReads() as reads:
        analysis = analysis_record(report, args.output, reads, args.seconds)
        selected_analysis = analysis
        if args.short_loops is not None:
            sources = {g.id: g for g in (*analysis.loops.generators[:args.short_loops], *analysis.generators)}
            selected = tuple(sorted(sources.values(), key=lambda g: (g.htm_length, g.qtm_length, g.id)))
            loops = LoopGenerators(analysis.loops._native)
            object.__setattr__(loops, '_generators', selected)
            object.__setattr__(loops, '_block_inventory', analysis.block_inventory)
            selected_analysis = replace(analysis, loops=loops)
        report['discovery_generator_count'] = len(selected_analysis.loops.generators)
        validator = hoisted_validate() if args.hoist else original_validate

        def watch_validate(dictionary, *positional, **keywords):
            captured['dictionary'] = dictionary
            report['validation_entered'] = True
            report['dictionary_summary'] = dictionary.metadata
            return validator(dictionary, *positional, **keywords)

        reads.cached = args.cache
        sd.SymbolicAlgorithmDictionary.validate = watch_validate
        profiler = cProfile.Profile()

        def discover():
            if not args.no_profile:
                profiler.enable()
            try:
                return c.discover_symbolic_dictionary(selected_analysis, max_setup_words=384,
                                                      timeout=args.seconds*.9)
            finally:
                profiler.disable()

        try:
            dictionary = timed(report, args.output, reads, 'dictionary_discovery_and_validation', discover, args.seconds)
        finally:
            sd.SymbolicAlgorithmDictionary.validate = original_validate
        if dictionary is not None:
            report['dictionary_summary'] = dictionary.metadata
            report['validation_completed'] = True
        if not args.no_profile:
            stats = pstats.Stats(profiler).stats
            report['profile_top_cumulative'] = [
                {'file': str(Path(key[0]).relative_to(base.parent)) if str(key[0]).startswith(str(base.parent)) else key[0],
                 'line': key[1], 'function': key[2], 'primitive_calls': value[0], 'total_calls': value[1],
                 'self_seconds': value[2], 'cumulative_seconds': value[3]}
                for key, value in sorted(stats.items(), key=lambda item: item[1][3], reverse=True)[:35]]
        report.setdefault('validation_entered', False)
        save(report, args.output)


if __name__ == '__main__':
    main()
