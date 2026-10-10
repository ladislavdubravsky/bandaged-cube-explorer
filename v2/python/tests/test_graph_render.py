"""Bandage drawings preserve face actions and expose spatial symmetries."""

from collections import Counter
import importlib.util
import unittest
from unittest.mock import patch

import bce_v2 as c


HAS_PLOTS = all(importlib.util.find_spec(module) is not None
                for module in ("matplotlib", "networkx", "numpy"))
HAS_SCIPY = importlib.util.find_spec("scipy") is not None
POCKET = (
    1, 1, 2, 1, 1, 2, 3, 3, 0,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
    0, 0, 4, 0, 0, 4, 5, 5, 6,
)


def u_cycle():
    """Four physical shapes with just U allowed: every vertex has degree two."""
    labels = [0] * 27
    for cell in range(9, 27):
        labels[cell] = 1
    labels[c.UBL] = labels[c.UB] = 2
    return c.explore(labels)


@unittest.skipUnless(HAS_PLOTS, "optional graph and plots extras")
class BandageGraphRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use("Agg")
        cls.pocket = c.explore(POCKET)
        cls.bicube = c.explore(c.fixture("Bicube Fuse"))
        cls.cycle = u_cycle()

    def tearDown(self):
        import matplotlib.pyplot as plt
        plt.close("all")

    def artists(self, figure, prefix):
        return {artist.get_gid(): artist for axis in figure.axes
                for artist in axis.get_children()
                if isinstance(artist.get_gid(), str)
                and artist.get_gid().startswith(prefix)}

    def positive_edges(self, graph):
        return {(source, target, move) for source, target, move in graph.arcs
                if move in "URFDLB" and len(move) == 1}

    def shape_bounds(self, figure):
        import numpy as np
        points = {}
        for gid, artist in self.artists(figure, "bandage-shape-").items():
            if gid.endswith("-surface"):
                vertex = int(gid.split("-")[2])
                points.setdefault(vertex, []).extend(
                    point for path in artist.get_paths() for point in path.vertices)
        return {vertex: (np.min(values, axis=0), np.max(values, axis=0))
                for vertex, values in points.items()}

    def test_auto_summary_skips_layout_sizing_and_shape_materialization(self):
        # A low threshold exercises the large-graph policy on a real graph.
        graph = c.explore(POCKET)
        self.assertIsNone(graph._shapes)
        with patch("bce_v2.graph_render.bandage_graph_layout", side_effect=AssertionError("layout")), \
             patch("bce_v2.graph_render._shape_width_limit", side_effect=AssertionError("sizing")), \
             patch("bce_v2.graph_render._dependencies", side_effect=AssertionError("networkx")):
            figure = graph.draw(max_vertices=100, show_shapes=True)
        self.assertIsNone(graph._shapes)
        self.assertEqual(self.artists(figure, "bandage-edge-"), {})
        self.assertEqual(self.artists(figure, "bandage-shape-"), {})
        self.assertIn("580 shapes", figure.axes[0].get_title())
        self.assertTrue(any("view='full'" in text.get_text() for text in figure.axes[0].texts))

    def test_public_draw_api_forwards_view_size_limit_and_radius(self):
        summary = c.draw_bandage_graph(self.pocket, view="auto", max_vertices=100,
                                       radius=0, show_shapes=True)
        self.assertIn("580 shapes", summary.axes[0].get_title())
        self.assertEqual(self.artists(summary, "bandage-edge-"), {})
        local = c.draw_bandage_graph(self.cycle, view="local", max_vertices=3,
                                     radius=0, start=3, iterations=0)
        self.assertEqual(set(self.artists(local, "bandage-node-")), {"bandage-node-3"})
        self.assertEqual(self.artists(local, "bandage-edge-"), {})
        full = c.draw_bandage_graph(self.cycle, view="full", max_vertices=1,
                                    radius=0, iterations=0)
        self.assertEqual(set(self.artists(full, "bandage-edge-")), {
            f"bandage-edge-{source}-{target}-{move}"
            for source, target, move in self.positive_edges(self.cycle)})

    def test_full_override_and_small_auto_retain_all_actions(self):
        for view in ("auto", "full"):
            figure = self.cycle.draw(view=view, max_vertices=1 if view == "full" else 4,
                                     iterations=0)
            self.assertEqual(set(self.artists(figure, "bandage-edge-")), {
                f"bandage-edge-{source}-{target}-{move}"
                for source, target, move in self.positive_edges(self.cycle)})
        figure = self.cycle.draw(view="summary")
        self.assertEqual(self.artists(figure, "bandage-edge-"), {})

    def test_local_view_is_bounded_and_preserves_original_vertex_ids(self):
        actions = tuple(sorted(self.positive_edges(self.bicube)))
        start = 17
        with patch("bce_v2.graph_render.bandage_graph_layout", side_effect=AssertionError("full layout")):
            figure = self.bicube.draw(view="local", start=start, radius=2,
                                      max_vertices=7, iterations=0)
        vertices = {start}
        for gid in self.artists(figure, "bandage-edge-"):
            _, _, source, target, _ = gid.split("-")
            vertices.update((int(source), int(target)))
        self.assertLessEqual(len(vertices), 7)
        self.assertGreater(len(vertices), 1)
        distances = self.bicube.distances(start)
        self.assertTrue(all(distances[vertex] <= 2 for vertex in vertices))
        self.assertEqual(set(self.artists(figure, "bandage-edge-")), {
            f"bandage-edge-{source}-{target}-{move}"
            for source, target, move in actions if source in vertices and target in vertices})
        self.assertIn("Local view", figure.axes[0].get_title())
        self.assertIn(f"{len(vertices)} of", figure.axes[0].get_title())
        self.assertIn(f"bandage-node-{start}", self.artists(figure, "bandage-node-"))

    def test_local_radius_zero_draws_only_start_and_its_loops(self):
        figure = self.bicube.draw(view="local", start=3, radius=0, show_shapes=True)
        self.assertEqual({int(gid.split("-")[2]) for gid in
                          self.artists(figure, "bandage-shape-")}, {3})
        self.assertEqual(set(self.artists(figure, "bandage-edge-")), {
            f"bandage-edge-3-3-{move}" for source, target, move in self.positive_edges(self.bicube)
            if source == target == 3})

    def test_local_manual_positions_need_only_selected_vertices(self):
        positions = {3: (2., 4.)}
        figure = self.bicube.draw(view="local", start=3, radius=0, pos=positions)
        self.assertEqual(tuple(self.artists(figure, "bandage-node-")[
            "bandage-node-3"].center), positions[3])

    def test_view_options_are_validated_before_summary(self):
        for options in ({"view": "unknown"}, {"max_vertices": 0}, {"max_vertices": True},
                        {"radius": -1}, {"radius": 1.5}, {"layout": "bad"},
                        {"iterations": -1}, {"seed": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.cycle.draw(**options)

    def test_linear_cycles_keep_deterministic_order(self):
        from bce_v2.graph_render import _cycles
        self.assertEqual(_cycles((0, 3, 4, 1, 2)), [[0], [1, 3], [2, 4]])
        self.assertEqual(_cycles(tuple(range(16000))), [[vertex] for vertex in range(16000)])

    @unittest.skipUnless(HAS_SCIPY, "optional SciPy nearest neighbors")
    def test_large_automatic_picture_clearances_use_nearest_neighbors(self):
        import numpy as np
        from bce_v2.graph_render import _shape_width_limit
        positions = {vertex: (float(vertex), 0.) for vertex in range(2001)}
        ratios = {vertex: 1. for vertex in positions}
        with patch("numpy.linalg.norm", side_effect=AssertionError("all-pairs distances")):
            width = _shape_width_limit(positions, ratios, span=2000.,
                                       mode=c.DiagramMode.OPPOSITE_CORNERS, np=np)
        self.assertGreater(width, 0.)
        self.assertLess(width, 0.5)

    def test_automatic_sizes_leave_room_between_shapes_and_for_edges(self):
        import numpy as np
        labels = [0] * 27
        for cell in (c.U, c.UB, c.UF):
            labels[cell] = 1
        graph = c.explore(labels)
        positions = {0: (0., 0.), 1: (0.1, 0.)}
        for mode in c.DiagramMode:
            for figsize in (None, (4, 3), (3, 8)):
                with self.subTest(mode=mode, figsize=figsize):
                    figure = c.draw_bandage_graph(
                        graph, pos=positions, show_shapes=True, diagram_mode=mode,
                        figsize=figsize)
                    figure.canvas.draw()
                    bounds = self.shape_bounds(figure)
                    self.assertEqual(set(bounds), {0, 1})
                    # Conservative picture bounds consume less than half the
                    # separation, leaving a visible middle section of each arc.
                    radii = [np.linalg.norm(high - low) / 2 for low, high in bounds.values()]
                    self.assertLess(sum(radii), 0.05)
                    self.assertLess(bounds[0][1][0], bounds[1][0][0])
                    for arrow in self.artists(figure, "bandage-edge-").values():
                        self.assertTrue(np.isfinite(arrow.get_path().vertices).all())

    def test_automatic_sizes_respect_hidden_vertices_and_coordinate_scale(self):
        import numpy as np
        positions = {0: (0., 0.), 1: (0.05, 0.), 2: (2., 2.), 3: (0., 2.)}
        sizes = []
        widths = []
        for scale in (1., 0.001, 100.):
            figure = self.cycle.draw(
                pos={vertex: tuple(scale * np.array(point)) for vertex, point in positions.items()},
                show_shapes=True)
            figure.canvas.draw()
            bounds = self.shape_bounds(figure)
            self.assertEqual(set(bounds), {0})
            low, high = bounds[0]
            self.assertLess(np.linalg.norm(high - low) / 2, 0.025 * scale)
            sizes.append(figure.get_size_inches())
            widths.append((high[0] - low[0]) / scale)
        np.testing.assert_allclose(sizes, np.tile(sizes[0], (3, 1)), atol=1e-9)
        np.testing.assert_allclose(widths, [widths[0]] * 3, atol=1e-9)

    def test_automatic_figure_grows_with_layout_density_and_is_bounded(self):
        positions = {0: (0., 0.), 1: (2., 0.), 2: (2., 2.), 3: (0., 2.)}
        sparse = c.draw_bandage_graph(self.cycle, pos=positions)
        dense = c.draw_bandage_graph(self.pocket, layout="spring", iterations=20)
        self.assertGreater(dense.get_figwidth(), sparse.get_figwidth())
        for figure in (sparse, dense):
            self.assertGreaterEqual(figure.get_figwidth(), 6)
            self.assertLessEqual(figure.get_figwidth(), 24)

    def test_explicit_sizes_override_automatic_defaults_independently(self):
        import numpy as np
        positions = {0: (0., 0.), 1: (2., 0.), 2: (2., 2.), 3: (0., 2.)}
        for figsize in (None, (9, 5)):
            figure = c.draw_bandage_graph(
                self.cycle, pos=positions, show_shapes=True,
                figsize=figsize, shape_size=0.7)
            figure.canvas.draw()
            if figsize is not None:
                np.testing.assert_allclose(figure.get_size_inches(), figsize)
            low, high = self.shape_bounds(figure)[0]
            axis, = figure.axes
            pixels = axis.transData.transform(high)[0] - axis.transData.transform(low)[0]
            # The cube panels reserve a small gutter inside the specified width.
            self.assertAlmostEqual(pixels / figure.dpi, 0.7 * (1 + 1 / 1.08) / 2)

    def test_automatic_sizes_handle_coincident_positions_and_keep_validation(self):
        import numpy as np
        figure = c.draw_bandage_graph(
            self.cycle, pos=dict.fromkeys(range(4), (0., 0.)), show_shapes=True)
        figure.canvas.draw()
        self.assertTrue(np.isfinite(figure.get_size_inches()).all())
        self.assertTrue(all(np.isfinite(low).all() and np.isfinite(high).all()
                            for low, high in self.shape_bounds(figure).values()))
        for size in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(shape_size=size), self.assertRaises(ValueError):
                c.draw_bandage_graph(self.cycle, shape_size=size)
        for size in ((), (3,), (3, 0), (3, float("inf")), False):
            with self.subTest(figsize=size), self.assertRaises(ValueError):
                c.draw_bandage_graph(self.cycle, figsize=size)

    def test_exact_positive_native_actions_in_both_metrics(self):
        """Each arrow represents the original directed action, not an inverse view."""
        for metric in ("QTM", "HTM"):
            graph = c.explore(c.fixture("Bicube Fuse"), metric=metric)
            figure = c.draw_bandage_graph(graph, layout="spring", iterations=20, edge_labels=True)
            expected = self.positive_edges(graph)
            self.assertTrue(expected)
            self.assertEqual(set(self.artists(figure, "bandage-edge-")), {
                f"bandage-edge-{source}-{target}-{move}"
                for source, target, move in expected})
            labels = self.artists(figure, "bandage-label-")
            self.assertEqual(set(labels), {
                f"bandage-label-{source}-{target}-{move}"
                for source, target, move in expected})
            self.assertEqual(Counter(text.get_text() for text in labels.values()),
                             Counter(move for _, _, move in expected))
            for source, target, move in expected:
                self.assertEqual(graph[source].apply(move), graph[target])

    def test_pocket_graph_draws_every_shape_action(self):
        self.assertEqual(len(self.pocket), 580)
        expected = self.positive_edges(self.pocket)
        self.assertEqual(len(expected), 828)
        figure = c.draw_bandage_graph(self.pocket, layout="spring", iterations=20)
        self.assertEqual(len(self.artists(figure, "bandage-edge-")), 828)
        self.assertEqual(self.artists(figure, "bandage-label-"), {})

    def test_self_loops_and_parallel_face_actions_have_distinct_arrow_paths(self):
        import numpy as np
        graph = c.explore(c.Shape())
        self.assertEqual(len(graph), 1)
        figure = c.draw_bandage_graph(graph, edge_labels=True)
        edges = self.artists(figure, "bandage-edge-")
        self.assertEqual(set(edges), {f"bandage-edge-0-0-{face}" for face in "URFDLB"})
        paths = []
        for arrow in edges.values():
            path = arrow.get_path().vertices
            self.assertTrue(np.isfinite(path).all())
            self.assertGreater(np.ptp(path, axis=0).max(), 0)
            paths.append(tuple(np.round(path.flatten(), 9)))
        self.assertEqual(len(set(paths)), 6)

    def test_loops_and_shape_diagrams_fit_inside_the_rendered_axes(self):
        labels = [0] * 27
        for cell in (c.U, c.UB, c.UF):
            labels[cell] = 1
        graph = c.explore(labels)
        self.assertEqual(len(graph), 2)
        self.assertEqual(len(self.positive_edges(graph)), 8)
        figure = c.draw_bandage_graph(graph, pos={0: (-1., 0.), 1: (1., 0.)},
                                      figsize=(6, 6), show_shapes=True, edge_labels=True)
        figure.canvas.draw()
        axis, = figure.axes
        left, right = sorted(axis.get_xlim())
        bottom, top = sorted(axis.get_ylim())
        arrows = self.artists(figure, "bandage-edge-")
        self.assertEqual(set(arrows), {
            f"bandage-edge-{source}-{target}-{move}"
            for source, target, move in self.positive_edges(graph)})
        surfaces = {gid: artist for gid, artist in
                    self.artists(figure, "bandage-shape-").items()
                    if gid.endswith("-surface")}
        self.assertEqual({int(gid.split("-")[2]) for gid in surfaces}, {0, 1})
        paths = [(gid, arrow.get_path()) for gid, arrow in arrows.items()]
        paths.extend((gid, path) for gid, surface in surfaces.items()
                     for path in surface.get_paths())
        for gid, path in paths:
            with self.subTest(artist=gid):
                extent = path.get_extents()
                self.assertGreaterEqual(extent.xmin, left - 1e-9)
                self.assertLessEqual(extent.xmax, right + 1e-9)
                self.assertGreaterEqual(extent.ymin, bottom - 1e-9)
                self.assertLessEqual(extent.ymax, top + 1e-9)

    def test_arrow_direction_matches_native_source_and_target(self):
        import numpy as np
        positions = {0: (0., 0.), 1: (2., 0.), 2: (2., 2.), 3: (0., 2.)}
        figure = c.draw_bandage_graph(self.cycle, pos=positions)
        for source, target, move in self.positive_edges(self.cycle):
            arrow = self.artists(figure, "bandage-edge-")[
                f"bandage-edge-{source}-{target}-{move}"]
            vertices = arrow.get_path().vertices
            start = np.asarray(positions[source])
            end = np.asarray(positions[target])
            # The first path point is the tail; the arrowhead lies at the target.
            self.assertLess(np.linalg.norm(vertices[0] - start),
                            np.linalg.norm(vertices[0] - end))
            self.assertLess(np.linalg.norm(vertices[-2] - end),
                            np.linalg.norm(vertices[-2] - start))

    def test_degree_two_vertices_hide_markers_and_pictures_except_start(self):
        self.assertEqual(len(self.cycle), 4)
        degree = Counter()
        for source, target, _ in self.positive_edges(self.cycle):
            degree[source] += 1
            degree[target] += 1
        self.assertEqual(set(degree.values()), {2})
        for start in (0, 3):
            figure = c.draw_bandage_graph(self.cycle, start=start, layout="spring", iterations=20)
            self.assertEqual(set(self.artists(figure, "bandage-node-")),
                             {f"bandage-node-{start}"})
            pictured = c.draw_bandage_graph(self.cycle, start=start, layout="spring", iterations=20,
                                            show_shapes=True)
            surfaces = self.artists(pictured, "bandage-shape-")
            self.assertTrue(surfaces)
            self.assertEqual({int(gid.split("-")[2]) for gid in surfaces}, {start})

    def test_starting_marker_has_maximum_size_even_for_small_degree(self):
        degree = Counter()
        for source, target, _ in self.positive_edges(self.bicube):
            degree[source] += 1
            degree[target] += 1
        start = min(degree, key=degree.get)
        self.assertLess(degree[start], max(degree.values()))
        figure = c.draw_bandage_graph(self.bicube, start=start, layout="spring", iterations=20)
        markers = self.artists(figure, "bandage-node-")
        root = markers[f"bandage-node-{start}"]
        root_box = root.get_path().get_extents(root.get_transform())
        root_extent = max(root_box.width, root_box.height)
        for marker in markers.values():
            box = marker.get_path().get_extents(marker.get_transform())
            self.assertLessEqual(max(box.width, box.height), root_extent + 1e-9)

    def test_picture_sizes_follow_degree_with_start_always_maximum(self):
        import numpy as np
        degree = Counter()
        for source, target, _ in self.positive_edges(self.bicube):
            degree[source] += 1
            degree[target] += 1
        start = min(degree, key=degree.get)
        figure = c.draw_bandage_graph(self.bicube, start=start, show_shapes=True,
                                      layout="spring", iterations=20)
        horizontal = {}
        for gid, artist in self.artists(figure, "bandage-shape-").items():
            if gid.endswith("-surface"):
                vertex = int(gid.split("-")[2])
                horizontal.setdefault(vertex, []).extend(
                    point[0] for path in artist.get_paths() for point in path.vertices)
        widths = {vertex: np.ptp(coordinates) for vertex, coordinates in horizontal.items()}
        self.assertGreater(widths[start], 0)
        for vertex, width in widths.items():
            expected_ratio = 1 if vertex == start else degree[vertex] / max(degree.values())
            self.assertAlmostEqual(width / widths[start], expected_ratio, places=8)

    def test_graph_draw_convenience_accepts_shape_start(self):
        figure = self.cycle.draw(start=self.cycle[2], layout="spring", iterations=20)
        self.assertEqual(set(self.artists(figure, "bandage-node-")), {"bandage-node-2"})
        self.assertEqual(set(self.artists(figure, "bandage-edge-")), {
            f"bandage-edge-{source}-{target}-{move}"
            for source, target, move in self.positive_edges(self.cycle)})

    def test_edge_face_colors_and_white_to_black(self):
        from matplotlib.colors import to_rgba
        palette = {"U": "white", "R": "purple", "F": "cyan", "D": "gold",
                   "L": "orange", "B": "navy"}
        figure = c.draw_bandage_graph(c.Shape(), face_colors=palette, edge_labels=True)
        edges = self.artists(figure, "bandage-edge-")
        for face in "URFDLB":
            expected = to_rgba("black" if face == "U" else palette[face])
            self.assertEqual(tuple(edges[f"bandage-edge-0-0-{face}"].get_edgecolor()), expected)
        self.assertEqual(palette["U"], "white", "drawing must preserve the caller's mapping")

    def test_center_block_diagrams_color_displayed_faces_and_other_blocks_white(self):
        from matplotlib.colors import to_rgb
        palette = dict(zip("URFDLB", ("magenta", "cyan", "lime", "gold", "orange", "navy")))
        plain = c.draw_bandage_graph(c.Shape(), show_shapes=True, face_colors=palette)
        labels = [0] * 27
        labels[c.U] = labels[c.UF] = 1
        fused = c.draw_bandage_graph(labels, show_shapes=True, face_colors=palette)

        def colors(figure):
            return Counter(tuple(color[:3]) for gid, artist in
                           self.artists(figure, "bandage-shape-0-").items()
                           if gid.endswith("-surface")
                           for color in artist.get_facecolor())

        plain_colors, fused_colors = colors(plain), colors(fused)
        self.assertTrue(plain_colors)
        self.assertEqual(set(plain_colors), {to_rgb(color) for color in palette.values()} | {(1., 1., 1.)})
        self.assertEqual(sum(plain_colors.values()), 54)
        self.assertEqual(plain_colors[(1., 1., 1.)], 48)
        # U--UF colors UF's two exterior stickers by their displayed U/F faces.
        self.assertEqual(fused_colors[to_rgb(palette["U"])], plain_colors[to_rgb(palette["U"])] + 1)
        self.assertEqual(fused_colors[to_rgb(palette["F"])], plain_colors[to_rgb(palette["F"])] + 1)
        self.assertEqual(fused_colors[(1., 1., 1.)], 46)

    def test_partial_graphs_have_explicit_partial_title(self):
        graph = c.explore(POCKET, max_vertices=12)
        self.assertFalse(graph.complete)
        figure = c.draw_bandage_graph(graph, layout="spring", iterations=20)
        title = " ".join(axis.get_title() for axis in figure.axes)
        self.assertIn("partial", title.lower())
        self.assertEqual(len(self.artists(figure, "bandage-edge-")),
                         len(self.positive_edges(graph)))

    def test_layouts_are_finite_and_reproducible(self):
        import numpy as np
        layouts = ("symmetry", "spring", "spectral")
        if HAS_SCIPY:
            layouts += ("kamada_kawai",)
        for layout in layouts:
            with self.subTest(layout=layout):
                first = c.bandage_graph_layout(self.bicube, layout=layout, seed=17,
                                               iterations=40)
                second = c.bandage_graph_layout(self.bicube, layout=layout, seed=17,
                                                iterations=40)
                self.assertEqual(set(first), set(range(len(self.bicube))))
                coordinates = np.asarray([first[index] for index in range(len(self.bicube))])
                self.assertEqual(coordinates.shape, (len(self.bicube), 2))
                self.assertTrue(np.isfinite(coordinates).all())
                np.testing.assert_allclose(coordinates,
                    np.asarray([second[index] for index in range(len(self.bicube))]), atol=1e-12)

    def test_supplied_positions_are_used_without_mutating_them(self):
        positions = {0: (2., 3.), 1: (4., 3.), 2: (4., 6.), 3: (2., 6.)}
        saved = dict(positions)
        figure = c.draw_bandage_graph(self.cycle, start=3, pos=positions)
        marker = self.artists(figure, "bandage-node-")["bandage-node-3"]
        self.assertEqual(tuple(marker.center), positions[3])
        self.assertEqual(positions, saved)

    def test_symmetry_layout_has_deterministic_fallback_without_rotations(self):
        import numpy as np
        graph = c.explore(self.cycle[0], max_vertices=2)
        self.assertFalse(any({shape.rotated(rotation) for shape in graph} == set(graph)
                             for rotation in range(1, 24)))
        first = c.bandage_graph_layout(graph, layout="symmetry", seed=12, iterations=20)
        second = c.bandage_graph_layout(graph, layout="symmetry", seed=12, iterations=20)
        self.assertEqual(set(first), {0, 1})
        np.testing.assert_allclose([first[vertex] for vertex in range(len(graph))],
                                   [second[vertex] for vertex in range(len(graph))], atol=1e-12)
        self.assertGreater(np.linalg.norm(np.asarray(first[0]) - first[1]), 0)

    def test_symmetry_layout_preserves_exact_pocket_cube_rotation_distances(self):
        import numpy as np
        positions = c.bandage_graph_layout(self.pocket, seed=4, iterations=80)
        points = np.asarray([positions[index] for index in range(len(self.pocket))])
        distances = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)
        index_by_shape = {shape: index for index, shape in enumerate(self.pocket)}
        for rotation in (7, 10):
            permutation = [index_by_shape[shape.rotated(rotation)] for shape in self.pocket]
            self.assertEqual(permutation[0], 0)
            np.testing.assert_allclose(distances,
                distances[np.ix_(permutation, permutation)], atol=1e-8, rtol=1e-8)
        nontrivial = 0
        for index, shape in enumerate(self.pocket):
            orbit = [index, index_by_shape[shape.rotated(7)], index_by_shape[shape.rotated(10)]]
            if len(set(orbit)) == 3:
                nontrivial += 1
                self.assertGreater(min(distances[orbit[0], orbit[1]],
                                       distances[orbit[1], orbit[2]],
                                       distances[orbit[2], orbit[0]]), 1e-7)
        self.assertGreater(nontrivial, 0)


if __name__ == "__main__":
    unittest.main()
