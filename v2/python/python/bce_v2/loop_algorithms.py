"""Bounded discovery of witnessed powers, commutators and conjugates.

Every leaf ultimately refers to an original loop at one reference root. Words
execute left to right: [A, B] means A B A^-1 B^-1, and conj(S, A) means
S A S^-1. Discovery is a finite experiment, not a completeness or optimality
claim. The complete original loop set is retained separately in each library.
"""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from itertools import zip_longest
import json
from math import isqrt, lcm
from pathlib import Path
import re

from . import BlockedMoveError, State
from ._moves import _simplified_moves
from .block_actions import _CELL_POINTS, _POINTS
from .isotropy import IsotropyAnalysis, LoopGenerators, isotropy_loops
from .loop_rotations import (
    bandage_symmetries, inverse_rotation, normalize_rotation, rotate_moves, rotate_permutation,
)


_IDENTITY = tuple(range(48))
_MOVE = re.compile(r"[URFDLB](?:2|')?")


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        qualifier = "nonnegative" if minimum == 0 else "positive"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def _inverse_moves(moves):
    return tuple(move if move.endswith("2") else move[:-1] if move.endswith("'")
                 else move + "'" for move in reversed(moves))


def _inverse(permutation):
    result = [0] * len(permutation)
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


def _then(first, second):
    return tuple(second[point] for point in first)


def _power(permutation, exponent):
    result, seen = list(range(len(permutation))), set()
    for start in range(len(permutation)):
        if start in seen:
            continue
        cycle, point = [], start
        while point not in seen:
            seen.add(point)
            cycle.append(point)
            point = permutation[point]
        shift = exponent % len(cycle)
        for index, point in enumerate(cycle):
            result[point] = cycle[(index + shift) % len(cycle)]
    return tuple(result)


def _order(permutation):
    seen, result = set(), 1
    for start in range(len(permutation)):
        if start in seen:
            continue
        length, point = 0, start
        while point not in seen:
            seen.add(point)
            length += 1
            point = permutation[point]
        result = lcm(result, length)
    return result


def _records(generators):
    if hasattr(generators, "analysis"):
        generators = generators.analysis
    if isinstance(generators, IsotropyAnalysis):
        generators = generators.loops
    if hasattr(generators, "loops"):
        generators = generators.loops
    if isinstance(generators, LoopGenerators):
        generators = generators.generators
    if isinstance(generators, dict):
        return generators
    return {generator.id: generator for generator in generators}


def _reference(initial):
    if isinstance(initial, IsotropyAnalysis):
        return initial.loops
    if hasattr(initial, "analysis"):
        return initial.analysis.loops
    return isotropy_loops(initial)


def _loops_from_records(generators):
    """Recover the legal reference from original witness records."""
    if hasattr(generators, "analysis"):
        generators = generators.analysis
    if hasattr(generators, "loops"):
        generators = generators.loops
    if isinstance(generators, LoopGenerators):
        return generators
    records = _records(generators)
    if not records:
        raise ValueError("expanded_moves requires original witnesses with a reference root")
    owners = [getattr(record, "_owner", None) for record in records.values()]
    if owners[0] is None or any(owner is not owners[0] for owner in owners):
        raise ValueError("original witnesses must share a reference root")
    return LoopGenerators(owners[0])


