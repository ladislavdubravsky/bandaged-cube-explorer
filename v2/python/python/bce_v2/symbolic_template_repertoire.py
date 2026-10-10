"""Shared exact algorithm bodies for certified symbolic feature chains.

Only the small case tables and witnessed expression trees are inspected. The
group certificate supplies coverage; template selection has separate bounds.
"""

from collections import Counter
from dataclasses import replace
from functools import lru_cache
import json
from math import isfinite

from ._moves import _simplified_moves
from .human_chains import _inverse_moves
from .human_methods import HumanMethod, _expression_bound, _require, _validate_method
from .human_repertoire import HumanMacroRecipe, HumanRepertoireMacro, _same_json
from .isotropy import LoopGenerators, isotropy_loops
from .loop_algorithms import LoopAlgorithm, LoopExpression
from .loop_rotations import bandage_symmetries, inverse_rotation, rotate_moves


_DIMENSIONS = ("description_score", "instruction_symbols", "macro_count", "mean_htm",
               "worst_htm", "max_case_count", "case_count_sum")
_PREFERENCES = {
    "memory": _DIMENSIONS,
    "execution": ("mean_htm", "worst_htm", *_DIMENSIONS[:3], *_DIMENSIONS[5:]),
    "recognition": (*_DIMENSIONS[5:], *_DIMENSIONS[:3], *_DIMENSIONS[3:5]),
}
_SCOPE = "exact uniform-group additive costs before cancellation between stages"
def _sequence(*children):
    """Normalize adjacent repeated calls without changing their physical word."""
    result = []
    for child in children:
        for part in child.children if child.kind == "sequence" else (child,):
            body, power = ((part.children[0], part.exponent)
                           if part.kind == "power" else (part, 1))
            if result:
                previous = result[-1]
                old_body, old_power = ((previous.children[0], previous.exponent)
                    if previous.kind == "power" else (previous, 1))
                if body == old_body:
                    result.pop()
                    power += old_power
            if power:
                result.append(HumanMacroRecipe.power(body, power))
    return result[0] if len(result) == 1 else HumanMacroRecipe.sequence(*result)


def _human_symbols(recipe, records):
    """Native face turns and their signed powers use ordinary turn notation."""
    from .human_instruction_render import _expand
    if recipe.kind == "macro":
        return 1
    if recipe.kind in ("power", "rotated"):
        body = recipe.children[0]
        while body.kind in ("power", "rotated"):
            body = body.children[0]
        if body.kind == "macro" and len(records[body.macro_id].algorithm.turn_sequence.split()) == 1:
            return len(_expand(recipe, records, 100000).split())
    return int(recipe.kind != "sequence") + sum(_human_symbols(c, records) for c in recipe.children)


