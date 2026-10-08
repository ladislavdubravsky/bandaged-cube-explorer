"""Bounded comparisons of physical and structured witnessed loop solutions.

The complete GAP solver remains the membership oracle and fallback. Searches
operate on exact sticker actions, never on unchecked move substitutions.
"""

from dataclasses import dataclass
import heapq
import itertools
import json
from pathlib import Path

from ._moves import _simplified_moves
from .gap_backend import GapError, GapTimeoutError
from .loop_solver import _solve_options


def _inverse(permutation):
    result = [0] * len(permutation)
    for source, destination in enumerate(permutation):
        result[destination] = source
    return tuple(result)


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be a nonnegative integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


@dataclass(frozen=True)
class AlgorithmSolution:
    """One replay-checked answer, retaining the loop construction tree.

    expression describes the loop stage. solution includes shape_solution.
    The structural score is a description heuristic, not a memorability proof.
    """

    status: str
    solution: str | None
    shape_solution: str | None
    structured_expression: object
    algorithms: tuple
    base_algorithms: tuple
    metric: str
    structure_score: tuple
    source: str
    stop_reason: str | None = None

    @property
    def expression(self):
        return self.structured_expression.render()

    @property
    def structured_turn_sequence(self):
        """The loop stage in move notation, preserving powers and brackets."""
        return self.structured_expression.render_moves(self.base_algorithms)

    @property
    def algorithm_count(self):
        """Visible definitions to remember, counting a leaf and inverse once."""
        return len(self.structured_expression.memory_keys)

    @property
    def original_loop_count(self):
        """Original graph witnesses, including hidden literal-leaf provenance."""
        return len(self.base_algorithms)

    @property
    def htm_length(self):
        return None if self.solution is None else len(self.solution.split())

    @property
    def qtm_length(self):
        if self.solution is None:
            return None
        return sum(2 if move.endswith("2") else 1 for move in self.solution.split())

    @property
    def distance(self):
        return self.htm_length if self.metric == "HTM" else self.qtm_length

    @property
    def optimal(self):
        return False

    def to_dict(self):
        return {"status": self.status, "solution": self.solution,
                "shape_solution": self.shape_solution, "expression": self.expression,
                "structured_turn_sequence": self.structured_turn_sequence,
                "structured_expression": self.structured_expression.to_dict(),
                "algorithms": [a.to_dict() for a in self.algorithms],
                "base_algorithms": [a.to_dict() for a in self.base_algorithms],
                "algorithm_count": self.algorithm_count,
                "original_loop_count": self.original_loop_count, "metric": self.metric,
                "htm_length": self.htm_length, "qtm_length": self.qtm_length,
                "structure_score": list(self.structure_score), "source": self.source,
                "optimal": False, "stop_reason": self.stop_reason}


@dataclass(frozen=True)
class LoopSolutionOptions:
    """Best actual lengths and best descriptions among the candidates found.

    search_complete only concerns the bounded macro searches, not shortest
    physical solutions or a minimum human repertoire. Exact reachability comes
    from baseline, independently of discovery and search limits.
    """

    shortest_found: AlgorithmSolution
    most_structured: AlgorithmSolution
    baseline: object
    searched_states: int
    search_complete: bool
    stop_reason: str | None
    max_states: int
    max_depth: int
    candidate_stop_reasons: tuple[str, ...] = ()
    discovery_metadata: tuple = ()

    @property
    def library_metadata(self):
        """Discovery limits and observed counts, copied for safe inspection."""
        return dict(self.discovery_metadata)

    def to_dict(self):
        return {"format": "bce-v2-loop-solution-options", "version": 1,
                "shortest_found": self.shortest_found.to_dict(),
                "most_structured": self.most_structured.to_dict(),
                "baseline": self.baseline.to_dict(),
                "searched_states": self.searched_states,
                "search_complete": self.search_complete, "stop_reason": self.stop_reason,
                "max_states": self.max_states, "max_depth": self.max_depth,
                "candidate_stop_reasons": list(self.candidate_stop_reasons),
                "library_metadata": self.library_metadata,
                "optimal": False}

    def to_json(self, path=None):
        value = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).write_text(value, encoding="utf-8")
        return value

    def save(self, path):
        self.to_json(path)
        return self.to_dict()


