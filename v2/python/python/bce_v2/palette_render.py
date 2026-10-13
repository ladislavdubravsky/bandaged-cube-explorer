"""Vocabulary notation and certified, finite procedural recognition rules.

The saved case policy remains the execution certificate. A procedure only
factors its exact calls: every displayed operation consumes a prefix and
leaves the saved suffix for the resulting observation. This is the same
positive-rank, re-observation design used by the older human repertoire,
with complete palette operations retained as preservation boundaries.
"""

from dataclasses import dataclass
from functools import lru_cache
from itertools import groupby


_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _letter(index):
    result = ""
    while index >= 0:
        index, remainder = divmod(index, 26)
        result = chr(ord("A") + remainder) + result
        index -= 1
    return result


def execution_vocabulary(palette, recipe_paths):
    """Return used declarations and role-specific A, B, ... display names.

    Stable execution and serialized IDs are retained. Setup and adjustment
    declarations of the same exact physical word can share a display name;
    bodies remain separate because their inverse permissions are distinct.
    """
    records = {record["id"]: record for record in palette.recipe_records}
    used = [records[identifier] for path in recipe_paths
            for identifier in expanded_recipe_path(palette, path)]
    aliases, declarations, short_words = {}, [], {}
    next_index = 0
    for kind, entries, key in (("Body", palette.bodies, "body_id"),
                               ("Setup", palette.setups, "setup_id"),
                               ("Adjustment", palette.adjustments, "adjustment_id")):
        names = {record[key] for record in used}
        for declaration in entries:
            if declaration.id not in names:
                continue
            identity = declaration.algorithm.turn_sequence, declaration.algorithm.permutation
            name = short_words.get(identity) if kind != "Body" else None
            if name is None:
                name = _letter(next_index)
                next_index += 1
            if kind != "Body":
                short_words[identity] = name
            aliases[key, declaration.id] = name
            declarations.append((kind, name, declaration))
    return tuple(declarations), aliases


