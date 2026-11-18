## Network Analysis Tools
## Veera Muangsin

import streamlit as st
import networkx as nx
import pandas as pd
import numpy as np
from pyvis.network import Network
import matplotlib.pyplot as plt
from matplotlib import colormaps, colors as mcolors
from scipy.stats import rankdata
import io
import random
from typing import Dict, Optional, Tuple

@st.cache_data
def load_network_from_file(uploaded_file, file_format, csv_header: bool = True, csv_directed: bool = False):
    """Return a NetworkX graph from an uploaded Streamlit file object.

    csv_header: the first CSV row holds column names (otherwise it is an edge).
    csv_directed: build a directed graph (first column -> second column).
    """
    try:
        if file_format == 'CSV':
            # accept comma-, tab- or space-separated edge lists
            df = pd.read_csv(uploaded_file, sep=r"\s*,\s*|\s+", engine="python",
                             header=0 if csv_header else None)
            if df.shape[1] < 2:
                raise ValueError("CSV needs at least two columns (source, target)")
            G = nx.from_pandas_edgelist(df, df.columns[0], df.columns[1],
                                        create_using=nx.DiGraph if csv_directed else nx.Graph)

        elif file_format == 'GML':
            G = nx.parse_gml(uploaded_file.getvalue().decode('utf-8'))

        elif file_format == 'GraphML':
            text = uploaded_file.getvalue().decode('utf-8')
            G = nx.read_graphml(io.StringIO(text))

        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        if len(G) == 0:
            raise ValueError("The resulting graph has no nodes.")

        return G

    except Exception as e:
        # keep Streamlit in the UI layer; re-raise for caller to catch
        raise RuntimeError(f"Failed to load network: {e}") from e

def graph_key(G: nx.Graph) -> str:
    """Cheap fingerprint of a graph, so cached results are reused only for the same graph."""
    if G.is_directed():
        edges = frozenset(G.edges())                       # (source, target) order matters
    else:
        edges = frozenset(frozenset(e) for e in G.edges())
    kind = "D" if G.is_directed() else "U"
    return f"{kind}-{G.number_of_nodes()}-{G.number_of_edges()}-{hash(edges)}"

def edge_weight_attr(G: nx.Graph) -> Optional[str]:
    """Name of the numeric edge-weight attribute ('weight' or 'value', as exported by Gephi), if any."""
    for attr in ("weight", "value"):
        if any(isinstance(d.get(attr), (int, float)) for _, _, d in G.edges(data=True)):
            return attr
    return None

def to_simple_undirected(G: nx.Graph) -> nx.Graph:
    """Undirected simple graph (no direction, multi-edges or self-loops) for clustering/path metrics."""
    U = nx.Graph(G)
    U.remove_edges_from(nx.selfloop_edges(U))
    return U

def largest_component(G: nx.Graph) -> nx.Graph:
    """The graph itself if connected, otherwise its largest connected component."""
    if nx.is_connected(G):
        return G
    return G.subgraph(max(nx.connected_components(G), key=len)).copy()

# Above this many nodes, path length, diameter and betweenness are estimated from a random sample
# of SAMPLE_SIZE start nodes (exact computation grows with the square of the network size).
SAMPLE_THRESHOLD = 1000
SAMPLE_SIZE = 500

def path_stats(G: nx.Graph, seed: int = 42):
    """Average shortest path length and diameter of a connected graph, from one breadth-first search
    per start node. Exact up to SAMPLE_THRESHOLD nodes; above that, estimated from SAMPLE_SIZE random
    start nodes (the diameter is then a lower bound). Returns (L, diameter, exact)."""
    nodes = list(G)
    exact = len(nodes) <= SAMPLE_THRESHOLD
    sources = nodes if exact else random.Random(seed).sample(nodes, SAMPLE_SIZE)
    total, pairs, diameter = 0, 0, 0
    for s in sources:
        dist = nx.single_source_shortest_path_length(G, s)
        total += sum(dist.values())
        pairs += len(dist) - 1
        diameter = max(diameter, max(dist.values()))
    return (total / pairs if pairs else 0.0), diameter, exact

@st.cache_data(show_spinner="Computing network statistics...")
def compute_basic_stats(_G: nx.Graph, key: str) -> Dict:
    """Basic statistics. Path length and diameter use the largest component if the graph is disconnected."""
    U = to_simple_undirected(_G)
    lcc = largest_component(U)
    L, diameter, exact = path_stats(lcc)
    return {
        "Nodes": _G.number_of_nodes(),
        "Edges": _G.number_of_edges(),
        "Density": nx.density(_G),
        "Diameter": diameter,
        "Avg Clustering": nx.average_clustering(U),
        "Avg Path Length": L,
        "Exact": exact,
        "Connected": lcc.number_of_nodes() == U.number_of_nodes(),
        "LCC Size": lcc.number_of_nodes(),
    }

@st.cache_data(show_spinner="Generating random graphs...")
def compare_with_random(_G: nx.Graph, key: str, n_samples: int = 5) -> pd.DataFrame:
    """Compare clustering C and average path length L with random graphs
    that have the same number of nodes and edges (Erdos-Renyi)."""
    U = to_simple_undirected(_G)
    n, m = U.number_of_nodes(), U.number_of_edges()

    def measure(H):
        return [nx.average_clustering(H), path_stats(largest_component(H))[0]]

    observed = np.array(measure(U))
    random_mean = np.mean([measure(nx.gnm_random_graph(n, m, seed=s)) for s in range(n_samples)], axis=0)
    return pd.DataFrame(
        {"This network": observed, "Random graph": random_mean, "Ratio": observed / random_mean},
        index=["Avg clustering C", "Avg path length L"],
    )

