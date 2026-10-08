"""Witnessed block-permutation quotients and abelian kernel corrections."""

from dataclasses import dataclass, field
import json
from math import lcm, prod
from pathlib import Path

from ._moves import _simplified_moves
from .gap_backend import GapError, _validated_options
from .isotropy import IsotropyAnalysis, analyze_isotropy
from .loop_solver import LoopStep, _inverse_moves


def _expression(steps, attribute="generator_id", prefix="L"):
    return " ".join(prefix + str(getattr(step, attribute)) +
                    (f"^{step.exponent}" if step.exponent != 1 else "") for step in steps)


def _word_moves(steps, generators):
    by_id = {generator.id: generator for generator in generators}
    for step in steps:
        moves = tuple(by_id[step.generator_id].moves.split())
        if step.exponent < 0:
            moves = _inverse_moves(moves)
        for _ in range(abs(step.exponent)):
            yield from moves


def _permutation_order(permutation):
    seen, order = set(), 1
    for start in range(len(permutation)):
        if start in seen:
            continue
        point, length = start, 0
        while point not in seen:
            seen.add(point)
            point, length = permutation[point], length + 1
        order = lcm(order, length)
    return order


@dataclass(frozen=True)
class KernelStep:
    """A signed power of an algorithm in the prepared kernel basis."""

    basis_id: str
    exponent: int

    def to_dict(self):
        return {"basis_id": self.basis_id, "exponent": self.exponent}


@dataclass(frozen=True)
class KernelAlgorithm:
    """An independent kernel generator with an original-loop witness.

    Kernel IDs are local to this prepared reference library. The underlying
    steps retain the original graph loop IDs and their execution order.
    """

    id: str
    order: int
    permutation: tuple[int, ...]
    steps: tuple[LoopStep, ...]
    _inventory: object = field(repr=False, compare=False)
    _generators: tuple = field(repr=False, compare=False)

    @property
    def expression(self):
        return _expression(self.steps)

    @property
    def moves(self):
        return " ".join(_word_moves(self.steps, self._generators))

    @property
    def turn_sequence(self):
        return _simplified_moves(_word_moves(self.steps, self._generators))

    @property
    def qtm_length(self):
        by_id = {generator.id: generator for generator in self._generators}
        return sum(abs(step.exponent) * by_id[step.generator_id].qtm_length for step in self.steps)

    @property
    def htm_length(self):
        return len(self.turn_sequence.split())

    @property
    def block_action(self):
        return self._inventory.action(self.permutation)

    def to_dict(self, *, include_moves=True):
        record = {"id": self.id, "order": self.order,
                  "permutation": list(self.permutation),
                  "steps": [step.to_dict() for step in self.steps],
                  "expression": self.expression, "qtm_length": self.qtm_length,
                  "block_action": self.block_action.to_dict()}
        if include_moves:
            record.update(moves=self.moves, turn_sequence=self.turn_sequence,
                          htm_length=self.htm_length)
        return record


