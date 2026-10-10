"""Witnessed feature stabilizers without enumeration of the reference group.

GAP constructs exact stabilizers and words. Portable Schreier certificates
check their orders and membership in Python; only the small feature orbits
are enumerated. Every word refers to the original physical root loops.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
from math import prod
from pathlib import Path

from . import State
from .block_actions import _CELL_POINTS
from .gap_backend import GapError, _gap_images, _run_gap, _validated_options
from .human_chains import BlockFeature, _KINDS, _STRATEGIES, _observation
from .loop_algorithms import LoopExpression
from .symbolic_groups import PermutationGroupCertificate, StabilizerLevel, StrongGenerator


_IDENTITY = tuple(range(48))
_BEGIN = "__BCE_SYMBOLIC_CHAIN_V1_BEGIN__"
_END = "__BCE_SYMBOLIC_CHAIN_V1_END__"


# Source appended to this program consists exclusively of validated integer
# lists. In particular no feature names, paths or arbitrary strings enter GAP.
_PROGRAM = r'''
SetPrintFormattingStatus("*stdout*", false);;
BCEChooseFeature := fail;;
BCENewFeatureStabilizer := fail;;
BCESymbolicChain := function(images, blockImages, points, phases, manual)
    local roots, projections, H, full, P, map, epi, wordPerms, wordValues, wordFor, certFor,
          groups, steps, skipped, choices, choice, kind, block, action,
          orbit, next, reps, p, t, current, candidates, i, order, kernel, imageCert;
    roots := List(images, PermList);
    H := GroupWithGenerators(roots, ());
    StabChain(H, rec(random := 1000));
    full := H;
    projections := List(blockImages, PermList);
    P := GroupWithGenerators(projections, ());
    StabChain(P, rec(random := 1000));
    map := GroupHomomorphismByImages(H, P, roots, projections);
    if map = fail or not IsSurjective(map) then
        Error("block projection is not a surjective homomorphism");
    fi;
    kernel := Size(H) / Size(P);
    epi := EpimorphismFromFreeGroup(H);
    if MappingGeneratorsImages(epi)[2] <> roots then
        Error("free-group map changed the original-loop order");
    fi;
    wordPerms := [()]; wordValues := [[]];
    wordFor := function(p)
        local found, word, external, result, j;
        found := Position(wordPerms, p);
        if found <> fail then return wordValues[found]; fi;
        word := PreImagesRepresentative(epi, p);
        if word = fail or Image(epi, word) <> p then
            Error("symbolic word failed verification");
        fi;
        external := ExtRepOfObj(word);
        result := [];
        for j in [1,3..Length(external)-1] do
            Add(result, [external[j]-1, external[j+1]]);
        od;
        Add(wordPerms, p); Add(wordValues, result);
        return result;
    end;
    certFor := function(G, degree, lift)
        local chain, pool, bases, level, generator, base, previous,
              levels, indices, j;
        chain := StabChain(G, rec(random := 1000));
        pool := []; bases := [];
        while IsBound(chain.orbit) do
            Add(bases, chain.orbit[1]);
            for generator in chain.generators do
                if not generator in pool then Add(pool, generator); fi;
            od;
            chain := chain.stabilizer;
        od;
        levels := []; previous := [];
        for base in bases do
            indices := Filtered([1..Length(pool)], j ->
                ForAll(previous, p -> p^pool[j] = p));
            Add(levels, [base-1, List(indices, j -> j-1)]);
            Add(previous, base);
        od;
        return [Size(G), List(GeneratorsOfGroup(G), g -> ListPerm(g,degree)-1),
                List(pool, g -> [ListPerm(g,degree)-1, wordFor(lift(g))]), levels];
    end;
    imageCert := certFor(P, Length(points), g -> PreImagesRepresentative(map,g));
    groups := [certFor(H,48,g -> g)]; steps := []; skipped := [];
    for kind in phases do
        if manual then
            choices := kind;
        else
            choices := [];
        fi;
        current := 1;
        while true do
            if manual then
                if current > Length(choices) then break; fi;
                choice := choices[current]; current := current+1;
                block := choice[2]+1;
                if choice[1] = 0 then action := OnSets; else action := OnTuples; fi;
                orbit := Orbit(H, points[block], action);
                if Length(orbit) = 1 then Add(skipped, choice); continue; fi;
            else
                if BCEChooseFeature <> fail then
                    choice := BCEChooseFeature(H, points, kind, Length(steps));
                    if choice = fail then break; fi;
                    block := choice[2]+1;
                    if choice[1] = 0 then action := OnSets; else action := OnTuples; fi;
                else
                    if kind = 0 then action := OnSets; else action := OnTuples; fi;
                    candidates := [];
                    for i in [1..Length(points)] do
                        orbit := Orbit(H, points[i], action);
                        if Length(orbit) > 1 then Add(candidates,[Length(orbit),i]); fi;
                    od;
                    if Length(candidates) = 0 then break; fi;
                    Sort(candidates); block := candidates[1][2];
                    choice := [kind, block-1];
                fi;
                orbit := Orbit(H, points[block], action);
            fi;
            next := Stabilizer(H, points[block], action);
            StabChain(next, rec(random := 1000));
            if Size(H) <> Length(orbit) * Size(next) then
                Error("feature stabilizer index failed verification");
            fi;
            reps := [];
            for p in orbit do
                t := RepresentativeAction(H, points[block], p, action);
                if t = fail or not t in H or action(points[block],t) <> p then
                    Error("feature transversal failed verification");
                fi;
                Add(reps,[ListPerm(t,48)-1,wordFor(t)]);
            od;
            Add(steps,[choice[1],choice[2],Size(H),Size(next),reps]);
            if BCENewFeatureStabilizer <> fail then
                BCENewFeatureStabilizer(H,next,points[block],action,orbit);
            fi;
            H := next; Add(groups,certFor(H,48,g -> g));
        od;
    od;
    if ErrorCount() <> 0 then QuitGap(1); fi;
    Print("__BCE_SYMBOLIC_CHAIN_V1_BEGIN__\n");
    Print("[\"",GAPInfo.Version,"\",",Size(full),",",Size(P),",",kernel,
          ",",Size(H),",",groups,",",steps,",",skipped,",",imageCert,"]\n");
    Print("__BCE_SYMBOLIC_CHAIN_V1_END__\n");
end;;
'''


def _check(condition, message):
    if not condition:
        raise GapError(message)


def _expression(syllables, generators):
    return LoopExpression.sequence(*(LoopExpression.power(
        LoopExpression.loop(generators[index].id), exponent)
        for index, exponent in syllables))


def _expression_from_dict(record):
    allowed = {"kind", "children", "exponent", "generator_id", "moves", "rotation"}
    if not isinstance(record, dict) or set(record) - allowed:
        raise ValueError("invalid symbolic loop expression")
    return LoopExpression(record["kind"],
                          tuple(_expression_from_dict(c) for c in record.get("children", ())),
                          record.get("exponent", 1), record.get("generator_id"),
                          record.get("moves"), record.get("rotation"))


def _original_loop_expression(expression):
    # Literal turns and geometric transfers need additional physical checks.
    # Chain transversals intentionally retain only original-loop operations.
    return (expression.kind in {"loop", "sequence", "power", "commutator", "conjugate"}
            and all(_original_loop_expression(c) for c in expression.children))


def _feature(blocks, kind, block):
    return BlockFeature(_KINDS[kind], blocks[block].cells)


def _fixed_features(inventory, group):
    actions = tuple(inventory.action(generator.permutation)
                    for generator in group.strong_generators)
    identity = inventory.action(_IDENTITY)
    return tuple(BlockFeature(kind, slot.cells)
                 for kind in _KINDS for block, slot in enumerate(inventory.blocks)
                 if all(_observation(action, block, kind) ==
                        _observation(identity, block, kind) for action in actions))


def _orbit(inventory, group, block, kind):
    """Only a physical feature orbit, never the subgroup's elements."""
    solved = _observation(inventory.action(_IDENTITY), block, kind)
    actions = tuple(inventory.action(generator.permutation)
                    for generator in group.strong_generators)
    found, queue = {solved}, deque([solved])
    modulus = inventory.blocks[block].orientation_order
    while queue:
        value = queue.popleft()
        for action in actions:
            destination = action.destinations[value[0]]
            image = ((destination,) if kind == "place_block" else
                     (destination, (value[1] + action.phases[value[0]]) % modulus))
            if image not in found:
                found.add(image)
                queue.append(image)
    return tuple(sorted(found))


