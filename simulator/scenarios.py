"""Chaos injectors: latency spike, zone outage, noisy neighbor, rolling failures."""

from __future__ import annotations

import random
from typing import Any, Callable

import networkx as nx

from risk_containment.models import HealthState, get_node_attr, set_node_attr


def scenario_latency_spike(
    core_node_id: Any,
    steps_start: int,
    steps_duration: int,
    capacity_factor: float = 0.4,
) -> Callable[[nx.DiGraph, int], None]:
    def inject(G: nx.DiGraph, step: int) -> None:
        if core_node_id not in G:
            return
        if steps_start <= step < steps_start + steps_duration:
            cap = get_node_attr(G, core_node_id, "capacity", 100)
            if "capacity_original" not in G.nodes[core_node_id]:
                G.nodes[core_node_id]["capacity_original"] = cap
            set_node_attr(G, core_node_id, "capacity", max(1, cap * capacity_factor))
        elif "capacity_original" in G.nodes[core_node_id]:
            set_node_attr(G, core_node_id, "capacity", G.nodes[core_node_id]["capacity_original"])
    return inject


def scenario_zone_outage(
    node_ids: list[Any],
    steps_start: int,
    steps_duration: int,
    fail_fraction: float = 0.08,
    seed: int | None = None,
) -> Callable[[nx.DiGraph, int], None]:
    rng = random.Random(seed)
    n_fail = max(1, int(len(node_ids) * fail_fraction))

    def inject(G: nx.DiGraph, step: int) -> None:
        if steps_start <= step < steps_start + steps_duration:
            for n in rng.sample(node_ids, min(n_fail, len(node_ids))):
                if n in G:
                    set_node_attr(G, n, "health_state", HealthState.FAILED)
                    set_node_attr(G, n, "cooldown_remaining", 5)
    return inject


def scenario_noisy_neighbor(
    mid_node_id: Any,
    steps_start: int,
    steps_duration: int,
    extra_load: float = 150.0,
) -> Callable[[nx.DiGraph, int], None]:
    def inject(G: nx.DiGraph, step: int) -> None:
        if mid_node_id not in G:
            return
        if steps_start <= step < steps_start + steps_duration:
            cur = get_node_attr(G, mid_node_id, "current_load", 0)
            set_node_attr(G, mid_node_id, "current_load", cur + extra_load)
            if get_node_attr(G, mid_node_id, "health_state") == HealthState.HEALTHY:
                set_node_attr(G, mid_node_id, "health_state", HealthState.DEGRADED)
    return inject


def scenario_rolling_failures(
    steps_start: int,
    steps_duration: int,
    fail_fraction_per_step: float = 0.01,
    seed: int | None = None,
) -> Callable[[nx.DiGraph, int], None]:
    rng = random.Random(seed)

    def inject(G: nx.DiGraph, step: int) -> None:
        if steps_start <= step < steps_start + steps_duration:
            nodes = list(G.nodes())
            k = max(1, int(len(nodes) * fail_fraction_per_step))
            for n in rng.sample(nodes, min(k, len(nodes))):
                if get_node_attr(G, n, "health_state") != HealthState.ISOLATED:
                    set_node_attr(G, n, "health_state", HealthState.FAILED)
                    set_node_attr(G, n, "cooldown_remaining", 5)
    return inject


def get_scenario_injector(
    scenario_name: str,
    G: nx.DiGraph,
    steps_total: int,
    seed: int,
) -> Callable[[nx.DiGraph, int], None] | None:
    nodes = list(G.nodes())
    entry = list(G.graph.get("entry_nodes", nodes[:1]))
    if not nodes:
        return None
    start, duration = steps_total // 5, steps_total // 3
    rng = random.Random(seed)
    if scenario_name in ("S1", "latency_spike", "Latency spike"):
        return scenario_latency_spike(entry[0] if entry else nodes[0], start, duration)
    if scenario_name in ("S2", "zone_outage", "Zone outage"):
        n_zone = max(1, int(len(nodes) * rng.uniform(0.05, 0.10)))
        return scenario_zone_outage(rng.sample(nodes, min(n_zone, len(nodes))), start, duration, seed=seed)
    if scenario_name in ("S3", "noisy_neighbor", "Noisy neighbor"):
        return scenario_noisy_neighbor(nodes[len(nodes) // 2] if len(nodes) > 1 else nodes[0], start, duration)
    if scenario_name in ("S4", "rolling_failures", "Rolling failures"):
        return scenario_rolling_failures(start, duration, seed=seed)
    return None
