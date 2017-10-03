# -*- coding: utf-8 -*-

# correlate turn distances from solved shape
distcomp = zip(*[[dist[v], similarity(nbrrep(i2c[v]), nbrrep(i2c[0]))] for v in verts])
plt.scatter(*distcomp)

# clustering / classification on all nbrreps
# http://scikit-learn.org/stable/modules/tree.html
from sklearn import tree


# graph drawing - probably easiest to fall back to Mathematica for really nice graphs
# pos = nx.spring_layout(g)
# nx.draw_networkx_edges(g, pos, width=1, alpha=0.5)
# nx.draw_networkx_edge_labels(g, pos, labels, font_size=8)
# https://networkx.github.io/documentation/networkx-1.9/examples/drawing/labels_and_colors.html

