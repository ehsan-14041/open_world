"""
Where every number in the shop comparison comes from.

The honest position on elasticity for a retailer: the two meta-analyses this wedge cites both
measure BRAND-level switching — a customer picking a different tin off the same shelf. What a
shop actually does when it raises prices is invite the customer to shop somewhere else, which
is harder. So the literature bounds the range from above, and only the HIGH setting is classed
as research; central and low are our judgement and say so. No store-level meta-analysis with a
usable published mean was found, and a brand-level figure was not stretched to cover the gap.

Declarative, because the PHP host renders the same rows from this same spec.
"""

from __future__ import annotations

from event_sim.wedge.evidence import (
    ASSUMPTION,
    CUSTOMER,
    DERIVED,
    Assumption,
    render_registry,
)
from event_sim.wedge.evidence import BIJMOLT_2005, TELLIS_1988

from event_sim.shop.baseline import ShopBaseline
from event_sim.shop.worlds import (
    PRICE_RISE_B,
    PRICE_RISE_C,
    TRIM_DEMAND_COST_RATIO,
    TRIM_EFFECTIVENESS,
    cogs_reduction_points,
)

SOURCES: list[dict[str, str]] = [BIJMOLT_2005, TELLIS_1988]

#: Only the high setting is a published figure — the brand-level meta-analytic mean.
RESEARCH_SETTINGS = ["high"]

REGISTRY_SPEC: list[dict] = [
    {"key": "monthly_revenue", "label": "Current monthly sales", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_revenue"}},
    {"key": "daily_orders", "label": "Orders per day", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "daily_orders"}},
    {"key": "monthly_cogs", "label": "Monthly cost of goods", "klass": CUSTOMER,
     "value": {"kind": "money_with_pct", "field": "monthly_cogs", "pct_of": "cogs_pct"}},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs (incl. wages)", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_fixed_costs"},
     "note": "Treated as unchanged over 90 days."},
    {"key": "cash_on_hand", "label": "Cash available today", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "cash_on_hand"}},
    {"key": "supplier_increase_pct", "label": "Supplier cost increase", "klass": CUSTOMER, "swept": True,
     "value": {"kind": "g", "field": "supplier_increase_pct", "prefix": "+", "suffix": "%"},
     "note": "Tested at 15%, 25% and 35%."},
    {"key": "low_margin_share_pct", "label": "Share of orders on low-margin lines", "klass": CUSTOMER,
     "value": {"kind": "g", "field": "low_margin_share_pct", "suffix": "%"}},
    {"key": "price_sensitivity", "label": "Price sensitivity of customers", "klass": ASSUMPTION,
     "swept": True, "elasticity": True,
     "value": {"kind": "axis", "axis": "price_sensitivity",
               "map": {"low": "0.70", "central": "1.30", "high": "2.60"}},
     "source": "bijmolt2005 (brand-level mean); tellis1988 (second reference point)",
     "assumption_source": "No study supports this setting. bijmolt2005 and tellis1988 measure brand "
                          "switching inside a shop and set the top of the range, not its middle.",
     "note": "A 1% price rise eventually reduces orders by this percentage. Low 0.70 / central 1.30 / "
             "high 2.60. Only the high setting is a published figure — the brand-level meta-analytic "
             "mean, i.e. customers who can buy the identical item elsewhere. The central and low "
             "settings are our judgement, set below brand level because changing shop is harder than "
             "changing brand. This is the assumption most likely to change the decision."},
    {"key": "cogs_pass_through", "label": "Share of supplier increase reaching your cost of goods",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "axis", "axis": "cogs_pass_through",
               "map": {"low": "70%", "central": "100%", "high": "100%"}},
     "note": "100% by definition unless you can substitute cheaper lines, renegotiate, or hold "
             "fixed-price contracts (tested at 70%)."},
    {"key": "inventory_lag", "label": "Delay before higher supplier prices reach your costs",
     "klass": ASSUMPTION,
     "value": {"kind": "literal", "text": "about 20 days (stock on hand)"},
     "note": "Stock already on the shelf was bought at the old price. Tested over a 10-30 day range; "
             "the comparison uses the midpoint. A shop holding more stock than that sees the increase "
             "later than this shows."},
    {"key": "demand_adjustment_speed", "label": "How quickly customers react to a price change",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "axis", "axis": "demand_adjustment_speed",
               "map": {"slow": "about two and a half weeks to half-react",
                       "central": "about eight days to half-react",
                       "fast": "about four days to half-react"}}},
    {"key": "trim_effectiveness", "label": "Cost saving from dropping low-margin lines",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "template",
               "text": "{reduction:g} points off average cost of goods "
                       "({trim_effectiveness:.3f} per point of low-margin share)"},
     "note": "Assumes low-margin lines carry roughly 2.9x the average cost share, which is close to "
             "what makes them low-margin. Tested at half and one-and-a-half times this rate."},
    {"key": "trim_demand_cost", "label": "Orders lost from dropping those lines", "klass": ASSUMPTION,
     "value": {"kind": "template", "text": "{demand_cost:.1f}% of orders"},
     "note": f"{TRIM_DEMAND_COST_RATIO:g} of the cost saving, in points of orders: customers who came "
             f"for the removed lines and do not substitute. Higher than the cafe's ratio because a "
             f"shopper who cannot find a specific product is more likely to leave."},
    {"key": "price_rises", "label": "Price rises compared", "klass": CUSTOMER,
     "value": {"kind": "literal", "text": f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%"},
     "note": "The decisions being compared; fixed by the question."},
    {"key": "horizon", "label": "Comparison horizon", "klass": ASSUMPTION,
     "value": {"kind": "literal", "text": "90 days"},
     "note": "Long enough for the stock to turn over at the new cost and for most of the customer "
             "reaction to land; short enough that rent and wages can be treated as fixed."},
    {"key": "average_order_value", "label": "Average order value", "klass": DERIVED,
     "value": {"kind": "money", "field": "average_order_value", "dp": 2},
     "note": "Monthly sales divided by monthly orders."},
    {"key": "cogs_per_order", "label": "Cost of goods per order", "klass": DERIVED,
     "value": {"kind": "money", "field": "cogs_per_order", "dp": 2}},
]


def registry(
    baseline: ShopBaseline,
    *,
    axis_settings: dict[str, str],
    trim_effectiveness: float = TRIM_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    reduction = cogs_reduction_points(baseline, trim_effectiveness)
    return render_registry(
        REGISTRY_SPEC, baseline,
        axis_settings=axis_settings,
        knobs={"trim_effectiveness": trim_effectiveness},
        extra={
            "cogs_pct": baseline.cogs_pct,
            "reduction": reduction,
            "demand_cost": TRIM_DEMAND_COST_RATIO * reduction,
            "average_order_value": baseline.average_order_value,
            "cogs_per_order": baseline.cogs_per_order,
        },
        custom_elasticity=custom_elasticity,
        research_settings=RESEARCH_SETTINGS,
    )
