"""Physical recognition patterns for every certified action-family stage case.

The saved observation determines what is shown. Its physical representative
supplies sticker positions, but never adds recognition requirements. Only small
declared alignment families are expanded; the ambient state group is not
enumerated and no new algorithm or execution permission is introduced.
"""

from dataclasses import dataclass, replace

from . import State
from .human_chains import _feature_indices, _observation
from .human_diagrams import _orientation_marker_points
from .human_methods import (_goal_observation, _recognition_spec,
                            _stage_observation, _state_for_permutation, _then)
from .human_render import _recognition_cue, recognition_wording


_IDENTITY = tuple(range(48))
_ALIGNED_KINDS = ("place_blocks_up_to_alignment", "solve_blocks_up_to_actions")


@dataclass(frozen=True)
class StageDiagramVariant:
    """One witnessed state with explicit, observation-derived display roles.

    Block IDs name physical source identities. Sticker IDs name *current*
    positions in URFDLB's 54-facelet order. Slot labels name destination block
    indices, and each region is a tuple of current reference cell indices.
    Fully colored blocks have observed poses; inset colors identify blocks
    whose orientation is ignored. A reference sticker alone reads orientation
    without exposing the occupant's other sticker colors.
    """

    state: State
    full_blocks: tuple[int, ...] = ()
    location_blocks: tuple[int, ...] = ()
    reference_stickers: tuple[int, ...] = ()
    piece_labels: tuple[tuple[int, str], ...] = ()
    slot_labels: tuple[tuple[int, str], ...] = ()
    solved_blocks: tuple[int, ...] = ()
    regions: tuple[tuple[int, ...], ...] = ()
    orientation_labels: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class StageCaseDiagram:
    """Certified physical patterns with a canonical saved observation.

    Exact cases have that observation in every variant. A partial procedural
    pattern can also illustrate other observations in its enclosing
    StageRecognitionDiagram's certified first-match domain.
    """

    stage_number: int
    observation: tuple[int, ...]
    cue: str
    variants: tuple[StageDiagramVariant, ...]
    notes: tuple[str, ...] = ()
    ready: bool = False


@dataclass(frozen=True)
class StageRecognitionDiagram:
    """One ordered visible test and its existing permitted instruction.

    ``matching_observations`` is the literal test's truth set;
    ``observations`` is its effective domain after preceding rows. The latter
    may contain several exact observations illustrated by one partial pattern.
    """

    cue: str
    observations: tuple[tuple[int, ...], ...]
    recipe: tuple[str, ...]
    diagram: StageCaseDiagram
    conditions: tuple[str, ...] = ()
    matching_observations: tuple[tuple[int, ...], ...] = ()


def _facelet(point):
    face, offset = divmod(point, 8)
    return face * 9 + offset + (offset >= 4)


def _observer_records(inventory, stage, observation):
    """Partition the joint observation using the existing certified readers."""
    identity, offset, records = inventory.action(_IDENTITY), 0, []
    for feature, block in _recognition_spec(inventory, stage):
        width = len(_observation(identity, block, feature.kind))
        value = observation[offset:offset + width]
        if len(value) != width:
            raise ValueError("diagram observation has an invalid recognition width")
        records.append((feature, _feature_indices(inventory, feature), value))
        offset += width
    if offset != len(observation):
        raise ValueError("diagram observation has an invalid recognition width")
    return tuple(records)


def _uniform_relative(feature, indices, observation, inventory):
    """Identify full poses modulo one common, unrestricted orientation offset."""
    if feature.kind != "solve_blocks_up_to_actions" or len(indices) < 2:
        return False
    orders = {inventory.blocks[index].orientation_order for index in indices}
    if len(orders) != 1 or next(iter(orders)) <= 1:
        return False
    order, width = next(iter(orders)), 2 * len(indices)
    rows = tuple(observation[start:start + width]
                 for start in range(0, len(observation), width))
    if len(rows) != order or any(row[::2] != rows[0][::2] for row in rows):
        return False
    shifts = []
    for row in rows:
        offsets = {(row[2 * position + 1] - rows[0][2 * position + 1]) % order
                   for position in range(len(indices))}
        if len(offsets) != 1:
            return False
        shifts.append(next(iter(offsets)))
    return set(shifts) == set(range(order))


