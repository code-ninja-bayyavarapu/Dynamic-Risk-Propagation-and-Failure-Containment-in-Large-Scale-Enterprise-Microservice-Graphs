"""Poisson request load at entry nodes; propagation along dependency edges."""

from __future__ import annotations

import math
import random
from typing import Any

import networkx as nx

from risk_containment.models import get_edge_attr, get_node_attr, set_node_attr


def _blocked(G: nx.DiGraph, n: Any) -> bool:
    s = get_node_attr(G, n, "health_state", None)
    if s is None:
        return False
    state = s.value if hasattr(s, "value") else str(s)
    return state in ("ISOLATED", "FAILED")


class WorkloadGenerator:
    def __init__(self, lambda_per_entry: float = 30.0, seed: int | None = None):
        self.lambda_per_entry = lambda_per_entry
        self.rng = random.Random(seed)

    def _poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        L = math.exp(-lam)
        k, p = 0, 1.0
        while p > L:
            k += 1
            p *= self.rng.random()
        return k - 1

    def step(
        self,
        G: nx.DiGraph,
        entry_nodes: list[Any] | None = None,
        request_scale: float = 1.0,
    ) -> dict[Any, float]:
        if entry_nodes is None:
            entry_nodes = list(G.graph.get("entry_nodes", []))
        if not entry_nodes:
            entry_nodes = [list(G.nodes())[0]] if G.nodes() else []

        lam = self.lambda_per_entry * request_scale
        load: dict[Any, float] = {n: 0.0 for n in G.nodes()}
        for ent in entry_nodes:
            if ent not in G or _blocked(G, ent):
                continue
            load[ent] = load.get(ent, 0) + float(self._poisson(lam))

        for _ in range(G.number_of_nodes() + 1):
            changed = False
            for u, v in G.edges():
                if _blocked(G, u) or _blocked(G, v):
                    continue
                cr = get_edge_attr(G, u, v, "call_rate_weight", 0.5)
                out_deg = G.out_degree(u)
                if out_deg > 0:
                    cr /= out_deg
                inc = load.get(u, 0) * cr
                if inc > 0:
                    prev = load.get(v, 0)
                    load[v] = prev + inc
                    changed = changed or (load[v] != prev)
            if not changed:
                break

        for n in G.nodes():
            set_node_attr(G, n, "current_load", load.get(n, 0))
        return load
