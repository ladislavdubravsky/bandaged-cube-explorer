# -*- coding: utf-8 -*-

import csv
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import networkx as nx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import v1.core as c
from v1.graphics import draw_cubes

# shark fin soup
cube =  [   1,1,2,
           1,1,2,
          3,3,0,
            4,4,5,
           4,4,5,
          6,6,0,
            7,7,8,
           7,7,8,
          9,9,0   ]

# 1x1x2 maxout
cube =  [   1,1,4,
           2,2,4,
          3,3,0,
            10,12,5,
           10,0,5,
          9,8,7,
            11,12,6,
           11,0,6,
          9,8,7   ]


cube = [  2, 2, 10,
         3, 3, 10,
        4, 4, 0,
          1, 1, 9,
         1, 1, 9,
        5, 6, 7,
          1, 1, 8,
         1, 1, 8,
        5, 6, 7]

verts, edges, labels, i2c, c2i = c.explore(c.normalize(cube), fullperm=False)
g = nx.Graph(edges)

with open("graph_good.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows([[e[0], e[1], labels[e]] for e in edges])

draw_cubes([i2c[i] for i in verts], ncol=15, size=1)

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for i in range(max(dist.values()) + 1):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))

# correlate turn distances from solved shape
distcomp = zip(*[[dist[v], c.similarity(c.nbrrep(i2c[v]), c.nbrrep(i2c[0]))] for v in verts])
plt.figure()
plt.scatter(*distcomp)
plt.show()

farthest = max(dist, key=dist.get)
print("Path from a farthest shape:", c.shortest_path(g, farthest, 0, labels, c2i))

