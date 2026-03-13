"""Graph generation for microservice dependency graphs."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import networkx as nx

from risk_containment.models import (
    HealthState,
    make_edge_attrs,
    make_node_attrs,
)

def _assign_node_attrs(
    G: nx.DiGraph,
    entry_nodes: list[Any],
    sink_nodes: list[Any],
    rng: random.Random,
) -> None:
    """Assign capacities, weights, SLA tiers to nodes."""
    for n in G.nodes():
        cap = max(10.0, rng.gammavariate(2, 50) + 20)
        crit = rng.randint(1, 5)
        tier_choice = rng.choices(
            ["gold", "silver", "bronze"],
            weights=[0.2, 0.5, 0.3],
        )[0]
        base_fail = 0.005 + rng.random() * 0.02
        G.nodes[n].update(
            make_node_attrs(
                base_failure_prob=base_fail,
                criticality_weight=crit,
                sla_tier=tier_choice,
                capacity=cap,
                health_state=HealthState.HEALTHY,
            )
        )
    for u, v in G.edges():
        cr = 0.2 + rng.random() * 0.8
        cw = 0.2 + rng.random() * 0.8
        G.edges[u, v].update(
            make_edge_attrs(call_rate_weight=cr, coupling_weight=cw)
        )


def scale_free_directed(
    n: int,
    entry_count: int = 5,
    sink_count: int = 5,
    seed: int | None = None,
) -> nx.DiGraph:
    """Generate a scale-free directed graph."""
    rng = random.Random(seed)
    G = nx.DiGraph()
    if n < 3:
        n = 3
    for i in range(min(5, n)):
        G.add_node(i)
    for i in range(min(4, n - 1)):
        G.add_edge(i, i + 1)
    for i in range(5, n):
        G.add_node(i)
        out_degree = rng.randint(1, min(4, i))
        targets = list(G.nodes())[:i]
        if not targets:
            continue
        weights = [G.in_degree(t) + 1 for t in targets]
        total = sum(weights)
        chosen = set()
        for _ in range(out_degree):
            r = rng.uniform(0, total)
            for t, w in zip(targets, weights):
                if t in chosen:
                    continue
                r -= w
                if r <= 0:
                    chosen.add(t)
                    G.add_edge(i, t)
                    break
        in_degree = rng.randint(0, min(3, i))
        sources = [x for x in targets if x not in chosen][:i]
        if sources and in_degree > 0:
            sw = [G.out_degree(s) + 1 for s in sources]
            stotal = sum(sw)
            for _ in range(in_degree):
                r = rng.uniform(0, stotal)
                for s, w in zip(sources, sw):
                    r -= w
                    if r <= 0:
                        G.add_edge(s, i)
                        break
    if G.number_of_edges() < n:
        for _ in range(n):
            u, v = rng.sample(list(G.nodes()), 2)
            if u != v and not G.has_edge(u, v):
                G.add_edge(u, v)
    out_deg = [(n, G.out_degree(n)) for n in G.nodes()]
    in_deg = [(n, G.in_degree(n)) for n in G.nodes()]
    out_deg.sort(key=lambda x: -x[1])
    sink_candidates = [(n, G.in_degree(n) - G.out_degree(n)) for n in G.nodes()]
    sink_candidates.sort(key=lambda x: -x[1])
    entry_nodes = [x[0] for x in out_deg[: max(1, min(entry_count, n))]]
    sink_nodes = [x[0] for x in sink_candidates[: max(1, min(sink_count, n))]]
    _assign_node_attrs(G, entry_nodes, sink_nodes, rng)
    G.graph["entry_nodes"] = entry_nodes
    G.graph["sink_nodes"] = sink_nodes
    return G


def small_world_directed(
    n: int,
    entry_count: int = 5,
    sink_count: int = 5,
    k: int = 4,
    p: float = 0.2,
    seed: int | None = None,
) -> nx.DiGraph:
    """Generate a small-world style directed graph."""
    rng = random.Random(seed)
    G = nx.DiGraph()
    for i in range(n):
        G.add_node(i)
    k = min(k, n - 1)
    for i in range(n):
        for j in range(1, k // 2 + 1):
            target = (i + j) % n
            if rng.random() < p:
                target = rng.choice([x for x in range(n) if x != i])
            G.add_edge(i, target)
    entry_nodes = rng.sample(list(G.nodes()), min(entry_count, n))
    sink_nodes = rng.sample(
        [x for x in G.nodes() if x not in entry_nodes], min(sink_count, n)
    )
    if not sink_nodes and n > entry_count:
        sink_nodes = [x for x in G.nodes() if x not in entry_nodes][:sink_count]
    _assign_node_attrs(G, entry_nodes, sink_nodes, rng)
    G.graph["entry_nodes"] = entry_nodes
    G.graph["sink_nodes"] = sink_nodes
    return G


def load_graph_from_json(path: str | Path) -> nx.DiGraph:
    """Load a microservice graph from a JSON file."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    G = nx.DiGraph()
    nodes = data.get("nodes", data.get("services", []))
    edges = data.get("edges", data.get("dependencies", []))
    for nd in nodes:
        if isinstance(nd, dict):
            nid = nd.get("id", nd.get("name", str(len(G.nodes()))))
            G.add_node(
                nid,
                **make_node_attrs(
                    base_failure_prob=nd.get("base_failure_prob", 0.01),
                    criticality_weight=nd.get("criticality_weight", 3),
                    sla_tier=nd.get("sla_tier", "silver"),
                    capacity=float(nd.get("capacity", 100)),
                    health_state=HealthState.HEALTHY,
                )
            )
        else:
            G.add_node(nd, **make_node_attrs(health_state=HealthState.HEALTHY))
    for e in edges:
        if isinstance(e, dict):
            u = e.get("from", e.get("source", e.get("caller")))
            v = e.get("to", e.get("target", e.get("callee")))
            G.add_edge(
                u,
                v,
                **make_edge_attrs(
                    call_rate_weight=e.get("call_rate_weight", 0.5),
                    coupling_weight=e.get("coupling_weight", 0.5),
                    is_critical_path=e.get("is_critical_path", False),
                ),
            )
        else:
            u, v = e[0], e[1]
            G.add_edge(u, v, **make_edge_attrs())
    entry = data.get("entry_nodes", [])
    if not entry and nodes:
        entry = [
            n.get("id", n.get("name", str(i))) if isinstance(n, dict) else n
            for i, n in enumerate(nodes[:3])
        ]
    sink = data.get("sink_nodes", [])
    if not entry and G.nodes():
        entry = list(G.nodes())[:3]
    G.graph["entry_nodes"] = entry[: len(G.nodes())]
    G.graph["sink_nodes"] = sink or list(G.nodes())[-3:]
    return G


def get_entry_nodes(G: nx.DiGraph) -> list[Any]:
    """Return entry nodes."""
    return list(G.graph.get("entry_nodes", []))


def get_sink_nodes(G: nx.DiGraph) -> list[Any]:
    """Return sink nodes."""
    return list(G.graph.get("sink_nodes", []))
