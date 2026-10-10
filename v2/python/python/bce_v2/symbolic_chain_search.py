"""Dictionary-aware feature chains with witnessed, bounded Schreier refinement.

The searched vertices are physical observations, at most 24 for one rigid
block. Exact permutation-group stabilizers supply independent completeness
certificates and unrestricted fallback words throughout the optimization.
"""

from __future__ import annotations

from dataclasses import replace
from heapq import heappop, heappush
import json
from inspect import signature

from .block_actions import _CELL_POINTS
from .gap_backend import GapError, _gap_images, _run_gap, _validated_options
from .human_chains import BlockFeature, plan_human_stages
from .human_methods import (_compile_plan, _expression_bound, _inverse, _observe,
                            _validate_method)
from .loop_algorithms import AlgorithmLibrary, LoopExpression
from .symbolic_chains import _PROGRAM as _CHAIN_PROGRAM, _parse_symbolic_plan_output
from .symbolic_human_algorithms import _additive_metrics, _successor


_BEGIN = "__BCE_DICTIONARY_CHAIN_V1_BEGIN__"
_END = "__BCE_DICTIONARY_CHAIN_V1_END__"
_SEARCH_DEFAULTS = dict(mode="structured", max_seed_loops=32, max_candidates=16000,
                        max_word_length=16, rounds=4, max_states=2000,
                        max_stage_generators=128, max_alternatives=3,
                        max_htm_length=240, max_expanded_moves=960)


