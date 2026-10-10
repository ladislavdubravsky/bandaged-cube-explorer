"""Bounded algorithm improvement on certified, small feature orbits.

Only observation states are searched. Full-group membership uses portable
stabilizer certificates, and every original case remains a complete fallback.
Search edge costs are additive heuristics; reported exact method costs exclude
cancellation between successive stage words.
"""

from collections import Counter, defaultdict
from dataclasses import replace
from heapq import heappop, heappush
import json

from .human_methods import _expression_bound, _inverse, _observe, _validate_method
from .isotropy import LoopGenerators, isotropy_loops
from .loop_algorithms import AlgorithmLibrary, LoopExpression, discover_loop_algorithms


_IDENTITY = tuple(range(48))


def _additive_metrics(method):
    costs = method.additive_costs()
    result = {"states": method.group_order, "exact": True, "scope": costs["scope"],
              "boundary_cancellation_included": False, "additive_costs": costs,
              "algorithm_count": len(method.algorithms),
              "definition_htm": sum(a.htm_length for a in method.algorithms),
              "definition_qtm": sum(a.qtm_length for a in method.algorithms),
              "visible_leaf_count": len({key for a in method.algorithms
                                         for key in a.expression.memory_keys}),
              "original_leaf_count": len({i for a in method.algorithms for i in a.base_ids})}
    for metric in ("htm", "qtm"):
        record = costs[metric]
        result["mean_" + metric] = record["mean"]
        result["worst_" + metric] = record["worst"]
        result["total_" + metric] = (method.group_order * record["mean_numerator"]
                                   // record["mean_denominator"])
    return result


def _successor(observation, action, inventory):
    destination = action.destinations[observation[0]]
    if len(observation) == 1:
        return (destination,)
    order = inventory.blocks[observation[0]].orientation_order
    return destination, (observation[1] + action.phases[observation[0]]) % order


def _orbit_edges(candidates, stage, inventory, maximum):
    """Reserve edges for orbit coverage before adding redundant cheap actions."""
    observations = stage.observations
    distinct = {}
    for item in candidates:
        action = inventory.action(item.algorithm.permutation)
        mapping = tuple(_successor(value, action, inventory) for value in observations)
        if mapping == observations:
            continue
        previous = distinct.get(mapping)
        if previous is None or item.key < previous.key:
            distinct[mapping] = item
    mappings = sorted(distinct, key=lambda m: distinct[m].key)
    reached = {stage.solved_observation}
    positions = {value: index for index, value in enumerate(observations)}
    selected = []

    def closure(edges):
        found = set(reached)
        pending = list(found)
        for value in pending:
            for mapping in edges:
                successor = mapping[positions[value]]
                if successor not in found:
                    found.add(successor)
                    pending.append(successor)
        return found

    while mappings and len(selected) < maximum:
        scored = [(len(closure((*selected, mapping))), distinct[mapping].key, mapping)
                  for mapping in mappings]
        _, _, chosen = min(scored, key=lambda value: (-value[0], value[1]))
        selected.append(chosen)
        mappings.remove(chosen)
        reached = closure(selected)
        if len(reached) == len(observations):
            selected.extend(mappings[:maximum - len(selected)])
            break
    return [distinct[mapping] for mapping in selected]


def improve_symbolic_human_method(method, *, mode, max_seed_loops, max_candidates,
                                  max_word_length, rounds, max_states, max_stage_generators,
                                  max_alternatives, max_htm_length, max_expanded_moves,
                                  dictionary=None):
    """Improve a symbolic method without enumerating its reference group.

    Public argument validation is shared with ``improve_human_method``. A
    discovery budget and a feature-orbit search budget share the candidate
    limit. Zero work returns the complete baseline, including long witnesses.
    """
    # The public dispatcher imports this module; defer its result records to
    # avoid a circular import during package initialization.
    from .human_algorithms import (
        HumanAlgorithmAlternative, HumanAlgorithmSearch, _Candidate,
    )

    settings = dict(mode=mode, max_seed_loops=max_seed_loops, max_candidates=max_candidates,
                    max_word_length=max_word_length, rounds=rounds, max_states=max_states,
                    max_stage_generators=max_stage_generators, max_alternatives=max_alternatives,
                    max_htm_length=max_htm_length, max_expanded_moves=max_expanded_moves)
    complete_loops = isotropy_loops(method.reference_shape)
    baseline = _validate_method(method, complete_loops=complete_loops)
    generators = baseline.generators
    if dictionary is not None:
        from .symbolic_dictionary import SymbolicAlgorithmDictionary
        if not isinstance(dictionary, SymbolicAlgorithmDictionary):
            raise TypeError("dictionary must be a SymbolicAlgorithmDictionary")
        dictionary.validate(inventory=baseline.inventory, generators=generators)
        orders = dictionary.metadata
        for field, expected in (("group_order", baseline.group_order),
                                ("quotient_order", baseline.quotient_order),
                                ("orientation_target_order", baseline.kernel_order)):
            if type(orders.get(field)) is not int or orders[field] != expected:
                raise ValueError("dictionary orders disagree with the certified reference group")
    records = {g.id: g for g in generators}
    # Use precisely the saved leaf library: local IDs can differ from a newly
    # explored graph, especially at a nonzero original reference vertex.
    witness_loops = LoopGenerators(generators[0]._owner) if generators else None
    builder = AlgorithmLibrary(witness_loops, (), (), ()) if witness_loops is not None else None
    counts, sources = Counter(), Counter()
    pool, seen = defaultdict(list), set()

    def candidate(algorithm, source):
        algorithm = replace(algorithm, _inventory=baseline.inventory, _generators=generators,
                            _leaf_htm_lengths=tuple((g.id, g.htm_length) for g in generators),
                            _human_score=())
        return _Candidate(algorithm, source, algorithm.expression.structure_cost(generators))

    def add(item):
        choices = pool[item.algorithm.permutation]
        if any(c.algorithm.expression == item.algorithm.expression for c in choices):
            return
        choices.append(item)
        keep = [min(choices, key=lambda c: c.key), min(choices, key=lambda c: c.structured_key)]
        keep.extend(sorted(choices, key=lambda c: c.key))
        retained = []
        for choice in keep:
            if choice not in retained:
                retained.append(choice)
            if len(retained) >= max(2, max_alternatives):
                break
        pool[item.algorithm.permutation] = retained

    def fits(algorithm):
        return (algorithm.htm_length <= max_htm_length and
                _expression_bound(algorithm.expression, records) <= max_expanded_moves)

    def propose(expression, source):
        if counts["candidates_examined"] >= max_candidates:
            counts["candidate_limit_reached"] = 1
            return False
        counts["candidates_examined"] += 1
        sources[source] += 1
        if expression in seen:
            counts["duplicate_expressions"] += 1
            return True
        seen.add(expression)
        if _expression_bound(expression, records) > max_expanded_moves:
            counts["expansion_pruned"] += 1
            return True
        algorithm = builder.build_algorithm(expression, max_expanded_moves=max(1, max_expanded_moves))
        if algorithm.permutation == _IDENTITY:
            counts["identity_candidates"] += 1
        elif algorithm.htm_length > max_htm_length:
            counts["length_pruned"] += 1
        else:
            if algorithm.permutation not in baseline._permutations:
                raise ValueError("discovered loop leaves the certified reference group")
            counts["candidates_built"] += 1
            add(candidate(algorithm, source))
        return True

    fallbacks = {a.id: candidate(a, "baseline") for a in baseline.algorithms}
    for item in fallbacks.values():
        add(item)
    discovery = None
    enabled = bool(generators and max_candidates and (max_seed_loops or dictionary is not None) and
                   max_htm_length and max_expanded_moves)
    if enabled and dictionary is not None:
        for algorithm in dictionary.algorithms:
            if counts["candidates_examined"] >= max_candidates:
                counts["candidate_limit_reached"] = 1
                break
            counts["candidates_examined"] += 1
            sources["shared_dictionary"] += 1
            if fits(algorithm):
                if algorithm.permutation not in baseline._permutations:
                    raise ValueError("dictionary algorithm leaves the certified reference group")
                seen.add(algorithm.expression)
                add(candidate(algorithm, "shared_dictionary"))
                counts["candidates_built"] += 1
            else:
                counts["dictionary_length_pruned"] += 1
    if enabled and dictionary is None:
        discovery_budget = max_candidates if mode == "original" else max(1, max_candidates // 2)
        discovery = discover_loop_algorithms(
            witness_loops, max_seed_loops=max_seed_loops,
            rounds=rounds if mode == "structured" else 0,
            max_candidates=discovery_budget,
            max_algorithms=max(1, discovery_budget), max_htm_length=max_htm_length,
            max_expanded_moves=max_expanded_moves)
        counts["candidates_examined"] = discovery.examined_count
        counts["rounds_completed"] = discovery.rounds_completed
        counts["identity_candidates"] = discovery.identity_count
        counts["duplicate_expressions"] = discovery.duplicate_count
        counts["length_pruned"] = discovery.length_pruned_count
        counts["expansion_pruned"] = discovery.expansion_pruned_count
        sources["standalone_discovery"] = discovery.examined_count
        for algorithm in discovery.algorithms:
            seen.add(algorithm.expression)
            if fits(algorithm):
                add(candidate(algorithm, "standalone_discovery"))
                counts["candidates_built"] += 1
            else:
                counts["expansion_pruned"] += 1
        # Inverses are important edges even when discovery had zero rounds.
        # Admit them once globally, using the same finite proposal limit.
        inverse_sources = [min(choices, key=lambda c: c.key)
                           for choices in tuple(pool.values())]
        for item in sorted(inverse_sources, key=lambda c: c.key):
            if not fits(item.algorithm):
                continue
            if not propose(LoopExpression.power(item.algorithm.expression, -1), "inverse"):
                break

    stages, selected, alternatives, summaries = [], [], [], []
    changed_total = 0
    for stage_index, (stage, certified) in enumerate(zip(baseline.stages,
                                                       baseline._symbolic_chain.stages)):
        # Filtering sifts permutations through a BSGS certificate. It never
        # iterates over the members of the (possibly enormous) stabilizer.
        admissible = [item for effect, choices in pool.items()
                      if effect in certified.group_before for item in choices]
        edges = _orbit_edges((item for item in admissible if fits(item.algorithm)),
                             stage, baseline.inventory, max_stage_generators)
        if (enabled and mode != "original" and max_word_length and edges and
                counts["candidates_examined"] < max_candidates):
            remaining_states = max_states - counts["states_expanded"]
            state_share = remaining_states // max(1, len(baseline.stages) - stage_index)
            actions = [(edge, baseline.inventory.action(edge.algorithm.permutation)) for edge in edges]
            # Depth is part of the label: a cheaper but longer route must not
            # remove a more expensive route with room below the depth limit.
            start = stage.solved_observation, 0
            labels, settled = {start: (0, 0)}, set()
            queue, serial = [(0, 0, 0, start, ())], 0
            expanded = 0
            observations = set(stage.observations)
            while queue and counts["candidates_examined"] < max_candidates:
                if expanded >= state_share:
                    counts["stage_state_share_limit_reached"] = 1
                    if counts["states_expanded"] >= max_states:
                        counts["state_limit_reached"] = 1
                    break
                htm, qtm, _, state, path = heappop(queue)
                if state in settled or labels.get(state) != (htm, qtm):
                    continue
                settled.add(state)
                observation, depth = state
                expanded += 1
                counts["states_expanded"] += 1
                if observation != stage.solved_observation:
                    propose(LoopExpression.power(LoopExpression.sequence(*path), -1), "feature_orbit")
                if depth >= max_word_length:
                    continue
                for edge, action in actions:
                    counts["transitions_examined"] += 1
                    successor = _successor(observation, action, baseline.inventory)
                    if successor not in observations:
                        raise ValueError("stage algorithm leaves its certified observation orbit")
                    next_state = successor, depth + 1
                    cost = htm + edge.algorithm.htm_length, qtm + edge.algorithm.qtm_length
                    if next_state not in labels or cost < labels[next_state]:
                        labels[next_state] = cost
                        serial += 1
                        heappush(queue, (*cost, serial, next_state, (*path, edge.algorithm.expression)))
            # Include newly discovered paths as direct options for this stage.
            admissible = [item for effect, choices in pool.items()
                          if effect in certified.group_before for item in choices]

        by_observation = defaultdict(list)
        for item in admissible:
            observation = _observe(baseline.inventory.action(_inverse(item.algorithm.permutation)),
                                   stage.block_index, stage.feature.kind)
            by_observation[observation].append(item)
        cases, changed, improved, fallback_count = [], 0, 0, 0
        for case in stage.cases:
            if case.algorithm_id is None:
                cases.append(case)
                continue
            fallback = fallbacks[case.algorithm_id]
            choices = [fallback, *by_observation[case.observation]]
            best = min(choices, key=lambda c: c.key)
            if best.key[:2] >= fallback.key[:2]:
                best = fallback
            keep = [best, fallback, min(choices, key=lambda c: c.structured_key)]
            keep.extend(sorted(choices, key=lambda c: c.key))
            retained = []
            for item in keep:
                if item not in retained:
                    retained.append(item)
                if len(retained) >= max_alternatives:
                    break
            alternatives.extend(HumanAlgorithmAlternative(stage.number, case.observation,
                                                          item.algorithm, item.source)
                                for item in retained)
            identifier = f"A{len(selected) + 1}"
            selected.append(replace(best.algorithm, id=identifier))
            cases.append(replace(case, algorithm_id=identifier))
            changed += best.algorithm.turn_sequence != fallback.algorithm.turn_sequence
            improved += best.key[:2] < fallback.key[:2]
            fallback_count += best.source == "baseline"
        changed_total += changed
        summaries.append({"stage_number": stage.number, "cases": stage.case_count,
                          "changed_cases": changed, "improved_cases": improved,
                          "fallback_cases": fallback_count,
                          "admissible_effects": len({item.algorithm.permutation for item in admissible})})
        stages.append(replace(stage, cases=tuple(cases)))

    result = baseline
    if changed_total:
        result = _validate_method(replace(baseline, algorithms=tuple(selected), stages=tuple(stages)),
                                  complete_loops=complete_loops)
    before, after = _additive_metrics(baseline), _additive_metrics(result)
    metadata = {"settings": settings, "backend": "symbolic", "exhaustive_word_search": False,
                "selection": "case physical HTM, QTM; certified feature-orbit membership",
                "macro_search_cost": "additive edge HTM and QTM; heuristic for simplified physical words",
                "preparation_group_elements": 0, "preparation_feature_observations": sum(
                    stage.case_count for stage in baseline.stages),
                "native_loop_count": len(complete_loops),
                "seed_loop_count": 0 if discovery is None else discovery.seed_count,
                "seed_action_count": 0 if discovery is None else len(discovery.shortest),
                "candidates_examined": counts["candidates_examined"],
                "candidates_built": counts["candidates_built"],
                "states_expanded": counts["states_expanded"],
                "transitions_examined": counts["transitions_examined"],
                "attempted_by_source": dict(sorted(sources.items())),
                "candidate_limit_reached": bool(counts["candidate_limit_reached"] or
                                                counts["candidates_examined"] == max_candidates),
                "state_limit_reached": bool(counts["state_limit_reached"]),
                "stage_state_share_limit_reached": bool(counts["stage_state_share_limit_reached"]),
                "identity_candidates": counts["identity_candidates"],
                "duplicate_expressions": counts["duplicate_expressions"],
                "length_pruned": counts["length_pruned"], "expansion_pruned": counts["expansion_pruned"],
                "rounds_completed": counts["rounds_completed"], "proposed_stages": summaries,
                "stages": summaries, "accepted": True, "baseline_metrics": before,
                "proposed_metrics": after, "improved_metrics": after,
                "fallback_policy_retained": True, "coverage": result.coverage,
                "discovery_metadata": None if discovery is None else discovery.metadata,
                "dictionary_metadata": None if dictionary is None else dictionary.metadata}
    retained = tuple(item for effect in sorted(pool)
                     for item in sorted(pool[effect], key=lambda c: c.key))
    return HumanAlgorithmSearch(baseline, result, tuple(alternatives), generators,
                                json.dumps(metadata, sort_keys=True, separators=(",", ":")), retained)
