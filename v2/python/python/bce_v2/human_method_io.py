"""Portable human-method records, independently checked when they are loaded.

The fingerprint detects accidental changes; it is not a coverage certificate.
Loading a completed method regenerates its complete shape-loop source without
GAP and asks the method validator to recheck every mathematical claim.
"""

from hashlib import sha256
import json
from pathlib import Path
import re

from . import Shape
from ._moves import _simplified_moves
from .block_actions import BlockInventory
from .human_chains import BlockFeature
from .human_witnesses import stored_loop_generators
from .isotropy import isotropy_loops
from .loop_algorithms import LoopAlgorithm, LoopExpression


_MODEL = "full-grid-27-fixed-centers"
_MOVE = re.compile(r"[URFDLB](?:2|')?")
_DECIMAL = re.compile(r"[1-9][0-9]*")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_CONVENTIONS = {
    "format": "bce-v2-human-method", "version": 1, "model": _MODEL,
    "frame": "fixed", "notation": "Singmaster", "symmetry": "none",
    "permutation_degree": 48, "permutation_index_base": 0,
    "permutation_point_order": "URFDLB-without-centers",
    "permutation_action": "source-to-destination",
    "permutation_composition": "execution-order",
    "preservation": "whole_algorithm_endpoints",
}
_METHOD_FIELDS = set(_CONVENTIONS) | {
    "reference_shape", "root_vertex", "block_inventory", "strategy", "status",
    "reason", "group_order", "quotient_order", "kernel_order", "terminal_order",
    "coverage", "coverage_scope", "quality", "human_method_complete",
    "max_group_elements", "gap_version", "initial_features", "skipped_features",
    "generators", "stages", "algorithms", "fingerprint",
}


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _same(first, second):
    # Python considers 1, 1.0 and True equal; a saved integer convention does not.
    return _canonical(first) == _canonical(second)


def _fingerprint(record):
    return sha256(_canonical({key: value for key, value in record.items()
                              if key != "fingerprint"}).encode("utf-8")).hexdigest()


def _fields(record, names, label):
    if not isinstance(record, dict) or set(record) != set(names):
        raise ValueError(f"invalid {label} fields")


def _integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer at least {minimum}")
    return value