class _Bodies:
    def __init__(self, method, allow_symmetry):
        self.method = method
        self.rotations = ("", *bandage_symmetries(method.reference_shape)) if allow_symmetry else ("",)
        self.roots = {g.id: g for g in method.generators}
        self.loops = LoopGenerators(method.generators[0]._owner) if method.generators else None
        self.witnesses = {}
        self.word_cache, self.alias_cache = {}, {}

    def word(self, expression):
        if expression not in self.word_cache:
            self.word_cache[expression] = (expression.moves if expression.kind == "turns" else
                _simplified_moves(expression.expanded_moves(self.loops,
                    max_expanded_moves=max(1, _expression_bound(expression, self.roots))).split()))
        return self.word_cache[expression]

    def alias(self, expression):
        if expression in self.alias_cache:
            return self.alias_cache[expression]
        word = self.word(expression)
        if not word:
            return "", "", 1
        options = []
        for rotation in self.rotations:
            rotated = rotate_moves(word, rotation)
            options.extend(((rotated, rotation, 1), (_inverse_moves(rotated), rotation, -1)))
        canonical, rotation, sign = min(options, key=lambda item:
            (item[0], len(item[1].split()), item[1], -item[2]))
        if canonical not in self.witnesses:
            witness = LoopExpression.rotated(rotation, expression) if rotation else expression
            if sign == -1:
                witness = LoopExpression.power(witness, -1)
            self.witnesses[canonical] = witness
        self.alias_cache[expression] = canonical, inverse_rotation(rotation), sign
        return self.alias_cache[expression]

    def definitions(self, selected):
        lengths = tuple((g.id, g.htm_length) for g in self.method.generators)
        result = []
        for word in sorted(selected, key=lambda word: (len(word.split()), word)):
            identifier = f"M{len(result) + 1}"
            expression = self.witnesses[word]
            result.append(HumanRepertoireMacro(identifier, LoopAlgorithm(identifier, expression,
                expression.evaluate(self.method.generators), word, self.method.inventory,
                lengths, self.method.generators)))
        return tuple(result)

    def recipes(self, selected):
        definitions = self.definitions(selected)
        names = {macro.algorithm.turn_sequence: macro.id for macro in definitions}

        @lru_cache(maxsize=None)
        def convert(expression):
            physical = self.word(expression)
            if physical in names:
                return HumanMacroRecipe.macro(names[physical])
            reverse = _inverse_moves(physical)
            if reverse in names:
                return HumanMacroRecipe.power(HumanMacroRecipe.macro(names[reverse]), -1)
            word, rotation, sign = self.alias(expression)
            if not word:
                return HumanMacroRecipe.sequence()
            if word in names:
                recipe = HumanMacroRecipe.power(HumanMacroRecipe.macro(names[word]), sign)
                return HumanMacroRecipe.rotated(rotation, recipe) if rotation else recipe
            if expression.kind == "turns":
                if self.word(expression.children[0]) == self.word(expression):
                    return convert(expression.children[0])
                raise ValueError("opaque physical word requires a template definition")
            if expression.kind == "loop":
                raise ValueError("original loop requires a template definition")
            children = tuple(convert(child) for child in expression.children)
            if expression.kind == "sequence":
                return _sequence(*children)
            if expression.kind == "power":
                return HumanMacroRecipe.power(children[0], expression.exponent)
            if expression.kind == "rotated":
                return HumanMacroRecipe.rotated(expression.rotation, children[0])
            return HumanMacroRecipe(expression.kind, children)

        algorithms = {a.id: convert(a.expression) for a in self.method.algorithms}
        recipes = tuple(tuple(algorithms[c.algorithm_id] if c.algorithm_id is not None else
                              HumanMacroRecipe.sequence() for c in stage.cases)
                        for stage in self.method.stages)
        return definitions, recipes

    def fallback(self):
        selected = {self.alias(algorithm.expression)[0] for algorithm in self.method.algorithms}
        selected.discard("")
        return self.recipes(selected)

    def shared(self, settings, templates):
        counts, seed_words = Counter(), set()
        for generator in self.method.generators:
            expression = LoopExpression.loop(generator.id)
            word = self.alias(expression)[0]
            if len(generator.turn_sequence.split()) == 1:
                word = generator.turn_sequence
                self.witnesses[word] = expression
            if word:
                seed_words.add(word)
        examined = 0

        def walk(expression, previous_word=None):
            nonlocal examined
            if examined >= settings["max_word_candidates"]:
                return
            examined += 1
            word = self.alias(expression)[0]
            if word and word != previous_word:
                counts[word] += 1
            if expression.kind == "turns" and self.word(expression.children[0]) != self.word(expression):
                seed_words.add(word)
                return
            for child in expression.children:
                walk(child, word)

        for algorithm in self.method.algorithms:
            walk(algorithm.expression)
        for template in templates:
            walk(template.expression)
            counts[self.alias(template.expression)[0]] += 1
        # Required opaque leaves remain available even after the proposal cap.
        def required(expression):
            if expression.kind == "turns" and self.word(expression.children[0]) != self.word(expression):
                seed_words.add(self.alias(expression)[0])
            else:
                for child in expression.children:
                    required(child)
        for algorithm in self.method.algorithms:
            required(algorithm.expression)
        seed_words.discard("")
        selected = set(seed_words)

        def score(words):
            definitions, recipes = self.recipes(words)
            records = {m.id: m for m in definitions}
            return (sum(len(word.split()) for word in words) +
                    sum(_human_symbols(recipe, records) for stage in recipes for recipe in stage))

        current = score(selected)
        @lru_cache(maxsize=None)
        def depth(expression):
            return int(expression.kind not in ("loop", "turns")) + max(
                (depth(child) for child in expression.children), default=0)

        proposals = sorted((word for word, count in counts.items()
                            if count > 1 and word not in selected and
                            len(word.split()) <= settings["chunk_options"]["max_word_moves"] and
                            depth(self.witnesses[word]) <= settings["max_applications"]),
                           key=lambda word: (-(counts[word] - 1) * len(word.split()), word))
        proposals = proposals[:settings["max_word_frontier"]]
        trials = examined_trials = 0
        for _ in range(settings["max_trials"]):
            if not proposals:
                break
            alternatives = []
            for word in proposals:
                examined_trials += 1
                alternatives.append((score(selected | {word}), word))
            value, word = min(alternatives)
            if value >= current:
                break
            selected.add(word)
            proposals.remove(word)
            current = value
            trials += 1
        definitions, recipes = self.recipes(selected)
        return definitions, recipes, {"expression_nodes_examined": examined,
            "expression_limit_reached": int(examined >= settings["max_word_candidates"]),
            "template_trials_examined": examined_trials, "accepted_shared_bodies": trials,
            "shared_body_proposals": len(proposals) + trials,
            "group_elements_enumerated": 0}


