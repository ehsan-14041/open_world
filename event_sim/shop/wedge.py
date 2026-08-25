"""
The shop wedge.

Same instrument as the cafe, pointed at a retailer: one shock, three decisions, one model.
What differs is what the evidence supports — a shop's customers can more often buy the
identical item elsewhere, so the elasticity range sits higher — and how long stock sits on the
shelf before the supplier increase reaches the books.
"""

from __future__ import annotations

from typing import Any

from event_sim.shop.baseline import DEMO_SHOP, INTAKE_FIELDS, ShopBaseline
from event_sim.shop.evidence import SOURCES, registry
from event_sim.shop.worlds import (
    HORIZON_DAYS,
    MODULE_ID,
    PRICE_RISE_B,
    PRICE_RISE_C,
    TRIM_DEMAND_COST_RATIO,
    TRIM_EFFECTIVENESS,
    build_worlds,
    cogs_reduction_points,
)
from event_sim.wedge.spec import WedgeSpec

DEFAULT_AXES: dict[str, str] = {
    "price_sensitivity": "central",
    "cogs_pass_through": "central",
    "demand_adjustment_speed": "central",
}

SWEEP: dict[str, list[Any]] = {
    "price_sensitivity": ["low", "central", "high"],
    "cogs_pass_through": ["low", "central"],
    "supplier_increase_pct": [15.0, 25.0, 35.0],
    "trim_effectiveness": [0.1875, 0.375, 0.5625],
    "demand_adjustment_speed": ["slow", "central", "fast"],
}

SWEEP_LABELS: dict[str, str] = {
    "price_sensitivity": "How price-sensitive customers are",
    "cogs_pass_through": "How much of the supplier increase reaches your costs",
    "supplier_increase_pct": "How large the supplier increase actually is",
    "trim_effectiveness": "How much dropping low-margin lines really saves",
    "demand_adjustment_speed": "How quickly customers react",
}


def _grid_key(baseline: ShopBaseline, settings: dict[str, Any], _comparison: Any) -> dict[str, Any]:
    return {
        "price_sensitivity": settings["price_sensitivity"],
        "cogs_pass_through": settings["cogs_pass_through"],
        "supplier_increase_pct": float(settings["supplier_increase_pct"]),
        "reduction_points": cogs_reduction_points(baseline, float(settings["trim_effectiveness"])),
        "demand_adjustment_speed": settings["demand_adjustment_speed"],
    }


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
    "demo_noun": "shop",
    "page_title": "Shop cost decision — three options compared",
    "research_settings": ["high"],
    "world_verdict_labels": {
        "A": "Holding prices",
        "B": f"Raising prices {PRICE_RISE_B:g}%",
        "C": f"A {PRICE_RISE_C:g}% rise plus dropping low-margin lines",
    },
    "world_names": {
        "A": "Hold prices",
        "B": f"Raise prices {PRICE_RISE_B:g}%",
        "C": f"Raise prices {PRICE_RISE_C:g}% + drop low-margin lines",
    },
    "world_short": {"A": "Hold prices", "B": f"Raise {PRICE_RISE_B:g}%",
                    "C": f"Raise {PRICE_RISE_C:g}% + drop lines"},
    "headline": "Your supplier put prices up {shock}%. Should you pass it on?",
    "hero_lede": "We compared three decisions using the same model of your shop and the same "
                 "assumptions. Only the decision changes between them — so the differences come "
                 "from the decision, not from different guesses.",
    "unit_word": "orders",
    "unit_word_singular": "order",
    "cost_word": "cost of goods",
    "uncertainty_title": "How price-sensitive are your customers?",
    "uncertainty_eyebrow": "The biggest uncertainty",
    "sens_help": {
        "low": "Loyal customers, an awkward shop to replace, or competitors raising prices too.",
        "central": "Our judgement: customers who could shop elsewhere, with some effort.",
        "high": "Research figure for customers who can buy the identical item elsewhere.",
    },
    "sens_values": {"low": "0.70", "central": "1.30", "high": "2.60"},
    "c_card_note": "Depends on two of our assumptions: how much dropping low-margin lines cuts "
                   "your {cost} (about {red} points here) and how many {unit} leave with those "
                   "lines ({loss}%). Neither is calibrated to your business yet.",
    "chart_title": "Cash in the bank under each decision",
    "chart_lede": "Costs take about three weeks to rise — the stock on your shelves was bought at "
                  "the old price. Customers react to a new price within a week or two.",
    "next_measurement": "A two-week price test on a handful of lines — or your own sales figures "
                        "from the last time you put prices up — would tell you far more about how "
                        "your customers respond than any assumption we can make. That evidence can "
                        "replace the estimate used here.",
    "sources_note": "On price sensitivity: the research quoted measures customers switching "
                    "between brands on the same shelf, which is easier than switching shops. It "
                    "sets the top of the range rather than the middle, and the middle is our "
                    "judgement, not a research finding.",
    "limits_does_not": [
        "Predict the future or guarantee an outcome.",
        "Model how competitors or marketplaces react.",
        "Model advertising, search ranking or promotions.",
        "Know your customers' price sensitivity — unless you bring evidence.",
    ],
    "intake_groups": [
        {"label": "Your business", "fields": ["monthly_revenue", "daily_orders", "cash_on_hand"]},
        {"label": "Your costs", "fields": ["monthly_cogs", "monthly_fixed_costs"]},
        {"label": "The shock", "fields": ["supplier_increase_pct"]},
        {"label": "Your range", "fields": ["low_margin_share_pct", "name"]},
    ],
}

SHOP_WEDGE = WedgeSpec(
    id="shop",
    business="Shop / Online Store",
    question="My supplier raised prices. Should I pass it on?",
    module_id=MODULE_ID,
    horizon_days=HORIZON_DAYS,
    default_axes=DEFAULT_AXES,
    demand_var="demand",
    price_var="retail_price",
    unit_cost_var="unit_cost",
    index_vars=("supplier_cost", "unit_cost", "retail_price", "demand"),
    elasticity_edge="retail_price->demand",
    slice_question="Supplier costs rose. Which response?",
    build_worlds=build_worlds,
    build_registry=registry,
    sweep=SWEEP,
    sweep_labels=SWEEP_LABELS,
    sources=SOURCES,
    intake_fields=INTAKE_FIELDS,
    demo_factory=lambda: DEMO_SHOP,
    baseline_from_dict=ShopBaseline.from_dict,
    knob_defaults={"trim_effectiveness": TRIM_EFFECTIVENESS},
    capacity_per_day=None,
    copy=COPY,
)
