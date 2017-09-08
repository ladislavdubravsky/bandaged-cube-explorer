# -*- coding: utf-8 -*-
"""
Created on Wed Sep  6 19:14:20 2017

@author: Lenovo
"""

import copy
import networkx as nx

# face index sets
U = [a*9 + b*3 + c for a in range(0,3) for b in range(0,3) for c in range(0,1)]
D = [a*9 + b*3 + c for a in range(0,3) for b in range(0,3) for c in range(2,3)]
R = [a*9 + b*3 + c for a in range(0,3) for b in range(0,1) for c in range(0,3)]
L = [a*9 + b*3 + c for a in range(0,3) for b in range(2,3) for c in range(0,3)]
F = [a*9 + b*3 + c for a in range(0,1) for b in range(0,3) for c in range(0,3)]
B = [a*9 + b*3 + c for a in range(2,3) for b in range(0,3) for c in range(0,3)]
FACES = [U, D, R, L, F, B]


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
    newcube = copy.deepcopy(cube)
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
cube1 = [1,1] + [i+2 for i in range(25)]
cube1 = normalize([1,1,2,1,1,2,0,0,0,1,1,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0])
verts, edges, tovisit = [], [], []
full2int, int2full = {}, {}
counter = 0

def visit(cube):
    global verts, edges, tovisit, FACES
    verts.append(cube)
    for face in FACES:
        if turnable(face, cube):
            new = turn(face, cube)
            edges.append([cube, new])
            if new not in verts:
                tovisit.append(new)
    if tovisit:
        visit(tovisit.pop(0))


# graphics - display bandage
import matplotlib as mpl
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import matplotlib.pyplot as plt

def draw_block(ax, at, size):
    x0, y0, z0, x, y, z = *at, *size
    c = 0
    xs = np.asarray([0,x-c,x-c,x-c,x-c,x-c,x-c,0,0,0,0,0,x-c,x-c,0,0])
    ys = np.asarray([0,0,0,0,y-c,y-c,y-c,y-c,y-c,y-c,0,0,0,y-c,y-c,0])
    zs = np.asarray([0,0,z-c,0,0,z-c,0,0,z-c,0,0,z-c,z-c,z-c,z-c,z-c])
    ax.plot(xs + x0, ys + y0, zs + z0, color="blue")


fig = plt.figure()
ax = fig.gca(projection='3d')
x = np.asarray([0,0.9,0.9,0,0,0,0.9,0.9,0,0])
y = np.asarray([0,0,0.9,0.9,0,0,0,0.9,0.9,0])
z = np.asarray([0,0,0,0,0,0.9,0.9,0.9,0.9,0.9])
#ax.plot(x, y, z, color="blue")
#ax.set_xticks([0,1,2])
#ax.set_yticks([0,1,2])
#ax.set_zticks([0,1,2])
[draw_block(ax, (i,j,k), (1,1,1)) for i in range(3) for j in range(3) for k in range(3)]

def draw_cube(cube):
    pass

plt.show()
