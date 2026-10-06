"""
Where every number in the salon comparison comes from.

The honest position here is blunter than in the other two wedges: we found no peer-reviewed
price elasticity for personal-care services with a usable published mean. So the elasticity is
a MODEL ASSUMPTION at every setting — `RESEARCH_SETTINGS` is deliberately empty — and the
report says so in those words rather than borrowing a retail meta-analysis and hoping the
reader does not check the population.

The retail figures are still listed as sources, because the reasoning for where the salon range
sits refers to them: below brand-level retail switching, because changing hairdresser costs a
client more than changing which tin they pick off a shelf. That reasoning is an argument, not
evidence, and is labelled as one.

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

#: Empty on purpose: no published elasticity for personal-care services could be used honestly.
RESEARCH_SETTINGS: list[str] = []

REGISTRY_SPEC: list[dict] = [
    {"key": "monthly_revenue", "label": "Current monthly sales", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_revenue"}},
    {"key": "appointments_per_day", "label": "Appointments per day", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "appointments_per_day", "dp": 1}},
    {"key": "utilisation_pct", "label": "How full the diary is today", "klass": CUSTOMER, "swept": True,
     "value": {"kind": "g", "field": "utilisation_pct", "suffix": "%"},
     "note": "Tested at 75% and 95% as well. This decides how much the capacity ceiling matters: at "
             "95% full, appointments lost to a price rise were largely being turned away anyway."},
    {"key": "demand_growth_pct", "label": "How much busier it has become", "klass": CUSTOMER, "swept": True,
     "value": {"kind": "g", "field": "demand_growth_pct", "prefix": "+", "suffix": "%"},
     "note": "Tested at 15%, 25% and 35%."},
    {"key": "monthly_variable_costs", "label": "Monthly product cost", "klass": CUSTOMER,
     "value": {"kind": "money_with_pct", "field": "monthly_variable_costs", "pct_of": "variable_cost_pct"},
     "note": "Products and consumables only. Wages are in fixed costs."},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs (incl. wages)", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "monthly_fixed_costs"},
     "note": "Treated as unchanged over 90 days. Over that horizon a salon's staff cost does not move "
             "with one more or one fewer appointment, which is why serving extra clients adds little "
             "cost and why the capacity ceiling, not the cost, is the binding constraint."},
    {"key": "cash_on_hand", "label": "Cash available today", "klass": CUSTOMER,
     "value": {"kind": "money", "field": "cash_on_hand"}},
    {"key": "low_margin_share_pct", "label": "Share of appointments on discounted / low-margin services",
     "klass": CUSTOMER,
     "value": {"kind": "g", "field": "low_margin_share_pct", "suffix": "%"}},
    {"key": "price_sensitivity", "label": "Price sensitivity of clients", "klass": ASSUMPTION,
     "swept": True, "elasticity": True,
     "value": {"kind": "axis", "axis": "price_sensitivity",
               "map": {"low": "0.30", "central": "0.60", "high": "1.20"}},
     "assumption_source": "No direct source. bijmolt2005 / tellis1988 are listed only as the retail "
                          "reference points the range is positioned against.",
     "note": "A 1% price rise eventually reduces appointments WANTED by this percentage. Low 0.30 / "
             "central 0.60 / high 1.20. NO published elasticity for personal-care services with a "
             "usable mean was found, so all three settings are our judgement, not research. They sit "
             "below the retail brand-level meta-analyses because changing hairdresser costs a client "
             "more than changing brand on a shelf — an argument, not evidence. The high setting exists "
             "to test what happens if that argument is wrong."},
    {"key": "capacity_per_day", "label": "Appointment slots available per day", "klass": DERIVED,
     "value": {"kind": "money", "field": "capacity_per_day", "dp": 1},
     "note": "Appointments per day divided by how full the diary is. Held fixed for 90 days: hiring or "
             "extending hours is a different decision from the one being compared here."},
    {"key": "capacity_rule", "label": "What happens when demand exceeds the slots", "klass": DERIVED,
     "value": {"kind": "literal", "text": "appointments served = the smaller of wanted and available"},
     "note": "An accounting identity, not a simulated behaviour. Appointments above the ceiling are "
             "counted as turned away — which the business itself usually cannot observe, so treat that "
             "figure as a model quantity rather than a measurement."},
    {"key": "demand_adjustment_speed", "label": "How quickly clients react to a price change",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "axis", "axis": "demand_adjustment_speed",
               "map": {"slow": "about three weeks to half-react",
                       "central": "about eleven days to half-react",
                       "fast": "about five days to half-react"}},
     "note": "Clients on a six-week cycle only meet a new price at their next visit, which is why even "
             "the fast setting is not immediate."},
    {"key": "mix_effectiveness", "label": "Cost saving from shifting the service mix",
     "klass": ASSUMPTION, "swept": True,
     "value": {"kind": "template",
               "text": "{reduction:g} points off cost per appointment "
                       "({mix_effectiveness:.2f} per point of low-margin share)"},
     "note": "Tested at half and one-and-a-half times this rate."},
    {"key": "mix_price_gain", "label": "Price gain from a richer mix", "klass": ASSUMPTION,
     "value": {"kind": "template", "text": "+{price_gain:.1f}% on the average ticket"},
     "note": f"{MIX_PRICE_GAIN_RATIO:g} of the cost saving: services that cost more to deliver "
             f"generally sell for more."},
    {"key": "mix_demand_cost", "label": "Appointments lost from cutting discounts", "klass": ASSUMPTION,
     "value": {"kind": "template", "text": "{demand_cost:.1f}% of appointments wanted"},
     "note": f"{MIX_DEMAND_COST_RATIO:g} of the cost saving, in points of demand: clients who came for "
             f"the discounted service and will not pay full price."},
    {"key": "price_rises", "label": "Price rises compared", "klass": CUSTOMER,
     "value": {"kind": "literal", "text": f"B: +{PRICE_RISE_B:g}%   C: +{PRICE_RISE_C:g}%"},
     "note": "The decisions being compared; fixed by the question."},
    {"key": "horizon", "label": "Comparison horizon", "klass": ASSUMPTION,
     "value": {"kind": "literal", "text": "90 days"},
     "note": "Long enough for clients on a typical rebooking cycle to meet the new price at least once; "
             "short enough that rent and wages can be treated as fixed. Hiring, or opening more hours, "
             "is outside it."},
    {"key": "average_ticket", "label": "Average price per appointment", "klass": DERIVED,
     "value": {"kind": "money", "field": "average_ticket", "dp": 2},
     "note": "Monthly sales divided by monthly appointments."},
    {"key": "cost_per_appointment", "label": "Product cost per appointment", "klass": DERIVED,
     "value": {"kind": "money", "field": "unit_cost", "dp": 2}},
]


def registry(
    baseline: SalonBaseline,
    *,
    axis_settings: dict[str, str],
    mix_effectiveness: float = MIX_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> list[Assumption]:
    reduction = cost_reduction_points(baseline, mix_effectiveness)
    return render_registry(
        REGISTRY_SPEC, baseline,
        axis_settings=axis_settings,
        knobs={"mix_effectiveness": mix_effectiveness},
        extra={
            "variable_cost_pct": baseline.variable_cost_pct,
            "reduction": reduction,
            "demand_cost": MIX_DEMAND_COST_RATIO * reduction,
            "price_gain": MIX_PRICE_GAIN_RATIO * reduction,
            "capacity_per_day": baseline.capacity_per_day,
            "average_ticket": baseline.average_ticket,
            "unit_cost": baseline.unit_cost,
        },
        custom_elasticity=custom_elasticity,
        research_settings=RESEARCH_SETTINGS,
    )