def _fixed_blocks(inventory, group):
    """Subgroup generators prove every displayed earlier full-pose guarantee."""
    actions = tuple(inventory.action(generator.permutation)
                    for generator in group.strong_generators)
    return tuple(index for index in range(len(inventory.blocks))
                 if all(action.destinations[index] == index and not action.phases[index]
                        for action in actions))


def _reference_sticker(inventory, permutation, source):
    point, = _orientation_marker_points(inventory, (source,))
    return _facelet(permutation[point])


def _variant(method, permutation, records, solved):
    inventory = method.inventory
    action = inventory.action(permutation)
    full, location, stickers, pieces, slots, regions, readings = set(), set(), set(), {}, {}, set(), {}
    for feature, indices, observation in records:
        kind = feature.kind
        if kind in ("solve_block", "solve_blocks"):
            full.update(indices)
            pieces.update((index, inventory.blocks[index].compact_name) for index in indices)
        elif kind == "orient_slots":
            sources = {destination: source for source, destination in enumerate(action.destinations)}
            for slot in indices:
                sticker = _reference_sticker(inventory, permutation, sources[slot])
                stickers.add(sticker)
                readings[sticker] = str(action.phases[sources[slot]])
                slots[slot] = inventory.blocks[slot].compact_name
        elif _uniform_relative(feature, indices, observation, inventory):
            for index in indices:
                sticker = _reference_sticker(inventory, permutation, index)
                stickers.add(sticker)
                readings[sticker] = str(action.phases[index])
                pieces[index] = inventory.blocks[index].compact_name
        elif kind == "solve_blocks_up_to_actions":
            full.update(indices)
            pieces.update((index, inventory.blocks[index].compact_name) for index in indices)
        else:
            full.update(index for index in indices if inventory.blocks[index].orientation_order == 1)
            location.update(index for index in indices if inventory.blocks[index].orientation_order > 1)
            pieces.update((index, inventory.blocks[index].compact_name) for index in indices)
            if kind == "occupy_slots":
                # Outline the observed occupied region. An additional home
                # outline would introduce a second, unlabeled meaning.
                regions.add(tuple(sorted(cell for index in indices
                                         for cell in inventory.blocks[action.destinations[index]].cells)))
    # Finer independent observations retain all information they actually read.
    # An exact pose therefore takes precedence over a placement-only display.
    location.difference_update(full)
    return StageDiagramVariant(
        _state_for_permutation(method.reference_shape, permutation),
        tuple(sorted(full)), tuple(sorted(location)), tuple(sorted(stickers)),
        tuple(sorted(pieces.items())), tuple(sorted(slots.items())), solved,
        tuple(sorted(regions)), tuple(sorted(readings.items())))


def _visible_key(variant, inventory):
    """Ignore representative differences on unobserved blocks and orientations."""
    action = inventory.action(variant.state)
    return (tuple((source, action.destinations[source], action.phases[source])
                  for source in variant.full_blocks),
            tuple((source, action.destinations[source]) for source in variant.location_blocks),
            variant.reference_stickers,
            tuple((source, action.destinations[source]) for source, _ in variant.piece_labels),
            variant.slot_labels, variant.regions, variant.orientation_labels)


