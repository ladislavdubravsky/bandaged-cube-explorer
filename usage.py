# -*- coding: utf-8 -*-
"""
Usage example.
"""

# 0. import libraries we'll be using
import matplotlib.pyplot as plt
import networkx as nx
import core as c
from graphics import draw_cubes

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

# note however the solved shape is chosen the best way it could be!
nx.diameter(g)
nx.radius(g)
[v for v in verts if nx.eccentricity(g, v) == 16]
draw_cubes([i2c[v] for v in verts if nx.eccentricity(g, v) == 28])

# 7. draw the farthest three shapes and find a path to one of them
farthest = [i2c[v] for v in verts if dist[v] == 16]
draw_cubes(farthest)
c.shortest_path(g, alca, farthest[1], labels, c2i)

# 8. explore stabilizer / feature chain lengths
f1 = [v for v in verts if i2c[v][c.F] == i2c[v][c.DF]]
p = nx.shortest_path_length(g)
plt.hist([min([p[u][v] for v in f1]) for u in verts], bins=7)
draw_cubes([i2c[u] for u in verts if min([p[u][v] for v in f1]) == 7])

""" Why is Belt Road easier than Alcatraz?
The reason is: it has small-step stabilizer chains.
I.e., mostly any shape can be solved piece by piece using short algorithms.
"""
