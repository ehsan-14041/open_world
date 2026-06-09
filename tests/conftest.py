"""
Shared pytest fixtures for the Strategic Decision Intelligence test suite.

Factories (return a callable) so each test gets a FRESH, independently-mutable copy:
  - make_world(state, turn=0)        -> a bare WorldModel
  - l4_scenario()                    -> the canonical L4 pricing scenario (raw dict)
  - causal_scenario()               -> a normalized pricing scenario with a causal graph
  - threshold_scenario()            -> the normalized Path-A threshold fixture (JSON)
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from schemas.scenario_schema import normalize_scenario
from core.world_model import WorldModel

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---- canonical scenario definitions (private; copied per call) ----

_L4_PRICING: dict = {
    "description": "B2B SaaS pricing",
    "initial_state": {"price": 100, "churn_rate": 0.15, "customers": 500, "mrr": 50000, "cash": 1200000},
    "variable_specs": {
        "price": {"min": 0, "behavior_type": "FLOW"},
        "churn_rate": {"min": 0, "max": 0.5, "behavior_type": "FLOW"},
        "customers": {"min": 0, "behavior_type": "STOCK"},
        "mrr": {"min": 0, "behavior_type": "STOCK"},
        "cash": {"min": 0, "behavior_type": "STOCK"},
    },
    "initial_agents": [
        {"name": "founder", "role": "Founder", "objectives": {"mrr": 0.6, "cash": 0.4}},
        {"name": "competitor", "role": "Competitor", "objectives": {"customers": 1.0}},
    ],
    "causal_links": [
        {"from": "price", "to": "churn_rate", "polarity": "positive", "strength": 0.5},
        {"from": "churn_rate", "to": "customers", "polarity": "negative", "strength": 0.7},
        {"from": "customers", "to": "mrr", "polarity": "positive", "strength": 0.8},
        {"from": "mrr", "to": "cash", "polarity": "positive", "strength": 0.6},
        {"from": "cash", "to": "price", "polarity": "negative", "strength": 0.2},
    ],
    "allowed_actions": ["increase_price", "decrease_price", "steady"],
    "rules": [
        {"id": "churn_cliff", "condition_key": "var_above", "effect_key": "scale_var",
         "params": {"var": "churn_rate", "threshold": 0.4, "target": "mrr", "factor": 0.7}}
    ],
}

_CAUSAL_PRICING: dict = {
    "description": "B2B SaaS pricing decision",
    "initial_state": {"price": 100.0, "churn": 15.0, "customers": 500.0, "mrr": 50000.0, "system_stability": 70.0},
    "causal_links": [
        {"from": "price", "to": "churn", "polarity": "positive", "strength": 0.5},
        {"from": "churn", "to": "customers", "polarity": "negative", "strength": 0.7},
        {"from": "customers", "to": "mrr", "polarity": "positive", "strength": 0.8},
        {"from": "churn", "to": "system_stability", "polarity": "negative", "strength": 0.5},
    ],
    "initial_agents": [
        {"name": "founder", "role": "Founder", "objectives": {"mrr": 0.6, "customers": 0.4}},
        {"name": "customers", "role": "Customer", "objectives": {"churn": -0.5}},
    ],
    "allowed_actions": ["increase_price", "decrease_price", "retain_customers", "steady"],
}


@pytest.fixture
def make_world():
    """Factory for a bare WorldModel: make_world({"mrr": 100}, turn=2)."""
    def _make(state: dict, turn: int = 0) -> WorldModel:
        return WorldModel(global_state=dict(state), variables=None, causal_links=[], relations=[],
                          entities={}, narrative=[], ontology={}, version=0, turn=turn, events=[])
    return _make


@pytest.fixture
def l4_scenario():
    """Factory: a fresh raw copy of the canonical L4 pricing scenario."""
    return lambda: copy.deepcopy(_L4_PRICING)


@pytest.fixture
def causal_scenario():
    """Factory: a fresh normalized pricing scenario with a causal graph."""
    return lambda: normalize_scenario(copy.deepcopy(_CAUSAL_PRICING))


@pytest.fixture
def threshold_scenario():
    """Factory: the normalized Path-A threshold fixture (tests/fixtures/threshold_startup.json)."""
    raw = json.loads((_FIXTURES / "threshold_startup.json").read_text(encoding="utf-8"))
    return lambda: normalize_scenario(copy.deepcopy(raw))
