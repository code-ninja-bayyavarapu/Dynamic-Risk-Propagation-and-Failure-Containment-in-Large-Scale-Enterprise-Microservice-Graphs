"""Data models for microservice graph and simulator state."""

from __future__ import annotations

from enum import Enum
from typing import Any

import networkx as nx


class HealthState(str, Enum):
    """Node health state."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    ISOLATED = "ISOLATED"


class SLATier(str, Enum):
    """SLA tier for services."""

    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


def make_node_attrs(
    base_failure_prob: float = 0.01,
    criticality_weight: int = 3,
    sla_tier: str = "silver",
    capacity: float = 100.0,
    current_load: float = 0.0,
    health_state: HealthState = HealthState.HEALTHY,
    risk_score: float = 0.0,
    steps_failed: int = 0,
    steps_isolated_high_risk: int = 0,
    steps_recovered_low_risk: int = 0,
    cooldown_remaining: int = 0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build node attributes dict for a service."""
    return {
        "base_failure_prob": base_failure_prob,
        "criticality_weight": min(5, max(1, criticality_weight)),
        "sla_tier": sla_tier,
        "capacity": max(1.0, capacity),
        "current_load": current_load,
        "health_state": health_state,
        "risk_score": risk_score,
        "steps_failed": steps_failed,
        "steps_isolated_high_risk": steps_isolated_high_risk,
        "steps_recovered_low_risk": steps_recovered_low_risk,
        "cooldown_remaining": cooldown_remaining,
        "error_rate_proxy": 0.0,
        "recent_failures": 0,
        **kwargs,
    }


def make_edge_attrs(
    call_rate_weight: float = 0.5,
    coupling_weight: float = 0.5,
    is_critical_path: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build edge attributes dict for a dependency."""
    return {
        "call_rate_weight": max(0.0, min(1.0, call_rate_weight)),
        "coupling_weight": max(0.0, min(1.0, coupling_weight)),
        "is_critical_path": is_critical_path,
        **kwargs,
    }


def get_node_attr(G: nx.DiGraph, node: Any, key: str, default: Any = None) -> Any:
    """Safe get node attribute."""
    return G.nodes[node].get(key, default)


def get_edge_attr(
    G: nx.DiGraph, u: Any, v: Any, key: str, default: Any = None
) -> Any:
    """Safe get edge attribute."""
    if not G.has_edge(u, v):
        return default
    return G.edges[u, v].get(key, default)


def set_node_attr(G: nx.DiGraph, node: Any, key: str, value: Any) -> None:
    """Set node attribute."""
    G.nodes[node][key] = value


def set_edge_attr(G: nx.DiGraph, u: Any, v: Any, key: str, value: Any) -> None:
    """Set edge attribute."""
    if G.has_edge(u, v):
        G.edges[u, v][key] = value