@dataclass(frozen=True)
class BlockStructure:
    """Exact H -> P with an independent, witnessed basis of its kernel K."""

    analysis: IsotropyAnalysis
    quotient_order: int
    kernel_order: int
    basis: tuple[KernelAlgorithm, ...]
    gap_version: str

    @property
    def group_order(self):
        return self.analysis.group_order

    @property
    def inventory(self):
        return self.analysis.block_inventory

    @property
    def generators(self):
        return self.analysis.generators

    @property
    def root_shape(self):
        return self.analysis.loops.root_shape

    def to_dict(self, *, include_moves=True):
        return {"format": "bce-v2-block-structure", "version": 1,
                "model": "full-grid-27-fixed-centers", "complete": True,
                "root_shape": self.root_shape.labels,
                "root_vertex": self.analysis.loops.root_vertex,
                "group_order": str(self.group_order),
                "quotient_order": str(self.quotient_order),
                "kernel_order": str(self.kernel_order), "kernel_abelian": True,
                "gap_version": self.gap_version,
                "generator_ids": list(self.analysis.generator_ids),
                "block_inventory": self.inventory.to_dict(),
                "basis": [algorithm.to_dict(include_moves=include_moves) for algorithm in self.basis]}

    def to_json(self, path=None, *, include_moves=True):
        text = json.dumps(self.to_dict(include_moves=include_moves), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def save(self, path, *, include_moves=True):
        self.to_json(path, include_moves=include_moves)
        return self.to_dict(include_moves=include_moves)


def analyze_block_structure(initial, *, gap_executable="gap", timeout=None, root=None):
    """Prepare exact quotient/kernel groups without enumerating colored states.

    Accept the same inputs as analyze_isotropy(), or reuse an IsotropyAnalysis.
    All block maps and basis witnesses refer to that analysis's actual root.
    """
    from .block_gap import analyze_block_structure as gap_analyze

    gap_executable, timeout = _validated_options(gap_executable, timeout)
    if root is not None and (isinstance(root, bool) or not isinstance(root, int)):
        raise TypeError("root must be an integer vertex ID")

    if isinstance(initial, BlockStructure):
        if root is not None and root != initial.analysis.loops.root_vertex:
            raise ValueError("root differs from the already prepared block structure")
        return initial
    if isinstance(initial, IsotropyAnalysis):
        if root is not None and root != initial.loops.root_vertex:
            raise ValueError("root differs from the supplied isotropy analysis")
        analysis = initial
    else:
        analysis = analyze_isotropy(initial, gap_executable=gap_executable, timeout=timeout, root=root)
    generators = analysis.generators
    inventory = analysis.block_inventory
    result = gap_analyze(
        [generator.permutation for generator in generators],
        [generator.block_action.destinations for generator in generators],
        gap_executable=gap_executable, timeout=timeout,
    )
    if (result.group_order != analysis.group_order or
            result.group_order != result.quotient_order * result.kernel_order):
        raise GapError("block quotient/kernel orders disagree with the isotropy analysis")
    basis = []
    identity = tuple(range(len(inventory.blocks)))
    for index, record in enumerate(result.basis):
        steps = tuple(LoopStep(generators[i].id, exponent) for i, exponent in record.syllables)
        algorithm = KernelAlgorithm(f"K{index}", record.order, record.permutation,
                                    steps, inventory, generators)
        try:
            action = algorithm.block_action
        except ValueError as error:
            raise GapError("kernel basis has an invalid rigid block action") from error
        if action.destinations != identity or _permutation_order(record.permutation) != record.order:
            raise GapError("kernel basis does not fix footprints or has an incorrect order")
        # Verify the exact lift through original IDs without expanding turns.
        lifted = inventory.identity()
        for i, exponent in record.syllables:
            lifted = lifted.then(generators[i].block_action ** exponent)
        if lifted.permutation != record.permutation:
            raise GapError("kernel basis original-loop witness failed exact verification")
        basis.append(algorithm)
    if prod(algorithm.order for algorithm in basis) != result.kernel_order:
        raise GapError("independent kernel basis orders disagree with the kernel order")
    return BlockStructure(analysis, result.quotient_order, result.kernel_order,
                          tuple(basis), result.gap_version)


@dataclass(frozen=True)
class _BlockFactorization:
    reachable: bool
    placement_steps: tuple[LoopStep, ...] = ()
    kernel_steps: tuple[KernelStep, ...] = ()
    steps: tuple[LoopStep, ...] = ()
    stop_reason: str | None = None


def _flatten_steps(placement_steps, kernel_steps, structure):
    """Lift both stages to original loop IDs, retaining compact loop powers."""
    basis = {algorithm.id: algorithm for algorithm in structure.basis}
    orders = {generator.id: _permutation_order(generator.permutation)
              for generator in structure.generators}
    result = []

    def append(step):
        exponent = step.exponent
        if result and result[-1].generator_id == step.generator_id:
            exponent += result.pop().exponent
        exponent %= orders[step.generator_id]
        if 2 * exponent > orders[step.generator_id]:
            exponent -= orders[step.generator_id]
        if exponent:
            result.append(LoopStep(step.generator_id, exponent))

    for step in placement_steps:
        append(step)
    for step in kernel_steps:
        word = basis[step.basis_id].steps
        if step.exponent < 0:
            word = tuple(LoopStep(s.generator_id, -s.exponent) for s in reversed(word))
        for _ in range(abs(step.exponent)):
            for syllable in word:
                append(syllable)
    return tuple(result)


def _factor_block_action(structure, target, *, gap_executable, timeout):
    """Find target = placement_lift then kernel_correction in execution order."""
    from .block_gap import factor_block_permutation, factor_kernel

    inventory, generators = structure.inventory, structure.generators
    try:
        action = inventory.action(target)
    except ValueError:
        # Valid imported cube states may rotate a symmetric core-anchored
        # block in place. Such a block cannot move under any outer-face word.
        return _BlockFactorization(False, stop_reason="kernel_residual_not_in_group")
    quotient = factor_block_permutation(
        [generator.block_action.destinations for generator in generators], action.destinations,
        gap_executable=gap_executable, timeout=timeout,
    )
    if quotient.group_order != structure.quotient_order:
        raise GapError("quotient factorization order disagrees with the prepared structure")
    if not quotient.reachable:
        return _BlockFactorization(False, stop_reason="block_permutation_not_in_group")
    placement = tuple(LoopStep(generators[i].id, exponent) for i, exponent in quotient.syllables)
    lifted = inventory.identity()
    for i, exponent in quotient.syllables:
        lifted = lifted.then(generators[i].block_action ** exponent)
    if lifted.destinations != action.destinations:
        raise GapError("quotient word failed independent block-permutation verification")
    correction = lifted.inverse().then(action)
    if correction.destinations != tuple(range(len(inventory.blocks))):
        raise GapError("lifted placement did not leave a footprint-fixing residual")
    kernel = factor_kernel(
        [algorithm.permutation for algorithm in structure.basis], correction.permutation,
        gap_executable=gap_executable, timeout=timeout,
    )
    if kernel.group_order != structure.kernel_order:
        raise GapError("kernel factorization order disagrees with the prepared structure")
    if not kernel.reachable:
        return _BlockFactorization(False, placement_steps=placement,
                                   stop_reason="kernel_residual_not_in_group")
    if len(kernel.exponents) != len(structure.basis):
        raise GapError("kernel coordinate count differs from the prepared basis")
    kernel_steps = tuple(KernelStep(algorithm.id, exponent)
                         for algorithm, exponent in zip(structure.basis, kernel.exponents) if exponent)
    verified = lifted
    for algorithm, exponent in zip(structure.basis, kernel.exponents):
        verified = verified.then(algorithm.block_action ** exponent)
    if verified.permutation != action.permutation:
        raise GapError("quotient/kernel word failed independent exact-action verification")
    flattened = _flatten_steps(placement, kernel_steps, structure)
    final = inventory.identity()
    by_id = {generator.id: generator for generator in generators}
    for step in flattened:
        final = final.then(by_id[step.generator_id].block_action ** step.exponent)
    if final.permutation != action.permutation:
        raise GapError("flattened original-loop word failed exact-action verification")
    return _BlockFactorization(True, placement, kernel_steps, flattened)
