"""Portable witnessed repertoires, independently checked without GAP.

The fingerprint detects accidental changes. Loading rechecks the embedded
methods, master witnesses, recipe transitions, progress ranks and rule cover.
"""

import json
from pathlib import Path
import re

from ._moves import _simplified_moves
from .human_method_io import (
    _CONVENTIONS as _METHOD_CONVENTIONS, _FINGERPRINT, _algorithm_to_dict,
    _expression, _fields, _fingerprint, _integer, _list, _observation,
    _permutation, _same, _string, _word,
)
from .loop_algorithms import LoopAlgorithm


_CONVENTIONS = {
    **_METHOD_CONVENTIONS, "format": "bce-v2-human-repertoire",
    "preservation": "whole_instruction_endpoints",
    "coverage": "certified", "coverage_scope": "all_reference_group_states",
    "quality": "computational_baseline", "human_method_complete": True,
}
_FIELDS = set(_CONVENTIONS) | {
    "reference_shape", "root_vertex", "baseline", "method", "macros",
    "stages", "metadata", "fingerprint",
}
_MACRO_ID = re.compile(r"M[1-9][0-9]*")
_ALGORITHM_FIELDS = {"id", "expression", "permutation", "turn_sequence", "htm_length", "qtm_length"}


def _signed_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _macro_id(value):
    value = _string(value, "macro ID")
    if _MACRO_ID.fullmatch(value) is None:
        raise ValueError("macro ID must be M followed by a canonical positive integer")
    return value


def _recipe(record):
    from .human_repertoire import HumanMacroRecipe

    if not isinstance(record, dict) or not isinstance(record.get("kind"), str):
        raise ValueError("invalid macro recipe")
    kind = record["kind"]
    fields = {"kind", "macro_id"} if kind == "macro" else {"kind", "children"}
    fields |= {"exponent"} if kind == "power" else {"rotation"} if kind == "rotated" else set()
    _fields(record, fields, "macro recipe")
    if kind == "macro":
        recipe = HumanMacroRecipe.macro(_macro_id(record["macro_id"]))
    else:
        kwargs = {"children": tuple(_recipe(child) for child in
                                     _list(record["children"], "recipe children"))}
        if kind == "power":
            kwargs["exponent"] = _signed_integer(record["exponent"], "recipe exponent")
        if kind == "rotated":
            kwargs["rotation"] = _string(record["rotation"], "recipe rotation")
        recipe = HumanMacroRecipe(kind, **kwargs)
    if not _same(recipe.to_dict(), record):
        raise ValueError("recipe must use canonical notation")
    return recipe


def _case_to_dict(case):
    return {"observation": list(case.observation), "recipe": case.recipe.to_dict(),
            "instruction": None if case.instruction is None else case.instruction.to_dict(),
            "next_observation": list(case.next_observation), "rank": case.rank}


def _rule_to_dict(rule):
    return {"id": rule.id, "stage_number": rule.stage_number, "kind": rule.kind,
            "recipe": rule.recipe.to_dict(),
            "observations": [list(observation) for observation in rule.observations],
            "exponents": list(rule.exponents), "cycle": [list(observation) for observation in rule.cycle]}


def _stage_to_dict(stage):
    return {"number": stage.number, "cases": [_case_to_dict(case) for case in stage.cases],
            "rules": [_rule_to_dict(rule) for rule in stage.rules]}


def repertoire_to_dict(repertoire):
    """Return the canonical complete wrapper and its content fingerprint."""
    record = {**_CONVENTIONS, "reference_shape": repertoire.method.reference_shape.labels,
              "root_vertex": repertoire.method.root_vertex,
              "baseline": repertoire.baseline.to_dict(), "method": repertoire.method.to_dict(),
              "macros": [_algorithm_to_dict(macro.algorithm) for macro in repertoire.macros],
              "stages": [_stage_to_dict(stage) for stage in repertoire.stages],
              "metadata": repertoire.metadata}
    record["fingerprint"] = _fingerprint(record)
    return record


