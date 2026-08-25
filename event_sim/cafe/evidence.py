"""
Where every number in the cafe comparison comes from.

Written as a declarative spec rather than as code, because the PHP host renders the same rows
from the same spec. Writing the prose twice, once per language, would guarantee that the two
drifted; this way there is one source and a test that compares the two renderings.
"""

from __future__ import annotations

from event_sim.wedge.evidence import (  # noqa: F401  (re-exported for existing importers)
    ASSUMPTION,
    CUSTOMER,
    DERIVED,
    LADDER,
    RESEARCH,
    Assumption,
    class_counts,
    render_registry,
)
from event_sim.wedge.evidence import ANDREYEVA_2010, BIJMOLT_2005

from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.worlds import (
    PRICE_RISE_B,
    PRICE_RISE_C,
    REFORMULATION_EFFECTIVENESS,
    cogs_reduction_points,
)

SOURCES: list[dict[str, str]] = [ANDREYEVA_2010, BIJMOLT_2005]

#: Settings at which the elasticity is genuinely backed by a published study.
RESEARCH_SETTINGS = ["central"]

REGISTRY_SPEC: list[dict] = [
    {"key": "monthly_revenue", "label": "Current monthly sales", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_revenue"}},
    {"key": "daily_orders", "label": "Orders per day", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "daily_orders"}},
    {"key": "monthly_cogs", "label": "Monthly ingredient cost", "klass": CUSTOMER,
     "value": {"kind": "money_with_pct", "field": "monthly_cogs", "pct_of": "cogs_pct"}},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs (incl. wages)", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_fixed_costs"},
     "note": "Treated as unchanged over 90 days."},
    {"key": "cash_on_hand", "label": "Cash available today", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "cash_on_hand"}},
    {"key": "supplier_increase_pct", "label": "Supplier cost increase", "klass": CUSTOMER, "swept": True,
     "value": {"kind": "g", "field": "supplier_increase_pct", "prefix": "+", "suffix": "%"},
     "note": "Tested at 20%, 30% and 40%."},
    {"key": "low_margin_share_pct", "label": "Share of orders on low-margin items", "klass": CUSTOMER,
     "value": {"kind": "g", "field": "low_margin_share_pct", "suffix": "%"}},
    {"key": "price_sensitivity", "label": "Price sensitivity of customers", "klass": ASSUMPTION,
     "swept": True, "elasticity": True,
     "value": {"kind": "axis", "axis": "price_sensitivity",
               "map": {"low": "0.50", "central": "0.81", "high": "1.60"}},
     "source": "andreyeva2010; bijmolt2005 (upper reference)",
     "assumption_source": "No study supports this setting. andreyeva2010 backs the central value; "
                          "bijmolt2005 is the upper reference the high setting was placed against.",
     "note": "A 1% price rise eventually reduces orders by this percentage. Low 0.50 / central 0.81 / "
             "high 1.60. This is the assumption most likely to change the decision."},
    {"key": "cogs_pass_through", "label": "Share of supplier increase reaching your costs",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "axis", "axis": "cogs_pass_through",
               "map": {"low": "70%", "central": "100%", "high": "100%"}},
     "note": "100% by definition unless you can substitute, renegotiate or have fixed-price "
             "contracts (tested at 70%)."},
    {"key": "cogs_lag", "label": "Delay before higher prices reach your costs", "klass": ASSUMPTION,
     "value": {"kind": "literal", "text": "about 7 days (stock on hand)"},
     "note": "Fresh inventory turns over in roughly a week; costs then rise over a few more days."},
    {"key": "demand_adjustment_speed", "label": "How quickly customers react to a price change",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "axis", "axis": "demand_adjustment_speed",
               "map": {"slow": "about a month to half-react",
                       "central": "about two weeks to half-react",
                       "fast": "about a week to half-react"}}},
    {"key": "reformulation_effectiveness", "label": "Ingredient-cost saving from trimming the menu",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "template",
               "text": "{reduction:g} points off average ingredient cost "
                       "({reformulation_effectiveness:.2f} per point of low-margin share)"},
     "note": "Tested at half and one-and-a-half times this rate."},
    {"key": "reformulation_demand_cost", "label": "Orders lost from removing items", "klass": ASSUMPTION,
     "value": {"kind": "template", "text": "{demand_cost:.1f}% of orders"},
     "note": "One third of the ingredient-cost saving, in points of orders: customers who came for "
             "the removed items."},
    {"key": "price_rises", "label": "Price rises compared", "klass": CUSTOMER,
     "value": {"kind": "literal", "text": f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%"},
     "note": "The decisions being compared; fixed by the question."},
    {"key": "horizon", "label": "Comparison horizon", "klass": ASSUMPTION,
     "value": {"kind": "literal", "text": "90 days"},
     "note": "Long enough for costs and most of the customer reaction to land; short enough that "
             "wages and rent can be treated as fixed. Slow customer reactions are not fully visible "
             "within it."},
    {"key": "average_order_value", "label": "Average order value", "klass": DERIVED,
     "value": {"kind": "money", "field": "average_order_value", "dp": 2},
     "note": "Monthly sales divided by monthly orders."},
    {"key": "cogs_per_order", "label": "Ingredient cost per order", "klass": DERIVED,
     "value": {"kind": "money", "field": "cogs_per_order", "dp": 2}},
]


def registry(
    baseline: CafeBaseline,
    *,
    axis_settings: dict[str, str],
    reformulation_effectiveness: float = REFORMULATION_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    reduction = cogs_reduction_points(baseline, reformulation_effectiveness)
    return render_registry(
        REGISTRY_SPEC, baseline,
        axis_settings=axis_settings,
        knobs={"reformulation_effectiveness": reformulation_effectiveness},
        extra={
            "cogs_pct": baseline.cogs_pct,
            "reduction": reduction,
            "demand_cost": 0.33 * reduction,
            "average_order_value": baseline.average_order_value,
            "cogs_per_order": baseline.cogs_per_order,
        },
        custom_elasticity=custom_elasticity,
        research_settings=RESEARCH_SETTINGS,
    )
