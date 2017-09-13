# -*- coding: utf-8 -*-
"""
BANDAGED CUBE EXPLORER

@author: Ladislav Dubravský
"""

import copy
import networkx as nx
from operator import itemgetter

# face index sets
FACES = {"L": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (0,)],
         "R": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (2,)],
         "B": [a*9 + b*3 + c for a in (0,1,2) for b in (0,) for c in (0,1,2)],
         "F": [a*9 + b*3 + c for a in (0,1,2) for b in (2,) for c in (0,1,2)],
         "U": [a*9 + b*3 + c for a in (0,) for b in (0,1,2) for c in (0,1,2)],
         "D": [a*9 + b*3 + c for a in (2,) for b in (0,1,2) for c in (0,1,2)]}


def turnable(face, cube):
    """ Is a face turnable on a cube? """
    # turnable if no block spans both the face and its complement
    faceblocks = set([cube[i] for i in face])
    restblocks = set([cube[i] for i in set(range(27)) - set(face)])
    return False if faceblocks & restblocks else True


def _rotate(fc):
    """ Rotate a length-9 list representing a layer 90 degrees. """
    return [fc[6], fc[3], fc[0], fc[7], fc[4], fc[1], fc[8], fc[5], fc[2]]


def turn(face, cube):
    """ Do a single face turn and return the new cube. """
    facecontent = [cube[i] for i in range(27) if i in face]
    turned = _rotate(facecontent)
    if face[0] == 2: # right face, rotate clockwise as conventional
        turned = _rotate(_rotate(turned))
    newcube = copy.deepcopy(cube) # consider list(cube)
    for i, fi in enumerate(face):
        newcube[fi] = turned[i]
    return normalize(newcube)


def normalize(cube):
    """ Normalize a cubelist to get unique bandage shape representation. """
    # handle zeros, which represent non-connected cubies, first
    blockno = 1 + max([1] + cube)
    for i, v in enumerate(cube):
        if v == 0:
            cube[i] = blockno
            blockno += 1

    # now re-number blocks in reading order
    blockno = 1
    mapping = {}
    for v in cube:
        if v in mapping:
            continue
        else:
            mapping[v] = blockno
            blockno += 1
    return list(map(lambda x: mapping[x], cube))


def explore(initcube):
    """ Breadth-first explore puzzle from given bandage state. """
    norm = normalize(initcube)
    verts, edges, tovisit = [], [], [norm]
    edgelabels = {}
    cube2int, int2cube = {}, {} # bijection for short repre of cube as int
    cube2int[tuple(norm)] = 0
    int2cube[0] = norm
    counter = 0 # counter of discovered vertices used for their short labeling

    while tovisit:
        cube = tovisit.pop(0)
        verts.append(cube2int[tuple(cube)])
        for facename, face in FACES.items():
            if turnable(face, cube):
                new = turn(face, cube)
                if tuple(new) not in cube2int:
                    tovisit.append(new)
                    counter += 1
                    cube2int[tuple(new)] = counter
                    int2cube[counter] = new
                newedge = (cube2int[tuple(cube)], cube2int[tuple(new)])
                edges.append(newedge)
                edgelabels[newedge] = facename

    return verts, edges, edgelabels, int2cube, cube2int


def shortest_path(g, scrambled, solved, labels, c2i):
    """ Given graph g, its edge labels labels and a cube2int dictionary, all as
    returned by the explore function, output shortest path from scrambled to
    solved, where scrambled and solved are bandage shapes represented by
    cubelists. Output is in standard move notation. """
    path = nx.dijkstra_path(g,
                            c2i[tuple(normalize(mixed))],
                            c2i[tuple(normalize(cube1))])
    path = zip(path, path[1:])
    res = ["dummy"]
    for e in path:
        new = labels[e] if e in labels else labels[(e[1], e[0])] + "'"
        if res[-1] == new:
            res[-1] = res[-1][0] + "2"
        else:
            res.append(new)
    return " ".join(res[1:])


def do(cube, moves):
    """ Execute a move sequence in standard notation on given cube and return
    result. If impossible return index of first impossible turn. """
    res = copy.deepcopy(cube)
    for i, move in enumerate(moves.split()):
        face = FACES[move[0]]
        if not turnable(face, cube):
            raise Exception(" ".join(["Face", move, "at move number",
                                      str(i + 1), "cannot be turned!"]))
        if move in ["U", "D", "R", "L", "F", "B"]:
            res = turn(face, res)
        if move in ["U2", "D2", "R2", "L2", "F2", "B2"]:
            res = turn(face, turn(face, res))
        if move in ["U'", "D'", "R'", "L'", "F'", "B'"]:
            res = turn(face, turn(face, turn(face, res)))
    return res


def distance(s1, s2):
    """ Modified Hamming distance to measure similarity of strings representing
    cubie relationship with its various neighbors. """
    return sum(c1 != c2 for c1, c2 in zip(s1, s2))


# cube input
cube1 = [   1,1,0,
           1,1,0,
          0,0,0,
            2,2,7,
           2,2,6,
          3,4,5,
            2,2,7,
           2,2,6,
          3,4,5   ]
