"""
Where every number in the shop comparison comes from.

The honest position on elasticity for a retailer: the two meta-analyses this wedge cites both
measure BRAND-level switching — a customer picking a different tin off the same shelf. What a
shop actually does when it raises prices is invite the customer to shop somewhere else, which
is harder. So the literature bounds the range from above, and the central value is our
judgement, labelled as one. No store-level meta-analysis with a usable published mean was
found; we did not stretch a brand-level figure to cover the gap.
"""

from __future__ import annotations

from event_sim.wedge.evidence import (
    ASSUMPTION,
    CUSTOMER,
    DERIVED,
    RESEARCH,
    Assumption,
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


def registry(
    baseline: ShopBaseline,
    *,
    axis_settings: dict[str, str],
    trim_effectiveness: float = TRIM_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    setting = axis_settings.get("price_sensitivity", "central")
    elasticity_value = {"low": "0.70", "central": "1.30", "high": "2.60"}[setting]
    # Only the HIGH setting is a published figure; the other two are our judgement.
    elasticity_class = RESEARCH if setting == "high" else ASSUMPTION
    if custom_elasticity is not None:
        elasticity_value, elasticity_class = f"{abs(custom_elasticity):.2f} (your value)", CUSTOMER

    pass_through = {"low": "70%", "central": "100%", "high": "100%"}[
        axis_settings.get("cogs_pass_through", "central")]
    speed = {"slow": "about two and a half weeks to half-react",
             "central": "about eight days to half-react",
             "fast": "about four days to half-react"}[
        axis_settings.get("demand_adjustment_speed", "central")]
    reduction = cogs_reduction_points(baseline, trim_effectiveness)

    return [
        Assumption("monthly_revenue", "Current monthly sales", f"{baseline.monthly_revenue:,.0f}", CUSTOMER, False),
        Assumption("daily_orders", "Orders per day", f"{baseline.daily_orders:,.0f}", CUSTOMER, False),
        Assumption("monthly_cogs", "Monthly cost of goods",
                   f"{baseline.monthly_cogs:,.0f} ({baseline.cogs_pct:.0f}% of sales)", CUSTOMER, False),
        Assumption("monthly_fixed_costs", "Monthly fixed costs (incl. wages)",
                   f"{baseline.monthly_fixed_costs:,.0f}", CUSTOMER, False,
                   note="Treated as unchanged over 90 days."),
        Assumption("cash_on_hand", "Cash available today", f"{baseline.cash_on_hand:,.0f}", CUSTOMER, False),
        Assumption("supplier_increase_pct", "Supplier cost increase",
                   f"+{baseline.supplier_increase_pct:g}%", CUSTOMER, True,
                   note="Tested at 15%, 25% and 35%."),
        Assumption("low_margin_share_pct", "Share of orders on low-margin lines",
                   f"{baseline.low_margin_share_pct:g}%", CUSTOMER, False),
        Assumption("price_sensitivity", "Price sensitivity of customers", elasticity_value, elasticity_class, True,
                   note="A 1% price rise eventually reduces orders by this percentage. Low 0.70 / "
                        "central 1.30 / high 2.60. Only the high setting is a published figure — it is the "
                        "brand-level meta-analytic mean, i.e. customers who can buy the identical item "
                        "elsewhere. The central and low settings are our judgement, set below brand level "
                        "because changing shop is harder than changing brand. This is the assumption most "
                        "likely to change the decision.",
                   source="bijmolt2005 (high setting); tellis1988 (second reference point)"),
        Assumption("cogs_pass_through", "Share of supplier increase reaching your cost of goods",
                   pass_through, ASSUMPTION, True,
                   note="100% by definition unless you can substitute cheaper lines, renegotiate, or hold "
                        "fixed-price contracts (tested at 70%)."),
        Assumption("inventory_lag", "Delay before higher supplier prices reach your costs",
                   "about 20 days (stock on hand)", ASSUMPTION, False,
                   note="Stock already on the shelf was bought at the old price. Tested over a 10-30 day "
                        "range; the comparison uses the midpoint. A shop holding more stock than that sees "
                        "the increase later than this shows."),
        Assumption("demand_adjustment_speed", "How quickly customers react to a price change",
                   speed, ASSUMPTION, True),
        Assumption("trim_effectiveness", "Cost saving from dropping low-margin lines",
                   f"{reduction:g} points off average cost of goods "
                   f"({trim_effectiveness:.3f} per point of low-margin share)", ASSUMPTION, True,
                   note="Assumes low-margin lines carry roughly 2.9x the average cost share, which is close "
                        "to what makes them low-margin. Tested at half and one-and-a-half times this rate."),
        Assumption("trim_demand_cost", "Orders lost from dropping those lines",
                   f"{TRIM_DEMAND_COST_RATIO * reduction:.1f}% of orders", ASSUMPTION, False,
                   note=f"{TRIM_DEMAND_COST_RATIO:g} of the cost saving, in points of orders: customers who "
                        f"came for the removed lines and do not substitute. Higher than the cafe's ratio "
                        f"because a shopper who cannot find a specific product is more likely to leave."),
        Assumption("price_rises", "Price rises compared",
                   f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%", CUSTOMER, False,
                   note="The decisions being compared; fixed by the question."),
        Assumption("horizon", "Comparison horizon", "90 days", ASSUMPTION, False,
                   note="Long enough for the stock to turn over at the new cost and for most of the customer "
                        "reaction to land; short enough that rent and wages can be treated as fixed."),
        Assumption("average_order_value", "Average order value", f"{baseline.average_order_value:,.2f}",
                   DERIVED, False, note="Monthly sales divided by monthly orders."),
        Assumption("cogs_per_order", "Cost of goods per order", f"{baseline.cogs_per_order:,.2f}",
                   DERIVED, False),
    ]