def _augment(repertoire, dictionary):
    from .human_repertoire import _repertoire_metrics
    from .template_human_repertoire import _augment_metrics
    result = _augment_metrics(_repertoire_metrics(repertoire.method, repertoire.macros,
        repertoire.stages, {}), repertoire.method, repertoire.stages, dictionary)
    records = {macro.id: macro for macro in repertoire.macros}
    result["instruction_symbols"] = sum(_human_symbols(c.recipe, records)
        for stage in repertoire.stages for c in stage.cases)
    result["learned_body_count"] = sum(m.algorithm.htm_length > 1 for m in repertoire.macros)
    result["max_body_htm"] = max((m.algorithm.htm_length for m in repertoire.macros), default=0)
    result["description_score"] = result["dictionary_score"] + result["instruction_symbols"]
    return result


def _prepare(initial, settings, strategy, features, dictionary, dictionary_options,
             discovery_options, gap_executable, timeout, root):
    if isinstance(initial, HumanMethod):
        if initial.backend != "symbolic" or initial.status != "completed":
            raise ValueError("symbolic template repertoire requires a complete symbolic method")
        if features is not None or strategy != "fully_solve_each_block":
            raise ValueError("a supplied method retains its own baseline features")
        if root is not None and root != initial.root_vertex:
            raise ValueError("root differs from the supplied method reference")
        if settings["select_chain"]:
            raise ValueError("a supplied symbolic method retains its certified chain; select a new chain first")
        if dictionary is not None or dictionary_options is not None or discovery_options is not None:
            raise ValueError("a supplied symbolic method already contains its policy witnesses")
        return initial
    from .human_chain_search import select_human_chain
    from .human_methods import synthesize_human_method
    if not settings["select_chain"]:
        return synthesize_human_method(initial, strategy=strategy, features=features, backend="symbolic",
                                       gap_executable=gap_executable, timeout=timeout, root=root)
    if features is not None:
        raise ValueError("use a supplied symbolic method for an explicitly fixed feature chain")
    options = {"max_candidates": 16000, "max_states": 6000, "max_word_length": 16,
               "max_stage_generators": 128, "max_htm_length": 240, "max_expanded_moves": 960,
               **(discovery_options or {})}
    if dictionary is None:
        dictionary_options = {"max_candidates": 12000, "rounds": 4, "max_algorithms": 1024,
            "max_setup_depth": 2, "max_setup_words": 384, "max_conjugates": 12000,
            "max_htm_length": 80, "max_expanded_moves": 400, **(dictionary_options or {})}
    search = select_human_chain(initial, backend="symbolic", strategy=strategy,
        preference="recognition" if settings["preference"] == "recognition" else "execution",
        beam_width=settings["beam_width"], max_expansions=settings["max_chain_expansions"],
        max_methods=settings["max_chain_methods"], discovery_options=options,
        dictionary=dictionary, dictionary_options=dictionary_options,
        gap_executable=gap_executable, timeout=timeout, root=root)
    return search.method


