"""Containment strategies: ours (risk-based), baselines, and ablations."""

from __future__ import annotations

from typing import Any, Callable

import networkx as nx

from risk_containment.models import (
    HealthState,
    get_edge_attr,
    get_node_attr,
    set_node_attr,
)

# --- Our method parameters ---
THRESH_ISOLATE = 0.7
THRESH_RECOVER = 0.35
K_STEPS_ISOLATE = 2
M_STEPS_RECOVER = 3
EMA_ALPHA = 0.3
MAX_ISOLATED_BUDGET = 50
COOLDOWN_STEPS = 5


def _update_risk_score(
    G: nx.DiGraph,
    use_smoothing: bool = True,
    use_clamp: bool = True,
    ema_alpha: float = EMA_ALPHA,
) -> None:
    """Update risk_score per node: local signals + upstream propagation, EMA, clamp [0,1]."""
    updates: dict[Any, float] = {}
    for n in G.nodes():
        local = 0.0
        err = get_node_attr(G, n, "error_rate_proxy", 0.0)
        local += err * 0.4
        load = get_node_attr(G, n, "current_load", 0)
        cap = get_node_attr(G, n, "capacity", 100)
        if cap and load > 0.9 * cap:
            local += 0.3
        rf = get_node_attr(G, n, "recent_failures", 0)
        local += min(0.3, rf * 0.15)
        if get_node_attr(G, n, "health_state") == HealthState.FAILED:
            local = max(local, 0.9)
        upstream = 0.0
        for u, v in G.in_edges(n):
            if v != n:
                continue
            ru = get_node_attr(G, u, "risk_score", 0.0)
            cw = get_edge_attr(G, u, v, "coupling_weight", 0.5)
            cr = get_edge_attr(G, u, v, "call_rate_weight", 0.5)
            upstream += ru * (cw * 0.5 + cr * 0.5)
        in_deg = G.in_degree(n)
        if in_deg > 0:
            upstream = upstream / in_deg
        raw = min(1.0, local * 0.6 + upstream * 0.4)
        if use_smoothing:
            old = get_node_attr(G, n, "risk_score", 0.0)
            raw = ema_alpha * raw + (1 - ema_alpha) * old
        if use_clamp:
            raw = max(0.0, min(1.0, raw))
        updates[n] = raw
    for n, v in updates.items():
        set_node_attr(G, n, "risk_score", v)


def _ours_isolate(
    G: nx.DiGraph,
    thresh_isolate: float = THRESH_ISOLATE,
    k_steps: int = K_STEPS_ISOLATE,
    impact_aware: bool = True,
    max_isolated: int = MAX_ISOLATED_BUDGET,
) -> set[Any]:
    """Nodes to isolate: risk >= thresh for k steps; impact-aware prefers low criticality; cap by budget."""
    to_isolate: set[Any] = set()
    n_isolated = sum(1 for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.ISOLATED)
    budget = max(0, max_isolated - n_isolated)
    candidates = []
    for n in G.nodes():
        if get_node_attr(G, n, "health_state") == HealthState.ISOLATED:
            continue
        if get_node_attr(G, n, "health_state") == HealthState.FAILED:
            continue
        r = get_node_attr(G, n, "risk_score", 0.0)
        if r >= thresh_isolate:
            k = get_node_attr(G, n, "steps_isolated_high_risk", 0) + 1
            set_node_attr(G, n, "steps_isolated_high_risk", k)
            if k >= k_steps:
                crit = get_node_attr(G, n, "criticality_weight", 3)
                candidates.append((n, crit))
        else:
            set_node_attr(G, n, "steps_isolated_high_risk", 0)
    if impact_aware:
        candidates.sort(key=lambda x: x[1])
    for n, _ in candidates:
        if len(to_isolate) >= budget:
            break
        to_isolate.add(n)
    return to_isolate


def _ours_recover(
    G: nx.DiGraph,
    thresh_recover: float = THRESH_RECOVER,
    m_steps: int = M_STEPS_RECOVER,
) -> set[Any]:
    """Re-enable ISOLATED nodes that have risk <= thresh for m steps."""
    to_recover: set[Any] = set()
    for n in G.nodes():
        if get_node_attr(G, n, "health_state") != HealthState.ISOLATED:
            set_node_attr(G, n, "steps_recovered_low_risk", 0)
            continue
        r = get_node_attr(G, n, "risk_score", 0.0)
        if r <= thresh_recover:
            m = get_node_attr(G, n, "steps_recovered_low_risk", 0) + 1
            set_node_attr(G, n, "steps_recovered_low_risk", m)
            if m >= m_steps:
                to_recover.add(n)
        else:
            set_node_attr(G, n, "steps_recovered_low_risk", 0)
    return to_recover