def _notes(records, inventory):
    notes = []
    for feature, indices, observation in records:
        kind = feature.kind
        if kind in ("place_block", "place_blocks", "place_blocks_up_to_alignment", "occupy_slots"):
            notes.append("Small colored squares identify placement-only pieces; their illustrated orientation is ignored.")
        if kind == "orient_slots":
            notes.append("Read the reference sticker of each labelled slot's current occupant; its identity is ignored.")
        if _uniform_relative(feature, indices, observation, inventory):
            notes.append("The sticker readings show the illustrated orientation differences.")
        elif kind == "solve_blocks_up_to_actions":
            notes.append("The alternative arrangements belong to the same case under the remaining action family.")
        if kind == "place_blocks_up_to_alignment":
            notes.append("The alternative arrangements share one allowed alignment for all named pieces.")
        if kind == "occupy_slots":
            notes.append("The outlined occupied region matters; ordering and orientation within it are ignored.")
    return tuple(dict.fromkeys(notes))


def _general_families(records, inventory):
    return tuple(feature.alignment_permutations for feature, indices, observation in records
                 if feature.kind in _ALIGNED_KINDS and
                 not _uniform_relative(feature, indices, observation, inventory))


def _noncommuting_families(families):
    """One Cartesian product need not span overlapping noncommuting groups."""
    return any(_then(first, second) != _then(second, first)
               for position, family in enumerate(families)
               for other in families[position + 1:]
               for first in family for second in other)


def _coupled_background(records, inventory):
    """Notice when an adjustment also changes a separately observed block.

    A hidden background action might restore that extra observation while
    retaining another allowed pose. Sampling only declared adjustments then
    supplies witnesses, without proving that every joint arrangement is drawn.
    """
    for feature, indices, observation in records:
        if (feature.kind not in _ALIGNED_KINDS or
                _uniform_relative(feature, indices, observation, inventory)):
            continue
        own = set(indices)
        actions = tuple(inventory.action(permutation)
                        for permutation in feature.alignment_permutations)
        for other, other_indices, _ in records:
            if other == feature:
                continue
            orientation = other.kind in ("solve_block", "solve_blocks", "orient_slots",
                                         "solve_blocks_up_to_actions")
            placement = other.kind != "orient_slots"
            if any((placement and action.destinations[index] != index) or
                   (orientation and action.phases[index])
                   for index in set(other_indices) - own for action in actions):
                return True
    return False


def stage_case_diagrams(method, stage_number):
    """Return one physical pattern per certified observation, without search.

    Exact poses are fully colored. Placement-only pieces use inset colors.
    Anonymous and relative orientations expose only intrinsic reference
    stickers. General small residual families supply explicit alternatives,
    filtered against the *complete joint observation* and preceding subgroup.
    """
    from .coarse_methods import CoarseMethod

    if not isinstance(method, CoarseMethod):
        raise TypeError("stage case diagrams require a CoarseMethod")
    if type(stage_number) is not int:
        raise TypeError("stage_number must be an integer")
    if not 1 <= stage_number <= len(method.stages):
        raise ValueError("stage_number is outside the coarse method")
    stage = method.stages[stage_number - 1]
    chain = method.ambient_method._symbolic_chain
    group = chain.stages[method.prefix_stage_count + stage_number - 1].group_before
    inventory, solved, result = method.inventory, _fixed_blocks(method.inventory, group), []
    identity = inventory.action(_IDENTITY)
    goal = _observation(identity, stage.block_index, stage.feature.kind)
    for case in stage.cases:
        permutation = case.representative
        if permutation not in group:
            raise ValueError("case diagram does not preserve earlier stage commitments")
        action = inventory.action(permutation)
        if _stage_observation(action, stage, inventory) != case.observation:
            raise ValueError("case diagram disagrees with its certified observation")
        records = _observer_records(inventory, stage, case.observation)
        candidates = {permutation}
        families = _general_families(records, inventory)
        for family in families:
            # Independent observers can admit independent adjustments.
            # Keep their Cartesian combinations, rather than showing
            # only one adjustment at a time. Do not filter intermediate
            # actions: a later complete adjustment can restore another
            # observer. Each declared finite group includes identity.
            candidates = {_then(alignment, candidate)
                          for candidate in candidates for alignment in family}
        variants, seen = [], set()
        # Keep the saved witness first; remaining equivalent arrangements have
        # deterministic order and retain all preceding stage guarantees.
        for candidate in (permutation, *sorted(candidates - {permutation})):
            if candidate not in group:
                continue
            if _stage_observation(inventory.action(candidate), stage, inventory) != case.observation:
                continue
            variant = _variant(method, candidate, records, solved)
            key = _visible_key(variant, inventory)
            if key not in seen:
                variants.append(variant)
                seen.add(key)
        ready = _goal_observation(case.observation, inventory, stage) == goal
        notes = _notes(records, inventory)
        if _noncommuting_families(families) or _coupled_background(records, inventory):
            notes += ("The pictures show witnessed alternatives; additional accepted arrangements "
                      "are specified by the equivalent-pattern conditions above.",)
        result.append(StageCaseDiagram(
            stage.number, case.observation,
            recognition_wording(_recognition_cue(stage, case.observation, inventory)),
            tuple(variants), notes, ready))
    return tuple(result)


