"""Time-stepped discrete-event simulator for microservice dependency graphs."""

from __future__ import annotations

import random
from typing import Any, Callable

import networkx as nx

from risk_containment.models import (
    HealthState,
    get_edge_attr,
    get_node_attr,
    set_node_attr,
)
from risk_containment.graph_gen import get_entry_nodes


DEFAULT_STEPS = 200
DEFAULT_REQUESTS_PER_ENTRY = 30
DEFAULT_COOLDOWN_STEPS = 5
DEFAULT_DEGRADED_FAILURE_BOOST = 0.15
DEFAULT_UPSTREAM_FAILURE_BOOST = 0.25
OVERLOAD_THRESHOLD = 0.9


def _propagate_load(
    G: nx.DiGraph,
    entry_nodes: list[Any],
    requests_per_entry: float,
    rng: random.Random,
) -> dict[Any, float]:
    """Propagate requests from entry nodes downstream; return load per node."""
    scale = G.graph.get("request_scale", 1.0)
    requests_per_entry = requests_per_entry * scale
    load: dict[Any, float] = {n: 0.0 for n in G.nodes()}
    for ent in entry_nodes:
        if ent not in G or get_node_attr(G, ent, "health_state") == HealthState.ISOLATED:
            continue
        if get_node_attr(G, ent, "health_state") == HealthState.FAILED:
            continue
        req = requests_per_entry * (0.8 + rng.random() * 0.4)
        load[ent] = load.get(ent, 0) + req
    changed = True
    for _ in range(G.number_of_nodes() + 1):
        if not changed:
            break
        changed = False
        for u, v in G.edges():
            if get_node_attr(G, u, "health_state") in (HealthState.ISOLATED, HealthState.FAILED):
                continue
            if get_node_attr(G, v, "health_state") == HealthState.ISOLATED:
                continue
            cr = get_edge_attr(G, u, v, "call_rate_weight", 0.5)
            out_edges = list(G.out_edges(u))
            if out_edges:
                cr = cr / max(1, len(out_edges))
            inc = load.get(u, 0) * cr
            if inc > 0:
                old = load.get(v, 0)
                load[v] = old + inc
                if old + inc != old:
                    changed = True
    return load


def _apply_failures(
    G: nx.DiGraph,
    rng: random.Random,
    degraded_failure_boost: float = 0.15,
    upstream_failure_boost: float = 0.25,
) -> None:
    """Apply independent and correlated failures."""
    for n in list(G.nodes()):
        state = get_node_attr(G, n, "health_state", HealthState.HEALTHY)
        if state == HealthState.ISOLATED:
            continue
        base = get_node_attr(G, n, "base_failure_prob", 0.01)
        capacity = get_node_attr(G, n, "capacity", 100)
        load = get_node_attr(G, n, "current_load", 0)
        fail_prob = base
        if state == HealthState.DEGRADED or (capacity and load > OVERLOAD_THRESHOLD * capacity):
            fail_prob = min(0.99, fail_prob + degraded_failure_boost)
        for u, v in G.in_edges(n):
            if v != n:
                continue
            if get_node_attr(G, u, "health_state") == HealthState.FAILED:
                cw = get_edge_attr(G, u, v, "coupling_weight", 0.5)
                cr = get_edge_attr(G, u, v, "call_rate_weight", 0.5)
                fail_prob = min(0.99, fail_prob + upstream_failure_boost * (cw * 0.5 + cr * 0.5))
        if rng.random() < fail_prob:
            set_node_attr(G, n, "health_state", HealthState.FAILED)
            set_node_attr(G, n, "cooldown_remaining", get_node_attr(G, n, "cooldown_steps", 5))
            set_node_attr(G, n, "recent_failures", get_node_attr(G, n, "recent_failures", 0) + 1)
            set_node_attr(G, n, "steps_failed", get_node_attr(G, n, "steps_failed", 0) + 1)


def _apply_recovery(G: nx.DiGraph, cooldown_steps: int = 5) -> None:
    """Recovery: FAILED -> cooldown -> DEGRADED; DEGRADED -> HEALTHY if load ok."""
    for n in G.nodes():
        state = get_node_attr(G, n, "health_state", HealthState.HEALTHY)
        if state == HealthState.FAILED:
            rem = get_node_attr(G, n, "cooldown_remaining", cooldown_steps)
            if rem <= 1:
                set_node_attr(G, n, "health_state", HealthState.DEGRADED)
                set_node_attr(G, n, "cooldown_remaining", 0)
            else:
                set_node_attr(G, n, "cooldown_remaining", rem - 1)
        elif state == HealthState.DEGRADED:
            cap = get_node_attr(G, n, "capacity", 100)
            load = get_node_attr(G, n, "current_load", 0)
            if cap and load <= OVERLOAD_THRESHOLD * cap * 0.8:
                set_node_attr(G, n, "health_state", HealthState.HEALTHY)
        rf = get_node_attr(G, n, "recent_failures", 0)
        if rf > 0:
            set_node_attr(G, n, "recent_failures", max(0, rf - 1))


