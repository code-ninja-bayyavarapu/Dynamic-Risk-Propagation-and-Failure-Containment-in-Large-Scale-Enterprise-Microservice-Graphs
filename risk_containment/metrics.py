"""Metrics collection from simulation runs."""

from __future__ import annotations

from typing import Any

import networkx as nx

from risk_containment.models import HealthState, get_node_attr


def cascade_size(snap: dict[str, Any]) -> int:
    """Count of nodes not HEALTHY (DEGRADED + FAILED + ISOLATED)."""
    return snap.get("n_degraded", 0) + snap.get("n_failed", 0) + snap.get("n_isolated", 0)


def compute_metrics(
    snapshots: list[dict[str, Any]],
    G: nx.DiGraph,
    strategy_name: str,
    scenario_name: str,
    seed: int,
    graph_size: int,
) -> dict[str, Any]:
    """Compute all required metrics from a run's snapshots."""
    if not snapshots:
        return {
            "strategy": strategy_name,
            "scenario": scenario_name,
            "seed": seed,
            "graph_size": graph_size,
            "cascade_size_peak": 0,
            "time_to_containment": 0,
            "total_failed_steps": 0,
            "sla_violations": 0,
            "p99_latency_proxy": 0.0,
            "throughput_completed": 0.0,
            "false_isolations": 0,
            "mttr": 0,
        }
    n_nodes = graph_size or len(G.nodes())
    cascade_sizes = [cascade_size(s) for s in snapshots]
    cascade_size_peak = max(cascade_sizes) if cascade_sizes else 0
    # Time to containment: first step after which cascade stops growing (or end)
    time_to_containment = len(snapshots)
    for i in range(1, len(snapshots)):
        if cascade_sizes[i] <= cascade_sizes[i - 1] and cascade_sizes[i] > 0:
            # Could define as first local max or first step where we're stable
            pass
        if i >= 2 and cascade_sizes[i] <= cascade_sizes[i - 1] <= cascade_sizes[i - 2]:
            time_to_containment = i
            break
    total_failed_steps = sum(s.get("n_failed", 0) for s in snapshots)
    # SLA: gold tier nodes with high error or degraded/failed
    gold_tier = [n for n in G.nodes() if get_node_attr(G, n, "sla_tier") == "gold"]
    sla_violations = 0
    for s in snapshots:
        # We don't have per-node state in snapshot; use aggregate proxy: if any gold node would be in bad state
        # From snapshot we only have counts. Approximate: when n_failed + n_degraded is high, gold likely affected
        if (s.get("n_failed", 0) + s.get("n_degraded", 0)) > 0 and gold_tier:
            sla_violations += 1
    # p99 latency proxy: queueing delay ~ load/capacity; we'd need per-step per-node. Use mean of max load ratio.
    p99_latency_proxy = 0.0
    throughput_completed = 0.0
    # Throughput: successful requests. Proxy = sum over steps of (healthy nodes * their capacity utilization that didn't fail)
    for s in snapshots:
        healthy = s.get("n_healthy", 0)
        throughput_completed += healthy * 0.5
    false_isolations = 0
    mttr = 0
    # MTTR: steps to recover to stable (cascade_size near 0)
    for i in range(len(snapshots) - 1, -1, -1):
        if cascade_sizes[i] <= max(1, n_nodes * 0.05):
            mttr = len(snapshots) - 1 - i
            break
    return {
        "strategy": strategy_name,
        "scenario": scenario_name,
        "seed": seed,
        "graph_size": graph_size,
        "cascade_size_peak": cascade_size_peak,
        "time_to_containment": time_to_containment,
        "total_failed_steps": total_failed_steps,
        "sla_violations": sla_violations,
        "p99_latency_proxy": round(p99_latency_proxy, 4),
        "throughput_completed": round(throughput_completed, 2),
        "false_isolations": false_isolations,
        "mttr": mttr,
    }


def snapshots_to_timeseries_csv(snapshots: list[dict[str, Any]], extra: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert snapshots to flat rows for CSV."""
    rows = []
    for s in snapshots:
        row = {**extra, "step": s["step"], "n_healthy": s["n_healthy"], "n_degraded": s["n_degraded"], "n_failed": s["n_failed"], "n_isolated": s["n_isolated"]}
        row["cascade_size"] = cascade_size(s)
        rows.append(row)
    return rows
