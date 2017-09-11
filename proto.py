# -*- coding: utf-8 -*-
"""
Created on Sat Sep  9 17:32:06 2017

@author: Ladislav
"""

import copy
import networkx as nx
import pygraphviz as pgv
from operator import itemgetter
from itertools import groupby

# face index sets
FACES = {"U": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (0,)],
         "D": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (2,)],
         "L": [a*9 + b*3 + c for a in (0,1,2) for b in (0,) for c in (0,1,2)],
         "R": [a*9 + b*3 + c for a in (0,1,2) for b in (2,) for c in (0,1,2)],
         "B": [a*9 + b*3 + c for a in (0,) for b in (0,1,2) for c in (0,1,2)],
         "F": [a*9 + b*3 + c for a in (2,) for b in (0,1,2) for c in (0,1,2)]}


# turnability test - no block spans both the face and its complement
def turnable(face, cube):
    faceblocks = set([cube[i] for i in face])
    restblocks = set([cube[i] for i in set(range(27)) - set(face)])
    if faceblocks & restblocks:
        return False
    else:
        return True


# rotate length-9 list representing a layer 90 degrees clockwise
def rotate(fc):
    return [fc[6], fc[3], fc[0], fc[7], fc[4], fc[1], fc[8], fc[5], fc[2]]


# turn a face and return the new cube
def turn(face, cube):
    facecontent = [cube[i] for i in range(27) if i in face]
    turned = rotate(facecontent)
    newcube = copy.deepcopy(cube) # consider list(cube)
    for i, fi in enumerate(face):
        newcube[fi] = turned[i]
    return normalize(newcube)


# normalize block numbering to get unique cube representation
def normalize(cube):
    # handle zeros, which represent non-connected cubies, first
    blockno = 1 + max([1] + cube)
    for i, v in enumerate(cube):
        if v == 0:
            cube[i] = blockno
            blockno += 1

    # now number blocks in reading order
    blockno = 1
    mapping = {}
    for v in cube:
        if v in mapping:
            continue
        else:
            mapping[v] = blockno
            blockno += 1
    return list(map(lambda x: mapping[x], cube))


# breadth-first explore puzzle from given bandage state
def explore(initcube):
    verts, edges, tovisit = [], [], [initcube]
    edgelabels = {}
    cube2int, int2cube = {}, {} # bijection for short repre of cube as int
    cube2int[tuple(initcube)] = 0
    int2cube[0] = initcube
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


# cube input
cube1 = [   2,2,0,
           2,2,0,
          0,0,0,
            1,1,7,
           1,1,6,
          3,4,5,
            1,1,7,
           1,1,6,
          3,4,5   ]
cube1 = normalize(cube1)
verts, edges, labels, _, _ = explore(cube1)

g = nx.Graph(edges)
pos = nx.spring_layout(g)
nx.draw_networkx_edges(g, pos, width=1, alpha=0.5)
nx.draw_networkx_edge_labels(g, pos, labels, font_size=8)

plt.show()
# https://networkx.github.io/documentation/networkx-1.9/examples/drawing/labels_and_colors.html



# graphics - display bandage
import matplotlib as mpl
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import matplotlib.pyplot as plt

def draw_block(ax, at, size, c):
    x0, y0, z0, x, y, z = *at, *size
    xs = np.asarray([0,x-c,x-c,x-c,x-c,x-c,x-c,0,0,0,0,0,x-c,x-c,0,0])
    ys = np.asarray([0,0,0,0,y-c,y-c,y-c,y-c,y-c,y-c,0,0,0,y-c,y-c,0])
    zs = np.asarray([0,0,z-c,0,0,z-c,0,0,z-c,0,0,z-c,z-c,z-c,z-c,z-c])
    if x == y == z == 1:
        color = (0.8, 0.8, 0.8)
    else:
        color = (0, 0, 1)
    ax.plot(xs + x0, ys + y0, zs + z0, color=color)


def ternary(dec):
    res = []
    n = dec
    while n > 0:
        res.insert(0, n % 3)
        n = n // 3
    return [0]*(3 - len(res)) + res


def draw_cube(cube, margin=0):
    fig = plt.figure()
    ax = fig.gca(projection='3d')
    ax.set_axis_off()
    
    # rotate so that "code graphic" for cube input matches picture orientation
    rcube = list(itemgetter(24,15,6,21,12,3,18,9,0,25,16,7,22,13,4,\
                            19,10,1,26,17,8,23,14,5,20,11,2)(cube))
    rev = rcube[::-1]
    
    # sort to draw 1x1 cubies first so they'll be drawn BELOW larger blocks
    blocks = map(itemgetter(-1),
                 sorted([(len(list(v)), k) for k, v in groupby(sorted(cube1))]))
    
    for block in blocks:
        x0, y0, z0 = ternary(rcube.index(block))
        x1, y1, z1 = ternary(len(rcube) - 1 - rev.index(block))
        x, y, z = min(x0, x1), min(y0, y1), min(z0, z1)
        draw_block(ax, (x, y, z), (1 + abs(x1 - x0), 1 + abs(y1 - y0), 1 + abs(z1 - z0)), margin)
    plt.show()

# do second method with matplotlib lines lines2D
