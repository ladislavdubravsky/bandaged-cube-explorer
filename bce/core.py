# -*- coding: utf-8 -*-
"""
Core functions for bandaged cube exploration.
"""

import copy
import re
import networkx as nx
from collections import Counter


UBL = 0
UB  = 1
UBR = 2
UL  = 3
U   = 4
UR  = 5
UFL = 6
UF  = 7
UFR = 8
BL  = 9
B   = 10
BR  = 11
L   = 12
C   = 13
R   = 14
FL  = 15
F   = 16
FR  = 17
DBL = 18
DB  = 19
DBR = 20
DL  = 21
D   = 22
DR  = 23
DFL = 24
DF  = 25
DFR = 26


FACES = {"L": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (0,)],
         "M": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (1,)],
         "R": [a*9 + b*3 + c for a in (0,1,2) for b in (0,1,2) for c in (2,)],
         "B": [a*9 + b*3 + c for a in (0,1,2) for b in (0,) for c in (0,1,2)],
         "S": [a*9 + b*3 + c for a in (0,1,2) for b in (1,) for c in (0,1,2)],
         "F": [a*9 + b*3 + c for a in (0,1,2) for b in (2,) for c in (0,1,2)],
         "U": [a*9 + b*3 + c for a in (0,) for b in (0,1,2) for c in (0,1,2)],
         "E": [a*9 + b*3 + c for a in (1,) for b in (0,1,2) for c in (0,1,2)],
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


def turn(face, cube, fullperm=False):
    """ Do a single face turn and return the new cube. """
    facecontent = [cube[i] for i in range(27) if i in face]
    turned = _rotate(facecontent)
    if face[0] in [1, 2]: # if R or M face, rotate clockwise as conventional!
        turned = _rotate(_rotate(turned))
    newcube = copy.deepcopy(cube) # consider list(cube)
    for i, fi in enumerate(face):
        newcube[fi] = turned[i]
    return newcube if fullperm else normalize(newcube)


def normalize(cube, keepzeros=False):
    """ Normalize a cubelist to get unique bandage shape representation. You
    don't normally need to be calling this. """
    # handle zeros, which represent non-connected cubies, first
    if not keepzeros:
        blockno = 1 + max([1] + cube)
        for i, v in enumerate(cube):
            if v == 0:
                cube[i] = blockno
                blockno += 1

    # now re-number blocks in reading order
    blockno = 1
    mapping = {0: 0}
    for v in cube:
        if v in mapping or v == 0:
            continue
        else:
            mapping[v] = blockno
            blockno += 1
    return list(map(lambda x: mapping[x], cube))


def explore(initcube, fullperm=False):
    """ Breadth-first explore puzzle from given bandage state. """
    norm = copy.deepcopy(initcube)
    norm = norm if fullperm else normalize(norm)
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
            if facename in "UDRLFB" and turnable(face, cube):
                new = turn(face, cube, fullperm=fullperm)
                if tuple(new) not in cube2int:
                    tovisit.append(new)
                    counter += 1
                    cube2int[tuple(new)] = counter
                    int2cube[counter] = new
                newedge = (cube2int[tuple(cube)], cube2int[tuple(new)])
                edges.append(newedge)
                edgelabels[newedge] = facename

    return verts, edges, edgelabels, int2cube, cube2int


