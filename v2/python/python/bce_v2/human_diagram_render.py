"""Cube pictures for the guaranteed recognition features of a human method."""

import base64
from collections.abc import Mapping
from io import BytesIO

from .graphics import _block_mesh, _mesh_color, _palette, _sticker_colors, draw_cubes
from .human_diagram_modes import DiagramMode
from .human_diagrams import HumanRecognitionDiagram


DIAGRAM_MODES = tuple(DiagramMode)
_SOLVED_COLOR = (0.5, 0.5, 0.5)  # RGB: 0 = black; 1 = white.
_WHITE = (1.0, 1.0, 1.0)


def validate_diagram_mode(mode):
    try:
        return DiagramMode(mode)
    except (TypeError, ValueError):
        raise ValueError("diagram_mode must be DiagramMode.TRANSPARENT or "
                         "DiagramMode.OPPOSITE_CORNERS") from None


def validate_face_colors(face_colors=None):
    """Normalize optional URFDLB palette overrides to a complete RGB mapping.

    The standard cube palette is white, red, green, yellow, orange, and blue.
    A partial mapping changes only those faces, using any Matplotlib color.
    These colors affect presentation only; face letters keep their identity.
    """
    if face_colors is not None:
        if not isinstance(face_colors, Mapping):
            raise TypeError("face_colors must map U, R, F, D, L, or B to Matplotlib colors")
        if set(face_colors) - set("URFDLB"):
            raise ValueError("face_colors keys must be U, R, F, D, L, or B")
    try:
        from matplotlib.colors import to_rgb
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[plots] to draw recognition diagrams") from error
    palette = _palette(face_colors)
    result = {}
    for face, color in palette.items():
        try:
            result[face] = to_rgb(color)
        except (TypeError, ValueError) as error:
            raise ValueError(f"face_colors[{face!r}] must be a valid Matplotlib color") from error
    return result


def recognition_diagram_colors(diagram, *, face_colors=None,
                               diagram_mode: DiagramMode = DiagramMode.OPPOSITE_CORNERS):
    """Return each physical sticker's role color in 54-facelet URFDLB order.

    Solved blocks use dark grey. Face centers and current targets retain
    their full physical sticker colors. Other blocks stay white,
    including correctly placed blocks whose orientation is still unsolved.
    """
    if not isinstance(diagram, HumanRecognitionDiagram):
        raise TypeError("diagram must be a HumanRecognitionDiagram")
    validate_diagram_mode(diagram_mode)
    palette = validate_face_colors(face_colors)
    return tuple(palette[face] if index % 9 == 4 or role == "current" else
                 _SOLVED_COLOR if role == "solved" else _WHITE
                 for index, (face, role) in enumerate(zip(
                     diagram.state.facelets, diagram.sticker_roles)))


def _transparent_sticker_opacities(diagram):
    """Keep centers at full color and solved blocks at their dark grey shade."""
    return tuple(1.0 if index % 9 == 4 or role == "solved" else
                 0.95 if role == "current" else 0.06
                 for index, role in enumerate(diagram.sticker_roles))


