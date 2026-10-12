#!/usr/bin/env python3
"""Replay a one-bond refinement whose root isotropy groups do not nest.

Run from the repository root with its installed native engine:

    v2/.venv/bin/python v2/research/probe_bandage_refinement.py

Every raw word is checked both by native shape/colored replay and by the
production compiled-word obstruction certificate. This is a counterexample
to root-loop inclusion, not an enumeration of either isotropy group.
"""

import argparse
import json
from pathlib import Path

import bce_v2 as c


def fused_blocks(shape):
    return [
        [name for name, label in zip(c.CELL_NAMES, shape) if label == block]
        for block in sorted(set(shape))
        if sum(label == block for label in shape) > 1
    ]


def is_refinement(fine, coarse):
    """Every fine block must be contained in one coarse block."""
    return all(
        fine[first] != fine[second] or coarse[first] == coarse[second]
        for first in range(27)
        for second in range(27)
    )


def replay(shape, word, obstruction):
    endpoint = shape.apply(word)
    colored = c.State(shape).apply(word)
    source_bits = c.shape_bond_bits(shape)
    endpoint_bits = c.shape_bond_bits(endpoint)
    closed = endpoint == shape
    if colored.shape != endpoint:
        raise AssertionError("native colored and shape replay disagree")
    if not obstruction.is_legal_bits(source_bits):
        raise AssertionError("compiled legality disagrees with native replay")
    if obstruction.endpoint_bits(source_bits) != endpoint_bits:
        raise AssertionError("compiled endpoint disagrees with native replay")
    if obstruction.is_closed_bits(source_bits) != closed:
        raise AssertionError("compiled closure disagrees with native replay")
    return {
        "source_labels": shape.labels,
        "source_fused_blocks": fused_blocks(shape),
        "source_bond_bits": f"{source_bits:014x}",
        "source_legal_moves": shape.legal_moves,
        "raw_word": word,
        "native_legal": True,
        "native_closed": closed,
        "endpoint_labels": endpoint.labels,
        "endpoint_fused_blocks": fused_blocks(endpoint),
        "endpoint_bond_bits": f"{endpoint_bits:014x}",
        "sticker_permutation": list(colored.sticker_permutation),
        "compiled_legal": obstruction.is_legal_bits(source_bits),
        "compiled_closed": obstruction.is_closed_bits(source_bits),
        "compiled_endpoint_matches_native": True,
    }, endpoint


def run():
    labels = [0] * 27
    for block, names in enumerate((("UFR", "UR"), ("UBL", "UL")), 1):
        for name in names:
            labels[c.CELL_NAMES.index(name)] = block
    coarse = c.Shape(labels)
    fine_labels = labels.copy()
    for name in ("UBL", "UL"):
        fine_labels[c.CELL_NAMES.index(name)] = 0
    fine = c.Shape(fine_labels)
    word = "U2"
    obstruction = c.compile_word_obstruction(word)
    coarse_record, coarse_endpoint = replay(coarse, word, obstruction)
    fine_record, fine_endpoint = replay(fine, word, obstruction)
    coarse_bits = c.shape_bond_bits(coarse)
    fine_bits = c.shape_bond_bits(fine)
    removed_bits = coarse_bits & ~fine_bits
    checks = {
        "fine_refines_coarse_at_source": is_refinement(fine, coarse),
        "fine_refines_coarse_at_endpoint": is_refinement(fine_endpoint, coarse_endpoint),
        "fine_source_bonds_subset_of_coarse": not (fine_bits & ~coarse_bits),
        "exactly_one_source_bond_removed": removed_bits.bit_count() == 1,
        "same_faithful_effect_on_both_specifications": (
            coarse_record["sticker_permutation"] == fine_record["sticker_permutation"]
        ),
        "coarse_root_loop_is_fine_open_arrow": (
            coarse_record["native_closed"] and not fine_record["native_closed"]
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"counterexample validation failed: {checks}")
    return {
        "format": "bce-research-bandage-refinement-transfer",
        "version": 1,
        "scope": "one-bond native replay counterexample; no group enumeration",
        "model": "27-cell fixed-frame partition; faithful 48-sticker effects",
        "cell_order": list(c.CELL_NAMES),
        "raw_word": word,
        "removed_source_bond_bits": f"{removed_bits:014x}",
        "compiled_forbidden_bond_bits": f"{obstruction.forbidden_bonds:014x}",
        "coarse": coarse_record,
        "fine": fine_record,
        "checks": checks,
        "conclusion": (
            "Deleting one bond preserves this raw word's legality but not root "
            "shape closure: U2 belongs to coarse root isotropy and not fine root isotropy."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent
        / "research-results" / "bandage-refinement-transfer.json",
    )
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Validated one-bond refinement: U2 is coarse-closed and fine-open; wrote {args.output}")


if __name__ == "__main__":
    main()
