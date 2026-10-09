"""Optional matplotlib shape galleries and colored cube nets.

Faces are built from occupied cells, so connected noncuboid blocks are drawn
without filling their bounding boxes. Coplanar seams inside a block are hidden.
"""

from collections import Counter
from collections.abc import Mapping
from math import atan, ceil, degrees, sqrt

from . import Shape, State, shape


# Standard URFDLB facelets in the legacy 27-cell grid. Each face is viewed
# from outside: U has B at the top, D has F, and the side faces have U.
_FACE_CELLS = {
    "U": tuple(row * 3 + col for row in range(3) for col in range(3)),
    "R": tuple(row * 9 + (2 - col) * 3 + 2 for row in range(3) for col in range(3)),
    "F": tuple(row * 9 + 6 + col for row in range(3) for col in range(3)),
    "D": tuple(18 + (2 - row) * 3 + col for row in range(3) for col in range(3)),
    "L": tuple(row * 9 + col * 3 for row in range(3) for col in range(3)),
    "B": tuple(row * 9 + 2 - col for row in range(3) for col in range(3)),
}

_FACE_PLANES = {"U": (2, 1, 3), "R": (0, 1, 3), "F": (1, -1, 0),
                "D": (2, -1, 0), "L": (0, -1, 0), "B": (1, 1, 3)}

# The second camera is the first rotated 180 degrees about the FL--BR
# edge-center axis (1, 1, 0): (x, y, z) -> (y, x, -z). The roll is essential;
# opposing azimuth/elevation alone would rotate about a different axis.
_CORNER_ELEVATION = degrees(atan(1 / sqrt(2)))
_VIEWS = {
    "UFR": (_CORNER_ELEVATION, -45, 0, "UFR"),
    "BLD": (-_CORNER_ELEVATION, 135, 180, "BLD"),
}


def _palette(colors):
    palette = {"U": "#f7f7f7", "R": "#d62828", "F": "#2a9d45",
               "D": "#ffd43b", "L": "#ff8c22", "B": "#2463d4"}
    if colors is not None:
        if not isinstance(colors, Mapping):
            raise TypeError("colors must map face letters to matplotlib colors")
        if set(colors) - set(palette):
            raise ValueError("colors keys must be U, R, F, D, L, or B")
        palette.update(colors)
    return palette


def draw_net(state, *, colors=None, size=2, linewidth=2):
    """Return a matplotlib Figure showing all 54 colored stickers of a State.

    The unfolded net has U above F, L/F/R/B across the middle, and D below F.
    Letters identify sticker colors by their fixed centers. Thin lines divide
    stickers; thick internal lines separate bandage blocks in the current state.
    Face borders outline panels, independently of bandages across folded edges.

    Default colors are U white, R red, F green, D yellow, L orange, B blue.
    Pass a colors mapping keyed by face letters to override any of them.
    """
    if not isinstance(state, State):
        raise TypeError("a colored net requires a State")
    if size <= 0 or linewidth < 0:
        raise ValueError("size must be positive and linewidth nonnegative")
    palette = _palette(colors)
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from matplotlib.patches import Rectangle
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[plots] to draw colored nets") from error
    palette = {letter: to_rgb(color) for letter, color in palette.items()}
    facelets = state.facelets
    labels = state.shape.labels
    positions = {"U": (1, 0), "L": (0, 1), "F": (1, 1),
                 "R": (2, 1), "B": (3, 1), "D": (1, 2)}
    figure, axis = plt.subplots(figsize=(4 * size, 3 * size))
    axis.set_aspect("equal")
    axis.set_axis_off()
    axis.set(xlim=(-0.2, 13.7), ylim=(10.2, -0.6))
    for face_index, face in enumerate("URFDLB"):
        column, row = positions[face]
        x, y = column * 3.5, row * 3.5
        cells = _FACE_CELLS[face]
        axis.text(x + 1.5, y - 0.18, face, ha="center", va="bottom", weight="bold")
        for sticker in range(9):
            r, c = divmod(sticker, 3)
            letter = facelets[face_index * 9 + sticker]
            rgb = palette[letter]
            axis.add_patch(Rectangle((x + c + 0.03, y + r + 0.03), 0.94, 0.94,
                                     facecolor=rgb, edgecolor="#888888", linewidth=0.4))
            luminance = sum(a * b for a, b in zip(rgb, (0.2126, 0.7152, 0.0722)))
            axis.text(x + c + 0.5, y + r + 0.5, letter,
                      ha="center", va="center", color="white" if luminance < 0.45 else "black")
            if c < 2 and labels[cells[sticker]] != labels[cells[sticker + 1]]:
                axis.plot([x + c + 1] * 2, [y + r, y + r + 1],
                          color="black", linewidth=linewidth)
            if r < 2 and labels[cells[sticker]] != labels[cells[sticker + 3]]:
                axis.plot([x + c, x + c + 1], [y + r + 1] * 2,
                          color="black", linewidth=linewidth)
        axis.add_patch(Rectangle((x, y), 3, 3, fill=False, edgecolor="black", linewidth=1))
    figure.tight_layout(pad=0.5)
    return figure


