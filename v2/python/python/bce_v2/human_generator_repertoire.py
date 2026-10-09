"""Stage guides whose entire learned vocabulary is the reduced loop basis."""

from dataclasses import replace
import json

from .human_algorithms import _stage_groups
from .human_chains import plan_human_stages
from .human_methods import HumanMethod, _compile_plan, _require, _then, _validate_method
from .human_repertoire import (
    HumanMacroRecipe, HumanRepertoire, HumanRepertoireCase, HumanRepertoireMacro,
    _baseline_metrics, _compile_policies, _same_json, _validate_repertoire,
)
from .isotropy import isotropy_loops
from .loop_algorithms import LoopAlgorithm, LoopExpression, _loops_from_records


_IDENTITY = tuple(range(48))
_METADATA_FIELDS = {
    "basis", "construction", "generator_ids", "coverage", "human_reviewed",
    "exhaustive_repertoire_search", "baseline_metrics", "selected_metrics",
}


def generator_human_repertoire(initial, *, strategy="fully_solve_each_block", features=None,
                               max_group_elements=None, gap_executable="gap", timeout=None,
                               root=None):
    """Build the usual stage guide, learning only reduced isotropy generators.

    Accepts the shape/analysis/prepared-plan inputs of ``plan_human_stages``.
    A complete ``HumanMethod`` instead retains its stage chain, rebuilding its
    corrections in the reduced generator alphabet. Its original loop library
    is reduced again using GAP; it need not already use the reduced basis.

    Each case gives one complete sequence of generator powers. Intermediate
    generators may move earlier solved blocks; the complete correction restores
    them. Finite BFS witnesses provide coverage, without algorithm discovery,
    vocabulary optimization, or a shortest physical-word claim. A group-element
    limit stops construction with an error rather than an incomplete guide.
    Saved repertoires can be loaded and applied without GAP.
    """
    supplied_method = initial if isinstance(initial, HumanMethod) else None
    if supplied_method is not None:
        if supplied_method.status != "completed":
            raise ValueError("generator repertoire requires a complete method")
        if features is not None or strategy != "fully_solve_each_block":
            raise ValueError("a supplied method retains its own stage chain")
        if root is not None:
            if isinstance(root, bool) or not isinstance(root, int):
                raise TypeError("root must be an integer vertex ID")
            if root != supplied_method.root_vertex:
                raise ValueError("root differs from the supplied method reference")
        loops = (_loops_from_records(supplied_method.generators) if supplied_method.generators
                 else isotropy_loops(supplied_method.reference_shape))
        supplied_method = _validate_method(supplied_method, complete_loops=loops)
        initial = loops
        strategy = "manual"
        features = tuple(stage.feature for stage in supplied_method.stages)
    plan = plan_human_stages(initial, strategy=strategy, features=features,
                             max_group_elements=max_group_elements, gap_executable=gap_executable,
                             timeout=timeout, root=None if supplied_method is not None else root)
    if plan.status != "completed":
        raise ValueError(f"generator repertoire requires a complete plan: {plan.reason}")
    baseline = _compile_plan(plan)
    if supplied_method is not None:
        baseline = replace(baseline, strategy=supplied_method.strategy,
                           skipped_features=supplied_method.skipped_features,
                           root_vertex=supplied_method.root_vertex)

    lengths = tuple((generator.id, generator.htm_length) for generator in baseline.generators)
    macros = tuple(HumanRepertoireMacro(f"M{index}", LoopAlgorithm(
        f"M{index}", LoopExpression.loop(generator.id), generator.permutation,
        generator.turn_sequence, baseline.inventory, lengths, baseline.generators))
        for index, generator in enumerate(baseline.generators, 1))
    identifiers = {generator.id: macro.id for generator, macro in zip(baseline.generators, macros)}
    algorithms = {algorithm.id: algorithm for algorithm in baseline.algorithms}
    policies = []
    for stage in baseline.stages:
        cases = []
        for case in stage.cases:
            algorithm = algorithms.get(case.algorithm_id)
            if algorithm is None:
                recipe, instruction, rank = HumanMacroRecipe.sequence(), None, 0
            else:
                steps = algorithm.expression.loop_steps(max_syllables=max(1, len(plan.group)))
                factors = tuple(HumanMacroRecipe.power(HumanMacroRecipe.macro(identifiers[identifier]), exponent)
                                for identifier, exponent in steps)
                recipe = factors[0] if len(factors) == 1 else HumanMacroRecipe.sequence(*factors)
                instruction, rank = recipe, algorithm.htm_length
            cases.append(HumanRepertoireCase(case.observation, recipe, instruction,
                                            stage.solved_observation, rank))
        policies.append(tuple(cases))

    # Reuse the existing projection, recognition-family compiler and complete
    # proof. Fixed-basis construction does not generate or search templates.
    actions = {permutation: baseline.inventory.action(permutation)
               for permutation in sorted(baseline._permutations)}
    groups = _stage_groups(baseline, actions)
    method, compiled_macros, stages, metrics = _compile_policies(
        baseline, macros, tuple(policies), actions, groups, plan.analysis.loops)
    metadata = {
        "basis": "reduced_generators", "construction": "original_loop_bfs",
        "generator_ids": [generator.id for generator in method.generators],
        "coverage": "certified", "human_reviewed": False, "exhaustive_repertoire_search": False,
        "baseline_metrics": _baseline_metrics(baseline, actions), "selected_metrics": metrics,
    }
    repertoire = HumanRepertoire(baseline, method, compiled_macros, stages,
                                 json.dumps(metadata, sort_keys=True))
    return _validate_repertoire(repertoire, complete_loops=plan.analysis.loops)


