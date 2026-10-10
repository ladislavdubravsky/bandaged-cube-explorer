"""Reusable physical algorithms discovered before choosing a stabilizer chain.

Discovery is bounded. Pure orientation coverage is measured exactly in the
actual cyclic block coordinates; an incomplete dictionary never acquires a
completeness claim from its size or from having found a few localized effects.
All exported words retain expressions in the original legal root loops.
"""

from collections import Counter, deque
from dataclasses import dataclass, field
from itertools import zip_longest
import json
from math import gcd, prod
from pathlib import Path

from . import Shape, State
from .computation import checkpoint, report_progress
from .gap_backend import analyze_generators
from .isotropy import IsotropyAnalysis
from .loop_algorithms import (
    AlgorithmLibrary, LoopAlgorithm, LoopExpression, _ExpansionLimit, _LengthLimit, _integer,
    _reference, _then, discover_loop_algorithms,
)
from .loop_rotations import normalize_rotation, rotate_moves, rotate_permutation


_IDENTITY = tuple(range(48))
_ORIGINAL_KINDS = {"loop", "sequence", "power", "commutator", "conjugate"}


def _prime_parts(number):
    result, prime = {}, 2
    while prime * prime <= number:
        power = 1
        while number % prime == 0:
            number //= prime
            power *= prime
        if power > 1:
            result[prime] = power
        prime += 1
    if number > 1:
        result[number] = number
    return result


