"""
The salon wedge.

Not a third cost-shock calculator. The thing that changes is demand, and the decision turns on
a ceiling: a diary has a fixed number of slots, so appointments lost to a price rise may be
ones that were being turned away anyway. That ceiling is applied by the accounting layer, which
is what lets the engine stay acyclic — price moves demand, and nothing feeds back.
"""

from __future__ import annotations

from typing import Any

from event_sim.salon.baseline import DEMO_SALON, INTAKE_FIELDS, SalonBaseline
from event_sim.salon.evidence import SOURCES, registry
from event_sim.salon.worlds import (
    HORIZON_DAYS,
    MIX_DEMAND_COST_RATIO,
    MIX_EFFECTIVENESS,
    MODULE_ID,
    PRICE_RISE_B,
    PRICE_RISE_C,
    build_worlds,
    capacity_per_day,
    cost_reduction_points,
)
from event_sim.wedge.spec import WedgeSpec, _key_from_fields

DEFAULT_AXES: dict[str, str] = {
    "price_sensitivity": "central",
    "demand_adjustment_speed": "central",
}

SWEEP: dict[str, list[Any]] = {
    "price_sensitivity": ["low", "central", "high"],
    "utilisation_pct": [75.0, 95.0],
    "demand_growth_pct": [15.0, 25.0, 35.0],
    "mix_effectiveness": [0.16, 0.32, 0.48],
    "demand_adjustment_speed": ["slow", "central", "fast"],
}

SWEEP_LABELS: dict[str, str] = {
    "price_sensitivity": "How price-sensitive clients are",
    "utilisation_pct": "How full the diary really is",
    "demand_growth_pct": "How much busier it has actually become",
    "mix_effectiveness": "How much shifting the mix really saves",
    "demand_adjustment_speed": "How quickly clients react",
}


def _grid_key(baseline, settings: dict[str, Any], _comparison: Any) -> dict[str, Any]:
    return _key_from_fields(COPY["grid_key_fields"], cost_reduction_points(baseline, float(settings["mix_effectiveness"])), settings)


