# -*- coding: utf-8 -*-

import networkx as nx
import pandas as pd
import bce.core as c
from bce.graphics import draw_cubes

alca =  [   6,6,0,
           6,6,0,
          0,0,0,
            7,7,5,
           7,7,4,
          1,2,3,
            7,7,5,
           7,7,4,
          1,2,3   ]

verts, edges, labels, i2c, c2i = c.explore(alca)
g = nx.Graph(edges)

pred, dist = nx.dijkstra_predecessor_and_distance(g, 0)
len([v for v in verts if dist[v] < 7])
smaller = [" ".join([str(e[0]), str(e[1]), labels[e]]) for e in edges
           if dist[e[0]] < 7 and dist[e[1]] < 7]

# correlate turn distances from solved shape
distcomp = zip(*[[dist[v], c.similarity(c.nbrrep(i2c[v]), c.nbrrep(i2c[0]))] for v in verts])
plt.scatter(*distcomp)

# clustering / classification on all nbrreps
# http://scikit-learn.org/stable/modules/tree.html
from sklearn import tree


# graph drawing - probably easiest to fall back to Mathematica for really nice graphs
# pos = nx.spring_layout(g)
# nx.draw_networkx_edges(g, pos, width=1, alpha=0.5)
# nx.draw_networkx_edge_labels(g, pos, labels, font_size=8)
# https://networkx.github.io/documentation/networkx-1.9/examples/drawing/labels_and_colors.html

