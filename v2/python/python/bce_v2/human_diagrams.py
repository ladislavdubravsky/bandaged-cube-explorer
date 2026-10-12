"""Recognition pictures with colors derived from guaranteed stage features.

The representative supplies a physical picture, but never decides which
blocks count as solved. That decision uses the method's exact subgroup facts.
Placement cases include every possible target orientation, because a single
representative's stickers are not a placement recognition requirement.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from . import State
from .block_actions import _CELL_POINTS, _STICKER_IMAGES, _powers
from .graphics import _FACE_CELLS
from .human_methods import HumanMethod, _observe, _state_for_permutation, _then
from .human_chains import _feature_indices, _resolve_feature


@dataclass(frozen=True)
class HumanRecognitionDiagram:
    """One physical orientation pictured for a recognition case.

    ``block_roles`` follows physical reference-block identities;
    ``cell_roles`` follows their current cells; ``sticker_roles`` follows the
    54 URFDLB facelets. The renderer chooses how to show these guarantees
    for each diagram mode. Placed and other unsolved blocks share white
    stickers while their semantic roles stay distinct.
    For an anonymous orientation stage, ``orientation_slots`` names the
    reference slots and ``phase`` is their destination-indexed phase vector.
    ``orientation_markers`` gives one phase-distinguishing facet per occupant
    in 54-facelet order. Renderers hide their remaining sticker identities.
    """

    stage_number: int
    observation: tuple[int, ...]
    state: State
    block_roles: tuple[str, ...]
    cell_roles: tuple[str, ...]
    sticker_roles: tuple[str, ...]
    phase: int | tuple[int, ...]
    orientation_independent: bool
    orientation_slots: tuple[int, ...] = ()
    orientation_markers: tuple[int, ...] = ()

    @property
    def current_blocks(self):
        return tuple(i for i, role in enumerate(self.block_roles) if role == "current")


def _method(value):
    method = value if isinstance(value, HumanMethod) else getattr(value, "method", None)
    if not isinstance(method, HumanMethod):
        raise TypeError("recognition diagrams require a HumanMethod or a method-bearing result")
    if method.status != "completed":
        raise ValueError("recognition diagrams require a completed method")
    return method


def _stage(method, number):
    if isinstance(number, bool) or not isinstance(number, int):
        raise TypeError("stage_number must be an integer")
    if not 1 <= number <= len(method.stages):
        raise ValueError("stage_number is outside the method")
    return method.stages[number - 1]


def recognition_block_roles(value, stage_number):
    """Classify physical blocks before this stage, independent of its case.

    Initial guarantees include immobile blocks and blocks forced correct by
    the complete reference-loop group. Implied guarantees from earlier stages
    are included. Only the explicitly recognized stage target is highlighted;
    other blocks an algorithm happens to move do not become recognition cues.
    """
    method = _method(value)
    stage = _stage(method, stage_number)
    if stage.recognition_features and stage.recognition_features != (stage.feature,):
        raise ValueError("recognition block roles do not yet support independent observers")
    features = set(method.initial_features)
    for previous in method.stages[:stage_number - 1]:
        features.add(previous.feature)
        features.update(previous.implied_features)
    solved = {index for feature in features if feature.kind in ("solve_block", "solve_blocks")
              for index in ((_resolve_feature(method.inventory, feature),) if feature.kind == "solve_block"
                            else _resolve_feature(method.inventory, feature))}
    placed = {index for feature in features if feature.kind in ("place_block", "place_blocks")
              for index in ((_resolve_feature(method.inventory, feature),) if feature.kind == "place_block"
                            else _resolve_feature(method.inventory, feature))}
    current = _feature_indices(method.inventory, stage.feature)
    return tuple("current" if i in current else
                 "solved" if i in solved else
                 "placed" if i in placed else "unsolved"
                 for i, block in enumerate(method.inventory.blocks))


def _diagram(method, stage, observation, permutation, roles):
    action = method.inventory.action(permutation)
    orientation_slots = stage.block_index if stage.feature.kind == "orient_slots" else ()
    if orientation_slots:
        roles = tuple("current" if destination in orientation_slots else roles[source]
                      for source, destination in enumerate(action.destinations))
    cells = ["unsolved"] * 27
    for source, destination in enumerate(action.destinations):
        for cell in method.inventory.blocks[destination].cells:
            cells[cell] = roles[source]
    cell_roles = tuple(cells)
    sticker_roles = tuple(cell_roles[cell]
                          for face in "URFDLB" for cell in _FACE_CELLS[face])
    markers = ()
    if orientation_slots:
        faithful_facelets = tuple(index for index in range(54) if index % 9 != 4)
        markers = tuple(sorted(faithful_facelets[permutation[point]]
                               for point in _orientation_marker_points(method.inventory,
                                                                       orientation_slots)))
    return HumanRecognitionDiagram(
        stage.number, observation,
        _state_for_permutation(method.reference_shape, permutation),
        roles, cell_roles, sticker_roles,
        observation if orientation_slots else
        tuple(action.phases[index] for index in _feature_indices(method.inventory, stage.feature))
        if isinstance(stage.block_index, tuple) else action.phases[stage.block_index],
        stage.feature.kind in ("place_block", "place_blocks", "occupy_slots", "place_blocks_up_to_alignment"),
        orientation_slots, markers)


def _orientation_marker_points(inventory, slots):
    """One intrinsic facet whose position distinguishes every cyclic phase.

    The same template facet is transported into each compatible reference
    block. After any action its location depends only on destination and phase,
    so arbitrary occupant permutations never change the recognition picture.
    """
    exemplar = inventory.blocks[slots[0]]
    rotations = _powers(exemplar.positive_rotation, exemplar.orientation_order)
    point = next((point for cell in exemplar.template_cells for point in _CELL_POINTS[cell]
                  if len({_STICKER_IMAGES[rotation][point] for rotation in rotations})
                  == exemplar.orientation_order), None)
    if point is None:
        raise ValueError("orientation footprint has no faithful facet distinguishing its phases")
    return tuple(_STICKER_IMAGES[inventory.blocks[index].frame][point] for index in slots)


def _symbolic_orientation_representatives(method, stage):
    """Explore the target's complete oriented observation orbit only.

    Deduplication uses (destination, phase), rather than full permutations.
    Retaining one permutation path for each observation supplies physical
    pictures while the subgroup can have arbitrarily many elements.
    """
    group = method._symbolic_chain.stages[stage.number - 1].group_before
    identity = tuple(range(48))
    indices = (_feature_indices(method.inventory, stage.feature)
               if stage.feature.kind in ("place_blocks_up_to_alignment", "solve_blocks_up_to_actions") else stage.block_index)
    kind = "solve_blocks" if isinstance(stage.block_index, tuple) else "solve_block"
    solved = _observe(method.inventory.action(identity), indices, kind)
    representatives = {solved: identity}
    queue = deque([identity])
    alphabet = tuple(generator.permutation for generator in group.strong_generators)
    while queue:
        permutation = queue.popleft()
        for generator in alphabet:
            successor = _then(permutation, generator)
            observation = _observe(method.inventory.action(successor), indices, kind)
            if observation not in representatives:
                representatives[observation] = successor
                queue.append(successor)
    return tuple(representatives[observation] for observation in sorted(representatives))


def recognition_stage_diagrams(value, stage_number):
    """Map every exact observation to its tuple of physical case pictures.

    Full-solve and slot-orientation cases need one picture. Placement cases show all target phases
    actually realizable after the earlier stages, so every valid orientation
    is accepted. Variations in unrelated unsolved blocks remain hidden by the
    white stickers and therefore need no extra pictures.
    """
    method = _method(value)
    stage = _stage(method, stage_number)
    if stage.recognition_features and stage.recognition_features != (stage.feature,):
        raise ValueError("independent recognition uses the guide's complete pattern table; "
                         "recognition diagrams do not yet support several observers")
    roles = recognition_block_roles(method, stage_number)
    if stage.feature.kind in ("solve_block", "solve_blocks", "orient_slots"):
        return {case.observation: (_diagram(method, stage, case.observation,
                                           case.representative, roles),)
                for case in stage.cases}

    representatives = {case.observation: {} for case in stage.cases}
    indices = (_feature_indices(method.inventory, stage.feature)
               if stage.feature.kind in ("place_blocks_up_to_alignment", "solve_blocks_up_to_actions") else stage.block_index)
    # Keep the declared example for its phase. Other phases use deterministic
    # physical representatives from the complete, already validated group.
    for case in stage.cases:
        action = method.inventory.action(case.representative)
        phase = (_observe(action, indices, "solve_blocks")
                 if isinstance(stage.block_index, tuple) else action.phases[stage.block_index])
        representatives[case.observation][phase] = case.representative
    earlier = method.stages[:stage_number - 1]
    permutations = (_symbolic_orientation_representatives(method, stage)
                    if method._symbolic_chain is not None else sorted(method._permutations))
    for permutation in permutations:
        action = method.inventory.action(permutation)
        if any(_observe(action, previous.block_index, previous.feature.kind)
               != previous.solved_observation for previous in earlier):
            continue
        observation = _observe(action, stage.block_index, stage.feature.kind)
        # Membership observes the unordered destination region. Distinct
        # internal assignments are additional valid pictures of that case.
        key = (_observe(action, indices, "solve_blocks")
               if isinstance(stage.block_index, tuple) else action.phases[stage.block_index])
        representatives[observation].setdefault(key, permutation)
    return {case.observation: tuple(
                _diagram(method, stage, case.observation, permutation, roles)
                for _, permutation in sorted(representatives[case.observation].items()))
            for case in stage.cases}


def recognition_case_diagrams(value, stage_number, observation):
    """Return all orientation pictures for one exact recognition case."""
    method = _method(value)
    stage = _stage(method, stage_number)
    observation = tuple(observation)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in observation):
        raise TypeError("observation entries must be integers")
    if observation not in stage.observations:
        raise ValueError("observation is not a case in that stage")
    return recognition_stage_diagrams(method, stage_number)[observation]