def _order(value, label, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical positive decimal string")
    return int(value)


def _list(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _string(value, label, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _permutation(value):
    value = _list(value, "permutation")
    if (len(value) != 48 or any(isinstance(p, bool) or not isinstance(p, int) for p in value)
            or set(value) != set(range(48))):
        raise ValueError("permutation must contain sticker images 0 through 47 exactly once")
    return tuple(value)


def _observation(value):
    return tuple(_integer(item, "observation coordinate")
                 for item in _list(value, "observation"))


def _feature(record):
    _fields(record, {"kind", "reference_cells"}, "feature")
    feature = BlockFeature(_string(record["kind"], "feature kind"),
                           tuple(_list(record["reference_cells"], "reference cells")))
    if not _same(feature.to_dict(), record):
        raise ValueError("feature cells must use canonical reference order")
    return feature


def _expression(record):
    if not isinstance(record, dict) or not isinstance(record.get("kind"), str):
        raise ValueError("invalid algorithm expression")
    kind = record["kind"]
    fields = {"kind", "generator_id"} if kind == "loop" else {"kind", "children"}
    fields |= ({"exponent"} if kind == "power" else {"moves"} if kind == "turns"
               else {"rotation"} if kind == "rotated" else set())
    _fields(record, fields, "expression")
    if kind == "loop":
        expression = LoopExpression.loop(_integer(record["generator_id"], "loop ID"))
    else:
        children = tuple(_expression(child) for child in _list(record["children"], "expression children"))
        kwargs = {"children": children}
        if kind == "power":
            exponent = record["exponent"]
            if isinstance(exponent, bool) or not isinstance(exponent, int):
                raise ValueError("expression exponent must be an integer")
            kwargs["exponent"] = exponent
        if kind == "turns":
            kwargs["moves"] = _string(record["moves"], "literal turns")
        if kind == "rotated":
            kwargs["rotation"] = _string(record["rotation"], "rotation")
        expression = LoopExpression(kind, **kwargs)
    if not _same(expression.to_dict(), record):
        raise ValueError("expression must use canonical notation")
    return expression


def _word(value, label):
    value = _string(value, label)
    if " ".join(value.split()) != value or any(_MOVE.fullmatch(m) is None for m in value.split()):
        raise ValueError(f"{label} must be a canonical outer-face Singmaster word")
    return value


def _generators(records, inventory, root_vertex, complete_loops):
    records = _list(records, "generators")
    expected = {"id", "source", "target", "permutation", "qtm_length", "block_action",
                "moves", "turn_sequence", "htm_length"}
    identifiers = set()
    for record in records:
        _fields(record, expected, "generator")
        identifier = _integer(record["id"], "loop ID")
        if identifier in identifiers:
            raise ValueError("original loop IDs must be unique")
        identifiers.add(identifier)
        for key in ("source", "target"):
            if _integer(record[key], f"loop {key}") >= complete_loops.shape_count:
                raise ValueError("original loop endpoint is outside the shape component")
        _permutation(record["permutation"])
        _integer(record["qtm_length"], "original QTM length", 1)
        _integer(record["htm_length"], "original HTM length", 1)
        _word(record["moves"], "original loop moves")
        _word(record["turn_sequence"], "original loop turn sequence")
    generators = stored_loop_generators(records, inventory, root_vertex, complete_loops)
    for generator, record in zip(generators, records):
        if (generator.qtm_length != sum(2 if move.endswith("2") else 1
                                        for move in generator.moves.split())
                or not _same(generator.to_dict(), record)):
            raise ValueError("original loop metadata disagrees with its physical witness")
    return generators


def _algorithm_to_dict(algorithm):
    return {"id": algorithm.id, "expression": algorithm.expression.to_dict(),
            "permutation": list(algorithm.permutation), "turn_sequence": algorithm.turn_sequence,
            "htm_length": algorithm.htm_length, "qtm_length": algorithm.qtm_length}


def _stage_to_dict(stage):
    return {"number": stage.number, "feature": stage.feature.to_dict(),
            "block_index": stage.block_index, "block_name": stage.block_name,
            "order_before": str(stage.order_before), "order_after": str(stage.order_after),
            "index": stage.index, "case_count": stage.case_count,
            "solved_observation": list(stage.solved_observation),
            "implied_features": [feature.to_dict() for feature in stage.implied_features],
            "cases": [{"observation": list(case.observation), "algorithm_id": case.algorithm_id,
                       "representative": list(case.representative)} for case in stage.cases]}


def method_to_dict(method):
    """Return a self-contained canonical method record with its fingerprint."""
    record = {
        **_CONVENTIONS, "reference_shape": method.reference_shape.labels,
        "root_vertex": method.root_vertex, "block_inventory": method.inventory.to_dict(),
        "strategy": method.strategy, "status": method.status, "reason": method.reason,
        "group_order": str(method.group_order),
        "quotient_order": None if method.quotient_order is None else str(method.quotient_order),
        "kernel_order": None if method.kernel_order is None else str(method.kernel_order),
        "terminal_order": None if method.terminal_order is None else str(method.terminal_order),
        "coverage": method.coverage, "coverage_scope": method.coverage_scope,
        "quality": method.quality, "human_method_complete": method.human_method_complete,
        "max_group_elements": method.max_group_elements, "gap_version": method.gap_version,
        "initial_features": [feature.to_dict() for feature in method.initial_features],
        "skipped_features": [feature.to_dict() for feature in method.skipped_features],
        "generators": [generator.to_dict() for generator in method.generators],
        "stages": [_stage_to_dict(stage) for stage in method.stages],
        "algorithms": [_algorithm_to_dict(algorithm) for algorithm in method.algorithms],
    }
    record["fingerprint"] = _fingerprint(record)
    return record


def method_to_json(method, path=None):
    """Serialize portable JSON, optionally writing it to a file."""
    text = json.dumps(method_to_dict(method), indent=2, sort_keys=True) + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def method_from_dict(record):
    """Rebuild a portable method and independently certify saved coverage.

    Loading needs the Rust engine, but does not invoke GAP. A completed record
    regenerates the complete reference shape component and its native loops;
    saved certification labels and the fingerprint are never treated as proof.
    """
    from .human_methods import HumanMethod, HumanMethodCase, HumanMethodStage, _validate_method

    _fields(record, _METHOD_FIELDS, "human method")
    if any(not _same(record[key], value) for key, value in _CONVENTIONS.items()):
        raise ValueError("unsupported human method format, model, frame, or conventions")
    fingerprint = record["fingerprint"]
    if (not isinstance(fingerprint, str) or _FINGERPRINT.fullmatch(fingerprint) is None
            or fingerprint != _fingerprint(record)):
        raise ValueError("human method fingerprint does not match its content")
    if type(record["human_method_complete"]) is not bool:
        raise ValueError("human_method_complete must be a boolean")
    shape = Shape(_list(record["reference_shape"], "reference shape"))
    if not _same(shape.labels, record["reference_shape"]):
        raise ValueError("reference shape must use canonical partition labels")
    inventory = BlockInventory(shape)
    if not _same(inventory.to_dict(), record["block_inventory"]):
        raise ValueError("saved block inventory disagrees with the reference shape and frames")
    root_vertex = _integer(record["root_vertex"], "reference root vertex")
    group_order = _order(record["group_order"], "group order")
    quotient_order = _order(record["quotient_order"], "quotient order", optional=True)
    kernel_order = _order(record["kernel_order"], "kernel order", optional=True)
    _order(record["terminal_order"], "terminal order", optional=True)
    status = _string(record["status"], "status")
    if status not in ("completed", "limit_reached"):
        raise ValueError("unsupported human method status")
    limit = record["max_group_elements"]
    if limit is not None:
        _integer(limit, "max_group_elements", 1)
    strategy = _string(record["strategy"], "strategy")
    reason = _string(record["reason"], "reason", optional=True)
    gap_version = _string(record["gap_version"], "GAP version")
    initial_features = tuple(_feature(item) for item in _list(record["initial_features"], "initial features"))
    skipped_features = tuple(_feature(item) for item in _list(record["skipped_features"], "skipped features"))
    if status == "completed":
        complete_loops = isotropy_loops(shape)
        if root_vertex >= complete_loops.shape_count:
            raise ValueError("saved root vertex is outside the reference shape component")
        generators = _generators(record["generators"], inventory, root_vertex, complete_loops)
    else:
        complete_loops = None
        if record["generators"] != []:
            raise ValueError("an incomplete method cannot contain original loop witnesses")
        generators = ()
    algorithms = []
    for item in _list(record["algorithms"], "algorithms"):
        _fields(item, {"id", "expression", "permutation", "turn_sequence", "htm_length", "qtm_length"},
                "algorithm")
        identifier = _string(item["id"], "algorithm ID")
        if not identifier:
            raise ValueError("algorithm ID cannot be empty")
        expression = _expression(item["expression"])
        permutation = _permutation(item["permutation"])
        moves = _word(item["turn_sequence"], "algorithm turn sequence")
        if _simplified_moves(moves.split()) != moves:
            raise ValueError("algorithm turn sequence must combine adjacent same-face turns")
        _integer(item["htm_length"], "algorithm HTM length")
        _integer(item["qtm_length"], "algorithm QTM length")
        algorithm = LoopAlgorithm(identifier, expression, permutation, moves, inventory,
                                  tuple((g.id, g.htm_length) for g in generators), generators)
        if not _same(_algorithm_to_dict(algorithm), item):
            raise ValueError("algorithm costs disagree with its physical witness")
        algorithms.append(algorithm)
    stages = []
    stage_fields = {"number", "feature", "block_index", "block_name", "order_before", "order_after",
                    "index", "case_count", "solved_observation", "implied_features", "cases"}
    for item in _list(record["stages"], "stages"):
        _fields(item, stage_fields, "stage")
        cases = []
        for case in _list(item["cases"], "cases"):
            _fields(case, {"observation", "algorithm_id", "representative"}, "case")
            cases.append(HumanMethodCase(_observation(case["observation"]),
                                         _string(case["algorithm_id"], "case algorithm ID", optional=True),
                                         _permutation(case["representative"])))
        _integer(item["index"], "stage index", 1)
        _integer(item["case_count"], "case count", 1)
        stage = HumanMethodStage(
            _integer(item["number"], "stage number", 1), _feature(item["feature"]),
            _integer(item["block_index"], "block index"), _string(item["block_name"], "block name"),
            _order(item["order_before"], "stage group order"),
            _order(item["order_after"], "stage stabilizer order"),
            _observation(item["solved_observation"]),
            tuple(_feature(feature) for feature in _list(item["implied_features"], "implied features")),
            tuple(cases))
        if not _same(_stage_to_dict(stage), item):
            raise ValueError("stage metadata disagrees with its cases")
        stages.append(stage)
    method = HumanMethod(shape, strategy, status, group_order, quotient_order, kernel_order,
                         root_vertex, generators, tuple(stages), tuple(algorithms), initial_features,
                         skipped_features, limit, reason, gap_version, inventory, frozenset())
    try:
        method = _validate_method(method, complete_loops=complete_loops)
    except (TypeError, RuntimeError) as error:
        raise ValueError(f"invalid human method: {error}") from error
    if not _same(method_to_dict(method), record):
        raise ValueError("saved method claims disagree with independently checked coverage")
    return method


def load_human_method(path):
    """Load and independently validate a portable method JSON file."""
    return method_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
