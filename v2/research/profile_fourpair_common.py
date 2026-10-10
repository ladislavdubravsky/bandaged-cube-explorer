"""Shared instrumentation for the bounded FourPair research probes.

All optimizations are scoped to the probe process. Production code is unchanged.
"""

from collections import Counter
import inspect
import json
from pathlib import Path
import resource
import signal
import textwrap
from time import perf_counter

import bce_v2 as c
from bce_v2.isotropy import LoopGenerator
import bce_v2.symbolic_dictionary as sd

from profile_symbolic_basis import bandage_from_notebook


class Deadline(Exception):
    pass


class MoveReads:
    """Count and optionally memoize immutable native loop witness strings."""

    def __init__(self):
        self.original = LoopGenerator.moves
        self.counts = Counter()
        self.cache = {}
        self.cached = False

    def __enter__(self):
        def moves(generator):
            self.counts['property_reads'] += 1
            key = (id(generator._owner), generator.id)
            if self.cached and key in self.cache:
                self.counts['cache_hits'] += 1
                return self.cache[key][1]
            # The production descriptor is now cached_property. Invoke that
            # descriptor directly so instrumentation retains its cache; old
            # property-based revisions remain usable for historical probes.
            if hasattr(self.original, 'func'):
                if self.original.attrname in generator.__dict__:
                    self.counts['production_cache_hits'] += 1
                else:
                    self.counts['native_reads'] += 1
                word = self.original.__get__(generator, type(generator))
            else:
                self.counts['native_reads'] += 1
                word = self.original.fget(generator)
            if self.cached:
                # Retain owners so object IDs cannot be reused during the run.
                self.cache[key] = (generator._owner, word)
            return word
        LoopGenerator.moves = property(moves)
        return self

    def __exit__(self, *_):
        LoopGenerator.moves = self.original


def save(record, path):
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


def timed(record, path, reads, operation, function, seconds):
    before_self = resource.getrusage(resource.RUSAGE_SELF)
    before_child = resource.getrusage(resource.RUSAGE_CHILDREN)
    reads.counts.clear()
    start = perf_counter()
    row = {'operation': operation, 'budget_seconds': seconds}
    result = None

    def expired(*_):
        raise Deadline('external wall-clock research budget expired')

    handler = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        result = function()
        row['status'] = 'completed'
    except Deadline:
        row['status'] = 'external_cutoff'
    except Exception as error:
        row.update(status='error', error=f'{type(error).__name__}: {error}')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)
        own = resource.getrusage(resource.RUSAGE_SELF)
        child = resource.getrusage(resource.RUSAGE_CHILDREN)
        row.update(wall_seconds=perf_counter()-start,
                   self_cpu_seconds=own.ru_utime+own.ru_stime-before_self.ru_utime-before_self.ru_stime,
                   child_cpu_seconds=max(0.0, child.ru_utime+child.ru_stime-before_child.ru_utime-before_child.ru_stime),
                   moves=dict(reads.counts))
        record['measurements'].append(row)
        save(record, path)
        print(json.dumps(row), flush=True)
    return result


def analysis_record(record, path, reads, seconds):
    base = Path(__file__).resolve().parents[1]
    bandage = bandage_from_notebook(base / 'examples/FourPair.ipynb')
    analysis = timed(record, path, reads, 'analyze_isotropy',
                     lambda: c.analyze_isotropy(bandage, timeout=seconds), seconds)
    if analysis is None:
        raise RuntimeError('FourPair analysis did not complete; see measurement')
    record.update(puzzle='FourPair', bandage=bandage, group_order=analysis.group_order,
                  shape_count=analysis.loops.shape_count,
                  original_generator_count=len(analysis.loops.generators),
                  reduced_generator_ids=list(analysis.generator_ids),
                  inventory_counts=dict(Counter(b.kind+':'+b.type for b in analysis.block_inventory.blocks)))
    save(record, path)
    return analysis


def hoisted_validate():
    """Retain every signature/replay check; share immutable alphabet signatures."""
    source = textwrap.dedent(inspect.getsource(sd.SymbolicAlgorithmDictionary.validate))
    old = 'signatures = lambda records: tuple((g.id, g.permutation, g.moves) for g in records)'
    replacement = ('signature_cache = {}\n'
        '    def signatures(records):\n'
        '        key = id(records)\n'
        '        if key not in signature_cache:\n'
        '            signature_cache[key] = (records, tuple((g.id, g.permutation, g.moves) for g in records))\n'
        '        return signature_cache[key][1]')
    if source.count(old) != 1:
        if 'signature_cache' in source:
            # Production has incorporated the same hoist (and stronger
            # immutable-owner proof reuse); do not replace it with an older
            # validator merely to keep a historical experiment flag working.
            return sd.SymbolicAlgorithmDictionary.validate
        raise RuntimeError('validator source changed; review the runtime hoist experiment')
    namespace = dict(sd.__dict__)
    exec(source.replace(old, replacement), namespace)
    return namespace['validate']
