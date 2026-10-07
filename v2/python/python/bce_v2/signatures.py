"""Block inventories for connected cuboids, optionally omitting the virtual core.

Dimensions are sorted longest first. Position variants with different center
or core content have distinct names, even when their dimensions agree.
"""

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import prod

from . import shape


@dataclass(frozen=True)
class BlockType:
    code: str
    dimensions: tuple[int, int, int]
    name: str
    description: str
    centers: int | None = None
    core_position: bool | None = None

    @property
    def volume(self):
        """Volume of the bounding box, including a possible omitted core."""
        return prod(self.dimensions)


BLOCK_TYPES = tuple(sorted((
    BlockType("333", (3, 3, 3), "Fused cube", "The whole cube shell", 6, True),
    BlockType("332", (3, 3, 2), "Two layers", "Two full layers fused together", 5, True),
    BlockType("331", (3, 3, 1), "Full layer", "An outer layer with one face center", 1, False),
    BlockType("331Core", (3, 3, 1), "331Core", "A middle layer with four face centers", 4, True),
    BlockType("322", (3, 2, 2), "BigBlock", "A 3×2×2 bounding box", 4, True),
    BlockType("321", (3, 2, 1), "321", "An outer 3×2×1 rectangle", 1, False),
    BlockType("321Core", (3, 2, 1), "321Core", "A middle 3×2×1 box with three face centers", 3, True),
    BlockType("311", (3, 1, 1), "311", "A straight bar without a face center", 0, False),
    BlockType("BigClock", (3, 1, 1), "BigClock", "A 311 bar through one face center", 1, False),
    BlockType("311Core", (3, 1, 1), "311Core", "Opposite face centers joined through the core", 2, True),
    BlockType("222", (2, 2, 2), "222", "A 2×2×2 bounding box", 3, True),
    BlockType("221", (2, 2, 1), "221", "An outer 2×2×1 rectangle", 1, False),
    BlockType("221Core", (2, 2, 1), "221Core", "A middle 2×2×1 box with two face centers", 2, True),
    BlockType("Clock", (2, 1, 1), "Clock", "A 211 block containing a face center", 1, False),
    BlockType("Pair", (2, 1, 1), "Pair", "A 211 block without a face center", 0, False),
    BlockType("211Core", (2, 1, 1), "211Core", "A face center joined to the core", 1, True),
    BlockType("111", (1, 1, 1), "Singleton", "One unfused physical cubie"),
), key=lambda block: (-block.volume, tuple(-d for d in block.dimensions), block.code)))
_TYPES = {block.code: block for block in BLOCK_TYPES}
_TYPE_BY_GEOMETRY = {(block.dimensions, block.centers, block.core_position): block.code
                     for block in BLOCK_TYPES if block.volume > 1}
SINGLETON_TYPES = tuple(block.code for block in BLOCK_TYPES if block.volume == 1)


@dataclass(frozen=True)
class Block:
    """One physical block, retaining geometry beyond its coarse type."""

    label: int
    type: str
    dimensions: tuple[int, int, int]
    cells: tuple[int, ...]
    corners: int
    edges: int
    centers: int
    cores: int
    core_hole: bool

    @property
    def cubies(self):
        return len(self.cells)


def classify_blocks(value, *, core_bonds=False):
    """Return blocks of a cuboid partition as immutable records.

    The default ignores an independent ghost core and accepts connected boxes
    with that core omitted. Full 27-cell cuboids require core_bonds=True.
    Noncuboid blocks are rejected rather than assigned their bounding-box type.
    """
    if not isinstance(core_bonds, bool):
        raise TypeError("core_bonds must be a bool")
    labels = shape(value).labels
    if not core_bonds and labels.count(labels[13]) != 1:
        raise ValueError("shell signatures require an independent virtual core")
    groups = {}
    for cell, label in enumerate(labels):
        if cell != 13 or core_bonds:
            groups.setdefault(label, []).append(cell)
    result = []
    for label, cells in groups.items():
        coordinates = [tuple((cell // stride) % 3 for stride in (9, 3, 1))
                       for cell in cells]
        ranges = [range(min(point[axis] for point in coordinates),
                        max(point[axis] for point in coordinates) + 1)
                  for axis in range(3)]
        box = {d * 9 + f * 3 + r for d, f, r in product(*ranges)}
        core_position = 13 in box
        core_hole = not core_bonds and core_position
        if not core_bonds:
            box.discard(13)
        if box != set(cells):
            raise ValueError(f"block {label} is not a cuboid footprint")
        dimensions = tuple(sorted(map(len, ranges), reverse=True))
        exposed = Counter(sum(coordinate != 1 for coordinate in point)
                          for point in coordinates)
        centers = exposed[1]
        if len(cells) == 1:
            code = "111"
        else:
            code = _TYPE_BY_GEOMETRY[dimensions, centers, core_position]
        result.append(Block(label, code, dimensions, tuple(cells),
                            exposed[3], exposed[2], centers, int(13 in cells), core_hole))
    return tuple(result)


def block_signature(value, *, include_singletons=False, core_bonds=False):
    """Count each block type; omit implied 111 blocks unless requested.

    These are the actual blocks of the supplied specification. To describe
    behavioral atlas classes, supply their implicitly closed representative.
    """
    if not isinstance(include_singletons, bool):
        raise TypeError("include_singletons must be a bool")
    counts = Counter(block.type for block in classify_blocks(value, core_bonds=core_bonds))
    return {block.code: counts[block.code] for block in BLOCK_TYPES
            if counts[block.code] and (include_singletons or block.volume > 1)}


def format_signature(counts, *, include_singletons=False):
    """Format counts largest first, e.g. '2x221 Clock 2xPair'.

    Size means bounding-box volume, with dimensions breaking ties. Numeric
    names distinguish center/core variants. An empty nonsingleton inventory
    displays as '111 only'.
    """
    if not isinstance(include_singletons, bool):
        raise TypeError("include_singletons must be a bool")
    for code, count in counts.items():
        if code not in _TYPES:
            raise ValueError(f"unknown block type {code!r}; use a variant name from BLOCK_TYPES")
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("block counts must be nonnegative integers")
        if count < 0:
            raise ValueError("block counts must be nonnegative integers")
    parts = []
    for block in BLOCK_TYPES:
        count = counts.get(block.code, 0)
        if count and (include_singletons or block.volume > 1):
            parts.append(block.code if count == 1 else f"{count}x{block.code}")
    return " ".join(parts) or "111 only"
