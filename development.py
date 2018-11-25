# -*- coding: utf-8 -*-

import csv
import networkx as nx
import pandas as pd
import bce.core as c
from bce.graphics import draw_cubes

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

with open(r"C:\temp\graph_good.csv", "w") as f:
    writer = csv.writer(f)
    writer.writerows([[e[0], e[1], labels[e]] for e in edges])

draw_cubes([i2c[i] for i in range(121)], ncol=15, size=1)

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for i in range(max(dist.values()) + 1):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))

# correlate turn distances from solved shape
distcomp = zip(*[[dist[v], c.similarity(c.nbrrep(i2c[v]), c.nbrrep(i2c[0]))] for v in verts])
plt.scatter(*distcomp)

# clustering / classification on all nbrreps
# http://scikit-learn.org/stable/modules/tree.html
from sklearn import tree


c2i[tuple([  4,4,6,
           2,2,6,
          3,3,0,
            10,10,8,
           10,10,8,
          7,5,1,
            10,10,9,
           10,10,9,
          7,5,1])] # 2385
c.shortest_path(g, 2385, 0, labels, c2i)