_ADAPTIVE_PROGRAM = r'''
BCEAdaptive := rec();;
BCEInverseWord := w -> List(Reversed(w), s -> [s[1],-s[2]]);;
BCEConfigureDictionary := function(images, costs, limits)
    local i, p, add;
    BCEAdaptive.pool := [];
    BCEAdaptive.index := NewDictionary((),true);
    BCEAdaptive.archive := [];
    BCEAdaptive.archiveIndex := NewDictionary((),true);
    BCEAdaptive.limits := limits;
    BCEAdaptive.stats := [];
    BCEAdaptive.evaluations := 0;
    BCEAdaptive.added := 0;
    BCEAdaptive.truncated := 0;
    BCEAdaptive.remaining := limits[2];
    add := function(p,cost,word)
        local found, archived;
        if p = () then return; fi;
        archived := LookupDictionary(BCEAdaptive.archiveIndex,p);
        if archived = fail then
            Add(BCEAdaptive.archive,rec(p:=p,cost:=cost,word:=word));
            AddDictionary(BCEAdaptive.archiveIndex,p,Length(BCEAdaptive.archive));
        elif cost < BCEAdaptive.archive[archived].cost then
            BCEAdaptive.archive[archived] := rec(p:=p,cost:=cost,word:=word);
        fi;
        found := LookupDictionary(BCEAdaptive.index,p);
        if found <> fail then
            if cost < BCEAdaptive.pool[found].cost then
                BCEAdaptive.pool[found] := rec(p:=p,cost:=cost,word:=word);
            fi;
        elif Length(BCEAdaptive.pool) < limits[1] then
            Add(BCEAdaptive.pool,rec(p:=p,cost:=cost,word:=word));
            AddDictionary(BCEAdaptive.index,p,Length(BCEAdaptive.pool));
            BCEAdaptive.added := BCEAdaptive.added+1;
        else
            BCEAdaptive.truncated := BCEAdaptive.truncated+1;
        fi;
    end;
    BCEAdaptive.add := add;
    for i in [1..Length(images)] do
        p := PermList(images[i]);
        add(p,costs[i],[[i-1,1]]);
        add(p^-1,costs[i],[[i-1,-1]]);
    od;
end;;

BCEOrbitWords := function(orbit,point,action,pool)
    local n, distances, words, perms, done, start, i, next, eligible,
          best, j, entry, image, cost;
    n := Length(orbit);
    distances := List([1..n],i -> 1000000000);
    words := List([1..n],i -> fail); perms := List([1..n],i -> fail);
    done := [];
    start := Position(orbit,point);
    distances[start] := 0; words[start] := []; perms[start] := ();
    for i in [1..n] do
        eligible := Filtered([1..n],j -> not j in done and words[j] <> fail);
        if Length(eligible) = 0 then break; fi;
        best := eligible[1];
        for j in eligible do
            if distances[j] < distances[best] then best := j; fi;
        od;
        Add(done,best);
        for entry in pool do
            image := Position(orbit,action(orbit[best],entry.p));
            cost := distances[best]+entry.cost;
            if cost < distances[image] then
                distances[image] := cost;
                words[image] := Concatenation(words[best],entry.word);
                perms[image] := perms[best]*entry.p;
            fi;
        od;
    od;
    return rec(distances:=distances,words:=words,perms:=perms,
               reached:=Length(done));
end;;

BCEChooseFeature := function(H,points,kind,stageNumber)
    local pool, kinds, candidates, action, block, orbit, paths, missing,
          mean, score, shortlist, entry, next, survivors, remaining,
          futureOrbit, futurePaths, futureGap, futureCost, levels, chosen,
          info, rank;
    pool := Filtered(BCEAdaptive.pool,e -> e.p in H);
    Sort(pool,function(a,b) return a.cost < b.cost; end);
    BCEAdaptive.eligible := pool;
    if kind = 2 then kinds := [0,1]; else kinds := [kind]; fi;
    candidates := [];
    for entry in kinds do
        if entry = 0 then action := OnSets; else action := OnTuples; fi;
        for block in [1..Length(points)] do
            orbit := Orbit(H,points[block],action);
            if Length(orbit) > 1 then
                BCEAdaptive.evaluations := BCEAdaptive.evaluations+1;
                paths := BCEOrbitWords(orbit,points[block],action,pool);
                missing := Length(orbit)-paths.reached;
                mean := Sum(Filtered(paths.distances,d -> d < 1000000000)) / Length(orbit);
                if stageNumber >= BCEAdaptive.limits[4] then
                    score := [Length(orbit),block];
                elif BCEAdaptive.limits[5] = 1 then
                    score := [Length(orbit),missing,mean,block];
                else
                    score := [missing / (Length(orbit)-1),
                              mean / (Log(Float(Length(orbit)))/Log(2.0)),Length(orbit),block];
                fi;
                Add(candidates,rec(kind:=entry,block:=block,orbit:=orbit,
                                   paths:=paths,score:=score,mean:=mean));
            fi;
        od;
    od;
    if Length(candidates) = 0 then return fail; fi;
    Sort(candidates,function(a,b) return a.score < b.score; end);
    chosen := candidates[1];
    # A bounded one-step lookahead compares exact residual feature orbits.
    # Coverage of those orbits is a proxy, never a completeness assertion.
    if stageNumber < BCEAdaptive.limits[4] and BCEAdaptive.limits[5] = 0 then
        shortlist := candidates{[1..Minimum(Length(candidates),BCEAdaptive.limits[6])]};
        rank := fail;
        for info in shortlist do
            if info.kind = 0 then action := OnSets; else action := OnTuples; fi;
            next := Stabilizer(H,points[info.block],action);
            survivors := Filtered(pool,e -> action(points[info.block],e.p) = points[info.block]);
            futureGap := 0; futureCost := 0; levels := 0;
            for block in [1..Length(points)] do
                futureOrbit := Orbit(next,points[block],OnTuples);
                if Length(futureOrbit) > 1 then
                    levels := levels+1;
                    futurePaths := BCEOrbitWords(futureOrbit,points[block],OnTuples,survivors);
                    futureGap := futureGap+(Length(futureOrbit)-futurePaths.reached)/(Length(futureOrbit)-1);
                    futureCost := futureCost+Sum(Filtered(futurePaths.distances,d -> d < 1000000000)) /
                                  Length(futureOrbit)/(Log(Float(Length(futureOrbit)))/Log(2.0));
                fi;
            od;
            score := [info.score[1],info.score[2]+
                      (4*futureGap+futureCost)/Maximum(1,levels),info.score[3],info.block];
            if rank = fail or score < rank then chosen := info; rank := score; fi;
        od;
    fi;
    BCEAdaptive.chosen := chosen;
    return [chosen.kind,chosen.block-1];
end;;

BCENewFeatureStabilizer := function(H,K,point,action,orbit)
    local paths, pool, basis, subgroup, candidate, entry, i, j, p, word,
          cost, proposals, generated, reached, beforeCount;
    pool := BCEAdaptive.eligible;
    paths := BCEAdaptive.chosen.paths;
    basis := []; subgroup := GroupWithGenerators([],());
    StabChain(subgroup,rec(random:=1000));
    # A short exact generating subset keeps the Schreier proposal count small
    # and retains odd coupled parity actions when the dictionary supplies them.
    for entry in pool do
        if not entry.p in subgroup then
            Add(basis,entry);
            subgroup := GroupWithGenerators(List(basis,e -> e.p),());
            StabChain(subgroup,rec(random:=1000));
            if Size(subgroup) = Size(H) then break; fi;
        fi;
    od;
    # Retire words that cannot survive the selected feature. Their recipes
    # remain in the archive for policies at earlier stages, while capacity is
    # available for newly protected words and late coupled parity bridges.
    BCEAdaptive.pool := Filtered(pool,e -> e.p in K);
    BCEAdaptive.index := NewDictionary((),true);
    for i in [1..Length(BCEAdaptive.pool)] do
        AddDictionary(BCEAdaptive.index,BCEAdaptive.pool[i].p,i);
    od;
    beforeCount := Length(BCEAdaptive.archive); proposals := 0;
    for i in [1..Length(orbit)] do
        if paths.words[i] <> fail then
            for entry in basis do
                j := Position(orbit,action(orbit[i],entry.p));
                if paths.words[j] <> fail then
                    if BCEAdaptive.remaining = 0 then break; fi;
                    proposals := proposals+1;
                    BCEAdaptive.remaining := BCEAdaptive.remaining-1;
                    cost := paths.distances[i]+entry.cost+paths.distances[j];
                    if cost <= BCEAdaptive.limits[3] then
                        p := paths.perms[i]*entry.p*paths.perms[j]^-1;
                        if not p in K then Error("dictionary Schreier word leaves exact stabilizer"); fi;
                        word := Concatenation(paths.words[i],entry.word,BCEInverseWord(paths.words[j]));
                        BCEAdaptive.add(p,cost,word);
                        BCEAdaptive.add(p^-1,cost,BCEInverseWord(word));
                    fi;
                fi;
            od;
        fi;
        if BCEAdaptive.remaining = 0 then break; fi;
    od;
    Add(BCEAdaptive.stats,[BCEAdaptive.chosen.kind,BCEAdaptive.chosen.block-1,
        Length(orbit),paths.reached,Length(pool),Length(basis),Size(subgroup),Size(H),
        Length(BCEAdaptive.archive)-beforeCount,proposals]);
end;;

BCEExportDictionaryChain := function()
    Print("__BCE_DICTIONARY_CHAIN_V1_BEGIN__\n");
    Print("[",List(BCEAdaptive.archive,e -> [ListPerm(e.p,48)-1,e.cost,e.word]),
          ",",BCEAdaptive.stats,",",BCEAdaptive.evaluations,",",BCEAdaptive.truncated,"]\n");
    Print("__BCE_DICTIONARY_CHAIN_V1_END__\n");
end;;
'''