@dataclass(frozen=True)
class SymbolicRepresentative:
    observation: tuple[int, ...]
    permutation: tuple[int, ...]
    expression: LoopExpression

    def to_dict(self):
        return {"observation": list(self.observation),
                "permutation": list(self.permutation),
                "expression": self.expression.to_dict()}


@dataclass(frozen=True)
class SymbolicStage:
    number: int
    feature: BlockFeature
    block_index: int
    block_name: str
    group_before: PermutationGroupCertificate = field(repr=False)
    group_after: PermutationGroupCertificate = field(repr=False)
    observations: tuple[tuple[int, ...], ...]
    solved_observation: tuple[int, ...]
    implied_features: tuple[BlockFeature, ...]
    representatives: tuple[SymbolicRepresentative, ...]

    @property
    def order_before(self):
        return self.group_before.order

    @property
    def order_after(self):
        return self.group_after.order

    @property
    def index(self):
        return self.order_before // self.order_after

    @property
    def case_count(self):
        return len(self.observations)

    def to_dict(self, *, include_elements=False):
        return {"number": self.number, "feature": self.feature.to_dict(),
                "block_index": self.block_index, "block_name": self.block_name,
                "order_before": str(self.order_before), "order_after": str(self.order_after),
                "index": self.index, "observations": [list(o) for o in self.observations],
                "solved_observation": list(self.solved_observation),
                "implied_features": [f.to_dict() for f in self.implied_features],
                "representatives": [r.to_dict() for r in self.representatives]}


