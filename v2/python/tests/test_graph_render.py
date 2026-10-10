"""Bandage drawings preserve face actions and expose spatial symmetries."""

from collections import Counter
import importlib.util
import unittest

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
