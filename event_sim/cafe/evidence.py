"""
Every assumption in the comparison, classified.

Four customer-facing classes, mapped onto the project's evidence ladder so nothing is
silently promoted:

    CUSTOMER INPUT      user_assumption        the owner typed it; we take it as given
    EXTERNAL RESEARCH   literature_backed      a cited study supports the central value
    ASSUMPTION          expert_assumption      our judgement, stated as such, and swept
    DERIVED             derived                arithmetic on the above, no new information

The registry is the page-5 table of the report and the "how this was calculated" panel of
the demo. It is generated from one list so the two can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.worlds import PRICE_RISE_B, PRICE_RISE_C, REFORMULATION_EFFECTIVENESS, cogs_reduction_points

CUSTOMER = "Customer input"
RESEARCH = "External research"
ASSUMPTION = "Assumption"
DERIVED = "Derived"

LADDER = {CUSTOMER: "user_assumption", RESEARCH: "literature_backed", ASSUMPTION: "expert_assumption", DERIVED: "derived"}


@dataclass(frozen=True)
class Assumption:
    key: str
    label: str
    value: str
    klass: str
    swept: bool
    note: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ladder_status"] = LADDER[self.klass]
        return d


SOURCES: list[dict[str, str]] = [
    {
        "id": "andreyeva2010",
        "citation": "Andreyeva T, Long MW, Brownell KD. The impact of food prices on consumption: a systematic review of research on the price elasticity of demand for food. American Journal of Public Health. 2010;100(2):216-222. doi:10.2105/AJPH.2008.151415",
        "population": "160 US studies, 1938-2007; 13 estimates for the 'food away from home' category",
        "estimate": "Own-price elasticity 0.81 (95% CI 0.56-1.07; range 0.23-1.76)",
        "limitations": "Category-level (primary demand): how much less the public eats out when eating out as a whole gets dearer. Not firm-level. US only. Studies up to 2007.",
        "transfer": "Justified for the CENTRAL setting when the cost shock is market-wide and competitors also raise prices, so the cafe's price moves with the category. Not justified on its own for a single cafe raising prices while competitors hold theirs.",
    },
    {
        "id": "bijmolt2005",
        "citation": "Bijmolt THA, van Heerde HJ, Pieters RGM. New empirical generalizations on the determinants of price elasticity. Journal of Marketing Research. 2005;42(2):141-156.",
        "population": "1,851 price elasticities from 81 studies, predominantly packaged consumer goods in retail scanner data",
        "estimate": "Mean brand-level price elasticity -2.62",
        "limitations": "Brand-level in supermarket categories with near-perfect substitutes on the same shelf. An independent cafe is differentiated by location, habit and service in ways a packaged brand is not.",
        "transfer": "Used only as the upper reference point. The HIGH setting of 1.60 is a judgement placed between the category CI top (1.07) and this mean, and is classified as an assumption, not research.",
    },
]


def registry(
    baseline: CafeBaseline,
    *,
    axis_settings: dict[str, str],
    reformulation_effectiveness: float = REFORMULATION_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    elasticity_value = {"low": "0.50", "central": "0.81", "high": "1.60"}[axis_settings.get("price_sensitivity", "central")]
    elasticity_class = RESEARCH if axis_settings.get("price_sensitivity", "central") == "central" else ASSUMPTION
    if custom_elasticity is not None:
        elasticity_value, elasticity_class = f"{abs(custom_elasticity):.2f} (your value)", CUSTOMER
    pass_through = {"low": "70%", "central": "100%", "high": "100%"}[axis_settings.get("cogs_pass_through", "central")]
    speed = {"slow": "about a month to half-react", "central": "about two weeks to half-react", "fast": "about a week to half-react"}[
        axis_settings.get("demand_adjustment_speed", "central")
    ]
    reduction = cogs_reduction_points(baseline, reformulation_effectiveness)

    return [
        Assumption("monthly_revenue", "Current monthly sales", f"{baseline.monthly_revenue:,.0f}", CUSTOMER, False),
        Assumption("daily_orders", "Orders per day", f"{baseline.daily_orders:,.0f}", CUSTOMER, False),
        Assumption("monthly_cogs", "Monthly ingredient cost", f"{baseline.monthly_cogs:,.0f} ({baseline.cogs_pct:.0f}% of sales)", CUSTOMER, False),
        Assumption("monthly_fixed_costs", "Monthly fixed costs (incl. wages)", f"{baseline.monthly_fixed_costs:,.0f}", CUSTOMER, False,
                   note="Treated as unchanged over 90 days."),
        Assumption("cash_on_hand", "Cash available today", f"{baseline.cash_on_hand:,.0f}", CUSTOMER, False),
        Assumption("supplier_increase_pct", "Supplier cost increase", f"+{baseline.supplier_increase_pct:g}%", CUSTOMER, True,
                   note="Tested at 20%, 30% and 40%."),
        Assumption("low_margin_share_pct", "Share of orders on low-margin items", f"{baseline.low_margin_share_pct:g}%", CUSTOMER, False),
        Assumption("price_sensitivity", "Price sensitivity of customers", elasticity_value, elasticity_class, True,
                   note="A 1% price rise eventually reduces orders by this percentage. Low 0.50 / central 0.81 / high 1.60. This is the assumption most likely to change the decision.",
                   source="andreyeva2010; bijmolt2005 (upper reference)"),
        Assumption("cogs_pass_through", "Share of supplier increase reaching your costs", pass_through, ASSUMPTION, True,
                   note="100% by definition unless you can substitute, renegotiate or have fixed-price contracts (tested at 70%)."),
        Assumption("cogs_lag", "Delay before higher prices reach your costs", "about 7 days (stock on hand)", ASSUMPTION, False,
                   note="Fresh inventory turns over in roughly a week; costs then rise over a few more days."),
        Assumption("demand_adjustment_speed", "How quickly customers react to a price change", speed, ASSUMPTION, True),
        Assumption("reformulation_effectiveness", "Ingredient-cost saving from trimming the menu",
                   f"{reduction:g} points off average ingredient cost ({reformulation_effectiveness:.2f} per point of low-margin share)", ASSUMPTION, True,
                   note="Tested at half and one-and-a-half times this rate."),
        Assumption("reformulation_demand_cost", "Orders lost from removing items", f"{0.33 * reduction:.1f}% of orders", ASSUMPTION, False,
                   note="One third of the ingredient-cost saving, in points of orders: customers who came for the removed items."),
        Assumption("price_rises", "Price rises compared", f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%", CUSTOMER, False,
                   note="The decisions being compared; fixed by the question."),
        Assumption("horizon", "Comparison horizon", "90 days", ASSUMPTION, False,
                   note="Long enough for costs and most of the customer reaction to land; short enough that wages and rent can be treated as fixed. Slow customer reactions are not fully visible within it."),
        Assumption("average_order_value", "Average order value", f"{baseline.average_order_value:,.2f}", DERIVED, False,
                   note="Monthly sales divided by monthly orders."),
        Assumption("cogs_per_order", "Ingredient cost per order", f"{baseline.cogs_per_order:,.2f}", DERIVED, False),
    ]


def class_counts(items: list[Assumption]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in items:
        out[a.klass] = out.get(a.klass, 0) + 1
    return out
