"""
The cafe wedge, assembled from the shared machinery.

This file changes no arithmetic. The module, the coefficients, the horizon, the sweep, the
three decisions and the evidence registry are exactly what they were when the wedge was
audited; what has moved is the code that runs them, which is now shared with the shop and the
salon so that all three are demonstrably the same instrument pointed at different businesses.

A regression test asserts the central results and all three engine fingerprints are unchanged.
"""

from __future__ import annotations

from typing import Any

from event_sim.cafe.baseline import DEMO_CAFE, INTAKE_FIELDS, CafeBaseline
from event_sim.cafe.evidence import registry
from event_sim.cafe.worlds import (
    HORIZON_DAYS,
    MODULE_ID,
    PRICE_RISE_B,
    PRICE_RISE_C,
    REFORMULATION_EFFECTIVENESS,
    build_worlds,
    cogs_reduction_points,
)
from event_sim.wedge.evidence import ANDREYEVA_2010, BIJMOLT_2005
from event_sim.wedge.spec import WedgeSpec, _key_from_fields

DEFAULT_AXES: dict[str, str] = {
    "price_sensitivity": "central",
    "cogs_pass_through": "central",
    "demand_adjustment_speed": "central",
}

SWEEP: dict[str, list[Any]] = {
    "price_sensitivity": ["low", "central", "high"],
    "cogs_pass_through": ["low", "central"],
    "supplier_increase_pct": [20.0, 30.0, 40.0],
    "reformulation_effectiveness": [0.15, 0.30, 0.45],
    "demand_adjustment_speed": ["slow", "central", "fast"],
}

SWEEP_LABELS: dict[str, str] = {
    "price_sensitivity": "How price-sensitive customers are",
    "cogs_pass_through": "How much of the supplier increase reaches your costs",
    "supplier_increase_pct": "How large the supplier increase actually is",
    "reformulation_effectiveness": "How much trimming the menu really saves",
    "demand_adjustment_speed": "How quickly customers react",
}


def _grid_key(baseline, settings: dict[str, Any], _comparison: Any) -> dict[str, Any]:
    return _key_from_fields(COPY["grid_key_fields"], cogs_reduction_points(baseline, float(settings["reformulation_effectiveness"])), settings)


COPY: dict[str, Any] = {
    "grid_key": _grid_key,
    "fields": {
        "units_per_day": "daily_orders",
        "unit_cost_total": "monthly_cogs",
        "revenue": "monthly_revenue",
        "fixed": "monthly_fixed_costs",
        "cash": "cash_on_hand",
        "shock": "supplier_increase_pct",
        "low_margin": "low_margin_share_pct",
    },
    "primary_axis": "price_sensitivity",
    "summary_fields": [
        ["monthly_revenue", "monthly_revenue", 2], ["daily_orders", "daily_orders", 1],
        ["average_order_value", "average_ticket", 2], ["monthly_cogs", "unit_cost_total", 2],
        ["cogs_pct", "cost_pct", 1], ["gross_margin_pct", "gross_margin_pct", 1],
        ["monthly_fixed_costs", "fixed", 2], ["monthly_net", "monthly_net", 2],
        ["net_margin_pct", "net_margin_pct", 1], ["cash_on_hand", "cash", 2],
        ["supplier_increase_pct", "supplier_increase_pct", None],
        ["low_margin_share_pct", "low_margin_share_pct", None],
    ],
    "grid_key_fields": {
        "price_sensitivity": "price_sensitivity",
        "cogs_pass_through": "cogs_pass_through",
        "supplier_increase_pct": {"float": "supplier_increase_pct"},
        "reduction_points": "reduction",
        "demand_adjustment_speed": "demand_adjustment_speed",
    },
    "demo_noun": "cafe",
    "page_title": "Cafe cost decision — three options compared",
    "research_settings": ["central"],
    "world_verdict_labels": {
        "A": "Doing nothing",
        "B": "Raising prices 10%",
        "C": "A 5% rise plus trimming the menu",
    },
    "world_names": {
        "A": "Hold prices",
        "B": "Raise prices 10%",
        "C": "Raise prices 5% + simplify low-margin items",
    },
    "world_short": {"A": "Hold prices", "B": "Raise 10%", "C": "Raise 5% + simplify"},
    "headline": "Ingredient costs are up {shock}%. What should you do?",
    "hero_lede": "We compared three decisions using the same model of your cafe and the same "
                 "assumptions. Only the decision changes between them — so the differences come "
                 "from the decision, not from different guesses.",
    "unit_word": "orders",
    "unit_word_singular": "order",
    "cost_word": "ingredient cost",
    "uncertainty_title": "How price-sensitive are your customers?",
    "uncertainty_eyebrow": "The biggest uncertainty",
    "sens_help": {
        "low": "Loyal customers, or your competitors are raising prices too.",
        "central": "The typical response found in research on eating out.",
        "high": "Stress case: competitors hold their prices and customers have easy alternatives.",
    },
    "sens_values": {"low": "0.50", "central": "0.81", "high": "1.60"},
    "c_card_note": "Depends on two of our assumptions: how much simplifying the menu cuts "
                   "ingredient cost (about {red} points here) and how many {unit} leave with the "
                   "removed items ({loss}%). Neither is calibrated to your business yet.",
    "chart_title": "Cash in the bank under each decision",
    "chart_lede": "Costs take about a week to rise — you are still using stock bought at the old "
                  "price. Customers take a couple of weeks to react to a new price.",
    "next_measurement": "A small real-world price test — a few items, a few weeks — or your sales "
                        "figures from the last time you changed prices would give much better "
                        "evidence about how your customers respond. That evidence can replace the "
                        "research estimate in this comparison.",
    "sources_note": "On price sensitivity: external research gives a reference range for eating "
                    "out as a whole. Your actual customers may be more or less price-sensitive "
                    "than that, and the High setting is a stress assumption rather than a "
                    "research finding.",
    "limits_does_not": [
        "Predict the future or guarantee an outcome.",
        "Model how competitors react.",
        "Model the wider economy, seasons or new customers.",
        "Know your customers' price sensitivity — unless you bring evidence.",
    ],
    "intake_groups": [
        {"label": "Your business", "fields": ["monthly_revenue", "daily_orders", "cash_on_hand"]},
        {"label": "Your costs", "fields": ["monthly_cogs", "monthly_fixed_costs"]},
        {"label": "The shock", "fields": ["supplier_increase_pct"]},
        {"label": "Your menu", "fields": ["low_margin_share_pct", "name"]},
    ],
}

CAFE_WEDGE = WedgeSpec(
    id="cafe",
    business="Cafe / Restaurant",
    question="Ingredient costs jumped. What should I change?",
    module_id=MODULE_ID,
    horizon_days=HORIZON_DAYS,
    default_axes=DEFAULT_AXES,
    demand_var="demand",
    price_var="menu_price",
    unit_cost_var="cogs_per_order",
    index_vars=("input_cost", "cogs_per_order", "menu_price", "demand"),
    elasticity_edge="menu_price->demand",
    slice_question="Ingredient costs rose. Which response?",
    build_worlds=build_worlds,
    build_registry=registry,
    sweep=SWEEP,
    sweep_labels=SWEEP_LABELS,
    sources=[ANDREYEVA_2010, BIJMOLT_2005],
    intake_fields=INTAKE_FIELDS,
    demo_factory=lambda: DEMO_CAFE,
    baseline_from_dict=CafeBaseline.from_dict,
    knob_defaults={"reformulation_effectiveness": REFORMULATION_EFFECTIVENESS},
    capacity_per_day=None,
    copy=COPY,
)
