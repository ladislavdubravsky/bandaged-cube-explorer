# -*- coding: utf-8 -*-
"""
Usage example.
"""

# 0. import libraries we'll be using
import networkx as nx
import bce.core as c
from bce.graphics import draw_cubes

# 1. define a bandage shape - alcatraz puzzle solved shape
alca =  [   6,6,0,
           6,6,0,
          0,0,0,
            7,7,5,
           7,7,4,
          1,2,3,
            7,7,5,
           7,7,4,
          1,2,3   ]

# 2. visualize it
draw_cubes(alca)
draw_cubes(alca, alpha=0.25, size=6)

# 3. explore the puzzle and store results
verts, edges, labels, i2c, c2i = c.explore(alca)
g = nx.Graph(edges)

# 4. how many shapes are there?
len(verts)

# 5. consider a scrambled shape and find a shortest solution
scrambled =  [   6,6,0,
               6,6,4,
              0,2,0,
                7,7,5,
               7,7,4,
              1,2,3,
                7,7,5,
               7,7,0,
              1,0,3   ]
draw_cubes(scrambled)

c.shortest_path(g, scrambled, alca, labels, c2i)

# 6. find out how many shapes there are at given distance from solved shape
pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for i in range(max(dist.values()) + 1):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))

# 7. note however the solved shape is chosen the best way it could be!
nx.diameter(g)
nx.radius(g)
[v for v in verts if nx.eccentricity(g, v) == 16]
draw_cubes([i2c[v] for v in verts if nx.eccentricity(g, v) == 28])

# 8. draw the farthest three shapes and find a path to one of them
farthest = [i2c[v] for v in verts if dist[v] == 16]
draw_cubes(farthest)
c.shortest_path(g, alca, farthest[1], labels, c2i)

nx.eccentricity(g, c2i[tuple(farthest[1])])

# 9. shortest paths are too hard - explore stabilizer / feature chains
def layers_distance(g, layers, dist=None):
    """ Calculates the largest shortest distance between a vertex from
    layer[i] and a vertex from layer[i + 1] in graph g, for all consecutive
    layer pairs.
    If dictionary of distances dist is not supplied, it is calculated as
    nx.shortest_path_length(g).
    This function is typically called to assess feasibility of cube solving
    via a particular stabilizer chain / feature chain. """
    if not dist:
        d = nx.shortest_path_length(g)
    else:
        d = dist
    return [max(min(d[i][j] for j in layers[n + 1]) for i in layers[n])
        for n in range(len(layers) - 1)]
# tallying, e.g. collections Counter

# define a stabilizer chain
v0 = set(verts)
v1 = {v for v in verts if i2c[v][c.F]  == i2c[v][c.DF]}
v2 = {v for v in v1    if i2c[v][c.R]  == i2c[v][c.DR]}
v3 = {v for v in v2    if i2c[v][c.FL] == i2c[v][c.DFL]}
v4 = {v for v in v3    if i2c[v][c.BR] == i2c[v][c.DBR]}
v5 = {v for v in v4    if i2c[v][c.FR] == i2c[v][c.DFR]}

# calculate maximum number of moves (QTM) in each solution step
d = nx.shortest_path_length(g)
layers_distance(g, [v0, v1, v2, v3, v4, v5], dist=d)

# explore the worst cases
wc = [[i2c[u], i2c[v]] for u in v4-v5 for v in v5 if d[u][v] == 10]
draw_cubes(wc[7], size=3)
c.shortest_path(g, wc[4][0], wc[4][1], labels, c2i)

wc = [[i2c[u], i2c[v]] for u in v3-v4 for v in v4 if d[u][v] == 10]
draw_cubes(wc[7], size=3)
c.shortest_path(g, wc[4][0], wc[4][1], labels, c2i)

# go back and try a different feature chain - will it be better?
v1 = {v for v in verts if i2c[v][c.F] == i2c[v][c.DF] or i2c[v][c.R] == i2c[v][c.DR]}
v2 = {v for v in v1    if i2c[v][c.F] == i2c[v][c.DF] and i2c[v][c.R] == i2c[v][c.DR]}
v3 = {v for v in v2    if i2c[v][c.FL] == i2c[v][c.DFL] or i2c[v][c.BR] == i2c[v][c.DBR]}
v4 = {v for v in v3    if i2c[v][c.FL] == i2c[v][c.DFL] and i2c[v][c.BR] == i2c[v][c.DBR]}
v5 = {v for v in v4    if i2c[v][c.FR] == i2c[v][c.DFR]}
layers_distance(g, [v0, v1, v2, v3, v4, v5], dist=d)

# think about less boilerplate for defining chains

""" Why is Belt Road easier than Alcatraz?
The reason is: it has small-step stabilizer chains.
I.e., mostly any shape can be solved piece by piece using short algorithms.
"""
