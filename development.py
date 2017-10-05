# -*- coding: utf-8 -*-

import csv
import networkx as nx
import pandas as pd
import bce.core as c
from bce.graphics import draw_cubes

cube =  [   1,1,9,
           2,2,9,
          3,3,0,
            10,10,8,
           10,10,8,
          4,5,6,
            10,10,7,
           10,10,7,
          4,5,6   ]

verts, edges, labels, i2c, c2i = c.explore(cube, fullperm=False)
g = nx.Graph(edges)

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for i in range(max(dist.values()) + 1):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))

# correlate turn distances from solved shape
distcomp = zip(*[[dist[v], c.similarity(c.nbrrep(i2c[v]), c.nbrrep(i2c[0]))] for v in verts])
plt.scatter(*distcomp)

# clustering / classification on all nbrreps
# http://scikit-learn.org/stable/modules/tree.html
from sklearn import tree


with open(r"C:\temp\graph.csv", "w") as f:
    writer = csv.writer(f)
    writer.writerows([[e[0], e[1], labels[e]] for e in edges])

c.to_dbrecord(cube)
db = pd.read_csv(r"C:\Python\bandaged-cube-explorer\puzzles\database.csv", index_col=0)
cube = [int(i) for i in db.loc["Alcatraz", "Shape"].split(".")]
draw_cubes([cube, c.do(cube, "x2 z'")])