def _field_names(field, inventory):
    """Decode only the library's generated field labels, never user text."""
    label = field[0]
    return tuple(index for part in label.split("`")[1::2]
                 for index, block in enumerate(inventory.blocks) if part == block.compact_name)


def _field_literal(field, value, inventory):
    label, _, kind, metadata = field
    if kind == "destination":
        return (f"{label} is at home" if value == metadata else
                f"{label} occupies `{inventory.blocks[value].compact_name}`")
    if kind == "bool":
        return label if value else "not (" + label + ")"
    if kind == "relative_phase" and value == 0:
        return label.replace(" minus ", " equals ")
    return f"{label} = {value} (mod {metadata})"


def _predicate_catalog(stage, inventory, fields):
    from .palette_render import _recognition_predicates

    literal_fields = {}
    for field in fields:
        for value in set(field[1]):
            literal_fields[_field_literal(field, value, inventory)] = field
    return {text: (mask, literal_fields.get(text)) for text, mask in
            _recognition_predicates(stage, inventory, include_patterns=True)}


def _condition_mask(condition, catalog, full):
    if condition in catalog:
        return catalog[condition][0]
    if condition.startswith("otherwise (") and condition.endswith(")"):
        return full ^ catalog[condition[len("otherwise ("):-1]][0]
    raise ValueError("recognition diagram has a condition outside the generated predicate vocabulary")


def _ordered_partition(conditions, recipes, catalog, observations, ready, expected):
    """Prove the original instruction is selected by each first matching row."""
    full = (1 << len(observations)) - 1
    masks = []
    for row in conditions:
        mask = full
        for condition in row:
            mask &= _condition_mask(condition, catalog, full)
        masks.append(mask)
    assigned = [[] for _ in conditions]
    for index, observation in enumerate(observations):
        if observation in ready:
            if expected(observation):
                return None
            continue
        selected = next((number for number, mask in enumerate(masks) if mask & (1 << index)), None)
        if selected is None or recipes[selected] != expected(observation):
            return None
        assigned[selected].append(observation)
    return tuple(masks), tuple(tuple(row) for row in assigned)


