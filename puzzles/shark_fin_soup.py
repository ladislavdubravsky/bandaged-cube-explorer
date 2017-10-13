# -*- coding: utf-8 -*-
"""
The Shark Fin Soup cube
"""

import csv
import pandas as pd
import networkx as nx
import bce.core as c
from bce.graphics import draw_cubes

cube =  [   1,1,2,
           1,1,2,
          3,3,0,
            4,4,5,
           4,4,5,
          6,6,0,
            7,7,8,
           7,7,8,
          9,9,0   ]
cube = c.normalize(cube)
verts, edges, labels, i2c, c2i = c.explore(cube, fullperm=False)
g = nx.Graph(edges)

# distances, farthest shapes, reach them and test yourself solving
pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
for i in range(max(dist.values()) + 1):
    print(i, ":", len(list(filter(lambda x: dist[x] == i, verts))))
    
farthest = [i2c[v] for v in verts if dist[v] == 20]
draw_cubes(farthest)
c.shortest_path(g, cube, farthest[1], labels, c2i)

# highly turnable shapes
len([v for v in verts if g.degree(v) == 2])
turnable3 = [v for v in verts if g.degree(v) == 6]
draw_cubes([i2c[i] for i in turnable3], ncol=5, size=2)

# get help for a shape
scram = [   1,1,2,
           1,1,2,
          0,0,0,
            4,4,8,
           4,4,5,
          3,6,9,
            7,7,8,
           7,7,5,
          3,6,9   ]
scram = c.normalize(scram)
c.shortest_path(g, scram, c.normalize(cube), labels, c2i)

# export for visualization
with open(r"C:\temp\graph.csv", "w") as f:
    writer = csv.writer(f)
    writer.writerows([[e[0], e[1], labels[e]] for e in edges])

# prepare database format for storing, later check load from db
c.to_dbrecord(cube)
db = pd.read_csv(r"C:\Python\bandaged-cube-explorer\puzzles\database.csv", index_col=0)
cube = [int(i) for i in db.loc["Alcatraz", "Shape"].split(".")]
draw_cubes([cube, c.do(cube, "x2 z'")])

# ALGS
# D R2 U' D' R2 U               cross swap of two pairs
# D R2 U' R2 U D' F2 U F2 U'