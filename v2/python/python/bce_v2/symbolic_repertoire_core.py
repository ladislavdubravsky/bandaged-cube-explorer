"""Shared recipe policies on certified feature orbits, without group closure.

A stage certificate identifies the exact stabilizer K inside H. Its case
representative t identifies the entire fiber Kt. An instruction in H has one
observation transition on that fiber, so checking t proves every state in it.
The saved methods carry the subgroup proofs needed to verify this offline.
"""

from dataclasses import replace
import json

from . import State
from .human_methods import _observe, _require, _then, _validate_method
from .isotropy import isotropy_loops
from .preparation import reference_loops


_IDENTITY = tuple(range(48))


def symbolic_policy_metrics(method):
    """Use exact additive costs; never iterate the certified reference group."""
    from .symbolic_human_algorithms import _additive_metrics

    measured = _additive_metrics(method)
    result = {key: value for key, value in measured.items()
              if key not in ("exact", "scope", "boundary_cancellation_included", "additive_costs")}
    leaves = {identifier for algorithm in method.algorithms for identifier in algorithm.base_ids}
    result["original_leaf_htm"] = sum(generator.htm_length for generator in method.generators
                                      if generator.id in leaves)
    return result


def compile_symbolic_policies(method, definitions, policies, *, loops=None):
    """Project complete named recipes into an already certified stage chain."""
    from .human_repertoire import (
        HumanRepertoireStage, _build_algorithm, _repertoire_metrics, _rules,
    )
    from .human_repertoire_io import _macro_id

    _require(method.backend == "symbolic" and method.status == "completed",
             "symbolic policies require a complete symbolic method")
    definitions = tuple(definitions)
    for macro in definitions:
        _macro_id(macro.id)
    policies = tuple(tuple(cases) for cases in policies)
    _require(len(policies) == len(method.stages), "missing symbolic policy stages")
    used = {identifier for cases in policies for case in cases
            for recipe in (case.recipe, case.instruction) if recipe is not None
            for identifier in recipe.macro_ids}
    macros = tuple(macro for macro in definitions if macro.id in used)
    _require({macro.id for macro in macros} == used and len(macros) == len(used),
             "symbolic recipe refers to an unknown or duplicate master")
    stages, policies_out, algorithms = [], [], []
    for stage, certified, cases in zip(method.stages, method._symbolic_chain.stages, policies):
        _require(tuple(case.observation for case in cases) == stage.observations,
                 "symbolic policy cases omit or reorder observations")
        compiled = []
        for original, case in zip(stage.cases, cases):
            identifier = None
            if case.instruction is not None:
                identifier = f"A{len(algorithms) + 1}"
                algorithms.append(_build_algorithm(case.recipe, macros, method, identifier))
            compiled.append(replace(original, algorithm_id=identifier))
        stages.append(replace(stage, cases=tuple(compiled)))
        policies_out.append(HumanRepertoireStage(
            stage.number, cases,
            _rules(stage.number, cases, stage, macros, {}, (method, certified.group_before))))
    loops = loops or reference_loops(method)
    projected = _validate_method(replace(method, algorithms=tuple(algorithms), stages=tuple(stages)),
                                 complete_loops=loops)
    policies_out = tuple(policies_out)
    metrics = _repertoire_metrics(projected, macros, policies_out, {})
    return projected, macros, policies_out, metrics


def build_symbolic_repertoire(method, definitions, recipes, *, baseline=None, metadata=None):
    """Compile direct case recipes while preserving their physical corrections.

    ``recipes`` follows the exact stage/case order of ``method`` and may contain
    either complete HumanRepertoireCase policies or direct HumanMacroRecipes.
    Omitted metadata is an internal construction result: its witnesses are
    checked here, and the search wrapper supplies measured selection metadata
    before returning or serializing its final portable repertoire.
    """
    from .human_repertoire import HumanMacroRecipe, HumanRepertoire, HumanRepertoireCase

    recipes = tuple(tuple(cases) for cases in recipes)
    _require(len(recipes) == len(method.stages), "missing symbolic recipe stages")
    policies = []
    for stage, cases in zip(method.stages, recipes):
        _require(len(cases) == stage.case_count, "missing symbolic case recipes")
        converted = []
        for observation, recipe in zip(stage.observations, cases):
            if isinstance(recipe, HumanRepertoireCase):
                converted.append(recipe)
                continue
            _require(isinstance(recipe, HumanMacroRecipe), "invalid symbolic case recipe")
            solved = observation == stage.solved_observation
            converted.append(HumanRepertoireCase(
                observation, recipe, None if solved else recipe,
                stage.solved_observation, 0 if solved else 1))
        policies.append(tuple(converted))
    loops = reference_loops(method)
    projected, macros, stages, _ = compile_symbolic_policies(
        method, definitions, policies, loops=loops)
    result = HumanRepertoire(baseline or method, projected, macros, stages,
                             json.dumps(metadata or {}, sort_keys=True, allow_nan=False))
    return validate_symbolic_repertoire(result, complete_loops=loops,
                                       validate_metadata=metadata is not None)


