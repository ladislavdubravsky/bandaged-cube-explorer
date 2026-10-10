#!/usr/bin/env python3
"""Bounded symbolic stage planning with complete versus reduced root libraries.

Run with v2/.venv/bin/python. A temporary loop wrapper exposes the reduced
original witnesses with their original IDs. Production code is unchanged.
The reduced portable group certificate then checks all omitted native loops.
This measures planning, not dictionary quality or physical correction length.
"""

import argparse
import ast
from dataclasses import replace
import json
import os
from pathlib import Path
import resource
import signal
from time import perf_counter

import bce_v2 as c
from bce_v2.loop_algorithms import _loops_from_records
from bce_v2.symbolic_chains import plan_symbolic_stages


class Deadline(Exception):
    pass


def cpu():
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime, child.ru_utime + child.ru_stime


def timing(before, start):
    after = cpu()
    return {'wall_seconds': perf_counter() - start,
            'self_cpu_seconds': after[0] - before[0],
            'child_cpu_seconds': after[1] - before[1]}


def bandage_from_notebook(path):
    for cell in json.loads(path.read_text())['cells']:
        if cell['cell_type'] != 'code':
            continue
        for node in ast.parse(''.join(cell['source'])).body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'bandage'
                    for target in node.targets):
                return ast.literal_eval(node.value)
    raise ValueError('notebook has no literal bandage assignment')


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--puzzle', choices=('BeltRoad', 'MostSignaturesCube', 'FourPair'), default='FourPair')
    parser.add_argument('--basis', choices=('both', 'original', 'reduced'), default='both')
    parser.add_argument('--gap-seconds', type=float, default=60)
    parser.add_argument('--python-seconds', type=float, default=90)
    parser.add_argument('--output', type=Path, default=base / 'research-results/symbolic-basis-performance.json')
    args = parser.parse_args()
    if args.gap_seconds <= 0 or args.python_seconds <= 0:
        parser.error('time bounds must be positive')
    bandage = bandage_from_notebook(base / 'examples' / (args.puzzle + '.ipynb'))
    before, start = cpu(), perf_counter()
    analysis = c.analyze_isotropy(bandage, timeout=args.gap_seconds)
    analysis_timing = timing(before, start)
    originals, reduced = analysis.loops.generators, analysis.generators
    record = {
        'format': 'bce-v2-symbolic-basis-performance', 'version': 1,
        'puzzle': args.puzzle, 'bandage': bandage, 'analysis': analysis_timing,
        'group_order': analysis.group_order, 'shape_count': analysis.loops.shape_count,
        'arc_count': analysis.loops.arc_count, 'original_loop_count': len(originals),
        'reduced_loop_count': len(reduced), 'reduced_ids': list(analysis.generator_ids),
        'gap_timeout_seconds': args.gap_seconds, 'python_deadline_seconds': args.python_seconds,
        'cpu_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'scope': 'uncprofiled symbolic fully-solve baseline planning only; excludes dictionary, compilation and rendering',
        'measurements': [],
    }

    def save():
        args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')

    print(json.dumps(record), flush=True)
    save()
    reduced_loops = _loops_from_records(reduced)
    object.__setattr__(reduced_loops, '_generators', reduced)
    object.__setattr__(reduced_loops, '_block_inventory', analysis.block_inventory)
    reduced_analysis = replace(analysis, loops=reduced_loops)
    plans = {}

    def expired(*_):
        raise Deadline('Python symbolic planning exceeded wall-time bound')

    previous_handler = signal.signal(signal.SIGALRM, expired)
    try:
        for label, selected in [('reduced', reduced_analysis), ('original', analysis)]:
            if args.basis != 'both' and args.basis != label:
                continue
            measurement = {'basis': label, 'input_generator_count': len(selected.loops.generators)}
            before, start = cpu(), perf_counter()
            try:
                signal.setitimer(signal.ITIMER_REAL, args.python_seconds)
                plan = plan_symbolic_stages(selected, strategy='fully_solve_each_block', timeout=args.gap_seconds)
                signal.setitimer(signal.ITIMER_REAL, 0)
                plans[label] = plan
                measurement.update(
                    status='completed', group_order=plan.group_order,
                    quotient_order=plan.quotient_order, kernel_order=plan.kernel_order,
                    terminal_order=plan.terminal_order, stages=len(plan.stages),
                    cases=sum(stage.case_count for stage in plan.stages),
                    features=[(stage.feature.kind, list(stage.feature.cells), stage.case_count) for stage in plan.stages],
                    strong_generator_counts=[len(plan.group.strong_generators)] +
                        [len(stage.group_after.strong_generators) for stage in plan.stages])
            except Exception as error:
                measurement.update(status='error', error=type(error).__name__, message=str(error))
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                measurement.update(timing(before, start))
                record['measurements'].append(measurement)
                save()
                print(json.dumps(measurement), flush=True)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)
    if 'reduced' in plans:
        before, start = cpu(), perf_counter()
        complete_membership = all(generator.permutation in plans['reduced'].group for generator in originals)
        record['complete_loop_membership_verification'] = timing(before, start)
        record['reduced_certificate_covers_every_original_loop'] = complete_membership
        assert complete_membership
    if len(plans) == 2:
        record['same_group_orders'] = all(
            getattr(plans['reduced'], key) == getattr(plans['original'], key)
            for key in ('group_order', 'quotient_order', 'kernel_order', 'terminal_order'))
        record['same_features_and_case_counts'] = (
            record['measurements'][0]['features'] == record['measurements'][1]['features'])
        assert record['same_group_orders'] and record['same_features_and_case_counts']
    save()
    print('Saved', args.output, flush=True)


if __name__ == '__main__':
    main()
