"""Geometry-led anchor proposals for a preservation-derived workspace.

A free face suggests keeping its layer available while anchoring a region
on the opposite face. Components closest to that opposite face's axis are
jointly proposed before peripheral components. This is a structural entry
heuristic, not a coverage theorem or a hardcoded method for a cubie class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType

from .assembly_goals import _bound, _cells, _indices, _inventory
from .block_actions import _CELL_POINTS, _NORMALS, _coordinates
from .human_chains import BlockFeature


def _on_face(cell, normal):
    return sum(value * axis for value, axis in zip(_coordinates(cell), normal)) == 1


def _axis_distance(block, normal):
    distances = []
    for cell in block.cells:
        coordinates = _coordinates(cell)
        axial = sum(value * axis for value, axis in zip(coordinates, normal))
        distances.append(sum(value * value for value in coordinates) - axial * axial)
    return Fraction(sum(distances), len(distances))


@dataclass(frozen=True)
class WorkspaceAnchorEvidence:
    """One geometric reason for proposing a complete joint anchor."""

    feature: BlockFeature
    free_face: str
    opposite_face: str
    block_indices: tuple[int, ...]
    opposite_component_indices: tuple[int, ...]
    mean_squared_axis_distance: Fraction

    def to_dict(self):
        distance = self.mean_squared_axis_distance
        return {"feature": self.feature.to_dict(), "free_face": self.free_face,
                "opposite_face": self.opposite_face, "block_indices": list(self.block_indices),
                "opposite_component_indices": list(self.opposite_component_indices),
                "mean_squared_axis_distance": {"numerator": distance.numerator,
                                               "denominator": distance.denominator},
                "coverage_claim": False}


@dataclass(frozen=True)
class WorkspaceAnchorProposals:
    """Immutable bounded proposals and the physical geometry behind them."""

    features: tuple[BlockFeature, ...]
    evidence: tuple[WorkspaceAnchorEvidence, ...]
    metadata: object = field(repr=False)

    def to_dict(self):
        metadata = dict(self.metadata)
        metadata["domain_block_indices"] = list(metadata["domain_block_indices"])
        metadata["free_faces"] = list(metadata["free_faces"])
        metadata["oversized_ties"] = [list(value) for value in metadata["oversized_ties"]]
        return {"format": "bce-v2-workspace-anchor-proposals", "version": 1,
                "features": [feature.to_dict() for feature in self.features],
                "evidence": [evidence.to_dict() for evidence in self.evidence],
                "metadata": metadata, "coverage_claim": False}


def propose_workspace_anchors(inventory, domain_cells, *, max_candidates=12, max_components=6):
    """Suggest axis-near anchors opposite faces left free by the workspace.

    ``domain_cells`` is a union of whole physical components. Only marked,
    movable components wholly inside an opposite face can be selected. The
    entire set tied at minimum mean squared distance is retained together;
    an oversized tie is skipped and reported. No component is split, and
    no inactive center is introduced to manufacture a smaller anchor.
    """
    inventory = _inventory(inventory)
    domain_cells = _cells(domain_cells, "domain_cells")
    domain_indices = _indices(inventory, domain_cells)
    max_candidates = _bound(max_candidates, "max_candidates")
    max_components = _bound(max_components, "max_components", minimum=1)
    free_faces = tuple(face for face, normal in _NORMALS.items()
                       if not any(_on_face(cell, normal) for cell in domain_cells))
    proposed, evidence, oversized = [], [], []
    for free_face in free_faces:
        normal = _NORMALS[free_face]
        opposite_face = next(face for face, other in _NORMALS.items()
                             if other == tuple(-axis for axis in normal))
        opposite_normal = _NORMALS[opposite_face]
        opposite = tuple(index for index in domain_indices
                         if inventory.blocks[index].movable and
                         any(_CELL_POINTS[cell] for cell in inventory.blocks[index].cells) and
                         all(_on_face(cell, opposite_normal) for cell in inventory.blocks[index].cells))
        if not opposite:
            continue
        distances = {index: _axis_distance(inventory.blocks[index], opposite_normal) for index in opposite}
        minimum = min(distances.values())
        members = tuple(index for index in opposite if distances[index] == minimum)
        if len(members) > max_components:
            oversized.append((free_face, len(members)))
            continue
        cells = tuple(cell for index in members for cell in inventory.blocks[index].cells)
        feature = BlockFeature("solve_blocks", cells)
        if feature not in proposed:
            proposed.append(feature)
        evidence.append(WorkspaceAnchorEvidence(feature, free_face, opposite_face, members, opposite, minimum))
    features = tuple(proposed[:max_candidates])
    retained = tuple(item for item in evidence if item.feature in features)
    metadata = MappingProxyType({"domain_block_indices": domain_indices, "free_faces": free_faces,
                                "max_candidates": max_candidates, "max_components": max_components,
                                "candidates_bounded": len(proposed) > max_candidates,
                                "oversized_ties": tuple(oversized), "coverage_claim": False,
                                "heuristic": "minimum_mean_squared_distance_to_opposite_face_axis"})
    return WorkspaceAnchorProposals(features, retained, metadata)
