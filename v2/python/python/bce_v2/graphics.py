"""Optional matplotlib galleries of exact block footprints.

Faces are built from occupied cells, so connected noncuboid blocks are drawn
without filling their bounding boxes. Coplanar seams inside a block are hidden.
"""

from collections import Counter
from math import ceil

from . import Shape, State, shape


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


def _block_mesh(indices, transparent):
    faces = []
    edges = Counter()
    # The fixed camera sees right, front, and up. Rear/bottom outline artists
    # can otherwise appear through opaque faces under matplotlib's depth sort.
    visible_planes = {(0, 1, 3), (1, -1, 0), (2, 1, 3)}
    for plane, vertices in _block_faces(indices):
        if not transparent and plane not in visible_planes:
            continue
        faces.append(vertices)
        for first, second in zip(vertices, vertices[1:] + vertices[:1]):
            edges[(plane, tuple(sorted((first, second))))] += 1
    outlines = sorted({edge for (_, edge), count in edges.items() if count == 1})
    return faces, outlines


def draw_cubes(cubes, *, alpha=1, color=(1, 1, 1), size=4,
               linewidth=2, ncol=3):
    """Return a matplotlib Figure containing one shape or a gallery.

    Use matplotlib.pyplot.show() for a script, or display the returned figure
    in a notebook. alpha < 1 reveals internal block faces. State inputs show
    their uncolored bandage shape; this gallery does not render stickers.
    """
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must lie between zero and one")
    if isinstance(ncol, bool) or not isinstance(ncol, int) or ncol <= 0:
        raise ValueError("ncol must be a positive integer")
    if size <= 0 or linewidth < 0:
        raise ValueError("size must be positive and linewidth nonnegative")
    if isinstance(cubes, (Shape, State)):
        values = [shape(cubes)]
    else:
        values = list(cubes)
        if values and isinstance(values[0], int):
            values = [shape(values)]
        else:
            values = [shape(value) for value in values]
    if not values:
        raise ValueError("a gallery requires at least one shape")
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[plots] to draw shapes") from error
    columns = min(ncol, len(values))
    rows = ceil(len(values) / columns)
    figure = plt.figure(figsize=(columns * size, rows * size))
    for index, value in enumerate(values):
        axis = figure.add_subplot(rows, columns, index + 1, projection="3d")
        axis.set_axis_off()
        axis.set(xlim=(0, 3), ylim=(0, 3), zlim=(0, 3))
        axis.set_box_aspect((1, 1, 1))
        axis.view_init(elev=25, azim=-55)
        labels = value.labels
        for block in sorted(set(labels)):
            faces, lines = _block_mesh(
                [cell for cell, label in enumerate(labels) if label == block], alpha < 1)
            if faces:
                axis.add_collection3d(Poly3DCollection(
                    faces, facecolors=color, alpha=alpha, linewidths=0))
            if lines:
                axis.add_collection3d(Line3DCollection(
                    lines, colors="black", linewidths=linewidth, alpha=alpha))
    figure.subplots_adjust(wspace=0, hspace=0)
    return figure
