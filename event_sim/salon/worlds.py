"""
The change, and the three decisions — as engine events and interventions.

The shock here is DEMAND, not cost: more people want appointments than before. What makes the
decision interesting is that the diary has a ceiling, and that ceiling is applied by the
accounting layer (served = min(wanted, slots)), not by the engine — a business cannot serve
appointments it has no slots for, which is an identity about slots rather than a behaviour.

Everything that changes behaviour is a named constant here so the report can list it and the
sweep can move it.
"""

from __future__ import annotations

from event_sim.engine import Intervention
from event_sim.schemas import EventDefinition, WorldSlice
from event_sim.wedge.spec import WorldSpec

from event_sim.salon.baseline import SalonBaseline

HORIZON_DAYS = 90
MODULE_ID = "salon_capacity_pricing_v1"

#: Percentage points of variable cost per appointment removed per percentage point of
#: appointments on discounted / low-margin services. 0.32 means a salon where 25% of
#: appointments are low-margin can cut variable cost per appointment by 8 points by shifting
#: the diary. EXPERT ASSUMPTION. Swept at 0.16 / 0.32 / 0.48.
MIX_EFFECTIVENESS = 0.32

#: Appointments lost per point of variable cost removed, in points of demand. EXPERT
#: ASSUMPTION: clients who came for the discounted service and will not pay full price.
MIX_DEMAND_COST_RATIO = 0.4

#: How much of the mix shift shows up as a higher average ticket, per point of cost removed.
#: EXPERT ASSUMPTION: a richer mix sells for more, not only costs more.
MIX_PRICE_GAIN_RATIO = 0.25

#: Price rises compared. Fixed by the product definition.
PRICE_RISE_B = 10.0
PRICE_RISE_C = 5.0


def demand_growth(baseline: SalonBaseline) -> EventDefinition:
    """
    The shared change: more people want appointments, and keep wanting them.

    Injected into `market_demand`, the exogenous driver — never into `appointment_demand`
    directly. The engine holds an event's target at its displacement and drops the relaxation
    term, so an event aimed at appointment_demand would switch off the price elasticity that
    feeds the same variable and make all three options show identical demand.
    """
    return EventDefinition(
        id="demand_increase",
        label=f"Appointments wanted +{baseline.demand_growth_pct:g}%",
        description="Demand for appointments rises and stays at the new level for 90 days.",
        targets={"market_demand": float(baseline.demand_growth_pct)},
        start_turn=1,
        duration=HORIZON_DAYS,
        shape="step",
        status="user_assumption",
    )


def cost_reduction_points(baseline: SalonBaseline, effectiveness: float = MIX_EFFECTIVENESS) -> float:
    return round(baseline.low_margin_share_pct * effectiveness, 3)


def build_worlds(
    slice_: WorldSlice,
    baseline: SalonBaseline,
    *,
    mix_effectiveness: float = MIX_EFFECTIVENESS,
) -> list[WorldSpec]:
    growth = demand_growth(baseline)
    reduction = cost_reduction_points(baseline, mix_effectiveness)

    world_a = WorldSpec(
        id="A",
        label="Keep prices, serve more",
        headline="Leave prices where they are and fit in as many of the extra appointments as the diary allows.",
        price_rise_pct=0.0,
        cogs_reduction_points=0.0,
        events=[growth],
        interventions=[],
    )
    world_b = WorldSpec(
        id="B",
        label=f"Raise prices {PRICE_RISE_B:g}%",
        headline=f"Raise prices {PRICE_RISE_B:g}% and let demand settle back toward the slots you actually have.",
        price_rise_pct=PRICE_RISE_B,
        cogs_reduction_points=0.0,
        events=[growth],
        interventions=[
            Intervention.from_slice(
                slice_, "raise_prices", magnitude=PRICE_RISE_B, start_turn=1, duration=HORIZON_DAYS
            )
        ],
    )
    world_c = WorldSpec(
        id="C",
        label=f"Raise prices {PRICE_RISE_C:g}% + shift the mix",
        headline=(
            f"A smaller {PRICE_RISE_C:g}% rise, plus moving the diary toward services that earn "
            f"more and cutting discounting."
        ),
        price_rise_pct=PRICE_RISE_C,
        cogs_reduction_points=reduction,
        events=[growth],
        interventions=[
            Intervention.from_slice(
                slice_, "raise_prices", magnitude=PRICE_RISE_C, start_turn=1, duration=HORIZON_DAYS
            ),
            Intervention.from_slice(
                slice_, "shift_service_mix", magnitude=reduction, start_turn=1, duration=HORIZON_DAYS
            ),
        ],
    )
    return [world_a, world_b, world_c]


def capacity_per_day(baseline: SalonBaseline, **_knobs: float) -> float:
    """Appointment slots available per day. Fixed over the horizon — that is the whole point."""
    return baseline.capacity_per_day
