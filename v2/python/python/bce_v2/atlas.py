"""Read-only queries on a derived block-signature SQLite atlas."""

import json
from pathlib import Path
import sqlite3

from . import Shape
from .signatures import BLOCK_TYPES, SINGLETON_TYPES


def _types(code):
    if code == "211":
        return tuple(block.code for block in BLOCK_TYPES if block.dimensions == (2, 1, 1))
    if code not in {block.code for block in BLOCK_TYPES}:
        raise ValueError(f"unknown block type {code!r}")
    return (code,)


class PuzzleAtlas:
    """One row per puzzle class in an explicitly chosen atlas cohort.

    Cohorts: all (7,073), mirror (4,860), mobile (7,070), filtered (4,857).
    The default filtered cohort identifies mirrors and excludes permanently
    frozen or one-axis puzzles. Queries count the implicitly closed blocks.
    """

    COHORTS = ("all", "mirror", "mobile", "filtered")

    def __init__(self, path, *, cohort="filtered"):
        if cohort not in self.COHORTS:
            raise ValueError(f"cohort must be one of {self.COHORTS}")
        self._cohort = cohort
        self._view = f"puzzles_{cohort}"
        self.connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        try:
            if (self.connection.execute("PRAGMA user_version").fetchone()[0] != 2
                    or self.metadata.get("schema") != "bandaged-cube-block-signatures-v2"):
                raise ValueError("unsupported block-signature atlas schema; rebuild the signature database")
        except Exception:
            self.close()
            raise

    @property
    def cohort(self):
        return self._cohort

    @property
    def metadata(self):
        return {row["key"]: json.loads(row["value"])
                for row in self.connection.execute("SELECT key, value FROM metadata")}

    def query(self, sql, parameters=()):
        """Return dictionaries from custom SQL; the database is opened read-only."""
        return [dict(row) for row in self.connection.execute(sql, parameters)]

    def __len__(self):
        return self.connection.execute(f"SELECT COUNT(*) FROM {self._view}").fetchone()[0]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _where(self, contains, only, signature):
        clauses, parameters = [], []
        for code, count in ({} if contains is None else contains).items():
            types = _types(code)
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError("minimum counts must be positive integers")
            if count <= 0:
                raise ValueError("minimum counts must be positive")
            placeholders = ",".join("?" for _ in types)
            clauses.append("(SELECT COUNT(*) FROM blocks b WHERE b.puzzle_id = p.id "
                           f"AND b.block_type IN ({placeholders})) >= ?")
            parameters.extend((*types, count))
        if only is not None:
            if isinstance(only, str):
                raise TypeError("only must be a sequence of types, e.g. ('211',)")
            allowed = sorted(set(SINGLETON_TYPES).union(*(set(_types(code)) for code in only)))
            placeholders = ",".join("?" for _ in allowed)
            clauses.append("NOT EXISTS (SELECT 1 FROM blocks b WHERE b.puzzle_id = p.id "
                           f"AND b.block_type NOT IN ({placeholders}))")
            parameters.extend(allowed)
        if signature is not None:
            if not isinstance(signature, str):
                raise TypeError("signature must be human-readable text from format_signature")
            clauses.append("p.signature = ?")
            parameters.append(signature)
        return " AND ".join(clauses) or "1", parameters

    def select(self, *, contains=None, only=None, signature=None):
        """Select by minimum block counts, allowed types, and/or exact signature.

        '211' matches both Clock and Pair. Other names match exact variants,
        e.g. '221' excludes '221Core', and '311' excludes 'BigClock'. Singletons are always
        allowed by only. Examples: contains={'222': 1}, only=('211',),
        signature='2x221 Clock 2xPair'. These constraints can be combined.
        """
        where, parameters = self._where(contains, only, signature)
        return self.query(f"SELECT p.* FROM {self._view} p WHERE {where} ORDER BY p.id",
                          parameters)

    def containing(self, code, *, at_least=1):
        return self.select(contains={code: at_least})

    def only(self, *codes):
        return self.select(only=codes)

    def maximum(self, code, *, only=None):
        """Return (largest count, all matching puzzles), optionally restricting types.

        An empty candidate set returns (None, []); singletons are always allowed.
        maximum('211', only=('211',)) asks for the most dominoes with nothing
        larger. maximum('Pair', only=('Pair',)) forbids Clocks as well.
        """
        types = _types(code)
        where, parameters = self._where(None, only, None)
        placeholders = ",".join("?" for _ in types)
        rows = self.query(
            "SELECT p.*, (SELECT COUNT(*) FROM blocks b WHERE b.puzzle_id = p.id "
            f"AND b.block_type IN ({placeholders})) AS block_count "
            f"FROM {self._view} p WHERE {where} ORDER BY block_count DESC, p.id",
            [*types, *parameters])
        maximum = rows[0]["block_count"] if rows else None
        return maximum, [row for row in rows if row["block_count"] == maximum]

    def signature_counts(self):
        """List every signature, its puzzle count, and the implied singleton count."""
        return self.query(
            "SELECT signature, COUNT(*) AS puzzles, MIN(singletons) AS singletons, "
            "MIN(singletons) AS singletons_min, "
            f"MAX(singletons) AS singletons_max FROM {self._view} "
            "GROUP BY signature ORDER BY puzzles DESC, signature")

    def shape(self, puzzle_id):
        rows = self.query(f"SELECT labels FROM {self._view} WHERE id = ?", (puzzle_id,))
        if not rows:
            raise KeyError(puzzle_id)
        return Shape(list(map(int, rows[0]["labels"].split())))