def _search(target, algorithms, *, structured, metric, max_states, max_depth, generators):
    """Bounded best-first word search; preserve depth and repertoire in labels.

    Physical priorities use additive macro costs, while returned answers are
    compared after actual move cancellation. This is deliberately not a claim
    of globally shortest turns. Structured priorities account for base reuse.
    """
    from .loop_algorithms import LoopExpression

    identity = tuple(range(48))
    if target == identity:
        return [()], 0, True, None
    if not max_states or not max_depth:
        return [], 0, False, "state_limit" if not max_states else "depth_limit"
    edges = []
    for algorithm in algorithms:
        cost = algorithm.htm_length if metric == "HTM" else algorithm.qtm_length
        memory = frozenset(algorithm.expression.memory_keys)
        edges.append((algorithm.permutation, algorithm.expression, algorithm,
                      memory, cost))
        inverse = _inverse(algorithm.permutation)
        if inverse != algorithm.permutation:
            edges.append((inverse, LoopExpression.power(algorithm.expression, -1), algorithm,
                          memory, cost))
    counter = itertools.count()
    initial_priority = (0, 0, 0) if structured else 0
    support_sizes = {algorithm.id: len(algorithm.support) for algorithm in algorithms}
    queue = [(initial_priority, next(counter), identity, (), frozenset(), 0)]
    # A shallow arrival must survive a cheaper deep arrival under a depth cap.
    best = {(identity, 0, frozenset()): initial_priority}
    found, reached_depth, stopped = [], False, None
    while queue:
        priority, _, permutation, path, bases, cost = heapq.heappop(queue)
        label = (permutation, len(path), bases if structured else frozenset())
        if best.get(label) != priority:
            continue
        if len(path) >= max_depth:
            reached_depth = True
            continue
        for effect, expression, algorithm, edge_bases, edge_cost in edges:
            result = tuple(effect[p] for p in permutation)
            next_path = path + ((expression, algorithm),)
            used = bases | edge_bases
            total = cost + edge_cost
            if result == target:
                found.append(next_path)
                # Goal witnesses need not be expanded further; the complete
                # solver and separate objectives already provide alternatives.
                continue
            if structured:
                # Priority is only a search heuristic. Final choices use the
                # expression model's common structural score.
                tree = LoopExpression.sequence(*(entry[0] for entry in next_path))
                value = (max(support_sizes[entry[1].id] for entry in next_path),
                         tree.structure_cost(generators), total)
            else:
                value = total
            next_label = (result, len(next_path), used if structured else frozenset())
            previous = best.get(next_label)
            if previous is not None and previous <= value:
                continue
            if previous is None and len(best) >= max_states:
                stopped = "state_limit"
                break
            best[next_label] = value
            heapq.heappush(queue, (value, next(counter), result, next_path, used, total))
        if stopped:
            break
    if stopped is None and reached_depth:
        stopped = "depth_limit"
    return found, len(best), stopped is None, stopped


