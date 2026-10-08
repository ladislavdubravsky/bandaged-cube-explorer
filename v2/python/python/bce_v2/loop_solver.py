"""Colored scramble solutions through witnessed shape loops and GAP.

Only the complete shape component is explored. A stable, reduced library of
original loops supplies the baseline. Opt-in algorithm discovery and comparison
retain richer short and structured alternatives with original witnesses.
"""

from dataclasses import dataclass
import json
from pathlib import Path

from . import Shape, State, explore
from ._moves import _simplified_moves
from .gap_backend import GapError, _validated_options
from .graph import ShapeGraph
from .isotropy import IsotropyAnalysis, LoopGenerator, LoopGenerators


def _inverse_moves(moves):
    return tuple(move if move.endswith("2") else
                 move[:-1] if move.endswith("'") else move + "'"
                 for move in reversed(moves))


def _solve_options(metric, max_expanded_moves):
    if not isinstance(metric, str):
        raise TypeError("metric must be QTM or HTM")
    metric = metric.upper()
    if metric not in ("QTM", "HTM"):
        raise ValueError("metric must be QTM or HTM")
    if max_expanded_moves is not None:
        if isinstance(max_expanded_moves, bool) or not isinstance(max_expanded_moves, int):
            raise TypeError("max_expanded_moves must be a nonnegative integer or None")
        if max_expanded_moves < 0:
            raise ValueError("max_expanded_moves must be nonnegative")
    return metric


def _factorization_option(value):
    if not isinstance(value, str):
        raise TypeError("factorization must be sticker or quotient_kernel")
    if value not in ("sticker", "quotient_kernel"):
        raise ValueError("factorization must be sticker or quotient_kernel")
    return value


@dataclass(frozen=True)
class LoopStep:
    """A signed power of one original root-loop algorithm."""

    generator_id: int
    exponent: int

    def to_dict(self):
        return {"generator_id": self.generator_id, "exponent": self.exponent}


@dataclass(frozen=True)
class LoopSolution:
    """A verified colored solution, a proof of unreachability, or an expansion cap.

    Steps apply after shape_solution. Algorithms contains just their used
    original loops, counting inverses and powers as the same base algorithm.
    required_expanded_moves counts unsimplified QTM witness turns, including
    restoration; it is None when no factorization exists. No shortest or
    minimum-repertoire guarantee is made. Quotient/kernel results additionally
    retain separate placement and kernel expressions and their witnessed
    algorithms; steps remains the flattened word in original loop IDs.
    """

    status: str
    solution: str | None
    shape_solution: str | None
    steps: tuple[LoopStep, ...]
    algorithms: tuple[LoopGenerator, ...]
    root_shape: Shape
    group_order: int
    gap_version: str
    metric: str
    stop_reason: str | None = None
    required_expanded_moves: int | None = None
    factorization: str = "sticker"
    quotient_order: int | None = None
    kernel_order: int | None = None
    placement_steps: tuple[LoopStep, ...] = ()
    kernel_steps: tuple = ()
    kernel_algorithms: tuple = ()
    placement_algorithms: tuple[LoopGenerator, ...] = ()

    @property
    def optimal(self):
        return False

    @property
    def algorithm(self):
        return "loops"

    @property
    def algorithm_count(self):
        """Distinct root-loop algorithms, excluding shape restoration turns."""
        return len(self.algorithms)

    @property
    def expression(self):
        return " ".join(f"L{step.generator_id}" +
                        (f"^{step.exponent}" if step.exponent != 1 else "")
                        for step in self.steps)

    @property
    def placement_expression(self):
        return " ".join(f"L{step.generator_id}" +
                        (f"^{step.exponent}" if step.exponent != 1 else "")
                        for step in self.placement_steps)

    @property
    def kernel_expression(self):
        return " ".join(step.basis_id +
                        (f"^{step.exponent}" if step.exponent != 1 else "")
                        for step in self.kernel_steps)

    @property
    def qtm_length(self):
        if self.solution is None:
            return None
        return sum(2 if move.endswith("2") else 1 for move in self.solution.split())

    @property
    def htm_length(self):
        return None if self.solution is None else len(self.solution.split())

    @property
    def distance(self):
        """Cost of the returned sequence in metric; not a shortest distance."""
        return self.qtm_length if self.metric == "QTM" else self.htm_length

    def to_dict(self):
        return {
            "format": "bce-v2-loop-solution", "version": 1,
            "model": "full-grid-27-fixed-centers", "notation": "Singmaster",
            "symmetry": "none", "status": self.status, "solution": self.solution,
            "metric": self.metric, "distance": self.distance, "optimal": False,
            "algorithm": self.algorithm, "preference": "few_algorithms",
            "shape_solution": self.shape_solution,
            "root_shape": self.root_shape.labels,
            "steps": [step.to_dict() for step in self.steps],
            "expression": self.expression,
            "algorithms": [algorithm.to_dict() for algorithm in self.algorithms],
            "algorithm_count": self.algorithm_count,
            "qtm_length": self.qtm_length, "htm_length": self.htm_length,
            "group_order": str(self.group_order), "gap_version": self.gap_version,
            "stop_reason": self.stop_reason,
            "required_expanded_moves": self.required_expanded_moves,
            "factorization": self.factorization,
            "quotient_order": str(self.quotient_order) if self.quotient_order is not None else None,
            "kernel_order": str(self.kernel_order) if self.kernel_order is not None else None,
            "placement_steps": [step.to_dict() for step in self.placement_steps],
            "kernel_steps": [step.to_dict() for step in self.kernel_steps],
            "placement_expression": self.placement_expression,
            "kernel_expression": self.kernel_expression,
            "kernel_algorithms": [algorithm.to_dict() for algorithm in self.kernel_algorithms],
            "placement_algorithms": [algorithm.to_dict() for algorithm in self.placement_algorithms],
        }

    def to_json(self, path=None):
        result = json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n"
        if path is not None:
            Path(path).write_text(result, encoding="utf-8")
        return result

    def save(self, path):
        self.to_json(path)
        return self.to_dict()