def _masked_variant(variant, fields, inventory):
    """Expose only positive tested coordinates, hiding the rest of the goal."""
    action, permutation = inventory.action(variant.state), variant.state.sticker_permutation
    full, location, absolute, relative, stickers = set(), set(), set(), set(), set()
    pieces, slots, regions, readings = {}, {}, set(), {}
    by_destination = {destination: source for source, destination in enumerate(action.destinations)}
    for field in fields:
        label, _, kind, metadata = field
        names = _field_names(field, inventory)
        if kind == "destination":
            source = metadata
            (full if inventory.blocks[source].orientation_order == 1 else location).add(source)
            pieces[source] = inventory.blocks[source].compact_name
        elif kind in ("phase", "relative_phase"):
            slot_based = label.startswith("phase at ")
            for index in names:
                source = by_destination[index] if slot_based else index
                sticker = _reference_sticker(inventory, permutation, source)
                stickers.add(sticker)
                readings[sticker] = str(action.phases[source])
                if slot_based:
                    slots[index] = inventory.blocks[index].compact_name
                else:
                    pieces[source] = inventory.blocks[source].compact_name
                (relative if kind == "relative_phase" else absolute).add(source)
        elif kind == "bool":
            # Membership names a home location in an unordered occupied
            # region. Show its current occupant only when it is actually in
            # the selected physical family; do not invent an assignment.
            for slot in names:
                regions.add(inventory.blocks[slot].cells)
                slots[slot] = inventory.blocks[slot].compact_name
                source = by_destination[slot]
                if source in dict(variant.piece_labels):
                    (full if inventory.blocks[source].orientation_order == 1 else location).add(source)
                    pieces[source] = inventory.blocks[source].compact_name
    # A tested location and absolute orientation jointly determine the pose.
    full.update(location & absolute)
    location.difference_update(full | relative)
    return replace(variant, full_blocks=tuple(sorted(full)), location_blocks=tuple(sorted(location)),
                   reference_stickers=tuple(sorted(stickers)), piece_labels=tuple(sorted(pieces.items())),
                   slot_labels=tuple(sorted(slots.items())), regions=tuple(sorted(regions)),
                   orientation_labels=tuple(sorted(readings.items())))


def _common_field(stage, fields, observations):
    """Choose one coordinate already forced by earlier first-match branches."""
    positions = {observation: index for index, observation in enumerate(stage.observations)}
    for field in fields:
        if len(set(field[1])) <= 1:
            continue
        if len({field[1][positions[observation]] for observation in observations}) == 1:
            return field
    return None


def _presentation_record(method, stage, exact, observations, recipe, cue, conditions, matching, fields):
    """Show every distinct visible arrangement within this partial pattern.

    Common orientation shifts are physical alternatives, so the procedural
    picture shows them directly rather than relying on a footer to explain an
    arbitrary exemplar. Only already declared finite families are expanded.
    """
    inventory = method.inventory
    group = method.ambient_method._symbolic_chain.stages[
        method.prefix_stage_count + stage.number - 1].group_before
    variants, seen = [], set()
    for observation in observations:
        representative = exact[observation]
        records = _observer_records(inventory, stage, observation)
        candidates = {variant.state.sticker_permutation for variant in representative.variants}
        for feature, indices, value in records:
            if _uniform_relative(feature, indices, value, inventory):
                candidates = {_then(alignment, candidate) for candidate in candidates
                              for alignment in feature.alignment_permutations}
        saved = representative.variants[0].state.sticker_permutation
        for permutation in (saved, *sorted(candidates - {saved})):
            if permutation not in group or _stage_observation(
                    inventory.action(permutation), stage, inventory) != observation:
                continue
            variant = _variant(method, permutation, records, representative.variants[0].solved_blocks)
            if fields is not None:
                variant = _masked_variant(variant, fields, inventory)
            key = _visible_key(variant, inventory)
            if key not in seen:
                variants.append(variant)
                seen.add(key)
    if not variants:
        raise ValueError("recognition pattern has no certified physical arrangement")
    picture = replace(exact[observations[0]], cue=recognition_wording(cue), notes=(),
                      variants=tuple(variants))
    return StageRecognitionDiagram(picture.cue, observations, recipe, picture,
                                   tuple(conditions), matching)


