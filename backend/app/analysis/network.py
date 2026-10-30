"""Social network analysis: graph construction, communities, centrality.

Statistical graph relationships only — the system does not claim real-world
coordination, and private IP addresses are never exposed.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict

import networkx as nx
import pandas as pd

from app.utils.column_detect import resolve
from app.utils.errors import ValidationFailed

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Edges represent statistical interaction patterns in the loaded dataset "
    "(mentions, replies, shares). They do not by themselves indicate "
    "coordination, conspiracy, or real-world relationships. Private IP "
    "addresses are never included."
)

MENTION_RE = re.compile(r"@([A-Za-z0-9_]{1,50})")
EDGE_TYPES = ("mention", "reply", "share")


def build_graph(
    df: pd.DataFrame,
    mapping: dict,
    *,
    edge_types: tuple[str, ...] = EDGE_TYPES,
    min_weight: int = 1,
    date_from: str | None = None,
    date_to: str | None = None,
    max_nodes: int = 400,
) -> tuple[nx.Graph, dict]:
    user_col = resolve(mapping, "username") or resolve(mapping, "user_id")
    if not user_col or user_col not in df.columns:
        raise ValidationFailed("Network analysis requires a username/user_id column.")

    work = df.copy()
    ts_col = resolve(mapping, "timestamp")
    if (date_from or date_to) and ts_col and ts_col in work.columns:
        ts = pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        if date_from:
            work = work[ts >= pd.to_datetime(date_from, utc=True, errors="coerce")]
            ts = pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        if date_to:
            work = work[ts <= pd.to_datetime(date_to, utc=True, errors="coerce")]

    text_col = resolve(mapping, "text") or resolve(mapping, "text_clean")
    reply_col = resolve(mapping, "reply_to_username")
    share_col = resolve(mapping, "shared_from_username")
    platform_col = resolve(mapping, "platform")
    likes_col = resolve(mapping, "likes")
    comments_col = resolve(mapping, "comments")
    shares_col = resolve(mapping, "shares")

    edges: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"weight": 0, "types": Counter()}
    )
    node_platform: dict[str, Counter] = defaultdict(Counter)
    node_activity: Counter = Counter()
    node_engagement: Counter = Counter()

    known_users: set[str] | None = None

    for _, row in work.iterrows():
        src = str(row[user_col]) if pd.notna(row[user_col]) else None
        if not src or src == "nan":
            continue
        node_activity[src] += 1
        if platform_col and platform_col in work.columns and pd.notna(row.get(platform_col)):
            node_platform[src][str(row[platform_col])] += 1
        eng = 0.0
        if likes_col and likes_col in work.columns:
            eng += pd.to_numeric(row.get(likes_col), errors="coerce") or 0
        if comments_col and comments_col in work.columns:
            eng += 2 * (pd.to_numeric(row.get(comments_col), errors="coerce") or 0)
        if shares_col and shares_col in work.columns:
            eng += 3 * (pd.to_numeric(row.get(shares_col), errors="coerce") or 0)
        node_engagement[src] += float(eng)

        if "reply" in edge_types and reply_col and reply_col in work.columns:
            target = row.get(reply_col)
            if isinstance(target, str) and target.strip() and target != src:
                key = (src, target.strip())
                edges[key]["weight"] += 1
                edges[key]["types"]["reply"] += 1

        if "share" in edge_types and share_col and share_col in work.columns:
            target = row.get(share_col)
            if isinstance(target, str) and target.strip() and target != src:
                key = (src, target.strip())
                edges[key]["weight"] += 1
                edges[key]["types"]["share"] += 1

        if "mention" in edge_types and text_col and text_col in work.columns:
            text = row.get(text_col)
            if isinstance(text, str):
                for handle in set(MENTION_RE.findall(text)):
                    if handle == src:
                        continue
                    key = (src, handle)
                    edges[key]["weight"] += 1
                    edges[key]["types"]["mention"] += 1

    filtered = {
        k: v for k, v in edges.items() if v["weight"] >= max(1, int(min_weight))
    }

    # Keep the highest-degree nodes if the graph is very large.
    degree_guess: Counter = Counter()
    for (s, t), v in filtered.items():
        degree_guess[s] += v["weight"]
        degree_guess[t] += v["weight"]
    if len(degree_guess) > max_nodes:
        keep = {u for u, _ in degree_guess.most_common(max_nodes)}
        filtered = {k: v for k, v in filtered.items() if k[0] in keep and k[1] in keep}

    G = nx.Graph()
    for (s, t), v in filtered.items():
        dominant = v["types"].most_common(1)[0][0]
        G.add_edge(s, t, weight=v["weight"], edge_type=dominant,
                   types=[t2 for t2, _ in v["types"].most_common()])

    for node in G.nodes:
        G.nodes[node]["platform"] = (
            node_platform[node].most_common(1)[0][0] if node_platform.get(node) else "unknown"
        )
        G.nodes[node]["activity"] = int(node_activity.get(node, 0))
        G.nodes[node]["engagement"] = round(float(node_engagement.get(node, 0.0)), 2)

    stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 5) if G.number_of_nodes() > 1 else 0.0,
        "components": nx.number_connected_components(G) if G.number_of_nodes() else 0,
        "avg_degree": (
            round(sum(dict(G.degree()).values()) / G.number_of_nodes(), 3)
            if G.number_of_nodes()
            else 0
        ),
        "total_interaction_volume": int(sum(v["weight"] for v in filtered.values())),
    }
    return G, stats


def detect_communities(G: nx.Graph) -> dict:
    communities: list[list[str]] = []
    method = "connected_components"
    if G.number_of_nodes() == 0:
        return {"method": method, "communities": [], "count": 0}
    try:
        if hasattr(nx.algorithms.community, "louvain_communities"):
            communities = [
                sorted(c)
                for c in nx.algorithms.community.louvain_communities(
                    G, weight="weight", seed=42
                )
            ]
            method = "louvain"
    except Exception as exc:  # pragma: no cover
        logger.warning("Louvain failed (%s); using connected components.", exc)
        communities = [sorted(c) for c in nx.connected_components(G)]
        method = "connected_components"
    if not communities:
        communities = [sorted(c) for c in nx.connected_components(G)]
        method = "connected_components"

    # Community interaction volume = internal edge weight sum.
    out = []
    for idx, members in enumerate(sorted(communities, key=len, reverse=True)):
        member_set = set(members)
        internal = sum(
            d["weight"]
            for u, v, d in G.edges(data=True)
            if u in member_set and v in member_set
        )
        out.append(
            {
                "id": idx,
                "size": len(members),
                "interaction_volume": int(internal),
                "members": members[:25],
            }
        )
    return {"method": method, "count": len(out), "communities": out}


def compute_centrality(G: nx.Graph) -> dict:
    if G.number_of_nodes() == 0:
        return {"degree": [], "betweenness": [], "pagerank": []}

    degree = sorted(
        ((n, d) for n, d in G.degree(weight="weight")), key=lambda x: -x[1]
    )[:15]

    try:
        if G.number_of_nodes() > 300:
            k = max(10, min(50, G.number_of_nodes() // 10))
            between = nx.betweenness_centrality(G, weight="weight", k=k, seed=42)
        else:
            between = nx.betweenness_centrality(G, weight="weight")
    except Exception as exc:  # pragma: no cover
        logger.warning("Betweenness failed: %s", exc)
        between = {}
    between_top = sorted(between.items(), key=lambda x: -x[1])[:15]

    try:
        pagerank = nx.pagerank(G, weight="weight", max_iter=60)
    except Exception:  # pragma: no cover
        pagerank = {n: 0.0 for n in G.nodes}
    pr_top = sorted(pagerank.items(), key=lambda x: -x[1])[:15]

    # Store back onto nodes so the graph response can color/size by them.
    for n in G.nodes:
        G.nodes[n]["betweenness"] = round(float(between.get(n, 0.0)), 5)
        G.nodes[n]["pagerank"] = round(float(pagerank.get(n, 0.0)), 5)

    return {
        "degree": [{"id": n, "value": int(v)} for n, v in degree],
        "betweenness": [{"id": n, "value": round(float(v), 5)} for n, v in between_top],
        "pagerank": [{"id": n, "value": round(float(v), 5)} for n, v in pr_top],
    }


def graph_payload(
    G: nx.Graph,
    stats: dict,
    communities: dict,
    centrality: dict,
    classification_scores: dict[str, float] | None = None,
) -> dict:
    communities_of = {}
    for comm in communities.get("communities", []):
        for member in comm["members"]:
            communities_of[member] = comm["id"]

    nodes = []
    for n in G.nodes:
        data = G.nodes[n]
        node = {
            "id": n,
            "label": n,
            "platform": data.get("platform", "unknown"),
            "degree": int(G.degree(n)),
            "weighted_degree": int(G.degree(n, weight="weight")),
            "activity": data.get("activity", 0),
            "engagement": data.get("engagement", 0),
            "betweenness": data.get("betweenness", 0.0),
            "pagerank": data.get("pagerank", 0.0),
            "cluster": communities_of.get(n),
        }
        if classification_scores and n in classification_scores:
            node["classification_score"] = round(classification_scores[n], 4)
        nodes.append(node)

    edges = [
        {
            "source": u,
            "target": v,
            "weight": d.get("weight", 1),
            "edge_type": d.get("edge_type", "mention"),
            "types": d.get("types", []),
        }
        for u, v, d in G.edges(data=True)
    ]

    return {
        "disclaimer": DISCLAIMER,
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "communities": communities,
        "centrality": centrality,
    }
