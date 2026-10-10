"""Directed single-turn bandage graphs and deterministic geometric layouts.

Layout uses unweighted shape adjacency; full rendering retains every clockwise
action, including parallel edges and loops. Large graphs default to a summary,
with optional bounded local views. No shape is quotiented by rotation.
"""

from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from inspect import signature
from math import cos, isfinite, pi, sin, sqrt

from . import explore
from .graph import ShapeGraph
from .graphics import _FACE_CELLS, _FACE_PLANES, _block_mesh, _palette
from .human_diagram_modes import DiagramMode


_LAYOUTS = ("symmetry", "spring", "kamada_kawai", "spectral")
_VIEWS = ("auto", "full", "summary", "local")
_DEFAULT_MAX_VERTICES = 1000


def _dependencies():
    try:
        import networkx as nx
        import numpy as np
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[graph,plots] "
                          "to draw bandage graphs") from error
    return nx, np


def _graph(value):
    return value if isinstance(value, ShapeGraph) else explore(value)


def _actions(graph):
    return tuple((source, target, move) for source, target, move in graph.arcs
                 if move in "URFDLB" and len(move) == 1)


def _geometry(graph, nx):
    result = nx.Graph()
    result.add_nodes_from(range(len(graph)))
    result.add_edges_from((source, target) for source, target, _ in _actions(graph)
                         if source != target)
    return result


def _cycles(permutation):
    visited = bytearray(len(permutation))
    result = []
    for first in range(len(permutation)):
        if visited[first]:
            continue
        vertex = first
        cycle = []
        while not visited[vertex]:
            visited[vertex] = 1
            cycle.append(vertex)
            vertex = permutation[vertex]
        result.append(cycle)
    return result


def _planar_symmetry(graph):
    """Find an actual component automorphism with a noncollapsing 2D action.

    Orders three/four act as rotations and allow at most one fixed point.
    An involution acts as reflection, allowing many fixed points on its axis.
    Rotations must preserve retained *actions*, also for partial explorations.
    """
    from .block_actions import _NORMALS, _ROTATIONS, _rotate

    vertices = {value: vertex for vertex, value in enumerate(graph.shapes)}
    actions = set(_actions(graph))
    face_at = {normal: face for face, normal in _NORMALS.items()}
    candidates = []
    for index, rotation in enumerate(_ROTATIONS[1:], 1):
        permutation = tuple(vertices.get(value.rotated(index), -1) for value in graph)
        if -1 in permutation or permutation == tuple(range(len(graph))):
            continue
        cycles = _cycles(permutation)
        order = max(map(len, cycles))
        if order not in (2, 3, 4) or any(len(cycle) not in (1, order) for cycle in cycles):
            continue
        if order > 2 and sum(len(cycle) == 1 for cycle in cycles) > 1:
            continue
        faces = {face: face_at[_rotate(rotation, normal)] for face, normal in _NORMALS.items()}
        if any((permutation[source], permutation[target], faces[move]) not in actions
               for source, target, move in actions):
            continue
        moved = sum(len(cycle) for cycle in cycles if len(cycle) > 1)
        candidates.append((order, moved, -index, permutation, cycles))
    return max(candidates, key=lambda value: value[:3]) if candidates else None