@dataclass(frozen=True)
class LoopExpression:
    """An immutable expression whose witnesses execute in written order.

    A ``turns`` leaf displays a physical word while retaining an original
    loop expression as its sole child. Its declaration is verified when built
    as an algorithm; hiding provenance never hides a legality requirement.
    """

    kind: str
    children: tuple = ()
    exponent: int = 1
    generator_id: int | None = None
    moves: str | None = None
    rotation: str | None = None

    def __post_init__(self):
        arities = {"loop": 0, "sequence": None, "power": 1,
                   "commutator": 2, "conjugate": 2, "turns": 1, "rotated": 1}
        if self.kind not in arities:
            raise ValueError(f"unknown loop expression kind {self.kind!r}")
        if not isinstance(self.children, tuple) or any(not isinstance(c, LoopExpression)
                                                      for c in self.children):
            raise TypeError("expression children must be a tuple of LoopExpression values")
        arity = arities[self.kind]
        if arity is not None and len(self.children) != arity:
            raise ValueError(f"{self.kind} requires {arity} children")
        if isinstance(self.exponent, bool) or not isinstance(self.exponent, int):
            raise TypeError("expression exponent must be an integer")
        if self.kind == "loop":
            _integer(self.generator_id, "generator ID", 0)
        elif self.generator_id is not None:
            raise ValueError("only a loop leaf has a generator ID")
        if self.kind != "power" and self.exponent != 1:
            raise ValueError("only a power expression has an exponent other than one")
        if self.kind == "turns":
            if not isinstance(self.moves, str):
                raise TypeError("literal turns must be a Singmaster string")
            if any(_MOVE.fullmatch(move) is None for move in self.moves.split()):
                raise ValueError("literal turns must use outer-face Singmaster notation")
            object.__setattr__(self, "moves", _simplified_moves(self.moves.split()))
        elif self.moves is not None:
            raise ValueError("only a turns leaf has literal moves")
        if self.kind == "rotated":
            object.__setattr__(self, "rotation", normalize_rotation(self.rotation))
        elif self.rotation is not None:
            raise ValueError("only a rotated expression has a rotation")

    @classmethod
    def loop(cls, generator_id):
        return cls("loop", generator_id=generator_id)

    @classmethod
    def sequence(cls, *expressions):
        """Join words, combining adjacent equal expressions into powers."""
        result = []
        for expression in expressions:
            if not isinstance(expression, cls):
                raise TypeError("sequence operands must be LoopExpression values")
            children = expression.children if expression.kind == "sequence" else (expression,)
            for child in children:
                body, exponent = (child.children[0], child.exponent) if child.kind == "power" else (child, 1)
                if result:
                    previous = result[-1]
                    previous_body, previous_exponent = ((previous.children[0], previous.exponent)
                                                        if previous.kind == "power" else (previous, 1))
                    if previous_body == body:
                        result.pop()
                        exponent += previous_exponent
                if exponent:
                    result.append(body if exponent == 1 else cls.power(body, exponent))
        return cls("sequence", tuple(result))

    @classmethod
    def power(cls, expression, exponent):
        if not isinstance(expression, cls):
            raise TypeError("power operand must be a LoopExpression")
        if isinstance(exponent, bool) or not isinstance(exponent, int):
            raise TypeError("expression power must be an integer")
        if expression.kind == "power":
            exponent *= expression.exponent
            expression = expression.children[0]
        return cls("power", (expression,), exponent)

    @classmethod
    def commutator(cls, first, second):
        return cls("commutator", (first, second))

    @classmethod
    def conjugate(cls, setup, body):
        return cls("conjugate", (setup, body))

    @classmethod
    def turns(cls, moves, witness):
        return cls("turns", (witness,), moves=moves)

    @classmethod
    def rotated(cls, rotation, body):
        """Transfer a witnessed loop by a proper bandage-preserving regrip."""
        if not isinstance(body, cls):
            raise TypeError("rotation operand must be a LoopExpression")
        rotation = normalize_rotation(rotation)
        while body.kind == "rotated":
            rotation = normalize_rotation(rotation + " " + body.rotation)
            body = body.children[0]
        return cls("rotated", (body,), rotation=rotation) if rotation else body

    @property
    def base_ids(self):
        if self.kind == "loop":
            return (self.generator_id,)
        return tuple(sorted({identifier for child in self.children for identifier in child.base_ids}))

    @property
    def memory_keys(self):
        """Visible memorized leaves, treating a literal word and inverse alike."""
        if self.kind == "loop":
            return (("loop", self.generator_id),)
        if self.kind == "turns":
            word = tuple(self.moves.split())
            return (("turns", min(word, _inverse_moves(word))),)
        return tuple(sorted({key for child in self.children for key in child.memory_keys}, key=repr))

    def render(self):
        if self.kind == "loop":
            return f"L{self.generator_id}"
        if self.kind == "turns":
            return "{" + self.moves + "}"
        if self.kind == "sequence":
            return " ".join(child.render() for child in self.children) or "()"
        if self.kind == "power":
            child = self.children[0]
            rendered = child.render()
            if child.kind not in ("loop", "turns"):
                rendered = "(" + rendered + ")"
            return rendered + f"^{self.exponent}"
        if self.kind == "rotated":
            return f"rotate({self.rotation or '()'}, {self.children[0].render()})"
        first, second = (child.render() for child in self.children)
        return f"[{first}, {second}]" if self.kind == "commutator" else f"conj({first}, {second})"

    def render_moves(self, generators):
        """Display actual turns while preserving powers and bracket structure.

        ``(R U)3`` repeats a word, ``[A, B]`` means A B A^-1 B^-1,
        and ``[S: A]`` means S A S^-1. Inverses reverse the actual turns;
        negative powers repeat that inverted word with a positive exponent.
        This display notation is distinct from the expanded Singmaster word
        accepted by State.apply(). Original-ID render() remains unchanged.
        """
        records = _records(generators)
        missing = set(self.base_ids) - set(records)
        if missing:
            raise ValueError(f"unknown original loop IDs: {sorted(missing)}")

        def display(node, inverse=False):
            if node.kind == "loop":
                moves = records[node.generator_id].turn_sequence.split()
                return " ".join(_inverse_moves(moves) if inverse else moves) or "()"
            if node.kind == "turns":
                moves = node.moves.split()
                return " ".join(_inverse_moves(moves) if inverse else moves) or "()"
            if node.kind == "sequence":
                children = reversed(node.children) if inverse else node.children
                words = [display(child, inverse) for child in children]
                return " ".join(word for word in words if word != "()") or "()"
            if node.kind == "power":
                exponent = -node.exponent if inverse else node.exponent
                if exponent == 0:
                    return "()"
                body = display(node.children[0], exponent < 0)
                exponent = abs(exponent)
                if body == "()" or exponent == 1:
                    return body
                if _MOVE.fullmatch(body):
                    amount = 2 if body.endswith("2") else 3 if body.endswith("'") else 1
                    amount = amount * exponent % 4
                    if not amount:
                        return "()"
                    return body[0] + ("2" if amount == 2 else "'" if amount == 3 else "")
                return "(" + body + ")" + str(exponent)
            if node.kind == "rotated":
                body = display(node.children[0], inverse)
                if not node.rotation:
                    return body
                return f"{node.rotation} ({body}) {inverse_rotation(node.rotation)}"
            first, second = node.children
            if node.kind == "commutator":
                if inverse:
                    first, second = second, first
                return f"[{display(first)}, {display(second)}]"
            return f"[{display(first)}: {display(second, inverse)}]"

        return display(self)

    def __str__(self):
        return self.render()

    def to_dict(self):
        record = {"kind": self.kind}
        if self.kind == "loop":
            record["generator_id"] = self.generator_id
        else:
            record["children"] = [child.to_dict() for child in self.children]
        if self.kind == "power":
            record["exponent"] = self.exponent
        if self.kind == "turns":
            record["moves"] = self.moves
        if self.kind == "rotated":
            record["rotation"] = self.rotation
        return record

    def loop_steps(self, *, max_syllables=10_000):
        """Expand to original loop IDs and signed powers under a finite cap."""
        _integer(max_syllables, "max_syllables")

        def collect(expression):
            if expression.kind == "rotated":
                raise ValueError("rotation transfers retain geometric witnesses; use expanded_moves()")
            if expression.kind == "loop":
                return ((expression.generator_id, 1),)
            if expression.kind == "turns":
                return collect(expression.children[0])
            if expression.kind == "sequence":
                return merge(step for child in expression.children for step in collect(child))
            words = [collect(child) for child in expression.children]
            if expression.kind == "power":
                word, exponent = words[0], expression.exponent
                if not exponent or not word:
                    return ()
                if len(word) == 1:
                    return ((word[0][0], word[0][1] * exponent),)
                if exponent < 0:
                    word = tuple((identifier, -power) for identifier, power in reversed(word))
                if abs(exponent) * len(word) > max_syllables:
                    raise ValueError("expression expansion exceeds max_syllables")
                return merge(step for _ in range(abs(exponent)) for step in word)
            first, second = words
            inverse_first = tuple((identifier, -power) for identifier, power in reversed(first))
            if expression.kind == "conjugate":
                return merge((*first, *second, *inverse_first))
            inverse_second = tuple((identifier, -power) for identifier, power in reversed(second))
            return merge((*first, *second, *inverse_first, *inverse_second))

        def merge(steps):
            result = []
            for identifier, exponent in steps:
                if result and result[-1][0] == identifier:
                    exponent += result.pop()[1]
                if exponent:
                    result.append((identifier, exponent))
                if len(result) > max_syllables:
                    raise ValueError("expression expansion exceeds max_syllables")
            return tuple(result)

        return collect(self)

    def evaluate(self, generators):
        """Evaluate the faithful action without expanding repeated words."""
        return _evaluate(self, _records(generators), {})

    def expanded_moves(self, generators, *, max_expanded_moves=100_000):
        """Build a checked face-only witness, including certified regrip transfers."""
        _integer(max_expanded_moves, "max_expanded_moves")
        records = _records(generators)
        has_reference = (isinstance(generators, (LoopGenerators, IsotropyAnalysis))
                         or hasattr(generators, "loops") or hasattr(generators, "analysis"))
        reference = generators if has_reference else records
        loops = _loops_from_records(reference)
        return _build(self, loops, records, {}, {}, set(),
                      max_expanded_moves).turn_sequence

    def structure_cost(self, generators):
        """Description cost, learning each visible leaf only once."""
        records = _records(generators)
        visible_ids = [key[1] for key in self.memory_keys if key[0] == "loop"]
        lengths = {identifier: records[identifier].htm_length for identifier in visible_ids
                   if identifier in records}
        missing = set(self.base_ids) - set(records)
        if missing:
            raise ValueError(f"unknown original loop IDs: {sorted(missing)}")
        return _structure(self, lengths)[0]


