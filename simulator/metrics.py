"""Per-run metrics: cascade peak, failed steps, SLA violations, throughput, MTTR, containment time."""

from __future__ import annotations

from typing import Any

import networkx as nx

from risk_containment.models import get_node_attr


def _cascade_size(snap: dict[str, Any]) -> int:
    return snap.get("n_degraded", 0) + snap.get("n_failed", 0) + snap.get("n_isolated", 0)


def _state_str(s) -> str:
    return s.value if hasattr(s, "value") else str(s)


def collect_snapshot(G: nx.DiGraph) -> dict[str, Any]:
    n_healthy = n_degraded = n_failed = n_isolated = 0
    for n in G.nodes():
        state = get_node_attr(G, n, "health_state", None)
        s = _state_str(state) if state is not None else "healthy"
        if s in ("HEALTHY", "healthy"):
            n_healthy += 1
        elif s in ("DEGRADED", "degraded"):
            n_degraded += 1
        elif s in ("FAILED", "failed"):
            n_failed += 1
        elif s in ("ISOLATED", "isolated"):
            n_isolated += 1
        else:
            n_healthy += 1
    return {"n_healthy": n_healthy, "n_degraded": n_degraded, "n_failed": n_failed, "n_isolated": n_isolated}


class SimulationMetrics:
    def __init__(self, G: nx.DiGraph, steps_total: int):
        self.G = G
        self.steps_total = steps_total
        self.snapshots: list[dict[str, Any]] = []
        self._gold = [n for n in G.nodes() if get_node_attr(G, n, "sla_tier") == "gold"]

    def record(self, step: int, snap: dict[str, Any]) -> None:
        snap["step"] = step
        self.snapshots.append(snap)

    def compute(self) -> dict[str, Any]:
        if not self.snapshots:
            return {
                "cascade_peak_size": 0,
                "total_failed_steps": 0,
                "SLA_violations": 0,
                "throughput_completed": 0.0,
                "MTTR": 0,
                "false_isolations": 0,
                "containment_time": 0,
            }
        cascade_sizes = [_cascade_size(s) for s in self.snapshots]
        total_failed = sum(s.get("n_failed", 0) for s in self.snapshots)
        sla = sum(1 for s in self.snapshots if (s.get("n_failed", 0) + s.get("n_degraded", 0) > 0 and self._gold))
        throughput = sum(s.get("n_healthy", 0) * 0.5 for s in self.snapshots)
        n_nodes = len(self.G.nodes())
        mttr = 0
        for i in range(len(self.snapshots) - 1, -1, -1):
            if cascade_sizes[i] <= max(1, int(n_nodes * 0.05)):
                mttr = len(self.snapshots) - 1 - i
                break
        containment_time = len(self.snapshots)
        for i in range(2, len(self.snapshots)):
            if cascade_sizes[i] <= cascade_sizes[i - 1] <= cascade_sizes[i - 2]:
                containment_time = i
                break
        return {
            "cascade_peak_size": max(cascade_sizes),
            "total_failed_steps": total_failed,
            "SLA_violations": sla,
            "throughput_completed": round(throughput, 2),
            "MTTR": mttr,
            "false_isolations": 0,
            "containment_time": containment_time,
        }