def _symmetric_spring(geometry, symmetry, *, seed, iterations, nx, np):
    """Fruchterman--Reingold forces, projected onto an exact cyclic symmetry."""
    order, _, _, _, cycles = symmetry
    count = len(geometry)
    matrix = (np.diag((-1., 1.)) if order == 2 else
              np.array(((cos(2 * pi / order), -sin(2 * pi / order)),
                        (sin(2 * pi / order), cos(2 * pi / order)))))
    powers = [np.linalg.matrix_power(matrix, step) for step in range(order)]

    def project(values):
        result = np.empty_like(values)
        for cycle in cycles:
            if len(cycle) == 1:
                # Reflection fixes a line; a nontrivial rotation fixes the origin.
                result[cycle[0]] = (0., values[cycle[0], 1]) if order == 2 else (0., 0.)
            else:
                point = sum(powers[step].T @ values[vertex]
                            for step, vertex in enumerate(cycle)) / order
                for step, vertex in enumerate(cycle):
                    result[vertex] = powers[step] @ point
        return result

    random = np.random.RandomState(seed)
    adjacency = nx.to_numpy_array(geometry, dtype=float) if count <= 1000 else None
    # A symmetry-compatible low-frequency seed exposes the large-scale shape.
    # Random perturbations separate vertices sharing all low-frequency modes.
    positions = None
    if adjacency is not None:
        laplacian = np.diag(adjacency.sum(axis=1)) - adjacency
        _, eigenvectors = np.linalg.eigh(laplacian)
        for column in range(1, count):
            vector = eigenvectors[:, column]
            candidate = project(np.column_stack((vector, np.zeros(count))))
            if np.linalg.norm(candidate) > 1e-7:
                positions = candidate / max(np.max(np.abs(candidate)), 1e-9)
                if order == 2:
                    # The second coordinate must be invariant under reflection.
                    for second in range(1, count):
                        invariant = project(np.column_stack((np.zeros(count), eigenvectors[:, second])))
                        if np.linalg.norm(invariant) > 1e-7:
                            positions += invariant / max(np.max(np.abs(invariant)), 1e-9)
                            break
                break
    if positions is None:
        positions = project(random.normal(size=(count, 2)))
    positions += 0.03 * project(random.normal(size=(count, 2)))
    # Above 1,000 shapes, block the all-pairs repulsion and retain only sparse
    # adjacency. This avoids allocating an N x N x 2 tensor for a large graph.
    if adjacency is None:
        edge_pairs = np.asarray(list(geometry.edges()), dtype=int).reshape(-1, 2)
    ideal = 1 / sqrt(count)
    temperature = 0.1 * max(float(np.ptp(positions, axis=0).max()), 1.)
    cooling = temperature / (iterations + 1)
    for _ in range(iterations):
        if adjacency is not None:
            difference = positions[:, None, :] - positions[None, :, :]
            distance = np.maximum(np.linalg.norm(difference, axis=-1), 0.01)
            forces = np.einsum("ijk,ij->ik", difference,
                               ideal * ideal / distance**2 - adjacency * distance / ideal)
        else:
            forces = np.empty_like(positions)
            for first in range(0, count, 128):
                last = min(first + 128, count)
                difference = positions[first:last, None, :] - positions[None, :, :]
                distance = np.maximum(np.linalg.norm(difference, axis=-1), 0.01)
                forces[first:last] = np.einsum("ijk,ij->ik", difference,
                                               ideal * ideal / distance**2)
            sources, targets = edge_pairs.T
            difference = positions[sources] - positions[targets]
            attraction = difference * (np.linalg.norm(difference, axis=-1) / ideal)[:, None]
            np.add.at(forces, sources, -attraction)
            np.add.at(forces, targets, attraction)
        length = np.maximum(np.linalg.norm(forces, axis=-1), 0.01)
        update = project(forces * (temperature / length)[:, None])
        positions = project(positions + update)
        temperature -= cooling
        if np.linalg.norm(update) / count < 1e-5:
            break
    positions = nx.rescale_layout(positions, scale=1)
    return {vertex: tuple(point) for vertex, point in enumerate(positions)}


