"""Shared witnessed masters and terminating recognition rules for fixed stages."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from itertools import zip_longest
import json
from math import isfinite
from pathlib import Path

from . import State
from ._moves import _simplified_moves
from .human_algorithms import _metrics, _stage_groups
from .human_diagram_modes import DiagramMode
from .human_chains import _inverse_moves
from .human_move_notation import _conjugation_notation
from .human_methods import (HumanMethod, _expression_bound, _inverse, _observe,
                            _require, _then, _validate_method)
from .isotropy import isotropy_loops
from .loop_algorithms import LoopAlgorithm, LoopExpression


_IDENTITY = tuple(range(48))
_DIMENSIONS = ("macro_count", "macro_definition_htm", "mean_htm", "worst_htm", "rule_count")
_PREFERENCES = {"memory": _DIMENSIONS,
                "execution": (*_DIMENSIONS[2:4], *_DIMENSIONS[:2], _DIMENSIONS[4])}


def _macro_map(macros):
    return macros if isinstance(macros, dict) else {macro.id: macro for macro in macros}


@dataclass(frozen=True)
class HumanMacroRecipe:
    """A named-master expression; names are separate from original loop IDs."""

    kind: str
    children: tuple = ()
    macro_id: str | None = None
    exponent: int = 1
    rotation: str | None = None

    def __post_init__(self):
        arities = {"macro": 0, "sequence": None, "power": 1,
                   "conjugate": 2, "commutator": 2, "rotated": 1}
        if self.kind not in arities:
            raise ValueError("unknown master recipe kind")
        if not isinstance(self.children, tuple) or any(not isinstance(c, HumanMacroRecipe) for c in self.children):
            raise TypeError("recipe children must be a tuple of recipes")
        if arities[self.kind] is not None and len(self.children) != arities[self.kind]:
            raise ValueError("invalid recipe arity")
        if self.kind == "macro":
            if not isinstance(self.macro_id, str) or not self.macro_id or any(c.isspace() for c in self.macro_id):
                raise ValueError("a master recipe needs a nonempty master ID")
        elif self.macro_id is not None:
            raise ValueError("only a master leaf has a master ID")
        if isinstance(self.exponent, bool) or not isinstance(self.exponent, int):
            raise TypeError("recipe exponent must be an integer")
        if self.kind != "power" and self.exponent != 1:
            raise ValueError("only powers have a nondefault exponent")
        if self.kind == "rotated":
            from .loop_rotations import normalize_rotation
            object.__setattr__(self, "rotation", normalize_rotation(self.rotation))
        elif self.rotation is not None:
            raise ValueError("only rotated recipes have a rotation")

    @classmethod
    def macro(cls, identifier):
        return cls("macro", macro_id=identifier)

    @classmethod
    def sequence(cls, *children):
        flat = tuple(c for child in children for c in
                     (child.children if child.kind == "sequence" else (child,)))
        return cls("sequence", flat)

    @classmethod
    def power(cls, child, exponent):
        if isinstance(exponent, bool) or not isinstance(exponent, int):
            raise TypeError("recipe exponent must be an integer")
        if not isinstance(child, cls):
            raise TypeError("power body must be a recipe")
        if child.kind == "power":
            return cls.power(child.children[0], child.exponent * exponent)
        return child if exponent == 1 else cls("power", (child,), exponent=exponent)

    @classmethod
    def conjugate(cls, setup, body):
        return cls("conjugate", (setup, body))

    @classmethod
    def commutator(cls, first, second):
        return cls("commutator", (first, second))

    @classmethod
    def rotated(cls, rotation, child):
        return cls("rotated", (child,), rotation=rotation)

    @property
    def macro_ids(self):
        return ((self.macro_id,) if self.kind == "macro" else
                tuple(sorted({i for child in self.children for i in child.macro_ids})))

    def loop_expression(self, macros):
        records = _macro_map(macros)
        if self.kind == "macro":
            try:
                return records[self.macro_id].algorithm.expression
            except KeyError:
                raise ValueError(f"unknown master ID {self.macro_id}") from None
        children = tuple(c.loop_expression(records) for c in self.children)
        if self.kind == "sequence":
            return LoopExpression.sequence(*children)
        if self.kind == "power":
            return LoopExpression.power(children[0], self.exponent)
        if self.kind == "rotated":
            return LoopExpression.rotated(self.rotation, children[0])
        return LoopExpression(self.kind, children)

    def render(self):
        if self.kind == "macro":
            return self.macro_id
        if self.kind == "sequence":
            return " ".join(c.render() for c in self.children) or "()"
        if self.kind == "power":
            child = self.children[0]
            body = child.render() if child.kind == "macro" else f"({child.render()})"
            return f"{body}^{self.exponent}"
        if self.kind == "rotated":
            return f"rotate({self.rotation}, {self.children[0].render()})"
        if self.kind == "conjugate":
            setup, body = self.children
            # Recipes store setup · body · setup^-1; right exponents use
            # S^A = A^-1 · S · A, so their exponent is the inverse setup.
            exponent = self.power(setup, -1)
            return _conjugation_notation(
                body.render(), exponent.render(),
                body_is_atom=body.kind in ("macro", "commutator"),
                exponent_is_atom=exponent.kind == "macro")
        a, b = (c.render() for c in self.children)
        return f"[{a}, {b}]"

    def to_dict(self):
        result = {"kind": self.kind}
        if self.kind == "macro":
            result["macro_id"] = self.macro_id
        else:
            result["children"] = [c.to_dict() for c in self.children]
        if self.kind == "power":
            result["exponent"] = self.exponent
        if self.kind == "rotated":
            result["rotation"] = self.rotation
        return result


def _recipe_ordering_text(recipe):
    """Keep deterministic search choices independent of teaching notation.

    This is the original recipe ordering key. It is intentionally separate
    from the user-facing render so presentation changes cannot select a
    different equal-cost method or renumber recognition families.
    """
    if recipe.kind == "macro":
        return recipe.macro_id
    if recipe.kind == "sequence":
        return " ".join(_recipe_ordering_text(child) for child in recipe.children) or "()"
    if recipe.kind == "power":
        child = recipe.children[0]
        body = _recipe_ordering_text(child)
        if child.kind != "macro":
            body = f"({body})"
        return f"{body}^{recipe.exponent}"
    if recipe.kind == "rotated":
        return f"rotate({recipe.rotation}, {_recipe_ordering_text(recipe.children[0])})"
    first, second = (_recipe_ordering_text(child) for child in recipe.children)
    return (f"conj({first}, {second})" if recipe.kind == "conjugate"
            else f"[{first}, {second}]")


@dataclass(frozen=True)
class HumanRepertoireMacro:
    id: str
    algorithm: LoopAlgorithm


@dataclass(frozen=True)
class HumanRepertoireCase:
    observation: tuple[int, ...]
    recipe: HumanMacroRecipe
    instruction: HumanMacroRecipe | None
    next_observation: tuple[int, ...]
    rank: int


@dataclass(frozen=True)
class HumanRecognitionRule:
    id: str
    stage_number: int
    kind: str
    recipe: HumanMacroRecipe
    observations: tuple[tuple[int, ...], ...]
    exponents: tuple[int, ...]
    cycle: tuple[tuple[int, ...], ...] = ()


@dataclass(frozen=True)
class HumanRepertoireStage:
    number: int
    cases: tuple[HumanRepertoireCase, ...]
    rules: tuple[HumanRecognitionRule, ...]


@dataclass(frozen=True)
class HumanRepertoireStep:
    stage_number: int
    observation: tuple[int, ...]
    recipe: HumanMacroRecipe
    turn_sequence: str
    rank_before: int
    rank_after: int
    before: State
    after: State


@dataclass(frozen=True)
class HumanRepertoireApplication:
    status: str
    state: State
    steps: tuple[HumanRepertoireStep, ...]
    reason: str | None = None

    @property
    def turn_sequence(self):
        return _simplified_moves(move for step in self.steps for move in step.turn_sequence.split())


@dataclass(frozen=True)
class HumanRepertoire:
    baseline: HumanMethod
    method: HumanMethod
    macros: tuple[HumanRepertoireMacro, ...]
    stages: tuple[HumanRepertoireStage, ...]
    _metadata_json: str = field(repr=False, compare=False)

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    def to_dict(self):
        from .human_repertoire_io import repertoire_to_dict
        return repertoire_to_dict(self)

    def to_json(self, path=None):
        from .human_repertoire_io import repertoire_to_json
        return repertoire_to_json(self, path)

    def save(self, path):
        self.to_json(path)
        return self.to_dict()

    @classmethod
    def from_dict(cls, record):
        from .human_repertoire_io import repertoire_from_dict
        return repertoire_from_dict(record)

    def write_guide(self, path=None, *, diagram_mode: DiagramMode | None = None, face_colors=None):
        """Write a guide with optional case diagrams and face-palette overrides.

        ``face_colors`` maps U/R/F/D/L/B to Matplotlib colors and affects
        diagrams only. Omitted faces retain the standard palette. Leave
        ``diagram_mode`` unset for a text guide without plotting dependencies,
        or choose ``DiagramMode.OPPOSITE_CORNERS`` / ``DiagramMode.TRANSPARENT``.
        """
        from .human_repertoire_render import repertoire_guide
        guide = repertoire_guide(self, diagram_mode=diagram_mode, face_colors=face_colors)
        if path is not None:
            Path(path).write_text(guide, encoding="utf-8")
        return guide

    def recipe_for(self, stage_number, observation):
        if isinstance(stage_number, bool) or not isinstance(stage_number, int):
            raise TypeError("stage_number must be an integer")
        if not 1 <= stage_number <= len(self.stages):
            raise ValueError("stage_number is outside the repertoire")
        case = next((c for c in self.stages[stage_number - 1].cases if c.observation == tuple(observation)), None)
        if case is None:
            raise ValueError("unknown stage observation")
        return case.recipe

    def recognize(self, state):
        return self.method.recognize(state)

    def next_step(self, state):
        recognized = self.recognize(state)
        if recognized.status == "solved":
            return None
        if recognized.status != "ready":
            raise ValueError(f"{recognized.status}: {recognized.reason}")
        stage = self.stages[recognized.stage_number - 1]
        case = next(c for c in stage.cases if c.observation == recognized.observation)
        algorithm = _build_algorithm(case.instruction, self.macros, self.method, "instruction")
        after = state.apply(algorithm.turn_sequence)
        feature = self.method.stages[stage.number - 1]
        observation = _observe(self.method.inventory.action(after), feature.block_index, feature.feature.kind)
        next_case = next(c for c in stage.cases if c.observation == observation)
        _require(observation == case.next_observation and next_case.rank < case.rank,
                 "recognition instruction fails its progress rank")
        action = self.method.inventory.action(after)
        _require(after.shape == self.method.reference_shape and
                 all(_observe(action, p.block_index, p.feature.kind) == p.solved_observation
                     for p in self.method.stages[:stage.number - 1]),
                 "recognition instruction fails endpoint preservation")
        return HumanRepertoireStep(stage.number, case.observation, case.instruction, algorithm.turn_sequence,
                                   case.rank, next_case.rank, state, after)

    def apply(self, state):
        recognized = self.recognize(state)
        if recognized.status not in ("ready", "solved"):
            return HumanRepertoireApplication(recognized.status, state, (), recognized.reason)
        current, steps = state, []
        maximum = sum(max((c.rank for c in s.cases), default=0) for s in self.stages)
        for _ in range(maximum + 1):
            step = self.next_step(current)
            if step is None:
                return HumanRepertoireApplication("solved", current, tuple(steps))
            steps.append(step)
            current = step.after
        raise ValueError("recognition rules failed their finite progress bound")


def _build_algorithm(recipe, macros, method, identifier):
    expression = recipe.loop_expression(macros)
    records = {g.id: g for g in method.generators}
    word = expression.expanded_moves(method.generators,
                                     max_expanded_moves=max(1, _expression_bound(expression, records)))
    return LoopAlgorithm(identifier, expression, expression.evaluate(method.generators),
                         _simplified_moves(word.split()), method.inventory,
                         tuple((g.id, g.htm_length) for g in method.generators), method.generators)


def _rules(number, cases, method_stage, macros, actions, current):
    families = defaultdict(list)
    for case in cases:
        if case.instruction is not None:
            instruction = case.instruction
            body, exponent = ((instruction.children[0], instruction.exponent)
                              if instruction.kind == "power" else (instruction, 1))
            families[body].append((case, exponent))
    rules = []
    for body, entries in sorted(families.items(), key=lambda item: _recipe_ordering_text(item[0])):
        cycle = ()
        if (len(entries) == method_stage.case_count - 1 and
                all(c.next_observation == method_stage.solved_observation for c, _ in entries)):
            algorithm = _build_algorithm(body, macros, current[0], "cycle")
            if algorithm.permutation in current[1]:
                observation, observed = method_stage.solved_observation, []
                representative = _IDENTITY
                while observation not in observed:
                    observed.append(observation)
                    representative = _then(representative, algorithm.permutation)
                    observation = _observe(actions[representative], method_stage.block_index, method_stage.feature.kind)
                if observation == method_stage.solved_observation and len(observed) == method_stage.case_count:
                    cycle = tuple(observed)
        kind = "cycle" if cycle else "powers" if len(entries) > 1 or any(e != 1 for _, e in entries) else "instruction"
        rules.append(HumanRecognitionRule(f"R{number}.{len(rules) + 1}", number, kind, body,
                                           tuple(c.observation for c, _ in entries),
                                           tuple(e for _, e in entries), cycle))
    return tuple(rules)


@dataclass(frozen=True)
class _Template:
    recipe: HumanMacroRecipe
    algorithm: LoopAlgorithm
    family: str


class _Context:
    def __init__(self, method, loops, settings):
        self.method, self.loops, self.settings = method, loops, settings
        self.actions = {p: method.inventory.action(p) for p in sorted(method._permutations)}
        self.groups = _stage_groups(method, self.actions)
        self.macros, self.baseline_recipes = self._masters()
        self.by_id = _macro_map(self.macros)
        self.templates, self.transitions = [], []
        self.counts = defaultdict(int)
        self.seen = set()
        for macro in self.macros:
            for exponent in (1, -1):
                self.add(HumanMacroRecipe.power(HumanMacroRecipe.macro(macro.id), exponent), "basic", bounded=False)
        self.generate()
        self._transitions()

    def _masters(self):
        # Merge only literal inverse word pairs. Equal actions with different
        # physical words remain distinct, preserving the exact source fallback.
        records, source = {}, {}
        algorithms = list(self.method.algorithms)
        extra = sorted(self.method.generators, key=lambda g: (g.htm_length, g.id))[:self.settings["max_extra_macros"]]
        algorithms.extend(LoopAlgorithm(f"L{g.id}", LoopExpression.loop(g.id), g.permutation, g.turn_sequence,
                                        self.method.inventory, tuple((p.id, p.htm_length) for p in self.method.generators),
                                        self.method.generators) for g in extra)
        generators = {g.id: g for g in self.method.generators}
        for index, algorithm in enumerate(algorithms):
            expression = algorithm.expression
            witnessed = expression.expanded_moves(self.method.generators,
                max_expanded_moves=max(1, _expression_bound(expression, generators)))
            if _simplified_moves(witnessed.split()) != algorithm.turn_sequence:
                expression = LoopExpression.turns(algorithm.turn_sequence, expression)
            word, inverse = algorithm.turn_sequence, _inverse_moves(algorithm.turn_sequence)
            canonical = min(word, inverse)
            sign = 1 if canonical == word else -1
            if canonical not in records:
                records[canonical] = replace(algorithm,
                    expression=expression if sign == 1 else LoopExpression.power(expression, -1),
                    permutation=algorithm.permutation if sign == 1 else _inverse(algorithm.permutation),
                    turn_sequence=canonical)
            if index < len(self.method.algorithms):
                source[algorithm.id] = canonical, sign
        masters = []
        by_word = {}
        for word, algorithm in sorted(records.items(), key=lambda pair: (pair[1].htm_length, pair[0])):
            identifier = f"M{len(masters) + 1}"
            masters.append(HumanRepertoireMacro(identifier, replace(algorithm, id=identifier)))
            by_word[word] = identifier
        recipes = {a.id: HumanMacroRecipe.power(HumanMacroRecipe.macro(by_word[source[a.id][0]]), source[a.id][1])
                   for a in self.method.algorithms}
        return tuple(masters), recipes

    def add(self, recipe, family, bounded=True):
        if bounded:
            if self.counts["recipe_candidates_examined"] >= self.settings["max_recipes"]:
                self.counts["recipe_limit_reached"] = 1
                return False
            self.counts["recipe_candidates_examined"] += 1
        if recipe in self.seen:
            self.counts["duplicate_recipes"] += 1
            return True
        self.seen.add(recipe)
        algorithm = _build_algorithm(recipe, self.macros, self.method, "template")
        if algorithm.permutation == _IDENTITY:
            self.counts["identity_recipes"] += 1
            return True
        _require(algorithm.permutation in self.method._permutations, "recipe leaves the complete reference group")
        self.templates.append(_Template(recipe, algorithm, family))
        return True

    def generate(self):
        masters = [HumanMacroRecipe.macro(m.id) for m in self.macros]
        if not masters or self.settings["max_recipes"] == 0:
            return
        setups = masters[:self.settings["max_setup_macros"]]
        def powers():
            for power in range(2, self.settings["max_power"] + 1):
                for recipe in masters:
                    for exponent in (power, -power):
                        yield "power", HumanMacroRecipe.power(recipe, exponent)
        def constructions():
            for setup in setups:
                for body in masters:
                    if setup == body:
                        continue
                    for exponent in (1, -1):
                        yield "structured", HumanMacroRecipe.conjugate(setup, HumanMacroRecipe.power(body, exponent))
                    yield "structured", HumanMacroRecipe.commutator(setup, body)
        def symmetries():
            if not self.settings["allow_symmetry"]:
                return
            from .loop_rotations import bandage_symmetries
            for rotation in bandage_symmetries(self.method.reference_shape):
                for recipe in masters:
                    yield "structured", HumanMacroRecipe.rotated(rotation, recipe)
        # Interleave families so a narrow proposal budget includes powers and
        # structured recipes rather than exhausting one family first.
        for batch in zip_longest(powers(), constructions(), symmetries()):
            for proposal in batch:
                if proposal is not None and not self.add(proposal[1], proposal[0]):
                    return

    def _transitions(self):
        for stage, (current, _) in zip(self.method.stages, self.groups):
            fibers = {o: tuple(p for p in current if _observe(self.actions[p], stage.block_index, stage.feature.kind) == o)
                      for o in stage.observations}
            edges = []
            for template in self.templates:
                if template.algorithm.permutation not in current:
                    continue
                table = {}
                for observation, fiber in fibers.items():
                    targets = {_observe(self.actions[_then(p, template.algorithm.permutation)],
                                        stage.block_index, stage.feature.kind) for p in fiber}
                    _require(len(targets) == 1, "recipe transition is not constant on its whole observation fiber")
                    table[observation] = next(iter(targets))
                edges.append((template, table))
            self.transitions.append(tuple(edges))

    def policy(self, available, family):
        output = []
        permitted = {"basic"} if family == "basic" else {"basic", "power"} if family == "powers" else {"basic", "power", "structured"}
        for stage, transitions in zip(self.method.stages, self.transitions):
            reverse = defaultdict(list)
            for template, table in transitions:
                if template.family not in permitted or not set(template.recipe.macro_ids) <= available:
                    continue
                for source, target in table.items():
                    reverse[target].append((source, template))
            labels, parents = {stage.solved_observation: (0, 0)}, {}
            queue = [(0, 0, stage.solved_observation)]
            while queue:
                cost, steps, observation = heappop(queue)
                if labels[observation] != (cost, steps):
                    continue
                for source, template in reverse[observation]:
                    candidate = cost + template.algorithm.htm_length, steps + 1
                    old = labels.get(source)
                    if old is None or candidate < old or (candidate == old and
                            _recipe_ordering_text(template.recipe) <
                            _recipe_ordering_text(parents[source][0].recipe)):
                        labels[source] = candidate
                        parents[source] = template, observation
                        heappush(queue, (*candidate, source))
            if len(labels) != stage.case_count:
                return None
            cases = []
            for original in stage.observations:
                observation, recipes = original, []
                while observation != stage.solved_observation:
                    template, next_observation = parents[observation]
                    recipes.append(template.recipe)
                    _require(labels[next_observation][0] < labels[observation][0], "recipe fails positive progress")
                    observation = next_observation
                instruction = parents[original][0].recipe if recipes else None
                next_observation = parents[original][1] if recipes else original
                cases.append(HumanRepertoireCase(original, HumanMacroRecipe.sequence(*recipes), instruction,
                                                 next_observation, labels[original][0]))
            output.append(tuple(cases))
        return tuple(output)

    def exact_baseline(self):
        return tuple(tuple(HumanRepertoireCase(c.observation,
            self.baseline_recipes[c.algorithm_id] if c.algorithm_id is not None else HumanMacroRecipe.sequence(),
            self.baseline_recipes[c.algorithm_id] if c.algorithm_id is not None else None,
            stage.solved_observation,
            next(a.htm_length for a in self.method.algorithms if a.id == c.algorithm_id)
            if c.algorithm_id is not None else 0) for c in stage.cases) for stage in self.method.stages)

    def compile(self, policies):
        return _compile_policies(self.method, self.macros, policies, self.actions,
                                 self.groups, self.loops)


def _compile_policies(baseline, definitions, policies, actions, groups, loops):
    """Project complete named recipes into the shared method and rule format."""
    used = {i for cases in policies for c in cases for i in c.recipe.macro_ids}
    macros = tuple(m for m in definitions if m.id in used)
    stages, rules, algorithms = [], [], []
    for stage, cases, (current, _) in zip(baseline.stages, policies, groups):
        compiled = []
        for original, case in zip(stage.cases, cases):
            identifier = None
            if case.instruction is not None:
                identifier = f"A{len(algorithms) + 1}"
                algorithms.append(_build_algorithm(case.recipe, macros, baseline, identifier))
            compiled.append(replace(original, algorithm_id=identifier))
        stages.append(replace(stage, cases=tuple(compiled)))
        rules.append(HumanRepertoireStage(stage.number, cases,
            _rules(stage.number, cases, stage, macros, actions, (baseline, current))))
    method = _validate_method(replace(baseline, algorithms=tuple(algorithms), stages=tuple(stages)),
                              complete_loops=loops)
    metrics = _repertoire_metrics(method, macros, tuple(rules), actions)
    return method, macros, tuple(rules), metrics


def _repertoire_metrics(method, macros, stages, actions):
    result = _metrics(method, actions)
    result.update(macro_count=len(macros), macro_definition_htm=sum(m.algorithm.htm_length for m in macros),
                  rule_count=sum(len(s.rules) for s in stages),
                  case_count_sum=sum(len(s.cases) for s in stages))
    return result


def _baseline_metrics(method, actions):
    """Measure the exact source policy with literal inverse-word sharing."""
    algorithms = {a.id: a for a in method.algorithms}
    by_stage = tuple({min(algorithms[c.algorithm_id].turn_sequence,
                          _inverse_moves(algorithms[c.algorithm_id].turn_sequence))
                      for c in stage.cases if c.algorithm_id is not None}
                     for stage in method.stages)
    words = set().union(*by_stage) if by_stage else set()
    result = _metrics(method, actions)
    result.update(macro_count=len(words), macro_definition_htm=sum(len(w.split()) for w in words),
                  rule_count=sum(len(w) for w in by_stage),
                  case_count_sum=sum(s.case_count for s in method.stages))
    return result


def _same_json(first, second):
    return json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def _validate_metadata(metadata, actual, before):
    """Check measured policies and consistency of the recorded search history.

    Historical candidate costs are diagnostics, rather than replay certificates:
    only the actual baseline and selected policy are embedded in the artifact.
    """
    _require(_same_json(metadata.get("selected_metrics"), actual) and
             _same_json(metadata.get("baseline_metrics"), before) and
             metadata.get("coverage") == "certified",
             "saved repertoire metrics or coverage disagree with verified policies")
    _require(metadata.get("human_reviewed") is False and
             metadata.get("exhaustive_repertoire_search") is False,
             "unsupported human review or exhaustive quality-search claim")
    settings = metadata.get("settings")
    budget_names = ("max_trials", "max_recipes", "max_power", "max_extra_macros", "max_setup_macros")
    _require(isinstance(settings, dict) and
             set(settings) == {"preference", "allow_symmetry", "max_cost_ratio", *budget_names},
             "invalid saved repertoire settings")
    _require(settings["preference"] in _PREFERENCES and type(settings["allow_symmetry"]) is bool and
             all(type(settings[k]) is int and settings[k] >= 0 for k in budget_names),
             "invalid saved repertoire settings")
    ratio = settings["max_cost_ratio"]
    _require(type(ratio) in (int, float) and isfinite(ratio) and ratio >= 1, "invalid saved cost guard")
    _require(_same_json(metadata.get("pareto_dimensions"), _DIMENSIONS) and
             _same_json(metadata.get("preference_orders"), _PREFERENCES),
             "invalid saved repertoire objectives")
    candidates = metadata.get("candidates")
    _require(isinstance(candidates, list) and candidates, "missing saved repertoire candidates")
    for index, candidate in enumerate(candidates, 1):
        _require(isinstance(candidate, dict) and
                 set(candidate) == {"id", "source", "metrics", "admissible"} and
                 candidate["id"] == f"C{index}" and isinstance(candidate["source"], str),
                 "invalid saved repertoire candidate")
        metrics = candidate["metrics"]
        _require(isinstance(metrics, dict) and set(metrics) == set(actual) and
                 all(type(v) in (int, float) and isfinite(v) and v >= 0 for v in metrics.values()),
                 "invalid saved candidate metrics")
        admissible = metrics["total_htm"] <= before["total_htm"] * ratio and metrics["worst_htm"] <= before["worst_htm"] * ratio
        _require(type(candidate["admissible"]) is bool and candidate["admissible"] == admissible,
                 "saved candidate admissibility disagrees with the cost guard")
    fallback_keys = ("states", "mean_htm", "worst_htm", "total_htm", "mean_qtm", "worst_qtm", "total_qtm",
                     "macro_count", "macro_definition_htm", "rule_count", "case_count_sum")
    _require(candidates[0]["source"] == "exact_baseline" and
             _same_json({k: candidates[0]["metrics"][k] for k in fallback_keys},
                        {k: before[k] for k in fallback_keys}),
             "saved exact fallback disagrees with the baseline")
    eligible = [c for c in candidates if c["admissible"]]
    def dominates(first, second):
        return (all(first["metrics"][k] <= second["metrics"][k] for k in _DIMENSIONS) and
                any(first["metrics"][k] < second["metrics"][k] for k in _DIMENSIONS))
    frontier = [c for c in eligible if not any(dominates(other, c) for other in eligible)]
    _require(metadata.get("frontier") == [c["id"] for c in frontier],
             "saved frontier disagrees with recorded candidate metrics")
    selected = min(frontier, key=lambda c: (*[c["metrics"][k] for k in _PREFERENCES[settings["preference"]]], c["id"]))
    _require(metadata.get("selected_id") == selected["id"] and _same_json(selected["metrics"], actual),
             "saved selection disagrees with the verified policy or recorded objectives")
    _require(actual["total_htm"] <= before["total_htm"] * ratio and
             actual["worst_htm"] <= before["worst_htm"] * ratio,
             "selected repertoire violates its whole-method guard")


def optimize_human_repertoire(method, *, preference="memory", max_trials=64, max_recipes=2000,
                              max_power=4, max_extra_macros=16, max_setup_macros=16,
                              allow_symmetry=True, max_cost_ratio=1.0):
    """Share witnessed definitions while retaining exact complete fallback rules.

    Greedy trials and structured recipe proposals have separate explicit bounds.
    The default guard forbids whole-method mean/worst HTM regression. An explicit
    larger ratio permits a measured repertoire/execution tradeoff. No minimal
    vocabulary, shortest physical word or human-usability claim is made.
    """
    if not isinstance(method, HumanMethod):
        raise TypeError("repertoire optimization requires a compiled HumanMethod")
    if method.status != "completed":
        raise ValueError("repertoire optimization requires a complete method")
    if preference not in _PREFERENCES:
        raise ValueError("preference must be memory or execution")
    settings = dict(preference=preference, max_trials=max_trials, max_recipes=max_recipes,
                    max_power=max_power, max_extra_macros=max_extra_macros,
                    max_setup_macros=max_setup_macros, allow_symmetry=allow_symmetry,
                    max_cost_ratio=max_cost_ratio)
    for name in ("max_trials", "max_recipes", "max_power", "max_extra_macros", "max_setup_macros"):
        value = settings[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
    if type(allow_symmetry) is not bool:
        raise TypeError("allow_symmetry must be a boolean")
    if (isinstance(max_cost_ratio, bool) or not isinstance(max_cost_ratio, (int, float)) or
            not isfinite(max_cost_ratio) or max_cost_ratio < 1):
        raise ValueError("max_cost_ratio must be finite and at least one")
    loops = isotropy_loops(method.reference_shape)
    baseline = _validate_method(method, complete_loops=loops)
    context = _Context(baseline, loops, settings)
    candidates, seen = [], {}
    counts = defaultdict(int)

    def consider(policies, source):
        if policies is None:
            return None
        signature = tuple(tuple((c.recipe, c.instruction, c.next_observation, c.rank) for c in cases) for cases in policies)
        if signature in seen:
            return seen[signature]
        compiled, macros, stages, metrics = context.compile(policies)
        identifier = f"C{len(candidates) + 1}"
        candidate = identifier, source, compiled, macros, stages, metrics
        seen[signature] = candidate
        candidates.append(candidate)
        return candidate

    consider(context.exact_baseline(), "exact_baseline")
    before = _baseline_metrics(baseline, context.actions)

    def admissible(candidate):
        return (candidate[5]["total_htm"] <= before["total_htm"] * max_cost_ratio and
                candidate[5]["worst_htm"] <= before["worst_htm"] * max_cost_ratio)

    def rank(candidate):
        return tuple(candidate[5][k] for k in _PREFERENCES[preference])

    available = frozenset(m.id for m in context.macros)
    families = ("basic", "powers", "structured")
    for family in families:
        consider(context.policy(available, family), f"initial:{family}")
    # Expensive definitions first, restarting after a successful removal.
    while available and counts["trials_examined"] < max_trials:
        removed = False
        for identifier in sorted(available, key=lambda i: (-context.by_id[i].algorithm.htm_length, i)):
            if counts["trials_examined"] >= max_trials:
                break
            counts["trials_examined"] += 1
            trial = available - {identifier}
            reachable, feasible = False, []
            for family in families:
                policies = context.policy(trial, family)
                reachable |= policies is not None
                candidate = consider(policies, f"remove:{identifier}:{family}")
                if candidate is not None and admissible(candidate):
                    feasible.append(candidate)
            if not reachable:
                counts["unreachable_trials"] += 1
            elif not feasible:
                counts["quality_rejected_trials"] += 1
            if feasible:
                available = trial
                counts["accepted_deletions"] += 1
                removed = True
                break
        if not removed:
            break
    eligible = [c for c in candidates if admissible(c)]
    def dominates(first, second):
        return (all(first[5][k] <= second[5][k] for k in _DIMENSIONS) and
                any(first[5][k] < second[5][k] for k in _DIMENSIONS))
    frontier = [c for c in eligible if not any(dominates(other, c) for other in eligible)]
    selected = min(frontier, key=lambda c: (*rank(c), c[0]))
    metadata = {"settings": settings, **dict(context.counts), **dict(counts),
                "trials_examined": counts["trials_examined"],
                "recipe_candidates_examined": context.counts["recipe_candidates_examined"],
                "unreachable_trials": counts["unreachable_trials"],
                "quality_rejected_trials": counts["quality_rejected_trials"],
                "accepted_deletions": counts["accepted_deletions"],
                "trial_limit_reached": counts["trials_examined"] >= max_trials,
                "recipe_limit_reached": bool(context.counts["recipe_limit_reached"] or
                                             context.counts["recipe_candidates_examined"] == max_recipes),
                "seed_macro_count": len(context.macros), "template_count": len(context.templates),
                "exhaustive_repertoire_search": False, "human_reviewed": False, "coverage": "certified",
                "pareto_dimensions": _DIMENSIONS, "preference_orders": _PREFERENCES,
                "baseline_metrics": before, "selected_metrics": selected[5],
                "selected_id": selected[0], "frontier": [c[0] for c in frontier],
                "candidates": [{"id": c[0], "source": c[1], "metrics": c[5], "admissible": admissible(c)}
                               for c in candidates]}
    result = HumanRepertoire(baseline, selected[2], selected[3], selected[4], json.dumps(metadata, sort_keys=True))
    return _validate_repertoire(result, complete_loops=loops)


def _validate_repertoire(repertoire, *, complete_loops=None):
    """Reprove the displayed vocabulary, rules, ranks and compiled projection."""
    loops = complete_loops or isotropy_loops(repertoire.method.reference_shape)
    baseline = _validate_method(repertoire.baseline, complete_loops=loops)
    method = _validate_method(repertoire.method, complete_loops=loops)
    _require(baseline.status == method.status == "completed" and
             baseline.reference_shape == method.reference_shape and baseline._permutations == method._permutations,
             "repertoire baseline and projection have different references or groups")
    if repertoire.metadata.get("basis") != "templates":
        _require(tuple((s.feature, s.observations) for s in baseline.stages) ==
                 tuple((s.feature, s.observations) for s in method.stages),
                 "repertoire changes the declared stage chain")
    macros = _macro_map(repertoire.macros)
    _require(len(macros) == len(repertoire.macros), "duplicate master IDs")
    initial = State(method.reference_shape)
    for macro in repertoire.macros:
        algorithm = macro.algorithm
        _require(macro.id == algorithm.id and algorithm.permutation != _IDENTITY and
                 algorithm.permutation in method._permutations, "invalid master definition")
        recipe = HumanMacroRecipe.macro(macro.id)
        checked = _build_algorithm(recipe, macros, method, macro.id)
        _require(checked.permutation == algorithm.permutation and checked.turn_sequence == algorithm.turn_sequence and
                 initial.apply(algorithm.turn_sequence).shape == method.reference_shape and
                 initial.apply(algorithm.turn_sequence).sticker_permutation == algorithm.permutation,
                 "master physical word disagrees with its original witness")
    actions = {p: method.inventory.action(p) for p in sorted(method._permutations)}
    groups = _stage_groups(method, actions)
    _require(len(repertoire.stages) == len(method.stages), "missing repertoire stages")
    used = set()
    compiled_algorithms = {a.id: a for a in method.algorithms}
    for rules_stage, stage, (current, target) in zip(repertoire.stages, method.stages, groups):
        _require(rules_stage.number == stage.number and
                 tuple(c.observation for c in rules_stage.cases) == stage.observations, "invalid rule stage cases")
        by_observation = {c.observation: c for c in rules_stage.cases}
        for original, case in zip(stage.cases, rules_stage.cases):
            _require(type(case.rank) is int and case.rank >= 0, "rank must be a nonnegative integer")
            if case.observation == stage.solved_observation:
                _require(case.rank == 0 and case.instruction is None and not case.recipe.children and
                         case.recipe.kind == "sequence" and case.next_observation == case.observation,
                         "solved observation must skip without a recipe")
                continue
            _require(case.instruction is not None and case.next_observation in by_observation,
                     "unsolved case has no recognition instruction")
            next_case = by_observation[case.next_observation]
            _require(next_case.rank < case.rank, "recognition instruction does not decrease rank")
            full = _build_algorithm(case.recipe, macros, method, "case")
            instruction = _build_algorithm(case.instruction, macros, method, "instruction")
            _require(instruction.permutation in current and full.permutation in current,
                     "recipe fails whole-instruction endpoint preservation")
            fiber = [p for p in current if _observe(actions[p], stage.block_index, stage.feature.kind) == case.observation]
            _require(all(_observe(actions[_then(p, instruction.permutation)], stage.block_index, stage.feature.kind) ==
                         case.next_observation and _then(p, full.permutation) in target for p in fiber),
                     "recipe transition or correction fails its whole case fiber")
            projected = compiled_algorithms[original.algorithm_id]
            _require((projected.permutation, projected.turn_sequence) == (full.permutation, full.turn_sequence),
                     "repertoire recipe disagrees with compiled method")
            path, observation = [], case.observation
            while observation != stage.solved_observation:
                entry = by_observation[observation]
                _require(entry.instruction is not None and entry.next_observation in by_observation and
                         type(entry.rank) is int and
                         type(by_observation[entry.next_observation].rank) is int and
                         0 <= by_observation[entry.next_observation].rank < entry.rank,
                         "displayed recognition path does not decrease rank")
                path.append(entry.instruction)
                observation = entry.next_observation
            replayed = _build_algorithm(HumanMacroRecipe.sequence(*path), macros, method, "path")
            _require((replayed.permutation, replayed.turn_sequence) == (full.permutation, full.turn_sequence),
                     "displayed recognition path disagrees with full case recipe")
            used.update(case.recipe.macro_ids)
            used.update(case.instruction.macro_ids)
        expected = _rules(stage.number, rules_stage.cases, stage, repertoire.macros, actions, (method, current))
        _require(rules_stage.rules == expected, "recognition families omit, overlap or misdescribe cases")
    _require(used == set(macros), "repertoire contains hidden or unused master definitions")
    actual = _repertoire_metrics(method, repertoire.macros, repertoire.stages, actions)
    before = _baseline_metrics(baseline, actions)
    if repertoire.metadata.get("basis") == "templates":
        from .template_human_repertoire import _validate_template_metadata
        _validate_template_metadata(repertoire, actual, before)
    elif "basis" in repertoire.metadata:
        from .human_generator_repertoire import _validate_generator_metadata
        _validate_generator_metadata(repertoire, actual, before)
    else:
        _validate_metadata(repertoire.metadata, actual, before)
    return replace(repertoire, baseline=baseline, method=method)
