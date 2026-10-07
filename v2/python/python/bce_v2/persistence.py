"""Versioned records for reproducible experiments.

Version 1 retains a validated solved-to-state scramble. Version 2 stores
validated cubie arrays for imported states without such a witness. Neither
ordinary validity nor rigid-block validity establishes bandaged reachability.
Graph records are inspection exports, not imported completeness proofs.
"""

import json
from pathlib import Path

from . import State, shape

MODEL = "full-grid-27-fixed-centers"


def puzzle_record(value, *, name=None, metric="QTM"):
    metric = metric.upper()
    if metric not in ("QTM", "HTM"):
        raise ValueError("metric must be QTM or HTM")
    if name is not None and not isinstance(name, str):
        raise TypeError("name must be a string or None")
    initial = value.specification if isinstance(value, State) else shape(value)
    record = {
        "format": "bce-v2-puzzle", "version": 1, "model": MODEL,
        "notation": "Singmaster", "metric": metric, "symmetry": "none",
        "name": name, "labels": initial.labels,
        "scramble": value.scramble if isinstance(value, State) else "",
    }
    if isinstance(value, State) and value.scramble is None:
        record["version"] = 2
        del record["scramble"]
        record["cubies"] = {"corners": value.corners, "twists": value.twists,
                            "edges": value.edges, "flips": value.flips}
    return record


def save_puzzle(value, path, *, name=None, metric="QTM"):
    """Save a shape or colored State, returning its versioned JSON record."""
    record = puzzle_record(value, name=name, metric=metric)
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    return record


def load_puzzle(path):
    """Validate a version-1 or version-2 record and return its colored State.

    The saved labels are the reference bandage membership, not a scrambled
    shape treated as a new puzzle. Use result.shape for shape-only work.
    """
    return state_from_record(json.loads(Path(path).read_text(encoding="utf-8")))


def state_from_record(record):
    if (not isinstance(record, dict) or type(record.get("version")) is not int
            or record["version"] not in (1, 2)
            or record.get("format") != "bce-v2-puzzle"):
        raise ValueError("unsupported puzzle record format or version")
    expected = {"format", "version", "model", "notation", "metric", "symmetry",
                "name", "labels", "scramble" if record["version"] == 1 else "cubies"}
    if set(record) != expected:
        raise ValueError("invalid puzzle record fields")
    if (record["model"] != MODEL or record["symmetry"] != "none"
            or record["notation"] != "Singmaster"):
        raise ValueError("unsupported model, symmetry, or move notation")
    if record["metric"] not in ("QTM", "HTM"):
        raise ValueError("unsupported move metric")
    if record["name"] is not None and not isinstance(record["name"], str):
        raise ValueError("invalid puzzle name")
    if not isinstance(record["labels"], list):
        raise ValueError("invalid labels")
    try:
        initial = shape(record["labels"])
    except (ValueError, TypeError) as error:
        raise ValueError("invalid puzzle labels") from error
    if record["labels"] != initial.labels:
        raise ValueError("saved puzzle labels must be canonical")
    if record["version"] == 1:
        if not isinstance(record["scramble"], str):
            raise ValueError("invalid scramble")
        return State(initial).apply(record["scramble"])
    cubies = record["cubies"]
    if (not isinstance(cubies, dict) or set(cubies) != {"corners", "twists", "edges", "flips"}
            or any(not isinstance(values, list) for values in cubies.values())):
        raise ValueError("invalid colored cubie fields")
    try:
        return State.from_cubies(initial, **cubies)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid colored puzzle record: {error}") from error


def save_graph(graph, path):
    graph.to_json(path)
    return graph.to_dict()