def recipe_structure(palette, path, aliases):
    """Render physical call order with explicit signs, powers and setups.

    Consecutive identical declared calls and repeated ordered compositions
    are grouped. A setup recipe remains an explicitly bracketed conjugate,
    without assuming commutativity or granting an inverse-body permission
    absent from the palette.
    """
    from .human_repertoire import HumanMacroRecipe

    records = {record["id"]: record for record in palette.recipe_records}
    path = expanded_recipe_path(palette, path)
    calls = []
    for identifier, group in groupby(path):
        count = sum(1 for _ in group)
        record = records[identifier]
        key = "body_id" if record["body_id"] is not None else "adjustment_id"
        name = aliases[key, record[key]]
        exponent = record["exponent"]
        setup = record["setup_id"]
        body = HumanMacroRecipe.power(HumanMacroRecipe.macro(name), exponent)
        if setup is not None:
            call = HumanMacroRecipe.power(HumanMacroRecipe.conjugate(
                HumanMacroRecipe.macro(aliases['setup_id', setup]), body), count)
        else:
            call = HumanMacroRecipe.power(body, count)
        calls.append(call)
    # Share the repertoire's typed expression tree, while retaining palette
    # setup notation and superscripts. Repeated compositions remain ordered
    # words: this factoring never assumes that operations commute.
    factored, start = [], 0
    while start < len(calls):
        best = None
        for width in range(1, (len(calls) - start) // 2 + 1):
            block = calls[start:start + width]
            count = 1
            while calls[start + count * width:start + (count + 1) * width] == block:
                count += 1
            if count > 1 and (best is None or width * count > best[0] * best[1]):
                best = width, count
        if best is None:
            factored.append(calls[start])
            start += 1
        else:
            width, count = best
            body = calls[start] if width == 1 else HumanMacroRecipe.sequence(*calls[start:start + width])
            factored.append(HumanMacroRecipe.power(body, count))
            start += width * count
    def render(recipe):
        if recipe.kind == "macro":
            return recipe.macro_id
        if recipe.kind == "sequence":
            return " ".join(render(child) for child in recipe.children)
        if recipe.kind == "conjugate":
            setup, body = recipe.children
            return f"[{render(setup)}: {render(body)}]"
        child, = recipe.children
        body = render(child)
        if child.kind == "sequence":
            body = "(" + body + ")"
        return body + str(recipe.exponent).translate(_SUPERSCRIPT)
    return " ".join(render(call) for call in factored) or "(no moves)"


def expanded_recipe_path(palette, path):
    """Expand derived operations to the original, explicitly permitted calls."""
    records = {record["id"]: record for record in palette.recipe_records}
    result = []
    def append(identifier, parents=()):
        if identifier not in records:
            raise ValueError("unknown palette operation: " + identifier)
        original = tuple(records[identifier].get("original_recipe_ids", (identifier,)))
        if original == (identifier,):
            result.append(identifier)
            return
        if identifier in parents or not original:
            raise ValueError("invalid derived palette operation expansion")
        for child in original:
            append(child, (*parents, identifier))
    for identifier in path:
        append(identifier)
    return tuple(result)


@dataclass(frozen=True)
class PaletteProcedureRule:
    """One conjunction of visible cues and its exact permitted operation."""

    conditions: tuple[str, ...]
    recipe: tuple[str, ...]
    observations: tuple[tuple[int, ...], ...]
    next_observations: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PaletteProcedureStage:
    number: int
    solved_observation: tuple[int, ...]
    observations: tuple[tuple[int, ...], ...]
    ranks: tuple[int, ...]
    rules: tuple[PaletteProcedureRule, ...]
    maximum_repetitions: int
    htm_costs: tuple[int, ...]
    qtm_costs: tuple[int, ...]

    @property
    def rule_count(self):
        return len(self.rules)

    @property
    def instruction_family_count(self):
        return len({rule.recipe for rule in self.rules})

    def instruction_for(self, observation):
        if tuple(observation) == self.solved_observation:
            return ()
        matches = [rule for rule in self.rules if tuple(observation) in rule.observations]
        if len(matches) != 1:
            raise ValueError("procedure has no unique instruction for this observation")
        return matches[0].recipe


def _recognition_transition(observation, action, stage, inventory):
    from .human_chains import _feature_successor, _observation
    from .human_methods import _recognition_spec

    identity, offset, result = inventory.action(tuple(range(48))), 0, []
    for feature, block in _recognition_spec(inventory, stage):
        width = len(_observation(identity, block, feature.kind))
        result.extend(_feature_successor(observation[offset:offset + width], action,
                                        inventory, block, feature.kind))
        offset += width
    if offset != len(observation):
        raise ValueError("procedure observation has an invalid recognition width")
    return tuple(result)


def _recognition_fields(stage, inventory):
    """Read only functions of the certified observation, including phase differences.

    Residual-action observations contain every equivalent full pose. A field
    is retained only when it has the same value in all equivalent rows of
    every case. Thus an absolute phase erased by the residual subgroup can
    never leak into recognition. Relative phases can remain observable.
    """
    from .human_chains import _feature_indices, _observation
    from .human_methods import _recognition_spec

    fields, offset = [], 0
    identity = inventory.action(tuple(range(48)))
    observations = stage.observations
    for feature, block in _recognition_spec(inventory, stage):
        width = len(_observation(identity, block, feature.kind))
        values = [value[offset:offset + width] for value in observations]
        offset += width
        kind = feature.kind
        indices = _feature_indices(inventory, feature)
        pose = kind in ("solve_block", "solve_blocks", "solve_blocks_up_to_actions")
        aligned = kind in ("place_blocks_up_to_alignment", "solve_blocks_up_to_actions")
        stride = 2 if pose else 1
        row_width = len(indices) * stride
        if kind == "orient_slots":
            rows = [(value,) for value in values]
        elif kind == "occupy_slots":
            for index in indices:
                fields.append((f"`{inventory.blocks[index].compact_name}` is in the home region",
                               tuple(index in value for value in values), "bool", None))
            continue
        else:
            rows = [tuple(value[start:start + row_width]
                          for start in range(0, len(value), row_width)) if aligned else (value,)
                    for value in values]
        phases = []
        for position, index in enumerate(indices):
            name = f"`{inventory.blocks[index].compact_name}`"
            if kind != "orient_slots":
                destinations = [tuple(row[position * stride] for row in case_rows)
                                for case_rows in rows]
                if all(len(set(value)) == 1 for value in destinations):
                    fields.append((name, tuple(value[0] for value in destinations), "destination", index))
            if pose or kind == "orient_slots":
                coordinates = [tuple(row[position if kind == "orient_slots" else position * 2 + 1]
                                     for row in case_rows) for case_rows in rows]
                phases.append((index, coordinates))
                if all(len(set(value)) == 1 for value in coordinates):
                    fields.append((("phase at " if kind == "orient_slots" else "phase of ") + name,
                                   tuple(value[0] for value in coordinates),
                                   "phase", inventory.blocks[index].orientation_order))
        for first_position, (first, first_values) in enumerate(phases):
            for second, second_values in phases[first_position + 1:]:
                order = inventory.blocks[first].orientation_order
                if order != inventory.blocks[second].orientation_order:
                    continue
                differences = [tuple((a - b) % order for a, b in zip(left, right))
                               for left, right in zip(first_values, second_values)]
                if all(len(set(value)) == 1 for value in differences):
                    names = (inventory.blocks[first].compact_name,
                             inventory.blocks[second].compact_name)
                    prefix = "phase at " if kind == "orient_slots" else "phase of "
                    fields.append((f"{prefix}`{names[0]}` minus {prefix}`{names[1]}`",
                                   tuple(value[0] for value in differences), "relative_phase", order))
    return tuple(fields)


def _recognition_predicates(stage, inventory, *, include_patterns=False):
    """Small exact tests over footprints, phases and relative phases."""
    predicates, seen = [], set()
    full = (1 << stage.case_count) - 1
    for label, values, kind, metadata in _recognition_fields(stage, inventory):
        for value in sorted(set(values), key=lambda value:
                            (kind == "destination" and value != metadata, value)):
            mask = sum(1 << index for index, entry in enumerate(values) if entry == value)
            if mask in (0, full) or mask in seen or full ^ mask in seen:
                continue
            seen.add(mask)
            if kind == "destination":
                positive = (f"{label} is at home" if value == metadata else
                            f"{label} occupies `{inventory.blocks[value].compact_name}`")
            elif kind == "bool":
                positive = label if value else "not (" + label + ")"
            elif kind == "relative_phase" and value == 0:
                positive = label.replace(" minus ", " equals ")
            else:
                positive = f"{label} = {value} (mod {metadata})"
            predicates.append((positive, mask))
    if include_patterns:
        # An exact pattern is a finite fallback, used only when no small
        # visible predicate separates observations requiring different calls.
        from .human_render import _recognition_cue
        for index, observation in enumerate(stage.observations):
            mask = 1 << index
            if mask not in seen:
                predicates.append((_recognition_cue(stage, observation, inventory), mask))
    return tuple(predicates)


def _decision_rules(stage, inventory, choices, transitions, weights):
    """Compile a disjoint conditional cover, sharing any common instruction."""
    predicates = _recognition_predicates(stage, inventory)
    root = sum(1 << index for index, observation in enumerate(stage.observations)
               if observation != stage.solved_observation)

    def common(mask):
        indices = [index for index in range(stage.case_count) if mask & (1 << index)]
        result = set(choices[indices[0]])
        for index in indices[1:]:
            result.intersection_update(choices[index])
        return tuple(sorted(result, key=lambda recipe: (len(recipe), weights[recipe], recipe)))

    partitions = {}
    for index in range(stage.case_count):
        if root & (1 << index):
            signature = tuple(bool(truth & (1 << index)) for _, truth in predicates)
            partitions[signature] = partitions.get(signature, 0) | (1 << index)
    if any(not common(mask) for mask in partitions.values()):
        predicates = _recognition_predicates(stage, inventory, include_patterns=True)

    @lru_cache(None)
    def compile_tree(mask):
        shared = common(mask)
        if shared:
            return 1, 0, ("leaf", shared[0], mask)
        best = None
        splits = [(text, mask & truth, mask & ~truth) for text, truth in predicates
                  if mask & truth and mask & ~truth]
        # Full dynamic programming is tiny for human-sized stages. Larger
        # fallback domains use balanced splits, with the same exact coverage.
        if stage.case_count > 12:
            splits = sorted(splits, key=lambda split:
                            (abs(split[1].bit_count() - split[2].bit_count()), len(split[0])))[:1]
        for text, yes, no in splits:
            left, right = compile_tree(yes), compile_tree(no)
            candidate = (left[0] + right[0], left[1] + right[1] + len(text),
                         ("if", text, left[2], right[2]))
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is None:
            raise ValueError("visible predicates cannot distinguish procedure commands")
        return best

    if not root:
        return ()
    output = []
    def flatten(tree, conditions=()):
        if tree[0] == "leaf":
            _, recipe, mask = tree
            observations = tuple(observation for index, observation in enumerate(stage.observations)
                                 if mask & (1 << index))
            output.append(PaletteProcedureRule(conditions, recipe, observations,
                         tuple(transitions[recipe][observation] for observation in observations)))
            return
        _, text, yes, no = tree
        flatten(yes, (*conditions, text))
        flatten(no, (*conditions, "otherwise (" + text + ")"))
    flatten(compile_tree(root)[2])
    return tuple(output)


def certified_procedure(method):
    """Factor the saved complete policy into certified conditional instructions.

    This reads the existing portable subgroup certificates and exact case
    paths; it performs neither ambient-group enumeration nor quality search.
    Complete operations belong to the preceding subgroup, proving endpoint
    preservation. Prefix/suffix equality proves termination, physical costs,
    original-body permissions and complete observation-fiber coverage.
    """
    palette, inventory = method.palette, method.inventory
    algorithms = {algorithm.id: algorithm for algorithm in palette.recipes}
    saved = {(number, observation): path for number, observation, path in method.case_recipes}
    stages = []
    for stage, certified in zip(method.stages,
                               method.ambient_method._symbolic_chain.stages[method.prefix_stage_count:]):
        paths = {observation: expanded_recipe_path(palette, saved[stage.number, observation])
                 for observation in stage.observations}
        available = set(identifier for observation in stage.observations
                        for identifier in saved[stage.number, observation])
        # Factor only with definitions already used somewhere in this method.
        from .palette_policies import recipe_taught_ids
        teaching = recipe_taught_ids(palette)
        taught = frozenset(identifier for path in saved.values() for step in path
                          for identifier in teaching[step])
        available.update(identifier for identifier in algorithms
                         if teaching[identifier].issubset(taught))
        candidates = [(identifier,) for identifier in sorted(available)
                      if algorithms[identifier].permutation in certified.group_before]
        # Keep the exact complete correction as a fallback, so every stage
        # always has a certified finite procedure even if its cases differ.
        candidates.extend(path for observation in stage.observations
                          if (path := saved[stage.number, observation]) and path not in candidates)
        choices = [set() for _ in stage.observations]
        transitions, weights = {}, {}
        for recipe in candidates:
            original = expanded_recipe_path(palette, recipe)
            if not original:
                continue
            from .human_chains import _then
            permutation = tuple(range(48))
            for identifier in recipe:
                if algorithms[identifier].permutation not in certified.group_before:
                    raise ValueError("procedure operation fails endpoint preservation")
                permutation = _then(permutation, algorithms[identifier].permutation)
            action = inventory.action(permutation)
            mapping = {observation: _recognition_transition(observation, action, stage, inventory)
                       for observation in stage.observations}
            if not set(mapping.values()).issubset(paths):
                raise ValueError("procedure leaves its complete certified observation domain")
            admitted = False
            for index, observation in enumerate(stage.observations):
                path = paths[observation]
                if path[:len(original)] == original and path[len(original):] == paths[mapping[observation]]:
                    choices[index].add(recipe)
                    admitted = True
            if admitted:
                transitions[recipe] = mapping
                weights[recipe] = sum(algorithms[identifier].htm_length for identifier in recipe)
        if any(not choices[index] for index, observation in enumerate(stage.observations)
               if observation != stage.solved_observation):
            raise ValueError("procedure omits a saved non-goal observation")
        rules = _decision_rules(stage, inventory, choices, transitions, weights)
        rank = {observation: len(path) for observation, path in paths.items()}
        for rule in rules:
            if any(rank[after] >= rank[before]
                   for before, after in zip(rule.observations, rule.next_observations)):
                raise ValueError("procedure does not strictly decrease its finite progress rank")
        repetitions = {}
        def count(observation):
            if observation == stage.solved_observation:
                return 0
            if observation not in repetitions:
                rule = next(rule for rule in rules if observation in rule.observations)
                repetitions[observation] = 1 + count(transitions[rule.recipe][observation])
            return repetitions[observation]
        def costs(metric):
            totals = {stage.solved_observation: 0}
            def cost(observation):
                if observation not in totals:
                    rule = next(rule for rule in rules if observation in rule.observations)
                    totals[observation] = sum(getattr(algorithms[identifier], metric + "_length")
                                            for identifier in rule.recipe) + cost(
                                            transitions[rule.recipe][observation])
                return totals[observation]
            return tuple(cost(value) for value in stage.observations)
        stages.append(PaletteProcedureStage(stage.number, stage.solved_observation,
                      stage.observations, tuple(rank[value] for value in stage.observations),
                      rules, max(count(value) for value in stage.observations), costs("htm"), costs("qtm")))
    return tuple(stages)


def _phase_frame_lines(stage, inventory):
    """Concrete marker positions make absolute and relative phase tests visible."""
    from .block_actions import _STICKER_IMAGES, _inverse, _powers
    from .human_chains import _feature_indices
    from .human_diagrams import _orientation_marker_points
    from .human_methods import _recognition_spec
    from .human_render import _sticker

    classes, anonymous = {}, set()
    for feature, _ in _recognition_spec(inventory, stage):
        if feature.kind not in ("orient_slots", "solve_block", "solve_blocks", "solve_blocks_up_to_actions"):
            continue
        for index in _feature_indices(inventory, feature):
            block = inventory.blocks[index]
            if block.orientation_order > 1:
                key = block.template_cells, block.orientation_order
                classes.setdefault(key, set()).add(index)
                if feature.kind == "orient_slots":
                    anonymous.add(key)
    if not classes:
        return []
    lines = ["Read phase by following the listed reference facet on the current piece. "
             "Its current position selects the phase in the footprint table. "
             "For a relative-phase test, subtract the two readings modulo their common order.", ""]
    for key, indices in classes.items():
        _, order = key
        first = min(indices)
        marker = _orientation_marker_points(inventory, (first,))[0]
        template_marker = _STICKER_IMAGES[_inverse(inventory.blocks[first].frame)][marker]
        marker_indices = (tuple(index for index, block in enumerate(inventory.blocks)
                                if (block.template_cells, block.orientation_order) == key)
                          if key in anonymous else tuple(sorted(indices)))
        markers = (f"`{inventory.blocks[index].compact_name}`: "
                   f"`{_sticker(_STICKER_IMAGES[inventory.blocks[index].frame][template_marker])}`"
                   for index in marker_indices)
        lines.extend(["Reference phase markers: " + "; ".join(markers) + ".", "",
                      "| Current footprint | " + " | ".join(f"Phase {phase}" for phase in range(order)) + " |",
                      "| --- | " + " | ".join("---" for _ in range(order)) + " |"])
        destinations = {inventory.action(case.representative).destinations[index]
                        for case in stage.cases for index in indices}
        if key in anonymous:
            destinations.update(indices)
        # A residual action may move a selected identity within its region;
        # include those legal equivalent footprints as well.
        for permutation in stage.feature.alignment_permutations:
            action = inventory.action(permutation)
            destinations.update(action.destinations[index] for index in indices)
        rotations = _powers(inventory.blocks[first].positive_rotation, order)
        for destination in sorted(destinations):
            frame = inventory.blocks[destination].frame
            positions = (_STICKER_IMAGES[frame][_STICKER_IMAGES[rotation][template_marker]]
                         for rotation in rotations)
            lines.append(f"| `{inventory.blocks[destination].compact_name}` | " +
                         " | ".join(f"`{_sticker(point)}`" for point in positions) + " |")
        lines.append("")
    return lines


def _recognition_grid(stage, procedure, inventory):
    """A small Cartesian coordinate chart, certified by all exact observations."""
    fields = [field for field in _recognition_fields(stage, inventory) if len(set(field[1])) > 1]
    best = None
    for first_position, first in enumerate(fields):
        for second in fields[first_position + 1:]:
            rows, columns = tuple(sorted(set(first[1]))), tuple(sorted(set(second[1])))
            if len(rows) * len(columns) != stage.case_count or stage.case_count > 16:
                continue
            projected = tuple(zip(first[1], second[1]))
            if len(set(projected)) != stage.case_count:
                continue
            score = (len(rows) + len(columns), len(first[0]) + len(second[0]))
            if best is None or score < best[0]:
                best = score, first, second, rows, columns, projected
    if best is None:
        return None
    _, first, second, rows, columns, projected = best
    table = {coordinates: procedure.instruction_for(observation)
             for coordinates, observation in zip(projected, stage.observations)}
    return first, second, rows, columns, table


def _grid_field_label(field):
    label, _, kind, order = field
    if kind == "destination":
        return "current footprint of " + label
    return label + f" (mod {order})"


def _grid_value(field, value, inventory):
    return f"`{inventory.blocks[value].compact_name}`" if field[2] == "destination" else str(value)


def _remaining_family_lines(method, stage, aliases):
    """Name an exact small generating family from admitted complete operations."""
    if stage.feature.kind != "solve_blocks_up_to_actions":
        return []
    from .human_chains import _inverse, _then
    from .palette_policies import recipe_taught_ids

    family = set(stage.feature.alignment_permutations)
    teaching = recipe_taught_ids(method.palette)
    taught = frozenset(identifier for _, _, path in method.case_recipes for recipe in path
                       for identifier in teaching[recipe])
    records = {record["id"]: record for record in method.palette.recipe_records}
    def named(algorithm):
        for identifier in expanded_recipe_path(method.palette, (algorithm.id,)):
            record = records[identifier]
            key = "body_id" if record["body_id"] is not None else "adjustment_id"
            if (key, record[key]) not in aliases:
                return False
            if record["setup_id"] is not None and ("setup_id", record["setup_id"]) not in aliases:
                return False
        return True
    eligible = sorted((algorithm for algorithm in method.palette.recipes
                       if algorithm.permutation in family and algorithm.permutation != tuple(range(48))
                       and teaching[algorithm.id].issubset(taught) and named(algorithm)),
                      key=lambda algorithm: (algorithm.htm_length,
                          recipe_structure(method.palette, (algorithm.id,), aliases)))
    closure, generators, names = {tuple(range(48))}, [], []
    for algorithm in eligible:
        if algorithm.permutation in closure:
            continue
        generators.append(algorithm.permutation)
        name = recipe_structure(method.palette, (algorithm.id,), aliases)
        inverse = next((candidate for candidate in eligible
                        if candidate.permutation == _inverse(algorithm.permutation)), None)
        if inverse is not None:
            reverse = recipe_structure(method.palette, (inverse.id,), aliases)
            if reverse != name:
                name += " / " + reverse
        names.append("`" + name + "`")
        queue = list(closure)
        for element in queue:
            for generator in generators:
                image = _then(element, generator)
                if image not in closure:
                    closure.add(image)
                    queue.append(image)
        if closure == family:
            return ["The remaining action family is generated by " + ", ".join(names) + ".", ""]
    return []


def _ready_cue(stage, inventory):
    from .human_chains import _feature_indices
    from .human_render import _recognition_cue

    if stage.feature.kind == "solve_blocks_up_to_actions":
        indices = _feature_indices(inventory, stage.feature)
        width = 2 * len(indices)
        rows = tuple(stage.solved_observation[offset:offset + width]
                     for offset in range(0, len(stage.solved_observation), width))
        orders = {inventory.blocks[index].orientation_order for index in indices}
        if (len(indices) > 1 and len(orders) == 1 and next(iter(orders)) > 1 and
                all(row[::2] == indices and len(set(row[1::2])) == 1 for row in rows) and
                {row[1] for row in rows} == set(range(next(iter(orders))))):
            return "all named blocks are in their home footprints and their phase readings are equal"
    return _recognition_cue(stage, stage.solved_observation, inventory)


def execution_vocabulary_lines(declarations):
    """One shared letter vocabulary, with an exact action for every definition."""
    lines = ["## Execution vocabulary", "",
             "| Kind | Name | Turn sequence | Block action |",
             "| --- | --- | --- | --- |"]
    displayed = {}
    for kind, name, declaration in declarations:
        identity = declaration.algorithm.turn_sequence, declaration.algorithm.permutation
        if (kind, name) in displayed:
            if displayed[kind, name] != identity:
                raise ValueError("a shared vocabulary name has conflicting physical definitions")
            continue
        displayed[kind, name] = identity
        lines.append(f"| {kind} | `{name}` | `{declaration.algorithm.turn_sequence}` | "
                     f"`{declaration.algorithm.block_action.notation}` |")
    lines.append("")
    setup = next((name for kind, name, _ in declarations if kind == "Setup"), None)
    body = next((name for kind, name, _ in declarations if kind == "Body"), None)
    if setup is not None and body is not None:
        lines.extend([f"`[{setup}: {body}]` executes setup {setup}, body {body}, then undoes {setup}.", ""])
    return lines


def _stage_diagram_lines(method, stage, procedure, aliases, *, face_colors=None):
    """Illustrate certified first-match cases using the written recognition cues."""
    from .stage_diagrams import stage_recognition_diagrams
    from .stage_diagram_render import stage_case_image

    cases = stage_recognition_diagrams(method, stage.number, procedure)
    algorithms = {algorithm.id: algorithm for algorithm in method.palette.recipes}
    lines = ["### Diagrammatic guide:", "",
             "Match cases in order; use the first match, then inspect again.", ""]
    for number, case in enumerate(cases, 1):
        instruction = "— (no moves)"
        if case.recipe:
            structure = recipe_structure(method.palette, case.recipe, aliases)
            turns = " ".join(algorithms[identifier].turn_sequence for identifier in case.recipe)
            instruction = f"`{structure}` (`{turns}`)"
        lines.extend([f"- case {number}: {case.cue}", "",
                      "  Algorithm: " + instruction, "",
                      f"  ![Stage {stage.number} recognition pattern]("
                      f"{stage_case_image(case.diagram, method.inventory, face_colors=face_colors)})", ""])
    return lines


def palette_method_guide(method, *, declarations=None, aliases=None, include_vocabulary=True,
                         recognition_diagrams=False, face_colors=None):
    """Render compact procedures with a fixed, witnessed execution vocabulary."""
    from .human_render import _feature_name, _recognition_cue, recognition_wording
    from .human_repertoire_render import _stage_title

    if type(recognition_diagrams) is not bool:
        raise TypeError("recognition_diagrams must be a boolean")
    if face_colors is not None:
        from .graphics import _palette
        _palette(face_colors)
    procedures = certified_procedure(method)
    if declarations is None and aliases is None:
        declarations, aliases = execution_vocabulary(method.palette,
                                (path for _, _, path in method.case_recipes))
    elif declarations is None or aliases is None:
        raise ValueError("shared vocabulary requires both declarations and aliases")
    requirements = "; ".join(_feature_name(feature, method.inventory) for feature in method.domain_features)
    scope = (f"This method covers all **{method.group_order:,} reachable colored states** in the "
             "declared reference shape" +
             (f" satisfying: {requirements}." if requirements else "."))
    lines = ["# Solving from reference shape", "", scope, "",
             "Each stage has a complete observation-fiber certificate. The conditional rules "
             "factor the exact saved corrections and strictly decrease a finite progress rank. "
             "Every complete operation restores earlier commitments at its endpoint.", ""]
    if include_vocabulary:
        lines.extend(execution_vocabulary_lines(declarations))
    for stage, procedure in zip(method.stages, procedures):
        title = (f"Stage {stage.number}: Prepare {stage.block_name} for the remaining actions"
                 if stage.feature.kind == "solve_blocks_up_to_actions" else _stage_title(stage))
        lines.extend(["## " + title, "",
                      f"Commit to {_feature_name(stage.feature, method.inventory)}. "
                      f"This reduces {stage.order_before:,} possibilities to {stage.order_after:,}, "
                      f"with {stage.case_count} certified observations and {procedure.instruction_family_count} "
                      "instruction form" + ("s." if procedure.instruction_family_count != 1 else "."), "",
                      "Stop this stage when " + _ready_cue(stage, method.inventory) + ".", ""])
        lines.extend(_remaining_family_lines(method, stage, aliases))
        from .human_chains import _feature_indices
        if (stage.feature.kind in ("place_block", "place_blocks") and
                all(method.inventory.blocks[index].orientation_order == 1
                    for index in _feature_indices(method.inventory, stage.feature))):
            lines.extend(["These footprints have no remaining observable orientation; "
                          "placing them fully solves the named blocks.", ""])
        if (any("phase" in condition for rule in procedure.rules for condition in rule.conditions)
                or stage.feature.kind in ("orient_slots", "solve_blocks_up_to_actions")):
            lines.extend(_phase_frame_lines(stage, method.inventory))
        grid = _recognition_grid(stage, procedure, method.inventory)
        if len(procedure.rules) == 1 and not procedure.rules[0].conditions:
            lines.extend([f"Repeat **`{recipe_structure(method.palette, procedure.rules[0].recipe, aliases)}`** "
                          f"until the stage goal holds; at most {procedure.maximum_repetitions} "
                          "repetition" + ("s are needed." if procedure.maximum_repetitions != 1 else " is needed."), ""])
        elif grid is not None and stage.feature.kind == "solve_blocks_up_to_actions":
            first, second, rows, columns, table = grid
            lines.extend([f"Read {_grid_field_label(first)} and {_grid_field_label(second)}. "
                          "Execute the cell's Structure, then inspect again. "
                          f"At most {procedure.maximum_repetitions} instructions are needed.", "",
                          "| " + _grid_field_label(first) + " | " +
                          " | ".join(_grid_value(second, value, method.inventory) for value in columns) + " |",
                          "| --- | " + " | ".join("---" for _ in columns) + " |"])
            for row in rows:
                cells = ("Ready" if not table[row, column] else
                         "`" + recipe_structure(method.palette, table[row, column], aliases) + "`"
                         for column in columns)
                lines.append("| " + _grid_value(first, row, method.inventory) + " | " + " | ".join(cells) + " |")
            lines.append("")
        else:
            lines.extend(["Match the visible conditions, execute Structure, then inspect again. "
                          f"At most {procedure.maximum_repetitions} instructions are needed.", "",
                          "| Recognize | Structure |", "| --- | --- |"])
            for rule in procedure.rules:
                lines.append("| " + "; and ".join(rule.conditions or ("Any remaining case",)) +
                             " | `" + recipe_structure(method.palette, rule.recipe, aliases) + "` |")
            lines.append("")
        if stage.implied_features:
            lines.extend(["Also correct after this stage: " +
                          "; ".join(_feature_name(feature, method.inventory)
                                    for feature in stage.implied_features) + ".", ""])
        if recognition_diagrams:
            lines.extend(_stage_diagram_lines(method, stage, procedure, aliases,
                                              face_colors=face_colors))
    mean = sum(sum(procedure.htm_costs) / len(procedure.htm_costs) for procedure in procedures)
    worst = sum(max(procedure.htm_costs) for procedure in procedures)
    lines.extend([f"The {len(method.taught_body_ids)} learned bodies are shared across the stages. "
                  f"Following these instructions averages {mean:.2f} HTM and is at most "
                  f"{worst:,} HTM, before cancellation between complete operations.", "",
                  "After the final stage, every modeled corner and edge sticker is solved. "
                  "Unmarked center spin and independent virtual-core spin are outside this model.", ""])
    return recognition_wording("\n".join(lines))