def bandage_graph_layout(value, *, layout="symmetry", seed=0, iterations=300):
    """Return reproducible 2D positions keyed by shape vertex ID.

    ``symmetry`` constrains spring forces to a whole-cube rotation that preserves
    the actual component, when it admits a noncollapsing planar representation.
    It displays a cyclic subgroup, rather than promising every cube symmetry in
    two dimensions. If no such rotation exists it uses ordinary spring forces.
    ``spring`` is Fruchterman--Reingold, ``kamada_kawai`` minimizes path-length
    stress, and ``spectral`` uses the graph Laplacian. The latter two require
    SciPy for some or all graph sizes. Loops do not influence the layout, and
    neither the QTM/HTM metric nor parallel actions change layout weights.
    """
    if not isinstance(layout, str) or layout not in _LAYOUTS:
        raise ValueError(f"layout must be one of {_LAYOUTS}")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
        raise ValueError("iterations must be a nonnegative integer")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in 0..2**32-1")
    graph = _graph(value)
    nx, np = _dependencies()
    geometry = _geometry(graph, nx)
    if len(graph) == 1:
        return {0: (0., 0.)}
    if layout == "symmetry":
        symmetry = _planar_symmetry(graph)
        if symmetry:
            return _symmetric_spring(geometry, symmetry, seed=seed, iterations=iterations,
                                     nx=nx, np=np)
        layout = "spring"
    try:
        if layout == "spring":
            # Recent NetworkX versions otherwise switch to a different energy
            # solver at 500 vertices. Keep the named spring algorithm consistent.
            options = {"method": "force"} if "method" in signature(nx.spring_layout).parameters else {}
            positions = nx.spring_layout(geometry, seed=seed, iterations=iterations,
                                         weight=None, **options)
        elif layout == "kamada_kawai":
            positions = nx.kamada_kawai_layout(geometry, weight=None)
        else:
            positions = nx.spectral_layout(geometry, weight=None)
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[graph] for SciPy energy layouts") from error
    return {vertex: tuple(map(float, point)) for vertex, point in positions.items()}


def _palette_rgb(face_colors):
    from matplotlib.colors import to_rgb
    palette = {face: to_rgb(color) for face, color in _palette(face_colors).items()}
    # Face stickers and edges share the same white-to-black graph palette.
    white = {(1., 1., 1.), to_rgb(_palette(None)["U"])}
    edges = {face: (0., 0., 0.) if rgb in white else rgb
             for face, rgb in palette.items()}
    return edges, edges


def _project_cube(point, view):
    x, y, z = (coordinate - 1.5 for coordinate in point)
    if view == "BLD":
        x, y, z = y, x, -z
    return ((x + y) / sqrt(2), (-x + y + 2 * z) / sqrt(6))


def _shape_picture(axis, value, center, width, palette, mode, vertex):
    """Draw orthographic cube meshes as vector polygons on the graph axes."""
    from matplotlib.collections import LineCollection, PolyCollection

    views = ("UFR", "BLD") if mode is DiagramMode.OPPOSITE_CORNERS else ("UFR",)
    labels = value.labels
    center_blocks = {labels[_FACE_CELLS[face][4]] for face in "URFDLB"}
    panel_width = width / len(views)
    scale = panel_width / (3 * sqrt(2) * 1.08)
    for index, view in enumerate(views):
        offset = (center[0] + (index - (len(views) - 1) / 2) * panel_width, center[1])

        def project(point):
            x, y = _project_cube(point, view)
            return (offset[0] + scale * x, offset[1] + scale * y)

        surfaces, outlines = [], []
        transparent = mode is DiagramMode.TRANSPARENT
        faces_to_draw = set(_FACE_PLANES.values()) if transparent else {
            _FACE_PLANES[face] for face in view}
        for block in sorted(set(labels)):
            faces, lines = _block_mesh([cell for cell, label in enumerate(labels) if label == block],
                                      False, faces_to_draw, exterior_only=True)
            for face in faces:
                plane = next(key for key in faces_to_draw
                             if all(point[key[0]] == key[2] for point in face))
                letter = next(face for face, key in _FACE_PLANES.items() if key == plane)
                color = palette[letter] if block in center_blocks else (1., 1., 1.)
                opacity = (0.75 if block in center_blocks else 0.12) if transparent else 1.
                normal = (1, -1, 1) if view == "UFR" else (-1, 1, -1)
                depth = sum(coordinate * direction for point in face
                            for coordinate, direction in zip(point, normal))
                surfaces.append((depth, [project(point) for point in face], (*color, opacity)))
            outlines.extend([project(first), project(second)] for first, second in lines)
        surfaces.sort(key=lambda value: value[0])
        surface = PolyCollection([polygon for _, polygon, _ in surfaces],
                                 facecolors=[color for _, _, color in surfaces],
                                 edgecolors="none", zorder=5)
        surface.set_gid(f"bandage-shape-{vertex}-{view}-surface")
        axis.add_collection(surface)
        outline = LineCollection(outlines, colors="#252525", linewidths=0.5,
                                 alpha=0.6 if transparent else 1., zorder=6)
        outline.set_gid(f"bandage-shape-{vertex}-{view}-outline")
        axis.add_collection(outline)