def _bounded_integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _adaptive_plan(analysis, algorithms, *, kind, preference, max_expansions,
                   beam_width, max_pool=4096, max_schreier=1024,
                   max_htm_length=120, max_expanded_moves=960,
                   gap_executable="gap", timeout=None):
    executable, timeout = _validated_options(gap_executable, timeout)
    generators = tuple(analysis.loops.generators)
    blocks = analysis.block_inventory.blocks
    points = [sorted(p+1 for cell in b.cells for p in _CELL_POINTS[cell]) for b in blocks]
    projections = [[d+1 for d in g.block_action.destinations] for g in generators]
    limits = [max_pool, max_schreier, max_htm_length, max_expansions,
              int(preference == "recognition"), max(1, min(beam_width,4))]
    arguments = [_gap_images(tuple(g.permutation for g in generators)),
                 json.dumps(projections), json.dumps(points), json.dumps([kind]), "false"]
    configure = "BCEConfigureDictionary(" + ",".join((
        _gap_images(tuple(a.permutation for a in algorithms)),
        json.dumps([a.htm_length for a in algorithms]), json.dumps(limits))) + ");;\n"
    output = _run_gap(_CHAIN_PROGRAM + _ADAPTIVE_PROGRAM + configure +
                      "BCESymbolicChain(" + ",".join(arguments) + ");;\n" +
                      "BCEExportDictionaryChain();;\nQUIT;\n", executable, timeout,
                      "dictionary-aware symbolic chain search")
    plan = _parse_symbolic_plan_output(output, analysis, "manual")
    lines = output.splitlines()
    if lines.count(_BEGIN) != 1 or lines.count(_END) != 1:
        raise GapError("missing dictionary-chain search result markers")
    try:
        records, stats, evaluations, truncated = json.loads(
            "".join(lines[lines.index(_BEGIN)+1:lines.index(_END)]))
    except (ValueError, TypeError) as error:
        raise GapError("malformed dictionary-chain search result") from error
    builder = AlgorithmLibrary(analysis.loops, (), (), ())
    by_effect = {a.permutation: a for a in algorithms}
    roots = {g.id:g for g in generators}
    pruned = 0
    for permutation, cost, word in records:
        expression = LoopExpression.sequence(*(LoopExpression.power(algorithms[index].expression, exponent)
                                               for index, exponent in word))
        if _expression_bound(expression, roots) > max_expanded_moves:
            pruned += 1
            continue
        algorithm = builder.build_algorithm(expression,max_expanded_moves=max_expanded_moves)
        if algorithm.permutation != tuple(permutation):
            raise GapError("derived dictionary word fails original-loop witness verification")
        previous = by_effect.get(algorithm.permutation)
        if previous is None or (algorithm.htm_length,algorithm.qtm_length) < (previous.htm_length,previous.qtm_length):
            by_effect[algorithm.permutation] = algorithm
    metadata = {"stages": [dict(zip(("kind", "block_index", "case_count", "dictionary_cases_reached",
                                    "eligible_algorithms", "short_generating_subset_size", "subset_order",
                                    "exact_group_order", "new_schreier_effects", "schreier_proposals"), row))
                           for row in stats],
                "stage_edges_evaluated": evaluations, "pool_limit_rejections": truncated,
                "expansion_pruned": pruned, "retained_algorithms": len(by_effect),
                "kind_scope": "full_blocks" if kind == 1 else "placements_and_full_blocks",
                "optimized_prefix_decision_limit":max_expansions,
                "schreier_proposal_limit":max_schreier,
                "schreier_max_htm_length":max_htm_length,
                "schreier_max_expanded_moves":max_expanded_moves,
                "dictionary_span_scope":"GAP working pool before exported-word expansion filtering"}
    for i,stage in enumerate(metadata["stages"]):
        stage["dictionary_spans_before"] = stage["subset_order"] == stage["exact_group_order"]
        after = metadata["stages"][i+1]["subset_order"] if i+1 < len(metadata["stages"]) else 1
        stage["retained_next_span_order"] = after
        stage["dictionary_spans_after"] = after == plan.stages[i].order_after
    return plan, tuple(by_effect.values()), metadata