def step(
    G: nx.DiGraph,
    rng: random.Random,
    requests_per_entry: float = 30,
    strategy_isolate: Callable[[nx.DiGraph], set[Any]] | None = None,
    strategy_recover: Callable[[nx.DiGraph], set[Any]] | None = None,
    strategy_pre_step: Callable[[nx.DiGraph, int], None] | None = None,
    degraded_failure_boost: float = 0.15,
    upstream_failure_boost: float = 0.25,
    cooldown_steps: int = 5,
    step_index: int = 0,
) -> None:
    """Execute one simulation step."""
    entry_nodes = get_entry_nodes(G)
    if strategy_pre_step:
        strategy_pre_step(G, step_index)
    load = _propagate_load(G, entry_nodes, requests_per_entry, rng)
    for n in G.nodes():
        set_node_attr(G, n, "current_load", load.get(n, 0))
        cap = get_node_attr(G, n, "capacity", 100)
        if cap and load.get(n, 0) > OVERLOAD_THRESHOLD * cap:
            if get_node_attr(G, n, "health_state") == HealthState.HEALTHY:
                set_node_attr(G, n, "health_state", HealthState.DEGRADED)
    _apply_failures(G, rng, degraded_failure_boost, upstream_failure_boost)
    _apply_recovery(G, cooldown_steps)
    if strategy_isolate:
        to_isolate = strategy_isolate(G)
        for n in to_isolate:
            set_node_attr(G, n, "health_state", HealthState.ISOLATED)
    if strategy_recover:
        to_recover = strategy_recover(G)
        for n in to_recover:
            if get_node_attr(G, n, "health_state") == HealthState.ISOLATED:
                set_node_attr(G, n, "health_state", HealthState.DEGRADED)
    for n in G.nodes():
        state = get_node_attr(G, n, "health_state", HealthState.HEALTHY)
        load_n = get_node_attr(G, n, "current_load", 0)
        if state == HealthState.FAILED:
            set_node_attr(G, n, "error_rate_proxy", 1.0)
        elif load_n > 0:
            cap = get_node_attr(G, n, "capacity", 100)
            set_node_attr(
                G, n, "error_rate_proxy",
                min(1.0, 0.2 + 0.8 * (load_n / cap) if cap else 0.2),
            )
        else:
            set_node_attr(G, n, "error_rate_proxy", 0.0)


def run_simulation(
    G: nx.DiGraph,
    seed: int,
    steps: int = 200,
    requests_per_entry: float = 30,
    strategy_isolate: Callable[[nx.DiGraph], set[Any]] | None = None,
    strategy_recover: Callable[[nx.DiGraph], set[Any]] | None = None,
    strategy_pre_step: Callable[[nx.DiGraph, int], None] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Run simulation for `steps` steps; return per-step snapshots."""
    rng = random.Random(seed)
    for n in G.nodes():
        set_node_attr(G, n, "health_state", HealthState.HEALTHY)
        set_node_attr(G, n, "current_load", 0)
        set_node_attr(G, n, "risk_score", 0.0)
        set_node_attr(G, n, "cooldown_remaining", 0)
        set_node_attr(G, n, "steps_failed", 0)
        set_node_attr(G, n, "steps_isolated_high_risk", 0)
        set_node_attr(G, n, "steps_recovered_low_risk", 0)
        set_node_attr(G, n, "error_rate_proxy", 0.0)
        set_node_attr(G, n, "recent_failures", 0)
    snapshots = []
    for t in range(steps):
        step(
            G,
            rng,
            requests_per_entry=requests_per_entry,
            strategy_isolate=strategy_isolate,
            strategy_recover=strategy_recover,
            strategy_pre_step=strategy_pre_step,
            step_index=t,
            **kwargs,
        )
        snap = {
            "step": t,
            "n_healthy": sum(1 for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.HEALTHY),
            "n_degraded": sum(1 for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.DEGRADED),
            "n_failed": sum(1 for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.FAILED),
            "n_isolated": sum(1 for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.ISOLATED),
        }
        snapshots.append(snap)
    return snapshots