def _positions(pos, graph, np, vertices=None):
    required = set(range(len(graph))) if vertices is None else set(vertices)
    if not isinstance(pos, Mapping) or (
            set(pos) != required and (vertices is None or set(pos) != set(range(len(graph))))):
        raise ValueError("pos must map every vertex ID to a finite 2D position")
    result = {}
    for vertex, point in pos.items():
        try:
            point = np.asarray(point, dtype=float)
        except (TypeError, ValueError) as error:
            raise ValueError("pos must contain finite 2D positions") from error
        if point.shape != (2,) or not np.isfinite(point).all():
            raise ValueError("pos must contain finite 2D positions")
        result[vertex] = tuple(point)
    return result


def _local_vertices(actions, root, *, radius, max_vertices):
    """Select a bounded neighborhood without laying out the complete graph."""
    adjacent = defaultdict(set)
    for source, target, _ in actions:
        adjacent[source].add(target)
        adjacent[target].add(source)
    vertices = {root}
    pending = deque(((root, 0),))
    while pending and len(vertices) < max_vertices:
        vertex, distance = pending.popleft()
        if distance >= radius:
            continue
        for neighbor in sorted(adjacent[vertex]):
            if neighbor in vertices:
                continue
            vertices.add(neighbor)
            pending.append((neighbor, distance + 1))
            if len(vertices) == max_vertices:
                break
    return vertices


def _summary_figure(graph, actions, *, figsize, plt):
    """Draw statistics without loading shapes, constructing geometry, or layout."""
    figure, axis = plt.subplots(figsize=figsize or (8, 3))
    axis.set_axis_off()
    status = "Complete" if graph.complete else "Partial"
    axis.set_title(f"{status} graph · {len(graph):,} shapes · "
                   f"{len(actions):,} clockwise face turns", fontsize=11)
    axis.text(0.5, 0.65, "Shape graph summary", ha="center", va="center",
              transform=axis.transAxes, fontsize=15)
    axis.text(0.5, 0.42,
              f"{graph.metric} exploration · full graph layout skipped\n"
              "Use view='local' for a bounded neighborhood, or\n"
              "view='full' to explicitly request the complete drawing.",
              ha="center", va="center", transform=axis.transAxes, fontsize=10)
    figure.tight_layout()
    return figure


def _local_layout(vertices, actions, *, layout, seed, iterations, nx):
    geometry = nx.Graph()
    geometry.add_nodes_from(sorted(vertices))
    geometry.add_edges_from((source, target) for source, target, _ in actions
                           if source != target)
    if len(vertices) == 1:
        return {next(iter(vertices)): (0., 0.)}
    if layout in ("symmetry", "spring"):
        # A neighborhood need not retain any symmetry of the whole component.
        options = {"method": "force"} if "method" in signature(nx.spring_layout).parameters else {}
        positions = nx.spring_layout(geometry, seed=seed, iterations=iterations,
                                     weight=None, **options)
    elif layout == "kamada_kawai":
        positions = nx.kamada_kawai_layout(geometry, weight=None)
    else:
        positions = nx.spectral_layout(geometry, weight=None)
    return {vertex: tuple(map(float, point)) for vertex, point in positions.items()}