def symbolic_template_human_repertoire(initial, *, strategy, features, preference,
        allow_symmetry, select_chain, templates, max_trials, max_applications,
        max_word_candidates, max_word_frontier, beam_width, max_chain_expansions,
        max_chain_methods, max_cost_ratio, chunk_options, max_group_elements,
        gap_executable, timeout, root, dictionary, dictionary_options, discovery_options):
    from .symbolic_repertoire_core import build_symbolic_repertoire
    from .template_human_repertoire import _BUDGETS, _CHUNK_OPTIONS, _dictionary
    if max_group_elements is not None:
        raise ValueError("max_group_elements only applies to backend='explicit'")
    if preference not in _PREFERENCES:
        raise ValueError("preference must be memory, execution or recognition")
    if type(allow_symmetry) is not bool:
        raise TypeError("allow_symmetry must be a boolean")
    if select_chain is None:
        select_chain = not isinstance(initial, HumanMethod)
    if type(select_chain) is not bool:
        raise TypeError("select_chain must be a boolean or None")
    settings = dict(preference=preference, allow_symmetry=allow_symmetry, select_chain=select_chain,
        max_trials=max_trials, max_applications=max_applications, max_word_candidates=max_word_candidates,
        max_word_frontier=max_word_frontier, beam_width=beam_width,
        max_chain_expansions=max_chain_expansions, max_chain_methods=max_chain_methods,
        max_cost_ratio=max_cost_ratio)
    for name in _BUDGETS:
        if type(settings[name]) is not int:
            raise TypeError(f"{name} must be an integer")
        if settings[name] < (1 if name in ("beam_width", "max_word_frontier") else 0):
            raise ValueError(f"invalid template-search budget: {name}")
    if type(max_cost_ratio) not in (int, float) or not isfinite(max_cost_ratio) or max_cost_ratio < 1:
        raise ValueError("max_cost_ratio must be finite and at least one")
    if root is not None and type(root) is not int:
        raise TypeError("root must be an integer vertex ID")
    if chunk_options is not None and not isinstance(chunk_options, dict):
        raise TypeError("chunk_options must be a dictionary or None")
    if set(chunk_options or {}) - set(_CHUNK_OPTIONS):
        raise ValueError("unknown chunk option")
    settings["chunk_options"] = {**_CHUNK_OPTIONS, **(chunk_options or {})}
    for name, value in settings["chunk_options"].items():
        if type(value) is not int:
            raise TypeError(f"chunk {name} must be an integer")
        if value < (2 if name in ("min_chunk_length", "max_chunk_length") else 0):
            raise ValueError(f"invalid chunk budget: {name}")
    if settings["chunk_options"]["min_chunk_length"] > settings["chunk_options"]["max_chunk_length"]:
        raise ValueError("minimum chunk length exceeds maximum")
    templates = tuple(templates)
    if any(not isinstance(template, LoopAlgorithm) for template in templates):
        raise TypeError("templates must contain witnessed LoopAlgorithms")
    if discovery_options is not None and not isinstance(discovery_options, dict):
        raise TypeError("discovery_options must be a dictionary or None")
    if dictionary_options is not None and not isinstance(dictionary_options, dict):
        raise TypeError("dictionary_options must be a dictionary or None")
    if dictionary is not None:
        from .symbolic_dictionary import SymbolicAlgorithmDictionary
        if not isinstance(dictionary, SymbolicAlgorithmDictionary):
            raise TypeError("dictionary must be a SymbolicAlgorithmDictionary")
        if dictionary_options is not None:
            raise ValueError("dictionary_options cannot be supplied with a prepared dictionary")
    baseline = _prepare(initial, settings, strategy, features, dictionary, dictionary_options,
                        discovery_options, gap_executable, timeout, root)
    loops = isotropy_loops(baseline.reference_shape)
    _validate_method(baseline, complete_loops=loops)
    for template in templates:
        _require(template._inventory.root_shape == baseline.reference_shape and
                 template._generators == baseline.generators and
                 template.permutation in baseline._symbolic_chain.group,
                 "template refers to a different reference group or original witness library")
        from . import State
        replay = State(baseline.reference_shape).apply(template.turn_sequence)
        _require(replay.shape == baseline.reference_shape and replay.sticker_permutation == template.permutation and
                 template.expression.evaluate(baseline.generators) == template.permutation,
                 "template fails its witnessed physical replay")
    bodies = _Bodies(baseline, allow_symmetry)
    candidates = []

    def consider(definitions, recipes, source):
        repertoire = build_symbolic_repertoire(baseline, definitions, recipes)
        dictionary = _dictionary(baseline.reference_shape, repertoire.macros, settings["chunk_options"])
        candidates.append((f"C{len(candidates) + 1}", source, repertoire, dictionary,
                           _augment(repertoire, dictionary)))

    consider(*bodies.fallback(), "exact_baseline")
    search = {"group_elements_enumerated": 0, "expression_nodes_examined": 0,
              "expression_limit_reached": 0, "template_trials_examined": 0,
              "accepted_shared_bodies": 0, "shared_body_proposals": 0}
    if max_trials and max_word_candidates and max_applications:
        definitions, recipes, search = bodies.shared(settings, templates)
        consider(definitions, recipes, "shared_witnessed_bodies")
    before = candidates[0][4]

    def dominates(first, second):
        return all(first[k] <= second[k] for k in _DIMENSIONS) and any(first[k] < second[k] for k in _DIMENSIONS)
    frontier = [c for c in candidates if not any(dominates(o[4], c[4]) for o in candidates)]
    selected = min(frontier, key=lambda c: (*[c[4][k] for k in _PREFERENCES[preference]], c[0]))
    metadata = {"basis": "templates", "construction": "symbolic_template_search",
        "settings": settings, "coverage": "certified", "human_reviewed": False,
        "exhaustive_repertoire_search": False, "physical_shortest_claim": False,
        "cost_scope": _SCOPE, "policy_scope": "the selected physical case words are retained exactly",
        "search_scope": "bounded shared expression bodies and typed physical chunks; no group enumeration",
        "rotations": list(bodies.rotations), "chunk_dictionary": selected[3].to_dict(),
        "baseline_chunk_dictionary": candidates[0][3].to_dict(), "baseline_metrics": before,
        "selected_metrics": selected[4], "pareto_dimensions": _DIMENSIONS,
        "preference_orders": _PREFERENCES, "selected_id": selected[0],
        "frontier": [c[0] for c in frontier], "search": search,
        "candidates": [{"id": c[0], "source": c[1], "metrics": c[4], "admissible": True}
                       for c in candidates]}
    result = replace(selected[2], _metadata_json=json.dumps(metadata, sort_keys=True, allow_nan=False))
    from .human_repertoire import _validate_repertoire
    return _validate_repertoire(result, complete_loops=loops)


