"""
Where every number in the salon comparison comes from.

The honest position here is blunter than in the other two wedges: we found no peer-reviewed
price elasticity for personal-care services with a usable published mean. So the elasticity is
a MODEL ASSUMPTION at every setting, and the report says so in those words rather than
borrowing a retail meta-analysis and hoping the reader does not check the population.

The retail figures are still listed as sources, because the reasoning for where we put the
salon range refers to them — below brand-level retail switching, because changing hairdresser
costs a client more than changing which tin they pick off a shelf. That reasoning is an
argument, not evidence, and is labelled accordingly.
"""

from __future__ import annotations

from event_sim.wedge.evidence import (
    ASSUMPTION,
    CUSTOMER,
    DERIVED,
    Assumption,
)
from event_sim.wedge.evidence import BIJMOLT_2005, TELLIS_1988

from event_sim.salon.baseline import SalonBaseline
from event_sim.salon.worlds import (
    MIX_DEMAND_COST_RATIO,
    MIX_EFFECTIVENESS,
    MIX_PRICE_GAIN_RATIO,
    PRICE_RISE_B,
    PRICE_RISE_C,
    cost_reduction_points,
)

SOURCES: list[dict[str, str]] = [BIJMOLT_2005, TELLIS_1988]


def registry(
    baseline: SalonBaseline,
    *,
    axis_settings: dict[str, str],
    mix_effectiveness: float = MIX_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    setting = axis_settings.get("price_sensitivity", "central")
    elasticity_value = {"low": "0.30", "central": "0.60", "high": "1.20"}[setting]
    elasticity_class = ASSUMPTION          # never RESEARCH: no usable published figure exists
    if custom_elasticity is not None:
        elasticity_value, elasticity_class = f"{abs(custom_elasticity):.2f} (your value)", CUSTOMER

    speed = {"slow": "about three weeks to half-react",
             "central": "about eleven days to half-react",
             "fast": "about five days to half-react"}[
        axis_settings.get("demand_adjustment_speed", "central")]
    reduction = cost_reduction_points(baseline, mix_effectiveness)

    return [
        Assumption("monthly_revenue", "Current monthly sales", f"{baseline.monthly_revenue:,.0f}", CUSTOMER, False),
        Assumption("appointments_per_day", "Appointments per day", f"{baseline.appointments_per_day:,.1f}", CUSTOMER, False),
        Assumption("utilisation_pct", "How full the diary is today", f"{baseline.utilisation_pct:g}%", CUSTOMER, True,
                   note="Tested at 75% and 95% as well. This decides how much the capacity ceiling matters: "
                        "at 95% full, appointments lost to a price rise were largely being turned away anyway."),
        Assumption("demand_growth_pct", "How much busier it has become", f"+{baseline.demand_growth_pct:g}%", CUSTOMER, True,
                   note="Tested at 15%, 25% and 35%."),
        Assumption("monthly_variable_costs", "Monthly product cost",
                   f"{baseline.monthly_variable_costs:,.0f} ({baseline.variable_cost_pct:.0f}% of sales)", CUSTOMER, False,
                   note="Products and consumables only. Wages are in fixed costs."),
        Assumption("monthly_fixed_costs", "Monthly fixed costs (incl. wages)",
                   f"{baseline.monthly_fixed_costs:,.0f}", CUSTOMER, False,
                   note="Treated as unchanged over 90 days. Over that horizon a salon's staff cost does not "
                        "move with one more or one fewer appointment, which is why serving extra clients adds "
                        "little cost and why the capacity ceiling, not the cost, is the binding constraint."),
        Assumption("cash_on_hand", "Cash available today", f"{baseline.cash_on_hand:,.0f}", CUSTOMER, False),
        Assumption("low_margin_share_pct", "Share of appointments on discounted / low-margin services",
                   f"{baseline.low_margin_share_pct:g}%", CUSTOMER, False),
        Assumption("price_sensitivity", "Price sensitivity of clients", elasticity_value, elasticity_class, True,
                   note="A 1% price rise eventually reduces appointments WANTED by this percentage. Low 0.30 / "
                        "central 0.60 / high 1.20. NO published elasticity for personal-care services with a "
                        "usable mean was found, so all three settings are our judgement, not research. They sit "
                        "below the retail brand-level meta-analyses because changing hairdresser costs a client "
                        "more than changing brand on a shelf — an argument, not evidence. The high setting "
                        "exists to test what happens if that argument is wrong.",
                   source="No direct source. bijmolt2005 / tellis1988 are listed only as the retail reference "
                          "points the range is positioned against."),
        Assumption("capacity_per_day", "Appointment slots available per day",
                   f"{baseline.capacity_per_day:,.1f}", DERIVED, False,
                   note="Appointments per day divided by how full the diary is. Held fixed for 90 days: hiring "
                        "or extending hours is a different decision from the one being compared here."),
        Assumption("capacity_rule", "What happens when demand exceeds the slots",
                   "appointments served = the smaller of wanted and available", DERIVED, False,
                   note="An accounting identity, not a simulated behaviour. Appointments above the ceiling are "
                        "counted as turned away — which the business itself usually cannot observe, so treat "
                        "that figure as a model quantity rather than a measurement."),
        Assumption("demand_adjustment_speed", "How quickly clients react to a price change", speed, ASSUMPTION, True,
                   note="Clients on a six-week cycle only meet a new price at their next visit, which is why "
                        "even the fast setting is not immediate."),
        Assumption("mix_effectiveness", "Cost saving from shifting the service mix",
                   f"{reduction:g} points off cost per appointment "
                   f"({mix_effectiveness:.2f} per point of low-margin share)", ASSUMPTION, True,
                   note="Tested at half and one-and-a-half times this rate."),
        Assumption("mix_price_gain", "Price gain from a richer mix",
                   f"+{MIX_PRICE_GAIN_RATIO * reduction:.1f}% on the average ticket", ASSUMPTION, False,
                   note=f"{MIX_PRICE_GAIN_RATIO:g} of the cost saving: services that cost more to deliver "
                        f"generally sell for more."),
        Assumption("mix_demand_cost", "Appointments lost from cutting discounts",
                   f"{MIX_DEMAND_COST_RATIO * reduction:.1f}% of appointments wanted", ASSUMPTION, False,
                   note=f"{MIX_DEMAND_COST_RATIO:g} of the cost saving, in points of demand: clients who came "
                        f"for the discounted service and will not pay full price."),
        Assumption("price_rises", "Price rises compared",
                   f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%", CUSTOMER, False,
                   note="The decisions being compared; fixed by the question."),
        Assumption("horizon", "Comparison horizon", "90 days", ASSUMPTION, False,
                   note="Long enough for clients on a typical rebooking cycle to meet the new price at least "
                        "once; short enough that rent and wages can be treated as fixed. Hiring, or opening "
                        "more hours, is outside it."),
        Assumption("average_ticket", "Average price per appointment", f"{baseline.average_ticket:,.2f}",
                   DERIVED, False, note="Monthly sales divided by monthly appointments."),
        Assumption("cost_per_appointment", "Product cost per appointment", f"{baseline.unit_cost:,.2f}",
                   DERIVED, False),
    ]