def _default_figsize(positions, pairs, *, span, show_shapes, np):
    """Keep typical edges readable without producing an unbounded canvas."""
    lengths = [np.linalg.norm(np.array(positions[first]) - positions[second])
               for first, second in pairs if first != second]
    lengths = [length for length in lengths if length > span * 1e-10]
    spacing = float(np.median(lengths)) if lengths else span
    # Aim for longer edges when they need to accommodate cube pictures. The
    # initial drawing extent is 0.62 * span, with 93% of the figure height used.
    edge_inches = 1.2 if show_shapes else 0.35
    side = min(24., max(6., 1.24 * span * edge_inches / (0.93 * spacing)))
    return (side, side)


def _shape_width_limit(positions, ratios, *, span, mode, np):
    """Estimate a picture width in data units from local node clearances."""
    vertices = sorted(positions)
    points = np.array([positions[vertex] for vertex in vertices])
    weights = np.array([ratios.get(vertex, 0.) for vertex in vertices])
    nearest = []
    if len(points) > _DEFAULT_MAX_VERTICES:
        # Large drawings are opt-in. Even then, picture sizing should not add
        # another quadratic scan. A nearest-neighbor distance and the largest
        # possible partner weight give a conservative clearance for each node.
        distinct = np.unique(points, axis=0)
        if len(distinct) > 1:
            try:
                from scipy.spatial import cKDTree
            except ImportError:
                # Coordinate gaps bound every noncoincident pair's separation.
                # This conservative fallback keeps sizing linearithmic without
                # making SciPy a prerequisite for user-supplied coordinates.
                gaps = np.concatenate([np.diff(np.unique(points[:, axis])) for axis in (0, 1)])
                gap = float(np.min(gaps[gaps > 0])) if (gaps > 0).any() else 0.
                distances = np.full(len(points), gap)
            else:
                distances = cKDTree(distinct).query(points, k=2)[0][:, 1]
            visible = (weights > 0) & (distances > 0)
            nearest.extend(distances[visible] / (weights[visible] + weights.max()))
    else:
        # Hidden vertices still constrain pictures so incident short edges do
        # not disappear under a diagram. Small drawings retain exact bounds.
        for first in range(0, len(points), 128):
            last = min(first + 128, len(points))
            distances = np.linalg.norm(points[first:last, None, :] - points[None, :, :], axis=-1)
            sums = weights[first:last, None] + weights[None, :]
            limits = np.full(distances.shape, np.inf)
            valid = (distances > span * 1e-10) & (sums > 0)
            limits[valid] = distances[valid] / sums[valid]
            nearest.extend(limits.min(axis=1)[weights[first:last] > 0])
    nearest = sorted(value for value in nearest if isfinite(value))
    if not nearest:
        return 0.4 * span  # Single-node/entirely coincident layouts.
    # Ignore the tightest tenth on large layouts: a few almost coincident
    # vertices should not make every picture unreadable. Small graphs use the
    # minimum. Bounding circles leave at least 60% of typical edge lengths free.
    spacing = nearest[len(nearest) // 10]
    views = 2 if mode is DiagramMode.OPPOSITE_CORNERS else 1
    diagonal = sqrt(1 + (2 / (sqrt(3) * views))**2)
    return 0.8 * spacing / diagonal


def _drawing_extent(positions, pairs, ratios, *, center, span, shape_size,
                    show_shapes, drawing_inches, np):
    """Fit pictures, curved parallel actions, and loops without cropping them.

    Cube widths and arrow offsets are specified in physical units, so widening
    limits changes their data-space size. Iterate to fit those sizes together.
    """
    extent = 0.62 * span
    for _ in range(20):
        units = 2 * extent / drawing_inches
        radii = {vertex: (shape_size * units * ratio * 0.46 if show_shapes else
                          0.045 * units * ratio) for vertex, ratio in ratios.items()}
        needed = extent
        for vertex, ratio in ratios.items():
            half_width = shape_size * units * ratio / 2 if show_shapes else radii[vertex]
            needed = max(needed, float(np.max(np.abs(np.array(positions[vertex]) - center))) + half_width)
        for (first, second), records in pairs.items():
            for index, (source, target, _) in enumerate(records):
                a, b = np.array(positions[source]), np.array(positions[target])
                if source == target:
                    angle = 2 * pi * index / len(records)
                    outward = np.array((cos(angle), sin(angle)))
                    sideways = np.array((-sin(angle), cos(angle)))
                    radius = max(radii.get(source, 0), 0.035 * span)
                    points = (a + outward * radius * 3 + sideways * radius * 2,
                              a + outward * radius * 3 - sideways * radius * 2)
                else:
                    difference = b - a if source == first else a - b
                    curve = (index - (len(records) - 1) / 2) * 0.3
                    control = (a + b) / 2 + curve * np.array((difference[1], -difference[0]))
                    points = (control,)
                for point in points:
                    needed = max(needed, float(np.max(np.abs(point - center))) + 0.015 * span)
        if needed <= extent + span * 1e-6:
            return needed
        extent = needed
    return extent


def draw_bandage_graph(value, *, layout="symmetry", show_shapes=False,
                       edge_labels=False, face_colors=None, start=0,
                       figsize=None, shape_size=None, seed=0, iterations=300,
                       pos=None, diagram_mode=DiagramMode.OPPOSITE_CORNERS,
                       view="auto", max_vertices=_DEFAULT_MAX_VERTICES, radius=2):
    """Return a Matplotlib Figure of the single-turn shape groupoid graph.

    ``view='auto'`` draws the complete graph through ``max_vertices`` (default
    1,000), and a statistics summary above that limit. The summary performs no
    layout or shape-picture sizing. ``view='summary'`` always uses that summary;
    ``view='local'`` draws at most ``max_vertices`` within ``radius`` undirected
    quarter-turn steps of ``start``, retaining original vertex IDs. Local
    ``symmetry`` layout falls back to spring because the selected neighborhood
    need not preserve the component's rotations. ``view='full'`` explicitly
    requests the complete drawing, including potentially expensive layouts.

    Accept a ShapeGraph or any bandage accepted by ``explore``. Only positive
    U/R/F/D/L/B quarter-turn actions are drawn, even from an HTM graph. Every
    retained vertex and arc participates in a full drawing; degree-two markers/diagrams are hidden
    except for ``start`` (a vertex ID or shape), which always has maximum size.
    Degree counts incident positive arcs, with loops counted twice.

    Set ``show_shapes=True`` for miniature orthographic shape diagrams. Their
    linear sizes are proportional to degree; ``shape_size`` is the maximum
    diagram width in inches. With ``figsize=None``, edge spacing selects a square
    figure between 6 and 24 inches. With ``shape_size=None``, nearby vertices
    limit picture widths to leave room for edges, accounting for degree and
    diagram mode. Very close/coincident vertices may still overlap. Either size
    can be overridden independently. Arbitrary blocks are white. Exterior
    stickers of blocks containing fixed face centers use the displayed face's palette,
    with white face colors rendered black to match their edges.
    ``diagram_mode`` selects two opposite corners or one transparent view.
    Face colors also color edges; white (including the default near-white U)
    becomes black. ``edge_labels=True`` adds black Singmaster letters. ``pos`` accepts
    precomputed/manual coordinates for every full-view vertex, or just the
    selected local vertices. Partial explorations are clearly titled.
    Save the returned Figure as SVG/PDF to retain vector cube diagrams.
    """
    if not isinstance(view, str) or view not in _VIEWS:
        raise ValueError(f"view must be one of {_VIEWS}")
    if isinstance(max_vertices, bool) or not isinstance(max_vertices, int) or max_vertices <= 0:
        raise ValueError("max_vertices must be a positive integer")
    if isinstance(radius, bool) or not isinstance(radius, int) or radius < 0:
        raise ValueError("radius must be a nonnegative integer")
    if not isinstance(layout, str) or layout not in _LAYOUTS:
        raise ValueError(f"layout must be one of {_LAYOUTS}")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
        raise ValueError("iterations must be a nonnegative integer")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in 0..2**32-1")
    for name, flag in (("show_shapes", show_shapes), ("edge_labels", edge_labels)):
        if type(flag) is not bool:
            raise TypeError(f"{name} must be a boolean")
    if shape_size is not None and (
            isinstance(shape_size, bool) or not isinstance(shape_size, (int, float))
            or not isfinite(shape_size) or shape_size <= 0):
        raise ValueError("shape_size must be positive and finite")
    if figsize is not None:
        try:
            figsize = tuple(float(value) for value in figsize)
        except (TypeError, ValueError) as error:
            raise ValueError("figsize needs two positive finite dimensions") from error
        if len(figsize) != 2 or any(not isfinite(value) or value <= 0 for value in figsize):
            raise ValueError("figsize needs two positive finite dimensions")
    try:
        mode = DiagramMode(diagram_mode)
    except (TypeError, ValueError) as error:
        raise ValueError("diagram_mode must be a DiagramMode member") from error
    graph = _graph(value)
    root = graph._vertex(start)
    try:
        import matplotlib.pyplot as plt
        from matplotlib.path import Path
        from matplotlib.patches import Circle, FancyArrowPatch
    except ImportError as error:
        raise ImportError("install bandaged-cube-explorer-v2[graph,plots] "
                          "to draw bandage graphs") from error
    actions = _actions(graph)
    if view == "summary" or (view == "auto" and len(graph) > max_vertices):
        return _summary_figure(graph, actions, figsize=figsize, plt=plt)
    nx, np = _dependencies()
    palette, edge_colors = _palette_rgb(face_colors)
    if view == "local":
        vertices = _local_vertices(actions, root, radius=radius, max_vertices=max_vertices)
        actions = tuple(action for action in actions
                        if action[0] in vertices and action[1] in vertices)
        if pos is None:
            positions = _local_layout(vertices, actions, layout=layout, seed=seed,
                                      iterations=iterations, nx=nx)
        else:
            positions = {vertex: point for vertex, point in _positions(pos, graph, np, vertices).items()
                         if vertex in vertices}
    else:
        vertices = range(len(graph))
        positions = (_positions(pos, graph, np) if pos is not None else
                     bandage_graph_layout(graph, layout=layout, seed=seed, iterations=iterations))
    degrees = Counter(vertex for source, target, _ in actions for vertex in (source, target))
    maximum = max(degrees.values(), default=1)
    visible = {vertex for vertex in vertices if degrees[vertex] != 2 or vertex == root}
    ratios = {vertex: (1. if vertex == root else max(degrees[vertex], 1) / maximum)
              for vertex in visible}
    pairs = defaultdict(list)
    for action in actions:
        pairs[tuple(sorted(action[:2]))].append(action)
    coordinates = np.array(list(positions.values()))
    low, high = coordinates.min(axis=0), coordinates.max(axis=0)
    span = float((high - low).max()) or 1.
    center = (low + high) / 2
    if figsize is None:
        figsize = _default_figsize(positions, pairs, span=span, show_shapes=show_shapes, np=np)
    # Equal aspect leaves a square drawing area even on rectangular figures.
    drawing_inches = min(figsize[0] * 0.96, figsize[1] * 0.93)
    automatic_shapes = shape_size is None and show_shapes
    if shape_size is None:
        shape_size = 1.2 if mode is DiagramMode.OPPOSITE_CORNERS else 0.8
    extent = _drawing_extent(positions, pairs, ratios, center=center, span=span,
                             shape_size=shape_size, show_shapes=show_shapes,
                             drawing_inches=drawing_inches, np=np)
    if automatic_shapes:
        width_limit = _shape_width_limit(positions, ratios, span=span, mode=mode, np=np)
        shape_size = min(shape_size, width_limit * drawing_inches / (2 * extent))
        # Smaller pictures can only reduce the required extent, so this second
        # fit preserves the clearance calculated from the first fit.
        extent = _drawing_extent(positions, pairs, ratios, center=center, span=span,
                                 shape_size=shape_size, show_shapes=show_shapes,
                                 drawing_inches=drawing_inches, np=np)
    figure, axis = plt.subplots(figsize=figsize)
    figure.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.95)
    axis.set_aspect("equal")
    axis.set_axis_off()
    axis.set(xlim=(center[0] - extent, center[0] + extent),
             ylim=(center[1] - extent, center[1] + extent))
    units_per_inch = 2 * extent / drawing_inches
    widths = {vertex: shape_size * units_per_inch * ratio for vertex, ratio in ratios.items()}
    radii = {vertex: (widths[vertex] * 0.46 if show_shapes else
                      0.045 * units_per_inch * ratio) for vertex, ratio in ratios.items()}
    for (first, second), records in pairs.items():
        for index, (source, target, move) in enumerate(records):
            a, b = np.array(positions[source]), np.array(positions[target])
            label_point = (a + b) / 2
            if source == target:
                angle = 2 * pi * index / len(records)
                outward = np.array((cos(angle), sin(angle)))
                sideways = np.array((-sin(angle), cos(angle)))
                radius = max(radii.get(source, 0), 0.035 * span)
                start_point = a + outward * radius + sideways * radius * 0.3
                end_point = a + outward * radius - sideways * radius * 0.3
                path = Path([start_point, a + outward * radius * 3 + sideways * radius * 2,
                             a + outward * radius * 3 - sideways * radius * 2, end_point],
                            [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
                arrow = FancyArrowPatch(path=path, arrowstyle="-|>", mutation_scale=8,
                                        linewidth=0.9, color=edge_colors[move], zorder=1)
                label_point = a + outward * radius * 2.5
            else:
                canonical = b - a if source == first else a - b
                distance = np.linalg.norm(canonical)
                if distance < 1e-10:
                    # Supplied/spectral coincident coordinates still retain an arc.
                    b = b + np.array((0.02 * span, 0.02 * span))
                    canonical = b - a if source == first else a - b
                    distance = np.linalg.norm(canonical)
                curve = (index - (len(records) - 1) / 2) * 0.3
                curvature = curve if source == first else -curve
                arrow = FancyArrowPatch(a, b, connectionstyle=f"arc3,rad={curvature}",
                                        arrowstyle="-|>", mutation_scale=7,
                                        shrinkA=radii.get(source, 0) / units_per_inch * 72,
                                        shrinkB=radii.get(target, 0) / units_per_inch * 72,
                                        linewidth=0.8, color=edge_colors[move], zorder=1)
                normal = np.array((canonical[1], -canonical[0])) / distance
                label_point += normal * curve * distance * 0.5
            arrow.set_gid(f"bandage-edge-{source}-{target}-{move}")
            axis.add_patch(arrow)
            if edge_labels:
                label = axis.text(*label_point, move, color="black", fontsize=6,
                                  ha="center", va="center", zorder=7,
                                  bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.15})
                label.set_gid(f"bandage-label-{source}-{target}-{move}")
    for vertex in sorted(visible):
        if show_shapes:
            _shape_picture(axis, graph[vertex], positions[vertex], widths[vertex],
                           palette, mode, vertex)
        else:
            marker = Circle(positions[vertex], radius=radii[vertex],
                            facecolor="#253858" if vertex == root else "#6c7785",
                            edgecolor="white", linewidth=0.4, zorder=5)
            marker.set_gid(f"bandage-node-{vertex}")
            axis.add_patch(marker)
    status = "" if graph.complete else "Partial graph · "
    if view == "local":
        title = (f"{status}Local view · {len(vertices):,} of {len(graph):,} shapes · "
                 f"{len(actions):,} clockwise face turns")
    else:
        title = f"{status}{len(graph):,} shapes · {len(actions):,} clockwise face turns"
    axis.set_title(title, fontsize=11)
    return figure


__all__ = ["bandage_graph_layout", "draw_bandage_graph"]