def _coordinate_span(vectors, orders):
    """Exact subgroup order in a product of cyclic coordinates.

    For prime-order coordinates this is ordinary finite-field elimination.
    Prime-power coordinates also insert pivot-order multiples: these carry
    vectors generate the kernel of a coordinate projection. They matter for
    fused blocks with order four, where reduction modulo two alone loses
    information. Projection image order times kernel order gives exact span.
    """
    orders = tuple(orders)
    rows = tuple(tuple(vector) for vector in vectors)
    if any(len(row) != len(orders) for row in rows):
        raise ValueError("orientation vectors have the wrong dimension")
    if any(type(order) is not int or order < 1 for order in orders):
        raise ValueError("orientation orders must be positive integers")
    parts = tuple(_prime_parts(order) for order in orders)
    primes = sorted({prime for part in parts for prime in part})
    primary = {}
    for prime in primes:
        moduli = tuple(part.get(prime, 1) for part in parts)
        active = [tuple(value % modulus for value, modulus in zip(row, moduli))
                  for row in rows]
        cardinality, pivots = 1, []
        for column, modulus in enumerate(moduli):
            nonzero = [row for row in active if row[column]]
            if not nonzero:
                continue
            pivot = min(nonzero, key=lambda row: gcd(row[column], modulus))
            divisor = gcd(pivot[column], modulus)
            image_order = modulus // divisor
            multiplier = pow(pivot[column] // divisor, -1, image_order)
            pivot = tuple(value * multiplier % target
                          for value, target in zip(pivot, moduli))
            reduced = []
            for row in active:
                coefficient = row[column] // divisor
                value = tuple((a - coefficient * b) % target
                              for a, b, target in zip(row, pivot, moduli))
                if any(value):
                    reduced.append(value)
            carry = tuple(value * image_order % target
                          for value, target in zip(pivot, moduli))
            if any(carry):
                reduced.append(carry)
            active = list(dict.fromkeys(reduced))
            cardinality *= image_order
            pivots.append(image_order)
        primary[prime] = {"order": cardinality, "pivot_orders": tuple(pivots)}
    return prod(record["order"] for record in primary.values()), primary


def _family(algorithm, inventory):
    return (algorithm.is_kernel,
            tuple(sorted({inventory.blocks[index].kind for index in algorithm.support})))


def _key(algorithm):
    return (algorithm.htm_length, algorithm.qtm_length, len(algorithm.support),
            algorithm.expression.render())


def _round_robin(algorithms, inventory):
    families = {}
    for algorithm in algorithms:
        families.setdefault(_family(algorithm, inventory), []).append(algorithm)
    for choices in families.values():
        choices.sort(key=_key)
    for batch in zip_longest(*(families[key] for key in sorted(families))):
        yield from (algorithm for algorithm in batch if algorithm is not None)


def _basis(algorithms, inventory):
    kernels = [algorithm for algorithm in algorithms if algorithm.is_kernel]
    orders = tuple(block.orientation_order for block in inventory.blocks)
    vectors = {algorithm.permutation: algorithm.block_action.phases for algorithm in kernels}
    span, primary = _coordinate_span(vectors.values(), orders)

    def basis_key(algorithm):
        affected_primes = {prime for index in algorithm.support
                           for prime in _prime_parts(orders[index])}
        return (len(affected_primes) > 1, len(algorithm.support) > 2, *_key(algorithm))

    selected, selected_vectors, current = [], [], 1
    for algorithm in sorted(kernels, key=basis_key):
        vector = vectors[algorithm.permutation]
        enlarged, _ = _coordinate_span((*selected_vectors, vector), orders)
        if enlarged > current:
            selected.append(algorithm)
            selected_vectors.append(vector)
            current = enlarged
        if current == span:
            break
    # Greedy additions can become redundant in cyclic groups of mixed order.
    # Preserve the shorter preferred words while removing dispensable ones.
    for index in reversed(range(len(selected))):
        remaining = selected_vectors[:index] + selected_vectors[index+1:]
        if _coordinate_span(remaining, orders)[0] == span:
            selected.pop(index)
            selected_vectors.pop(index)
    independent = prod(_permutation_order(a.permutation) for a in selected) == span
    return tuple(selected), span, primary, independent


def _permutation_order(permutation):
    from .loop_algorithms import _order
    return _order(permutation)


def _plain_expression(expression, generators, direct_words, direct_effects, rotation=""):
    """Translate transfers into the same original-loop alphabet when possible."""
    if expression.kind == "turns":
        return _plain_expression(expression.children[0], generators, direct_words,
                                 direct_effects, rotation)
    if expression.kind == "rotated":
        combined = normalize_rotation(rotation + " " + expression.rotation)
        return _plain_expression(expression.children[0], generators, direct_words,
                                 direct_effects, combined)
    if expression.kind == "loop":
        if not rotation:
            return expression
        generator = generators[expression.generator_id]
        word = rotate_moves(generator.turn_sequence, rotation)
        if word in direct_words:
            return direct_words[word]
        effect = rotate_permutation(generator.permutation, rotation)
        return direct_effects.get(effect)
    children = tuple(_plain_expression(child, generators, direct_words, direct_effects, rotation)
                     for child in expression.children)
    if any(child is None for child in children):
        return None
    return LoopExpression(expression.kind, children, expression.exponent)


@dataclass(frozen=True)
class SymbolicAlgorithmDictionary:
    """Immutable bounded repertoire with original witnesses and exact span."""

    loops: object = field(repr=False, compare=False)
    algorithms: tuple
    orientation_basis: tuple
    _metadata_json: str = field(repr=False, compare=False)
    _validated: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "algorithms", tuple(self.algorithms))
        object.__setattr__(self, "orientation_basis", tuple(self.orientation_basis))

    @property
    def generators(self):
        return self.loops.generators

    @property
    def inventory(self):
        return self.loops.block_inventory

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    def validate(self, inventory=None, generators=None):
        """Replay every word and verify retained span without external tools."""
        inventory = self.inventory if inventory is None else inventory
        generators = self.generators if generators is None else tuple(generators)
        if inventory.root_shape != self.inventory.root_shape:
            raise ValueError("dictionary refers to a different root shape")
        signature_cache = {id(self.generators): (self.generators, self.loops.witness_signature)}

        def signatures(records):
            key = id(records)
            if key not in signature_cache:
                signature_cache[key] = (records, tuple(
                    (g.id, g.permutation, g.moves, g.qtm_length) for g in records))
            return signature_cache[key][1]

        signature = signatures(generators)
        if signature != self.loops.witness_signature:
            raise ValueError("dictionary refers to a different original-loop alphabet")
        if self._validated:
            return self
        metadata = self.metadata
        initial = State(inventory.root_shape)
        if len({g.id for g in generators}) != len(generators):
            raise ValueError("dictionary has duplicate original loop IDs")
        self.loops.validate_witnesses()
        by_id = {}
        for algorithm in self.algorithms:
            if algorithm.id in by_id or algorithm.permutation == _IDENTITY:
                raise ValueError("dictionary has duplicate IDs or an identity algorithm")
            by_id[algorithm.id] = algorithm

            def original(node):
                return node.kind in _ORIGINAL_KINDS and all(original(child) for child in node.children)

            if not original(algorithm.expression):
                raise ValueError("dictionary expression requires an unsupported leaf or transfer")
            if (algorithm._inventory.root_shape != inventory.root_shape or
                    signatures(algorithm._generators) != signatures(generators) or
                    algorithm.expression.evaluate(generators) != algorithm.permutation):
                raise ValueError("dictionary expression disagrees with its original-loop action")
            if algorithm.htm_length > metadata["settings"]["max_htm_length"]:
                raise ValueError("dictionary algorithm exceeds its physical length bound")
            moves = algorithm.expression.expanded_moves(
                self.loops, max_expanded_moves=max(1, metadata["settings"]["max_expanded_moves"]))
            for word in (moves, algorithm.turn_sequence):
                replay = initial.apply(word)
                if replay.shape != inventory.root_shape or replay.sticker_permutation != algorithm.permutation:
                    raise ValueError("dictionary algorithm fails physical replay")
        if any(by_id.get(algorithm.id) != algorithm or not algorithm.is_kernel
               for algorithm in self.orientation_basis):
            raise ValueError("dictionary orientation basis is outside its retained kernel algorithms")
        orders = tuple(block.orientation_order for block in inventory.blocks)
        actual = _coordinate_span((a.block_action.phases for a in self.algorithms if a.is_kernel), orders)[0]
        basis_span = _coordinate_span((a.block_action.phases for a in self.orientation_basis), orders)[0]
        if actual != basis_span or actual != metadata["orientation_span_order"]:
            raise ValueError("dictionary orientation span metadata or selected basis is invalid")
        independent = prod(_permutation_order(a.permutation) for a in self.orientation_basis) == basis_span
        if metadata["orientation_basis_independent"] != independent:
            raise ValueError("dictionary orientation independence claim is inconsistent")
        if metadata["orientation_complete"] != (actual == metadata["orientation_target_order"]):
            raise ValueError("dictionary orientation completeness claim is inconsistent")
        if all(isinstance(algorithm, LoopAlgorithm)
               for algorithm in (*self.algorithms, *self.orientation_basis)):
            object.__setattr__(self, "_validated", True)
        return self

    def to_dict(self):
        return {"format": "bce-v2-symbolic-algorithm-dictionary", "version": 1,
                "root_shape": self.inventory.root_shape.labels,
                "root_vertex": self.loops.root_vertex, "metadata": self.metadata,
                "generators": [g.to_dict() for g in self.generators],
                "algorithms": [a.to_dict() for a in self.algorithms],
                "orientation_basis_ids": [a.id for a in self.orientation_basis]}

    def to_json(self, path=None):
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path):
        self.to_json(path)
        return self.to_dict()

    @classmethod
    def from_dict(cls, record, initial=None):
        """Reload saved original-loop expressions and verify them without GAP.

        An optional native loop library/analysis supplies the current shape
        graph metadata. Its leaf IDs must match when it is used by a planner;
        otherwise the saved library keeps its portable original IDs. Exact
        target orders are saved GAP results and are checked against certified
        method orders when this dictionary is consumed by a symbolic method.
        """
        from .human_witnesses import _StoredLoopOwner
        from .isotropy import LoopGenerators
        from .symbolic_chains import _expression_from_dict

        if (not isinstance(record, dict) or
                record.get("format") != "bce-v2-symbolic-algorithm-dictionary" or
                record.get("version") != 1):
            raise ValueError("unsupported symbolic algorithm dictionary")
        try:
            shape = Shape(record["root_shape"])
            native = _reference(shape if initial is None else initial)
            if native.root_shape != shape:
                raise ValueError("saved dictionary and supplied reference shapes differ")
            inventory = native.block_inventory
            owner = _StoredLoopOwner(inventory, record["root_vertex"], record["generators"], native)
            loops = LoopGenerators(owner)
            builder = AlgorithmLibrary(loops, (), (), ())
            settings = record["metadata"]["settings"]
            algorithms = []
            for item in record["algorithms"]:
                expression = _expression_from_dict(item["expression"])
                algorithm = builder.build_algorithm(expression,
                                                      max_expanded_moves=settings["max_expanded_moves"],
                                                      max_htm_length=settings["max_htm_length"])
                if (list(algorithm.permutation) != item["permutation"] or
                        algorithm.turn_sequence != item["turn_sequence"] or algorithm.id != item["id"]):
                    raise ValueError("saved dictionary algorithm disagrees with its original-loop expression")
                algorithms.append(algorithm)
            by_id = {a.id: a for a in algorithms}
            basis = tuple(by_id[identifier] for identifier in record["orientation_basis_ids"])
            result = cls(loops, tuple(algorithms), basis,
                         json.dumps(record["metadata"], sort_keys=True, separators=(",", ":")))
            return result.validate()
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError("malformed symbolic algorithm dictionary") from error