@dataclass(frozen=True)
class SymbolicStagePlan:
    analysis: object | None
    strategy: str
    group: PermutationGroupCertificate
    stages: tuple[SymbolicStage, ...]
    initial_features: tuple[BlockFeature, ...]
    skipped_features: tuple[BlockFeature, ...]
    quotient_order: int
    kernel_order: int
    gap_version: str
    placement_group: PermutationGroupCertificate = field(repr=False)
    _inventory: object = field(repr=False, compare=False)
    _generators: tuple = field(repr=False, compare=False)
    status: str = "completed"
    reason: None = None
    max_group_elements: None = None
    block_structure: None = None

    @property
    def inventory(self):
        return self._inventory

    @property
    def group_order(self):
        return self.group.order

    @property
    def terminal_order(self):
        return self.stages[-1].order_after if self.stages else self.group.order

    @property
    def coverage_scope(self):
        return "chain_structure_only"

    @property
    def human_method_complete(self):
        return False

    def to_dict(self, *, include_elements=False, include_moves=True):
        return {"format": "bce-v2-symbolic-stage-chain", "version": 1,
                "strategy": self.strategy, "gap_version": self.gap_version,
                "group_order": str(self.group_order),
                "quotient_order": str(self.quotient_order),
                "kernel_order": str(self.kernel_order),
                "terminal_order": str(self.terminal_order),
                "placement_group": self.placement_group.to_dict(),
                "groups": [g.to_dict() for g in
                           (self.group, *(s.group_after for s in self.stages))],
                "initial_features": [f.to_dict() for f in self.initial_features],
                "skipped_features": [f.to_dict() for f in self.skipped_features],
                "stages": [s.to_dict() for s in self.stages]}

    def to_json(self, path=None, *, include_elements=False, include_moves=True):
        text = json.dumps(self.to_dict(include_elements=include_elements,
                                       include_moves=include_moves),
                          indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_elements=False, include_moves=True):
        self.to_json(path, include_elements=include_elements, include_moves=include_moves)
        return self.to_dict(include_elements=include_elements, include_moves=include_moves)

    def validate(self, inventory=None, generators=None, expected_order=None):
        """Certify root closure, each feature stabilizer and its transversal."""
        inventory = self.inventory if inventory is None else inventory
        generators = self._generators if generators is None else tuple(generators)
        roots = tuple(g.permutation for g in generators)
        _check(self.strategy in (*_STRATEGIES, "manual"), "unknown symbolic stage strategy")
        _check(isinstance(self.gap_version, str), "symbolic GAP version must be a string")
        root_state = State(inventory.root_shape)
        for generator in generators:
            replay = root_state.apply(generator.turn_sequence)
            _check(replay.shape == inventory.root_shape and
                   tuple(replay.sticker_permutation) == generator.permutation,
                   "symbolic original loop has an invalid physical witness")
        _check(self.group.root_generators == roots,
               "symbolic group certificate uses another original-loop alphabet")
        _check(all(self.group.contains(p) for p in roots),
               "symbolic root group omits an original loop")
        _check(expected_order is None or self.group_order == expected_order,
               "symbolic group order disagrees with the reference analysis")
        _check(self.quotient_order * self.kernel_order == self.group_order,
               "symbolic placement/kernel orders are inconsistent")
        projections = tuple(inventory.action(p).destinations for p in roots)
        _check(self.placement_group.degree == len(inventory.blocks) and
               self.placement_group.root_generators == projections and
               all(self.placement_group.contains(p) for p in projections) and
               self.placement_group.order == self.quotient_order,
               "symbolic placement-image certificate or quotient order is inconsistent")
        fixed = _fixed_features(inventory, self.group)
        _check(self.initial_features == fixed, "symbolic initial features are inconsistent")
        current = self.group
        identity = inventory.action(_IDENTITY)
        for number, stage in enumerate(self.stages, 1):
            _check(type(stage.number) is int and type(stage.block_index) is int and
                   all(type(value) is int for observation in
                       (stage.solved_observation, *stage.observations)
                       for value in observation) and
                   all(type(value) is int for representative in stage.representatives
                       for value in (*representative.observation, *representative.permutation)),
                   "symbolic stage coordinates must use integer scalar types")
            _check(stage.number == number and stage.group_before == current,
                   "symbolic stage order or preceding subgroup is inconsistent")
            _check(stage.group_after.root_generators == roots,
                   "symbolic stage certificate changes the original-loop alphabet")
            _check(0 <= stage.block_index < len(inventory.blocks) and
                   stage.feature.cells == inventory.blocks[stage.block_index].cells and
                   stage.block_name == inventory.blocks[stage.block_index].name,
                   "symbolic stage feature refers to another physical block")
            solved = _observation(identity, stage.block_index, stage.feature.kind)
            orbit = _orbit(inventory, current, stage.block_index, stage.feature.kind)
            _check(stage.solved_observation == solved and stage.observations == orbit and
                   len(orbit) > 1 and current.order == stage.group_after.order * len(orbit),
                   "symbolic feature orbit or stabilizer index is inconsistent")
            for generator in stage.group_after.strong_generators:
                _check(current.contains(generator.permutation),
                       "symbolic feature stabilizer is outside the preceding subgroup")
                _check(_observation(inventory.action(generator.permutation),
                                    stage.block_index, stage.feature.kind) == solved,
                       "symbolic feature stabilizer fails to fix its feature")
            _check(tuple(r.observation for r in stage.representatives) == orbit,
                   "symbolic transversal does not cover its complete feature orbit")
            for representative in stage.representatives:
                _check(_original_loop_expression(representative.expression) and
                       current.contains(representative.permutation) and
                       representative.expression.evaluate(generators) == representative.permutation,
                       "symbolic transversal has an invalid original-loop witness")
                _check(_observation(inventory.action(representative.permutation),
                                    stage.block_index, stage.feature.kind) == representative.observation,
                       "symbolic transversal has the wrong feature observation")
            after_fixed = _fixed_features(inventory, stage.group_after)
            implied = tuple(f for f in after_fixed if f not in fixed and f != stage.feature)
            _check(stage.implied_features == implied, "symbolic implied features are inconsistent")
            fixed, current = after_fixed, stage.group_after
        _check(current.order == 1 and prod(s.index for s in self.stages) == self.group_order,
               "symbolic stage chain does not terminate at faithful identity")
        _check((self.strategy == "manual" or not self.skipped_features) and
               all(feature in fixed for feature in self.skipped_features),
               "symbolic skipped features are inconsistent")
        return self


