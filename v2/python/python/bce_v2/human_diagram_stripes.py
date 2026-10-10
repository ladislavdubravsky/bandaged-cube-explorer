"""Small exterior overlays distinguish white stickers from hidden information."""

from collections import defaultdict

from .block_actions import _CELL_IMAGES, _NORMALS, _rotate
from .graphics import _FACE_CELLS, _FACE_PLANES, _palette
from .human_diagrams import HumanRecognitionDiagram
from .loop_rotations import rotation_tuple


def add_white_sticker_stripes(figure, diagrams, face_colors=None, *, rotation="",
                             transparent=False):
    """Hatch only visible colored stickers whose selected face color is white.

    Each unit sticker receives ten thin diagonal black stripes from edge to
    edge. Only targets and face centers retain their physical colors;
    grey solved stickers and plain white unfinished stickers remain unmarked.
    This overlays the existing mesh without changing its faces or block seams.
    """
    from matplotlib.colors import to_rgb
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    class StickerStripes(Line3DCollection):
        def do_3d_projection(self):
            super().do_3d_projection()
            # Matplotlib depth-sorts entire collections. A block's nearest
            # edge can therefore hide markings on its own more distant face.
            # Visible opaque faces are already culled, so draw this small
            # sticker decoration after the mesh while keeping its projection.
            return -1e6

    diagrams = ((diagrams,) if isinstance(diagrams, HumanRecognitionDiagram)
                else tuple(diagrams))
    white_faces = {face for face, color in _palette(face_colors).items()
                   if to_rgb(color) == (1.0, 1.0, 1.0)}
    if not white_faces:
        return
    stripe_ends = []
    for index in range(10):
        offset = (index - 4.5) / 5
        # Clip y = x + offset to the unit sticker square.
        first = (max(0., -offset), max(0., offset))
        second = (min(1., 1. - offset), min(1., 1. + offset))
        stripe_ends.append((first, second))
    display_rotation = rotation_tuple(rotation)
    destination_normals = {face: _rotate(display_rotation, normal)
                           for face, normal in _NORMALS.items()}
    face_for_normal = {normal: face for face, normal in _NORMALS.items()}
    views_per_diagram = 1 if transparent else 2
    for panel, axis in enumerate(figure.axes):
        diagram = diagrams[panel // views_per_diagram]
        visible_faces = None if transparent else ("UFR" if panel % 2 == 0 else "BLD")
        groups = defaultdict(list)
        for face_index, face in enumerate("URFDLB"):
            displayed_face = face_for_normal[destination_normals[face]]
            if visible_faces is not None and displayed_face not in visible_faces:
                continue
            coordinate, direction, plane = _FACE_PLANES[displayed_face]
            others = [index for index in range(3) if index != coordinate]
            for sticker, source_cell in enumerate(_FACE_CELLS[face]):
                index = face_index * 9 + sticker
                if diagram.state.facelets[index] not in white_faces:
                    continue
                role = diagram.sticker_roles[index]
                if sticker == 4:
                    category, opacity = "center", 1.
                elif role == "current":
                    category, opacity = "current", .95 if transparent else 1.
                else:
                    continue
                cell = _CELL_IMAGES[display_rotation][source_cell]
                origin = (cell % 3, 2 - cell // 3 % 3, 2 - cell // 9)
                for ends in stripe_ends:
                    segment = []
                    for first, second in ends:
                        point = list(origin)
                        point[coordinate] = plane + direction * .004
                        point[others[0]] += first
                        point[others[1]] += second
                        segment.append(tuple(point))
                    groups[category, opacity].append(segment)
        for (category, opacity), segments in groups.items():
            stripes = StickerStripes(segments, colors="black", linewidths=.35,
                                      alpha=opacity)
            stripes.set_gid(f"cube-{panel}-white-sticker-stripes-{category}")
            axis.add_collection3d(stripes)
