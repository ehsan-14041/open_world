"""
Coherence tests for the cafe wedge — not calibration, coherence.

Each one asks whether the comparison behaves the way any cafe owner would expect it to under
an obvious edge case. A failure here is a reason not to show the product, regardless of how
good the central case looks.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from event_sim.cafe.baseline import DEMO_CAFE
from event_sim.cafe.run import run_comparison


def test_no_cost_shock_means_doing_nothing_changes_nothing():
    c = run_comparison(replace(DEMO_CAFE, supplier_increase_pct=0.0))
    a = c.by_id("A")
    assert a.sim.series("cogs_per_order")[90] == pytest.approx(100.0)
    assert a.metrics["monthly_net"] == pytest.approx(DEMO_CAFE.monthly_net, rel=0.02)
    assert a.metrics["orders_change_pct"] == pytest.approx(0.0)


def test_no_cost_shock_price_rise_gains_only_what_pricing_gives():
    """With no shock, B's gain is pure price-minus-elasticity arithmetic, not a windfall."""
    c = run_comparison(replace(DEMO_CAFE, supplier_increase_pct=0.0))
    b = c.by_id("B")
    # revenue index = (1 - 0.081) * 1.10 = 1.0109 -> about +1.1% revenue at steady state
    assert b.metrics["revenue_change_pct"] == pytest.approx(1.09, abs=0.3)
    assert b.metrics["monthly_net"] - c.by_id("A").metrics["monthly_net"] < 0.06 * DEMO_CAFE.monthly_revenue


def test_zero_elasticity_means_a_price_rise_loses_no_customers():
    c = run_comparison(DEMO_CAFE, custom_elasticity=0.0)
    b = c.by_id("B")
    assert b.sim.series("demand")[90] == pytest.approx(100.0)
    assert b.metrics["orders_change_pct"] == pytest.approx(0.0)
    assert b.metrics["revenue_change_pct"] == pytest.approx(10.0, abs=0.1)


def test_very_high_elasticity_makes_the_bigger_price_rise_less_attractive():
    lo = run_comparison(DEMO_CAFE, custom_elasticity=0.5)
    hi = run_comparison(DEMO_CAFE, custom_elasticity=3.0)
    assert hi.by_id("B").metrics["cash_day_90"] < lo.by_id("B").metrics["cash_day_90"]
    # At 3.0 a 10% rise loses 30% of orders; holding prices should now beat raising them.
    assert hi.ranking().index("A") < hi.ranking().index("B")


def test_zero_reformulation_effectiveness_removes_world_c_cost_advantage():
    c = run_comparison(DEMO_CAFE, reformulation_effectiveness=0.0)
    w = c.by_id("C")
    assert w.spec.cogs_reduction_points == 0.0
    assert w.sim.series("cogs_per_order")[90] == pytest.approx(130.0, abs=0.3)
    assert w.sim.series("demand")[90] == pytest.approx(100.0 - 0.81 * 5.0, abs=0.1)


def test_a_bigger_supplier_shock_makes_holding_prices_more_painful():
    nets = [run_comparison(replace(DEMO_CAFE, supplier_increase_pct=s)).by_id("A").metrics["monthly_net"]
            for s in (10.0, 30.0, 50.0)]
    assert nets[0] > nets[1] > nets[2]


def test_identical_interventions_give_identical_outcomes():
    """World C with a 10% rise and zero reformulation is World B by another name."""
    from event_sim.cafe import worlds
    from event_sim.engine import Intervention, build_simulation
    from event_sim.cafe.run import _slice, DEFAULT_AXES
    from event_sim.engine import SimulationConfig

    s = _slice(None)
    cfg = SimulationConfig(turns=90, axis_settings=dict(DEFAULT_AXES), lag_setting="central", label="cafe")
    shock = worlds.cost_shock(DEMO_CAFE)
    b = build_simulation(s, config=cfg, events=[shock],
                         interventions=[Intervention.from_slice(s, "raise_prices", magnitude=10.0, duration=90)])
    c = build_simulation(s, config=cfg, events=[shock],
                         interventions=[Intervention.from_slice(s, "raise_prices", magnitude=10.0, duration=90),
                                        Intervention.from_slice(s, "reformulate_menu", magnitude=0.0, duration=90)])
    b.run(); c.run()
    assert b.series("demand") == c.series("demand")
    assert b.series("cogs_per_order") == c.series("cogs_per_order")


def test_price_rise_never_raises_orders():
    for setting in ("low", "central", "high"):
        c = run_comparison(DEMO_CAFE, axis_settings={"price_sensitivity": setting})
        assert c.by_id("B").metrics["orders_change_pct"] < 0
        assert c.by_id("C").metrics["orders_change_pct"] < 0


def test_clamping_never_engages_on_the_demo_grid():
    """If a range clamp fired the arithmetic would silently change; make sure it does not."""
    for setting in ("low", "central", "high"):
        for shock in (20.0, 40.0):
            c = run_comparison(replace(DEMO_CAFE, supplier_increase_pct=shock),
                               axis_settings={"price_sensitivity": setting})
            for w in c.worlds:
                clamped = [t for t in w.sim.result()["trajectory"] if t.get("clamped_variables")]
                assert not clamped, f"clamp engaged in world {w.spec.id}"