def make_ours(
    thresh_isolate: float = THRESH_ISOLATE,
    thresh_recover: float = THRESH_RECOVER,
    k_steps: int = K_STEPS_ISOLATE,
    m_steps: int = M_STEPS_RECOVER,
    use_hysteresis: bool = True,
    use_smoothing: bool = True,
    use_clamp: bool = True,
    impact_aware: bool = True,
    max_isolated: int = MAX_ISOLATED_BUDGET,
) -> tuple[Callable[[nx.DiGraph], set[Any]], Callable[[nx.DiGraph], set[Any]], Callable[[nx.DiGraph, int], None]]:
    """Return (isolate_fn, recover_fn, pre_step_fn) for our method."""
    def pre_step(G: nx.DiGraph, step_index: int) -> None:
        _update_risk_score(G, use_smoothing=use_smoothing, use_clamp=use_clamp)
    def isolate(G: nx.DiGraph) -> set[Any]:
        if not use_hysteresis:
            return set()
        return _ours_isolate(
            G,
            thresh_isolate=thresh_isolate,
            k_steps=k_steps if use_hysteresis else 1,
            impact_aware=impact_aware,
            max_isolated=max_isolated,
        )
    def recover(G: nx.DiGraph) -> set[Any]:
        if not use_hysteresis:
            return set()
        return _ours_recover(G, thresh_recover=thresh_recover, m_steps=m_steps if use_hysteresis else 1)
    return (isolate, recover, pre_step)


# --- Baselines ---

def no_containment_isolate(G: nx.DiGraph) -> set[Any]:
    """B0: No containment."""
    return set()


def no_containment_recover(G: nx.DiGraph) -> set[Any]:
    return set()


def static_circuit_breaker_isolate(G: nx.DiGraph) -> set[Any]:
    """B1: Isolate only when node FAILS; fixed cooldown."""
    return set()


def static_circuit_breaker_recover(G: nx.DiGraph) -> set[Any]:
    """Re-enable never here; FAILED nodes recover via simulator cooldown -> DEGRADED. We isolate on next step when FAILED."""
    return set()


def static_circuit_breaker_isolate_impl(G: nx.DiGraph, cooldown: int = COOLDOWN_STEPS) -> set[Any]:
    """B1: After a node fails, we treat it as isolated for cooldown (simulator already does FAILED->cooldown->DEGRADED). So B1 = isolate node when it just failed, keep it out of receiving traffic. Actually spec says: isolate when FAILS, keep isolated for fixed cooldown then re-enable. So we ISOLATE on failure (same as taking it out of flow). So: if state==FAILED, set ISOLATED and set cooldown; after cooldown steps, recover. So isolate set = {n : state was FAILED or we already isolated it and cooldown not expired}. We need to track per-node cooldown for isolation. Use cooldown_remaining for FAILED; for B1 we isolate on fail and use same counter."""
    to_isolate: set[Any] = set()
    for n in G.nodes():
        state = get_node_attr(G, n, "health_state", HealthState.HEALTHY)
        if state == HealthState.FAILED:
            to_isolate.add(n)
        elif state == HealthState.ISOLATED:
            rem = get_node_attr(G, n, "cooldown_remaining", 0)
            if rem > 0:
                to_isolate.add(n)
            else:
                set_node_attr(G, n, "cooldown_remaining", 0)
    return to_isolate


def static_circuit_breaker_recover_impl(G: nx.DiGraph, cooldown: int = COOLDOWN_STEPS) -> set[Any]:
    to_recover: set[Any] = set()
    for n in G.nodes():
        if get_node_attr(G, n, "health_state") != HealthState.ISOLATED:
            continue
        rem = get_node_attr(G, n, "cooldown_remaining", 0)
        if rem <= 0:
            to_recover.add(n)
    return to_recover


def make_static_circuit_breaker(cooldown: int = COOLDOWN_STEPS):
    """B1: Isolate on failure, re-enable after cooldown."""
    def isolate(G: nx.DiGraph) -> set[Any]:
        out = set()
        for n in G.nodes():
            if get_node_attr(G, n, "health_state") == HealthState.FAILED:
                out.add(n)
                set_node_attr(G, n, "cooldown_remaining", cooldown)
            elif get_node_attr(G, n, "health_state") == HealthState.ISOLATED:
                rem = get_node_attr(G, n, "cooldown_remaining", 0)
                if rem > 0:
                    set_node_attr(G, n, "cooldown_remaining", rem - 1)
                    out.add(n)
        return out
    def recover(G: nx.DiGraph) -> set[Any]:
        return {n for n in G.nodes() if get_node_attr(G, n, "health_state") == HealthState.ISOLATED and get_node_attr(G, n, "cooldown_remaining", 1) <= 0}
    return (isolate, recover, None)