def shortest_path(g, mixed, solved, labels, c2i):
    """ Given graph g, its edge labels labels and a cube2int dictionary, all as
    returned by the explore function, output shortest path from mixed to
    solved, where mixed and solved are bandage shapes represented by
    cubelists or integers. Output is in standard move notation. """
    vfrom = mixed if type(mixed) == int else c2i[tuple(normalize(mixed))]
    vto = solved if type(solved) == int else c2i[tuple(normalize(solved))]
    path = nx.dijkstra_path(g, vfrom, vto)
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
    result. If impossible because of bandaging raises exception. """
    res = normalize(copy.deepcopy(cube))
    # unravel X2s and X's
    moves = re.sub("([UDRLFBESMxyz])2", r"\1 \1", moves)
    moves = re.sub("([UDRLFBESMxyz])'", r"\1 \1 \1", moves)
    for move in moves.split():
        if move == "x":
            res = turn(FACES["R"], res)
            res = turn(FACES["M"], res)
            res = turn(FACES["L"], turn(FACES["L"], turn(FACES["L"], res)))
        if move == "y":
            res = turn(FACES["F"], res)
            res = turn(FACES["S"], res)
            res = turn(FACES["B"], res)
        if move == "z":
            res = turn(FACES["U"], res)
            res = turn(FACES["E"], res)
            res = turn(FACES["D"], res)

        if move not in "UDRLFBESM":
            continue
        face = FACES[move]
        if not turnable(face, res):
            raise Exception(" ".join(["Face", move, "cannot be turned!"]))
        res = turn(face, res)
    return res


def layers_distance(g, layers, dist=None, tally=False):
    """ Calculates either the largest shortest distance, or a full distribution
    of distances (if tally=True), between a vertex from layer[i] and a vertex
    from layer[i + 1] in graph g, for all consecutive layer pairs.
    If dictionary of distances dist is not supplied, it is calculated as
    nx.shortest_path_length(g).
    This function is typically called to assess feasibility of cube solving
    via a particular stabilizer chain / feature chain. """
    d = nx.shortest_path_length(g) if not dist else dist
    fnc = Counter if tally else max
    return [fnc(min(d[i][j] for j in layers[n + 1])
                for i in layers[n] - layers[n + 1])
                for n in range(len(layers) - 1)]


def path_to_next_layer(g, v, layers, dist, labels, c2i):
    """ For a graph, its vertex and layering, output shortest path from vertex
    to the next layer. """
    try:
        ind = [v in layer for layer in layers].index(False)
    except ValueError:
        print("Vertex lies in final layer!")
        return
    mindist = min(dist[v][w] for w in layers[ind])
    verts = [w for w in layers[ind] if dist[v][w] == mindist]
    return shortest_path(g, v, verts[0], labels, c2i)

    
def dist_to_next_layer(g, v, layers, dist):
    """ For a graph, its vertex and layering, output vertex distance from its
    current layer to the next layer. dist is a pre-computed graph distances
    dictionary, e.g. by dist = nx.shortest_path_length(g). """
    try:
        ind = [v in layer for layer in layers].index(False)
    except ValueError:
        print("Vertex lies in final layer!")
        return
    return min(dist[v][w] for w in layers[ind])


def nbrrep(cube):
    """ Turns a standard cubelist into a list of neighborhood connectivity
    vectors for cubies. """
    ncube = normalize(cube)
    res = []
    for i, b in enumerate(ncube):
        vector = []
        vector.append(1 if i % 3 < 2  and cube[i] == cube[i+1] else 0) # R
        vector.append(1 if i % 3 > 0  and cube[i] == cube[i-1] else 0) # L
        vector.append(1 if i % 9 < 6  and cube[i] == cube[i+3] else 0) # F
        vector.append(1 if i % 9 > 2  and cube[i] == cube[i-3] else 0) # B
        vector.append(1 if     i < 18 and cube[i] == cube[i+9] else 0) # D
        vector.append(1 if     i > 8  and cube[i] == cube[i-9] else 0) # U
        res += vector
    return res


def similarity(nbrcube1, nbrcube2):
    """ Hamming distance based similarity of nbrreps of cubelists. """
    flat1 = [y for x in nbrcube1 for y in x]
    flat2 = [y for x in nbrcube2 for y in x]
    return (sum(c1 == c2 for c1, c2 in zip(flat1, flat2)) - 54) / (162 - 54)


def to_dbrecord(cube):
    """ Transform a cube into a database.csv record. Most notably calculate
    the multiplicity of the various bandaged block types so that nice
    database searches by filtering on them can be done. """
    norm = copy.deepcopy(cube)
    norm = normalize(norm)
    shape = ".".join(str(i) for i in normalize(cube, keepzeros=True))
    pair = clock = bar = bigclock = quad = fuse2 = slab = cblock = fuse3 = 0
    bigblock = 0
    for blockno in range(1, max(norm)):
        no = norm.count(blockno) # number of cubies in this block
        inds = [i for i, block in enumerate(norm) if block == blockno]
        spans_center = any([i in [4, 10, 12, 14, 16, 22] for i in inds])
        if no == 2 and not spans_center:
            pair += 1
        if no == 2 and spans_center:
            clock += 1
        if no == 3 and not spans_center:
            clock += 1
        if no == 3 and spans_center:
            bigclock += 1
        if no == 4 and not spans_center:
            quad += 1
        if no == 4 and spans_center:
            fuse2 += 1
        if no == 6 and not spans_center:
            slab += 1
        if no == 6 and spans_center:
            cblock += 1
        if no == 8:
            fuse3 += 1
        if no == 12:
            bigblock += 1
    return ",".join(["NameMe!", shape, *[str(i) for i in (pair, clock, bar,
                     bigclock, quad, fuse2, slab, cblock, fuse3, bigblock)],
                     "Sources..."])

"""
   0  1  2
  3  4  5
 6  7  8
    9 10 11
  12 13 14
 15 16 17
    18 19 20
  21 22 23
 24 25 26
"""