CENTRALITY_FUNCS = {
    "Degree": nx.degree_centrality,
    # estimated from SAMPLE_SIZE start nodes on large graphs
    "Betweenness": lambda G: nx.betweenness_centrality(
        G, k=None if len(G) <= SAMPLE_THRESHOLD else SAMPLE_SIZE, seed=42),
    "Closeness": nx.closeness_centrality,
    "PageRank": nx.pagerank,
}

@st.cache_data(show_spinner="Computing centralities...")
def compute_centralities(_G: nx.Graph, key: str):
    """All centrality measures in one table, computed once per graph.
    Returns (table, names of measures that failed)."""
    table, failed = {}, []
    for name, func in CENTRALITY_FUNCS.items():
        try:
            table[name] = func(_G)
        except Exception:
            failed.append(name)
    df = pd.DataFrame(table)
    df.index.name = 'Node'
    return df.reset_index(), failed

def spectral_start(G: nx.Graph) -> Dict:
    """Same as nx.spectral_layout for large graphs, but repeatable: networkx's sparse eigen-solver
    starts from a random vector, so the layout (and the spring layout built on it) changed every run."""
    from scipy.sparse import diags
    from scipy.sparse.linalg import eigsh
    nodes = list(G)
    A = nx.to_scipy_sparse_array(G, nodelist=nodes, weight=None, dtype=float)
    laplacian = diags(A.sum(axis=1)) - A
    v0 = np.random.default_rng(42).random(len(nodes))          # fixed starting vector
    values, vectors = eigsh(laplacian, k=3, which="SM", ncv=max(7, int(np.sqrt(len(nodes)))), v0=v0)
    xy = vectors[:, np.argsort(values)[1:3]]                    # skip the trivial first eigenvector
    return dict(zip(nodes, nx.rescale_layout(xy, scale=1.0)))

MEASURES = ["degree", "betweenness", "closeness", "pagerank"]
MEASURE_COLUMN = {"degree": "Degree", "betweenness": "Betweenness",
                  "closeness": "Closeness", "pagerank": "PageRank"}   # column in the centrality table

def rank_fraction(values):
    """Position of each value on the colour scale (0 = lowest value, 1 = highest), by rank.
    Equal values share a position."""
    r = rankdata(values)
    return (r - r.min()) / (r.max() - r.min()) if r.max() > r.min() else np.full(len(r), 0.5)

def color_legend_html(title: str, values, frac, fmt) -> str:
    """Small colour-scale legend placed over the graph (also kept in the downloaded HTML).
    The labels are the values actually drawn at the left end, middle and right end of the scale."""
    stop_list = [mcolors.to_hex(colormaps["viridis"](f)) for f in np.linspace(0, 1, 11)]
    stops = ", ".join(stop_list)
    lo, mid, hi = (fmt(values[np.argmin(np.abs(frac - f))]) for f in (0, 0.5, 1))
    return (
        f'<div id="color-legend" data-title="Node colour: {title} (by rank)" data-stops="{",".join(stop_list)}" '
        f'data-labels="{lo}|{mid}|{hi}" '
        'style="position:absolute; top:10px; left:10px; z-index:5; width:230px; padding:6px 8px; '
        'background:rgba(255,255,255,0.9); border:1px solid #ddd; border-radius:4px; font:12px sans-serif">'
        f'<div style="margin-bottom:4px"><b>Node colour: {title}</b> (by rank)</div>'
        f'<div style="height:10px; background:linear-gradient(to right, {stops})"></div>'
        '<div style="display:flex; justify-content:space-between; margin-top:2px">'
        f'<span>{lo}</span><span>{mid}</span><span>{hi}</span></div>'
        '<div style="display:flex; justify-content:space-between; color:#777">'
        '<span>lowest</span><span>middle</span><span>highest</span></div></div>'
    )

# "Download JPG" button shown in the graph's top-right corner. It saves the current view (with any
# zoom or pan) on a white background, plus the colour legend if there is one.
JPG_BUTTON_HTML = """
<button onclick="downloadJPG()" title="Save the current view as a JPG image"
  style="position:absolute; top:10px; right:10px; z-index:6; padding:4px 10px; font:12px sans-serif;
         background:#fff; border:1px solid #bbb; border-radius:4px; cursor:pointer">Download JPG</button>
<script>
function downloadJPG() {
  var src = document.querySelector('#mynetwork canvas');
  var out = document.createElement('canvas');
  out.width = src.width; out.height = src.height;
  var ctx = out.getContext('2d');
  ctx.fillStyle = '#ffffff';                        // JPG has no transparency: use a white background
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.drawImage(src, 0, 0);
  var lg = document.getElementById('color-legend'); // the legend is HTML, so draw it onto the image
  if (lg) {
    var r = src.width / src.clientWidth, x = 10 * r, y = 10 * r, w = 230 * r, pad = 8 * r;
    var labels = lg.dataset.labels.split('|'), stops = lg.dataset.stops.split(',');
    ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.fillRect(x, y, w, 76 * r);
    ctx.strokeStyle = '#dddddd'; ctx.strokeRect(x, y, w, 76 * r);
    ctx.fillStyle = '#000000'; ctx.font = 'bold ' + (12 * r) + 'px sans-serif';
    ctx.textAlign = 'left'; ctx.fillText(lg.dataset.title, x + pad, y + 17 * r);
    var g = ctx.createLinearGradient(x + pad, 0, x + w - pad, 0);
    stops.forEach(function (c, i) { g.addColorStop(i / (stops.length - 1), c); });
    ctx.fillStyle = g; ctx.fillRect(x + pad, y + 25 * r, w - 2 * pad, 10 * r);
    var rows = [[labels, '#000000', 50], [['lowest', 'middle', 'highest'], '#777777', 66]];
    ctx.font = (12 * r) + 'px sans-serif';
    rows.forEach(function (row) {
      ctx.fillStyle = row[1];
      ctx.textAlign = 'left';   ctx.fillText(row[0][0], x + pad, y + row[2] * r);
      ctx.textAlign = 'center'; ctx.fillText(row[0][1], x + w / 2, y + row[2] * r);
      ctx.textAlign = 'right';  ctx.fillText(row[0][2], x + w - pad, y + row[2] * r);
    });
  }
  var a = document.createElement('a');
  a.href = out.toDataURL('image/jpeg', 0.95);
  a.download = 'network.jpg';
  document.body.appendChild(a); a.click(); a.remove();
}
</script>
"""

