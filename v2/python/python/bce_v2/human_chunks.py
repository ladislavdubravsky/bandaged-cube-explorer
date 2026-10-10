"""Shared, checked teaching phrases for several physical algorithm words.

The dictionary is a finite description search, not a shortest-grammar claim.
Phrases may be open paths, reused in inverse or properly rotated form.  Every
use retains an exact source guard and checked path.  A geometric similarity
never grants permission to execute a phrase at an unrelated shape.

Half turns may be split at phrase boundaries, exposing shared phrases hidden
by adjacent-turn simplification.  Setup/body/undo constructions retain their
off-reference local loop, rather than teaching the whole transport as opaque.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
from math import isqrt
import re

from . import Shape, shape
from ._moves import _simplified_moves
from .loop_rotations import (
    _CANONICAL_WORDS, inverse_rotation, normalize_rotation, rotate_moves,
)
from .shape_paths import ShapePath


_MOVE = re.compile(r"[URFDLB](?:2|')?")
_ROTATIONS = tuple(sorted(_CANONICAL_WORDS.values(), key=lambda word: (len(word.split()), word)))
# Build geometry through the checked public conversion once.  Mining millions
# of substring variants then needs only a six-face spelling substitution.
_FACE_MAPS = {rotation: dict(zip("URFDLB", rotate_moves("U R F D L B", rotation).split()))
              for rotation in _ROTATIONS}
_FORMAT = {"format": "bce-v2-human-chunks", "version": 1,
           "scope": "typed-physical-paths", "search": "bounded-greedy-description"}
_LIMIT_MINIMA = {"min_chunk_length": 2, "max_chunk_length": 2,
                 "max_chunks": 0, "max_candidates": 0, "max_word_moves": 0}


def _word(moves):
    if not isinstance(moves, str):
        raise TypeError("algorithm moves must be a face-turn string")
    if any(_MOVE.fullmatch(move) is None for move in moves.split()):
        raise ValueError("algorithm moves must use outer-face Singmaster notation")
    return _simplified_moves(moves.split())


def _inverse(word):
    return tuple(move if move.endswith("2") else move[:-1] if move.endswith("'")
                 else move + "'" for move in reversed(word))


def _amount(move):
    return 2 if move.endswith("2") else 3 if move.endswith("'") else 1


def _token(face, amount):
    return face + ("2" if amount == 2 else "'" if amount == 3 else "")


def _rotated_word(word, rotation):
    faces = _FACE_MAPS[rotation]
    return tuple(faces[move[0]] + move[1:] for move in word)


def _identifier(value, name):
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        raise ValueError(f"{name} must be a nonempty identifier without spaces")
    return value


def _integer(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class AlgorithmChunk:
    """One remembered spelling with exact admissible open-path instances."""

    id: str
    moves: str
    instances: tuple[ShapePath, ...]

    def __post_init__(self):
        _identifier(self.id, "chunk ID")
        if not self.moves or _word(self.moves) != self.moves:
            raise ValueError("chunk moves must be a nonempty normalized word")
        if (not isinstance(self.instances, tuple) or not self.instances or
                any(not isinstance(path, ShapePath) or path.moves != self.moves or path.frame
                    for path in self.instances)):
            raise ValueError("chunk instances must be checked paths in the definition frame")
        if len(set(self.instances)) != len(self.instances):
            raise ValueError("chunk instances must be distinct")

    @property
    def kind(self):
        return "local_loop" if all(path.is_closed for path in self.instances) else "open_path"

    def to_dict(self):
        return {"id": self.id, "moves": self.moves, "kind": self.kind,
                "instances": [path.to_dict() for path in self.instances]}

    @classmethod
    def from_dict(cls, record):
        if not isinstance(record, dict) or set(record) != {"id", "moves", "kind", "instances"}:
            raise ValueError("invalid chunk definition record")
        if not isinstance(record["instances"], list):
            raise TypeError("chunk instances must be a list")
        result = cls(record["id"], record["moves"],
                     tuple(ShapePath.from_dict(path) for path in record["instances"]))
        if record["kind"] != result.kind:
            raise ValueError("chunk kind disagrees with its checked endpoints")
        return result


@dataclass(frozen=True)
class ChunkExpression:
    """Typed grammar node; transport expands setup, local body, setup inverse."""

    kind: str
    path: ShapePath
    children: tuple = ()
    chunk_id: str | None = None
    instance: int | None = None
    inverse: bool = False
    rotation: str = ""

    def __post_init__(self):
        if self.kind not in ("literal", "chunk", "sequence", "transport"):
            raise ValueError("invalid chunk expression kind")
        if not isinstance(self.path, ShapePath) or self.path.frame:
            raise ValueError("chunk expressions require a checked fixed-frame path")
        if (not isinstance(self.children, tuple) or
                any(not isinstance(child, ChunkExpression) for child in self.children)):
            raise TypeError("chunk children must be a tuple of expressions")
        if type(self.inverse) is not bool:
            raise TypeError("chunk inverse flag must be a boolean")
        if self.rotation != normalize_rotation(self.rotation):
            raise ValueError("chunk rotation must be canonical")
        if self.kind == "chunk":
            _identifier(self.chunk_id, "chunk reference")
            _integer(self.instance, "chunk instance", 0)
            if self.children:
                raise ValueError("chunk references cannot have children")
        elif self.chunk_id is not None or self.instance is not None or self.inverse or self.rotation:
            raise ValueError("only a chunk reference has reference fields")
        if self.kind == "literal" and self.children:
            raise ValueError("literal chunks cannot have children")
        if self.kind == "transport" and len(self.children) != 2:
            raise ValueError("transport requires a setup and local loop")
        if self.kind in ("sequence", "transport"):
            if self.kind == "transport":
                expected = self.children[0].path.transport_loop(self.children[1].path)
            else:
                expected = ShapePath.identity(self.path.source_shape)
                for child in self.children:
                    expected = expected.then(child.path)
            if expected != self.path:
                raise ValueError("chunk expression endpoints, action, or expansion disagree")

    def _validate_reference(self, definitions):
        if self.kind == "chunk":
            definition = definitions.get(self.chunk_id)
            if definition is None or self.instance >= len(definition.instances):
                raise ValueError("chunk reference names a missing definition or source guard")
            path = definition.instances[self.instance]
            if self.inverse:
                path = path.inverse()
            path = path.rotated(self.rotation).reframed("")
            if path != self.path:
                raise ValueError("chunk reference violates its source, frame, action, or expansion guard")
        for child in self.children:
            child._validate_reference(definitions)

    def to_dict(self):
        return {"kind": self.kind, "path": self.path.to_dict(),
                "children": [child.to_dict() for child in self.children],
                "chunk_id": self.chunk_id, "instance": self.instance,
                "inverse": self.inverse, "rotation": self.rotation}

    @classmethod
    def from_dict(cls, record):
        expected = {"kind", "path", "children", "chunk_id", "instance", "inverse", "rotation"}
        if not isinstance(record, dict) or set(record) != expected:
            raise ValueError("invalid chunk expression record")
        if not isinstance(record["children"], list):
            raise TypeError("chunk expression children must be a list")
        return cls(record["kind"], ShapePath.from_dict(record["path"]),
                   tuple(cls.from_dict(child) for child in record["children"]),
                   record["chunk_id"], record["instance"], record["inverse"], record["rotation"])

    @property
    def notation(self):
        if self.kind == "literal":
            return self.path.moves or "()"
        if self.kind == "chunk":
            result = self.chunk_id + ("^-1" if self.inverse else "")
            # Spell the undo in reverse written order: readers can see that
            # each regrip is undone without learning a second equivalent grip.
            undo = " ".join(_inverse(self.rotation.split()))
            return (f"{self.rotation} ({result}) {undo}"
                    if self.rotation else result)
        if self.kind == "transport":
            setup, body = (child.notation for child in self.children)
            return f"({setup}) ({body}) ({setup})^-1"
        return " ".join(child.notation for child in self.children) or "()"

    @property
    def recipe_symbols(self):
        if self.kind == "literal":
            return len(self.path.moves.split())
        if self.kind == "chunk":
            return 1 + int(self.inverse)
        return sum(child.recipe_symbols for child in self.children) + int(self.kind == "transport")

    @property
    def regrip_count(self):
        return int(bool(self.rotation)) + sum(child.regrip_count for child in self.children)


def _nodes(expression):
    yield expression
    for child in expression.children:
        yield from _nodes(child)


@dataclass(frozen=True)
class ChunkDictionary:
    """Serializable shared grammar and independently checked master expansions."""

    reference_shape: Shape
    chunks: tuple[AlgorithmChunk, ...]
    masters: tuple[tuple[str, ChunkExpression], ...]
    search_limits: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "reference_shape", shape(self.reference_shape))
        if not isinstance(self.chunks, tuple) or any(not isinstance(chunk, AlgorithmChunk) for chunk in self.chunks):
            raise TypeError("dictionary chunks must be a tuple of definitions")
        definitions = {chunk.id: chunk for chunk in self.chunks}
        if len(definitions) != len(self.chunks):
            raise ValueError("duplicate chunk ID")
        if not isinstance(self.masters, tuple):
            raise TypeError("dictionary masters must be a tuple")
        object.__setattr__(self, "masters", tuple(tuple(pair) for pair in self.masters))
        identifiers, used = set(), {chunk.id: set() for chunk in self.chunks}
        for identifier, expression in self.masters:
            _identifier(identifier, "master ID")
            if identifier in identifiers or identifier in definitions:
                raise ValueError("duplicate master ID or master/chunk ID collision")
            identifiers.add(identifier)
            if not isinstance(expression, ChunkExpression) or expression.path.source_shape != self.reference_shape:
                raise ValueError("master expression must start at the dictionary reference")
            expression._validate_reference(definitions)
            for node in _nodes(expression):
                if node.kind == "chunk":
                    used[node.chunk_id].add(node.instance)
        if any(used[chunk.id] != set(range(len(chunk.instances))) for chunk in self.chunks):
            raise ValueError("dictionary contains an unused chunk definition or source guard")
        if not isinstance(self.search_limits, tuple) or len(dict(self.search_limits)) != len(self.search_limits):
            raise ValueError("invalid chunk search limits")
        object.__setattr__(self, "search_limits", tuple(tuple(pair) for pair in self.search_limits))
        if self.search_limits:
            limits = dict(self.search_limits)
            if set(limits) != set(_LIMIT_MINIMA):
                raise ValueError("unrecognized chunk search limits")
            for name, minimum in _LIMIT_MINIMA.items():
                _integer(limits[name], name, minimum)
            if limits["min_chunk_length"] > limits["max_chunk_length"]:
                raise ValueError("inconsistent chunk length limits")
            if (len(self.chunks) > min(limits["max_chunks"], limits["max_candidates"]) or
                    any(not limits["min_chunk_length"] <= len(chunk.moves.split()) <= limits["max_chunk_length"]
                        for chunk in self.chunks)):
                raise ValueError("dictionary exceeds its declared chunk search limits")
            if any(len(expression.path.moves.split()) > limits["max_word_moves"] and
                   any(node.kind != "literal" for node in _nodes(expression))
                   for _, expression in self.masters):
                raise ValueError("oversized master must retain a complete literal fallback")
            corpus_budget = max(limits["max_word_moves"],
                                4 * limits["max_chunk_length"] * isqrt(limits["max_candidates"]))
            eligible, total = set(), 0
            for identifier, expression in sorted(self.masters,
                                                  key=lambda pair: (pair[1].path.htm_length, pair[0])):
                size = expression.path.htm_length
                if size <= limits["max_word_moves"] and total + size <= corpus_budget:
                    eligible.add(identifier)
                    total += size
            if any(identifier not in eligible and expression.kind != "literal"
                   for identifier, expression in self.masters):
                raise ValueError("master outside the corpus budget must retain a literal fallback")

    @property
    def definitions(self):
        return {chunk.id: chunk for chunk in self.chunks}

    @property
    def master_formulas(self):
        return {identifier: expression.notation for identifier, expression in self.masters}

    def expand(self, master_id):
        for identifier, expression in self.masters:
            if identifier == master_id:
                return expression.path.moves
        raise KeyError(master_id)

    @property
    def metrics(self):
        learned = sum(len(chunk.moves.split()) for chunk in self.chunks)
        recipes = sum(expression.recipe_symbols for _, expression in self.masters)
        regrips = sum(expression.regrip_count for _, expression in self.masters)
        return {"dictionary_definition_moves": learned, "dictionary_definition_symbols": learned,
                "recipe_symbols": recipes, "regrip_count": regrips,
                "score": learned + recipes + regrips,
                "expanded_definition_moves": sum(len(expression.path.moves.split()) for _, expression in self.masters),
                "chunk_count": len(self.chunks), "master_count": len(self.masters)}

    @property
    def local_loops(self):
        return tuple({"master_id": identifier, "setup": node.children[0].path,
                      "body": node.children[1].path}
                     for identifier, expression in self.masters for node in _nodes(expression)
                     if node.kind == "transport")

    def to_dict(self):
        return {**_FORMAT, "reference_shape": self.reference_shape.labels,
                "chunks": [chunk.to_dict() for chunk in self.chunks],
                "masters": [{"id": identifier, "expression": expression.to_dict()}
                            for identifier, expression in self.masters],
                "search_limits": dict(self.search_limits), "metrics": self.metrics,
                "master_formulas": self.master_formulas}

    @classmethod
    def from_dict(cls, record):
        expected = set(_FORMAT) | {"reference_shape", "chunks", "masters", "search_limits", "metrics", "master_formulas"}
        if not isinstance(record, dict) or set(record) != expected:
            raise ValueError("invalid chunk dictionary record")
        if any(type(record[key]) is not type(value) or record[key] != value for key, value in _FORMAT.items()):
            raise ValueError("unsupported chunk dictionary format")
        if not isinstance(record["chunks"], list) or not isinstance(record["masters"], list):
            raise TypeError("dictionary chunks and masters must be lists")
        masters = []
        for master in record["masters"]:
            if not isinstance(master, dict) or set(master) != {"id", "expression"}:
                raise ValueError("invalid dictionary master record")
            masters.append((master["id"], ChunkExpression.from_dict(master["expression"])))
        if not isinstance(record["search_limits"], dict):
            raise TypeError("dictionary search limits must be a dictionary")
        result = cls(record["reference_shape"], tuple(AlgorithmChunk.from_dict(chunk) for chunk in record["chunks"]),
                     tuple(masters), tuple(sorted(record["search_limits"].items())))
        if (json.dumps(record["metrics"], sort_keys=True) != json.dumps(result.metrics, sort_keys=True) or
                record["master_formulas"] != result.master_formulas):
            raise ValueError("saved chunk metrics or formulas disagree with verified grammar")
        return result


@lru_cache(maxsize=32768)
def _family(word):
    return min(_rotated_word(candidate, rotation)
               for candidate in (word, _inverse(word)) for rotation in _ROTATIONS)


@lru_cache(maxsize=4096)
def _variants(word):
    variants = {}
    for inverse, candidate in ((False, word), (True, _inverse(word))):
        for rotation in _ROTATIONS:
            spelling = _rotated_word(candidate, rotation)
            score = (int(inverse) + int(bool(rotation)), len(rotation.split()), inverse, rotation)
            if spelling not in variants or score < variants[spelling][0]:
                variants[spelling] = score, inverse, rotation
    return tuple((spelling, inverse, rotation) for spelling, (_, inverse, rotation) in sorted(variants.items()))


def _match(word, index, remaining, spelling):
    """Match a phrase, optionally stopping halfway through a half turn."""
    if index + len(spelling) > len(word):
        return None
    for offset, move in enumerate(spelling):
        actual = _token(word[index][0], remaining) if offset == 0 else word[index + offset]
        if move == actual:
            continue
        if (offset == len(spelling) - 1 and actual.endswith("2") and
                move[0] == actual[0] and _amount(move) in (1, 3)):
            return index + offset, _amount(move)
        return None
    following = index + len(spelling)
    return following, _amount(word[following]) if following < len(word) else 0


@lru_cache(maxsize=2048)
def _alphabet(selected):
    alphabet = {}
    for number, definition in enumerate(selected):
        for spelling, inverse, rotation in _variants(definition):
            key = (spelling[0], spelling[1] if len(spelling) > 2 else None)
            alphabet.setdefault(key, []).append((spelling, number, inverse, rotation))
    return alphabet


def _parse(word, selected):
    """Finite dynamic-programming phrase cover with a literal fallback."""
    alphabet = _alphabet(tuple(selected))

    @lru_cache(maxsize=None)
    def solve(index, remaining):
        if index == len(word):
            return (0, 0, ()), ()
        following = index + 1
        tail_score, tail = solve(following, _amount(word[following]) if following < len(word) else 0)
        literal = ("literal", (_token(word[index][0], remaining),))
        score = (tail_score[0] + 1, tail_score[1] + 1, (literal, *tail_score[2]))
        result = (literal, *tail)
        first = _token(word[index][0], remaining)
        second = word[index + 1] if index + 1 < len(word) else None
        candidates = (*alphabet.get((first, second), ()), *alphabet.get((first, None), ()))
        for spelling, number, inverse, rotation in candidates:
            endpoint = _match(word, index, remaining, spelling)
            if endpoint is None:
                continue
            suffix_score, suffix = solve(*endpoint)
            atom = ("chunk", number, inverse, rotation)
            alternative = (suffix_score[0] + 1 + int(inverse) + int(bool(rotation)),
                           suffix_score[1] + 1, (atom, *suffix_score[2]))
            if alternative < score:
                score, result = alternative, (atom, *suffix)
        return score, result

    return solve(0, _amount(word[0]) if word else 0)


def _transport_parts(reference, word):
    for length in range((len(word) - 1) // 2, 0, -1):
        setup, body, undo = word[:length], word[length:-length], word[-length:]
        if _inverse(setup) != undo:
            continue
        path = ShapePath.from_moves(reference, " ".join(setup))
        local = ShapePath.from_moves(path.target_shape, " ".join(body))
        if local.is_closed:
            return setup, body, path.target_shape
    return None


def extract_algorithm_chunks(reference_shape, algorithms, *, min_chunk_length=3,
                             max_chunk_length=8, max_chunks=12,
                             max_candidates=256, max_word_moves=96):
    """Search a shared dictionary for named physical words in one reference.

    Proper regrips and inverses reuse a definition but pay instruction costs.
    The deterministic greedy search accepts a phrase only when the total
    definition/recipe/regrip score falls.  Budgets bound candidate mining and
    selection; oversized words retain their complete literal checked paths.
    Total searched corpus moves are bounded by ``max(max_word_moves,
    4 * max_chunk_length * isqrt(max_candidates))``; shortest eligible masters
    enter first, and additional masters retain complete literal paths.  Cheap
    substring counts cap candidates before geometric normalization and parsing.
    All supplied words are replayed even when the search budget is zero.
    """
    limits = {"min_chunk_length": _integer(min_chunk_length, "min_chunk_length", 2),
              "max_chunk_length": _integer(max_chunk_length, "max_chunk_length", 2),
              "max_chunks": _integer(max_chunks, "max_chunks", 0),
              "max_candidates": _integer(max_candidates, "max_candidates", 0),
              "max_word_moves": _integer(max_word_moves, "max_word_moves", 0)}
    if min_chunk_length > max_chunk_length:
        raise ValueError("min_chunk_length exceeds max_chunk_length")
    if not hasattr(algorithms, "items"):
        raise TypeError("algorithms must map master IDs to physical words")
    reference = shape(reference_shape)
    words, master_paths = {}, {}
    for identifier, moves in sorted(algorithms.items()):
        _identifier(identifier, "master ID")
        # Validate the unsimplified word before permitting cancellation.
        path = ShapePath.from_moves(reference, moves)
        words[identifier] = tuple(path.moves.split())
        master_paths[identifier] = path

    corpus_budget = max(max_word_moves, 4 * max_chunk_length * isqrt(max_candidates))
    eligible, corpus_moves = set(), 0
    for identifier, word in sorted(words.items(), key=lambda pair: (len(pair[1]), pair[0])):
        if len(word) <= max_word_moves and corpus_moves + len(word) <= corpus_budget:
            eligible.add(identifier)
            corpus_moves += len(word)
    transports = {identifier: _transport_parts(reference, word) if identifier in eligible else None
                  for identifier, word in words.items()}

    segments = []
    for identifier, word in words.items():
        if identifier not in eligible:
            continue
        parts = transports[identifier]
        segments.extend((parts[0], parts[1]) if parts else (word,))
    raw_counts = {}
    for word in segments if max_chunks and max_candidates else ():
        for start in range(len(word)):
            for length in range(min_chunk_length, min(max_chunk_length, len(word) - start) + 1):
                literal = word[start:start + length]
                # Split only boundary half turns: each variant remains a legal
                # prefix/suffix at that face and can be checked independently.
                first = (literal[0], literal[0][0], literal[0][0] + "'") if literal[0].endswith("2") else (literal[0],)
                last = (literal[-1], literal[-1][0], literal[-1][0] + "'") if literal[-1].endswith("2") else (literal[-1],)
                for head in first:
                    for tail in last:
                        spelling = (head, *literal[1:-1], tail)
                        raw_counts[spelling] = raw_counts.get(spelling, 0) + 1

    # The expensive 48-way equivalence and phrase-cover work sees at most
    # max_candidates raw spellings.  Counts are inexpensive and reward actual
    # repeated phrases before unrelated one-off substrings enter the budget.
    raw_pool = sorted(raw_counts, key=lambda spelling:
                      (-(raw_counts[spelling] - 1) * (len(spelling) - 1),
                       -len(spelling), spelling))[:max_candidates]
    candidates = {}
    for spelling in raw_pool:
        candidates.setdefault(_family(spelling), set()).add(spelling)

    # Rank families by actual occurrences, including proper rotated/inverse
    # forms.  This keeps one-off long phrases from filling the finite budget.
    ranked = []
    for family, spellings in candidates.items():
        occurrences = sum(raw_counts.get(spelling, 0) for spelling, _, _ in _variants(family))
        if occurrences < 2:
            continue
        # Keep an observed grip as the definition, rather than an arbitrary
        # lexicographic canonical grip that adds needless regrips everywhere.
        representative = min(spellings, key=lambda spelling:
                             (sum((int(inverse) + int(bool(rotation))) * raw_counts.get(variant, 0)
                                  for variant, inverse, rotation in _variants(spelling)), spelling))
        ranked.append((-(occurrences - 1) * (len(family) - 1), family, representative))
    pool = [representative for _, _, representative in sorted(ranked)[:max_candidates]]

    def score(selected):
        parses = [_parse(word, selected)[0] for word in segments]
        # At equal total description cost, prefer the fewer recipe atoms of
        # a longer coherent phrase over several dangling individual turns.
        return (sum(map(len, selected)) + sum(parsed[0] for parsed in parses),
                sum(parsed[1] for parsed in parses))

    selected, current = [], score(())
    for _ in range(max_chunks):
        alternatives = [(score((*selected, candidate)), candidate) for candidate in pool if candidate not in selected]
        if not alternatives:
            break
        best, candidate = min(alternatives)
        if best[0] >= current[0]:
            break
        selected.append(candidate)
        current = best

    # Drop previously useful definitions that become unused after a larger
    # phrase wins.  Otherwise the persistence guards would contain dead words.
    while selected:
        used = {atom[1] for word in segments for atom in _parse(word, selected)[1] if atom[0] == "chunk"}
        if used == set(range(len(selected))):
            break
        selected = [definition for index, definition in enumerate(selected) if index in used]

    instances = [[] for _ in selected]
    reserved = set(words)
    chunk_ids = []
    for _ in selected:
        number = len(chunk_ids) + 1
        identifier = f"C{number}"
        while identifier in reserved:
            number += 1
            identifier = f"C{number}"
        reserved.add(identifier)
        chunk_ids.append(identifier)

    def compile_segment(source, word, *, literal_only=False):
        atoms = (("literal", word),) if literal_only else _parse(word, selected)[1]
        combined = []
        for atom in atoms:
            if combined and combined[-1][0] == atom[0] == "literal":
                combined[-1] = ("literal", (*combined[-1][1], *atom[1]))
            else:
                combined.append(atom)
        children, current_shape = [], source
        for atom in combined:
            if atom[0] == "literal":
                path = ShapePath.from_moves(current_shape, " ".join(atom[1]))
                child = ChunkExpression("literal", path)
            else:
                _, number, inverse, rotation = atom
                spelling = _inverse(selected[number]) if inverse else selected[number]
                moves = rotate_moves(" ".join(spelling), rotation)
                path = ShapePath.from_moves(current_shape, moves)
                definition_path = path.rotated(inverse_rotation(rotation)).reframed("")
                if inverse:
                    definition_path = definition_path.inverse()
                if definition_path not in instances[number]:
                    instances[number].append(definition_path)
                index = instances[number].index(definition_path)
                child = ChunkExpression("chunk", path, chunk_id=chunk_ids[number], instance=index,
                                        inverse=inverse, rotation=rotation)
            children.append(child)
            current_shape = path.target_shape
        if len(children) == 1:
            return children[0]
        path = ShapePath.from_moves(source, " ".join(word))
        return ChunkExpression("sequence", path, tuple(children))

    masters = []
    for identifier, word in words.items():
        parts = transports[identifier]
        if parts:
            setup, body, local_shape = parts
            children = (compile_segment(reference, setup), compile_segment(local_shape, body))
            expression = ChunkExpression("transport", master_paths[identifier], children)
        else:
            expression = compile_segment(reference, word, literal_only=identifier not in eligible)
        masters.append((identifier, expression))
    chunks = tuple(AlgorithmChunk(identifier, " ".join(definition), tuple(paths))
                   for identifier, definition, paths in zip(chunk_ids, selected, instances))
    return ChunkDictionary(reference, chunks, tuple(masters), tuple(sorted(limits.items())))


__all__ = ["AlgorithmChunk", "ChunkExpression", "ChunkDictionary", "extract_algorithm_chunks"]
