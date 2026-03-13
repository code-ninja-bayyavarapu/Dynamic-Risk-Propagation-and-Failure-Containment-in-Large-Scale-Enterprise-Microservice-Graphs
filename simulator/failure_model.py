"""Failure probability: base + overload_penalty + upstream_failure_influence."""

from __future__ import annotations

import random
from typing import Any

import networkx as nx

from risk_containment.models import HealthState, get_edge_attr, get_node_attr, set_node_attr


def _state(G: nx.DiGraph, n: Any):
    return get_node_attr(G, n, "health_state", None)


def _upstream_risk(G: nx.DiGraph, n: Any) -> float:
    preds = list(G.predecessors(n))
    if not preds:
        return 0.0
    total = 0.0
    for u in preds:
        s = _state(G, u)
        risk = 1.0 if s == HealthState.FAILED else get_node_attr(G, u, "risk_score", 0.0)
        cw = get_edge_attr(G, u, n, "coupling_weight", 0.5)
        total += risk * (0.5 + 0.5 * cw)
    return total / len(preds)


class FailureModel:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def step(self, G: nx.DiGraph, cooldown_steps: int = 5) -> None:
        for n in G.nodes():
            s = _state(G, n)
            if s == HealthState.FAILED:
                cooldown = get_node_attr(G, n, "cooldown_remaining", cooldown_steps)
                if cooldown <= 1:
                    set_node_attr(G, n, "health_state", HealthState.DEGRADED)
                    set_node_attr(G, n, "cooldown_remaining", 0)
                else:
                    set_node_attr(G, n, "cooldown_remaining", cooldown - 1)
            elif s == HealthState.DEGRADED:
                cap = get_node_attr(G, n, "capacity", 100)
                load = get_node_attr(G, n, "current_load", 0)
                if cap and load <= 0.8 * cap:
                    set_node_attr(G, n, "health_state", HealthState.HEALTHY)

        for n in list(G.nodes()):
            s = _state(G, n)
            if s == HealthState.ISOLATED:
                continue
            if s == HealthState.FAILED:
                set_node_attr(G, n, "error_rate_proxy", 1.0)
                continue

            base = get_node_attr(G, n, "base_failure_prob", 0.01)
            capacity = get_node_attr(G, n, "capacity", 100)
            load = get_node_attr(G, n, "current_load", 0)
            overload_penalty = min(0.5, (load - capacity) / capacity) if capacity and load > capacity else 0.0
            failure_prob = min(0.99, base + overload_penalty + 0.3 * _upstream_risk(G, n))

            if self.rng.random() < failure_prob:
                set_node_attr(G, n, "health_state", HealthState.FAILED)
                set_node_attr(G, n, "cooldown_remaining", cooldown_steps)
                set_node_attr(G, n, "recent_failures", get_node_attr(G, n, "recent_failures", 0) + 1)
                set_node_attr(G, n, "error_rate_proxy", 1.0)
            else:
                err = (0.2 + 0.8 * (load / capacity)) if capacity and load > 0 else 0.0
                set_node_attr(G, n, "error_rate_proxy", min(1.0, err))