def solve_loop_options(solver, state, *, library=None, metric="HTM", max_states=2000,
                       max_depth=4, timeout=None):
    """Compare a complete solution with bounded short/structured macro words.

    max_states bounds stored search labels PER objective. max_depth bounds macro
    applications. Single-algorithm answers and their inverses are always checked
    before search, including when max_states is zero. Library discovery has its
    own explicit limits. No limit is interpreted as proof of unreachability.
    """
    from .loop_algorithms import (
        AlgorithmLibrary, LoopExpression, _ExpansionLimit, discover_loop_algorithms,
    )

    metric = _solve_options(metric, None)
    max_states = _limit(max_states, "max_states")
    max_depth = _limit(max_depth, "max_depth")
    if library is None:
        library = discover_loop_algorithms(solver.analysis)
    if not isinstance(library, AlgorithmLibrary):
        raise TypeError("library must be an AlgorithmLibrary")
    if library.loops.root_shape != solver.specification:
        raise ValueError("algorithm library reference specification differs from this solver")
    # IDs are graph-local: identical shapes alone do not certify witnesses from
    # another extraction/root. Check every leaf the library might use.
    originals = {g.id: g for g in solver.analysis.loops.generators}
    for generator in library.loops.generators:
        other = originals.get(generator.id)
        if other is None or other.permutation != generator.permutation or other.moves != generator.moves:
            raise ValueError("algorithm library original loop witnesses differ from this solver")
    baseline = solver.solve(state, metric=metric, timeout=timeout)
    expression = LoopExpression.sequence(*(
        LoopExpression.power(LoopExpression.loop(step.generator_id), step.exponent)
        for step in baseline.steps))
    if baseline.status != "solved":
        option = AlgorithmSolution(baseline.status, None, baseline.shape_solution,
                                   expression, (), (), metric, (), "baseline", baseline.stop_reason)
        return LoopSolutionOptions(option, option, baseline, 0, False, baseline.stop_reason,
                                   max_states, max_depth,
                                   discovery_metadata=tuple(library.metadata.items()))

    restoration = baseline.shape_solution
    restored = state.apply(restoration)
    target = _inverse(restored.sticker_permutation)
    answers, reasons = [], []

    def retain(tree, source, algorithms=(), expansion_budget=100_000):
        try:
            algorithm = library.build_algorithm(tree, max_expanded_moves=expansion_budget)
        except _ExpansionLimit:
            if source == "baseline":
                raise
            reasons.append("expression_limit")
            return
        if algorithm.permutation != target:
            raise GapError("algorithm expression disagrees with the exact solution target")
        solution = _simplified_moves(itertools.chain(restoration.split(), algorithm.moves.split()))
        if not state.apply(solution).is_solved:
            raise GapError("discovered algorithm solution failed legal colored replay")
        bases = tuple(originals[i] for i in sorted(algorithm.base_ids))
        if not algorithms:
            algorithms = (algorithm,) if algorithm.base_ids else ()
        answers.append(AlgorithmSolution("solved", solution, restoration, tree,
                                         tuple(dict((a.id, a) for a in algorithms).values()),
                                         bases, metric, algorithm.structure_score, source))

    # An already verified baseline must survive the discovery builder's default
    # expansion cap, even for a large ordinary-cube word.
    retain(expression, "baseline", expansion_budget=max(
        100_000, baseline.required_expanded_moves or 0))
    # Check all retained alternatives, not merely the representatives favored
    # by one objective. Inverses share the same memorized base algorithms.
    for algorithm in library.algorithms:
        if algorithm.permutation == target:
            retain(algorithm.expression, "discovered", (algorithm,))
        if _inverse(algorithm.permutation) == target:
            retain(LoopExpression.power(algorithm.expression, -1), "discovered", (algorithm,))
    searched, complete = 0, True
    shortest_by_effect = {}
    for algorithm in library.algorithms:
        previous = shortest_by_effect.get(algorithm.permutation)
        key = lambda a: (a.htm_length, a.qtm_length, a.id) if metric == "HTM" else (
            a.qtm_length, a.htm_length, a.id)
        if previous is None or key(algorithm) < key(previous):
            shortest_by_effect[algorithm.permutation] = algorithm
    short_candidates = tuple(sorted(shortest_by_effect.values(), key=key)) if shortest_by_effect else ()
    for structured, candidates in ((False, short_candidates), (True, library.structured)):
        paths, count, finished, reason = _search(
            target, candidates, structured=structured, metric=metric,
            max_states=max_states, max_depth=max_depth, generators=originals)
        searched += count
        complete &= finished
        if reason:
            reasons.append(reason)
        # Many words can describe the same goal. Expansion/replay is confined
        # to the best candidates under the two actual output objectives.
        proposed = []
        for path in paths:
            tree = LoopExpression.sequence(*(entry[0] for entry in path))
            try:
                algorithm = library.build_algorithm(tree)
            except _ExpansionLimit:
                reasons.append("expression_limit")
                continue
            moves = _simplified_moves(itertools.chain(restoration.split(), algorithm.moves.split()))
            length = len(moves.split()) if metric == "HTM" else sum(
                2 if m.endswith("2") else 1 for m in moves.split())
            proposed.append((length, algorithm.structure_score, tree, path))
        if proposed:
            selected = [min(proposed, key=lambda p: (p[0], p[1])),
                        min(proposed, key=lambda p: (p[1], p[0]))]
            for _, _, tree, path in selected:
                retain(tree, "structured_search" if structured else "short_search",
                       tuple(entry[1] for entry in path))
        # Feed a bounded, stable richer library into the general factorizer as
        # well. Appending the original complete reduced generators certifies
        # that selecting easy macros cannot sacrifice reachability. This also
        # supplies answers beyond the bounded search's word depth.
        if target != tuple(range(48)) and candidates:
            from .gap_backend import factor_permutation

            selected = list(candidates[:24])
            effects = {a.permutation for a in selected}
            for generator in solver.generators:
                if generator.permutation not in effects:
                    selected.append(library.build_algorithm(
                        LoopExpression.loop(generator.id),
                        max_expanded_moves=max(100_000, generator.qtm_length)))
                    effects.add(generator.permutation)
            try:
                factorization = factor_permutation(
                    [a.permutation for a in selected], target,
                    gap_executable=solver._gap_executable,
                    timeout=solver._timeout if timeout is None else timeout)
            except GapTimeoutError:
                # Optional improvements cannot erase the verified baseline.
                reasons.append("factorization_timeout")
                continue
            if not factorization.reachable or factorization.group_order != solver.group_order:
                raise GapError("enriched algorithm library disagrees with complete group membership")
            tree = LoopExpression.sequence(*(
                LoopExpression.power(selected[i].expression, exponent)
                for i, exponent in factorization.syllables))
            retain(tree, "structured_factorization" if structured else "short_factorization",
                   tuple(selected[i] for i, _ in factorization.syllables))
    shortest = min(answers, key=lambda a: (a.distance, a.structure_score, a.expression))
    structured = min(answers, key=lambda a: (a.structure_score, a.distance, a.expression))
    reason = ("state_limit" if "state_limit" in reasons else
              "depth_limit" if "depth_limit" in reasons else
              reasons[0] if reasons else None)
    return LoopSolutionOptions(shortest, structured, baseline, searched, complete, reason,
                               max_states, max_depth, tuple(dict.fromkeys(reasons)),
                               tuple(library.metadata.items()))
