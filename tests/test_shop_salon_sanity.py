"""
Coherence tests for the shop and salon wedges — not calibration, coherence.

Each one asks whether the comparison behaves the way any owner would expect it to under an
obvious edge case. A failure here is a reason not to show the product, regardless of how good
the central case looks.

These are also the tests that would have caught the salon's original structural bug, where the
demand-growth event was injected straight into the variable the price elasticity feeds. The
engine holds an event's target and discards relaxation, so the elasticity was silently inert
and every option showed identical demand. `test_a_price_rise_reduces_appointments_wanted` and
`test_no_event_target_is_also_an_edge_target` both fail on that structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_sim.salon.baseline import DEMO_SALON
from event_sim.salon.wedge import SALON_WEDGE
from event_sim.shop.baseline import DEMO_SHOP
from event_sim.shop.wedge import SHOP_WEDGE
from event_sim.wedge.compare import run_comparison
from event_sim.wedge.registry import WEDGES

ROOT = Path(__file__).resolve().parent.parent


# ---- structural -----------------------------------------------------------------------------

@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_no_event_target_is_also_an_edge_target(wedge_id):
    """
    An event HOLDS its target, discarding the relaxation term — so any edge pointing at that
    same variable becomes inert without warning. Shocks must therefore land on an exogenous
    driver that propagates through an edge, never on an endogenous variable.
    """
    wedge = WEDGES[wedge_id]
    module = json.loads(
        (ROOT / "world_models" / "small_business" / f"{wedge.module_id}.json").read_text(encoding="utf-8"))
    edge_targets = {e["target"] for e in module["edges"]}

    slice_ = __import__("event_sim.wedge.compare", fromlist=["wedge_slice"]).wedge_slice(wedge, None)
    baseline = wedge.demo_factory()
    for spec in wedge.build_worlds(slice_, baseline, **wedge.knob_defaults):
        for event in spec.events:
            for target in event.targets:
                assert target not in edge_targets, (
                    f"{wedge_id}: event {event.id} holds {target!r}, which is also an edge target — "
                    f"every edge into it would be silently disabled")


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_all_three_worlds_share_one_model_and_one_configuration(wedge_id):
    """The commercial claim is controlled comparison; this is what makes it checkable."""
    wedge = WEDGES[wedge_id]
    comp = run_comparison(wedge, wedge.demo_factory())
    assert len({w.fingerprint for w in comp.worlds}) == 3, "worlds must differ"
    assert comp.shared_fingerprint, "the shared part must be hashed"
    # Only events and interventions may differ, so identical specs must give identical results.
    assert len(comp.worlds) == 3


# ---- shop ------------------------------------------------------------------------------------

def test_shop_zero_supplier_shock_removes_the_shock():
    comp = run_comparison(SHOP_WEDGE, DEMO_SHOP.replace(supplier_increase_pct=0.0))
    a = comp.by_id("A")
    assert a.sim.series("unit_cost")[90] == pytest.approx(100.0)
    assert a.metrics["monthly_net"] == pytest.approx(DEMO_SHOP.monthly_net, rel=0.02)
    assert a.metrics["orders_change_pct"] == pytest.approx(0.0)


def test_shop_zero_elasticity_loses_no_orders_to_a_price_rise():
    comp = run_comparison(SHOP_WEDGE, DEMO_SHOP, custom_elasticity=0.0)
    b = comp.by_id("B")
    assert b.sim.series("demand")[90] == pytest.approx(100.0)
    assert b.metrics["orders_change_pct"] == pytest.approx(0.0)


def test_shop_extreme_elasticity_makes_a_price_rise_unattractive():
    lo = run_comparison(SHOP_WEDGE, DEMO_SHOP, custom_elasticity=0.3)
    hi = run_comparison(SHOP_WEDGE, DEMO_SHOP, custom_elasticity=6.0)
    assert hi.by_id("B").metrics["cash_day_90"] < lo.by_id("B").metrics["cash_day_90"]
    assert hi.ranking().index("A") < hi.ranking().index("B"), (
        "at an elasticity of 6 a price rise should be worse than holding prices")


def test_shop_zero_low_margin_share_removes_world_c_advantage():
    comp = run_comparison(SHOP_WEDGE, DEMO_SHOP.replace(low_margin_share_pct=0.0))
    c = comp.by_id("C")
    assert c.spec.cogs_reduction_points == 0.0
    # With nothing to trim, C is just a smaller price rise — no cost saving, no lost orders.
    assert c.sim.series("demand")[90] == pytest.approx(100.0 - 1.3 * 4.0, abs=0.35)


def test_shop_a_bigger_shock_never_helps_the_do_nothing_world():
    nets = [run_comparison(SHOP_WEDGE, DEMO_SHOP.replace(supplier_increase_pct=s)).by_id("A").metrics["monthly_net"]
            for s in (10.0, 25.0, 40.0)]
    assert nets[0] > nets[1] > nets[2]


def test_shop_price_rises_never_raise_orders():
    for setting in ("low", "central", "high"):
        comp = run_comparison(SHOP_WEDGE, DEMO_SHOP, axis_settings={"price_sensitivity": setting})
        assert comp.by_id("B").metrics["orders_change_pct"] < 0
        assert comp.by_id("C").metrics["orders_change_pct"] < 0


# ---- salon -----------------------------------------------------------------------------------

def test_salon_a_price_rise_reduces_appointments_wanted():
    """The regression guard for the structural bug: the elasticity must actually bite."""
    comp = run_comparison(SALON_WEDGE, DEMO_SALON)
    wanted_a = comp.by_id("A").sim.series("appointment_demand")[90]
    wanted_b = comp.by_id("B").sim.series("appointment_demand")[90]
    assert wanted_b < wanted_a - 1.0, "raising prices must reduce appointments wanted"


def test_salon_zero_elasticity_loses_no_appointments():
    comp = run_comparison(SALON_WEDGE, DEMO_SALON, custom_elasticity=0.0)
    a_wanted = comp.by_id("A").sim.series("appointment_demand")[90]
    b_wanted = comp.by_id("B").sim.series("appointment_demand")[90]
    assert b_wanted == pytest.approx(a_wanted, abs=1e-6)


def test_salon_extreme_elasticity_reverses_the_pricing_decision():
    """If clients really are that price-sensitive, protecting the diary stops paying."""
    lo = run_comparison(SALON_WEDGE, DEMO_SALON, custom_elasticity=0.2)
    hi = run_comparison(SALON_WEDGE, DEMO_SALON, custom_elasticity=8.0)
    assert hi.by_id("B").metrics["cash_day_90"] < lo.by_id("B").metrics["cash_day_90"]
    assert hi.ranking().index("A") < hi.ranking().index("B"), (
        "at an extreme elasticity, keeping prices should beat raising them")


def test_salon_spare_capacity_changes_what_serving_more_is_worth():
    """
    With a half-empty diary the extra demand can all be served, so holding prices captures it.
    With a full diary it cannot, so the same decision is worth less. The gap between A and B
    must therefore be larger when the diary is full.
    """
    empty = run_comparison(SALON_WEDGE, DEMO_SALON.replace(utilisation_pct=50.0))
    full = run_comparison(SALON_WEDGE, DEMO_SALON.replace(utilisation_pct=99.0))
    gap_empty = empty.by_id("B").metrics["cash_day_90"] - empty.by_id("A").metrics["cash_day_90"]
    gap_full = full.by_id("B").metrics["cash_day_90"] - full.by_id("A").metrics["cash_day_90"]
    assert gap_full > gap_empty, (
        "a full diary should make raising prices relatively more attractive, not less")


def test_salon_higher_utilisation_turns_more_people_away_under_do_nothing():
    away = [run_comparison(SALON_WEDGE, DEMO_SALON.replace(utilisation_pct=u)).by_id("A")
            .metrics["turned_away_per_day_end"] for u in (60.0, 80.0, 95.0)]
    assert away[0] <= away[1] <= away[2]
    assert away[2] > 0, "a nearly full diary plus more demand must turn someone away"


def test_salon_zero_mix_effect_removes_world_c_mix_advantage():
    comp = run_comparison(SALON_WEDGE, DEMO_SALON.replace(low_margin_share_pct=0.0))
    c = comp.by_id("C")
    assert c.spec.cogs_reduction_points == 0.0
    assert c.sim.series("cost_per_appointment")[90] == pytest.approx(100.0, abs=0.3)


def test_salon_capacity_never_lets_more_be_served_than_exists():
    for u in (40.0, 70.0, 100.0):
        comp = run_comparison(SALON_WEDGE, DEMO_SALON.replace(utilisation_pct=u))
        cap = DEMO_SALON.replace(utilisation_pct=u).capacity_per_day
        for w in comp.worlds:
            assert max(w.ledger.orders) <= cap + 1e-9, f"{w.spec.id} served more than {cap} slots"
            assert min(w.ledger.turned_away) >= 0.0


def test_salon_serving_more_never_costs_more_than_it_earns_at_this_margin():
    """Sanity on the cost side: appointments are high-margin, so more of them cannot hurt."""
    comp = run_comparison(SALON_WEDGE, DEMO_SALON.replace(utilisation_pct=50.0))
    a = comp.by_id("A")
    assert a.metrics["monthly_net"] > DEMO_SALON.monthly_net, (
        "with spare capacity, extra demand served at an 88% margin must increase net")