def _evaluate(expression, records, cache):
    if expression in cache:
        return cache[expression]
    if expression.kind == "loop":
        if expression.generator_id not in records:
            raise ValueError(f"unknown original loop ID {expression.generator_id}")
        value = tuple(records[expression.generator_id].permutation)
    else:
        values = [_evaluate(child, records, cache) for child in expression.children]
        if expression.kind == "turns":
            value = values[0]
        elif expression.kind == "sequence":
            value = _IDENTITY
            for child in values:
                value = _then(value, child)
        elif expression.kind == "power":
            value = _power(values[0], expression.exponent)
        elif expression.kind == "rotated":
            value = rotate_permutation(values[0], expression.rotation)
        elif expression.kind == "commutator":
            first, second = values
            value = _then(_then(_then(first, second), _inverse(first)), _inverse(second))
        else:
            first, second = values
            value = _then(_then(first, second), _inverse(first))
    cache[expression] = value
    return value


def _structure(expression, lengths):
    leaves = {}

    def visit(node):
        if node.kind == "power" and not node.exponent:
            return 0, 0, 0
        if node.kind == "power" and abs(node.exponent) == 1:
            return visit(node.children[0])
        if node.kind == "rotated":
            # A symmetry transfer reuses the very same learned algorithm.
            return visit(node.children[0])
        if node.kind in ("loop", "turns"):
            if node.kind == "loop":
                key, length = ("loop", node.generator_id), lengths[node.generator_id]
            else:
                word = tuple(node.moves.split())
                key, length = ("turns", min(word, _inverse_moves(word))), len(word)
            leaves[key] = 1 + length
            return 0, 1, 1
        children = [visit(child) for child in node.children]
        overhead = (max(0, len(children) - 1) if node.kind == "sequence" else
                    1 + len(str(abs(node.exponent))) if node.kind == "power" else 2)
        return (overhead + sum(child[0] for child in children),
                1 + sum(child[1] for child in children),
                1 + max((child[2] for child in children), default=0))

    overhead, nodes, depth = visit(expression)
    return sum(leaves.values()) + overhead, len(leaves), nodes, depth