class LoopSolver:
    """Prepare one puzzle's complete shape graph and stable algorithm library.

    initial may be a Shape/list, State (uses its reference specification), a
    complete ShapeGraph (uses vertex zero), LoopGenerators, or IsotropyAnalysis.
    An existing loop set or analysis defines the reference as its root_shape;
    subsequent State inputs must have that same reference specification.

    Preparation computes exact group order and a reduced subset of original
    witnessed loops with GAP, unless an existing analysis is supplied. Reusing
    the solver reuses this graph and library. The default sticker strategy
    factors the full action. factorization="quotient_kernel" prepares a cached
    block quotient and witnessed abelian kernel basis, then factors placement
    and correction separately. timeout bounds each GAP call separately, and
    does not bound shape exploration. GAP failures raise GapError.
    """

    __slots__ = ("_graph", "_analysis", "_generators", "_gap_executable", "_timeout",
                 "_factorization", "_block_structure")

    def __init__(self, initial, *, gap_executable="gap", timeout=None, factorization="sticker"):
        factorization = _factorization_option(factorization)
        gap_executable, timeout = _validated_options(gap_executable, timeout)
        if isinstance(initial, IsotropyAnalysis):
            analysis = initial
            graph = explore(analysis.loops.root_shape)
        elif isinstance(initial, LoopGenerators):
            graph = explore(initial.root_shape)
            analysis = initial.analyze(gap_executable=gap_executable, timeout=timeout)
        else:
            if isinstance(initial, State):
                initial = initial.specification
            graph = initial if isinstance(initial, ShapeGraph) else explore(initial)
            analysis = graph.isotropy_loops().analyze(
                gap_executable=gap_executable, timeout=timeout)
        object.__setattr__(self, "_graph", graph)
        object.__setattr__(self, "_analysis", analysis)
        object.__setattr__(self, "_generators", analysis.generators)
        object.__setattr__(self, "_gap_executable", gap_executable)
        object.__setattr__(self, "_timeout", timeout)
        object.__setattr__(self, "_factorization", factorization)
        object.__setattr__(self, "_block_structure", None)

    def __setattr__(self, name, value):
        raise AttributeError("LoopSolver is immutable")

    def __delattr__(self, name):
        raise AttributeError("LoopSolver is immutable")

    @property
    def analysis(self):
        return self._analysis

    @property
    def specification(self):
        return self.analysis.loops.root_shape

    @property
    def generators(self):
        """The stable reduced base-algorithm library shared across scrambles."""
        return self._generators

    @property
    def group_order(self):
        return self.analysis.group_order

    @property
    def shape_count(self):
        return len(self._graph)

    @property
    def factorization(self):
        return self._factorization

    @property
    def block_structure(self):
        """Lazily prepare and reuse the exact block quotient and kernel basis."""
        return self._prepare_block_structure(self._timeout)

    def _prepare_block_structure(self, timeout):
        if self._block_structure is None:
            from .block_solver import analyze_block_structure

            structure = analyze_block_structure(self.analysis, gap_executable=self._gap_executable,
                                                timeout=timeout)
            object.__setattr__(self, "_block_structure", structure)
        return self._block_structure

    def discover_algorithms(self, **options):
        """Mine bounded short and structured alternatives from the rich loops."""
        from .loop_algorithms import discover_loop_algorithms

        return discover_loop_algorithms(self.analysis, **options)

    def solve_options(self, state, *, library=None, metric="HTM", max_states=2000,
                      max_depth=4, timeout=None):
        """Expose shortest-found and structured answers with a complete fallback.

        Discovery and macro-word searches are bounded and make no optimality or
        human-memorability guarantee. Both answers include legally replay-checked
        moves, original-loop witnesses, and preserved construction trees.
        """
        from .loop_algorithm_solver import solve_loop_options

        return solve_loop_options(self, state, library=library, metric=metric,
                                  max_states=max_states, max_depth=max_depth,
                                  timeout=timeout)

    def solve(self, state, *, metric="QTM", timeout=None, max_expanded_moves=None):
        """Solve to the reference colored state using shape restoration and loops.

        Imported states need no scramble history. Exact complete-component and
        group membership checks can prove unreachability. Otherwise steps retain
        signed powers of original loops; expansion and legal replay verify the
        final answer. Adjacent same-face turns are simplified in both metrics.

        max_expanded_moves is an optional nonnegative UNSIMPLIFIED QTM expansion
        budget, including restoration. Exceeding it returns limit_reached with
        the compact factorization retained and solution=None. It does not bound
        GAP's internal word computation. timeout overrides the prepared timeout
        when non-None; a timeout raises GapTimeoutError, never unreachability.
        """
        if not isinstance(state, State):
            raise TypeError("loop solving requires a State")
        metric = _solve_options(metric, max_expanded_moves)
        _, gap_timeout = _validated_options(
            self._gap_executable, self._timeout if timeout is None else timeout)
        if state.specification != self.specification:
            raise ValueError("state reference specification differs from this loop solver")
        gap_version = self.analysis.gap_version
        structure = None

        def result(status, *, solution=None, restoration=None, steps=(), algorithms=(),
                   stop_reason=None, required=None, placement_steps=(), kernel_steps=(),
                   kernel_algorithms=()):
            placement_ids = {step.generator_id for step in placement_steps}
            placement_algorithms = tuple(generator for generator in self.generators
                                         if generator.id in placement_ids)
            return LoopSolution(
                status=status, solution=solution, shape_solution=restoration,
                steps=steps, algorithms=algorithms, root_shape=self.specification,
                group_order=self.group_order, gap_version=gap_version,
                metric=metric, stop_reason=stop_reason, required_expanded_moves=required,
                factorization=self.factorization,
                quotient_order=structure.quotient_order if structure else None,
                kernel_order=structure.kernel_order if structure else None,
                placement_steps=placement_steps, kernel_steps=kernel_steps,
                kernel_algorithms=kernel_algorithms, placement_algorithms=placement_algorithms)

        try:
            vertex = self._graph.vertex_id(state.shape)
        except ValueError:
            return result("unreachable", stop_reason="shape_outside_component")
        # This graph may have been re-explored from a supplied nonzero-root
        # loop set. Its vertex IDs must never index that old loop set's tree.
        restoration = self._graph.shortest_path(vertex, self.specification)
        restored = state.apply(restoration)
        if restored.shape != self.specification:
            raise GapError("shape restoration did not reach the solver reference")

        placement_steps, kernel_steps, kernel_algorithms = (), (), ()
        if self.factorization == "quotient_kernel":
            structure = self._prepare_block_structure(gap_timeout)
            gap_version = structure.gap_version
        if restored.is_solved:
            steps = ()
        else:
            inverse = [0] * 48
            for source, destination in enumerate(restored.sticker_permutation):
                inverse[destination] = source
            if structure is not None:
                from .block_solver import _factor_block_action

                factored = _factor_block_action(structure, inverse,
                                               gap_executable=self._gap_executable,
                                               timeout=gap_timeout)
                if not factored.reachable:
                    return result("unreachable", restoration=restoration,
                                  stop_reason=factored.stop_reason,
                                  placement_steps=factored.placement_steps)
                steps = factored.steps
                placement_steps, kernel_steps = factored.placement_steps, factored.kernel_steps
                used_basis = {step.basis_id for step in kernel_steps}
                kernel_algorithms = tuple(algorithm for algorithm in structure.basis
                                          if algorithm.id in used_basis)
            else:
                from .gap_backend import factor_permutation

                factored = factor_permutation(
                    [generator.permutation for generator in self.generators], inverse,
                    gap_executable=self._gap_executable,
                    timeout=gap_timeout)
                gap_version = factored.gap_version
                if factored.group_order != self.group_order:
                    raise GapError("factorization group order disagrees with the prepared analysis")
                if not factored.reachable:
                    return result("unreachable", restoration=restoration,
                                  stop_reason="residual_not_in_group")
                steps = tuple(LoopStep(self.generators[index].id, exponent)
                              for index, exponent in factored.syllables)

        used = {step.generator_id for step in steps}
        algorithms = tuple(generator for generator in self.generators if generator.id in used)
        by_id = {generator.id: generator for generator in algorithms}
        required = (sum(2 if move.endswith("2") else 1 for move in restoration.split()) +
                    sum(abs(step.exponent) * by_id[step.generator_id].qtm_length
                        for step in steps))
        if max_expanded_moves is not None and required > max_expanded_moves:
            return result("limit_reached", restoration=restoration, steps=steps,
                          algorithms=algorithms, stop_reason="expansion_limit", required=required,
                          placement_steps=placement_steps, kernel_steps=kernel_steps,
                          kernel_algorithms=kernel_algorithms)

        def expanded():
            yield from restoration.split()
            for step in steps:
                moves = tuple(by_id[step.generator_id].moves.split())
                if step.exponent < 0:
                    moves = _inverse_moves(moves)
                for _ in range(abs(step.exponent)):
                    yield from moves

        solution = _simplified_moves(expanded())
        if not state.apply(solution).is_solved:
            raise GapError("expanded loop factorization failed legal colored replay")
        return result("solved", solution=solution, restoration=restoration, steps=steps,
                      algorithms=algorithms, required=required, placement_steps=placement_steps,
                      kernel_steps=kernel_steps, kernel_algorithms=kernel_algorithms)