def _parse_certificate(raw, roots, *, degree=48):
    order, inputs, pool, levels = raw
    certificate = PermutationGroupCertificate(
        roots, tuple(StrongGenerator(tuple(p), tuple(tuple(s) for s in w)) for p, w in pool),
        tuple(StabilizerLevel(point, tuple(indices)) for point, indices in levels),
        input_generators=tuple(tuple(p) for p in inputs), degree=degree)
    _check(certificate.order == order, "GAP and portable subgroup orders disagree")
    return certificate


def plan_symbolic_stages(analysis, *, strategy="placement_then_orientation", features=None,
                         gap_executable="gap", timeout=None):
    """Compute exact small-feature stages and their physical transversals."""
    executable, timeout = _validated_options(gap_executable, timeout)
    if strategy not in (*_STRATEGIES, "manual"):
        raise ValueError("unknown human stage strategy")
    inventory = analysis.block_inventory
    blocks = inventory.blocks
    by_cells = {b.cells: i for i, b in enumerate(blocks)}
    if strategy == "manual":
        if features is None:
            raise ValueError("manual strategy requires features")
        features = tuple(features)
        if any(not isinstance(f, BlockFeature) for f in features):
            raise TypeError("manual features must be BlockFeature instances")
        if any(f.cells not in by_cells for f in features):
            raise ValueError("each feature must name exactly one block in the actual reference inventory")
        phases = [[[ _KINDS.index(f.kind), by_cells[f.cells]] for f in features]]
    else:
        if features is not None:
            raise ValueError("features are only accepted with strategy='manual'")
        phases = [_KINDS.index(kind) for kind in _STRATEGIES[strategy]]
    generators = tuple(analysis.loops.generators)
    roots = tuple(g.permutation for g in generators)
    points = [sorted(p+1 for cell in b.cells for p in _CELL_POINTS[cell]) for b in blocks]
    projections = [[d+1 for d in g.block_action.destinations] for g in generators]
    arguments = [_gap_images(roots), json.dumps(projections), json.dumps(points),
                 json.dumps(phases), "true" if strategy == "manual" else "false"]
    output = _run_gap(_PROGRAM + "\nBCESymbolicChain(" + ",".join(arguments) + ");;\nQUIT;\n",
                      executable, timeout, "symbolic stage planning")
    return _parse_symbolic_plan_output(output, analysis, strategy)


