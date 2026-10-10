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
from .graphics import _FACE_CELLS
from .human_methods import HumanMethod, _observe, _state_for_permutation, _then


@dataclass(frozen=True)
class HumanRecognitionDiagram:
    """One physical orientation pictured for a recognition case.

    ``block_roles`` follows physical reference-block identities;
    ``cell_roles`` follows their current cells; ``sticker_roles`` follows the
    54 URFDLB facelets. The renderer chooses how to show these guarantees
    for each diagram mode. Placed and other unsolved blocks share white
    stickers while their semantic roles stay distinct.
    """

    stage_number: int
    observation: tuple[int, ...]
    state: State
    block_roles: tuple[str, ...]
    cell_roles: tuple[str, ...]
    sticker_roles: tuple[str, ...]
    phase: int
    orientation_independent: bool

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
    features = set(method.initial_features)
    for previous in method.stages[:stage_number - 1]:
        features.add(previous.feature)
        features.update(previous.implied_features)
    solved = {feature.cells for feature in features if feature.kind == "solve_block"}
    placed = {feature.cells for feature in features if feature.kind == "place_block"}
    return tuple("current" if i == stage.block_index else
                 "solved" if block.cells in solved else
                 "placed" if block.cells in placed else "unsolved"
                 for i, block in enumerate(method.inventory.blocks))


def _diagram(method, stage, observation, permutation, roles):
    action = method.inventory.action(permutation)
    cells = ["unsolved"] * 27
    for source, destination in enumerate(action.destinations):
        for cell in method.inventory.blocks[destination].cells:
            cells[cell] = roles[source]
    cell_roles = tuple(cells)
    sticker_roles = tuple(cell_roles[cell]
                          for face in "URFDLB" for cell in _FACE_CELLS[face])
    return HumanRecognitionDiagram(
        stage.number, observation,
        _state_for_permutation(method.reference_shape, permutation),
        roles, cell_roles, sticker_roles, action.phases[stage.block_index],
        stage.feature.kind == "place_block")


def _symbolic_orientation_representatives(method, stage):
    """Explore the target's complete oriented observation orbit only.

    Deduplication uses (destination, phase), rather than full permutations.
    Retaining one permutation path for each observation supplies physical
    pictures while the subgroup can have arbitrarily many elements.
    """
    group = method._symbolic_chain.stages[stage.number - 1].group_before
    identity = tuple(range(48))
    solved = _observe(method.inventory.action(identity), stage.block_index, "solve_block")
    representatives = {solved: identity}
    queue = deque([identity])
    alphabet = tuple(generator.permutation for generator in group.strong_generators)
    while queue:
        permutation = queue.popleft()
        for generator in alphabet:
            successor = _then(permutation, generator)
            observation = _observe(method.inventory.action(successor), stage.block_index, "solve_block")
            if observation not in representatives:
                representatives[observation] = successor
                queue.append(successor)
    return tuple(representatives[observation] for observation in sorted(representatives))


def recognition_stage_diagrams(value, stage_number):
    """Map every exact observation to its tuple of physical case pictures.

    Full-solve cases need one picture. Placement cases show all target phases
    actually realizable after the earlier stages, so every valid orientation
    is accepted. Variations in unrelated unsolved blocks remain hidden by the
    white stickers and therefore need no extra pictures.
    """
    method = _method(value)
    stage = _stage(method, stage_number)
    roles = recognition_block_roles(method, stage_number)
    if stage.feature.kind == "solve_block":
        return {case.observation: (_diagram(method, stage, case.observation,
                                           case.representative, roles),)
                for case in stage.cases}

    representatives = {case.observation: {} for case in stage.cases}
    # Keep the declared example for its phase. Other phases use deterministic
    # physical representatives from the complete, already validated group.
    for case in stage.cases:
        phase = method.inventory.action(case.representative).phases[stage.block_index]
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
        representatives[observation].setdefault(action.phases[stage.block_index], permutation)
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
