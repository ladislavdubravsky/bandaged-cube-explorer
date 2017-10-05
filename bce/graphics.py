# -*- coding: utf-8 -*-
"""
Provides drawing capability for bandaged cube exploration: function draw_cubes.
"""

import copy
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from operator import itemgetter
from . import core


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
    Parameters:
        cubes:     a single cubelist or a list of cubelists
        alpha:     transparency, 0 <= alpha <= 1
        color:     color in format (r, g, b), 0 <= r, g, b <= 1
        size:      size of single figure
        linewidth: line width
        ncol:      number of figures per row
    """
    if not hasattr(cubes[0], "__len__"): # if single cube is input
        cubes_ = [cubes]
    else:
        cubes_ = cubes

    cnt = len(cubes_)
    fig = plt.figure(figsize=((ncol * size, (cnt // ncol + 1)*size)))
    for i, cube in enumerate(cubes_):
        cube = core.normalize(copy.deepcopy(cube))
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