def _parse_symbolic_plan_output(output, analysis, strategy):
    inventory = analysis.block_inventory
    blocks = inventory.blocks
    generators = tuple(analysis.loops.generators)
    roots = tuple(g.permutation for g in generators)
    lines = output.splitlines()
    _check(lines.count(_BEGIN) == lines.count(_END) == 1,
           "GAP returned missing or duplicate symbolic-chain markers")
    start, stop = lines.index(_BEGIN), lines.index(_END)
    try:
        version, order, quotient, kernel, terminal, raw_groups, raw_stages, raw_skipped, raw_placement = json.loads(
            "".join(lines[start+1:stop]))
    except (TypeError, ValueError) as error:
        raise GapError("GAP returned a malformed symbolic-chain record") from error
    _check(order == analysis.group_order, "symbolic root group disagrees with isotropy analysis")
    if terminal != 1:
        raise ValueError(f"manual features leave a subgroup of order {terminal}; add solve_block features")
    groups = tuple(_parse_certificate(raw, roots) for raw in raw_groups)
    _check(len(groups) == len(raw_stages)+1, "GAP returned inconsistent symbolic subgroup records")
    fixed = initial = _fixed_features(inventory, groups[0])
    stages = []
    identity = inventory.action(_IDENTITY)
    for number, raw in enumerate(raw_stages, 1):
        kind, block, before_order, after_order, raw_reps = raw
        feature = _feature(blocks, kind, block)
        _check((groups[number-1].order, groups[number].order) == (before_order, after_order),
               "GAP returned inconsistent symbolic stage orders")
        reps = tuple(sorted((SymbolicRepresentative(
            _observation(inventory.action(tuple(p)), block, feature.kind), tuple(p),
            _expression(w, generators)) for p, w in raw_reps), key=lambda r: r.observation))
        after_fixed = _fixed_features(inventory, groups[number])
        implied = tuple(f for f in after_fixed if f not in fixed and f != feature)
        stages.append(SymbolicStage(number, feature, block, blocks[block].name,
                                    groups[number-1], groups[number],
                                    tuple(r.observation for r in reps),
                                    _observation(identity, block, feature.kind), implied, reps))
        fixed = after_fixed
    plan = SymbolicStagePlan(analysis, strategy, groups[0], tuple(stages), initial,
                             tuple(_feature(blocks,k,b) for k,b in raw_skipped),
                             quotient, kernel, version,
                             _parse_certificate(raw_placement,
                                                tuple(g.block_action.destinations for g in generators),
                                                degree=len(blocks)),
                             inventory, generators)
    return plan.validate(expected_order=analysis.group_order)