def _validate_symbolic_template_metadata(repertoire, actual, before):
    """Check the saved exact grammar and its measured costs without mining."""
    from .human_chunks import ChunkDictionary
    from .template_human_repertoire import _BUDGETS, _CHUNK_OPTIONS
    metadata = repertoire.metadata
    fields = {"basis", "construction", "settings", "coverage", "human_reviewed",
        "exhaustive_repertoire_search", "physical_shortest_claim", "cost_scope", "policy_scope",
        "search_scope", "rotations", "chunk_dictionary", "baseline_chunk_dictionary",
        "baseline_metrics", "selected_metrics", "pareto_dimensions", "preference_orders",
        "selected_id", "frontier", "search", "candidates"}
    _require(set(metadata) == fields and metadata["basis"] == "templates" and
        metadata["construction"] == "symbolic_template_search" and metadata["coverage"] == "certified" and
        metadata["human_reviewed"] is False and metadata["exhaustive_repertoire_search"] is False and
        metadata["physical_shortest_claim"] is False and metadata["cost_scope"] == _SCOPE and
        metadata["policy_scope"] == "the selected physical case words are retained exactly" and
        metadata["search_scope"] == "bounded shared expression bodies and typed physical chunks; no group enumeration",
        "invalid symbolic template metadata")
    settings = metadata["settings"]
    _require(isinstance(settings, dict) and set(settings) == {"preference", "allow_symmetry", "select_chain",
        "max_cost_ratio", "chunk_options", *_BUDGETS} and settings["preference"] in _PREFERENCES and
        type(settings["allow_symmetry"]) is bool and type(settings["select_chain"]) is bool and
        all(type(settings[k]) is int and settings[k] >= (1 if k in ("beam_width", "max_word_frontier") else 0)
            for k in _BUDGETS), "invalid symbolic template settings")
    _require(type(settings["max_cost_ratio"]) in (int, float) and isfinite(settings["max_cost_ratio"]) and
        settings["max_cost_ratio"] >= 1, "invalid symbolic template cost guard")
    options = settings["chunk_options"]
    _require(isinstance(options, dict) and set(options) == set(_CHUNK_OPTIONS) and
        all(type(v) is int and v >= (2 if k in ("min_chunk_length", "max_chunk_length") else 0)
            for k, v in options.items()) and options["min_chunk_length"] <= options["max_chunk_length"],
        "invalid symbolic chunk budgets")
    bodies = _Bodies(repertoire.baseline, settings["allow_symmetry"])
    _require(metadata["rotations"] == list(bodies.rotations), "saved template symmetries disagree with the bandage")
    _require(repertoire.baseline._symbolic_chain.to_dict() == repertoire.method._symbolic_chain.to_dict(),
             "template projection changes the certified stage chain")

    def check(record, macros):
        dictionary = ChunkDictionary.from_dict(record)
        _require(dictionary.reference_shape == repertoire.method.reference_shape and
            dict(dictionary.search_limits) == options and
            tuple(i for i, _ in dictionary.masters) == tuple(sorted(m.id for m in macros)),
            "saved chunk dictionary reference, limits or master IDs disagree")
        _require(all(dictionary.expand(m.id) == m.algorithm.turn_sequence for m in macros),
                 "saved chunks do not reconstruct their templates")
        return dictionary
    dictionary = check(metadata["chunk_dictionary"], repertoire.macros)
    from .symbolic_repertoire_core import build_symbolic_repertoire
    fallback = build_symbolic_repertoire(repertoire.baseline, *bodies.fallback())
    fallback_dictionary = check(metadata["baseline_chunk_dictionary"], fallback.macros)
    actual, before = _augment(repertoire, dictionary), _augment(fallback, fallback_dictionary)
    _require(_same_json(metadata["selected_metrics"], actual) and
             _same_json(metadata["baseline_metrics"], before), "saved symbolic template metrics disagree")
    # This phase rewrites notation only. Every physical case word is preserved.
    old = {a.id: a for a in repertoire.baseline.algorithms}
    new = {a.id: a for a in repertoire.method.algorithms}
    _require(all(("" if c.algorithm_id is None else old[c.algorithm_id].turn_sequence) ==
                 ("" if d.algorithm_id is None else new[d.algorithm_id].turn_sequence)
                 for s, t in zip(repertoire.baseline.stages, repertoire.method.stages)
                 for c, d in zip(s.cases, t.cases)), "symbolic templates change a physical case correction")
    _require(_same_json(metadata["pareto_dimensions"], _DIMENSIONS) and
             _same_json(metadata["preference_orders"], _PREFERENCES), "invalid symbolic template objectives")
    candidates = metadata["candidates"]
    _require(isinstance(candidates, list) and candidates, "missing symbolic template candidates")
    for index, candidate in enumerate(candidates, 1):
        _require(isinstance(candidate, dict) and set(candidate) == {"id", "source", "metrics", "admissible"} and
            candidate["id"] == f"C{index}" and isinstance(candidate["source"], str) and candidate["admissible"] is True and
            isinstance(candidate["metrics"], dict) and set(candidate["metrics"]) == set(actual) and
            all(type(v) in (int, float) and isfinite(v) and v >= 0 for v in candidate["metrics"].values()),
            "invalid symbolic template candidate")
    _require(candidates[0]["source"] == "exact_baseline" and _same_json(candidates[0]["metrics"], before),
             "saved symbolic template fallback disagrees")
    frontier = [c for c in candidates if not any(all(o["metrics"][k] <= c["metrics"][k] for k in _DIMENSIONS) and
        any(o["metrics"][k] < c["metrics"][k] for k in _DIMENSIONS) for o in candidates)]
    selected = min(frontier, key=lambda c: (*[c["metrics"][k] for k in _PREFERENCES[settings["preference"]]], c["id"]))
    _require(metadata["frontier"] == [c["id"] for c in frontier] and metadata["selected_id"] == selected["id"] and
        _same_json(selected["metrics"], actual), "saved symbolic template selection disagrees")
    _require(isinstance(metadata["search"], dict) and all(type(v) is int and v >= 0
        for v in metadata["search"].values()) and metadata["search"].get("group_elements_enumerated") == 0,
        "invalid symbolic template search diagnostics")
    search = metadata["search"]
    _require(set(search) == {"group_elements_enumerated", "expression_nodes_examined", "expression_limit_reached",
        "template_trials_examined", "accepted_shared_bodies", "shared_body_proposals"} and
        search["expression_nodes_examined"] <= settings["max_word_candidates"] and
        search["accepted_shared_bodies"] <= settings["max_trials"] and
        search["shared_body_proposals"] <= settings["max_word_frontier"] and
        search["template_trials_examined"] <= settings["max_trials"] * settings["max_word_frontier"] and
        search["expression_limit_reached"] in (0, 1), "symbolic template search exceeds its saved budgets")