def validate_symbolic_repertoire(repertoire, *, complete_loops=None, validate_metadata=True):
    """Reprove masters, whole-fiber transitions and finite progress offline."""
    from .human_repertoire import (
        HumanMacroRecipe, _baseline_metrics, _build_algorithm, _macro_map,
        _repertoire_metrics, _rules, _validate_metadata,
    )
    from .human_repertoire_io import _macro_id

    _require(repertoire.baseline.backend == repertoire.method.backend == "symbolic",
             "repertoire baseline and projection use different backends")
    loops = complete_loops or reference_loops(repertoire.method)
    baseline = _validate_method(repertoire.baseline, complete_loops=loops)
    method = _validate_method(repertoire.method, complete_loops=loops)
    _require(baseline.status == method.status == "completed" and
             baseline.reference_shape == method.reference_shape and
             baseline.root_vertex == method.root_vertex and
             baseline.group_order == method.group_order and
             (baseline._permutations is method._permutations or
              (all(generator.permutation in method._permutations for generator in baseline.generators) and
               all(generator.permutation in baseline._permutations for generator in method.generators))),
             "repertoire baseline and projection have different references or groups")
    if repertoire.metadata.get("basis") != "templates":
        _require(tuple((stage.feature, stage.observations) for stage in baseline.stages) ==
                 tuple((stage.feature, stage.observations) for stage in method.stages),
                 "repertoire changes the declared stage chain")
    macros = _macro_map(repertoire.macros)
    _require(len(macros) == len(repertoire.macros), "duplicate master IDs")
    initial = State(method.reference_shape)
    built = {}

    def algorithm(recipe):
        if recipe not in built:
            built[recipe] = _build_algorithm(recipe, macros, method, "recipe")
        return built[recipe]

    for macro in repertoire.macros:
        record = macro.algorithm
        _macro_id(macro.id)
        _require(macro.id == record.id and record.permutation != _IDENTITY and
                 record.permutation in method._permutations,
                 "invalid master definition")
        checked = algorithm(HumanMacroRecipe.macro(macro.id))
        replay = initial.apply(record.turn_sequence)
        _require(checked.permutation == record.permutation and
                 checked.turn_sequence == record.turn_sequence and
                 replay.shape == method.reference_shape and replay.sticker_permutation == record.permutation,
                 "master physical word disagrees with its original witness")
    _require(len(repertoire.stages) == len(method.stages), "missing repertoire stages")
    compiled = {record.id: record for record in method.algorithms}
    used = set()
    for policy, stage, certified in zip(repertoire.stages, method.stages, method._symbolic_chain.stages):
        _require(policy.number == stage.number and
                 tuple(case.observation for case in policy.cases) == stage.observations,
                 "invalid rule stage cases")
        cases = {case.observation: case for case in policy.cases}
        for original, case in zip(stage.cases, policy.cases):
            _require(type(case.rank) is int and case.rank >= 0,
                     "rank must be a nonnegative integer")
            if case.observation == stage.solved_observation:
                _require(case.rank == 0 and case.instruction is None and
                         case.recipe.kind == "sequence" and not case.recipe.children and
                         case.next_observation == case.observation,
                         "solved observation must skip without a recipe")
                continue
            _require(case.instruction is not None and case.next_observation in cases,
                     "unsolved case has no recognition instruction")
            _require(type(cases[case.next_observation].rank) is int and
                     0 <= cases[case.next_observation].rank < case.rank,
                     "recognition instruction does not decrease rank")
            full, instruction = algorithm(case.recipe), algorithm(case.instruction)
            _require(instruction.permutation in certified.group_before and
                     full.permutation in certified.group_before,
                     "recipe fails whole-instruction endpoint preservation")
            next_action = method.inventory.action(_then(original.representative, instruction.permutation))
            _require(_observe(next_action, stage.block_index, stage.feature.kind) == case.next_observation and
                     _then(original.representative, full.permutation) in certified.group_after,
                     "recipe transition or correction fails its whole case fiber")
            projected = compiled[original.algorithm_id]
            _require((projected.permutation, projected.turn_sequence) ==
                     (full.permutation, full.turn_sequence),
                     "repertoire recipe disagrees with compiled method")
            path, observation = [], case.observation
            while observation != stage.solved_observation:
                entry = cases[observation]
                _require(entry.instruction is not None and entry.next_observation in cases and
                         type(entry.rank) is int and type(cases[entry.next_observation].rank) is int and
                         0 <= cases[entry.next_observation].rank < entry.rank,
                         "displayed recognition path does not decrease rank")
                path.append(entry.instruction)
                observation = entry.next_observation
            replayed = algorithm(HumanMacroRecipe.sequence(*path))
            _require((replayed.permutation, replayed.turn_sequence) ==
                     (full.permutation, full.turn_sequence),
                     "displayed recognition path disagrees with full case recipe")
            used.update(case.recipe.macro_ids)
            used.update(case.instruction.macro_ids)
        expected = _rules(stage.number, policy.cases, stage, repertoire.macros, {},
                          (method, certified.group_before))
        _require(policy.rules == expected, "recognition families omit, overlap or misdescribe cases")
    _require(used == set(macros), "repertoire contains hidden or unused master definitions")
    if validate_metadata:
        actual = _repertoire_metrics(method, repertoire.macros, repertoire.stages, {})
        before = _baseline_metrics(baseline, {})
        if repertoire.metadata.get("basis") == "templates":
            from .symbolic_template_repertoire import _validate_symbolic_template_metadata
            _validate_symbolic_template_metadata(repertoire, actual, before)
        else:
            _validate_metadata(repertoire.metadata, actual, before)
    return replace(repertoire, baseline=baseline, method=method)
