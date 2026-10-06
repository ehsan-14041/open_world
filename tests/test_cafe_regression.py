"""
The cafe wedge must not move.

It was audited and reached SELLABLE_DEMO_READY before the shop and salon wedges existed. When
its machinery was extracted into `event_sim.wedge` so all three could share it, the only
acceptable outcome was that every number stayed exactly where it was. These are the values
recorded from the audited artifact, hard-coded here so a future refactor cannot quietly move
them.

ONE THING DID CHANGE, and it is not a number. `EventSimulation.fingerprint()` hashes the whole
slice dict, which contains `excluded_systems` — a list of every OTHER module present in the
repository. Adding the shop and salon modules therefore changed the cafe's engine fingerprints
while leaving its coefficients, lags, events, interventions and outputs identical. That was
verified directly: with the two new module files temporarily removed, the engine fingerprints
match the audit exactly again.

The engine is frozen scientific infrastructure and was deliberately not modified. Instead the
reproducibility record now also carries a `trajectory_fingerprint` over only the parts that
determine a trajectory, which is stable across repository states — and that is what this test
pins.
"""

from __future__ import annotations

import pytest

from event_sim.cafe.baseline import DEMO_CAFE
from event_sim.cafe.run import run_comparison
from event_sim.cafe.sensitivity import run_sensitivity

#: From the audited artifact, reports/cafe_demo/cafe_decision_report.json at commit 77189c1.
AUDITED_CASH_DAY_90 = {"A": 16387.8904, "B": 24521.8970, "C": 21462.0722}
AUDITED_MONTHLY_NET = {"A": -1114.9999, "B": 1117.1091, "C": 364.6103}
AUDITED_MODULE_HASH = "2f23cedf54da0e509b51a5406338834dfb301f5bf30392c2d45cbef7d8ec2968"
AUDITED_SHARED_FINGERPRINT = "5ec5e89c2e2bf861057df1ec34cb4c2638085b50d2acfae55ee91c431bacc8b4"
AUDITED_WIN_COUNTS = {"A": 0, "B": 130, "C": 32}
AUDITED_RANKING = ["B", "C", "A"]


@pytest.fixture(scope="module")
def comparison():
    return run_comparison(DEMO_CAFE)


def test_cafe_central_cash_is_unchanged(comparison):
    for world_id, expected in AUDITED_CASH_DAY_90.items():
        assert comparison.by_id(world_id).metrics["cash_day_90"] == pytest.approx(expected, abs=1e-4)


def test_cafe_central_monthly_net_is_unchanged(comparison):
    for world_id, expected in AUDITED_MONTHLY_NET.items():
        assert comparison.by_id(world_id).metrics["monthly_net"] == pytest.approx(expected, abs=1e-4)


def test_cafe_ranking_is_unchanged(comparison):
    assert comparison.ranking() == AUDITED_RANKING


def test_cafe_module_and_shared_fingerprint_are_unchanged(comparison):
    """These two are registry-independent, so they must match the audit exactly."""
    assert comparison.module_semantic_hash == AUDITED_MODULE_HASH
    assert comparison.shared_fingerprint == AUDITED_SHARED_FINGERPRINT


def test_cafe_trajectory_fingerprints_are_distinct_and_recorded(comparison):
    fps = [w.trajectory_fingerprint for w in comparison.worlds]
    assert all(fps), "every world needs a registry-independent fingerprint"
    assert len(set(fps)) == 3, "three different decisions must hash differently"


def test_cafe_sensitivity_counts_are_unchanged():
    sens = run_sensitivity(DEMO_CAFE)
    assert sens.n == 162
    assert sens.win_counts() == AUDITED_WIN_COUNTS
    assert sens.central_ranking == AUDITED_RANKING
    assert sens.dominated_worlds() == ["A"]


def test_cafe_verdict_still_counts_rather_than_predicting():
    sens = run_sensitivity(DEMO_CAFE)
    verdict = sens.verdict()
    assert "130 of the 162" in verdict
    assert "not a probability estimate" in verdict
    for banned in ("chance", "probability of", "% likely", "confidence", "will be"):
        assert banned not in verdict.lower()
