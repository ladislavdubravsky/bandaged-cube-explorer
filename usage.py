# -*- coding: utf-8 -*-
"""
Usage example.
"""

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

draw_cubes(c.do(alca, "F R2"))

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
# define a stabilizer chain
v0 = set(verts)
v1 = {v for v in verts if i2c[v][c.F]  == i2c[v][c.DF]}
v2 = {v for v in v1    if i2c[v][c.R]  == i2c[v][c.DR]}
v3 = {v for v in v2    if i2c[v][c.FL] == i2c[v][c.DFL]}
v4 = {v for v in v3    if i2c[v][c.BR] == i2c[v][c.DBR]}
v5 = {v for v in v4    if i2c[v][c.FR] == i2c[v][c.DFR]}
layers = [v0, v1, v2, v3, v4, v5]

# calculate maximum number of moves (QTM) in each solution step
d = nx.shortest_path_length(g)
c.layers_distance(g, layers, dist=d)
c.layers_distance(g, layers, dist=d, tally=True)

# explore the worst cases
wc = [u for u in v2 - v3 if c.dist_to_next_layer(g, u, layers, d) == 12]
draw_cubes([i2c[u] for u in wc], size=3)
c.path_to_next_layer(g, wc[0], layers, d, labels, c2i)

# try a more general feature chain - will it be better?
v1 = {v for v in verts if i2c[v][c.F] == i2c[v][c.DF] or i2c[v][c.R] == i2c[v][c.DR]}
v2 = {v for v in v1    if i2c[v][c.F] == i2c[v][c.DF] and i2c[v][c.R] == i2c[v][c.DR]}
v3 = {v for v in v2    if i2c[v][c.FL] == i2c[v][c.DFL] or i2c[v][c.BR] == i2c[v][c.DBR]}
v4 = {v for v in v3    if i2c[v][c.FL] == i2c[v][c.DFL] and i2c[v][c.BR] == i2c[v][c.DBR]}
v5 = {v for v in v4    if i2c[v][c.FR] == i2c[v][c.DFR]}
layers = [v0, v1, v2, v3, v4, v5]
c.layers_distance(g, layers, dist=d, tally=True)

# explore the worst cases
wc = [u for u in v3 - v4 if c.dist_to_next_layer(g, u, layers, d) == 9]
draw_cubes([i2c[u] for u in wc], size=3)
c.path_to_next_layer(g, wc[0], layers, d, labels, c2i)

# TODO: think about less boilerplate for defining chains