def solve_colored_loops(state, *, solver=None, metric="QTM", gap_executable="gap",
                        timeout=None, max_expanded_moves=None, factorization=None):
    """Prepare and solve one colored scramble; reuse LoopSolver for many inputs.

    Only the shape graph is explored, never the full colored graph. The target
    is solved with the same reference specification. If solver is supplied its
    GAP executable is used; configure that executable on the prepared solver.
    Select factorization="quotient_kernel" to place blocks and then correct
    their orientations. An omitted strategy respects a supplied solver's mode.
    """
    if not isinstance(state, State):
        raise TypeError("loop solving requires a State")
    metric = _solve_options(metric, max_expanded_moves)
    if factorization is not None:
        factorization = _factorization_option(factorization)
    if solver is None:
        solver = LoopSolver(state, gap_executable=gap_executable, timeout=timeout,
                            factorization=factorization or "sticker")
    elif not isinstance(solver, LoopSolver):
        raise TypeError("solver must be a LoopSolver")
    elif gap_executable != "gap":
        raise ValueError("configure gap_executable on the prepared LoopSolver")
    elif factorization is not None and factorization != solver.factorization:
        raise ValueError("factorization differs from the prepared solver")
    return solver.solve(state, metric=metric, timeout=timeout,
                        max_expanded_moves=max_expanded_moves)