def _block_faces(indices):
    cells = {(index % 3, 2 - (index // 3) % 3, 2 - index // 9)
             for index in indices}
    for cell in sorted(cells):
        for axis in range(3):
            others = [coordinate for coordinate in range(3) if coordinate != axis]
            for direction in (-1, 1):
                neighbor = list(cell)
                neighbor[axis] += direction
                if tuple(neighbor) in cells:
                    continue
                plane = cell[axis] + (direction == 1)
                vertices = []
                for first, second in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    vertex = list(cell)
                    vertex[axis] = plane
                    vertex[others[0]] += first
                    vertex[others[1]] += second
                    vertices.append(tuple(vertex))
                yield (axis, direction, plane), vertices


def _block_mesh(indices, transparent, visible_planes=None, exterior_only=False):
    faces = []
    edges = Counter()
    # Hidden outlines can appear through opaque faces under matplotlib's depth
    # sort. Cull them for the selected camera; the default is the UFR view.
    if visible_planes is None:
        visible_planes = {_FACE_PLANES[face] for face in "UFR"}
    for plane, vertices in _block_faces(indices):
        if exterior_only and plane not in _FACE_PLANES.values():
            continue
        if not transparent and plane not in visible_planes:
            continue
        faces.append(vertices)
        for first, second in zip(vertices, vertices[1:] + vertices[:1]):
            edges[(plane, tuple(sorted((first, second))))] += 1
    outlines = sorted({edge for (_, edge), count in edges.items() if count == 1})
    return faces, outlines


def _sticker_colors(state, palette, overrides=None, rotation=None):
    """Color each exterior cell face without changing its block geometry."""
    from .block_actions import _CELL_IMAGES, _NORMALS, _rotate

    facelets = state.facelets
    result = {}
    for face_index, face in enumerate("URFDLB"):
        displayed_face = face
        if rotation is not None:
            normal = _rotate(rotation, _NORMALS[face])
            displayed_face = next(name for name, vector in _NORMALS.items() if vector == normal)
        axis, _, plane = _FACE_PLANES[displayed_face]
        for sticker, cell in enumerate(_FACE_CELLS[face]):
            index = 9 * face_index + sticker
            if rotation is not None:
                cell = _CELL_IMAGES[rotation][cell]
            result[(axis, plane, cell)] = (palette[facelets[index]] if overrides is None else overrides[index])
    return result


def _mesh_color(vertices, stickers, default):
    for axis in range(3):
        plane = vertices[0][axis]
        if all(vertex[axis] == plane for vertex in vertices):
            coords = [min(2, int(sum(vertex[i] for vertex in vertices) / 4))
                      for i in range(3)]
            cell = (2 - coords[2]) * 9 + (2 - coords[1]) * 3 + coords[0]
            return stickers.get((axis, plane, cell), default)
    raise ValueError("mesh face must lie in a coordinate plane")


def draw_cubes(cubes, *, alpha=1, color=(1, 1, 1), colors=False, size=4,
               linewidth=2, ncol=3, views=None, sticker_colors=None, exterior_only=False,
               rotation=""):
    """Return a matplotlib Figure containing one shape or a gallery.

    Use matplotlib.pyplot.show() for a script, or display the returned figure
    in a notebook. alpha < 1 reveals internal block faces. Set colors=True to
    display State sticker colors, or pass a palette mapping keyed by URFDLB.
    Shape-only inputs cannot supply colors. The default retains uncolored shapes.

    Omit views for the original angled camera. Otherwise views selects UFR,
    BLD, or both, with one projection per puzzle/view pair.
    These orthographic cameras look exactly down the respective corner diagonal.
    BLD is UFR rotated a half-turn about the FL--BR edge-center axis, including
    camera roll. Both views together expose every sticker. ncol limits panels
    per row; color supplies the body color and internal faces for transparency.

    sticker_colors overrides individual URFDLB facelets: pass 54 matplotlib
    colors for one State, or one 54-color sequence per State for a gallery.
    It enables colored drawing. exterior_only=True omits internal block faces,
    keeping transparent recognition pictures legible without interior surfaces.

    rotation is a whole-cube x/y/z word describing the pictured starting grip.
    Geometry and physical sticker colors rotate together; face labels identify
    local execution faces. The original Shape or State is never changed.
    """
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must lie between zero and one")
    if isinstance(ncol, bool) or not isinstance(ncol, int) or ncol <= 0:
        raise ValueError("ncol must be a positive integer")
    if size <= 0 or linewidth < 0:
        raise ValueError("size must be positive and linewidth nonnegative")
    if type(exterior_only) is not bool:
        raise TypeError("exterior_only must be a boolean")
    from .block_actions import _CELL_IMAGES
    from .loop_rotations import rotation_tuple
    display_rotation = rotation_tuple(rotation)
    corner_views = views is not None
    if views is None:
        views = ("UFR",)
    elif isinstance(views, str):
        views = (views,)
    else:
        views = tuple(views)
    if not views or any(view not in _VIEWS for view in views):
        raise ValueError("views must contain UFR and/or BLD")
    colored = (colors is not False and colors is not None) or sticker_colors is not None
    if colors is not False and colors is not None and colors is not True and not isinstance(colors, Mapping):
        raise TypeError("colors must be True, False, or a palette mapping")
    palette = _palette(colors if isinstance(colors, Mapping) else None) if colored else None
    if isinstance(cubes, (Shape, State)):
        values = [cubes]
    else:
        values = list(cubes)
        if values and isinstance(values[0], int):
            values = [shape(values)]
        else:
            values = [value if isinstance(value, State) else shape(value) for value in values]
    if not values:
        raise ValueError("a gallery requires at least one shape")
    if colored and any(not isinstance(value, State) for value in values):
        raise TypeError("colored drawing requires State inputs")
    overrides = None
    if sticker_colors is not None:
        overrides = ((tuple(sticker_colors),) if len(values) == 1 else
                     tuple(tuple(row) for row in sticker_colors))
        if len(overrides) != len(values) or any(len(row) != 54 for row in overrides):
            raise ValueError("sticker_colors needs 54 colors for each State")
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[plots] to draw shapes") from error
    if colored:
        palette = {letter: to_rgb(value) for letter, value in palette.items()}
    if overrides is not None:
        overrides = tuple(tuple(to_rgb(color) for color in row) for row in overrides)
    panels = [(value, view, value_index) for value_index, value in enumerate(values) for view in views]
    columns = min(ncol, len(panels))
    rows = ceil(len(panels) / columns)
    figure = plt.figure(figsize=(columns * size, rows * size))
    for index, (value, view, value_index) in enumerate(panels):
        axis = figure.add_subplot(rows, columns, index + 1, projection="3d")
        axis.set_axis_off()
        axis.set(xlim=(0, 3), ylim=(0, 3), zlim=(0, 3))
        axis.set_box_aspect((1, 1, 1))
        elevation, azimuth, roll, visible_faces = _VIEWS[view]
        if corner_views:
            axis.view_init(elev=elevation, azim=azimuth, roll=roll)
            axis.set_proj_type("ortho")
        else:
            axis.view_init(elev=25, azim=-55)
        visible_planes = {_FACE_PLANES[face] for face in visible_faces}
        source_labels = shape(value).labels
        labels = [None] * 27
        for source, destination in enumerate(_CELL_IMAGES[display_rotation]):
            labels[destination] = source_labels[source]
        current_overrides = None if overrides is None else overrides[value_index]
        stickers = _sticker_colors(value, palette, current_overrides, display_rotation) if colored else None
        for block in sorted(set(labels)):
            faces, lines = _block_mesh(
                [cell for cell, label in enumerate(labels) if label == block],
                alpha < 1, visible_planes, exterior_only)
            if faces:
                surface = Poly3DCollection(
                    faces, facecolors=[_mesh_color(face, stickers, color) for face in faces]
                    if colored else color, alpha=alpha,
                    edgecolors="#aaaaaa" if colored else "none",
                    linewidths=0.4 if colored else 0)
                surface.set_gid(f"cube-{index}-block-{block}-surface")
                axis.add_collection3d(surface)
            if lines:
                outline = Line3DCollection(lines, colors="black", linewidths=linewidth, alpha=alpha)
                outline.set_gid(f"cube-{index}-block-{block}-outline")
                axis.add_collection3d(outline)
        if colored:
            for face in visible_faces:
                coordinate, direction, plane = _FACE_PLANES[face]
                position = [1.5] * 3
                position[coordinate] = plane + direction * 0.01
                rgb = stickers[(coordinate, plane, _FACE_CELLS[face][4])]
                luminance = sum(a * b for a, b in zip(rgb, (0.2126, 0.7152, 0.0722)))
                axis.text(*position, face, ha="center", va="center",
                          color="white" if luminance < 0.45 else "black", zorder=10000)
    figure.subplots_adjust(wspace=0, hspace=0)
    return figure