def _select_edges(induced, solved, observations, maximum):
    """Select diverse induced actions using cached block effects and costs."""
    positions = {value:i for i,value in enumerate(observations)}
    selected = []
    remaining = sorted(induced,key=lambda key:induced[key][2])

    def closure(mappings):
        found, todo = {solved}, [solved]
        for value in todo:
            for mapping in mappings:
                image = mapping[positions[value]]
                if image not in found:
                    found.add(image); todo.append(image)
        return len(found)

    while remaining and len(selected) < maximum:
        chosen = min(remaining,key=lambda key:(-closure((*selected,key)),induced[key][2]))
        selected.append(chosen); remaining.remove(chosen)
        if closure(selected) == len(observations):
            selected.extend(remaining[:maximum-len(selected)])
            break
    return [(induced[key][0],induced[key][1]) for key in selected]


def _compile_dictionary_policy(plan, algorithms, settings):
    """Shortest additive macro paths on small observations, with full fallback."""
    baseline = _compile_plan(plan)
    records = {g.id:g for g in baseline.generators}
    builder = AlgorithmLibrary(plan.analysis.loops, (), (), ())
    used_algorithms = {a.id:a for a in baseline.algorithms}
    new_stages, changed, expansions = [], 0, 0
    next_id = len(used_algorithms)+1
    catalog = []
    for algorithm in algorithms:
        if (algorithm.htm_length <= settings["max_htm_length"] and
                _expression_bound(algorithm.expression,records) <= settings["max_expanded_moves"]):
            if algorithm.permutation not in plan.group:
                raise ValueError("shared algorithm leaves the certified reference group")
            action = baseline.inventory.action(algorithm.permutation)
            key = (algorithm.htm_length,algorithm.qtm_length,
                   algorithm.expression.structure_cost(baseline.generators),algorithm.expression.render())
            catalog.append((algorithm,action,key))
    for stage, certified in zip(baseline.stages, plan.stages):
        # H_i is the exact intersection of the preceding feature stabilizers.
        # With root membership certified once, these cached feature checks
        # are equivalent to sifting every candidate through every H_i again.
        earlier = baseline.stages[:stage.number-1]
        eligible = [(algorithm,action,key) for algorithm,action,key in catalog
                    if all(_observe(action,previous.block_index,previous.feature.kind)
                           == previous.solved_observation for previous in earlier)]
        # Retain a cheapest representative for each induced feature action.
        induced = {}
        for algorithm,action,cost_key in eligible:
            mapping = tuple(_successor(o,action,baseline.inventory) for o in stage.observations)
            previous = induced.get(mapping)
            if previous is None or cost_key < previous[2]:
                induced[mapping] = (algorithm,action,cost_key)
        edges = _select_edges(induced,stage.solved_observation,stage.observations,
                              settings["max_stage_generators"])
        solved = stage.solved_observation
        labels = {(solved,0):(0,0,LoopExpression.sequence())}
        heap = [(0,0,0,solved)]
        best = {solved:(0,0,LoopExpression.sequence())}
        # Direct dictionary cases are available even with a zero graph-search
        # budget. Longer compositions remain controlled by the search limits.
        for algorithm,action in edges:
            image = _successor(solved,action,baseline.inventory)
            value = (algorithm.htm_length,algorithm.qtm_length,algorithm.expression)
            if image not in best or value[:2] < best[image][:2]:
                best[image] = value
        while (heap and settings["mode"] != "original" and
               expansions < settings["max_states"]):
            htm,qtm,depth,observation = heappop(heap)
            stored = labels.get((observation,depth))
            if stored is None or (htm,qtm) != stored[:2]:
                continue
            expansions += 1
            if depth >= settings["max_word_length"]:
                continue
            for algorithm,action in edges:
                image = _successor(observation,action,baseline.inventory)
                costs = htm+algorithm.htm_length,qtm+algorithm.qtm_length
                label_key = image,depth+1
                if any(point == image and earlier_depth <= depth+1 and label[:2] <= costs
                       for (point,earlier_depth),label in labels.items()):
                    continue
                previous = labels.get(label_key)
                if previous is not None and previous[:2] <= costs:
                    continue
                expression = LoopExpression.sequence(stored[2],algorithm.expression)
                labels[label_key] = (*costs,expression)
                if image not in best or costs < best[image][:2]:
                    best[image] = (*costs,expression)
                heappush(heap,(*costs,depth+1,image))
        cases = []
        for case in stage.cases:
            if case.algorithm_id is None or case.observation not in best:
                cases.append(case); continue
            expression = LoopExpression.power(best[case.observation][2],-1)
            if _expression_bound(expression,records) > settings["max_expanded_moves"]:
                cases.append(case); continue
            algorithm = builder.build_algorithm(expression,max_expanded_moves=settings["max_expanded_moves"])
            if algorithm.htm_length > settings["max_htm_length"]:
                cases.append(case); continue
            fallback = used_algorithms[case.algorithm_id]
            if (algorithm.htm_length,algorithm.qtm_length) >= (fallback.htm_length,fallback.qtm_length):
                cases.append(case); continue
            algorithm = replace(algorithm,id=f"A{next_id}"); next_id += 1
            used_algorithms[algorithm.id] = algorithm
            cases.append(replace(case,algorithm_id=algorithm.id)); changed += 1
        new_stages.append(replace(stage,cases=tuple(cases)))
    used = {case.algorithm_id for stage in new_stages for case in stage.cases if case.algorithm_id}
    method = _validate_method(replace(baseline,stages=tuple(new_stages),
                                      algorithms=tuple(a for key,a in used_algorithms.items() if key in used)),
                              complete_loops=plan.analysis.loops)
    return baseline, method, {"cases_improved":changed,"observation_states_expanded":expansions,
                              "state_limit_reached":expansions >= settings["max_states"]}


