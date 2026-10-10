"""Exact reference-block actions and source-decorated cycle notation.

Rotations are signed axis tuples: (a, b, c) maps v to
(sign(a)*v[abs(a)-1], sign(b)*v[abs(b)-1], sign(c)*v[abs(c)-1]).
The coordinate frame is x=R, y=B, z=U, as in the Rust engine.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import json
from pathlib import Path

from . import CELL_NAMES, Shape, State, shape
from .signatures import classify_blocks


_IDENTITY = (1, 2, 3)
_SUFFIXES = {1: ("",), 2: ("", "+"), 3: ("", "+", "-"),
             4: ("", "+", "++", "-")}
# Same stable order as engine::symmetry::Rotation.
_AXES = ((0, 1, 2), (1, 2, 0), (2, 0, 1),
         (0, 2, 1), (2, 1, 0), (1, 0, 2))
_ROTATIONS = tuple(
    tuple((axis + 1) * sign for axis, sign in zip(axes, (a, b, parity * a * b)))
    for p, axes in enumerate(_AXES)
    for parity in (1 if p < 3 else -1,)
    for a, b in ((1, 1), (-1, 1), (1, -1), (-1, -1))
)


def _rotate(rotation, vector):
    return tuple((1 if axis > 0 else -1) * vector[abs(axis) - 1]
                 for axis in rotation)


def _compose_axes(left, right):
    """Ordinary composition: right is applied first."""
    return tuple((1 if axis > 0 else -1) * right[abs(axis) - 1]
                 for axis in left)


_COMPOSITIONS = {(left, right): _compose_axes(left, right)
                 for left in _ROTATIONS for right in _ROTATIONS}
_INVERSES = {rotation: next(candidate for candidate in _ROTATIONS
                           if _COMPOSITIONS[candidate, rotation] == _IDENTITY)
             for rotation in _ROTATIONS}


def _compose(left, right):
    """Ordinary composition: right is applied first."""
    return _COMPOSITIONS[left, right]


def _inverse(rotation):
    return _INVERSES[rotation]


def _coordinates(cell):
    return (cell % 3 - 1, 1 - cell // 3 % 3, 1 - cell // 9)


def _cell_at(vector):
    x, y, z = vector
    return (1 - z) * 9 + (1 - y) * 3 + x + 1


_CELL_IMAGES = {r: tuple(_cell_at(_rotate(r, _coordinates(c))) for c in range(27))
                for r in _ROTATIONS}
_NORMALS = dict(U=(0, 0, 1), R=(1, 0, 0), F=(0, -1, 0),
                D=(0, 0, -1), L=(-1, 0, 0), B=(0, 1, 0))
_CORNER_CELLS = (8, 6, 0, 2, 26, 24, 18, 20)
_EDGE_CELLS = (5, 7, 3, 1, 23, 25, 21, 19, 17, 15, 9, 11)
_CORNER_FACES = ("URF", "UFL", "ULB", "UBR", "DFR", "DLF", "DBL", "DRB")
_EDGE_FACES = ("UR", "UF", "UL", "UB", "DR", "DF", "DL", "DB", "FR", "FL", "BL", "BR")
_CORNER_FACELETS = ((8, 9, 20), (6, 18, 38), (0, 36, 47), (2, 45, 11),
                    (29, 26, 15), (27, 44, 24), (33, 53, 42), (35, 17, 51))
_EDGE_FACELETS = ((5, 10), (7, 19), (3, 37), (1, 46), (32, 16), (28, 25),
                  (30, 43), (34, 52), (23, 12), (21, 41), (50, 39), (48, 14))
_ORDERED_FACES = dict(zip(_CORNER_CELLS + _EDGE_CELLS, _CORNER_FACES + _EDGE_FACES))


def _compact(facelet):
    return facelet // 9 * 8 + facelet % 9 - int(facelet % 9 > 4)


_POINTS = {}
for _cells, _faces, _facelets in ((_CORNER_CELLS, _CORNER_FACES, _CORNER_FACELETS),
                                  (_EDGE_CELLS, _EDGE_FACES, _EDGE_FACELETS)):
    for _cell, _letters, _indices in zip(_cells, _faces, _facelets):
        for _face, _index in zip(_letters, _indices):
            _POINTS[_compact(_index)] = (_cell, _NORMALS[_face])
_POINTS = tuple(_POINTS[i] for i in range(48))
_POINT_INDEX = {point: index for index, point in enumerate(_POINTS)}
_STICKER_IMAGES = {
    r: tuple(_POINT_INDEX[_CELL_IMAGES[r][cell], _rotate(r, normal)]
             for cell, normal in _POINTS) for r in _ROTATIONS
}
_STICKER_ROTATIONS = {(point, image): rotation
                      for rotation, images in _STICKER_IMAGES.items()
                      for point, image in enumerate(images)}
_CELL_POINTS = tuple(tuple(i for i, (cell, _) in enumerate(_POINTS) if cell == c)
                     for c in range(27))


def cell_name(value):
    """Canonical cell name; equivalent face orders such as FLD become DFL."""
    if isinstance(value, str):
        names = {frozenset(name): name for name in CELL_NAMES}
        if len(set(value)) == len(value) and frozenset(value) in names:
            return names[frozenset(value)]
        raise ValueError(f"unknown cell name {value!r}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("cell must be an integer index or face-letter name")
    if not 0 <= value < 27:
        raise ValueError("cell index must be in 0..26")
    return CELL_NAMES[value]


def _footprint(rotation, cells):
    return tuple(sorted(_CELL_IMAGES[rotation][cell] for cell in cells))


@lru_cache(maxsize=96)
def _powers(generator, order):
    result = [_IDENTITY]
    for _ in range(1, order):
        result.append(_compose(generator, result[-1]))
    return tuple(result)


def _positive(template, stabilizer):
    order = len(stabilizer)
    if order == 1:
        return _IDENTITY
    if len(template) == 1 and template[0] in _ORDERED_FACES:
        normals = tuple(_NORMALS[f] for f in _ORDERED_FACES[template[0]])
        return next(r for r in stabilizer
                    if all(_rotate(r, normal) == normals[(i + 1) % order]
                           for i, normal in enumerate(normals)))
    # A face-contained footprint has nonzero centroid, so its stabilizer is
    # cyclic. Positive means clockwise as seen from outside along that axis.
    centroid = tuple(sum(_coordinates(cell)[axis] for cell in template)
                     for axis in range(3))
    for r in stabilizer:
        powers = _powers(r, order)
        if len(set(powers)) != order or _compose(r, powers[-1]) != _IDENTITY:
            continue
        if order == 2:
            return r
        for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            w = _rotate(r, v)
            cross = (v[1]*w[2] - v[2]*w[1], v[2]*w[0] - v[0]*w[2],
                     v[0]*w[1] - v[1]*w[0])
            turn = sum(a*b for a, b in zip(centroid, cross))
            if turn < 0:
                return r
            if turn > 0:
                break
    raise ValueError("block footprint has no cyclic orientation frame")


@dataclass(frozen=True)
class BlockSlot:
    """A reference footprint and physical identity, independent of labels."""

    cells: tuple[int, ...]
    name: str
    compact_name: str
    kind: str
    type: str | None
    dimensions: tuple[int, int, int] | None
    corners: int
    edges: int
    centers: int
    cores: int
    core_hole: bool
    movable: bool
    template_cells: tuple[int, ...]
    frame: tuple[int, int, int]
    positive_rotation: tuple[int, int, int]
    orientation_order: int

    @property
    def cubies(self):
        return len(self.cells)

    def to_dict(self):
        # Normalize tuples to arrays even when called outside json.dumps.
        return json.loads(json.dumps(asdict(self)))


@dataclass(frozen=True, init=False)
class BlockInventory:
    """Fixed frames for physical blocks at a loop library's reference shape.

    State inputs use their specification. Loop sets and analyses use their
    actual root_shape, including nonzero roots. No hull completion is applied.
    """

    root_shape: Shape
    blocks: tuple[BlockSlot, ...]
    _action_cache: dict = field(repr=False, compare=False)
    _slots: dict = field(repr=False, compare=False)
    _block_points: tuple = field(repr=False, compare=False)

    def __init__(self, reference=None):
        if hasattr(reference, "loops"):
            reference = reference.loops
        if hasattr(reference, "root_shape"):
            reference = reference.root_shape
        if isinstance(reference, State):
            reference = reference.specification
        reference = Shape() if reference is None else shape(reference)
        labels = reference.labels
        groups = {}
        for cell, label in enumerate(labels):
            groups.setdefault(label, []).append(cell)
        blocks = []
        for members in groups.values():
            cells = tuple(members)
            if cells == (13,):
                continue
            # Classify each physical block independently, preserving a shell
            # core hole and any real bonds to the core, even in mixed inputs.
            isolated = [0] * 27
            for cell in cells:
                isolated[cell] = 1
            try:
                metadata = next(b for b in classify_blocks(isolated, core_bonds=13 in cells)
                                if b.cells == cells)
            except ValueError:
                metadata = None
            counts = Counter(sum(c != 0 for c in _coordinates(cell)) for cell in cells)
            kind = ({3: "Corner", 2: "Edge", 1: "Center", 0: "Core"}[next(iter(counts))]
                    if len(cells) == 1 else metadata.type if metadata else "Block")
            compact = "-".join(cell_name(cell) for cell in cells)
            movable = any(all(sum(a*b for a, b in zip(_coordinates(cell), normal)) == 1
                              for cell in cells) for normal in _NORMALS.values())
            observable = bool(counts[3] or counts[2])
            template = min(_footprint(r, cells) for r in _ROTATIONS)
            frames = [r for r in _ROTATIONS if _footprint(r, template) == cells]
            if len(cells) == 1 and cells[0] in _ORDERED_FACES:
                source_faces = _ORDERED_FACES[template[0]]
                target_faces = _ORDERED_FACES[cells[0]]
                frames = [r for r in frames if all(_rotate(r, _NORMALS[a]) == _NORMALS[b]
                                                   for a, b in zip(source_faces, target_faces))]
            stabilizer = (tuple(r for r in _ROTATIONS if _footprint(r, template) == template)
                          if movable and observable else (_IDENTITY,))
            positive = _positive(template, stabilizer)
            blocks.append(BlockSlot(
                cells=cells, name=f"{kind} {compact}", compact_name=compact,
                kind=kind, type=metadata.type if metadata else None,
                dimensions=metadata.dimensions if metadata else None,
                corners=counts[3], edges=counts[2], centers=counts[1], cores=counts[0],
                core_hole=metadata.core_hole if metadata else False, movable=movable,
                template_cells=template, frame=frames[0], positive_rotation=positive,
                orientation_order=len(stabilizer),
            ))
        object.__setattr__(self, "root_shape", reference)
        object.__setattr__(self, "blocks", tuple(blocks))
        object.__setattr__(self, "_action_cache", {})
        object.__setattr__(self, "_slots", {block.cells: index for index, block in enumerate(blocks)})
        object.__setattr__(self, "_block_points", tuple(
            tuple(point for cell in block.cells for point in _CELL_POINTS[cell]) for block in blocks))

    def action(self, permutation):
        """Validate a faithful sticker action returning to this partition.

        Accept a 48-image permutation or State. This checks exact block
        rigidity and the outer-face model; it does not prove reachability.
        Off-root states must have their shape restored before this call.
        """
        if isinstance(permutation, State):
            if permutation.specification != self.root_shape:
                raise ValueError("state specification differs from the reference root")
            permutation = permutation.sticker_permutation
        permutation = tuple(permutation)
        if any(isinstance(p, bool) or not isinstance(p, int) for p in permutation):
            raise TypeError("sticker images must be integers")
        if len(permutation) != 48 or set(permutation) != set(range(48)):
            raise ValueError("sticker images must permute 0 through 47")
        if permutation in self._action_cache:
            return self._action_cache[permutation]
        destinations, rotations = [], []
        slots = self._slots
        for block, points in zip(self.blocks, self._block_points):
            cell_images = {}
            for cell in block.cells:
                targets = {_POINTS[permutation[p]][0] for p in _CELL_POINTS[cell]}
                if len(targets) > 1:
                    raise ValueError("sticker action splits a constituent cubie")
                cell_images[cell] = next(iter(targets)) if targets else cell
            footprint = tuple(sorted(cell_images.values()))
            if footprint not in slots:
                raise ValueError("sticker action does not preserve the reference partition; restore its shape")
            destination = slots[footprint]
            if not points:
                rotation = None  # Unmarked center spin/core orientation is invisible.
            else:
                rotation = _STICKER_ROTATIONS.get((points[0], permutation[points[0]]))
                if (rotation is None or
                        not all(_CELL_IMAGES[rotation][cell] == target
                                for cell, target in cell_images.items()) or
                        not all(_STICKER_IMAGES[rotation][point] == permutation[point]
                                for point in points)):
                    raise ValueError("sticker action violates rigid block orientation")
                if not block.movable and (destination != len(destinations) or rotation != _IDENTITY):
                    raise ValueError("a block outside every outer face is permanently immobile")
            destinations.append(destination)
            rotations.append(rotation)
        if sorted(destinations) != list(range(len(self.blocks))):
            raise ValueError("sticker action does not permute reference blocks")
        result = self._from_transitions(tuple(destinations), tuple(rotations))
        # Keep this compilation-local cache bounded even when callers traverse
        # a large explicit group. Invalid actions are never entered.
        if len(self._action_cache) >= 4096:
            self._action_cache.pop(next(iter(self._action_cache)))
        self._action_cache[permutation] = result
        return result

    def _from_transitions(self, destinations, rotations):
        phases = []
        for i, (destination, rotation) in enumerate(zip(destinations, rotations)):
            source, target = self.blocks[i], self.blocks[destination]
            if source.template_cells != target.template_cells:
                raise ValueError("action transports incompatible block footprints")
            if rotation is None:
                phases.append(0)
                continue
            local = _compose(_inverse(target.frame), _compose(rotation, source.frame))
            powers = _powers(source.positive_rotation, source.orientation_order)
            if local not in powers:
                raise ValueError("block rotation is outside its observable orientation frame")
            phases.append(powers.index(local))
        return BlockAction._create(self, destinations, rotations, tuple(phases))

    def identity(self):
        return self.action(range(48))

    def to_dict(self):
        return {"format": "bce-v2-block-inventory", "version": 1,
                "root_shape": self.root_shape.labels,
                "rotation_coordinates": "x=R,y=B,z=U",
                "rotation_encoding": "signed-output-axes",
                "blocks": [block.to_dict() for block in self.blocks]}

    def to_json(self, path=None):
        return _json_export(self.to_dict(), path)


@dataclass(frozen=True, init=False)
class BlockAction:
    """Exact rigid transitions, indexed by source reference block.

    Construct through inventory.action(). Phases use the inventory's fixed
    template-to-slot frames. The faithful permutation is reconstructed from
    the records, rather than retained as a separate potentially stale cache.
    """

    inventory: BlockInventory
    destinations: tuple[int, ...]
    rotations: tuple[tuple[int, int, int] | None, ...]
    phases: tuple[int, ...]

    def __init__(self):
        raise TypeError("construct block actions with BlockInventory.action()")

    @classmethod
    def _create(cls, inventory, destinations, rotations, phases):
        result = object.__new__(cls)
        for name, value in (("inventory", inventory), ("destinations", destinations),
                            ("rotations", rotations), ("phases", phases)):
            object.__setattr__(result, name, value)
        return result

    def to_permutation(self):
        """Reconstruct all 48 source-to-destination sticker images exactly."""
        result = list(range(48))
        for block, rotation in zip(self.inventory.blocks, self.rotations):
            if rotation is not None:
                for cell in block.cells:
                    for point in _CELL_POINTS[cell]:
                        result[point] = _STICKER_IMAGES[rotation][point]
        return tuple(result)

    @property
    def permutation(self):
        return self.to_permutation()

    def then(self, next_action):
        """Execute this action, then next_action; transport source phases."""
        if not isinstance(next_action, BlockAction):
            raise TypeError("composition requires a BlockAction")
        if self.inventory != next_action.inventory:
            raise ValueError("block actions have different reference inventories")
        destinations = tuple(next_action.destinations[d] for d in self.destinations)
        rotations = tuple(None if r is None else _compose(next_action.rotations[d], r)
                          for d, r in zip(self.destinations, self.rotations))
        return self.inventory._from_transitions(destinations, rotations)

    def inverse(self):
        destinations = [0] * len(self.destinations)
        rotations = [None] * len(destinations)
        for i, (d, r) in enumerate(zip(self.destinations, self.rotations)):
            destinations[d] = i
            rotations[d] = None if r is None else _inverse(r)
        return self.inventory._from_transitions(tuple(destinations), tuple(rotations))

    def __pow__(self, exponent):
        if isinstance(exponent, bool) or not isinstance(exponent, int):
            raise TypeError("action power must be an integer")
        base = self.inverse() if exponent < 0 else self
        exponent = abs(exponent)
        result = self.inventory.identity()
        while exponent:
            if exponent & 1:
                result = result.then(base)
            exponent >>= 1
            if exponent:
                base = base.then(base)
        return result

    @property
    def notation(self):
        """Deterministic disjoint cycles with a phase on each source entry."""
        seen, cycles = set(), []
        for start in range(len(self.inventory.blocks)):
            if start in seen:
                continue
            cycle, current = [], start
            while current not in seen:
                seen.add(current)
                source = self.inventory.blocks[current]
                name = source.compact_name
                if len(source.cells) > 1:
                    name = f"[{name}]"
                phase = self.phases[current]
                suffix = _SUFFIXES[source.orientation_order][phase]
                cycle.append(name + suffix)
                current = self.destinations[current]
            if len(cycle) > 1 or self.phases[start]:
                cycles.append("(" + " ".join(cycle) + ")")
        return "".join(cycles) or "()"

    def __str__(self):
        return self.notation

    def to_dict(self):
        return {"format": "bce-v2-block-action", "version": 1,
                "root_shape": self.inventory.root_shape.labels,
                "indexing": "source-reference-block", "composition": "execution-order",
                "notation": self.notation,
                "transitions": [
                    {"source": list(source.cells), "destination": list(self.inventory.blocks[d].cells),
                     "rotation": list(r) if r is not None else None,
                     "phase": q, "orientation_order": source.orientation_order}
                    for source, d, r, q in zip(self.inventory.blocks, self.destinations,
                                              self.rotations, self.phases)]}

    def to_json(self, path=None):
        return _json_export(self.to_dict(), path)


def _json_export(record, path):
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def block_inventory(reference=None):
    """Build deterministic physical block identities and orientation frames."""
    return BlockInventory(reference)
