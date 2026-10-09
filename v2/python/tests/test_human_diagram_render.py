"""Recognition pictures preserve physical colors and show complete case coverage."""

import base64
from collections import Counter
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bce_v2 as c
from bce_v2.human_diagrams import recognition_stage_diagrams
from bce_v2.human_diagram_render import (
    recognition_diagram_colors, recognition_diagram_figure, recognition_diagram_image,
    validate_diagram_mode, validate_face_colors,
)


RESULTS = Path(__file__).resolve().parents[2] / "research-results"
POCKET_RECORD = Path("/tmp/bandaged-pocket-cube-repertoire.json")
HAS_PLOTS = importlib.util.find_spec("matplotlib") is not None


@unittest.skipUnless(HAS_PLOTS, "optional plots extra")
class HumanDiagramRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use("Agg")
        with patch("subprocess.run", side_effect=AssertionError("portable pictures need no GAP")):
            cls.execution = c.load_human_repertoire(RESULTS / "alcatraz-execution-repertoire.json")
            cls.recognition = c.load_human_repertoire(RESULTS / "alcatraz-recognition-repertoire.json")
            cls.pocket = (c.load_human_repertoire(POCKET_RECORD) if POCKET_RECORD.exists()
                          else cls.execution)
            cls.pictures = recognition_stage_diagrams(cls.pocket, 1)
            cls.diagram = next(iter(cls.pictures.values()))[0]

    def tearDown(self):
        import matplotlib.pyplot as plt
        plt.close("all")

    def face_colors(self, axis):
        """Collect rendered sticker fills without depending on depth sort order."""
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        return [tuple(color[:3]) for collection in axis.collections
                if isinstance(collection, Poly3DCollection)
                for color in collection.get_facecolor()]

    def test_palette_hues_follow_physical_stickers_with_light_solved_and_white_unfinished(self):
        from matplotlib.colors import to_rgb
        from bce_v2.graphics import _palette
        from bce_v2.human_diagram_render import _SOLVED_WHITE_BLEND, _WHITE
        normal = {face: to_rgb(color) for face, color in _palette(None).items()}
        light = {face: tuple(part * (1 - _SOLVED_WHITE_BLEND) + _SOLVED_WHITE_BLEND
                            for part in color) for face, color in normal.items()}
        shifted_color = False
        seen_roles = set()
        for repertoire in (self.execution, self.recognition, self.pocket):
            for stage in repertoire.method.stages:
                for variants in recognition_stage_diagrams(repertoire, stage.number).values():
                    for diagram in variants:
                        colors = recognition_diagram_colors(diagram)
                        self.assertEqual(len(colors), 54)
                        for index, (role, face, color) in enumerate(zip(
                                diagram.sticker_roles, diagram.state.facelets, colors)):
                            seen_roles.add(role)
                            expected = (light[face] if role == "solved" else
                                        normal[face] if role == "current" else _WHITE)
                            self.assertEqual(color, expected)
                            shifted_color |= role == "current" and face != "URFDLB"[index // 9]
        self.assertEqual(seen_roles, {"solved", "current", "placed", "unsolved"})
        self.assertTrue(shifted_color, "the test must include a moved sticker color")
        luminance = lambda rgb: sum(a * b for a, b in zip(rgb, (0.2126, 0.7152, 0.0722)))
        for face in "RFLB":
            self.assertGreater(luminance(light[face]), luminance(normal[face]) + .25)
        self.assertEqual(normal["U"], to_rgb("#f7f7f7"))

    def test_custom_face_palette_changes_only_displayed_physical_sticker_colors(self):
        from matplotlib.colors import to_rgb
        from bce_v2.human_diagram_render import _SOLVED_WHITE_BLEND
        custom = {"U": "purple", "R": (0.12, 0.34, 0.56), "F": "cyan",
                  "D": "pink", "L": "navy", "B": "#13ad6b"}
        palette = validate_face_colors(custom)
        self.assertEqual(palette, {face: to_rgb(color) for face, color in custom.items()})
        diagram = next(diagram for repertoire in (self.pocket, self.recognition)
                       for stage in repertoire.method.stages
                       for variants in recognition_stage_diagrams(repertoire, stage.number).values()
                       for diagram in variants
                       if any(role == "current" and face != "URFDLB"[index // 9]
                              for index, (face, role) in enumerate(zip(
                                  diagram.state.facelets, diagram.sticker_roles))))
        original = (diagram.state, diagram.cell_roles, diagram.sticker_roles)
        colors = recognition_diagram_colors(diagram, face_colors=custom)
        for face, role, color in zip(diagram.state.facelets, diagram.sticker_roles, colors):
            if role == "current":
                self.assertEqual(color, palette[face])
            elif role == "solved":
                self.assertTrue(all(part >= _SOLVED_WHITE_BLEND for part in color))
                for component, original_component in zip(color, palette[face]):
                    self.assertAlmostEqual(component, _SOLVED_WHITE_BLEND +
                                           (1 - _SOLVED_WHITE_BLEND) * original_component)
            else:
                self.assertEqual(color, (1., 1., 1.))
        for mode in ("transparent", "opposite-corners"):
            figure = recognition_diagram_figure(diagram, diagram_mode=mode, face_colors=custom)
            rendered = [color for axis in figure.axes for color in self.face_colors(axis)]
            expected = recognition_diagram_colors(diagram, face_colors=custom, diagram_mode=mode)
            self.assertEqual(Counter(rendered), Counter(expected))
            image = recognition_diagram_image(diagram, diagram_mode=mode, face_colors=custom)
            self.assertTrue(base64.b64decode(image.split(",", 1)[1]).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual((diagram.state, diagram.cell_roles, diagram.sticker_roles), original)
        self.assertEqual(custom["U"], "purple", "normalization must not mutate the caller's mapping")
        partial = validate_face_colors({"U": "purple"})
        self.assertEqual(partial["U"], to_rgb("purple"))
        self.assertEqual(partial["R"], validate_face_colors()["R"])

    def test_diagram_mode_enum_lists_choices_and_preserves_string_compatibility(self):
        self.assertEqual(list(c.DiagramMode), [c.DiagramMode.TRANSPARENT,
                                             c.DiagramMode.OPPOSITE_CORNERS])
        for mode in c.DiagramMode:
            self.assertIs(validate_diagram_mode(mode), mode)
            self.assertIs(validate_diagram_mode(mode.value), mode)
            figure = recognition_diagram_figure(self.diagram, diagram_mode=mode)
            self.assertEqual(len(figure.axes), 1 if mode is c.DiagramMode.TRANSPARENT else 2)
        for mode in ([], {}, 1, "net"):
            with self.assertRaisesRegex(ValueError, "DiagramMode.TRANSPARENT"):
                validate_diagram_mode(mode)

    def test_all_starting_grips_preserve_sticker_geometry_hues_and_local_execution_faces(self):
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgb
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        from bce_v2.graphics import _FACE_CELLS
        from bce_v2.loop_rotations import _CANONICAL_WORDS, rotate_moves, rotation_tuple

        class RecordedFaces(Poly3DCollection):
            def __init__(self, vertices, *args, **kwargs):
                self.recorded_vertices = vertices
                self.recorded_colors = kwargs.get("facecolors")
                super().__init__(vertices, *args, **kwargs)

        normals = {"U": (0, 0, 1), "R": (1, 0, 0), "F": (0, -1, 0),
                   "D": (0, 0, -1), "L": (-1, 0, 0), "B": (0, 1, 0)}
        face_at_normal = {normal: face for face, normal in normals.items()}
        unique = tuple(to_rgb(f"#{index:02x}4488") for index in range(54))
        source_state = c.State().apply("L D B U")
        original = (source_state.facelets, source_state.shape.labels)
        for word in _CANONICAL_WORDS.values():
            rotation = rotation_tuple(word)
            spatial = lambda point: tuple((1 if axis > 0 else -1) * point[abs(axis) - 1]
                                          for axis in rotation)
            expected = {}
            rotated_facelets = [None] * 54
            renamed_faces = {face: face_at_normal[spatial(normal)]
                             for face, normal in normals.items()}
            for face_index, face in enumerate("URFDLB"):
                target_face = renamed_faces[face]
                normal = normals[target_face]
                axis = next(index for index, component in enumerate(normal) if component)
                plane = 3 if normal[axis] > 0 else 0
                for sticker, cell in enumerate(_FACE_CELLS[face]):
                    index = face_index * 9 + sticker
                    center = spatial((cell % 3 - 1, 1 - cell // 3 % 3, 1 - cell // 9))
                    destination = (1 - center[2]) * 9 + (1 - center[1]) * 3 + center[0] + 1
                    expected[(axis, plane, destination)] = unique[index]
                    target_index = "URFDLB".index(target_face) * 9 + _FACE_CELLS[target_face].index(destination)
                    rotated_facelets[target_index] = renamed_faces[source_state.facelets[index]]
            with patch("mpl_toolkits.mplot3d.art3d.Poly3DCollection", RecordedFaces):
                figure = c.draw_cubes(source_state, sticker_colors=unique, exterior_only=True,
                                      views=("UFR", "BLD"), ncol=2, rotation=word)
            actual = {}
            for view_index, view in enumerate(figure.axes):
                self.assertEqual({text.get_text() for text in view.texts},
                                 set("UFR" if view_index == 0 else "BLD"))
                for collection in view.collections:
                    if not isinstance(collection, RecordedFaces):
                        continue
                    for vertices, color in zip(collection.recorded_vertices, collection.recorded_colors):
                        axis = next(i for i in range(3) if len({vertex[i] for vertex in vertices}) == 1)
                        plane = vertices[0][axis]
                        xyz = [min(2, int(sum(vertex[i] for vertex in vertices) / 4)) for i in range(3)]
                        cell = (2 - xyz[2]) * 9 + (2 - xyz[1]) * 3 + xyz[0]
                        key = (axis, plane, cell)
                        self.assertNotIn(key, actual)
                        actual[key] = tuple(color)
            self.assertEqual(actual, expected, word)
            plt.close(figure)

            # Renaming center colors makes the same pictured cube importable.
            # Local face turns must match their transferred fixed-frame word.
            displayed_before = c.State.from_facelets("".join(rotated_facelets))
            body = "U R' F2"
            local_after = displayed_before.apply(body).facelets
            fixed_after = source_state.apply(rotate_moves(body, word)).facelets
            displayed_after = [None] * 54
            for face_index, face in enumerate("URFDLB"):
                target_face = renamed_faces[face]
                for sticker, cell in enumerate(_FACE_CELLS[face]):
                    center = spatial((cell % 3 - 1, 1 - cell // 3 % 3, 1 - cell // 9))
                    destination = (1 - center[2]) * 9 + (1 - center[1]) * 3 + center[0] + 1
                    target = "URFDLB".index(target_face) * 9 + _FACE_CELLS[target_face].index(destination)
                    displayed_after[target] = renamed_faces[fixed_after[face_index * 9 + sticker]]
            self.assertEqual(local_after, "".join(displayed_after), word)
        self.assertEqual((source_state.facelets, source_state.shape.labels), original)

    def test_transparent_starting_grips_preserve_per_sticker_colors_and_opacities(self):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        from bce_v2.graphics import _FACE_CELLS
        from bce_v2.loop_rotations import _CANONICAL_WORDS, rotation_tuple

        class RecordedFaces(Poly3DCollection):
            def __init__(self, vertices, *args, **kwargs):
                self.recorded_vertices = vertices
                super().__init__(vertices, *args, **kwargs)

            def set_facecolor(self, colors):
                super().set_facecolor(colors)
                self.recorded_colors = colors

        normals = {"U": (0, 0, 1), "R": (1, 0, 0), "F": (0, -1, 0),
                   "D": (0, 0, -1), "L": (-1, 0, 0), "B": (0, 1, 0)}
        original = (self.diagram.state, self.diagram.cell_roles, self.diagram.sticker_roles)
        colors = recognition_diagram_colors(self.diagram, diagram_mode=c.DiagramMode.TRANSPARENT)
        opacities = tuple(.95 if role == "current" else .72 if index % 9 == 4 else .06
                          for index, role in enumerate(self.diagram.sticker_roles))
        expected = Counter((*rgb, alpha) for rgb, alpha in zip(colors, opacities))
        for word in _CANONICAL_WORDS.values():
            rotation = rotation_tuple(word)
            spatial = lambda point: tuple((1 if coordinate > 0 else -1) * point[abs(coordinate) - 1]
                                          for coordinate in rotation)
            expected_geometry = {}
            for face_index, face in enumerate("URFDLB"):
                normal = spatial(normals[face])
                face_axis = next(index for index, component in enumerate(normal) if component)
                plane = 3 if normal[face_axis] > 0 else 0
                for sticker, cell in enumerate(_FACE_CELLS[face]):
                    index = face_index * 9 + sticker
                    center = spatial((cell % 3 - 1, 1 - cell // 3 % 3, 1 - cell // 9))
                    destination = (1 - center[2]) * 9 + (1 - center[1]) * 3 + center[0] + 1
                    expected_geometry[(face_axis, plane, destination)] = (*colors[index], opacities[index])
            with patch("mpl_toolkits.mplot3d.art3d.Poly3DCollection", RecordedFaces):
                figure = recognition_diagram_figure(self.diagram, diagram_mode=c.DiagramMode.TRANSPARENT,
                                                    rotation=word)
            axis = figure.axes[0]
            rendered = Counter(tuple(color) for collection in axis.collections
                               if isinstance(collection, Poly3DCollection)
                               for color in collection.get_facecolor())
            self.assertEqual(rendered, expected, word)
            actual_geometry = {}
            for collection in axis.collections:
                if isinstance(collection, Poly3DCollection):
                    self.assertIsNone(collection.get_alpha(), "alpha must vary by sticker, not block")
                    for vertices, color in zip(collection.recorded_vertices, collection.recorded_colors):
                        face_axis = next(i for i in range(3) if len({vertex[i] for vertex in vertices}) == 1)
                        plane = vertices[0][face_axis]
                        xyz = [min(2, int(sum(vertex[i] for vertex in vertices) / 4)) for i in range(3)]
                        cell = (2 - xyz[2]) * 9 + (2 - xyz[1]) * 3 + xyz[0]
                        actual_geometry[(face_axis, plane, cell)] = tuple(color)
            self.assertEqual(actual_geometry, expected_geometry, word)
            self.assertEqual({text.get_text() for text in axis.texts}, set("UFR"))
            plt.close(figure)
        self.assertEqual((self.diagram.state, self.diagram.cell_roles, self.diagram.sticker_roles), original)

    def test_invalid_face_palettes_fail_with_helpful_face_errors_before_drawing(self):
        with patch("bce_v2.human_diagram_render.draw_cubes") as drawing:
            for palette in ([], True, "red"):
                with self.assertRaisesRegex(TypeError, "face_colors must map"):
                    recognition_diagram_figure(self.diagram, face_colors=palette)
            with self.assertRaisesRegex(ValueError, "face_colors keys must be U"):
                recognition_diagram_image(self.diagram, face_colors={"X": "red"})
            for value in ("not-a-color", (1.2, 0., 0.), None):
                with self.assertRaisesRegex(ValueError, r"face_colors\['F'\]"):
                    recognition_diagram_colors(self.diagram, face_colors={"F": value})
            drawing.assert_not_called()

    def test_individual_facelet_overrides_reach_the_mesh_in_both_gallery_rows(self):
        from matplotlib.colors import to_rgb
        rows = [tuple(f"#{index:02x}4488" for index in range(54)),
                tuple(f"#8844{index:02x}" for index in range(54))]
        figure = c.draw_cubes([c.State(), c.State().apply("R U")],
                             sticker_colors=rows, exterior_only=True,
                             views=("UFR", "BLD"), ncol=2)
        self.assertEqual(len(figure.axes), 4)
        for index, axis in enumerate(figure.axes):
            row = rows[index // 2]
            faces = "UFR" if index % 2 == 0 else "BLD"
            expected = [to_rgb(row["URFDLB".index(face) * 9 + sticker])
                        for face in faces for sticker in range(9)]
            self.assertEqual(Counter(self.face_colors(axis)), Counter(expected))
            self.assertEqual({text.get_text() for text in axis.texts}, set(faces))

    def test_opposite_corner_views_are_opaque_and_cover_every_physical_sticker(self):
        from matplotlib.colors import to_rgb
        figure = recognition_diagram_figure(self.diagram, diagram_mode="opposite-corners")
        self.assertEqual(len(figure.axes), 2)
        front, back = figure.axes
        self.assertAlmostEqual(front.elev, -back.elev)
        self.assertAlmostEqual((back.azim - front.azim) % 360, 180)
        self.assertEqual((front.roll, back.roll), (0, 180))
        self.assertEqual((front._focal_length, back._focal_length), (float("inf"), float("inf")))
        self.assertEqual((front.get_title(), back.get_title()), ("UFR", "BLD"))
        rendered = self.face_colors(front) + self.face_colors(back)
        self.assertEqual(len(rendered), 54)
        self.assertEqual(Counter(rendered), Counter(map(to_rgb, recognition_diagram_colors(self.diagram))))
        self.assertTrue(all(collection.get_alpha() == 1
                            for axis in figure.axes for collection in axis.collections))

    def test_transparent_view_colors_only_centers_and_target_with_diagonal_projection(self):
        from math import atan, degrees, sqrt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        placed_example = next(diagram for stage in self.recognition.method.stages
                              for variants in recognition_stage_diagrams(self.recognition, stage.number).values()
                              for diagram in variants if "placed" in diagram.sticker_roles)
        for diagram in (self.diagram, placed_example):
            figure = recognition_diagram_figure(diagram, diagram_mode="transparent")
            self.assertEqual(len(figure.axes), 1)
            axis = figure.axes[0]
            colors = self.face_colors(axis)
            self.assertEqual(len(colors), 54)
            expected = recognition_diagram_colors(diagram, diagram_mode=c.DiagramMode.TRANSPARENT)
            self.assertEqual(Counter(colors), Counter(expected))
            palette = validate_face_colors()
            for index, (role, face, color) in enumerate(zip(
                    diagram.sticker_roles, diagram.state.facelets, expected)):
                self.assertEqual(color, palette[face] if role == "current" or index % 9 == 4
                                 else (1., 1., 1.))
            roles = {f"cube-0-block-{label}": diagram.cell_roles[cell]
                     for cell, label in enumerate(diagram.state.shape.labels)}
            for collection in axis.collections:
                alpha = collection.get_alpha()
                role = roles[collection.get_gid().rsplit("-", 1)[0]]
                if isinstance(collection, Poly3DCollection):
                    self.assertIsNone(alpha)
                    self.assertTrue(all(color[3] in (.06, .72, .95)
                                        for color in collection.get_facecolor()))
                elif role == "current":
                    self.assertGreater(alpha, .9)
                else:
                    self.assertEqual(alpha, .2)
            self.assertAlmostEqual(axis.elev, degrees(atan(1 / sqrt(2))))
            self.assertEqual((axis.azim, axis.roll), (-45, 0))
            self.assertEqual(axis._focal_length, float("inf"), "use the diagonal orthographic view")
            self.assertEqual(axis.get_title(), "UFR")

    def test_placement_orientations_receive_both_views_and_identifiable_labels(self):
        variants = next(variants for stage in self.recognition.method.stages
                        if stage.feature.kind == "place_block"
                        for variants in recognition_stage_diagrams(self.recognition, stage.number).values()
                        if len(variants) > 1)
        figure = recognition_diagram_figure(variants, diagram_mode="opposite-corners")
        self.assertEqual(len(figure.axes), 2 * len(variants))
        for index, axis in enumerate(figure.axes):
            self.assertEqual(axis.get_title(),
                             f"Orientation {index // 2 + 1} · {('UFR', 'BLD')[index % 2]}")

    def test_invalid_modes_and_mixed_cases_fail_before_drawing(self):
        with patch("bce_v2.human_diagram_render.draw_cubes") as drawing:
            for mode in ("net", "", None, True):
                with self.assertRaises(ValueError):
                    recognition_diagram_figure(self.diagram, diagram_mode=mode)
            for diagrams in ((), (object(),)):
                with self.assertRaises(TypeError):
                    recognition_diagram_figure(diagrams)
            different = [variants[0] for variants in self.pictures.values()][:2]
            with self.assertRaises(ValueError):
                recognition_diagram_figure(different)
            drawing.assert_not_called()
        with self.assertRaises(TypeError):
            recognition_diagram_colors(object())
        with self.assertRaises(ValueError):
            c.draw_cubes(c.State(), sticker_colors=["white"] * 53)
        with self.assertRaises(ValueError):
            c.draw_cubes([c.State(), c.State()], sticker_colors=[["white"] * 54])
        with self.assertRaises(TypeError):
            c.draw_cubes(c.Shape(), sticker_colors=["white"] * 54)
        with self.assertRaises(TypeError):
            c.draw_cubes(c.State(), exterior_only=1)

    def test_inline_png_is_self_contained_and_closes_its_figure_even_after_save_failure(self):
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        before = set(plt.get_fignums())
        image = recognition_diagram_image(self.diagram)
        self.assertTrue(image.startswith("data:image/png;base64,"))
        self.assertTrue(base64.b64decode(image.split(",", 1)[1]).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(set(plt.get_fignums()), before)
        with patch.object(Figure, "savefig", side_effect=RuntimeError("failed image encoding")):
            with self.assertRaisesRegex(RuntimeError, "failed image encoding"):
                recognition_diagram_image(self.diagram)
        self.assertEqual(set(plt.get_fignums()), before)

    def test_visual_guide_covers_every_instruction_skip_and_placement_orientation(self):
        for repertoire in (self.pocket, self.recognition):
            with patch("bce_v2.human_diagram_render.recognition_diagram_image",
                       return_value="data:image/png;base64,cGljdHVyZQ==") as image:
                guide = repertoire.write_guide(diagram_mode="opposite-corners")
            expected = [(stage.number, case.observation, case.instruction)
                        for stage in repertoire.stages for case in stage.cases]
            self.assertEqual(image.call_count, len(expected))
            self.assertEqual(guide.count("### Case "), len(expected))
            self.assertEqual(guide.count("![Stage "), len(expected))
            self.assertEqual(guide.count("Skip — already correct"), len(repertoire.stages))
            self.assertNotIn("### Complete cue lookup", guide)
            for call, (number, observation, instruction) in zip(image.call_args_list, expected):
                from bce_v2.human_instruction_render import instruction_presentation
                self.assertEqual(call.kwargs["diagram_mode"], "opposite-corners")
                self.assertEqual(call.args[0], recognition_stage_diagrams(repertoire, number)[observation])
                self.assertEqual(call.kwargs["rotation"], instruction_presentation(
                    instruction, repertoire).rotation if instruction is not None else "")
            import re
            instructions = re.findall(r"Execute `[^`]+: [URFDLB][^`]*`\.", guide)
            self.assertEqual(len(instructions), sum(instruction is not None for _, _, instruction in expected))
            self.assertNotIn("then inspect again", guide)
            self.assertNotIn("## Before starting", guide)
            self.assertNotIn("## Recognition colors", guide)
            self.assertNotIn("Match footprint", guide)
            self.assertIn("| Turn sequence | Block action | Structure |", guide)
            definitions = re.findall(r"^\| `(?:M|A)\d+: [^`]+` \| `[^`]+` \| `[^`]+` \|$",
                                     guide, re.MULTILINE)
            self.assertGreaterEqual(len(definitions), len(repertoire.macros))
            for macro in repertoire.macros:
                self.assertIn(f"| `{macro.id}: {macro.algorithm.turn_sequence}` |", guide)

    def test_text_guide_remains_available_and_saved_visual_guide_is_identical(self):
        text = self.pocket.write_guide()
        self.assertIn("### Complete cue lookup", text)
        self.assertNotIn("![Stage ", text)
        import re
        self.assertIn("| Turn sequence | Block action | Structure |", text)
        definitions = re.findall(r"^\| `(?:M|A)\d+: [^`]+` \| `[^`]+` \| `[^`]+` \|$",
                                 text, re.MULTILINE)
        self.assertGreaterEqual(len(definitions), len(self.pocket.macros))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            with patch("bce_v2.human_diagram_render.recognition_diagram_image",
                       return_value="data:image/png;base64,cGljdHVyZQ=="):
                guide = self.pocket.write_guide(path, diagram_mode="transparent")
            self.assertEqual(path.read_text(), guide)
            self.assertIn("![Stage ", guide)
        with patch("bce_v2.human_diagram_render.recognition_diagram_image") as image:
            with self.assertRaises(ValueError):
                self.pocket.write_guide(diagram_mode="net")
            image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