def local_only_isolate(G: nx.DiGraph, error_thresh: float = 0.6, load_thresh: float = 0.95) -> set[Any]:
    """B2: Isolate if local error/overload exceeds threshold; no upstream propagation."""
    to_isolate: set[Any] = set()
    for n in G.nodes():
        if get_node_attr(G, n, "health_state") in (HealthState.ISOLATED, HealthState.FAILED):
            continue
        err = get_node_attr(G, n, "error_rate_proxy", 0.0)
        load = get_node_attr(G, n, "current_load", 0)
        cap = get_node_attr(G, n, "capacity", 100)
        overload = (load / cap > load_thresh) if cap else False
        if err >= error_thresh or overload:
            to_isolate.add(n)
    return to_isolate


def local_only_recover(G: nx.DiGraph, error_thresh: float = 0.4) -> set[Any]:
    to_recover: set[Any] = set()
    for n in G.nodes():
        if get_node_attr(G, n, "health_state") != HealthState.ISOLATED:
            continue
        err = get_node_attr(G, n, "error_rate_proxy", 0.0)
        if err <= error_thresh:
            to_recover.add(n)
    return to_recover


def make_local_only(error_thresh: float = 0.6, recover_thresh: float = 0.4, load_thresh: float = 0.95):
    def isolate(G: nx.DiGraph) -> set[Any]:
        return local_only_isolate(G, error_thresh=error_thresh, load_thresh=load_thresh)
    def recover(G: nx.DiGraph) -> set[Any]:
        return local_only_recover(G, error_thresh=recover_thresh)
    return (isolate, recover, None)


# B3: Rate limit only — throttle at entry when system error rises; no targeted isolation.
# We implement by reducing requests_per_entry in pre_step when global error rate is high.
_rate_limit_global_error: list[float] = []


def make_rate_limit_only(
    error_thresh: float = 0.2,
    throttle_factor: float = 0.5,
) -> tuple[Callable[[nx.DiGraph], set[Any]], Callable[[nx.DiGraph], set[Any]], Callable[[nx.DiGraph, int], None] | None]:
    """B3: No isolation; pre_step will be applied by runner to reduce workload (we cannot change requests_per_entry from inside step). So we need to pass a flag or store in G.graph that runner reads. Alternatively: in pre_step we mark entry nodes as "shed" so load is reduced. Easiest: in simulator, support a graph-level 'request_scale' that multiplies requests_per_entry. Strategy sets G.graph['request_scale'] in pre_step."""
    def pre_step(G: nx.DiGraph, step_index: int) -> None:
        total_err = 0.0
        total_load = 0.0
        for n in G.nodes():
            load = get_node_attr(G, n, "current_load", 0)
            cap = get_node_attr(G, n, "capacity", 100)
            if cap and load > 0:
                total_err += get_node_attr(G, n, "error_rate_proxy", 0) * load
                total_load += load
        if total_load > 0:
            global_err = total_err / total_load
        else:
            global_err = 0.0
        if global_err > error_thresh:
            G.graph["request_scale"] = throttle_factor
        else:
            G.graph["request_scale"] = 1.0
    return (lambda G: set(), lambda G: set(), pre_step)


def get_strategy(name: str, **kwargs: Any):
    """Resolve strategy by name. Returns (isolate, recover, pre_step)."""
    if name == "NO_CONTAINMENT" or name == "B0":
        return (no_containment_isolate, no_containment_recover, None)
    if name == "STATIC_CIRCUIT_BREAKER" or name == "B1":
        return make_static_circuit_breaker(cooldown=kwargs.get("cooldown", COOLDOWN_STEPS))
    if name == "LOCAL_ONLY_ISOLATION" or name == "B2":
        return make_local_only()
    if name == "RATE_LIMIT_ONLY" or name == "B3":
        return make_rate_limit_only()
    if name == "OURS":
        return make_ours(**kwargs)
    if name == "OURS_NO_HYSTERESIS":
        return make_ours(use_hysteresis=False)
    if name == "OURS_NO_CAP":
        return make_ours(use_clamp=False)
    if name == "OURS_NO_SMOOTHING":
        return make_ours(use_smoothing=False)
    if name == "OURS_NO_IMPACT_AWARE":
        return make_ours(impact_aware=False)
    return (no_containment_isolate, no_containment_recover, None)
