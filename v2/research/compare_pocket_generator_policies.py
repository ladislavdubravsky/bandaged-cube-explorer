#!/usr/bin/env python3
"""Compare Pocket Cube policies in the vocabulary actually taught by the guide.

Run with v2/.venv/bin/python. The bounded controls enumerate words containing
at most six master applications; they do not establish shortest physical words.
Every retained method is independently reloaded and legally applied to all 432
reference-shaped colored states. No production solver or notebook is changed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from itertools import combinations
import json
from pathlib import Path

import bce_v2 as c
from bce_v2._moves import _simplified_moves
from bce_v2.human_algorithms import _metrics, _stage_groups
from bce_v2.human_methods import (
    _inverse, _observe, _state_for_permutation, _then, _validate_method,
)
from bce_v2.loop_algorithms import LoopAlgorithm, LoopExpression
from bce_v2.loop_rotations import bandage_symmetries, rotate_permutation


BANDAGE = [1, 1, 2, 1, 1, 2, 3, 3, 0,
           0, 0, 4, 0, 0, 4, 5, 5, 6,
           0, 0, 4, 0, 0, 4, 5, 5, 6]
IDENTITY = tuple(range(48))
RESULTS = Path(__file__).resolve().parent.parent / "research-results"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inverse_word(word):
    return tuple(move if move.endswith("2") else
                 move[:-1] if move.endswith("'") else move + "'"
                 for move in reversed(word))


def closure(alphabet):
    seen, queue = {IDENTITY}, [IDENTITY]
    for permutation in queue:
        for generator in alphabet:
            successor = _then(permutation, generator)
            if successor not in seen:
                seen.add(successor)
                queue.append(successor)
    return frozenset(seen)


def symmetry_closures(method):
    rotations = ("", *bandage_symmetries(method.reference_shape))
    records, pairwise = [], []
    for size in range(1, len(method.generators) + 1):
        for indices in combinations(range(len(method.generators)), size):
            alphabet = {rotate_permutation(method.generators[index].permutation, rotation)
                        for index in indices for rotation in rotations}
            records.append({"masters": [f"M{i + 1}" for i in indices],
                            "definition_htm": sum(method.generators[i].htm_length for i in indices),
                            "distinct_actions": len(alphabet), "group_order": len(closure(alphabet))})
    for first, generator in enumerate(method.generators):
        for second, other in enumerate(method.generators):
            if first == second:
                continue
            for rotation in rotations:
                image = rotate_permutation(generator.permutation, rotation)
                for sign, target in ((1, other.permutation), (-1, _inverse(other.permutation))):
                    if image == target:
                        pairwise.append({"from": f"M{first + 1}", "to": f"M{second + 1}",
                                         "rotation": rotation, "exponent": sign})
    return {"nonidentity_rotations": list(rotations[1:]), "closures": records,
            "pairwise_rotation_or_inverse_matches": pairwise}


@dataclass(frozen=True)
class Word:
    permutation: tuple[int, ...]
    turns: tuple[str, ...]
    factors: tuple[LoopExpression, ...]

    @property
    def key(self):
        return (len(self.turns), sum(2 if move.endswith("2") else 1 for move in self.turns),
                len(self.factors), tuple(expression.render() for expression in self.factors))

    @property
    def expression(self):
        return LoopExpression.sequence(*self.factors)


def bounded_policy(method, master_indices, *, symmetries, max_applications, loops):
    """Exhaust bounded words, then minimize each whole observation-fiber target.

    Adjacent literal inverse pairs can be omitted: deleting such a pair retains
    the same legal physical word after simplification and uses fewer masters.
    Equal physical variants are merged, including an involution's two signs.
    Previous complete corrections remain available as coverage fallbacks.
    """
    rotations = ("", *bandage_symmetries(method.reference_shape)) if symmetries else ("",)
    alphabet, seen = [], set()
    for index in master_indices:
        generator = method.generators[index]
        for rotation in rotations:
            for exponent in (1, -1):
                expression = LoopExpression.rotated(rotation, LoopExpression.power(
                    LoopExpression.loop(generator.id), exponent))
                turns = tuple(expression.expanded_moves(method.generators, max_expanded_moves=100).split())
                permutation = expression.evaluate(method.generators)
                if (permutation, turns) in seen:
                    continue
                seen.add((permutation, turns))
                alphabet.append(Word(permutation, turns, (expression,)))
    require(closure(tuple(word.permutation for word in alphabet)) == method._permutations,
            "requested master vocabulary does not generate the complete group")
    best, frontier = {IDENTITY: Word(IDENTITY, (), ())}, [(Word(IDENTITY, (), ()), None)]
    work = []
    for depth in range(1, max_applications + 1):
        following = []
        for word, last in frontier:
            for generator in alphabet:
                if last is not None and generator.turns == inverse_word(last):
                    continue
                successor = Word(_then(word.permutation, generator.permutation),
                                 tuple(_simplified_moves((*word.turns, *generator.turns)).split()),
                                 (*word.factors, *generator.factors))
                previous = best.get(successor.permutation)
                if previous is None or successor.key < previous.key:
                    best[successor.permutation] = successor
                following.append((successor, generator.turns))
        frontier = following
        work.append({"depth": depth, "words_evaluated": len(frontier), "effects_covered": len(best)})

    actions = {permutation: method.inventory.action(permutation) for permutation in method._permutations}
    originals = {algorithm.id: algorithm for algorithm in method.algorithms}
    lengths = tuple((generator.id, generator.htm_length) for generator in method.generators)
    algorithms, stages, cases = [], [], []
    for stage, (current, target) in zip(method.stages, _stage_groups(method, actions)):
        compiled = []
        for case in stage.cases:
            if case.algorithm_id is None:
                compiled.append(case)
                continue
            eligible = [word for permutation, word in best.items()
                        if permutation in current and _then(case.representative, permutation) in target]
            if not symmetries:
                original = originals[case.algorithm_id]
                eligible.append(Word(original.permutation, tuple(original.turn_sequence.split()),
                                     (original.expression,)))
            require(eligible, "bounded symmetry alphabet left a case uncovered")
            selected = min(eligible, key=lambda word: word.key)
            # Check the entire observation fiber, not just its representative.
            fiber = tuple(permutation for permutation in current
                          if _observe(actions[permutation], stage.block_index, stage.feature.kind) == case.observation)
            require(all(_then(permutation, selected.permutation) in target for permutation in fiber),
                    "case target does not correct its whole observation fiber")
            algorithm = LoopAlgorithm(f"A{len(algorithms) + 1}", selected.expression,
                                      selected.permutation, " ".join(selected.turns),
                                      method.inventory, lengths, method.generators)
            algorithms.append(algorithm)
            compiled.append(replace(case, algorithm_id=algorithm.id))
            cases.append({"stage": stage.number, "observation": list(case.observation),
                          "htm": algorithm.htm_length, "qtm": algorithm.qtm_length,
                          "expression": selected.expression.render(),
                          "turn_sequence": algorithm.turn_sequence, "fiber_size_checked": len(fiber)})
        stages.append(replace(stage, cases=tuple(compiled)))
    result = _validate_method(replace(method, algorithms=tuple(algorithms), stages=tuple(stages)),
                              complete_loops=loops)
    return result, {"max_applications": max_applications, "physical_shortest_claim": False,
                    "word_selection_key": ["simplified_htm", "simplified_qtm", "factor_count", "expression_text"],
                    "alphabet_size": len(alphabet), "symmetries": symmetries,
                    "masters": [f"M{i + 1}" for i in master_indices],
                    "coverage_fallback": "original_complete_policy" if not symmetries else "none_needed",
                    "enumeration": work, "cases": cases}


def verify(method, states):
    """Reload, then replay every solution through the legal colored engine."""
    loaded = c.HumanMethod.from_dict(method.to_dict())
    require(loaded.to_json() == method.to_json(), "method does not round-trip canonically")
    totals, worst = [0, 0], [0, 0]
    for state in states:
        require(state.scramble is None, "verification state retains scramble provenance")
        result = loaded.apply(state)
        require(result.status == "solved" and result.state.is_solved,
                "method failed a complete reference-group state")
        require(state.apply(result.turn_sequence) == result.state,
                "legal physical replay disagrees with the method result")
        turns = result.turn_sequence.split()
        for index, cost in enumerate((len(turns), sum(2 if move.endswith("2") else 1 for move in turns))):
            totals[index] += cost
            worst[index] = max(worst[index], cost)
    actions = {permutation: loaded.inventory.action(permutation) for permutation in loaded._permutations}
    metrics = _metrics(loaded, actions)
    require((metrics["total_htm"], metrics["total_qtm"], metrics["worst_htm"], metrics["worst_qtm"]) ==
            (*totals, *worst), "computed metrics disagree with legal replay")
    return {"metrics": metrics,
            "stage_chain": [{"block": stage.block_name, "feature": stage.feature.to_dict(),
                             "index": stage.index, "order_before": stage.order_before,
                             "order_after": stage.order_after} for stage in loaded.stages],
            "verification": {"portable_roundtrip": True, "physical_states_checked": len(states),
                             "complete_case_fibers_checked": True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "pocket-generator-policies.json")
    parser.add_argument("--selected-method", type=Path,
                        help="reuse a previously generated select_human_chain method")
    parser.add_argument("--max-applications", type=int, default=6)
    args = parser.parse_args(argv)
    require(1 <= args.max_applications <= 6, "max-applications must be between 1 and 6")
    analysis = c.analyze_isotropy(BANDAGE)
    selected = (c.load_human_method(args.selected_method) if args.selected_method else
                c.select_human_chain(analysis).method)
    require(selected.reference_shape == c.Shape(BANDAGE), "selected method uses another puzzle reference")
    rebuilt = c.generator_human_repertoire(selected)
    direct = c.generator_human_repertoire(analysis)
    states = tuple(_state_for_permutation(selected.reference_shape, permutation)
                   for permutation in sorted(selected._permutations))
    result = {"puzzle": "BandagedPocketCube", "bandage": BANDAGE,
              "group_order": analysis.group_order, "shape_count": analysis.loops.shape_count,
              "colored_state_count": analysis.colored_state_count,
              "scope": "uniform complete reference group, includes solved; shape restoration excluded",
              "masters": [{"id": f"M{i + 1}", "generator_id": generator.id,
                           "turn_sequence": generator.turn_sequence,
                           "block_action": generator.block_action.notation,
                           "htm": generator.htm_length, "qtm": generator.qtm_length}
                          for i, generator in enumerate(rebuilt.method.generators)],
              "symmetry": symmetry_closures(rebuilt.method), "variants": {}}
    for name, method in (("notebook_selected_before_rebuild", selected),
                         ("notebook_displayed_reduced_basis", rebuilt.method),
                         ("direct_default_reduced_basis", direct.method)):
        result["variants"][name] = verify(method, states)
    for name, indices, symmetries in (("bounded_six_fixed_basis", (0, 1, 2), False),
                                      ("bounded_six_two_templates_with_symmetry", (0, 2), True)):
        method, search = bounded_policy(rebuilt.method, indices, symmetries=symmetries,
                                        max_applications=args.max_applications, loops=analysis.loops)
        result["variants"][name] = {**verify(method, states), "search": search}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, variant in result["variants"].items():
        metrics = variant["metrics"]
        print(f"{name}: mean {metrics['mean_htm']:.6f} HTM; worst {metrics['worst_htm']} HTM")


if __name__ == "__main__":
    main()
