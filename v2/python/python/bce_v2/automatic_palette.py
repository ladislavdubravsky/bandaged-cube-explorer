"""Bounded automatic palettes from legal familiar words and native root loops.

The familiar vocabulary is a built-in starting point, not a declaration that
a particular bandage admits CFOP. Every candidate receives actual native
legality, shape-closure and original-loop witness checks. Shared endpoint
preservation chooses a coherent family without naming any ordinary pieces.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations
import json

from . import BlockedMoveError, State
from .algorithm_palette import AlgorithmPalette
from .computation import checkpoint
from .familiar_algorithm_catalog import FamiliarAlgorithm, familiar_algorithm_catalog
from .loop_algorithms import AlgorithmLibrary, LoopExpression, _IDENTITY, _reference


# These are additional familiar physical words, not cube-specific goals.
# Their effects and availability are checked just like every catalog entry.
_TEACHING_WORDS = (
    ("EO", "OLL", "F R U R' U' F'"),
    ("Sune", "OLL", "R U R' U R U2 R'"),
    ("Tperm", "PLL", "R U R' U' R' F R2 U' R' U' R U R' F'"),
    ("Ua", "edge_cycle", "R U' R U R U R U' R' U' R2"),
)
_PRIMARY_FAMILIES = frozenset(("OLL", "PLL", "edge_cycle"))
_SHORT_WORDS = tuple(face + suffix for face in "URFDLB" for suffix in ("", "2", "'"))


def _limit(value, name, *, minimum=0):
    if type(value) is not int:
        raise TypeError(name + " must be an integer")
    if value < minimum:
        raise ValueError(name + " is below its minimum")
    return value


@dataclass(frozen=True)
class AutomaticPaletteResult:
    """Finite declarations plus the actual acceptance and selection audit."""

    palette: AlgorithmPalette
    _metadata_json: str = field(repr=False)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)


def _candidates():
    """Base words precede a bounded selection of physical rotated forms."""
    seen = set()
    for identifier, family, word in _TEACHING_WORDS:
        seen.add(word)
        yield FamiliarAlgorithm.from_word(word, id=identifier, family=family)
    catalog = familiar_algorithm_catalog()
    for entry in (*catalog.base_templates, *catalog.variants):
        if entry.word not in seen:
            seen.add(entry.word)
            yield entry


def _fixed(action, active):
    return frozenset(index for index in active
                     if action.destinations[index] == index and not action.phases[index])


def _category(inventory, action, active):
    phases = tuple(sorted({inventory.blocks[index].orientation_order
                           for index in active if action.phases[index]}))
    if phases:
        return "orientation", phases
    return "placement", tuple(sorted({inventory.blocks[index].orientation_order
                                      for index in active
                                      if action.destinations[index] != index}))


def _cohort(entries, inventory, active, max_bodies):
    """Bounded fixed-pose intersections, shortest body per actual effect kind."""
    if not entries or not max_bodies:
        return (), frozenset()
    descriptions = tuple((entry, _fixed(entry[1].block_action, active),
                          _category(inventory, entry[1].block_action, active))
                         for entry in entries)
    regions = {fixed for _, fixed, _ in descriptions}
    regions.update(left[1] & right[1] for left, right in combinations(descriptions, 2))
    ranked = []
    for region in regions:
        representatives = {}
        for entry, fixed, category in descriptions:
            if region <= fixed:
                previous = representatives.get(category)
                if previous is None or (entry[1].htm_length, entry[2]) < (
                        previous[1].htm_length, previous[2]):
                    representatives[category] = entry
        selected = tuple(sorted(representatives.values(), key=lambda entry: entry[2]))[:max_bodies]
        if selected:
            # The intersection is recomputed after the hard body limit. More
            # categories come first, then a larger shared region, then lower
            # definition cost. Stable candidate order resolves exact ties.
            actual = frozenset.intersection(*(_fixed(entry[1].block_action, active)
                                             for entry in selected))
            ranked.append(((-len(selected), -len(actual),
                            sum(entry[1].htm_length for entry in selected),
                            tuple(entry[2] for entry in selected)), selected, actual))
    if not ranked:
        return (), frozenset()
    _, selected, fixed = min(ranked, key=lambda row: row[0])
    return selected, fixed


def automatic_algorithm_palette(initial, *, max_taught_bodies=7,
                                max_catalog_candidates=96, max_body_htm=40,
                                max_short_adjustment_htm=2,
                                max_native_candidates=32,
                                max_proof_moves=100_000):
    """Select a finite witnessed palette without caller algorithms or goals.

    A coherent family from the built-in OLL/PLL/edge-cycle vocabulary is
    preferred when legal. Other familiar families are available as a second
    bounded tier. When neither yields a useful family, reduced native root
    generators provide long bodies and short root loops provide explicit
    adjustments. That fallback retains at most ``max_taught_bodies`` long
    definitions; losing generators through this cap never implies coverage.

    Familiar bodies have explicit forward-only permission. Native fallback
    bodies explicitly permit inverses under the same taught ID. Setups and
    standalone adjustments are independently declared. Only physically legal
    root-closing short words preserving the selected family's shared poses
    are admitted; no blocked cancellation or shape symmetry is assumed.

    Native graph/group preparation is performed by the caller's existing
    analysis (or by ordinary loop preparation for a raw reference). This is
    a bounded vocabulary search, not a solver or a global discovery proof.
    """
    for name, value in (("max_taught_bodies", max_taught_bodies),
                        ("max_catalog_candidates", max_catalog_candidates),
                        ("max_native_candidates", max_native_candidates)):
        _limit(value, name)
    for name, value in (("max_body_htm", max_body_htm),
                        ("max_short_adjustment_htm", max_short_adjustment_htm),
                        ("max_proof_moves", max_proof_moves)):
        _limit(value, name)
    loops = _reference(initial)
    inventory = loops.block_inventory
    builder = AlgorithmLibrary(loops, (), (), ())
    root = State(loops.root_shape)
    original_actions = tuple(inventory.action(generator.permutation) for generator in loops.generators)
    active = tuple(index for index in range(len(inventory.blocks))
                   if any(action.destinations[index] != index or action.phases[index]
                          for action in original_actions))
    audit, entries = [], []

    def witnessed(identifier, word, source, **record):
        row = dict(id=identifier, source=source, word=word, **record)
        if len(word.split()) > max_body_htm:
            row.update(status="rejected", reason="max_body_htm")
            audit.append(row)
            return None
        checkpoint("automatic_palette_candidates", source=source, candidate=identifier)
        try:
            physical = root.apply(word)
        except BlockedMoveError:
            row.update(status="rejected", reason="blocked_move")
            audit.append(row)
            return None
        if physical.shape != loops.root_shape:
            row.update(status="rejected", reason="not_root_closing")
            audit.append(row)
            return None
        if tuple(physical.sticker_permutation) == _IDENTITY:
            row.update(status="rejected", reason="identity_effect")
            audit.append(row)
            return None
        try:
            expression = loops.certified_root_turns(word, max_proof_moves=max_proof_moves)
        except ValueError as error:
            if "max_proof_moves" not in str(error):
                raise
            row.update(status="rejected", reason="max_proof_moves")
            audit.append(row)
            return None
        algorithm = replace(builder.build_algorithm(expression,
                            max_expanded_moves=max(1, len(word.split()))), id=identifier)
        if algorithm.permutation != tuple(physical.sticker_permutation):
            raise AssertionError("automatic palette physical replay disagrees with its original witness")
        row.update(status="accepted", htm=algorithm.htm_length,
                   original_loop_ids=list(algorithm.base_ids))
        audit.append(row)
        return algorithm

    catalog_seen, catalog_limit_reached = 0, False
    if max_catalog_candidates and max_taught_bodies:
        for index, candidate in enumerate(_candidates()):
            if index >= max_catalog_candidates:
                catalog_limit_reached = True
                break
            catalog_seen += 1
            algorithm = witnessed(candidate.id, candidate.word, "familiar_catalog",
                                  family=candidate.family, base_id=candidate.base_id,
                                  rotation=candidate.rotation)
            if algorithm is not None:
                entries.append((candidate, algorithm, index))
    primary = tuple(entry for entry in entries if entry[0].family in _PRIMARY_FAMILIES)
    selected, preserved = _cohort(primary, inventory, active, max_taught_bodies)
    # A single family member can be useful, but if only one effect category
    # survived, broaden the bounded vocabulary before committing to it.
    if len(selected) < min(2, max_taught_bodies):
        broader, broader_preserved = _cohort(entries, inventory, active, max_taught_bodies)
        if len(broader) > len(selected):
            selected, preserved = broader, broader_preserved
    selection_kind = "familiar_preservation_cohort" if selected else "native_root_loops"
    bodies = tuple(entry[1] for entry in selected)
    allow_inverse = False
    native_examined = 0
    native_body_candidates = []
    # Reduced algebra generators are still witnessed by the complete original
    # alphabet. No generator word is replaced with an anonymous permutation.
    analysis = getattr(initial, "analysis", initial)
    basis = getattr(analysis, "generators", loops.generators)
    basis = tuple(sorted(basis, key=lambda generator: (len(generator.turn_sequence.split()),
                                                     generator.id)))
    if not bodies:
        allow_inverse = True
        for generator in basis[:max_native_candidates]:
            native_examined += 1
            algorithm = witnessed("loop:" + str(generator.id), generator.turn_sequence,
                                  "original_root_loop", generator_id=generator.id)
            if algorithm is not None and algorithm.htm_length > max_short_adjustment_htm:
                native_body_candidates.append(algorithm)
        bodies = tuple(native_body_candidates[:max_taught_bodies])
        preserved = (frozenset.intersection(*(_fixed(body.block_action, active) for body in bodies))
                     if bodies else frozenset())

    short_candidates = list(_SHORT_WORDS)
    short_candidates.extend(generator.turn_sequence for generator in
                            sorted(loops.generators, key=lambda value: (len(value.turn_sequence.split()), value.id))[:max_native_candidates]
                            if len(generator.turn_sequence.split()) <= max_short_adjustment_htm)
    adjustments, seen_words = [], set()
    for word in short_candidates:
        if word in seen_words or len(word.split()) > max_short_adjustment_htm:
            continue
        seen_words.add(word)
        algorithm = witnessed(word, word, "short_root_adjustment")
        if algorithm is not None:
            if not preserved <= _fixed(algorithm.block_action, active):
                audit[-1].update(status="rejected", reason="disrupts_selected_workspace")
            else:
                adjustments.append(algorithm)
    palette = AlgorithmPalette.from_algorithms(bodies, setups=tuple(adjustments),
                                              adjustments=tuple(adjustments),
                                              allow_inverse=allow_inverse)
    selected_ids = {body.id for body in bodies}
    for row in audit:
        row["selected_as_body"] = row["id"] in selected_ids and row["source"] != "short_root_adjustment"
        if row["source"] == "familiar_catalog" and row["status"] == "accepted" and not row["selected_as_body"]:
            row["selection_reason"] = "outside_selected_cohort_or_effect_representative"
    metadata = dict(format="bce-v2-automatic-palette", version=1,
                    selection_kind=selection_kind, reference_shape=list(loops.root_shape.labels),
                    catalog_candidates_examined=catalog_seen,
                    catalog_candidate_limit_reached=catalog_limit_reached,
                    catalog_scope="verified base words first, then bounded physical rotated catalog forms",
                    native_candidates_examined=native_examined,
                    native_basis_candidate_count=len(basis),
                    native_candidate_limit_reached=bool(not selected and len(basis) > max_native_candidates),
                    native_basis_scope="reduced analysis generators when present; original native loops otherwise",
                    active_component_indices=list(active),
                    inferred_shared_fixed_component_indices=sorted(preserved),
                    selected_body_ids=[body.id for body in bodies],
                    body_count=len(bodies), inverse_body_permission=allow_inverse,
                    short_setup_ids=[algorithm.id for algorithm in adjustments],
                    short_adjustment_ids=[algorithm.id for algorithm in adjustments],
                    native_body_candidates_omitted=max(0, len(native_body_candidates) - len(bodies)),
                    limits=dict(max_taught_bodies=max_taught_bodies,
                                max_catalog_candidates=max_catalog_candidates,
                                max_body_htm=max_body_htm,
                                max_short_adjustment_htm=max_short_adjustment_htm,
                                max_native_candidates=max_native_candidates,
                                max_proof_moves=max_proof_moves),
                    sources=audit, coverage_claim=False, goals_seeded=False,
                    ordinary_bandage_identity_branch=False,
                    nearby_shape_transport_performed=False,
                    new_loop_body_mining_performed=False,
                    scope="bounded physical vocabulary; complete method coverage requires subsequent certification")
    return AutomaticPaletteResult(palette, json.dumps(metadata, sort_keys=True))


__all__ = ["AutomaticPaletteResult", "automatic_algorithm_palette"]
