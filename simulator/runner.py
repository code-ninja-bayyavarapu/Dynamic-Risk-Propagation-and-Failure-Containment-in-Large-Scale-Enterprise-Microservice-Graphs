"""Simulation loop: workload -> failure model -> risk propagation -> containment."""

from __future__ import annotations

from typing import Any, Callable

import networkx as nx

from risk_containment.models import HealthState, set_node_attr
from risk_containment.strategies import get_strategy

from simulator.failure_model import FailureModel
from simulator.graph_generator import get_entry_nodes
from simulator.metrics import SimulationMetrics, collect_snapshot
from simulator.workload import WorkloadGenerator


def _reset(G: nx.DiGraph) -> None:
    for n in G.nodes():
        set_node_attr(G, n, "health_state", HealthState.HEALTHY)
        set_node_attr(G, n, "current_load", 0)
        set_node_attr(G, n, "risk_score", 0.0)
        set_node_attr(G, n, "cooldown_remaining", 0)
        set_node_attr(G, n, "recent_failures", 0)
        set_node_attr(G, n, "steps_isolated_high_risk", 0)
        set_node_attr(G, n, "steps_recovered_low_risk", 0)
        set_node_attr(G, n, "error_rate_proxy", 0.0)
    G.graph["request_scale"] = 1.0


def run_simulation(
    G: nx.DiGraph,
    steps: int,
    seed: int,
    *,
    lambda_per_entry: float = 30.0,
    scenario_inject: Callable[[nx.DiGraph, int], None] | None = None,
    strategy_name: str = "NO_CONTAINMENT",
) -> list[dict[str, Any]]:
    _reset(G)
    workload = WorkloadGenerator(lambda_per_entry=lambda_per_entry, seed=seed)
    failure = FailureModel(seed=seed + 1)
    entry_nodes = get_entry_nodes(G)
    isolate_fn, recover_fn, pre_step_fn = get_strategy(strategy_name)
    metrics_collector = SimulationMetrics(G, steps)

    for step in range(steps):
        if scenario_inject:
            scenario_inject(G, step)
        request_scale = G.graph.get("request_scale", 1.0)
        workload.step(G, entry_nodes=entry_nodes, request_scale=request_scale)
        failure.step(G)
        if pre_step_fn:
            pre_step_fn(G, step)
        if isolate_fn:
            for n in isolate_fn(G):
                set_node_attr(G, n, "health_state", HealthState.ISOLATED)
        if recover_fn:
            for n in recover_fn(G):
                set_node_attr(G, n, "health_state", HealthState.DEGRADED)
        snap = collect_snapshot(G)
        metrics_collector.record(step, snap)

    return metrics_collector.snapshots


def run_and_metrics(
    G: nx.DiGraph,
    steps: int,
    seed: int,
    strategy_name: str,
    scenario_name: str,
    scenario_inject: Callable[[nx.DiGraph, int], None] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    snapshots = run_simulation(
        G, steps, seed,
        scenario_inject=scenario_inject,
        strategy_name=strategy_name,
        **kwargs,
    )
    metrics_collector = SimulationMetrics(G, steps)
    metrics_collector.snapshots = snapshots
    out = metrics_collector.compute()
    return {
        "strategy": strategy_name,
        "scenario": scenario_name,
        "seed": seed,
        "graph_size": G.number_of_nodes(),
        "cascade_size_peak": out["cascade_peak_size"],
        "time_to_containment": out["containment_time"],
        "total_failed_steps": out["total_failed_steps"],
        "sla_violations": out["SLA_violations"],
        "throughput_completed": out["throughput_completed"],
        "false_isolations": out["false_isolations"],
        "mttr": out["MTTR"],
    }
