"""Declared, witnessed algorithm bodies admitted before method selection.

A setup is permission to conjugate a body, not permission to execute the
setup as a standalone correction. Standalone adjustments are declared
separately. Complete recipes are built before any stage-preservation test.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cached_property
from itertools import product
import json
from types import MappingProxyType

from ._moves import _simplified_moves
from .human_methods import _expression_bound
from .loop_algorithms import (AlgorithmLibrary, LoopAlgorithm, LoopExpression,
                              _loops_from_records, _then)
from .loop_rotations import (normalize_rotation, rotate_moves, rotate_permutation,
                             _CANONICAL_WORDS)


def _identifier(value, name):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be nonempty")


@dataclass(frozen=True)
class AlgorithmPaletteBody:
    """One taught body with a stable ID and explicit inverse permission.

    Repetition uses the same taught ID. When allowed, an inverse call also
    uses that ID; its sign is recorded in the recipe rather than adding a body.
    """

    id: str
    algorithm: LoopAlgorithm
    allow_inverse: bool = True

    def __post_init__(self):
        _identifier(self.id, "body ID")
        if not isinstance(self.algorithm, LoopAlgorithm):
            raise TypeError("body algorithm must be a witnessed LoopAlgorithm")
        if type(self.allow_inverse) is not bool:
            raise TypeError("allow_inverse must be a boolean")


@dataclass(frozen=True)
class AlgorithmPaletteSetup:
    """A named witnessed setup or explicitly available adjustment."""

    id: str
    algorithm: LoopAlgorithm

    def __post_init__(self):
        _identifier(self.id, "setup/adjustment ID")
        if not isinstance(self.algorithm, LoopAlgorithm):
            raise TypeError("setup/adjustment must be a witnessed LoopAlgorithm")


@dataclass(frozen=True)
class AlgorithmPaletteRegrip:
    """A physically certified use of a declared body in another cube grip.

    The executable face word has its own original-loop witness. Its teaching
    dependency remains ``body_id``; a regrip never grants an inverse call.
    """

    body_id: str
    rotation: str
    algorithm: LoopAlgorithm

    def __post_init__(self):
        _identifier(self.body_id, "regrip body ID")
        rotation = normalize_rotation(self.rotation)
        if not rotation:
            raise ValueError("a regrip must use a nonidentity rotation")
        object.__setattr__(self, "rotation", rotation)
        if not isinstance(self.algorithm, LoopAlgorithm):
            raise TypeError("regrip algorithm must be a witnessed LoopAlgorithm")


def _signatures(generators):
    return tuple((g.id, tuple(g.permutation), g.turn_sequence) for g in generators)


@dataclass(frozen=True)
class AlgorithmPalette:
    """A finite execution alphabet supplied before planning and factorization.

    ``recipes`` contains witnessed LoopAlgorithms for every permitted body
    sign, both without a setup and conjugated by each declared setup, plus
    the explicit standalone adjustments. No symmetry or inverse permission
    is inferred. The palette supplies useful actions, never a coverage claim.
    ``recipe_body_ids`` tracks taught IDs separately from physical recipes.
    """

    bodies: tuple[AlgorithmPaletteBody, ...]
    setups: tuple[AlgorithmPaletteSetup, ...] = ()
    adjustments: tuple[AlgorithmPaletteSetup, ...] = ()
    max_derived_power: int = 1
    max_derived_composition_length: int = 1
    max_derived_recipes: int = 0
    regrips: tuple[AlgorithmPaletteRegrip, ...] = ()

    def __post_init__(self):
        for name, cls in (("bodies", AlgorithmPaletteBody),
                          ("setups", AlgorithmPaletteSetup),
                          ("adjustments", AlgorithmPaletteSetup)):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, cls) for value in values):
                raise TypeError(f"{name} must contain {cls.__name__} instances")
            if len({value.id for value in values}) != len(values):
                raise ValueError(f"{name} IDs must be unique")
            object.__setattr__(self, name, values)
        regrips = tuple(self.regrips)
        if any(not isinstance(value, AlgorithmPaletteRegrip) for value in regrips):
            raise TypeError("regrips must contain AlgorithmPaletteRegrip instances")
        if len({(value.body_id, value.rotation) for value in regrips}) != len(regrips):
            raise ValueError("regrip body/rotation pairs must be unique")
        if any(value.body_id not in {body.id for body in self.bodies} for value in regrips):
            raise ValueError("regrips must refer to a declared body ID")
        object.__setattr__(self, "regrips", regrips)
        for name in ("max_derived_power", "max_derived_composition_length", "max_derived_recipes"):
            value = getattr(self, name)
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < (0 if name == "max_derived_recipes" else 1):
                raise ValueError(f"{name} is below its minimum")
        if self.max_derived_composition_length > 2:
            raise ValueError("derived compositions are bounded to two admitted operations")
        self.validate()

    @property
    def derivation_settings(self):
        """Portable bounds for endpoint operations, without new declarations."""
        return {name: getattr(self, name) for name in
                ("max_derived_power", "max_derived_composition_length", "max_derived_recipes")}

    def with_derived_actions(self, *, max_power=4, max_composition_length=2,
                            max_derived_recipes=256):
        """Profile bounded complete powers and compositions before choosing goals.

        Every derived operation is an ordered word over already admitted
        recipes. In particular it never grants an unavailable inverse or a
        standalone setup, and its teaching dependencies remain original IDs.
        """
        return replace(self, max_derived_power=max_power,
                       max_derived_composition_length=max_composition_length,
                       max_derived_recipes=max_derived_recipes)

    def with_rotated_bodies(self, initial=None, *, rotations=None,
                            max_proof_moves=1_000_000):
        """Admit legal, root-closing rotated calls with no new taught bodies.

        By default all 24 cube grips are considered. Exact bandage symmetry
        is sufficient but unnecessary: each transferred word is replayed on
        the reference shape and certified in its original-loop alphabet.
        Identical physical words for one body retain one deterministic grip.
        Native graph paths are needed only while creating these witnesses;
        the resulting declarations validate and execute offline.
        """
        from . import BlockedMoveError, State

        if type(max_proof_moves) is not int:
            raise TypeError("max_proof_moves must be an integer")
        if max_proof_moves < 0:
            raise ValueError("max_proof_moves must be nonnegative")
        if isinstance(rotations, str):
            raise TypeError("rotations must be a sequence of rotation words")
        rotations = tuple(dict.fromkeys(normalize_rotation(word) for word in
                          (_CANONICAL_WORDS.values() if rotations is None else rotations)))
        if not self.bodies:
            return self
        loops = _loops_from_records(self.generators if initial is None else initial)
        if (loops.root_shape != self.reference_shape or
                _signatures(loops.generators) != _signatures(self.generators)):
            raise ValueError("regrip witnesses require the palette's original-loop alphabet")
        builder = AlgorithmLibrary(loops, (), (), ())
        initial_state = State(self.reference_shape)
        regrips = list(self.regrips)
        existing = {(value.body_id, value.rotation) for value in regrips}
        seen = {(body.id, body.algorithm.turn_sequence) for body in self.bodies}
        seen.update((value.body_id, value.algorithm.turn_sequence) for value in regrips)
        for body in self.bodies:
            for rotation in rotations:
                if not rotation or (body.id, rotation) in existing:
                    continue
                word = rotate_moves(body.algorithm.turn_sequence, rotation)
                if (body.id, word) in seen:
                    continue
                try:
                    replay = initial_state.apply(word)
                except BlockedMoveError:
                    continue
                if replay.shape != self.reference_shape:
                    continue
                expression = loops.certified_root_turns(word, max_proof_moves=max_proof_moves)
                algorithm = replace(builder.build_algorithm(expression,
                    max_expanded_moves=max(1, len(word.split()))),
                    id="regrip:" + json.dumps([body.id, rotation], separators=(",", ":")))
                regrips.append(AlgorithmPaletteRegrip(body.id, rotation, algorithm))
                seen.add((body.id, word))
        return replace(self, regrips=tuple(regrips))

    @classmethod
    def from_algorithms(cls, bodies, *, setups=(), adjustments=(), allow_inverse=True):
        """Use supplied algorithm IDs as stable names in each declaration."""
        if type(allow_inverse) is not bool:
            raise TypeError("allow_inverse must be a boolean")
        bodies, setups, adjustments = tuple(bodies), tuple(setups), tuple(adjustments)
        if any(not isinstance(a, LoopAlgorithm) for a in (*bodies, *setups, *adjustments)):
            raise TypeError("palette algorithms must be witnessed LoopAlgorithm instances")
        return cls(tuple(AlgorithmPaletteBody(a.id, a, allow_inverse) for a in bodies),
                   tuple(AlgorithmPaletteSetup(a.id, a) for a in setups),
                   tuple(AlgorithmPaletteSetup(a.id, a) for a in adjustments))

    @property
    def _declared_algorithms(self):
        return tuple(value.algorithm for value in
                     (*self.bodies, *self.setups, *self.adjustments, *self.regrips))

    @property
    def reference_shape(self):
        algorithms = self._declared_algorithms
        return algorithms[0]._inventory.root_shape if algorithms else None

    @property
    def generators(self):
        algorithms = self._declared_algorithms
        return algorithms[0]._generators if algorithms else ()

    def validate(self, *, inventory=None, generators=None, group=None):
        """Check root, original witnesses and legal physical words offline."""
        from . import State

        algorithms = self._declared_algorithms
        if not algorithms:
            return self
        root = self.reference_shape
        expected = self.generators if generators is None else tuple(generators)
        if inventory is not None and inventory.root_shape != root:
            raise ValueError("palette refers to a different reference shape")
        if _signatures(expected) != _signatures(self.generators):
            raise ValueError("palette refers to a different original-loop alphabet")
        bodies = {body.id: body.algorithm for body in self.bodies}
        for regrip in self.regrips:
            body = bodies[regrip.body_id]
            if regrip.algorithm.turn_sequence != rotate_moves(body.turn_sequence, regrip.rotation):
                raise ValueError("regrip physical body differs from its declared rotated body")
            if regrip.algorithm.permutation != rotate_permutation(body.permutation, regrip.rotation):
                raise ValueError("regrip action differs from its declared rotated body")
        loops = _loops_from_records(self.generators)
        builder = AlgorithmLibrary(loops, (), (), ())
        records, initial = {g.id: g for g in expected}, State(root)
        for algorithm in algorithms:
            if (algorithm._inventory.root_shape != root or
                    _signatures(algorithm._generators) != _signatures(expected)):
                raise ValueError("palette algorithms must share a reference shape and original-loop alphabet")
            bound = max(1, _expression_bound(algorithm.expression, records))
            rebuilt = builder.build_algorithm(algorithm.expression, max_expanded_moves=bound)
            if rebuilt.permutation != algorithm.permutation:
                raise ValueError("palette expression disagrees with its original-loop action")
            if rebuilt.turn_sequence != algorithm.turn_sequence:
                raise ValueError("palette physical body differs from its witnessed expression word")
            replay = initial.apply(algorithm.turn_sequence)
            if replay.shape != root or tuple(replay.sticker_permutation) != algorithm.permutation:
                raise ValueError("palette algorithm fails legal physical replay")
            if group is not None and algorithm.permutation not in group:
                raise ValueError("palette algorithm leaves the certified reference group")
        return self

    @cached_property
    def _base_compiled(self):
        if not self._declared_algorithms:
            return (), ()
        loops = _loops_from_records(self.generators)
        builder = AlgorithmLibrary(loops, (), (), ())
        roots = {g.id: g for g in self.generators}
        recipes, records = [], []

        def add(kind, identifier, setup, exponent, expression, additive_htm, rotation=""):
            # IDs depend only on the declarations, not dictionary discovery,
            # effect deduplication, input order, or template canonicalization.
            identity = [kind, identifier, setup, exponent]
            if rotation:
                identity.append(rotation)
            recipe_id = "palette:" + json.dumps(identity,
                                                separators=(",", ":"))
            bound = max(1, _expression_bound(expression, roots))
            algorithm = replace(builder.build_algorithm(expression, max_expanded_moves=bound),
                                id=recipe_id)
            recipes.append(algorithm)
            records.append(dict(id=recipe_id, body_id=identifier if kind == "body" else None,
                                adjustment_id=identifier if kind == "adjustment" else None,
                                setup_id=setup, exponent=exponent,
                                rotation=rotation,
                                body_calls=1 if kind == "body" else 0,
                                setup_calls=1 if setup is not None else 0,
                                body_ids=(identifier,) if kind == "body" else (),
                                setup_ids=(setup,) if setup is not None else (),
                                adjustment_ids=(identifier,) if kind == "adjustment" else (),
                                original_recipe_ids=(recipe_id,), derived=False,
                                additive_htm=additive_htm, physical_htm=algorithm.htm_length))

        for adjustment in self.adjustments:
            add("adjustment", adjustment.id, None, 1, adjustment.algorithm.expression,
                adjustment.algorithm.htm_length)
        for body in self.bodies:
            # Keep the declared body as an expression boundary. Joining recipes
            # must not flatten its internal turns into anonymous loop leaves,
            # because later factorization needs to recognize the taught body.
            variants = (("", body.algorithm), *( (value.rotation, value.algorithm)
                        for value in self.regrips if value.body_id == body.id))
            for rotation, algorithm in variants:
                body_expression = LoopExpression.turns(algorithm.turn_sequence,
                                                       algorithm.expression)
                for exponent in (1, -1) if body.allow_inverse else (1,):
                    expression = (body_expression if exponent == 1 else
                                  LoopExpression.power(body_expression, -1))
                    add("body", body.id, None, exponent, expression, algorithm.htm_length, rotation)
                    for setup in self.setups:
                        # A setup may disrupt earlier goals temporarily. Preserve
                        # the complete setup/body/undo word for endpoint filtering.
                        add("body", body.id, setup.id, exponent,
                            LoopExpression.conjugate(setup.algorithm.expression, expression),
                            2 * setup.algorithm.htm_length + algorithm.htm_length, rotation)
        return tuple(recipes), tuple(records)

    @cached_property
    def _compiled(self):
        base, records = self._base_compiled
        if not base or not self.max_derived_recipes:
            return base, records, {"candidate_count_before_limit": 0, "candidates_bounded": False}
        from .block_actions import BlockInventory
        from .computation import checkpoint

        inventory = BlockInventory(self.reference_shape)
        indexed = {algorithm.id: (algorithm, record)
                   for algorithm, record in zip(base, records)}
        identity = tuple(range(48))

        def evidence(permutation):
            action = inventory.action(permutation)
            fixed_pose = frozenset(index for index, destination in enumerate(action.destinations)
                                   if destination == index and action.phases[index] == 0)
            fixed_placement = frozenset(index for index, destination in enumerate(action.destinations)
                                        if destination == index)
            zero_phase = frozenset(index for index, phase in enumerate(action.phases) if phase == 0)
            return fixed_pose, fixed_placement, zero_phase

        base_evidence = {algorithm.id: evidence(algorithm.permutation) for algorithm in base}
        candidates = {}
        # Equal effects with different teaching dependencies remain distinct:
        # one may reuse a previously taught body while the other would not.
        known = {(algorithm.permutation, record["body_ids"], record["setup_ids"],
                  record["adjustment_ids"]) for algorithm, record in zip(base, records)}

        def propose(path, *, power=False):
            checkpoint("palette_derived_operations")
            values = tuple(indexed[identifier] for identifier in path)
            permutation = identity
            for algorithm, _ in values:
                permutation = _then(permutation, algorithm.permutation)
            if permutation == identity:
                return
            dependencies = tuple(tuple(sorted({identifier for _, record in values
                                                for identifier in record[key]}))
                                 for key in ("body_ids", "setup_ids", "adjustment_ids"))
            key = (permutation, *dependencies)
            if key in known:
                return
            facts = evidence(permutation)
            # Powers expose periodic restoration. Other compositions are
            # useful when some endpoint fact is newly restored by the word.
            if not power and not any(fact - set.intersection(*(set(base_evidence[identifier][offset])
                                                               for identifier in path))
                                     for offset, fact in enumerate(facts)):
                return
            additive = sum(record["additive_htm"] for _, record in values)
            physical = len(_simplified_moves(tuple(move for algorithm, _ in values
                                                   for move in algorithm.turn_sequence.split())).split())
            inverse_calls = sum(record["exponent"] < 0 for _, record in values)
            choice = (physical, additive, len(path), inverse_calls, path)
            previous = candidates.get(key)
            if previous is None or choice < previous[0]:
                candidates[key] = (choice, facts, path, dependencies)

        ordered = tuple(sorted(indexed))
        for identifier in ordered:
            for exponent in range(2, self.max_derived_power + 1):
                propose((identifier,) * exponent, power=True)
        if self.max_derived_composition_length >= 2:
            for left, right in product(ordered, repeat=2):
                if left != right:
                    propose((left, right))
        choices = sorted(candidates.values(), key=lambda value:
                         (-len(value[1][0]), -len(value[1][1]), -len(value[1][2]),
                          len(value[3][0]) + len(value[3][1]) + len(value[3][2]), value[0]))
        loops = _loops_from_records(self.generators)
        builder = AlgorithmLibrary(loops, (), (), ())
        roots = {generator.id: generator for generator in self.generators}
        derived, derived_records = [], []
        for _, _, path, dependencies in choices[:self.max_derived_recipes]:
            expression = LoopExpression.sequence(*(indexed[identifier][0].expression for identifier in path))
            identifier = "palette:derived:" + json.dumps(path, separators=(",", ":"))
            algorithm = replace(builder.build_algorithm(expression, max_expanded_moves=max(
                1, _expression_bound(expression, roots))), id=identifier)
            source_records = tuple(indexed[source][1] for source in path)
            record = dict(id=identifier, body_id=None, setup_id=None, adjustment_id=None,
                          exponent=1, original_recipe_ids=path, derived=True,
                          body_ids=dependencies[0], setup_ids=dependencies[1],
                          adjustment_ids=dependencies[2],
                          body_calls=sum(source["body_calls"] for source in source_records),
                          setup_calls=sum(source["setup_calls"] for source in source_records),
                          additive_htm=sum(source["additive_htm"] for source in source_records),
                          physical_htm=algorithm.htm_length)
            derived.append(algorithm)
            derived_records.append(record)
        return ((*base, *derived), (*records, *derived_records),
                {"candidate_count_before_limit": len(choices),
                 "candidates_bounded": len(choices) > self.max_derived_recipes})

    @property
    def recipes(self):
        return self._compiled[0]

    @property
    def recipe_records(self):
        """JSON-compatible recipe declarations and body-call costs."""
        return tuple({key: list(value) if isinstance(value, tuple) else value
                      for key, value in record.items()} for record in self._compiled[1])

    @cached_property
    def recipe_body_ids(self):
        return MappingProxyType({record["id"]: record["body_ids"]
                                 for record in self._compiled[1]})

    @property
    def metadata(self):
        return {"body_ids": [body.id for body in self.bodies],
                "body_count": len(self.bodies),
                "inverse_body_ids": [body.id for body in self.bodies if body.allow_inverse],
                "setup_ids": [setup.id for setup in self.setups],
                "adjustment_ids": [adjustment.id for adjustment in self.adjustments],
                "regrip_count": len(self.regrips),
                "regrips": [{"body_id": value.body_id, "rotation": value.rotation,
                              "algorithm_id": value.algorithm.id} for value in self.regrips],
                "recipe_count": len(self.recipes), "recipes": list(self.recipe_records),
                "derived_recipe_count": len(self.recipes) - len(self._base_compiled[0]),
                "derivation_settings": self.derivation_settings,
                "derivation_diagnostics": dict(self._compiled[2]),
                "derived_operations_built_before_preservation_filter": bool(self.max_derived_recipes),
                "setup_undo_variants_built_before_preservation_filter": True,
                "coverage_claim": False}