def _style_transparent_axis(axis, diagram, panel_index, colors, rotation):
    """Give exterior sticker faces independent alpha within fused blocks."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from .block_actions import _CELL_IMAGES
    from .loop_rotations import rotation_tuple

    display_rotation = rotation_tuple(rotation)
    labels = [None] * 27
    for source, destination in enumerate(_CELL_IMAGES[display_rotation]):
        labels[destination] = diagram.state.shape.labels[source]
    faces_by_block = {label: _block_mesh(
        [cell for cell, block in enumerate(labels) if block == label],
        True, exterior_only=True)[0] for label in set(labels)}
    colors_by_face = _sticker_colors(diagram.state, None, colors, display_rotation)
    opacities = _sticker_colors(diagram.state, None,
                               _transparent_sticker_opacities(diagram), display_rotation)
    roles = {f"cube-{panel_index}-block-{label}": diagram.cell_roles[cell]
             for cell, label in enumerate(diagram.state.shape.labels)}
    for collection in axis.collections:
        prefix = collection.get_gid().rsplit("-", 1)[0]
        if isinstance(collection, Poly3DCollection):
            block = int(prefix.rsplit("-", 1)[1])
            faces = faces_by_block[block]
            rgba = [(*_mesh_color(face, colors_by_face, _WHITE),
                     _mesh_color(face, opacities, 0.06)) for face in faces]
            collection.set_alpha(None)
            collection.set_facecolor(rgba)
        else:
            collection.set_alpha(0.95 if roles[prefix] == "current" else 0.2)
    for label in axis.texts:
        label.set_color("#20242a")


def recognition_diagram_figure(diagrams, *, diagram_mode: DiagramMode = DiagramMode.OPPOSITE_CORNERS,
                               face_colors=None, rotation=""):
    """Draw one case, grouping all orientation variants under its instruction.

    Transparent mode looks along the UFR diagonal, retaining grey solved
    blocks, colored current targets and fully opaque face centers;
    other stickers are faint white.
    Interior block surfaces are omitted to preserve their color contrast.
    Opposite-corner mode gives opaque orthographic UFR and BLD views.
    rotation changes the pictured starting grip, keeping physical sticker
    hues and block roles while face labels name turns in the pictured frame.
    """
    diagram_mode = validate_diagram_mode(diagram_mode)
    diagrams = ((diagrams,) if isinstance(diagrams, HumanRecognitionDiagram) else tuple(diagrams))
    if not diagrams or any(not isinstance(d, HumanRecognitionDiagram) for d in diagrams):
        raise TypeError("a recognition picture needs one or more case diagrams")
    if len({(d.stage_number, d.observation) for d in diagrams}) != 1:
        raise ValueError("a recognition picture must contain one case")
    palette = validate_face_colors(face_colors)
    transparent = diagram_mode is DiagramMode.TRANSPARENT
    views = ("UFR",) if transparent else ("UFR", "BLD")
    overrides = tuple(recognition_diagram_colors(d, face_colors=palette,
                                                diagram_mode=diagram_mode) for d in diagrams)
    figure = draw_cubes([d.state for d in diagrams],
        sticker_colors=overrides[0] if len(diagrams) == 1 else overrides,
        alpha=0.48 if transparent else 1, exterior_only=True,
        views=views, size=3.0, linewidth=1.6,
        ncol=min(3, len(diagrams)) if transparent else 2, rotation=rotation)
    for index, axis in enumerate(figure.axes):
        if transparent:
            _style_transparent_axis(axis, diagrams[index], index, overrides[index], rotation)
        # Separate outlines already trace each fused block's boundary. The
        # individual sticker polygons must not add grid lines inside it.
        for collection in axis.collections:
            if collection.get_gid().endswith("-surface"):
                collection.set_edgecolor("none")
                collection.set_linewidth(0)
                collection.set_antialiased(False)
        label = views[index % len(views)]
        if len(diagrams) > 1:
            label = f"Orientation {index // len(views) + 1} · {label}"
        axis.set_title(label, fontsize=10, pad=0)
    columns = min(3, len(diagrams)) if transparent else 2
    rows = (len(figure.axes) + columns - 1) // columns
    if rows > 1:
        # Cube galleries otherwise have no row gap. Leave room for each next
        # orientation's title while retaining the size of the cube pictures.
        width, height = figure.get_size_inches()
        figure.set_size_inches(width, height + 0.6 * (rows - 1))
        figure.subplots_adjust(hspace=0.2)
    from .human_diagram_stripes import add_white_sticker_stripes
    add_white_sticker_stripes(figure, diagrams, palette, rotation=rotation, transparent=transparent)
    return figure


def recognition_diagram_image(diagrams, *, diagram_mode: DiagramMode = DiagramMode.OPPOSITE_CORNERS,
                              face_colors=None, rotation=""):
    """Return a standalone inline PNG and close its matplotlib figure."""
    figure = recognition_diagram_figure(diagrams, diagram_mode=diagram_mode,
                                        face_colors=face_colors, rotation=rotation)
    import matplotlib.pyplot as plt
    try:
        with BytesIO() as output:
            figure.savefig(output, format="png", dpi=110, bbox_inches="tight", pad_inches=0.04)
            return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    finally:
        plt.close(figure)