def _effect(permutation, inventory):
    support, kernel = [], True
    for index, block in enumerate(inventory.blocks):
        points = tuple(point for cell in block.cells for point in _CELL_POINTS[cell])
        if any(permutation[point] != point for point in points):
            support.append(index)
        locations = tuple(sorted(_POINTS[permutation[_CELL_POINTS[cell][0]]][0]
                                 if _CELL_POINTS[cell] else cell for cell in block.cells))
        if locations != block.cells:
            kernel = False
    return tuple(support), kernel


def _human_score(expression, permutation, inventory, lengths, records,
                 evaluations, htm_length, qtm_length):
    """Prefer localized effects and constituents, then reusable descriptions."""
    node = expression
    while node.kind == "rotated" or node.kind == "power" and abs(node.exponent) == 1:
        node = node.children[0]
    affected = len(_effect(permutation, inventory)[0])
    if node.kind == "sequence":
        application_affected = max((len(_effect(_evaluate(child, records, evaluations), inventory)[0])
                                    for child in node.children), default=0)
    else:
        application_affected = affected
    return (affected, application_affected, *_structure(expression, lengths),
            htm_length, qtm_length)


@dataclass(frozen=True)
class LoopAlgorithm:
    """A replayable exact effect with its visible expression and provenance.

    Costs refer to the simplified physical turn_sequence, unlike the raw QTM
    tree-witness lengths on the original LoopGenerator records.
    """

    id: str
    expression: LoopExpression
    permutation: tuple[int, ...]
    turn_sequence: str
    _inventory: object = field(repr=False, compare=False)
    _leaf_htm_lengths: tuple = field(default=(), repr=False, compare=False)
    _generators: tuple = field(default=(), repr=False, compare=False)
    _human_score: tuple = field(default=(), repr=False, compare=False)

    @property
    def moves(self):
        return self.turn_sequence

    @property
    def structured_turn_sequence(self):
        """Move-level powers and brackets, with the expanded word kept separately."""
        return self.expression.render_moves(self._generators)

    @property
    def qtm_length(self):
        return sum(2 if move.endswith("2") else 1 for move in self.turn_sequence.split())

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())

    @property
    def block_action(self):
        return self._inventory.action(self.permutation)

    @property
    def support(self):
        return _effect(self.permutation, self._inventory)[0]

    @property
    def is_kernel(self):
        return _effect(self.permutation, self._inventory)[1]

    @property
    def base_ids(self):
        return self.expression.base_ids

    @property
    def structure_score(self):
        if self._human_score:
            return self._human_score
        lengths = {identifier: self.htm_length for identifier in self.base_ids}
        lengths.update(self._leaf_htm_lengths)
        return _human_score(self.expression, self.permutation, self._inventory,
                            lengths, _records(self._generators), {},
                            self.htm_length, self.qtm_length)

    def to_dict(self, *, include_moves=True):
        record = {"id": self.id, "expression": self.expression.to_dict(),
                  "rendered_expression": self.expression.render(),
                  "permutation": list(self.permutation), "base_ids": list(self.base_ids),
                  "support": list(self.support), "is_kernel": self.is_kernel,
                  "structure_score": list(self.structure_score),
                  "qtm_length": self.qtm_length, "htm_length": self.htm_length,
                  "block_action": self.block_action.to_dict()}
        if include_moves:
            record.update(moves=self.moves, turn_sequence=self.turn_sequence,
                          structured_turn_sequence=self.structured_turn_sequence)
        return record


