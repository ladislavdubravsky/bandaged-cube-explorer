"""Opposite-corner cube pictures of certified action-family recognition cases.

Rendering uses the case's explicit observation masks, never incidental sticker
colors in its representative. Small colored squares identify pieces whose
orientations are irrelevant; full stickers describe required poses or the
reference stickers used to read orientation. Plotting remains optional.
"""

import base64
from io import BytesIO
from textwrap import fill

from .graphics import _FACE_CELLS, _FACE_PLANES, _block_mesh, _palette, draw_cubes


_VIEWS = ("UFR", "BLD")
_OBSERVED_GREY = (0.70, 0.72, 0.75)
_SOLVED_GREY = (0.43, 0.46, 0.49)
_CONTEXT = (0.96, 0.97, 0.98)
_INSET_SIDE = 0.48
_REGION_COLORS = ("#1368aa", "#703ca4", "#a64b08")


def _facelet_cell(index):
    face, sticker = divmod(index, 9)
    return _FACE_CELLS["URFDLB"[face]][sticker]


def _sticker_square(index, side=1.0, lift=0.006):
    """Four vertices on an exterior sticker, with a centered optional inset."""
    face = "URFDLB"[index // 9]
    cell = _facelet_cell(index)
    coordinate, direction, plane = _FACE_PLANES[face]
    others = tuple(axis for axis in range(3) if axis != coordinate)
    origin = (cell % 3, 2 - cell // 3 % 3, 2 - cell // 9)
    margin = (1.0 - side) / 2
    vertices = []
    for first, second in ((0, 0), (1, 0), (1, 1), (0, 1)):
        point = list(origin)
        point[coordinate] = plane + direction * lift
        point[others[0]] += margin + side * first
        point[others[1]] += margin + side * second
        vertices.append(tuple(point))
    return tuple(vertices)


def _source_cells(variant, inventory):
    action = inventory.action(variant.state)
    return {source: tuple(inventory.blocks[destination].cells)
            for source, destination in enumerate(action.destinations)}


def _observed_sources(variant, inventory, cells):
    """Find orientation-only occupants without exposing their identities."""
    sources = set(variant.full_blocks) | set(variant.location_blocks)
    sources.update(source for source, _ in variant.piece_labels)
    observed_cells = {_facelet_cell(index) for index in variant.reference_stickers}
    observed_cells.update(cell for slot, _ in variant.slot_labels
                          for cell in inventory.blocks[slot].cells)
    sources.update(source for source, occupied in cells.items()
                   if observed_cells.intersection(occupied))
    return sources


def _variant_colors(variant, inventory, *, face_colors=None):
    """Base colors in current URFDLB order; location insets are separate."""
    from matplotlib.colors import to_rgb

    palette = {face: to_rgb(color) for face, color in _palette(face_colors).items()}
    cells = _source_cells(variant, inventory)
    observed = _observed_sources(variant, inventory, cells)
    source_at = {cell: source for source, occupied in cells.items() for cell in occupied}
    full = set(variant.full_blocks)
    reference = set(variant.reference_stickers)
    solved = set(variant.solved_blocks)
    return tuple(palette[face] if index % 9 == 4 or source_at[_facelet_cell(index)] in full
                 or index in reference else
                 _OBSERVED_GREY if source_at[_facelet_cell(index)] in observed else
                 _SOLVED_GREY if source_at[_facelet_cell(index)] in solved else _CONTEXT
                 for index, face in enumerate(variant.state.facelets))


def _overlays(axis, variant, inventory, visible, prefix, *, face_colors=None):
    """Cull every overlay to its panel before drawing it above the block mesh."""
    from matplotlib.colors import to_rgb
    from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

    class StickerPolygons(Poly3DCollection):
        def do_3d_projection(self):
            super().do_3d_projection()
            # Visible faces are already culled. A fused block's mesh is sorted
            # as one collection, so depth alone can hide its own decorations.
            return -1e6

    class StickerLines(Line3DCollection):
        def do_3d_projection(self):
            super().do_3d_projection()
            return -1e6 - 1

    palette = {face: to_rgb(color) for face, color in _palette(face_colors).items()}
    source_at = {cell: source for source, occupied in _source_cells(variant, inventory).items()
                 for cell in occupied}
    location = set(variant.location_blocks) - set(variant.full_blocks)
    reference = set(variant.reference_stickers)
    indices = tuple(index for index in range(54)
                    if "URFDLB"[index // 9] in visible and index % 9 != 4
                    and source_at[_facelet_cell(index)] in location and index not in reference)
    if indices:
        squares = StickerPolygons([_sticker_square(index, _INSET_SIDE) for index in indices],
            facecolors=[palette[variant.state.facelets[index]] for index in indices],
            edgecolors="#51585f", linewidths=.45, antialiaseds=True)
        squares.set_gid(prefix + "-location-insets")
        squares.stage_facelet_indices = indices
        axis.add_collection3d(squares)

    borders = []
    border_indices = tuple(index for index in reference if "URFDLB"[index // 9] in visible)
    for index in border_indices:
        square = _sticker_square(index, .92, .009)
        borders.extend((first, second) for first, second in zip(square, square[1:] + square[:1]))
    if borders:
        lines = StickerLines(borders, colors="#303740", linewidths=.8)
        lines.set_gid(prefix + "-reference-sticker-borders")
        lines.stage_facelet_indices = border_indices
        axis.add_collection3d(lines)

    # The standard white is slightly off-white. Mark both that color and pure
    # white, distinguishing physical white stickers from neutral context.
    white = {face for face, color in palette.items()
             if max(color) - min(color) < .01 and min(color) >= .94}
    full = set(variant.full_blocks)
    white_indices = tuple(index for index in range(54)
        if "URFDLB"[index // 9] in visible and variant.state.facelets[index] in white
        and (index in indices or index in reference or index % 9 == 4
             or source_at[_facelet_cell(index)] in full))
    stripes = []
    for index in white_indices:
        side = _INSET_SIDE if index in indices else .90
        square = _sticker_square(index, side, .012)
        origin, first, _, second = square
        first_vector = tuple(value - base for value, base in zip(first, origin))
        second_vector = tuple(value - base for value, base in zip(second, origin))
        for offset in (-.75, -.50, -.25, 0., .25, .50, .75):
            ends = ((max(0., -offset), max(0., offset)),
                    (min(1., 1. - offset), min(1., 1. + offset)))
            stripes.append(tuple(tuple(origin[axis] + a * first_vector[axis] + b * second_vector[axis]
                                       for axis in range(3)) for a, b in ends))
    if stripes:
        lines = StickerLines(stripes, colors="#505050", linewidths=.35, alpha=.8)
        lines.set_gid(prefix + "-white-sticker-stripes")
        lines.stage_facelet_indices = white_indices
        axis.add_collection3d(lines)

    for number, region in enumerate(variant.regions):
        _, outlines = _block_mesh(region, False,
            {_FACE_PLANES[face] for face in visible}, exterior_only=True)
        if outlines:
            lines = StickerLines(outlines, colors=_REGION_COLORS[number % len(_REGION_COLORS)],
                                 linewidths=2.5, linestyles="dashed")
            lines.set_gid(prefix + f"-region-{number + 1}")
            axis.add_collection3d(lines)


def _labels(axis, variant, inventory, colors, visible):
    """Label pieces, slots and reference readings without an orientation table."""
    cells = _source_cells(variant, inventory)
    action = inventory.action(variant.state)
    by_source = {source: [str(name)] for source, name in variant.piece_labels}
    for slot, name in variant.slot_labels:
        source = action.destinations.index(slot)
        if str(name) not in by_source.setdefault(source, []):
            by_source[source].append(str(name))
    reference = set(variant.reference_stickers)
    orientation_labels = dict(getattr(variant, "orientation_labels", ()))
    labelled_readings = set()
    for source, labels in by_source.items():
        candidates = tuple(index for index in range(54)
                           if "URFDLB"[index // 9] in visible
                           and index % 9 != 4 and _facelet_cell(index) in cells[source])
        if not candidates:
            continue
        # Put the piece name by its reference sticker when that sticker is
        # visible. This disambiguates equally colored orientation stickers.
        index = next((index for index in candidates if index in reference), candidates[0])
        if index in orientation_labels:
            labels = [*labels[:-1], labels[-1] + ": " + orientation_labels[index]]
            labelled_readings.add(index)
        square = _sticker_square(index, .9, .022)
        point = tuple(sum(vertex[coordinate] for vertex in square) / 4 for coordinate in range(3))
        axis.text(*point, "\n".join(labels), ha="center", va="center", fontsize=6.9,
                  color="#20252b", zorder=1e7,
                  bbox=dict(boxstyle="round,pad=0.14", facecolor="white", alpha=.76,
                            edgecolor="none"))
    for index, reading in orientation_labels.items():
        if index in labelled_readings or "URFDLB"[index // 9] not in visible:
            continue
        square = _sticker_square(index, .9, .022)
        point = tuple(sum(vertex[coordinate] for vertex in square) / 4 for coordinate in range(3))
        axis.text(*point, reading, ha="center", va="center", fontsize=7.5,
                  color="#20252b", zorder=1e7,
                  bbox=dict(boxstyle="round,pad=0.14", facecolor="white", alpha=.76,
                            edgecolor="none"))


def stage_case_figure(case, inventory, *, face_colors=None):
    """Render all explicitly equivalent variants in two 3D views each.

    The model supplies complete recognition semantics and certified examples.
    This renderer never searches, adds recognition cues or changes algorithms.
    face_colors overrides the physical URFDLB palette consistently across
    stickers, identification squares, centers and white-sticker hatching.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[plots] to draw recognition cases") from error
    variants = tuple(case.variants)
    if not variants:
        raise ValueError("a recognition case needs at least one physical variant")
    colors = tuple(_variant_colors(variant, inventory, face_colors=face_colors)
                   for variant in variants)
    figure = None
    existing_figures = set(plt.get_fignums())
    try:
        figure = draw_cubes([variant.state for variant in variants],
            sticker_colors=colors[0] if len(variants) == 1 else colors,
            exterior_only=True, views=_VIEWS, ncol=2, size=3.1, linewidth=1.5)
        for panel, axis in enumerate(figure.axes):
            number, view_number = divmod(panel, 2)
            variant, visible = variants[number], _VIEWS[view_number]
            for collection in axis.collections:
                if collection.get_gid().endswith("-surface"):
                    collection.set_edgecolor("none")
                    collection.set_linewidth(0)
                    collection.set_antialiased(False)
            prefix = f"stage-{case.stage_number}-variant-{number + 1}-view-{visible}"
            _overlays(axis, variant, inventory, visible, prefix, face_colors=face_colors)
            _labels(axis, variant, inventory, colors[number], visible)
            title = visible if len(variants) == 1 else f"Equivalent arrangement {number + 1} · {visible}"
            axis.set_title(title, fontsize=9.5, pad=0)
        caption = fill(str(case.cue).replace("`", ""), width=86)
        heading_margin = .45 + .18 * caption.count("\n")
        figure.set_size_inches(6.2, 3.1 * len(variants) + heading_margin + .04)
        height = figure.get_size_inches()[1]
        # Inches, rather than a figure-height fraction, keep the heading clear
        # of the first row's titles when equivalent arrangements add rows.
        figure.suptitle(caption, fontsize=10.5, y=1 - .04 / height)
        figure.subplots_adjust(top=1 - heading_margin / height,
                               bottom=.04 / height,
                               left=.015, right=.985, wspace=.015, hspace=.16)
        return figure
    except BaseException:
        if figure is not None:
            plt.close(figure)
        else:
            # draw_cubes can fail after it allocates the figure. Close only
            # newly created figures, preserving the notebook's earlier plots.
            for number in set(plt.get_fignums()) - existing_figures:
                plt.close(number)
        raise


def stage_case_image(case, inventory, *, face_colors=None):
    """Portable inline PNG, releasing its figure even when encoding fails."""
    figure = stage_case_figure(case, inventory, face_colors=face_colors)
    import matplotlib.pyplot as plt
    try:
        with BytesIO() as output:
            figure.savefig(output, format="png", dpi=120, bbox_inches="tight", pad_inches=.04)
            return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    finally:
        plt.close(figure)