mixed = [   0,0,0,
           0,1,1,
          0,1,1,
            2,2,7,
           2,2,6,
          3,4,5,
            2,2,7,
           2,2,6,
          3,4,5   ]
verts, edges, labels, i2c, c2i = explore(cube1)
g = nx.Graph(edges)

shortest_path(g, mixed, cube1, labels, c2i)

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for k, v in dist.items():
    if v == 16:
        print(k)

# number of shapes at given distance
for i in range(20):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))


# graph drawing - probably easiest to fall back to Mathematica for really nice graphs
# pos = nx.spring_layout(g)
# nx.draw_networkx_edges(g, pos, width=1, alpha=0.5)
# nx.draw_networkx_edge_labels(g, pos, labels, font_size=8)
# https://networkx.github.io/documentation/networkx-1.9/examples/drawing/labels_and_colors.html


# GRAPHICS - DISPLAY BANDAGE SHAPE
# import matplotlib as mpl
# from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def _ternary(dec):
    """ Convert list index to ternary, giving three space coordinates. """
    res = []
    n = dec
    while n > 0:
        res.insert(0, n % 3)
        n = n // 3
    return [0]*(3 - len(res)) + res


def _draw_block(ax, at, size, alpha, color, lwidth):
    """ Construct a 3d block object and append it to the passed AxesSubplot
    object to be drawn later.
        For opaque (alpha=1) drawing, we need to take care of not drawing
    things that are not visible ourselves, because of mpl's likely
    unsalvageably buggy drawing (z)order. """
    x0, y0, z0, x, y, z = *at, *size
    V = np.array([[x0,     y0,     z0    ],
                  [x0 + x, y0,     z0    ],
                  [x0 + x, y0 + y, z0    ],
                  [x0,     y0 + y, z0    ],
                  [x0,     y0,     z0 + z],
                  [x0 + x, y0,     z0 + z],
                  [x0 + x, y0 + y, z0 + z],
                  [x0,     y0 + y, z0 + z]])

    faces = []
    if x0 + x == 3: # always draw global right face
        faces.append([V[1], V[5], V[6], V[2]])
    if y0 == 0:     # always draw global front face
        faces.append([V[0], V[1], V[5], V[4]])
    if z0 + z == 3: # always draw global up face
        faces.append([V[4], V[5], V[6], V[7]])
    if alpha < 1:   # if transparency, draw all sides for any block
        faces = [[V[0], V[1], V[2], V[3]], # down
                 [V[4], V[5], V[6], V[7]], # up
                 [V[1], V[5], V[6], V[2]], # right
                 [V[0], V[4], V[7], V[3]], # left
                 [V[0], V[1], V[5], V[4]], # front
                 [V[2], V[6], V[7], V[3]]] # back

    collection = Poly3DCollection(faces, linewidths=lwidth, edgecolors="black")
    collection.set_facecolor((*color, alpha))
    # collection.set_edgecolor((1, 1, 1, 0.1))
    ax.add_collection3d(collection)


def draw_cubes(cubes, alpha=1, color=(1, 1, 1), size=4, linewidth=2, ncol=3):
    """ Draw one or several bandage shapes in a grid layout.
    0 <= alpha <= 1: transparency
    color = (r, g, b), 0 <= r, g, b <= 1: color
    size: size of one cube drawing
    linewidth: line width
    ncol: number of figures per row """
    if not hasattr(cubes[0], "__len__"): # if single cube is input
        cubes_ = [cubes]
    else:
        cubes_ = cubes

    cnt = len(cubes_)
    fig = plt.figure(figsize=((ncol * size, (cnt // ncol + 1)*size)))
    for i, cube in enumerate(cubes_):
        # rotate so that "code graphic" for cube input matches drawing orientation
        rcube = list(itemgetter(24, 15, 6, 21, 12, 3, 18, 9,  0,
                                25, 16, 7, 22, 13, 4, 19, 10, 1,
                                26, 17, 8, 23, 14, 5, 20, 11, 2)(cube))
        rev = rcube[::-1]
        blocks = set(cube)
   
        ax = fig.add_subplot(cnt // ncol + 1, ncol, 1 + i, projection="3d")
        ax.set_axis_off()
        ax.axis("scaled")
        ax.set_xlim3d(0, 3)
        ax.set_ylim3d(0, 3)
        ax.set_zlim3d(0, 3)
        for block in blocks:
            # swap "rev" and "rcube" for backview - maybe add an option later
            x0, y0, z0 = _ternary(rcube.index(block))
            x1, y1, z1 = _ternary(len(rcube) - 1 - rev.index(block))
            x, y, z = min(x0, x1), min(y0, y1), min(z0, z1)
            _draw_block(ax, (x, y, z), (1 + abs(x1 - x0), 1 + abs(y1 - y0),
                1 + abs(z1 - z0)), alpha, color, linewidth)

    plt.subplots_adjust(wspace=0, hspace=0)
    plt.show()
