# -*- coding: utf-8 -*-
"""
Created on Sat Sep  9 17:32:06 2017

@author: Ladislav
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
    
    return res


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

shortest_path(g, mixed, cube1, labels)

#pos = nx.spring_layout(g)
#nx.draw_networkx_edges(g, pos, width=1, alpha=0.5)
#nx.draw_networkx_edge_labels(g, pos, labels, font_size=8)
# https://networkx.github.io/documentation/networkx-1.9/examples/drawing/labels_and_colors.html

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for k, v in dist.items():
    if v == 16:
        print(k)

cen = nx.closeness_centrality(g)
c = max(cen.values())
for k, v in cen.items():
    if v > c - 0.01:
        print(k)

# eccentricity, radius


# GRAPHICS - DISPLAY BANDAGE SHAPE
#import matplotlib as mpl
#from mpl_toolkits.mplot3d import Axes3D
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


def _draw_block(ax, at, size, alpha, color):
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
    if y0 == 0: # always draw global front face
        faces.append([V[0], V[1], V[5], V[4]])
    if z0 + z == 3: # always draw global up face
        faces.append([V[4], V[5], V[6], V[7]])
    if alpha < 1: # if transparency is wanted, draw all sides for any block
        faces = [[V[0], V[1], V[2], V[3]], # down
                 [V[4], V[5], V[6], V[7]], # up
                 [V[1], V[5], V[6], V[2]], # right
                 [V[0], V[4], V[7], V[3]], # left
                 [V[0], V[1], V[5], V[4]], # front
                 [V[2], V[6], V[7], V[3]]] # back

    collection = Poly3DCollection(faces, linewidths=3, edgecolors="black")
    collection.set_facecolor((*color, alpha))
    #collection.set_edgecolor((1, 1, 1, 0.1))
    ax.add_collection3d(collection)


def draw_cube(cube, alpha=1, color=(1, 1, 1)):
    """ Draw given bandage shape in given color (r, g, b), 0 <= r, g, b <= 1
    and transparency 0 <= alpha <= 1. """
    fig = plt.figure(figsize=(7, 7))
    ax = fig.gca(projection='3d')
    ax.set_axis_off()
    ax.axis("scaled")
    ax.set_xlim3d(0, 3)
    ax.set_ylim3d(0, 3)
    ax.set_zlim3d(0, 3)
   
    # rotate so that "code graphic" for cube input matches drawing orientation
    rcube = list(itemgetter(24,15,6,21,12,3,18,9,0,25,16,7,22,13,4,\
                            19,10,1,26,17,8,23,14,5,20,11,2)(cube))
    rev = rcube[::-1]
   
    # deprecated: sorting blocks trying to affect drawing order
    # blocks = map(itemgetter(-1),
    #              sorted([(len(list(v)), k) for k, v in groupby(sorted(cube1))]))
    blocks = set(cube)
   
    for block in blocks:
        # swap "rev" and "rcube" to get backview - might add as an option later
        x0, y0, z0 = _ternary(rcube.index(block))
        x1, y1, z1 = _ternary(len(rcube) - 1 - rev.index(block))
        x, y, z = min(x0, x1), min(y0, y1), min(z0, z1)
        _draw_block(ax, (x, y, z), (1 + abs(x1 - x0), 1 + abs(y1 - y0),
            1 + abs(z1 - z0)), alpha, color)
    plt.show()


def _draw_block_old(ax, at, size, c):
    """ Draw wireframe of block. Deprecated as subsumed in new draw_block. """
    x0, y0, z0, x, y, z = *at, *size
    xs = np.asarray([0,x-c,x-c,x-c,x-c,x-c,x-c,0,0,0,0,0,x-c,x-c,0,0])
    ys = np.asarray([0,0,0,0,y-c,y-c,y-c,y-c,y-c,y-c,0,0,0,y-c,y-c,0])
    zs = np.asarray([0,0,z-c,0,0,z-c,0,0,z-c,0,0,z-c,z-c,z-c,z-c,z-c])
    if x == y == z == 1:
        color = (0.4, 0.4, 0.4, 0.2)
    else:
        color = (0, 0, 1)
    ax.plot(xs + x0, ys + y0, zs + z0, color=color) 