def stage_recognition_diagrams(method, stage_number, procedure=None, *, use_grid=None):
    """Illustrate the guide's ordered positive cases, preserving every call.

    A visible predicate can cover several exact certified observations. Every
    simplification is checked by first-match replay over the complete observed
    domain. Grid stages retain the existing chart's coordinates and subtraction
    order. Negated branches are omitted only when this leaves selection exact.
    """
    from .palette_render import (_grid_field_label, _grid_value, _recognition_fields,
                                 _recognition_grid, certified_procedure)

    exact = {picture.observation: picture for picture in stage_case_diagrams(method, stage_number)}
    stage, inventory = method.stages[stage_number - 1], method.inventory
    procedure = certified_procedure(method)[stage_number - 1] if procedure is None else procedure
    if procedure.number != stage_number or procedure.observations != stage.observations:
        raise ValueError("recognition procedure does not match the certified stage")
    if use_grid is not None and type(use_grid) is not bool:
        raise TypeError("use_grid must be a boolean or None")
    fields = _recognition_fields(stage, inventory)
    ready = tuple(observation for observation in stage.observations if exact[observation].ready)
    if not ready:
        raise ValueError("recognition stage has no ready observation")
    grid = _recognition_grid(stage, procedure, inventory)
    repeating = len(procedure.rules) == 1 and not procedure.rules[0].conditions
    show_grid = (stage.feature.kind == "solve_blocks_up_to_actions" and grid is not None and
                 not repeating) if use_grid is None else use_grid
    if show_grid:
        if grid is None:
            raise ValueError("recognition stage has no certified coordinate grid")
        first, second, rows, columns, _, = grid
        positions = {observation: index for index, observation in enumerate(stage.observations)}
        by_coordinates = {(first[1][index], second[1][index]): observation
                          for observation, index in positions.items()}
        ordered = (*ready, *(by_coordinates[row, column] for row in rows for column in columns
                              if by_coordinates[row, column] not in ready))
        output = []
        for observation in ordered:
            index = positions[observation]
            cue = "; ".join(_grid_field_label(field) + " = " +
                            _grid_value(field, field[1][index], inventory) for field in (first, second))
            if observation in ready:
                cue = "Ready: " + cue
            output.append(_presentation_record(method, stage, exact, (observation,),
                                              procedure.instruction_for(observation), cue, (),
                                              (observation,), (first, second)))
        return tuple(output)

    output = [_presentation_record(method, stage, exact, ready, (), "Ready: " + exact[ready[0]].cue,
                                   (), ready, None)]
    catalog = _predicate_catalog(stage, inventory, fields)
    conditions = [tuple(rule.conditions) for rule in procedure.rules]
    recipes = tuple(rule.recipe for rule in procedure.rules)
    partition = _ordered_partition(conditions, recipes, catalog, stage.observations, set(ready),
                                   procedure.instruction_for)
    if partition is None:
        raise ValueError("recognition procedure is not a complete first-match instruction cover")
    # Remove redundant negative branches individually, checking the entire
    # domain each time rather than assuming a particular decision-tree shape.
    for number, row in enumerate(tuple(conditions)):
        for condition in row:
            if not condition.startswith("otherwise ("):
                continue
            candidate = conditions.copy()
            candidate[number] = tuple(item for item in candidate[number] if item != condition)
            checked = _ordered_partition(candidate, recipes, catalog, stage.observations, set(ready),
                                         procedure.instruction_for)
            if checked is not None:
                conditions, partition = candidate, checked
    masks, domains = partition
    for row, recipe, mask, domain in zip(conditions, recipes, masks, domains):
        if not domain:
            continue
        selected = []
        exact_fallback = False
        for condition in row:
            literal = (condition[len("otherwise ("):-1] if condition.startswith("otherwise (")
                       and condition.endswith(")") else condition)
            field = catalog[literal][1]
            if field is None:
                exact_fallback = True
            elif not condition.startswith("otherwise ("):
                selected.append(field)
        if not row:
            common = _common_field(stage, fields, domain)
            if common is not None:
                selected.append(common)
        cue = "; and ".join(row) if row else "Any remaining case"
        matching = tuple(observation for index, observation in enumerate(stage.observations)
                         if mask & (1 << index))
        output.append(_presentation_record(method, stage, exact, domain, recipe, cue, row, matching,
                                          None if exact_fallback else tuple(selected)))
    # The returned partial pictures partition the full observed domain while
    # their raw matching sets retain the certified first-match semantics.
    assert set(observation for record in output for observation in record.observations) == set(stage.observations)
    return tuple(output)