def repertoire_to_json(repertoire, path=None):
    """Serialize portable JSON, optionally writing to the supplied path."""
    text = json.dumps(repertoire_to_dict(repertoire), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def repertoire_from_dict(record):
    """Load and independently verify a complete repertoire without GAP."""
    from .human_methods import HumanMethod
    from .human_repertoire import (
        HumanRecognitionRule, HumanRepertoire, HumanRepertoireCase,
        HumanRepertoireMacro, HumanRepertoireStage, _validate_repertoire,
    )

    _fields(record, _FIELDS, "human repertoire")
    if any(not _same(record[key], value) for key, value in _CONVENTIONS.items()):
        raise ValueError("unsupported repertoire format, model, frame, or conventions")
    fingerprint = record["fingerprint"]
    if (not isinstance(fingerprint, str) or _FINGERPRINT.fullmatch(fingerprint) is None
            or fingerprint != _fingerprint(record)):
        raise ValueError("human repertoire fingerprint does not match its content")
    baseline = HumanMethod.from_dict(record["baseline"])
    method = HumanMethod.from_dict(record["method"])
    if not _same(method.reference_shape.labels, record["reference_shape"]):
        raise ValueError("repertoire reference shape disagrees with its compiled method")
    if _integer(record["root_vertex"], "reference root vertex") != method.root_vertex:
        raise ValueError("repertoire root vertex disagrees with its compiled method")
    metadata = record["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("repertoire metadata must be an object")
    try:
        metadata_json = json.dumps(metadata, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("repertoire metadata must contain finite JSON values") from error
    macros = []
    for item in _list(record["macros"], "macros"):
        _fields(item, _ALGORITHM_FIELDS, "macro algorithm")
        identifier = _macro_id(item["id"])
        expression = _expression(item["expression"])
        permutation = _permutation(item["permutation"])
        moves = _word(item["turn_sequence"], "macro turn sequence")
        if _simplified_moves(moves.split()) != moves:
            raise ValueError("macro turn sequence must combine adjacent same-face turns")
        _integer(item["htm_length"], "macro HTM length")
        _integer(item["qtm_length"], "macro QTM length")
        algorithm = LoopAlgorithm(identifier, expression, permutation, moves, method.inventory,
                                  tuple((g.id, g.htm_length) for g in method.generators), method.generators)
        if not _same(_algorithm_to_dict(algorithm), item):
            raise ValueError("macro costs disagree with its physical witness")
        macros.append(HumanRepertoireMacro(identifier, algorithm))
    stages = []
    for item in _list(record["stages"], "repertoire stages"):
        _fields(item, {"number", "cases", "rules"}, "repertoire stage")
        number = _integer(item["number"], "stage number", 1)
        cases = []
        for case in _list(item["cases"], "repertoire cases"):
            _fields(case, {"observation", "recipe", "instruction", "next_observation", "rank"},
                    "repertoire case")
            cases.append(HumanRepertoireCase(
                _observation(case["observation"]), _recipe(case["recipe"]),
                None if case["instruction"] is None else _recipe(case["instruction"]),
                _observation(case["next_observation"]), _integer(case["rank"], "case progress rank")))
        rules = []
        for rule in _list(item["rules"], "recognition rules"):
            _fields(rule, {"id", "stage_number", "kind", "recipe", "observations", "exponents", "cycle"},
                    "recognition rule")
            identifier = _string(rule["id"], "recognition rule ID")
            if not identifier:
                raise ValueError("recognition rule ID cannot be empty")
            rules.append(HumanRecognitionRule(
                identifier, _integer(rule["stage_number"], "rule stage number", 1),
                _string(rule["kind"], "recognition rule kind"), _recipe(rule["recipe"]),
                tuple(_observation(o) for o in _list(rule["observations"], "rule observations")),
                tuple(_signed_integer(e, "rule exponent") for e in
                      _list(rule["exponents"], "rule exponents")),
                tuple(_observation(o) for o in _list(rule["cycle"], "rule cycle"))))
        stage = HumanRepertoireStage(number, tuple(cases), tuple(rules))
        if not _same(_stage_to_dict(stage), item):
            raise ValueError("repertoire stage must use canonical notation")
        stages.append(stage)
    known = {macro.id for macro in macros}
    recipes = [recipe for stage in stages for case in stage.cases
               for recipe in (case.recipe, case.instruction) if recipe is not None]
    recipes.extend(rule.recipe for stage in stages for rule in stage.rules)
    if any(set(recipe.macro_ids) - known for recipe in recipes):
        raise ValueError("recipe refers to an unknown master definition")
    repertoire = HumanRepertoire(baseline, method, tuple(macros), tuple(stages), metadata_json)
    try:
        repertoire = _validate_repertoire(repertoire)
    except (TypeError, RuntimeError) as error:
        raise ValueError(f"invalid human repertoire: {error}") from error
    if not _same(repertoire_to_dict(repertoire), record):
        raise ValueError("saved repertoire claims disagree with independently checked rules and coverage")
    return repertoire


def load_human_repertoire(path):
    """Load a portable repertoire JSON file and recheck its complete policy."""
    return repertoire_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
