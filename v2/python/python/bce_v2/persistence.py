"""Versioned records for reproducible experiments.

Colored states persist as a solved bandage specification plus a validated
scramble. Graph records are exports: they cannot establish their own claimed
completeness and are not accepted as imported search results.
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
    return {
        "format": "bce-v2-puzzle", "version": 1, "model": MODEL,
        "notation": "Singmaster", "metric": metric, "symmetry": "none",
        "name": name, "labels": initial.labels,
        "scramble": value.scramble if isinstance(value, State) else "",
    }


def save_puzzle(value, path, *, name=None, metric="QTM"):
    """Save a shape or replayable colored State, returning its JSON record."""
    record = puzzle_record(value, name=name, metric=metric)
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    return record


def load_puzzle(path):
    """Validate a version-1 record and return its replayed colored State.

    The saved labels are the reference bandage membership, not a scrambled
    shape treated as a new puzzle. Use result.shape for shape-only work.
    """
    return state_from_record(json.loads(Path(path).read_text(encoding="utf-8")))


def state_from_record(record):
    expected = {"format", "version", "model", "notation", "metric", "symmetry",
                "name", "labels", "scramble"}
    if not isinstance(record, dict) or set(record) != expected:
        raise ValueError("invalid puzzle record fields")
    if (record["format"] != "bce-v2-puzzle" or type(record["version"]) is not int
            or record["version"] != 1):
        raise ValueError("unsupported puzzle record format or version")
    if (record["model"] != MODEL or record["symmetry"] != "none"
            or record["notation"] != "Singmaster"):
        raise ValueError("unsupported model, symmetry, or move notation")
    if record["metric"] not in ("QTM", "HTM"):
        raise ValueError("unsupported move metric")
    if record["name"] is not None and not isinstance(record["name"], str):
        raise ValueError("invalid puzzle name")
    if not isinstance(record["labels"], list) or not isinstance(record["scramble"], str):
        raise ValueError("invalid labels or scramble")
    try:
        initial = shape(record["labels"])
    except (ValueError, TypeError) as error:
        raise ValueError("invalid puzzle labels") from error
    if record["labels"] != initial.labels:
        raise ValueError("saved puzzle labels must be canonical")
    return State(initial).apply(record["scramble"])


def save_graph(graph, path):
    graph.to_json(path)
    return graph.to_dict()