LAYOUTS = ["forceatlas2", "spring", "kamada_kawai", "shell_by_degree", "circular", "random"]

@st.cache_data(show_spinner="Computing layout...")
def compute_layout(_G: nx.Graph, key: str, layout_type: str, node_spacing: float = 5.0) -> Dict:
    """Node positions, roughly within [-1, 1]. Cached, so changing fonts or sizes does not re-run the layout.

    node_spacing: spring layout only (ideal edge length k). ForceAtlas2's shape barely changes with its
    spacing parameters once rescaled to the window, so use the Graph Size slider to spread it out.
    """
    G = to_simple_undirected(_G)   # layouts ignore edge direction and repeated edges
    if layout_type == "forceatlas2":
        # Gephi's default layout. distributed_action ("dissuade hubs") stays off:
        # it pushes hubs to the edge and mixes the communities.
        # fewer iterations for large graphs (~1 s at 276 nodes, ~7 s at 1000 nodes), but at least 150:
        # with fewer, communities stay mixed. Each iteration slows down with the square of the size.
        max_iter = int(np.clip(150_000 / max(len(G), 1), 150, 500))
        pos = nx.forceatlas2_layout(G, max_iter=max_iter, seed=42)
        pos = nx.rescale_layout_dict(pos, scale=1.0)
    elif layout_type == "spring":
        k = 1 / np.sqrt(len(G)) * node_spacing
        if len(G) <= SAMPLE_THRESHOLD:
            pos = nx.spring_layout(G, k=k, iterations=50, seed=42)
        else:
            # large graphs: start from the (fast) spectral layout, so 20 iterations are enough
            pos = nx.spring_layout(G, k=k, pos=spectral_start(G), iterations=20, seed=42)
    elif layout_type == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    elif layout_type == "shell_by_degree":
        # hubs on the inner ring, mid-degree nodes next, the rest outside
        order = sorted(G, key=lambda n: G.degree(n), reverse=True)
        n1 = max(1, round(0.02 * len(G)))
        n2 = n1 + max(1, round(0.15 * len(G)))
        shells = [shell for shell in (order[:n1], order[n1:n2], order[n2:]) if shell]
        pos = nx.shell_layout(G, nlist=shells)
    elif layout_type == "circular":
        pos = nx.circular_layout(G)
    elif layout_type == "random":
        pos = nx.random_layout(G, seed=42)
    else:
        raise ValueError(f"Unknown layout: {layout_type}")
    # plain floats: random_layout returns float32, which pyvis cannot convert to JSON
    return {node: (float(xy[0]), float(xy[1])) for node, xy in pos.items()}

@st.cache_data(show_spinner="Removing node overlaps...")
def remove_overlaps(pos: Dict, radius: Dict, margin: float = 2.0, max_iter: int = 500,
                    max_fill: float = 0.25) -> Dict:
    """Like Gephi's Noverlap: push overlapping nodes apart until their circles no longer overlap.
    pos and radius are in drawing units (the same units vis-network uses for x, y and size).
    If the circles would cover more than max_fill of the drawing area, the layout is first spread
    out evenly; otherwise dense areas cannot make room."""
    from scipy.spatial import cKDTree
    nodes = list(pos)
    P = np.array([pos[n] for n in nodes], dtype=float)
    R = np.array([radius[n] for n in nodes], dtype=float) + margin / 2

    span = np.ptp(P, axis=0) + 2 * R.max()
    fill = (np.pi * R ** 2).sum() / (span[0] * span[1])
    P = P.mean(axis=0) + (P - P.mean(axis=0)) * max(1.0, np.sqrt(fill / max_fill))

    rng = np.random.default_rng(42)
    for _ in range(max_iter):
        pairs = cKDTree(P).query_pairs(2 * R.max(), output_type='ndarray')   # nearby pairs only
        if len(pairs) == 0:
            break
        i, j = pairs[:, 0], pairs[:, 1]
        delta = P[j] - P[i]
        dist = np.hypot(delta[:, 0], delta[:, 1])
        overlap = R[i] + R[j] - dist
        hit = overlap > 1e-6
        if not hit.any():
            break
        i, j, delta, dist, overlap = i[hit], j[hit], delta[hit], dist[hit], overlap[hit]
        same = dist < 1e-9                                       # nodes on the same spot
        if same.any():
            delta[same] = rng.normal(size=(same.sum(), 2))
            dist[same] = np.hypot(delta[same, 0], delta[same, 1])
        push = delta / dist[:, None] * (overlap / 2)[:, None]    # each node moves half the overlap
        move = np.zeros_like(P)
        np.add.at(move, i, -push)
        np.add.at(move, j, push)
        # average the pushes on nodes with several overlapping neighbours (prevents overshoot)
        count = np.bincount(np.concatenate([i, j]), minlength=len(P))[:, None]
        P += 1.5 * move / np.maximum(count, 1)
    return {n: (float(x), float(y)) for n, (x, y) in zip(nodes, P)}

