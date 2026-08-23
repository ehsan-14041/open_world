"""
Tests for the cafe cost-shock wedge.

The claims worth defending:

  * the three worlds share one model, one config and one baseline — only decisions differ;
  * the module behaves as its audit says (lags, elasticity, reformulation, no double count);
  * money is an identity over engine output, never an engine variable;
  * the customer copy never promises a forecast;
  * a real cafe replaces the demo without touching the module on disk.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from event_sim.cafe import accounting, evidence, worlds
from event_sim.cafe.baseline import DEMO_CAFE, INTAKE_FIELDS, CafeBaseline
from event_sim.cafe.run import run_comparison
from event_sim.registry import get_module

REPO = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO / "world_models" / "small_business" / "cafe_cost_shock_v1.json"
TEMPLATE = REPO / "event_sim" / "cafe" / "templates" / "decision_report.html"


@pytest.fixture(scope="module")
def comp():
    return run_comparison(DEMO_CAFE)


# --- invariance: the product property -------------------------------------------------------

def test_three_worlds_share_one_configuration(comp):
    fps = {w.fingerprint for w in comp.worlds}
    assert len(fps) == 3, "worlds must differ in outcome"
    assert comp.shared_fingerprint, "and share one configuration fingerprint"


def test_only_interventions_differ_between_worlds(comp):
    a, b, c = (w.spec for w in comp.worlds)
    assert a.events[0].to_dict() == b.events[0].to_dict() == c.events[0].to_dict()
    assert a.interventions == []
    assert [i.id for i in b.interventions] == ["raise_prices"]
    assert [i.id for i in c.interventions] == ["raise_prices", "reformulate_menu"]


def test_same_slice_object_feeds_all_three(comp):
    assert len({id(w.sim.slice) for w in comp.worlds}) == 1


# --- module audit: it does what it says ----------------------------------------------------

def test_cost_shock_holds_input_cost_for_the_whole_horizon(comp):
    s = comp.by_id("A").sim.series("input_cost")
    assert s[0] == 100.0 and all(abs(v - 130.0) < 1e-9 for v in s[1:])


def test_cogs_lags_behind_input_cost_by_about_a_week(comp):
    s = comp.by_id("A").sim.series("cogs_per_order")
    assert s[5] == pytest.approx(100.0), "old stock still being used"
    assert s[14] > 120.0 and s[30] == pytest.approx(130.0, abs=0.3)


def test_price_rise_moves_demand_by_the_elasticity(comp):
    d = comp.by_id("B").sim.series("demand")
    assert d[90] == pytest.approx(100.0 - 0.81 * 10.0, abs=0.1)


def test_demand_adjusts_gradually_not_instantly(comp):
    d = comp.by_id("B").sim.series("demand")
    assert d[1] > 99.0 and d[7] > d[14] > d[28] > d[90] - 0.5


def test_reformulation_lowers_cogs_and_costs_some_orders(comp):
    c = comp.by_id("C").sim
    assert c.series("cogs_per_order")[90] == pytest.approx(130.0 - 6.0, abs=0.3)
    expected_demand = 100.0 - 0.81 * 5.0 - 0.33 * 6.0
    assert c.series("demand")[90] == pytest.approx(expected_demand, abs=0.2)


def test_menu_price_has_no_incoming_edges_so_it_is_a_decision_not_an_outcome():
    m = get_module("cafe_cost_shock_v1")
    assert not [e for e in m.edges if e.target == "menu_price"]


def test_no_accounting_identity_is_modelled_as_an_edge():
    m = get_module("cafe_cost_shock_v1")
    ids = {v.id for v in m.variables}
    for forbidden in ("revenue", "margin", "gross_profit", "cash", "profit"):
        assert not any(forbidden in v for v in ids), f"{forbidden} must be an identity, not a state"


def test_no_stock_variables_in_the_module():
    m = get_module("cafe_cost_shock_v1")
    assert all(v.kind == "relaxation" for v in m.variables)


# --- accounting: identities over engine output -------------------------------------------

def test_gross_profit_is_revenue_minus_cogs_every_day(comp):
    led = comp.by_id("B").ledger
    for d in range(len(led.days)):
        assert led.gross_profit[d] == pytest.approx(led.revenue[d] - led.cogs[d])


def test_cash_is_yesterday_plus_net_every_day(comp):
    led = comp.by_id("C").ledger
    for d in range(1, len(led.days)):
        assert led.cash[d] == pytest.approx(led.cash[d - 1] + led.net[d])


def test_day_zero_reproduces_the_baseline_exactly(comp):
    led = comp.by_id("A").ledger
    assert led.orders[0] == pytest.approx(DEMO_CAFE.daily_orders)
    assert led.price[0] == pytest.approx(DEMO_CAFE.average_order_value)
    assert led.cash[0] == DEMO_CAFE.cash_on_hand


def test_cash_may_go_negative_for_a_tight_cafe():
    tight = replace(DEMO_CAFE, cash_on_hand=2_000.0, monthly_fixed_costs=34_000.0, is_demo=True)
    c = run_comparison(tight)
    m = c.by_id("A").metrics
    assert m["cash_goes_negative"] and m["first_negative_day"] is not None


def test_runway_none_when_cash_flow_positive(comp):
    assert comp.by_id("B").metrics["runway_months_at_end"] is None
    assert comp.by_id("A").metrics["runway_months_at_end"] is not None


# --- sensitivity direction (cheap, no full sweep) ----------------------------------------

def test_high_price_sensitivity_favours_the_menu_trim_over_the_bigger_price_rise():
    hi = run_comparison(DEMO_CAFE, axis_settings={"price_sensitivity": "high"})
    assert hi.ranking()[0] == "C"
    assert run_comparison(DEMO_CAFE).ranking()[0] == "B"


def test_doing_nothing_never_wins_at_central_assumptions(comp):
    assert comp.ranking()[-1] == "A"


# --- evidence and language -------------------------------------------------------------------

def test_every_assumption_is_classified_and_elasticity_is_cited(comp):
    reg = evidence.registry(DEMO_CAFE, axis_settings=comp.axis_settings)
    assert all(a.klass in evidence.LADDER for a in reg)
    el = next(a for a in reg if a.key == "price_sensitivity")
    assert el.klass == evidence.RESEARCH and "andreyeva2010" in el.source


def test_high_elasticity_setting_is_labelled_assumption_not_research():
    reg = evidence.registry(DEMO_CAFE, axis_settings={"price_sensitivity": "high"})
    assert next(a for a in reg if a.key == "price_sensitivity").klass == evidence.ASSUMPTION


def test_literature_edge_carries_real_citations():
    m = get_module("cafe_cost_shock_v1")
    e = next(x for x in m.edges if x.id == "menu_price->demand")
    assert e.status == "literature_backed"
    refs = " ".join(ev.reference for ev in e.evidence)
    assert "Andreyeva" in refs and "Bijmolt" in refs


def test_customer_copy_never_promises_a_forecast():
    html = TEMPLATE.read_text(encoding="utf-8")
    customer_text = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    customer_text = re.sub(r"<style.*?</style>", "", customer_text, flags=re.S)
    for banned in ("will happen", "guaranteed", "optimal decision", "we predict", "forecast of"):
        assert banned not in customer_text.lower(), f"banned phrase in customer copy: {banned}"
    # The disclaimer is injected from the bundle so it cannot be edited out of the page alone.
    report_src = (REPO / "event_sim" / "cafe" / "report.py").read_text(encoding="utf-8")
    assert "not a forecast" in report_src
    assert 'id="scenario-note"' in html and 'id="snf"' in html


def test_customer_ui_avoids_engineering_vocabulary():
    html = TEMPLATE.read_text(encoding="utf-8")
    visible = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    for jargon in ("WorldModule", "causal edge", "JSON", "confidence interval"):
        assert jargon not in visible


# --- intake and replaceability ---------------------------------------------------------------

def test_intake_has_eight_fields():
    assert len(INTAKE_FIELDS) == 8


def test_real_cafe_replaces_demo_without_touching_the_module_on_disk():
    before = MODULE_PATH.read_bytes()
    real = CafeBaseline.from_dict({
        "name": "Test cafe", "monthly_revenue": 30_000, "daily_orders": 120, "monthly_cogs": 10_000,
        "monthly_fixed_costs": 18_000, "cash_on_hand": 9_000, "supplier_increase_pct": 25, "low_margin_share_pct": 15,
    })
    c = run_comparison(real)
    assert not c.baseline.is_demo and len(c.worlds) == 3
    assert MODULE_PATH.read_bytes() == before


def test_custom_elasticity_is_in_memory_only():
    before = MODULE_PATH.read_bytes()
    c = run_comparison(DEMO_CAFE, custom_elasticity=1.2)
    assert c.by_id("B").sim.series("demand")[90] == pytest.approx(100.0 - 12.0, abs=0.2)
    assert MODULE_PATH.read_bytes() == before
    assert get_module("cafe_cost_shock_v1").edges[1].effect.central == 0.81


def test_invalid_inputs_are_refused_in_plain_language():
    bad = replace(DEMO_CAFE, monthly_cogs=60_000.0)
    assert any("below revenue" in p for p in bad.validate())
    with pytest.raises(ValueError):
        run_comparison(bad)


def test_reproducibility_record_is_complete(comp):
    r = comp.reproducibility_record()
    assert r["module_semantic_hash"] and r["shared_fingerprint"]
    assert {w["spec"]["id"] for w in r["worlds"]} == {"A", "B", "C"}
    assert all(w["engine_fingerprint"] for w in r["worlds"])


# --- the scientific track is untouched ----------------------------------------------------

def test_port_disruption_models_unchanged_by_the_wedge():
    from event_sim.freeze import snapshot

    s = snapshot()
    assert s["modules"]["port_disruption"].startswith("d4670fb108c2e9a3")
    assert s["modules"]["port_disruption_h1_queue_experimental"].startswith("324a8bf1d67d56ad")


# --- audit wording: non-probabilistic, accounting disclosed, World C flagged ------------

def test_sensitivity_verdict_uses_counts_not_probability_language():
    from event_sim.cafe.sensitivity import SensitivityResult, SweepPoint
    from event_sim.cafe.sensitivity import SWEEP
    import itertools
    keys = list(SWEEP)
    pts = []
    for combo in itertools.product(*(SWEEP[k] for k in keys)):
        s = dict(zip(keys, combo))
        top = "C" if s["price_sensitivity"] == "high" else "B"
        pts.append(SweepPoint(settings=s, ranking=[top, "C" if top == "B" else "B", "A"], metric={"A": 0, "B": 1, "C": 2}))
    r = SensitivityResult(baseline=DEMO_CAFE, metric="cash_day_90", points=pts, central_ranking=["B", "C", "A"])
    v = r.verdict()
    assert "ranked first in 108 of the 162" in v
    assert "not a probability estimate" in v
    for banned in ("probability", "% of", "wins", "chance", "likely"):
        assert banned not in v.split("not a probability")[0]


def test_template_discloses_accounting_and_flags_world_c():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "Cash is not simulated directly" in html
    assert "not yet calibrated to your business" in html
    assert "stress assumption" in html
    assert "your actual customers may be more or less price-sensitive" in html
    assert "What this does not do" in html
    assert "Ranked first in" in html and "Best in" not in html
    assert "not a probability estimate" in html


def test_template_has_four_visible_number_categories():
    html = TEMPLATE.read_text(encoding="utf-8")
    for label in ("'Your numbers'", "'External research'", "'Model assumptions'", "'Calculated from your numbers'", "Calculated results"):
        assert label in html
