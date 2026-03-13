"""Chaos / failure injection scenarios for experiments."""

from __future__ import annotations

import random
from typing import Any, Callable

import networkx as nx

from risk_containment.models import HealthState, get_node_attr, set_node_attr
from risk_containment.graph_gen import get_entry_nodes


def scenario_latency_spike(
    core_node_id: Any,
    steps_start: int,
    steps_duration: int,
    overload_factor: float = 2.0,
) -> Callable[[nx.DiGraph, int], None]:
    """S1: Latency spike / overload in a core dependency for N steps. We simulate by reducing effective capacity of that node."""
    def inject(G: nx.DiGraph, step_index: int) -> None:
        if core_node_id not in G:
            return
        if steps_start <= step_index < steps_start + steps_duration:
            cap = get_node_attr(G, core_node_id, "capacity", 100)
            G.nodes[core_node_id]["capacity_original"] = G.nodes[core_node_id].get("capacity_original", cap)
            set_node_attr(G, core_node_id, "capacity", cap / overload_factor)
        else:
            if "capacity_original" in G.nodes[core_node_id]:
                set_node_attr(G, core_node_id, "capacity", G.nodes[core_node_id]["capacity_original"])
    return inject


def scenario_zone_outage(
    node_ids: list[Any],
    steps_start: int,
    steps_duration: int,
    fail_prob: float = 0.8,
) -> Callable[[nx.DiGraph, int], None]:
    """S2: Zone outage: randomly fail a correlated cluster of nodes for N steps."""
    rng = random.Random(steps_start)
    def inject(G: nx.DiGraph, step_index: int) -> None:
        if steps_start <= step_index < steps_start + steps_duration:
            for n in node_ids:
                if n in G and rng.random() < fail_prob:
                    if "base_failure_prob_original" not in G.nodes[n]:
                        G.nodes[n]["base_failure_prob_original"] = get_node_attr(G, n, "base_failure_prob", 0.01)
                    set_node_attr(G, n, "health_state", HealthState.FAILED)
                    set_node_attr(G, n, "base_failure_prob", 0.99)
        else:
            for n in node_ids:
                if n in G and "base_failure_prob_original" in G.nodes[n]:
                    set_node_attr(G, n, "base_failure_prob", G.nodes[n]["base_failure_prob_original"])
    return inject


def scenario_noisy_neighbor(
    mid_tier_node_id: Any,
    steps_start: int,
    steps_duration: int,
    extra_load: float = 80.0,
) -> Callable[[nx.DiGraph, int], None]:
    """S3: Noisy neighbor: sustained overload on a mid-tier service (add extra load)."""
    def inject(G: nx.DiGraph, step_index: int) -> None:
        if mid_tier_node_id not in G:
            return
        if steps_start <= step_index < steps_start + steps_duration:
            cur = get_node_attr(G, mid_tier_node_id, "current_load", 0)
            set_node_attr(G, mid_tier_node_id, "current_load", cur + extra_load)
            if get_node_attr(G, mid_tier_node_id, "health_state") == HealthState.HEALTHY:
                set_node_attr(G, mid_tier_node_id, "health_state", HealthState.DEGRADED)
    return inject


def scenario_rolling_failures(
    fail_fraction: float = 0.01,
    steps_start: int = 10,
    steps_duration: int = 50,
    seed: int = 42,
) -> Callable[[nx.DiGraph, int], None]:
    """S4: Rolling failures: fail 1% of nodes per step for T steps."""
    rng = random.Random(seed)
    def inject(G: nx.DiGraph, step_index: int) -> None:
        if steps_start <= step_index < steps_start + steps_duration:
            nodes = list(G.nodes())
            k = max(1, int(len(nodes) * fail_fraction))
            chosen = rng.sample(nodes, min(k, len(nodes)))
            for n in chosen:
                if get_node_attr(G, n, "health_state") not in (HealthState.ISOLATED,):
                    set_node_attr(G, n, "health_state", HealthState.FAILED)
                    set_node_attr(G, n, "cooldown_remaining", 5)
    return inject


def get_scenario_injector(
    scenario_name: str,
    G: nx.DiGraph,
    steps_total: int,
    seed: int,
) -> Callable[[nx.DiGraph, int], None] | None:
    """Return a pre_step injector for the given scenario, or None."""
    entry = get_entry_nodes(G)
    nodes = list(G.nodes())
    if not nodes:
        return None
    rng = random.Random(seed)
    start = steps_total // 5
    duration = steps_total // 3
    if scenario_name == "S1" or scenario_name == "latency_spike":
        core = entry[0] if entry else nodes[0]
        return scenario_latency_spike(core, start, duration)
    if scenario_name == "S2" or scenario_name == "zone_outage":
        cluster_size = min(1 + int(len(nodes) * 0.1), len(nodes))
        cluster = rng.sample(nodes, cluster_size)
        return scenario_zone_outage(cluster, start, duration)
    if scenario_name == "S3" or scenario_name == "noisy_neighbor":
        mid = nodes[len(nodes) // 2] if nodes else nodes[0]
        return scenario_noisy_neighbor(mid, start, duration)
    if scenario_name == "S4" or scenario_name == "rolling_failures":
        return scenario_rolling_failures(steps_start=start, steps_duration=duration, seed=seed)
    return None