def symbolic_plan_from_dict(record, inventory, generators, expected_order=None):
    """Load and fully verify a portable chain without invoking GAP."""
    try:
        _check(isinstance(record, dict), "symbolic stage-chain record must be an object")
        _check(record["format"] == "bce-v2-symbolic-stage-chain" and record["version"] == 1,
               "unsupported symbolic stage-chain format")
        groups = tuple(PermutationGroupCertificate.from_dict(g) for g in record["groups"])
        rows = record["stages"]
        _check(len(groups) == len(rows)+1, "symbolic chain has inconsistent subgroup records")
        feature = lambda row: BlockFeature(row["kind"], tuple(row["reference_cells"]))
        stages = tuple(SymbolicStage(
            row["number"], feature(row["feature"]), row["block_index"], row["block_name"],
            groups[i], groups[i+1], tuple(tuple(o) for o in row["observations"]),
            tuple(row["solved_observation"]), tuple(feature(f) for f in row["implied_features"]),
            tuple(SymbolicRepresentative(tuple(r["observation"]), tuple(r["permutation"]),
                                         _expression_from_dict(r["expression"]))
                  for r in row["representatives"])) for i, row in enumerate(rows))
        plan = SymbolicStagePlan(None, record["strategy"], groups[0], stages,
                                 tuple(feature(f) for f in record["initial_features"]),
                                 tuple(feature(f) for f in record["skipped_features"]),
                                 int(record["quotient_order"]), int(record["kernel_order"]),
                                 record["gap_version"],
                                 PermutationGroupCertificate.from_dict(record["placement_group"]),
                                 inventory, tuple(generators))
        _check(int(record["group_order"]) == plan.group_order and
               int(record["terminal_order"]) == plan.terminal_order,
               "saved symbolic chain has inconsistent declared orders")
        for row, stage in zip(rows, stages):
            _check((int(row["order_before"]), int(row["order_after"]), row["index"]) ==
                   (stage.order_before, stage.order_after, stage.index),
                   "saved symbolic stage has inconsistent declared orders")
        _check(json.dumps(record, sort_keys=True) == json.dumps(plan.to_dict(), sort_keys=True),
               "saved symbolic stage chain does not use canonical fields and scalar types")
        return plan.validate(inventory, generators, expected_order)
    except (KeyError, TypeError, IndexError, ValueError) as error:
        raise GapError("invalid symbolic stage-chain record") from error