def _validate_generator_metadata(repertoire, actual, before):
    """Reprove a saved fixed vocabulary without GAP or an optimizer history."""
    metadata = repertoire.metadata
    _require(set(metadata) == _METADATA_FIELDS and metadata["basis"] == "reduced_generators" and
             metadata["construction"] == "original_loop_bfs" and metadata["coverage"] == "certified" and
             metadata["human_reviewed"] is False and metadata["exhaustive_repertoire_search"] is False,
             "invalid reduced-generator repertoire metadata")
    _require(_same_json(metadata["selected_metrics"], actual) and
             _same_json(metadata["baseline_metrics"], before),
             "saved generator repertoire metrics disagree with verified policies")
    method, baseline = repertoire.method, repertoire.baseline
    _require(method.generators == baseline.generators and
             _same_json(metadata["generator_ids"], [generator.id for generator in method.generators]),
             "saved reduced generator IDs disagree with the witness basis")
    _require(len(repertoire.macros) == len(method.generators), "generator repertoire changes its vocabulary")
    for index, (macro, generator) in enumerate(zip(repertoire.macros, method.generators), 1):
        _require(macro.id == f"M{index}" and macro.algorithm.expression == LoopExpression.loop(generator.id) and
                 macro.algorithm.turn_sequence == generator.turn_sequence and
                 macro.algorithm.permutation == generator.permutation,
                 "generator repertoire contains a synthesized master definition")
        # Each generator in the reduced basis must be indispensable. Closure
        # of the complete basis is already proved by the method validator.
        alphabet = tuple(other.permutation for other in method.generators if other.id != generator.id)
        generated, queue = {_IDENTITY}, [_IDENTITY]
        for permutation in queue:
            for other in alphabet:
                successor = _then(permutation, other)
                if successor not in generated:
                    generated.add(successor)
                    queue.append(successor)
        _require(generator.permutation not in generated, "saved generator basis is not reduced")
    algorithms = {algorithm.id: algorithm for algorithm in baseline.algorithms}
    projected = {algorithm.id: algorithm for algorithm in method.algorithms}
    for original, stage, policy in zip(baseline.stages, method.stages, repertoire.stages):
        for source_case, case, compiled in zip(original.cases, policy.cases, stage.cases):
            expected = case.instruction if case.instruction is not None else HumanMacroRecipe.sequence()
            _require(case.recipe == expected,
                     "generator case must give its complete correction")
            _require(case.next_observation == stage.solved_observation,
                     "generator correction does not finish its stage")
            if source_case.algorithm_id is not None:
                source, target = algorithms[source_case.algorithm_id], projected[compiled.algorithm_id]
                _require((source.permutation, source.turn_sequence) == (target.permutation, target.turn_sequence) and
                         case.rank == source.htm_length,
                         "generator correction disagrees with its BFS baseline")


__all__ = ["generator_human_repertoire"]