class NetworkVisualizer:
    def __init__(self, G: nx.Graph):
        self.G = G
        self.colors = [
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", 
            "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
            "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000"
        ]

    def create_interactive_network(
        self, 
        communities: Optional[Dict] = None,
        layout: str = "forceatlas2",
        centrality_metric: str = "degree",
        scale_factor: float = 1000,
        node_spacing: float = 5.0,
        node_size_range: Tuple[int, int] = (10, 50),
        show_edges: bool = True, 
        font_size: int = 14,
        weight_attr: Optional[str] = None,
        label_top_n: Optional[int] = None,
        hide_weak_pct: int = 0,
        weight_filter_attr: Optional[str] = None,
        min_component_size: int = 1,
        no_overlap: bool = False,
        color_by: str = "community",
        label_value: Optional[str] = None
    ) -> str:
        """label_top_n: show labels only for the N most central nodes (None = all).
        hide_weak_pct: hide this percentage of the weakest edges (by weight_filter_attr), drawing only.
        min_component_size: hide connected components with fewer nodes, drawing only.
        no_overlap: push overlapping nodes apart (like Gephi's Noverlap).
        color_by: "community", "single color", or a measure in MEASURES (coloured by rank).
        label_value: a measure in MEASURES to show next to each label, e.g. "salt (224)"."""
        # Hide small components. The layout is computed on what is shown, so the main part of
        # the network fills the canvas instead of being squeezed by a ring of small pieces.
        H = self.G
        if min_component_size > 1:
            keep = [n for c in nx.connected_components(to_simple_undirected(self.G))
                    if len(c) >= min_component_size for n in c]
            H = self.G.subgraph(keep).copy()

        # Get layout positions with adjustable spacing
        pos = compute_layout(H, graph_key(H), layout, node_spacing)
        
        # Scale positions
        pos = {node: (coord[0] * scale_factor, coord[1] * scale_factor) 
               for node, coord in pos.items()}

        # Centrality (cached): sets node size and which labels are shown.
        # With "single size", every node has the same size and labels go to the highest-degree nodes.
        single_size = centrality_metric == "single size"
        cent_df, failed = compute_centralities(self.G, graph_key(self.G))
        metric = "Degree" if single_size else MEASURE_COLUMN.get(centrality_metric, "Degree")
        if metric in failed:
            st.warning(f"Failed to compute {centrality_metric} centrality, using degree centrality instead.")
            metric = "Degree"
        # all measures (whole network), for tooltips, label values and colours
        measure_values = {m: dict(zip(cent_df['Node'], cent_df[MEASURE_COLUMN[m]]))
                          for m in MEASURES if MEASURE_COLUMN[m] not in failed}
        n_minus_1 = max(len(self.G) - 1, 1)

        def fmt_value(m, v):
            # degree as a number of links; the others with 3 significant digits
            return f"{round(v * n_minus_1)}" if m == "degree" else f"{v:.3g}"

        # values from the whole network (same as the centrality table), for the nodes shown
        centrality = {n: c for n, c in zip(cent_df['Node'], cent_df[metric]) if n in H}
        if label_top_n is None or label_top_n >= len(centrality):
            labelled = set(centrality)
        else:
            labelled = set(sorted(centrality, key=centrality.get, reverse=True)[:label_top_n])

        # Scale node sizes
        min_cent, max_cent = min(centrality.values()), max(centrality.values())
        min_size, max_size = node_size_range
        if single_size:
            size_scale = lambda x: (min_size + max_size) / 2
        elif max_cent > min_cent:
            size_scale = lambda x: min_size + (x - min_cent) * (max_size - min_size) / (max_cent - min_cent)
        else:
            size_scale = lambda x: (min_size + max_size) / 2

        # Push overlapping nodes apart, using their drawn sizes (+1 for the border)
        if no_overlap:
            pos = remove_overlaps(pos, {n: float(size_scale(centrality[n])) + 1 for n in pos})

        # Create a copy of the graph to modify attributes
        G_vis = H.copy()

        # Prepare color map for communities if present
        if communities:
            unique_communities = sorted(set(communities.values()))
            color_map = {com: self.colors[i % len(self.colors)] 
                        for i, com in enumerate(unique_communities)}

        # Node colours: by community, by a measure (rank-based colour scale), or one colour
        legend = ""
        node_color = {}
        if color_by == "community" and communities:
            node_color = {n: color_map[communities[n]] for n in G_vis}
        elif color_by in measure_values:
            shown = list(G_vis)
            values = np.array([measure_values[color_by][n] for n in shown])
            # rank, not raw value: centralities are very skewed, so a linear scale would give
            # almost every node the same colour
            frac = rank_fraction(values)
            node_color = {n: mcolors.to_hex(colormaps["viridis"](f)) for n, f in zip(shown, frac)}
            legend = color_legend_html(MEASURE_COLUMN[color_by], values, frac,
                                       lambda v: fmt_value(color_by, v))
        elif color_by in MEASURE_COLUMN:
            st.warning(f"{MEASURE_COLUMN[color_by]} could not be computed, so nodes use one colour.")

        # Set node attributes (replace file attributes such as Gephi 'graphics' with our own)
        for node in G_vis.nodes():
            lines = [f"Node: {node}"]
            tooltip = self.G.nodes[node].get('tooltip')
            if tooltip:
                lines.append(f"Tooltip: {tooltip}")
            lines.append(f"Degree: {self.G.degree(node)}")
            for m in ("betweenness", "closeness", "pagerank"):
                if m in measure_values:
                    lines.append(f"{MEASURE_COLUMN[m]}: {measure_values[m][node]:.3g}")
            if communities:
                lines.append(f"Community: {communities[node]}")
            label = str(node)
            if label_value in measure_values:
                label += f" ({fmt_value(label_value, measure_values[label_value][node])})"
            attrs = {
                # ' ' not '': pyvis replaces an empty label with the node name. Name still shows on hover.
                'label': label if node in labelled else ' ',
                # plain floats: random_layout returns float32, which pyvis cannot convert to JSON
                'size': float(size_scale(centrality[node])),
                'x': float(pos[node][0]),
                'y': float(pos[node][1]),
                'physics': False,
                'title': "\n".join(lines),
            }
            attrs['color'] = node_color.get(node, '#97c2fc')   # '#97c2fc' = pyvis default blue
            G_vis.nodes[node].clear()
            G_vis.nodes[node].update(attrs)

        # Hide the weakest edges (drawing only; the analysis keeps every edge)
        if hide_weak_pct > 0 and weight_filter_attr:
            weights = [d.get(weight_filter_attr) for _, _, d in G_vis.edges(data=True)]
            weights = [w for w in weights if isinstance(w, (int, float))]
            if weights:
                threshold = np.percentile(weights, hide_weak_pct)

                def is_weak(d):
                    w = d.get(weight_filter_attr)
                    return isinstance(w, (int, float)) and w < threshold

                if G_vis.is_multigraph():
                    weak = [(u, v, k) for u, v, k, d in G_vis.edges(keys=True, data=True) if is_weak(d)]
                else:
                    weak = [(u, v) for u, v, d in G_vis.edges(data=True) if is_weak(d)]
                G_vis.remove_edges_from(weak)

        # Create network
        directed = self.G.is_directed()
        nt = Network(
            height="720px",
            width="100%",
            bgcolor="#ffffff",
            font_color="black",
            directed=directed, cdn_resources='in_line'
        )

        # Fill pyvis's node and edge lists directly. pyvis's add_node/add_edge (used by from_nx)
        # compare every new edge with all previous ones, which takes minutes on large graphs.
        def vis_id(n):
            if isinstance(n, np.integer):
                return int(n)
            return n if isinstance(n, (str, int)) else str(n)

        for node, attrs in G_vis.nodes(data=True):
            node_dict = {'id': vis_id(node), 'shape': 'dot', 'font': {'color': 'black'}, **attrs}
            nt.nodes.append(node_dict)
            nt.node_ids.append(node_dict['id'])
            nt.node_map[node_dict['id']] = node_dict

        # Edges: uniform width, or width scaled by the weight attribute if requested.
        # One edge per node pair, as pyvis does (repeated edges would be drawn on top of each other).
        seen = set()
        for u, v, data in G_vis.edges(data=True):
            pair = (u, v) if directed else frozenset((u, v))
            if pair in seen:
                continue
            seen.add(pair)
            edge = {'from': vis_id(u), 'to': vis_id(v), 'width': 1}
            if directed:
                edge['arrows'] = 'to'
            w = data.get(weight_attr) if weight_attr else None
            if w is not None:
                edge['value'] = w            # vis-network scales edge width by 'value'
                edge['title'] = f"{weight_attr}: {w}"
            nt.edges.append(edge)

        # Curved edges are slow to draw in the browser; use straight edges on large graphs
        smooth = '{"type": "continuous", "roundness": 0.5}' if len(nt.edges) <= 2000 else 'false'

        # Set visualization options
        nt.set_options("""
        {
            "nodes": {
                "font": {"size": %d},
                "borderWidth": 2,
                "borderWidthSelected": 3,
                "shape": "dot"
            },
            "edges": {
                "color": {"color": "#666666"},
                "width": 1.5,
                "smooth": %s,
                "hidden": %s
            },
            "physics": {
                "enabled": false
            },
            "interaction": {
                "hover": true,
                "multiselect": true,
                "navigationButtons": true,
                "tooltipDelay": 100,
                "zoomView": true,
                "dragView": true,
                "zoomSpeed": 0.5
            }
        }
        """ % (font_size, smooth, str(not show_edges).lower()))

        # Build the page in memory: pyvis's save_graph writes with the system encoding
        # (cp1252 on Windows), which cannot encode the bundled vis-network library.
        html = nt.generate_html()
        return html.replace("<body>", "<body>" + legend + JPG_BUTTON_HTML, 1)

