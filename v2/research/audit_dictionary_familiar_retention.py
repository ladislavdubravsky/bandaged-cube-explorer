#!/usr/bin/env python3
"""Audit exact effects retained from the bounded materialized familiar catalog.

Run probe_geometric_chain.py first. Compares materialized transported words
with every final dictionary permutation, regardless of source algorithm ID.
Absence here means absence from this capped dictionary; it does not mean the
effect is unreachable through a sequence of retained words.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import bce_v2 as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dictionary", type=Path, default=Path("/tmp/geometric-chain-dictionary.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                        "research-results/familiar-dictionary-retention-audit.json")
    args = parser.parse_args()
    dictionary = c.SymbolicAlgorithmDictionary.from_dict(json.loads(args.dictionary.read_text()))
    metadata = dictionary.metadata["familiar_transport"]
    effects = {algorithm.permutation: algorithm for algorithm in dictionary.algorithms}
    state = c.State(dictionary.loops.root_shape)
    rows, present, absent = [], Counter(), Counter()
    for identifier, source in sorted(metadata["algorithms"].items()):
        permutation = state.apply(source["conjugate"]).sticker_permutation
        retained = effects.get(permutation)
        (present if retained else absent)[source["family"]] += 1
        rows.append(dict(source_algorithm_id=identifier, catalog_id=source["catalog_id"],
                         base_id=source["base_id"], family=source["family"],
                         word=source["conjugate"], htm=source["conjugate_htm"],
                         permutation=list(permutation), exact_effect_retained=retained is not None,
                         retained_algorithm_id=None if retained is None else retained.id,
                         retained_word=None if retained is None else retained.turn_sequence))
    record = dict(format="bce-v2-familiar-dictionary-retention-audit", version=1,
                  scope="bounded materialized familiar transported words; exact final dictionary effects, including different source IDs",
                  dictionary_sha256=hashlib.sha256(args.dictionary.read_bytes()).hexdigest(),
                  dictionary_algorithm_count=len(dictionary.algorithms),
                  materialized_count=len(rows), materialized_effects_retained=sum(present.values()),
                  present_families=dict(present), absent_families=dict(absent), rows=rows)
    assert record["materialized_effects_retained"] == metadata["dictionary_effect_count"]
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in record.items() if key != "rows"}))


if __name__ == "__main__":
    main()
