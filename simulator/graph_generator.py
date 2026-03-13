"""Service dependency graphs: scale-free, small-world, random (NetworkX)."""

from __future__ import annotations

import random
from typing import Any

import networkx as nx

from risk_containment.models import HealthState, make_edge_attrs, make_node_attrs


def _to_directed(G_undir: nx.Graph, rng: random.Random) -> nx.DiGraph:
    D = nx.DiGraph()
    D.add_nodes_from(G_undir.nodes())
    for u, v in G_undir.edges():
        D.add_edge(u, v) if rng.random() < 0.5 else D.add_edge(v, u)
    return D


def _assign_attrs(G: nx.DiGraph, rng: random.Random) -> None:
    for n in G.nodes():
        G.nodes[n].update(
            make_node_attrs(
                capacity=rng.uniform(100, 500),
                base_failure_prob=rng.uniform(0.005, 0.02),
                sla_tier=rng.choice(["gold", "silver", "bronze"]),
                criticality_weight=rng.randint(1, 5),
                current_load=0.0,
                error_rate_proxy=0.0,
                health_state=HealthState.HEALTHY,
            )
        )
    for u, v in G.edges():
        G.edges[u, v].update(
            make_edge_attrs(
                call_rate_weight=rng.uniform(0.2, 1.0),
                coupling_weight=rng.uniform(0.2, 1.0),
            )
        )


def _entry_sink(G: nx.DiGraph, n_entry: int, n_sink: int, rng: random.Random) -> list[Any]:
    nodes = list(G.nodes())
    if not nodes:
        return []
    out_deg = sorted(((n, G.out_degree(n)) for n in nodes), key=lambda x: -x[1])
    entry = [x[0] for x in out_deg[: min(n_entry, len(nodes))]]
    in_deg = sorted(((n, G.in_degree(n)) for n in nodes), key=lambda x: -x[1])
    sink = [x[0] for x in in_deg[: min(n_sink, len(nodes))]]
    G.graph["entry_nodes"] = entry
    G.graph["sink_nodes"] = sink
    return entry


def create_scale_free_graph(
    n: int,
    m: int = 2,
    n_entry: int = 5,
    n_sink: int = 5,
    seed: int | None = None,
) -> nx.DiGraph:
    """Barabási–Albert (undirected) then random edge orientation."""
    rng = random.Random(seed)
    m = max(1, min(m, n - 1))
    G = _to_directed(nx.barabasi_albert_graph(n, m, seed=seed), rng)
    _assign_attrs(G, rng)
    _entry_sink(G, n_entry, n_sink, rng)
    return G


def create_small_world_graph(
    n: int,
    k: int = 4,
    p: float = 0.2,
    n_entry: int = 5,
    n_sink: int = 5,
    seed: int | None = None,
) -> nx.DiGraph:
    """Watts–Strogatz then random edge orientation."""
    rng = random.Random(seed)
    k = min(k, n - 1)
    G = _to_directed(nx.watts_strogatz_graph(n, k, p, seed=seed), rng)
    _assign_attrs(G, rng)
    _entry_sink(G, n_entry, n_sink, rng)
    return G


def create_random_graph(
    n: int,
    p: float = 0.1,
    n_entry: int = 5,
    n_sink: int = 5,
    seed: int | None = None,
) -> nx.DiGraph:
    """Erdős–Rényi then random edge orientation; ensures at least some edges."""
    rng = random.Random(seed)
    G_undir = nx.erdos_renyi_graph(n, p, seed=seed)
    if not G_undir.edges():
        for _ in range(min(n, 2 * n)):
            u, v = rng.sample(range(n), 2)
            G_undir.add_edge(u, v)
    G = _to_directed(G_undir, rng)
    _assign_attrs(G, rng)
    _entry_sink(G, n_entry, n_sink, rng)
    return G


def get_entry_nodes(G: nx.DiGraph) -> list[Any]:
    return list(G.graph.get("entry_nodes", []))
