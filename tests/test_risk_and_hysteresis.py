"""Unit tests for risk score update and hysteresis logic."""

import random
from unittest.mock import MagicMock

import networkx as nx
import pytest

from risk_containment.models import HealthState, get_node_attr, set_node_attr
from risk_containment.strategies import (
    _ours_isolate,
    _ours_recover,
    _update_risk_score,
    make_ours,
)


@pytest.fixture
def small_graph():
    G = nx.DiGraph()
    G.add_node(0, base_failure_prob=0.01, criticality_weight=3, sla_tier="silver", capacity=100,
               current_load=0, health_state=HealthState.HEALTHY, risk_score=0.0,
               steps_isolated_high_risk=0, steps_recovered_low_risk=0, cooldown_remaining=0,
               error_rate_proxy=0.0, recent_failures=0)
    G.add_node(1, base_failure_prob=0.01, criticality_weight=2, sla_tier="bronze", capacity=50,
               current_load=0, health_state=HealthState.HEALTHY, risk_score=0.0,
               steps_isolated_high_risk=0, steps_recovered_low_risk=0, cooldown_remaining=0,
               error_rate_proxy=0.0, recent_failures=0)
    G.add_edge(0, 1, call_rate_weight=0.8, coupling_weight=0.7)
    G.graph["entry_nodes"] = [0]
    G.graph["sink_nodes"] = [1]
    return G


def test_risk_score_update_clamped(small_graph):
    """Risk score stays in [0, 1] with use_clamp=True."""
    G = small_graph
    set_node_attr(G, 0, "error_rate_proxy", 1.0)
    set_node_attr(G, 0, "current_load", 100)
    set_node_attr(G, 0, "capacity", 50)
    _update_risk_score(G, use_smoothing=True, use_clamp=True)
    r0 = get_node_attr(G, 0, "risk_score")
    assert 0 <= r0 <= 1.0
    r1 = get_node_attr(G, 1, "risk_score")
    assert 0 <= r1 <= 1.0


def test_risk_score_upstream_proagation(small_graph):
    """Downstream node gets some risk from upstream when upstream has high risk."""
    G = small_graph
    set_node_attr(G, 0, "risk_score", 0.9)
    set_node_attr(G, 0, "error_rate_proxy", 0.9)
    _update_risk_score(G, use_smoothing=False, use_clamp=True)
    r1 = get_node_attr(G, 1, "risk_score")
    assert r1 > 0


def test_hysteresis_isolate_after_k_steps(small_graph):
    """Isolation only happens after risk >= thresh for K consecutive steps."""
    G = small_graph
    set_node_attr(G, 0, "risk_score", 0.8)
    set_node_attr(G, 0, "steps_isolated_high_risk", 0)
    out1 = _ours_isolate(G, thresh_isolate=0.7, k_steps=2)
    assert 0 not in out1
    out2 = _ours_isolate(G, thresh_isolate=0.7, k_steps=2)
    assert 0 in out2


def test_hysteresis_recover_after_m_steps(small_graph):
    """Re-enable only after risk <= thresh for M consecutive steps."""
    G = small_graph
    set_node_attr(G, 0, "health_state", HealthState.ISOLATED)
    set_node_attr(G, 0, "risk_score", 0.2)
    set_node_attr(G, 0, "steps_recovered_low_risk", 0)
    out1 = _ours_recover(G, thresh_recover=0.35, m_steps=3)
    assert 0 not in out1
    out2 = _ours_recover(G, thresh_recover=0.35, m_steps=3)
    assert 0 not in out2
    out3 = _ours_recover(G, thresh_recover=0.35, m_steps=3)
    assert 0 in out3


def test_make_ours_returns_three_callables():
    isolate, recover, pre_step = make_ours()
    assert callable(isolate)
    assert callable(recover)
    assert callable(pre_step)


def test_ours_no_hysteresis_does_not_isolate(small_graph):
    """OURS_NO_HYSTERESIS: isolate/recover return empty sets."""
    from risk_containment.strategies import get_strategy
    isolate, recover, pre_step = get_strategy("OURS_NO_HYSTERESIS")
    out = isolate(small_graph)
    assert out == set()