class NetworkAnalyzer:
    def __init__(self, G: nx.Graph):
        self.G = G
        
    def get_centralities(self) -> pd.DataFrame:
        """Centrality table (cached per graph)"""
        df, failed = compute_centralities(self.G, graph_key(self.G))
        if failed:
            st.warning(f"Some centrality measures couldn't be computed: {', '.join(failed)}")
        return df.copy()   # copy: callers add columns
    
    def plot_degree_distribution(self, log_log: bool = False) -> plt.Figure:
        """Plot degree distribution as a histogram, or as a log-log CCDF P(Degree >= k)."""
        degrees = np.array([d for n, d in self.G.degree()])
        fig, ax = plt.subplots(figsize=(6, 4))
        if log_log:
            k, counts = np.unique(degrees[degrees > 0], return_counts=True)
            ccdf = counts[::-1].cumsum()[::-1] / counts.sum()   # fraction of nodes with degree >= k
            ax.loglog(k, ccdf, marker='o', linestyle='none', markersize=4, label='data')
            # Reference power laws: P(Degree >= k) = (k / k_min)^-(alpha - 1), starting at the first data point
            k_line = np.logspace(np.log10(k[0]), np.log10(k[-1]), 50)
            for alpha, style in [(2, '--'), (3, ':')]:
                ax.loglog(k_line, (k_line / k[0]) ** -(alpha - 1), linestyle=style, color='gray',
                          label=f'\u03b1 = {alpha} (slope \u2212{alpha - 1})')
            ax.set_ylim(ccdf.min() / 2, 1.5)   # keep the axis on the data; reference lines are clipped
            ax.legend(loc='lower left', fontsize=8)
            ax.set_ylabel('P(Degree \u2265 k)')
            ax.set_title('Degree Distribution (CCDF, log-log)')
        else:
            ax.hist(degrees, bins=range(degrees.max() + 2), align='left', rwidth=0.8)
            ax.set_ylabel('Frequency')
            ax.set_title('Degree Distribution')
        ax.set_xlabel('Degree k')
        fig.tight_layout()
        return fig

