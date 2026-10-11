"""Discover exact familiar bodies at nearby shapes and transport them home.

The search visits shapes in shortest HTM setup order. Cached obstruction
masks test whole words, including powers, against the full partition with
core bonds. Only a bounded, varied shortlist receives colored replay and an
original-loop certificate. No GAP factorization is needed. A single shortest
setup per shape is explored; this is an additional vocabulary, not a complete
search of colored setups or a substitute for the native generating set.
"""

from collections import deque
from dataclasses import dataclass, replace
import json
from math import isfinite
from time import monotonic

from ._moves import _simplified_moves
from .computation import checkpoint
from .familiar_algorithm_catalog import (
    FamiliarAlgorithmCatalog, compile_word_obstruction, familiar_algorithm_catalog,
    shape_bond_bits,
)
from .loop_algorithms import (
    AlgorithmLibrary, LoopExpression, _IDENTITY, _integer, _inverse_moves,
    _reference, _register, _select,
)


_MOVES = tuple(face + suffix for face in "URFDLB" for suffix in ("", "'", "2"))


@dataclass(frozen=True)
class _Opportunity:
    variant: object
    shape_index: int
    setup: str
    moves: str

    @property
    def rank(self):
        return (len(self.moves.split()), len(self.setup.split()),
                self.variant.htm, self.variant.id, self.shape_index)


def _shortlist(opportunities):
    """Reserve the nearest useful occurrence of every base before extra forms."""
    ranked = sorted(opportunities, key=lambda opportunity: opportunity.rank)
    bases, first, remaining = set(), [], []
    for opportunity in ranked:
        if opportunity.variant.base_id not in bases:
            bases.add(opportunity.variant.base_id)
            first.append(opportunity)
        else:
            remaining.append(opportunity)
    # Family round robin also helps when an unusually small candidate cap
    # cannot accommodate even one representative of every available base.
    families = {}
    for opportunity in first:
        families.setdefault(opportunity.variant.family, deque()).append(opportunity)
    while families:
        for family in sorted(tuple(families)):
            yield families[family].popleft()
            if not families[family]:
                del families[family]
    yield from remaining


def _ordered_variants(variants):
    """Test one form per base and family before broad orientation coverage."""
    bases, representatives, remaining = set(), [], []
    for variant in variants:
        if variant.base_id in bases:
            remaining.append(variant)
        else:
            bases.add(variant.base_id)
            representatives.append(variant)
    for batch in (representatives, remaining):
        families = {}
        for variant in batch:
            families.setdefault(variant.family, deque()).append(variant)
        while families:
            for family in sorted(tuple(families)):
                yield families[family].popleft()
                if not families[family]:
                    del families[family]