COPY: dict[str, Any] = {
    "grid_key": _grid_key,
    "fields": {
        "units_per_day": "appointments_per_day",
        "unit_cost_total": "monthly_variable_costs",
        "revenue": "monthly_revenue",
        "fixed": "monthly_fixed_costs",
        "cash": "cash_on_hand",
        "shock": "demand_growth_pct",
        "low_margin": "low_margin_share_pct",
        "utilisation": "utilisation_pct",
    },
    "primary_axis": "price_sensitivity",
    "summary_fields": [
        ["monthly_revenue", "monthly_revenue", 2], ["appointments_per_day", "appointments_per_day", 2],
        ["average_ticket", "average_ticket", 2], ["monthly_variable_costs", "unit_cost_total", 2],
        ["variable_cost_pct", "cost_pct", 1], ["gross_margin_pct", "gross_margin_pct", 1],
        ["monthly_fixed_costs", "fixed", 2], ["monthly_net", "monthly_net", 2],
        ["net_margin_pct", "net_margin_pct", 1], ["cash_on_hand", "cash", 2],
        ["utilisation_pct", "utilisation_pct", None], ["capacity_per_day", "capacity_per_day", 2],
        ["demand_growth_pct", "demand_growth_pct", None],
        ["low_margin_share_pct", "low_margin_share_pct", None],
    ],
    "grid_key_fields": {
        "price_sensitivity": "price_sensitivity",
        "utilisation_pct": {"float": "utilisation_pct"},
        "demand_growth_pct": {"float": "demand_growth_pct"},
        "reduction_points": "reduction",
        "demand_adjustment_speed": "demand_adjustment_speed",
    },
    "demo_noun": "salon",
    "page_title": "Salon pricing decision — three options compared",
    "research_settings": [],
    "world_verdict_labels": {
        "A": "Keeping prices and serving more",
        "B": f"Raising prices {PRICE_RISE_B:g}%",
        "C": f"A {PRICE_RISE_C:g}% rise plus shifting the mix",
    },
    "world_names": {
        "A": "Keep prices, serve more",
        "B": f"Raise prices {PRICE_RISE_B:g}%",
        "C": f"Raise prices {PRICE_RISE_C:g}% + shift the mix",
    },
    "world_short": {"A": "Keep prices", "B": f"Raise {PRICE_RISE_B:g}%",
                    "C": f"Raise {PRICE_RISE_C:g}% + shift mix"},
    "headline": "Your diary is {shock}% busier. Is it time to raise prices?",
    "hero_lede": "We compared three decisions using the same model of your salon and the same "
                 "assumptions. Only the decision changes between them — so the differences come "
                 "from the decision, not from different guesses.",
    "unit_word": "appointments",
    "unit_word_singular": "appointment",
    "cost_word": "cost per appointment",
    "uncertainty_title": "How price-sensitive are your clients?",
    "uncertainty_eyebrow": "The biggest uncertainty",
    "sens_help": {
        "low": "A loyal client base who book with you personally.",
        "central": "Our judgement for an appointment business with real switching costs.",
        "high": "Stress case: clients who treat it as a commodity and shop on price.",
    },
    "sens_values": {"low": "0.30", "central": "0.60", "high": "1.20"},
    "capacity_note": "Because your diary has a ceiling, some of the {unit} a price rise costs you "
                     "were being turned away anyway. That is why raising prices costs less here "
                     "than the price sensitivity on its own suggests.",
    "c_card_note": "Depends on three of our assumptions: how much shifting the mix cuts your "
                   "{cost} (about {red} points here), how much it lifts the average ticket, and "
                   "how many {unit} leave with the discounts ({loss}%). None is calibrated to "
                   "your business yet.",
    "chart_title": "Cash in the bank under each decision",
    "chart_lede": "Clients on a six-week cycle only meet a new price at their next visit, so the "
                  "reaction arrives over a couple of weeks rather than at once.",
    "next_measurement": "Raise the price of one service, or for new clients only, and count "
                        "rebookings for six weeks. That is a direct measurement of the one number "
                        "this decision hangs on — and for a salon there is no published figure to "
                        "fall back on, so your own test is worth more here than in any other trade.",
    "sources_note": "On price sensitivity: we found no published elasticity for personal-care "
                    "services that could be used honestly. Every setting on that control is our "
                    "judgement. The retail studies listed are only the reference points our range "
                    "was positioned against — they measure shoppers switching brands, not clients "
                    "changing salon.",
    "limits_does_not": [
        "Predict the future or guarantee an outcome.",
        "Model hiring, longer opening hours or a second chair.",
        "Model competitors, word of mouth or reputation.",
        "Know your clients' price sensitivity — there is no published figure, so your own test is the only real evidence.",
    ],
    "intake_groups": [
        {"label": "Your business", "fields": ["monthly_revenue", "appointments_per_day", "cash_on_hand"]},
        {"label": "Your diary", "fields": ["utilisation_pct", "demand_growth_pct"]},
        {"label": "Your costs", "fields": ["monthly_variable_costs", "monthly_fixed_costs"]},
        {"label": "Your services", "fields": ["low_margin_share_pct", "name"]},
    ],
}

SALON_WEDGE = WedgeSpec(
    id="salon",
    business="Salon / Service Business",
    question="My schedule is filling up. Is it time to raise prices?",
    module_id=MODULE_ID,
    horizon_days=HORIZON_DAYS,
    default_axes=DEFAULT_AXES,
    demand_var="appointment_demand",
    price_var="service_price",
    unit_cost_var="cost_per_appointment",
    index_vars=("market_demand", "appointment_demand", "service_price", "cost_per_appointment"),
    elasticity_edge="service_price->appointment_demand",
    slice_question="Demand for appointments rose. Which response?",
    build_worlds=build_worlds,
    build_registry=registry,
    sweep=SWEEP,
    sweep_labels=SWEEP_LABELS,
    sources=SOURCES,
    intake_fields=INTAKE_FIELDS,
    demo_factory=lambda: DEMO_SALON,
    baseline_from_dict=SalonBaseline.from_dict,
    knob_defaults={"mix_effectiveness": MIX_EFFECTIVENESS},
    capacity_per_day=capacity_per_day,
    copy=COPY,
)