@st.cache_data(show_spinner="Detecting communities...")
def detect_communities(_G: nx.Graph, key: str):
    """Community detection (greedy modularity, edge weights ignored)"""
    return list(nx.community.greedy_modularity_communities(to_simple_undirected(_G)))

def main():
    st.set_page_config(page_title="Network Analysis Tool", layout="wide")
    
    st.title("Network Analysis Tool")
    
    # Create tabs
    tab_viz, tab_analysis = st.tabs(["Network Visualization", "Network Analysis"])
    
    # Input and Visualization tab
    with tab_viz:
        # Move input controls to sidebar
        with st.sidebar:
            st.subheader("Network Input")
            data_source = st.radio(
                "Choose data source",
                ["Sample Networks", "Graph Generator", "Upload Network"]
            )
            
            # Get network based on selection
            G = None  # Initialize G
            if data_source == "Sample Networks":
                sample_option = st.selectbox(
                    "Select sample network",
                    ["Karate Club", "Les Miserables"]
                )
                G = nx.karate_club_graph() if sample_option == "Karate Club" else nx.les_miserables_graph()
                    
            elif data_source == "Graph Generator":
                generator_type = st.selectbox(
                    "Select generator type",
                    ["Complete Graph", "Random (Erdős-Rényi)", "Small World (Watts-Strogatz)", "Scale-free (Barabási-Albert)"]
                )
                
                if generator_type == "Complete Graph":
                    n = st.slider("Number of nodes", 3, 100, 20)
                    G = nx.complete_graph(n)
                    
                elif generator_type == "Random (Erdős-Rényi)":
                    n = st.slider("Number of nodes", 3, 100, 20)
                    p = st.slider("Edge probability", 0.0, 1.0, 0.2)
                    G = nx.erdos_renyi_graph(n, p, seed=42)
                    
                elif generator_type == "Small World (Watts-Strogatz)":
                    n = st.slider("Number of nodes", 100, 1000, 200)
                    k = st.slider("Number of nearest neighbors", 4, 20, 6)
                    p = st.slider("Rewiring probability", 0.0, 1.0, 0.1)
                    G = nx.watts_strogatz_graph(n, k, p, seed=42)
                    
                else:  # Barabási-Albert
                    n = st.slider("Number of nodes", 100, 1000, 200)
                    m = st.slider("Number of edges to attach", 1, 10, 3)
                    G = nx.barabasi_albert_graph(n, m, seed=42)
                    
            else:  # Upload Network
                file_format = st.selectbox(
                    "Choose file format",
                    ["CSV", "GML", "GraphML"]
                )
                
                uploaded_file = st.file_uploader(
                    "Upload network file",
                    type=["csv", "gml", "graphml"]
                )
                if file_format == "CSV":
                    csv_header = st.checkbox(
                        "First row is a header", value=True,
                        help="Untick if the first row is already an edge (e.g. 'timesofindia,shramn')"
                    )
                    csv_directed = st.checkbox(
                        "Directed edges (first column \u2192 second column)", value=False
                    )
                else:
                    csv_header, csv_directed = True, False
                
                if uploaded_file:
                    try:
                        G = load_network_from_file(uploaded_file, file_format, csv_header, csv_directed)
                    except RuntimeError as e:
                        st.error(f"{e}\n\nCheck that the file format matches the file.")
                        st.stop()
                else:
                    st.info("Please upload a network file or use other data sources")
                    st.stop()
            
            if G is not None:  # Only show options if we have a graph
                # Community detection
                st.markdown("---")  # Add separator
                show_communities = st.checkbox("Detect Communities")
                
                # Initialize communities variable
                communities = None
                community_stats_container = st.empty()  # Create a placeholder for stats
                
                if show_communities:
                    try:
                        communities_iter = detect_communities(G, graph_key(G))
                        communities = {}
                        
                        # Create a list to store community sizes
                        community_sizes = []
                        
                        for idx, community in enumerate(communities_iter):
                            community_sizes.append(len(community))
                            for node in community:
                                communities[node] = idx
                        
                        # Community statistics in a collapsible section (collapsed by default)
                        with community_stats_container.container():
                            with st.expander(f"Community Statistics ({len(communities_iter)} communities)",
                                             expanded=False):
                                st.metric("Number of Communities", len(communities_iter))
                                avg_size = sum(community_sizes) / len(community_sizes)
                                st.metric("Average Community Size", f"{avg_size:.1f}")
                            
                                # Sort communities by size in descending order
                                community_df = pd.DataFrame({
                                    'Community': range(len(community_sizes)),
                                    'Size': community_sizes
                                }).sort_values('Size', ascending=False)
                            
                                st.caption("Community Sizes (sorted by size):")
                                st.dataframe(
                                    community_df,
                                    hide_index=True,
                                    height=min(len(community_sizes) * 35 + 38, 300)
                                )
                            
                    except Exception as e:
                        st.warning(f"Could not detect communities: {str(e)}")

                # Visualization options
                st.markdown("---")  # Add separator
                st.subheader("Visualization Options")
                
                large = len(G) > SAMPLE_THRESHOLD
                layout_option = st.selectbox(
                    "Layout Algorithm",
                    LAYOUTS,
                    index=LAYOUTS.index("spring") if large else 0,   # spring is much faster on large graphs
                    help="forceatlas2: Gephi's default, good at separating communities (slow above 1,000 nodes). "
                         "shell_by_degree: hubs on the inner ring, low-degree nodes outside. "
                         "kamada_kawai: slow on large graphs (30\u201380 s at 1,000 nodes)."
                )
                if layout_option == "kamada_kawai" and len(G) > 300:
                    st.caption(f"Kamada\u2013Kawai is slow on large graphs; {len(G)} nodes may take a while.")
                if layout_option == "forceatlas2" and large:
                    st.caption(f"ForceAtlas2 is slow on large graphs ({len(G)} nodes). "
                               "spring gives a similar picture much faster.")
                centrality_option = st.selectbox(
                    "Node Size By", 
                    ["single size"] + MEASURES,
                    index=1   # degree
                )
                single_size = centrality_option == "single size"
                color_option = st.selectbox(
                    "Node Color By",
                    (["community"] if communities else []) + ["single color"] + MEASURES,
                    help="'community' appears when Detect Communities is ticked. "
                         "Measures use a colour scale by rank: dark purple = lowest, yellow = highest."
                )
                
                # Size controls 
                scale_factor = st.slider(
                    "Graph Size", 
                    min_value=500, 
                    max_value=3000, 
                    value=1000,
                    step=100,
                    help="Adjust the overall size of the graph"
                )
                
                if layout_option == "spring":
                    node_spacing = st.slider(
                        "Node Spacing",
                        min_value=1.0,
                        max_value=20.0,
                        value=5.0,
                        step=1.0,
                        help="Larger values push nodes further apart (spring layout only)"
                    )
                else:
                    node_spacing = 5.0
                
                if single_size:
                    size = st.slider("Node Size", min_value=5, max_value=200, value=20, step=5,
                                     help="Size of every node")
                    node_size_range = (size, size)
                else:
                    node_size_range = st.slider(
                        "Node Size Range",
                        min_value=5,
                        max_value=200,
                        value=(10, 50),
                        step=5,
                        help="Set the minimum and maximum node sizes"
                    )
                
                no_overlap = st.toggle(
                    "Prevent Node Overlap (Noverlap)",
                    value=False,
                    help="Like Gephi's Noverlap: pushes overlapping nodes apart, using their drawn sizes. "
                         "Dense graphs are spread out a little to make room."
                )
                
                # Node label font size
                font_size = st.slider(
                    "Label Font Size",
                    min_value=8,
                    max_value=40,
                    value=16,
                    step=2,
                    help="Adjust the font size of node labels"
                )
                
                # Label only the largest nodes (size = the Node Size By measure)
                label_top_n = st.slider(
                    "Show Labels for N Highest-Degree Nodes" if single_size else "Show Labels for N Largest Nodes",
                    min_value=0,
                    max_value=len(G),
                    value=min(len(G), 30),
                    help=("All nodes have the same size, so labels go to the nodes with the most links. "
                          if single_size else "Node size is set by 'Node Size By'. ")
                         + "Other names appear on hover."
                )
                label_value_option = st.selectbox(
                    "Value in Label",
                    ["none"] + MEASURES,
                    help="Adds the value to each shown label, e.g. 'salt (224)'. "
                         "Degree is a number of links; the others are centrality scores."
                )
                
                # Hide small disconnected pieces (only offered when there are several)
                component_sizes = sorted((len(c) for c in nx.connected_components(to_simple_undirected(G))),
                                         reverse=True)
                if len(component_sizes) > 1:
                    min_component_size = st.slider(
                        "Hide Components Smaller Than (nodes)",
                        min_value=1, max_value=component_sizes[0], value=1,
                        help="Drawing only: the analysis uses the whole network. 1 shows everything; "
                             f"{component_sizes[0]} shows only the largest component."
                    )
                else:
                    min_component_size = 1
                
                # Edge visibility
                show_edges = st.toggle(
                    "Show Edges",
                    value=True,  
                    help="Toggle edge visibility"
                )
                
                # Edge width by weight (only if the file has weights)
                weight_attr = edge_weight_attr(G)
                if weight_attr and show_edges:
                    scale_edges = st.toggle(
                        f"Edge Width by Weight ('{weight_attr}')",
                        value=False,
                        help="Thicker edges for larger weights"
                    )
                else:
                    scale_edges = False
                if weight_attr and show_edges:
                    hide_weak_pct = st.slider(
                        "Hide Weakest Edges (%)",
                        min_value=0, max_value=95, value=0, step=5,
                        help=f"Hide edges with the lowest '{weight_attr}'. Drawing only: the analysis uses all edges."
                    )
                else:
                    hide_weak_pct = 0
                if weight_attr:
                    st.caption(f"This network has edge weights ('{weight_attr}'). They are used only for "
                               "edge width; centrality and community detection ignore them.")

        
        # Main visualization area (now full width)
        if G is not None:
            # Initialize analyzers
            analyzer = NetworkAnalyzer(G)
            visualizer = NetworkVisualizer(G)
            
            # Display basic stats in a more compact form
            st.text(
                f"Nodes: {len(G.nodes())} | Edges: {len(G.edges())} | "
                f"Density: {nx.density(G):.3f}"
            )
            
            # Create and display visualization with increased height
            html_content = visualizer.create_interactive_network(
                communities=communities,
                layout=layout_option,
                centrality_metric=centrality_option,
                scale_factor=scale_factor,
                node_spacing=node_spacing,
                node_size_range=node_size_range,
                show_edges=show_edges,
                font_size=font_size,
                weight_attr=weight_attr if scale_edges else None,
                label_top_n=label_top_n,
                hide_weak_pct=hide_weak_pct,
                weight_filter_attr=weight_attr,
                min_component_size=min_component_size,
                no_overlap=no_overlap,
                color_by=color_option,
                label_value=None if label_value_option == "none" else label_value_option
            )
            if min_component_size > 1:
                shown = sum(s for s in component_sizes if s >= min_component_size)
                hidden = sum(1 for s in component_sizes if s < min_component_size)
                st.caption(f"Showing {shown} of {len(G)} nodes; {hidden} components with fewer than "
                           f"{min_component_size} nodes are hidden.")
            
            st.iframe(html_content, height=800)
            st.download_button(
                "Download interactive graph (HTML)",
                data=html_content,
                file_name="network.html",
                mime="text/html",
                help="A standalone page that opens in any browser, with zoom and hover"
            )
            st.caption("To save the graph as an image, use the **Download JPG** button in the graph's "
                       "top-right corner. It saves the current view, including any zoom.")
    
    # Analysis tab
    # Analysis tab
    with tab_analysis:
        if G is not None:
            # Initialize analyzer
            analyzer = NetworkAnalyzer(G)
            
            st.header("Network Analysis")
            
            # Get basic statistics
            key = graph_key(G)
            stats = compute_basic_stats(G, key)
            
            # Basic Statistics
            st.subheader("Basic Statistics")
            cols = st.columns(6)
            cols[0].metric("Nodes", stats["Nodes"])
            cols[1].metric("Edges", stats["Edges"])
            cols[2].metric("Density", f"{stats['Density']:.3f}")
            approx = "" if stats["Exact"] else "\u2248 "
            cols[3].metric("Diameter", f"{approx}{stats['Diameter']}")
            cols[4].metric("Avg Clustering", f"{stats['Avg Clustering']:.3f}",
                           help="Average fraction of a node's neighbours that are also connected to each other")
            cols[5].metric("Avg Path Length", f"{approx}{stats['Avg Path Length']:.2f}",
                           help="Average number of hops on the shortest path between two nodes")
            if not stats["Exact"]:
                st.caption(f"\u2248 Large network: path length and diameter are estimated from "
                           f"{SAMPLE_SIZE} randomly chosen start nodes.")
            if not stats["Connected"]:
                st.caption(f"The graph is disconnected. Diameter and path length use the largest "
                           f"component ({stats['LCC Size']} of {stats['Nodes']} nodes).")

            # Comparison with a random graph
            if st.checkbox("Compare with a random graph (same number of nodes and edges)"):
                st.dataframe(compare_with_random(G, key).round(3))
            
            # Create columns for degree distribution and centrality analysis
            st.markdown("---")  # Add separator
            left_col, right_col = st.columns(2)
            
            # Degree Distribution in left column
            with left_col:
                st.subheader("Degree Distribution")
                scale = st.radio("Scale", ["Histogram", "Log-log (CCDF)"], horizontal=True)
                fig = analyzer.plot_degree_distribution(log_log=(scale == "Log-log (CCDF)"))
                st.pyplot(fig)
                plt.close(fig)
            
            # Centrality Analysis in right column
            with right_col:
                st.subheader("Centrality Analysis")
                centrality_df = analyzer.get_centralities()
                if communities:
                    # same community numbers as the sidebar and the node colours
                    centrality_df.insert(1, 'Community', centrality_df['Node'].map(communities))
                else:
                    st.caption("Tick **Detect Communities** in the sidebar to add a Community column.")
                if len(G) > SAMPLE_THRESHOLD:
                    st.caption(f"\u2248 Large network: Betweenness is estimated from {SAMPLE_SIZE} "
                               "randomly chosen start nodes.")
                st.dataframe(
                    centrality_df,
                    height=400,  # Fixed height to match the plot
                    hide_index=True
                )
        else:
            st.info("Please select or upload a network in the Visualization tab")

if __name__ == "__main__":
    main()