def discover_familiar_algorithms(
        initial, *, catalog=None, max_setup_depth=8, max_shapes=2048,
        max_work=100_000, max_seconds=2.0, max_candidates=128,
        max_algorithms=256, max_htm_length=120, max_expanded_moves=480,
        max_proof_moves=100_000):
    """Return bounded certified familiar root loops in an AlgorithmLibrary.

    ``initial`` accepts the same reference inputs as loop discovery, or an
    existing AlgorithmLibrary whose retained algorithms join the candidate pool.
    Its complete native ``loops`` alphabet is always retained unchanged.
    Preparing that native alphabet is outside these optional-search budgets.

    ``max_work`` counts word/shape tests and attempted HTM transitions;
    ``max_shapes`` bounds both stored and scanned shapes. Catalog forms are
    tested by family, and each scans shapes in setup-distance order, so the
    first useful transports do not await compilation of the entire catalog.
    At most two nearest
    occurrences of each physical catalog word compete for the shortlist.
    ``max_candidates`` bounds materialized forward and inverse alternatives.
    Physical witness caps (``max_htm_length``, ``max_expanded_moves``) are
    independent of the expanded original-loop proof cap ``max_proof_moves``.
    ``max_seconds`` covers catalog construction, scanning and materialization,
    checked between indivisible operations. A quarter of the allowance is
    reserved for materialization. Set it to None to use only finite work caps.

    The library's familiar_transport metadata records limits, cutoffs and
    setup/body/undo for retained transported algorithms. Zero hits or a budget
    cutoff never makes a global impossibility or completeness claim.
    Portable original-loop libraries do not retain the graph certificate
    data; discovery records that it skipped them and preserves their library.
    """
    for name, value in (("max_setup_depth", max_setup_depth), ("max_shapes", max_shapes),
                        ("max_work", max_work), ("max_candidates", max_candidates),
                        ("max_proof_moves", max_proof_moves)):
        _integer(value, name, 0)
    for name, value in (("max_algorithms", max_algorithms),
                        ("max_htm_length", max_htm_length),
                        ("max_expanded_moves", max_expanded_moves)):
        _integer(value, name)
    if max_seconds is not None:
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)):
            raise TypeError("max_seconds must be a nonnegative finite number or None")
        if not isfinite(max_seconds) or max_seconds < 0:
            raise ValueError("max_seconds must be nonnegative and finite")
    if catalog is not None and not isinstance(catalog, FamiliarAlgorithmCatalog):
        raise TypeError("catalog must be a FamiliarAlgorithmCatalog or None")

    if isinstance(initial, AlgorithmLibrary):
        base = initial
        loops = base.loops
    else:
        loops = _reference(initial)
        base = AlgorithmLibrary(loops, (), (), (), max_seed_loops=0, rounds=0,
                                max_candidates=max_candidates, max_algorithms=max_algorithms,
                                max_htm_length=max_htm_length,
                                max_expanded_moves=max_expanded_moves)
    started = monotonic()
    deadline = None if max_seconds is None else started + max_seconds
    scan_deadline = None if max_seconds is None else started + .75 * max_seconds
    limits = dict(max_setup_depth=max_setup_depth, max_shapes=max_shapes, max_work=max_work,
                  max_seconds=max_seconds, max_candidates=max_candidates,
                  max_algorithms=max_algorithms, max_htm_length=max_htm_length,
                  max_expanded_moves=max_expanded_moves, max_proof_moves=max_proof_moves)
    stats = dict(work=0, shapes_seen=0, shapes_scanned=0, word_shape_tests=0,
                 transition_attempts=0, legal_occurrences=0, closed_occurrences=0,
                 available_words=0, available_bases=0, available_families=0,
                 opportunities=0, candidates_examined=0, certified_candidates=0,
                 identity_count=0, duplicate_count=0, length_pruned_count=0,
                 proof_pruned_count=0)
    reached = dict(work=False, shapes=False, depth=False, time=False,
                   candidates=False, algorithms=False)
    setup_work_limit = max_work // 3
    setup_work_limit_reached = False
    stop_reason = None
    root = loops.root_shape
    nodes, parent, parent_moves, depths = [root], [-1], [""], [0]
    seen, queue = {root: 0}, deque([0])
    setups, opportunities, occurrence_counts, available_ids = {0: ""}, [], {}, set()
    compiled, scanned_shapes = {}, set()
    variants = ()
    native_certification_available = callable(getattr(loops._native, "certify_root_loop", None))

    def expired(scan=False):
        limit = scan_deadline if scan else deadline
        return limit is not None and monotonic() >= limit

    def charge(kind):
        nonlocal stop_reason
        if expired(scan=True):
            reached["time"], stop_reason = True, "max_seconds"
            return False
        if stats["work"] >= max_work:
            reached["work"], stop_reason = True, "max_work"
            return False
        checkpoint("familiar_algorithms", work=1, shapes=stats["shapes_scanned"])
        stats["work"] += 1
        stats[kind] += 1
        return True

    def setup_word(index):
        if index not in setups:
            moves, cursor = [], index
            while cursor not in setups:
                moves.append(parent_moves[cursor])
                cursor = parent[cursor]
            setups[index] = " ".join(filter(None, (setups[cursor], " ".join(reversed(moves)))))
        return setups[index]

    disabled = not max_shapes or not max_work or not max_candidates or max_seconds == 0
    if not disabled and native_certification_available:
        catalog = familiar_algorithm_catalog() if catalog is None else catalog
        variants = tuple(catalog.variants)
        if len({variant.id for variant in variants}) != len(variants):
            raise ValueError("catalog variant IDs must be unique")
        stats["shapes_seen"] = 1
        shape_limit = min(max_shapes, loops.shape_count)
        while queue and variants and len(nodes) < shape_limit:
            index = queue.popleft()
            local_shape = nodes[index]
            if depths[index] >= max_setup_depth:
                # The full native graph gives a cheap exact indication that
                # the depth bound omitted shapes even when this vertex loops.
                reached["depth"] = reached["depth"] or len(seen) < loops.shape_count
                continue
            for move in _MOVES:
                if stats["transition_attempts"] >= setup_work_limit:
                    setup_work_limit_reached = True
                    break
                if not charge("transition_attempts"):
                    break
                if not local_shape.is_turnable(move[0]):
                    continue
                target = local_shape.apply(move)
                if target in seen:
                    continue
                if len(nodes) >= max_shapes:
                    reached["shapes"] = True
                    continue
                target_index = len(nodes)
                seen[target] = target_index
                nodes.append(target)
                parent.append(index)
                parent_moves.append(move)
                depths.append(depths[index] + 1)
                queue.append(target_index)
                stats["shapes_seen"] += 1
                if len(nodes) >= shape_limit:
                    break
            if stop_reason is not None or setup_work_limit_reached:
                break
        reached["shapes"] = reached["shapes"] or (
            len(nodes) == max_shapes and len(nodes) < loops.shape_count)
        reached["depth"] = reached["depth"] or (
            max_setup_depth == 0 and loops.shape_count > 1)
        masks = tuple(shape_bond_bits(local_shape) for local_shape in nodes)
        for variant in _ordered_variants(variants):
            if stop_reason is not None:
                break
            for index, bits in enumerate(masks):
                if not charge("word_shape_tests"):
                    break
                scanned_shapes.add(index)
                if variant.word not in compiled:
                    compiled[variant.word] = compile_word_obstruction(variant.word)
                obstruction = compiled[variant.word]
                if not obstruction.is_legal_bits(bits):
                    continue
                stats["legal_occurrences"] += 1
                if not obstruction.is_closed_bits(bits):
                    continue
                stats["closed_occurrences"] += 1
                available_ids.add(variant.id)
                # Whole words are tested before any shortening at setup/body
                # boundaries. Equivalent ordinary effects never merge masks.
                setup = setup_word(index)
                undo = " ".join(_inverse_moves(setup.split()))
                word = _simplified_moves((setup + " " + variant.word + " " + undo).split())
                if len(word.split()) > min(max_htm_length, max_expanded_moves):
                    stats["length_pruned_count"] += 1
                    continue
                count = occurrence_counts.get(variant.id, 0) + 1
                occurrence_counts[variant.id] = count
                opportunities.append(_Opportunity(variant, index, setup, word))
                if count >= 2:
                    break
        stats["shapes_scanned"] = len(scanned_shapes)
    else:
        if not native_certification_available and not disabled:
            stop_reason = "native_certification_unavailable"
        else:
            stop_reason = ("max_shapes" if not max_shapes else "max_work" if not max_work
                           else "max_candidates" if not max_candidates else "max_seconds")
            reached[{"max_shapes": "shapes", "max_work": "work", "max_candidates": "candidates",
                     "max_seconds": "time"}[stop_reason]] = True

    available = {variant.id: variant for variant in variants if variant.id in available_ids}
    stats.update(available_words=len(available),
                 available_bases=len({variant.base_id for variant in available.values()}),
                 available_families=len({variant.family for variant in available.values()}),
                 opportunities=len(opportunities))
    pool, transport_records = {}, {}
    for algorithm in base.algorithms:
        _register(pool, algorithm)
    if base.familiar_transport_json is not None:
        transport_records.update(json.loads(base.familiar_transport_json).get("algorithms", {}))
    candidates = list(_shortlist(opportunities))
    for opportunity in candidates:
        if stats["candidates_examined"] >= max_candidates:
            reached["candidates"] = True
            stop_reason = stop_reason or "max_candidates"
            break
        if expired():
            reached["time"] = True
            stop_reason = stop_reason or "max_seconds"
            break
        checkpoint("familiar_algorithms", work=1, candidates=stats["candidates_examined"])
        stats["candidates_examined"] += 1
        try:
            certificate = loops.certify_root_loop(opportunity.moves, max_proof_moves=max_proof_moves)
        except ValueError as error:
            if "max_proof_moves" not in str(error):
                raise
            stats["proof_pruned_count"] += 1
            continue
        proof_qtm = sum(loops.generator_records[identifier].qtm_length * abs(power)
                        for identifier, power in certificate.loop_steps(
                            max_syllables=max(1, max_proof_moves)))
        for inverse in (False, True):
            if inverse:
                if stats["candidates_examined"] >= max_candidates:
                    reached["candidates"] = True
                    stop_reason = stop_reason or "max_candidates"
                    break
                if expired():
                    reached["time"] = True
                    stop_reason = stop_reason or "max_seconds"
                    break
                checkpoint("familiar_algorithms", work=1, candidates=stats["candidates_examined"])
                stats["candidates_examined"] += 1
            moves = (" ".join(_inverse_moves(opportunity.moves.split()))
                     if inverse else opportunity.moves)
            witness = LoopExpression.power(certificate, -1) if inverse else certificate
            algorithm = base.build_algorithm(LoopExpression.turns(moves, witness),
                                             max_expanded_moves=max_expanded_moves,
                                             max_htm_length=max_htm_length)
            # The builder independently checks colored legality, exact shape
            # closure and equality to the original-loop certificate action.
            stats["certified_candidates"] += 1
            if algorithm.permutation == _IDENTITY:
                stats["identity_count"] += 1
                continue
            if not _register(pool, algorithm):
                stats["duplicate_count"] += 1
            variant = opportunity.variant
            body = " ".join(_inverse_moves(variant.word.split())) if inverse else variant.word
            transport_records[algorithm.id] = dict(
                catalog_id=variant.id, base_id=variant.base_id, family=variant.family,
                rotation=variant.rotation, catalog_inverse=variant.inverse,
                transported_inverse=inverse, setup=opportunity.setup, body=body,
                undo=" ".join(_inverse_moves(opportunity.setup.split())),
                setup_htm=len(opportunity.setup.split()), body_htm=len(body.split()),
                conjugate=algorithm.moves, conjugate_htm=algorithm.htm_length,
                proof_qtm=proof_qtm)

    original_effects = {generator.permutation for generator in loops} if pool else set()
    algorithms, shortest, structured, truncated = _select(pool, original_effects, max_algorithms)
    reached["algorithms"] = truncated
    transport_records = {algorithm.id: transport_records[algorithm.id]
                         for algorithm in algorithms if algorithm.id in transport_records}
    metadata = dict(limits=limits, **stats, limit_reached=reached, stop_reason=stop_reason,
                    catalog_words=len(variants), compiled_words=len(compiled),
                    setup_metric="HTM", max_occurrences_per_word=2,
                    setup_work_limit=setup_work_limit,
                    setup_work_limit_reached=setup_work_limit_reached,
                    work_scope="word/shape tests and attempted HTM transitions",
                    time_scope="catalog, masks, nearby-shape scan and bounded materialization",
                    native_preparation_in_budget=False,
                    native_certification_available=native_certification_available, exhaustive=False,
                    retained_transport_count=len(transport_records), algorithms=transport_records)
    return replace(base, algorithms=algorithms, shortest=shortest, structured=structured,
                   max_algorithms=max_algorithms,
                   algorithm_limit_reached=base.algorithm_limit_reached or truncated,
                   familiar_transport_json=json.dumps(metadata, sort_keys=True, allow_nan=False))