def select_symbolic_human_chain(initial, *, strategy="placement_then_orientation", manual_features=None,
                                preference="execution", beam_width=4, max_expansions=64, max_methods=16,
                                discovery_options=None, dictionary=None, dictionary_options=None,
                                max_group_elements=None, gap_executable="gap", timeout=None, root=None):
    """Compare complete symbolic controls and bounded dictionary-aware chains."""
    from .human_chain_search import HumanChainCandidate, HumanChainSearch
    from .symbolic_dictionary import SymbolicAlgorithmDictionary, discover_symbolic_dictionary

    if max_group_elements is not None:
        raise ValueError("max_group_elements only applies to backend='explicit'")
    if strategy not in ("placement_then_orientation","fully_solve_each_block"):
        raise ValueError("chain search strategy must name an automatic baseline")
    if preference not in ("execution","recognition"):
        raise ValueError("preference must be execution or recognition")
    for name,value,minimum in (("beam_width",beam_width,1),("max_expansions",max_expansions,0),
                               ("max_methods",max_methods,0)):
        _bounded_integer(value,name,minimum)
    if dictionary is not None and not isinstance(dictionary,SymbolicAlgorithmDictionary):
        raise TypeError("dictionary must be a SymbolicAlgorithmDictionary")
    if dictionary_options is not None and not isinstance(dictionary_options,dict):
        raise TypeError("dictionary_options must be a dictionary or None")
    if dictionary is not None and dictionary_options is not None:
        raise ValueError("dictionary_options cannot be supplied with a prepared dictionary")
    if dictionary_options is not None:
        allowed = set(signature(discover_symbolic_dictionary).parameters)-{"initial"}
        if set(dictionary_options)-allowed:
            raise ValueError("unknown dictionary option")
        for name,value in dictionary_options.items():
            if name not in ("gap_executable","timeout"):
                _bounded_integer(value,name,1 if name in (
                    "max_algorithms","max_htm_length","max_expanded_moves") else 0)
        _validated_options(dictionary_options.get("gap_executable",gap_executable),
                           dictionary_options.get("timeout",timeout))
    if discovery_options is not None and not isinstance(discovery_options,dict):
        raise TypeError("discovery_options must be a dictionary or None")
    supplied = dict(discovery_options or {})
    if set(supplied)-set(_SEARCH_DEFAULTS):
        raise ValueError("unknown discovery option")
    settings = {**_SEARCH_DEFAULTS,**supplied}
    if settings["mode"] not in ("original","shallow","structured"):
        raise ValueError("unknown discovery mode")
    for name,value in settings.items():
        if name != "mode":
            _bounded_integer(value,name,1 if name == "max_alternatives" else 0)
    if manual_features is not None:
        manual_features = tuple(manual_features)
        if any(not isinstance(f,BlockFeature) for f in manual_features):
            raise TypeError("manual_features must contain BlockFeature instances")
    first = plan_human_stages(initial,strategy="placement_then_orientation",backend="symbolic",
                              gap_executable=gap_executable,timeout=timeout,root=root)
    plans = [first,plan_human_stages(first.analysis,strategy="fully_solve_each_block",backend="symbolic",
                                    gap_executable=gap_executable,timeout=timeout,root=root)]
    analysis = plans[0].analysis
    if dictionary is None:
        options = dict(dictionary_options or {})
        options.setdefault("max_candidates",settings["max_candidates"]//2)
        options.setdefault("rounds",settings["rounds"])
        options.setdefault("max_seed_loops",settings["max_seed_loops"])
        options.setdefault("max_conjugates",settings["max_candidates"]//2)
        options.setdefault("gap_executable",gap_executable)
        options.setdefault("timeout",timeout)
        for name in ("max_htm_length","max_expanded_moves"):
            if name in supplied and settings[name] > 0:
                options.setdefault(name,settings[name])
        if any(not settings[name] for name in (
                "max_candidates","max_seed_loops","max_htm_length","max_expanded_moves")):
            options.update(max_candidates=0,rounds=0,max_conjugates=0)
        dictionary = discover_symbolic_dictionary(analysis,**options)
    elif dictionary_options is not None:
        raise ValueError("dictionary_options cannot be supplied with a prepared dictionary")
    if not isinstance(dictionary,SymbolicAlgorithmDictionary):
        raise TypeError("dictionary must be a SymbolicAlgorithmDictionary")
    dictionary.validate(inventory=analysis.block_inventory,generators=analysis.loops.generators)
    declared = dictionary.metadata
    if (any(type(declared[key]) is not int for key in
            ("group_order","quotient_order","orientation_target_order")) or
            declared["group_order"] != plans[0].group_order or
            declared["quotient_order"] != plans[0].quotient_order or
            declared["orientation_target_order"] != plans[0].kernel_order):
        raise ValueError("dictionary exact-order metadata disagrees with the certified reference group")
    roots = {g.id:g for g in analysis.loops.generators}
    algorithms = tuple(a for a in dictionary.algorithms[:settings["max_candidates"]]
                       if a.htm_length <= settings["max_htm_length"] and
                       _expression_bound(a.expression,roots) <= settings["max_expanded_moves"])
    candidates, metadata = [], {"backend":"symbolic", "coverage":"certified",
                                "rank_scope":"exact uniform-group additive HTM before boundary cancellation",
                                "exhaustive_chain_search":False,"human_reviewed":False,
                                "settings":dict(strategy=strategy,preference=preference,beam_width=beam_width,
                                                max_expansions=max_expansions,max_methods=max_methods,
                                                discovery_options=settings),
                                "discovery":dictionary.metadata,"adaptive_chains":[],
                                "effective_search_limits":{
                                    "adaptive_kind_count":min(max_methods,2),
                                    "lookahead_candidate_count":min(beam_width,4),
                                    "dictionary_admission_limit":settings["max_candidates"],
                                    "dictionary_effects_admitted":len(algorithms),
                                    "node_budget_scope":"optimized feature-prefix decisions; complete continuation is retained",
                                    "work_budget_scope":"dictionary mining, bounded setup closure and adaptive Schreier proposals are reported separately"}}

    def add(method,source):
        metrics = _additive_metrics(method)
        metrics.update(stage_count=len(method.stages),max_case_count=max((s.case_count for s in method.stages),default=0),
                       case_count_sum=sum(s.case_count for s in method.stages),
                       additive_mean_htm=metrics["mean_htm"],
                       original_leaf_htm=sum(g.htm_length for g in method.generators))
        candidates.append(HumanChainCandidate(f"C{len(candidates)+1}",source,method,
                                              json.dumps(metrics,sort_keys=True)))

    baselines = {}
    for plan in plans:
        raw, improved, stats = _compile_dictionary_policy(plan,algorithms,settings)
        baselines[plan.strategy] = raw
        add(raw,"fallback:"+plan.strategy)
        add(improved,"dictionary:"+plan.strategy)
    if manual_features is not None:
        plan = plan_human_stages(analysis,strategy="manual",features=manual_features,
                                 backend="symbolic",gap_executable=gap_executable,timeout=timeout)
        raw,improved,stats = _compile_dictionary_policy(plan,algorithms,settings)
        add(raw,"fallback:manual"); add(improved,"dictionary:manual")
    if algorithms and max_expansions and max_methods:
        remaining = max_expansions
        remaining_proposals = max(0,settings["max_candidates"]-len(algorithms))
        for kind in (1,2)[:min(max_methods,2)]:
            if remaining <= 0:
                break
            plan,pool,adaptive_stats = _adaptive_plan(
                analysis,algorithms,kind=kind,preference=preference,
                max_expansions=remaining,beam_width=beam_width,
                max_pool=max(2,min(4096,2*settings["max_candidates"])),
                max_schreier=remaining_proposals,
                max_htm_length=settings["max_htm_length"],
                max_expanded_moves=settings["max_expanded_moves"],
                gap_executable=gap_executable,timeout=timeout)
            raw,improved,stats = _compile_dictionary_policy(plan,pool,settings)
            add(raw,f"fallback:adaptive:{kind}")
            add(improved,f"dictionary:adaptive:{kind}")
            metadata["adaptive_chains"].append({**adaptive_stats,**stats})
            remaining -= min(remaining,len(plan.stages))
            remaining_proposals -= sum(row["schreier_proposals"] for row in adaptive_stats["stages"])
    execution = ("mean_htm","worst_htm","max_case_count","case_count_sum","definition_htm","stage_count")
    recognition = ("max_case_count","case_count_sum","mean_htm","worst_htm","definition_htm","stage_count")
    dimensions = execution
    frontier = tuple(c.id for c in candidates if not any(
        all(o.metrics[k] <= c.metrics[k] for k in dimensions) and
        any(o.metrics[k] < c.metrics[k] for k in dimensions) for o in candidates if o.id != c.id))
    by_id = {c.id:c for c in candidates}
    selected = min((by_id[key] for key in frontier),key=lambda c:(
        *(c.metrics[k] for k in (execution if preference == "execution" else recognition)),c.id))
    metadata.update(selected_source=selected.source,additional_methods_evaluated=len(metadata["adaptive_chains"]),
                    nodes_expanded=max_expansions-remaining if algorithms and max_expansions and max_methods else 0,
                    adaptive_schreier_proposals=sum(row["schreier_proposals"] for m in metadata["adaptive_chains"]
                                                    for row in m["stages"]),
                    stage_edges_evaluated=sum(m["stage_edges_evaluated"] for m in metadata["adaptive_chains"]))
    return HumanChainSearch(baselines[strategy],selected.method,tuple(candidates),frontier,
                            selected.id,json.dumps(metadata,sort_keys=True))