def discover_symbolic_dictionary(initial, *, max_candidates=12000, rounds=4, max_seed_loops=32,
                                 max_algorithms=1024, max_setup_depth=2,
                                 max_setup_words=256, max_conjugates=12000,
                                 max_htm_length=80, max_expanded_moves=400,
                                 max_original_loops=32,
                                 gap_executable="gap", timeout=None):
    """Discover a bounded reusable repertoire and measure exact orientation span.

    Setup words concatenate legal reference loops. A fused block's orientation
    modulus comes from its actual rigid footprint. GAP computes only exact
    input/placement orders; it never enumerates group elements or supplies
    long generic kernel words to this dictionary.
    """
    settings = dict(max_candidates=max_candidates, rounds=rounds, max_seed_loops=max_seed_loops,
                    max_algorithms=max_algorithms,
                    max_setup_depth=max_setup_depth, max_setup_words=max_setup_words,
                    max_conjugates=max_conjugates, max_htm_length=max_htm_length,
                    max_expanded_moves=max_expanded_moves, max_original_loops=max_original_loops)
    for name, value in settings.items():
        _integer(value, name, 1 if name in ("max_algorithms", "max_htm_length", "max_expanded_moves") else 0)
    loops = _reference(initial)
    inventory, generators = loops.block_inventory, loops.generators
    analysis = initial if isinstance(initial, IsotropyAnalysis) else loops.analyze(
        gap_executable=gap_executable, timeout=timeout)
    report_progress("dictionary", status="started", original_loops=len(generators),
                    algebra_generators=len(analysis.generators))
    projections = [tuple(g.block_action.destinations) + tuple(range(len(inventory.blocks), 48))
                   for g in analysis.generators]
    quotient = analyze_generators(projections, gap_executable=gap_executable,
                                  timeout=timeout, prune=False).group_order
    if analysis.group_order % quotient:
        raise ValueError("reference group and exact placement quotient orders are inconsistent")
    target = analysis.group_order // quotient
    builder = AlgorithmLibrary(loops, (), (), ())
    records = {g.id: g for g in generators}
    direct_words, direct_effects = {}, {}
    pool, counts = {}, Counter()

    def keep(algorithm):
        previous = pool.get(algorithm.permutation)
        if previous is None or _key(algorithm) < _key(previous):
            pool[algorithm.permutation] = algorithm
        return algorithm

    def build(expression):
        try:
            algorithm = builder.build_algorithm(expression, max_expanded_moves=max_expanded_moves,
                                                max_htm_length=max_htm_length)
        except _ExpansionLimit:
            counts["expansion_pruned"] += 1
            return None
        except _LengthLimit:
            counts["length_pruned"] += 1
            return None
        if algorithm.permutation == _IDENTITY:
            counts["identity_proposals"] += 1
            return None
        return keep(algorithm)

    originals = []
    # Keep the certified algebra basis and a bounded physical quality pool.
    # Native records are QTM ordered: a small window avoids expanding every
    # witness merely to rank its simplified HTM length.
    physical = list(analysis.generators)
    physical_ids = {generator.id for generator in physical}
    window = generators[:max_original_loops * 4]
    short = sorted((generator for generator in window if generator.id not in physical_ids),
                   key=lambda g: (g.htm_length, g.qtm_length, g.id))[:max_original_loops]
    physical.extend(short)
    original_budget = (3 * len(physical) if not max_candidates else
                       min(max_candidates, max(3 * len(analysis.generators),
                                               max_candidates // (rounds + 1))))
    for exponent in (1, -1, 2):
        for generator in physical:
            if counts["original_proposals_examined"] >= original_budget:
                break
            checkpoint("dictionary", work=1)
            counts["original_proposals_examined"] += 1
            expression = LoopExpression.power(LoopExpression.loop(generator.id), exponent)
            algorithm = build(expression)
            if algorithm is not None:
                originals.append(algorithm)
                direct_words.setdefault(algorithm.turn_sequence, expression)
                direct_effects.setdefault(algorithm.permutation, expression)

    mining = None
    mining_budget = max(0, max_candidates - counts["original_proposals_examined"])
    if mining_budget and max_seed_loops and physical:
        mining = discover_loop_algorithms(
            loops, max_seed_loops=min(max_seed_loops, mining_budget), rounds=rounds,
            max_candidates=mining_budget, max_algorithms=max(512, max_algorithms),
            max_htm_length=max_htm_length, max_expanded_moves=max_expanded_moves,
            seed_generator_ids=tuple(generator.id for generator in physical))
        for algorithm in mining.algorithms:
            expression = _plain_expression(algorithm.expression, records, direct_words, direct_effects)
            if expression is None:
                counts["untranslated_transfers"] += 1
            else:
                build(expression)

    # The setup alphabet uses cheap physical originals, with their inverses
    # and half turns. Its traversal is bounded independently of the group.
    alphabet = sorted({a.permutation: a for a in originals}.values(), key=_key)[:32]
    setups, queue, setup_effects = [], deque([(LoopExpression.sequence(), _IDENTITY, 0)]), {_IDENTITY}
    while queue and len(setups) < max_setup_words:
        checkpoint("dictionary", work=1)
        expression, effect, depth = queue.popleft()
        setups.append(expression)
        if depth >= max_setup_depth:
            continue
        for algorithm in alphabet:
            image = _then(effect, algorithm.permutation)
            if image in setup_effects:
                continue
            setup_effects.add(image)
            queue.append((LoopExpression.sequence(expression, algorithm.expression), image, depth+1))

    # A few support-diverse bodies from every family spread the setup budget
    # across corner/edge cycles, orientations and early mixed actions.
    families, bodies = {}, []
    body_candidates = sorted(pool.values(), key=lambda a: (
        len(a.support) > (2 if a.is_kernel else 3), *_key(a)))
    for algorithm in body_candidates:
        family = _family(algorithm, inventory)
        signatures = families.setdefault(family, set())
        if len(signatures) >= 2 or algorithm.support in signatures:
            continue
        signatures.add(algorithm.support)
        bodies.append(algorithm)
        if len(bodies) >= 48:
            break
    if setups and max_conjugates:
        for setup in setups:
            for body in bodies:
                for exponent in (1, -1):
                    if counts["conjugates_examined"] >= max_conjugates:
                        break
                    counts["conjugates_examined"] += 1
                    checkpoint("dictionary", work=1)
                    build(LoopExpression.conjugate(setup, LoopExpression.power(body.expression, exponent)))
                if counts["conjugates_examined"] >= max_conjugates:
                    break
            if counts["conjugates_examined"] >= max_conjugates:
                break

    basis, _, _, _ = _basis(pool.values(), inventory)
    selected, effects = [], set()
    # Keep the certified sparse span and cheap original early/parity actions.
    for algorithm in (*basis, *sorted(originals, key=_key)[:32],
                      *_round_robin(pool.values(), inventory)):
        if algorithm.permutation in effects:
            continue
        if len(selected) >= max_algorithms:
            break
        effects.add(algorithm.permutation)
        selected.append(algorithm)
    selected.sort(key=lambda a: (_family(a, inventory), *_key(a)))
    basis, span, primary, independent = _basis(selected, inventory)
    if target % span:
        raise ValueError("discovered pure orientations exceed the exact reference-footprint kernel")
    family_counts = Counter(str(_family(a, inventory)) for a in selected)
    metadata = {"settings": settings, "exhaustive_word_search": False,
                "group_order": analysis.group_order, "quotient_order": quotient,
                "orientation_target_order": target, "orientation_span_order": span,
                "orientation_complete": span == target,
                "orientation_missing_index": target // span,
                "orientation_span_method": "exact prime-power coordinate elimination",
                "orientation_primary_spans": {str(p): {"order": value["order"],
                                                        "pivot_orders": list(value["pivot_orders"])}
                                               for p, value in primary.items()},
                "orientation_basis_independent": independent,
                "orientation_basis_count": len(basis),
                "orientation_basis_total_htm": sum(a.htm_length for a in basis),
                "orientation_basis_max_htm": max((a.htm_length for a in basis), default=0),
                "original_loop_count": len(generators), "retained_original_effects": len(
                    {a.permutation for a in originals if a.permutation in effects}),
                "physical_original_loop_count": len(physical),
                "redundant_original_loop_count": len(short),
                "original_admission_limit_reached": len(physical) < len(generators),
                "candidate_count": counts["original_proposals_examined"] +
                                   (0 if mining is None else mining.examined_count),
                "algorithm_count": len(selected), "available_effect_count": len(pool),
                "algorithm_limit_reached": len(pool) > len(selected),
                "setup_word_count": len(setups), "setup_limit_reached": bool(queue),
                "conjugate_limit_reached": bool(max_conjugates and
                                                counts["conjugates_examined"] >= max_conjugates),
                "families": dict(sorted(family_counts.items())), "work": dict(counts),
                "mining": None if mining is None else mining.metadata,
                "target_source": "exact reference group and placement quotient orders",
                "coverage_scope": "orientation span; retained native loops are separate witnesses"}
    result = SymbolicAlgorithmDictionary(loops, tuple(selected), basis,
                                        json.dumps(metadata, sort_keys=True, separators=(",", ":"))).validate()
    report_progress("dictionary", status="completed", candidates=metadata["candidate_count"],
                    algorithms=len(selected), orientation_span_order=span,
                    orientation_target_order=target)
    return result