class _ExpansionLimit(ValueError):
    pass


class _LengthLimit(ValueError):
    pass


def _build(expression, loops, records, words, evaluations, verified_turns,
           max_expanded_moves, max_htm_length=None):
    if not isinstance(expression, LoopExpression):
        raise TypeError("algorithm expression must be a LoopExpression")
    missing = set(expression.base_ids) - set(records)
    if missing:
        raise ValueError(f"unknown original loop IDs: {sorted(missing)}")
    def verify_turns(node):
        if node in verified_turns:
            return
        if node.kind == "turns":
            if len(node.moves.split()) > max_expanded_moves:
                raise _ExpansionLimit("literal turns exceed max_expanded_moves")
            try:
                replay = State(loops.root_shape).apply(node.moves)
            except BlockedMoveError as error:
                raise ValueError("literal turns are blocked at the loop reference root") from error
            if (replay.shape != loops.root_shape
                    or replay.sticker_permutation != _evaluate(node.children[0], records, evaluations)):
                raise ValueError("literal turns do not match their original-loop witness")
        if (node.kind == "rotated" and node.rotation
                and node.rotation not in bandage_symmetries(loops.root_shape)):
            raise ValueError("rotation does not preserve the reference bandage shape")
        for child in node.children:
            verify_turns(child)
        verified_turns.add(node)

    verify_turns(expression)

    def expanded(node):
        if node.kind == "turns":
            return tuple(node.moves.split())
        if node.kind == "loop":
            identifier = node.generator_id
            if identifier not in words:
                if records[identifier].qtm_length > max_expanded_moves:
                    raise _ExpansionLimit("original loop witness exceeds max_expanded_moves")
                words[identifier] = tuple(records[identifier].turn_sequence.split())
            return words[identifier]
        if node.kind == "sequence":
            children, length = [], 0
            for child in node.children:
                word = expanded(child)
                length += len(word)
                if length > max_expanded_moves:
                    raise _ExpansionLimit("algorithm witness exceeds max_expanded_moves")
                children.append(word)
            return tuple(move for word in children for move in word)
        children = [expanded(child) for child in node.children]
        if node.kind == "rotated":
            return tuple(rotate_moves(" ".join(children[0]), node.rotation).split())
        if node.kind == "power":
            word, exponent = children[0], node.exponent
            if len(word) * abs(exponent) > max_expanded_moves:
                raise _ExpansionLimit("algorithm witness exceeds max_expanded_moves")
            if exponent < 0:
                word = _inverse_moves(word)
            return word * abs(exponent)
        first, second = children
        length = 2 * len(first) + (2 if node.kind == "commutator" else 1) * len(second)
        if length > max_expanded_moves:
            raise _ExpansionLimit("algorithm witness exceeds max_expanded_moves")
        word = first + second + _inverse_moves(first)
        return word + _inverse_moves(second) if node.kind == "commutator" else word

    turn_sequence = _simplified_moves(expanded(expression))
    if max_htm_length is not None and len(turn_sequence.split()) > max_htm_length:
        raise _LengthLimit("algorithm exceeds max_htm_length")
    permutation = _evaluate(expression, records, evaluations)
    digest = sha256(json.dumps([loops.root_shape.labels, expression.to_dict()],
                              sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    lengths = tuple((key[1], len(words[key[1]])) for key in expression.memory_keys if key[0] == "loop")
    htm_length = len(turn_sequence.split())
    qtm_length = sum(2 if move.endswith("2") else 1 for move in turn_sequence.split())
    score = _human_score(expression, permutation, loops.block_inventory, dict(lengths),
                         records, evaluations, htm_length, qtm_length)
    return LoopAlgorithm("A" + digest, expression, permutation, turn_sequence,
                         loops.block_inventory, lengths, loops.generators, score)


def _regrip_count(expression):
    """Break otherwise equal descriptions in favor of fewer regrips."""
    if expression.kind == "turns" or expression.kind == "power" and not expression.exponent:
        return 0
    own = 2 * len(expression.rotation.split()) if expression.kind == "rotated" else 0
    return own + sum(_regrip_count(child) for child in expression.children)


def _shortest_key(algorithm):
    return (algorithm.htm_length, algorithm.qtm_length, algorithm.structure_score,
            _regrip_count(algorithm.expression), algorithm.expression.render())


def _structured_key(algorithm):
    return (algorithm.structure_score, algorithm.htm_length, algorithm.qtm_length,
            _regrip_count(algorithm.expression), algorithm.expression.render())


def _register(pool, algorithm):
    if algorithm.permutation == _IDENTITY:
        return False
    previous = pool.get(algorithm.permutation)
    if previous is None:
        pool[algorithm.permutation] = (algorithm, algorithm)
        return True
    shortest, structured = previous
    if _shortest_key(algorithm) < _shortest_key(shortest):
        shortest = algorithm
    if _structured_key(algorithm) < _structured_key(structured):
        structured = algorithm
    pool[algorithm.permutation] = shortest, structured
    return (shortest, structured) != previous


def _select(pool, original_effects, max_algorithms):
    rankings = (
        sorted(pool, key=lambda effect: (*_shortest_key(pool[effect][0]), effect)),
        sorted(pool, key=lambda effect: (*_structured_key(pool[effect][1]), effect)),
        sorted(pool, key=lambda effect: (len(pool[effect][0].support),
                                        pool[effect][1].structure_score,
                                        pool[effect][0].htm_length, effect)),
        sorted(original_effects.intersection(pool),
               key=lambda effect: (*_shortest_key(pool[effect][0]), effect)),
    )
    effects, seen = [], set()
    for batch in zip_longest(*rankings):
        for effect in batch:
            if effect is not None and effect not in seen:
                effects.append(effect)
                seen.add(effect)
    algorithms, shortest, structured = [], [], []
    truncated = False
    for effect in effects:
        short, structure = pool[effect]
        representatives = (short,) if short.id == structure.id else (short, structure)
        if len(algorithms) + len(representatives) > max_algorithms:
            truncated = True
            continue
        algorithms.extend(representatives)
        shortest.append(short)
        structured.append(structure)
    return (tuple(algorithms), tuple(sorted(shortest, key=_shortest_key)),
            tuple(sorted(structured, key=_structured_key)), truncated)


@dataclass(frozen=True)
class AlgorithmLibrary:
    """Bounded representatives, plus the complete original witnessed loops.

    shortest and structured contain the best retained representative of each
    selected exact effect. The algorithms tuple is their union. Final limits
    can omit effects; they never alter loops or certify a generating family.
    """

    loops: LoopGenerators
    algorithms: tuple[LoopAlgorithm, ...]
    shortest: tuple[LoopAlgorithm, ...]
    structured: tuple[LoopAlgorithm, ...]
    max_seed_loops: int = 32
    rounds: int = 2
    max_candidates: int = 3000
    max_algorithms: int = 256
    max_htm_length: int = 120
    max_expanded_moves: int = 480
    seed_count: int = 0
    examined_count: int = 0
    rounds_completed: int = 0
    identity_count: int = 0
    duplicate_count: int = 0
    length_pruned_count: int = 0
    expansion_pruned_count: int = 0
    candidate_limit_reached: bool = False
    algorithm_limit_reached: bool = False
    original_limit_reached: bool = False
    round_limit_reached: bool = False
    custom_expression_count: int = 0
    symmetry_count: int = 0
    symmetry_transfer_count: int = 0

    @property
    def metadata(self):
        names = ("max_seed_loops", "rounds", "max_candidates", "max_algorithms", "max_htm_length",
                 "max_expanded_moves", "seed_count", "examined_count", "rounds_completed",
                 "identity_count", "duplicate_count", "length_pruned_count", "expansion_pruned_count",
                 "candidate_limit_reached", "algorithm_limit_reached", "original_limit_reached",
                 "round_limit_reached", "custom_expression_count", "symmetry_count",
                 "symmetry_transfer_count")
        return {**{name: getattr(self, name) for name in names}, "exhaustive": False,
                "proposal_budget_pruned": self.original_limit_reached or self.round_limit_reached
                or self.candidate_limit_reached,
                "original_loop_count": len(self.loops), "effect_count": len(self.shortest),
                "algorithm_count": len(self.algorithms),
                "literal_policy": "when a literal word has a smaller description cost"}

    def build_algorithm(self, expression, *, max_expanded_moves=100_000, max_htm_length=None):
        """Evaluate a custom expression with a finite witness expansion budget.

        This explicit builder can exceed discovery's display-length bound. It
        verifies all declared literal leaves against legal reference replay.
        """
        _integer(max_expanded_moves, "max_expanded_moves")
        if max_htm_length is not None:
            _integer(max_htm_length, "max_htm_length")
        return _build(expression, self.loops, _records(self.loops), {}, {}, set(),
                      max_expanded_moves, max_htm_length)

    def with_expressions(self, *expressions):
        """Return a new library retaining the best custom alternatives too."""
        pool = {}
        for algorithm in self.algorithms:
            _register(pool, algorithm)
        for expression in expressions:
            _register(pool, self.build_algorithm(expression))
        original_effects = {generator.permutation for generator in self.loops}
        algorithms, shortest, structured, truncated = _select(pool, original_effects, self.max_algorithms)
        return replace(self, algorithms=algorithms, shortest=shortest, structured=structured,
                       algorithm_limit_reached=self.algorithm_limit_reached or truncated,
                       custom_expression_count=self.custom_expression_count + len(expressions))

    def to_dict(self, *, include_moves=True):
        return {"format": "bce-v2-algorithm-library", "version": 1,
                "model": "full-grid-27-fixed-centers", "root_shape": self.loops.root_shape.labels,
                "root_vertex": self.loops.root_vertex, "metadata": self.metadata,
                "commutator_convention": "A B A^-1 B^-1",
                "conjugation_convention": "setup body setup^-1",
                "score": "affected-blocks, largest-constituent-support, memory-cost, visible-leaves, syntax-nodes, depth, HTM, QTM",
                "shortest_ids": [algorithm.id for algorithm in self.shortest],
                "structured_ids": [algorithm.id for algorithm in self.structured],
                "algorithms": [algorithm.to_dict(include_moves=include_moves) for algorithm in self.algorithms],
                "loops": self.loops.to_dict(include_moves=include_moves)}

    def to_json(self, path=None, *, include_moves=True):
        text = json.dumps(self.to_dict(include_moves=include_moves), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_moves=True):
        self.to_json(path, include_moves=include_moves)
        return self.to_dict(include_moves=include_moves)


def _mining_expressions(operands, symmetries=()):
    def powers():
        for algorithm in operands:
            order = _order(algorithm.permutation)
            placement_order = _order(algorithm.block_action.destinations)
            # Proper divisors isolate cycles beyond the small 2/3/4 cases:
            # for example, fifth/seventh powers separate order-5 and order-7
            # components of an order-35 action. Cycle lengths and their LCM
            # complements are included because each divides the full order.
            divisors = set()
            for divisor in range(2, isqrt(order) + 1):
                if order % divisor == 0:
                    divisors.update((divisor, order // divisor))
            exponents = [placement_order, 2, -2, 3, -3, 4, -placement_order]
            exponents.extend(sorted(divisors))
            normalized = set()
            for exponent in exponents:
                exponent %= order
                if 2 * exponent > order:
                    exponent -= order
                if exponent not in (-1, 0, 1) and exponent not in normalized:
                    normalized.add(exponent)
                    yield LoopExpression.power(algorithm.expression, exponent)

    def commutators():
        for index, first in enumerate(operands):
            for second in operands[index + 1:]:
                if (first.is_kernel and second.is_kernel
                        or not set(first.support).intersection(second.support)):
                    continue
                yield LoopExpression.commutator(first.expression, second.expression)
                yield LoopExpression.commutator(second.expression, first.expression)

    def conjugates():
        for index, setup in enumerate(operands):
            for other_index, body in enumerate(operands):
                if (index == other_index or setup.is_kernel and body.is_kernel
                        or not set(setup.support).intersection(body.support)):
                    continue
                yield LoopExpression.conjugate(setup.expression, body.expression)

    def transfers():
        for algorithm in operands:
            for rotation in symmetries:
                yield LoopExpression.rotated(rotation, algorithm.expression)

    for batch in zip_longest(powers(), commutators(), conjugates(), transfers()):
        for expression in batch:
            if expression is not None:
                yield expression


def discover_loop_algorithms(initial, *, max_seed_loops=32, rounds=2,
                             max_candidates=3000, max_algorithms=256,
                             max_htm_length=120):
    """Mine bounded exact effects, retaining short and structured alternatives.

    No GAP is needed. Complete original loops remain available even when only
    a bounded subset supplies mining seeds. Support includes orientation-only
    effects. Constructions use actual legal root loops and certified bandage
    symmetries. Each round receives a share of the remaining proposal budget;
    powers, commutators, conjugates and transfers are interleaved.
    """
    for name, value in (("max_seed_loops", max_seed_loops), ("rounds", rounds),
                        ("max_candidates", max_candidates), ("max_algorithms", max_algorithms),
                        ("max_htm_length", max_htm_length)):
        _integer(value, name, 0 if name == "rounds" else 1)
    loops = _reference(initial)
    symmetries = bandage_symmetries(loops.root_shape)
    records, words, evaluations, verified_turns = _records(loops), {}, {}, set()
    pool, originals, seen = {}, [], set()
    counts = dict(examined_count=0, identity_count=0, duplicate_count=0,
                  length_pruned_count=0, expansion_pruned_count=0,
                  symmetry_transfer_count=0)
    expansion_cap = max_htm_length * 4
    limited, round_limited = False, False

    def attempt(expression):
        nonlocal limited
        if counts["examined_count"] >= max_candidates:
            limited = True
            return None
        counts["examined_count"] += 1
        if expression.kind == "rotated":
            counts["symmetry_transfer_count"] += 1
        if expression in seen:
            counts["duplicate_count"] += 1
            return None
        seen.add(expression)
        try:
            algorithm = _build(expression, loops, records, words, evaluations, verified_turns,
                               expansion_cap, max_htm_length)
        except _ExpansionLimit:
            counts["expansion_pruned_count"] += 1
            return None
        except _LengthLimit:
            counts["length_pruned_count"] += 1
            return None
        if algorithm.permutation == _IDENTITY:
            counts["identity_count"] += 1
            return None
        if not _register(pool, algorithm):
            counts["duplicate_count"] += 1
        return algorithm

    original_budget = min(max_seed_loops, max_candidates,
                          max(1, max_candidates // (rounds + 1)))
    for generator in loops.generators[:original_budget]:
        if counts["examined_count"] >= max_candidates:
            limited = True
            break
        algorithm = attempt(LoopExpression.loop(generator.id))
        if algorithm is not None:
            originals.append(algorithm)
    original_effects = {algorithm.permutation for algorithm in originals}
    seeds = sorted(originals, key=lambda algorithm: (
        algorithm.htm_length, algorithm.qtm_length, algorithm.expression.render()))[:max_seed_loops]
    operands, rounds_completed = seeds, 0
    for round_index in range(rounds):
        if not operands or counts["examined_count"] >= max_candidates:
            limited = limited or bool(operands)
            break
        remaining = max_candidates - counts["examined_count"]
        round_limit = counts["examined_count"] + max(1, remaining // (rounds - round_index))
        fresh = []
        for expression in _mining_expressions(operands, symmetries):
            if counts["examined_count"] >= round_limit:
                round_limited = True
                break
            algorithm = attempt(expression)
            if algorithm is None:
                continue
            fresh.append(algorithm)
            if (1 + algorithm.htm_length < algorithm.expression.structure_cost(records)
                    and counts["examined_count"] < round_limit):
                literal = attempt(LoopExpression.turns(algorithm.turn_sequence, algorithm.expression))
                if literal is not None:
                    fresh.append(literal)
        rounds_completed += 1
        if not fresh:
            break
        # Keep setup loops alongside new structured bodies. A frontier made
        # solely of kernel elements cannot produce productive commutators.
        setup_count = min(len(seeds), max(1, max_seed_loops // 3))
        next_operands = list(seeds[:setup_count])
        effects = {algorithm.permutation for algorithm in next_operands}
        for algorithm in sorted(fresh, key=lambda candidate: (
                candidate.expression.kind not in ("commutator", "conjugate"),
                len(candidate.support), candidate.structure_score,
                candidate.htm_length, candidate.expression.render())):
            if algorithm.permutation not in effects:
                next_operands.append(algorithm)
                effects.add(algorithm.permutation)
            if len(next_operands) >= max_seed_loops:
                break
        operands = next_operands[:max_seed_loops]
    if rounds and counts["examined_count"] >= max_candidates:
        limited = True
    algorithms, shortest, structured, truncated = _select(pool, original_effects, max_algorithms)
    return AlgorithmLibrary(loops, algorithms, shortest, structured,
                            max_seed_loops=max_seed_loops, rounds=rounds,
                            max_candidates=max_candidates, max_algorithms=max_algorithms,
                            max_htm_length=max_htm_length, max_expanded_moves=expansion_cap,
                            seed_count=len(seeds), rounds_completed=rounds_completed,
                            candidate_limit_reached=limited, algorithm_limit_reached=truncated,
                            original_limit_reached=original_budget < len(loops),
                            round_limit_reached=round_limited,
                            symmetry_count=len(symmetries),
                            **counts)
