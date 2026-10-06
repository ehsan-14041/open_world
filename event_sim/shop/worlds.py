"""
The shock, and the three decisions — as engine events and interventions.

These are the ONLY things allowed to differ between worlds. Baseline, module, coefficients,
axis settings, horizon and engine are shared by construction: every world is built from the
same slice object and the same SimulationConfig, and a test asserts the shared fingerprint
components match. That invariance is the product.

Every quantity that changes behaviour is a named constant here, not a literal buried in a
call, so the report can list it and the sensitivity sweep can move it.
"""

from __future__ import annotations

from event_sim.engine import Intervention
from event_sim.schemas import EventDefinition, WorldSlice
from event_sim.wedge.spec import WorldSpec

from event_sim.shop.baseline import ShopBaseline

HORIZON_DAYS = 90
MODULE_ID = "shop_cost_shock_v1"

#: Percentage points of average cost-of-goods removed per percentage point of orders on
#: low-margin lines. 0.375 means dropping lines that make up 20% of orders trims average unit
#: cost by 7.5 points. EXPERT ASSUMPTION: low-margin lines are taken to carry roughly 2.9x the
#: average cost share — by definition they are the ones where the goods eat most of the price.
#: Higher than the cafe's 0.30 for that reason. Swept at 0.19 / 0.375 / 0.56.
TRIM_EFFECTIVENESS = 0.375

#: Orders lost per point of cost-of-goods removed, in points of demand. EXPERT ASSUMPTION and
#: higher than the cafe's 0.33: a shopper who came for a specific product and cannot find it is
#: more likely to leave than a cafe customer choosing from a shorter menu. Encoded in the
#: module as the intervention's demand effect per unit.
TRIM_DEMAND_COST_RATIO = 0.45

#: Price rises compared. Fixed by the product definition, and smaller than the cafe's 10%/5%
#: because a shop's customers can more easily buy the same item elsewhere — a 10% rise is not
#: the decision most small retailers are actually weighing.
PRICE_RISE_B = 8.0
PRICE_RISE_C = 4.0


def cost_shock(baseline: ShopBaseline) -> EventDefinition:
    """The shared shock: supplier prices step up and stay up for the whole horizon."""
    return EventDefinition(
        id="supplier_cost_increase",
        label=f"Supplier prices +{baseline.supplier_increase_pct:g}%",
        description="Wholesale / supplier prices rise and stay at the new level for 90 days.",
        targets={"supplier_cost": float(baseline.supplier_increase_pct)},
        start_turn=1,
        duration=HORIZON_DAYS,
        shape="step",
        status="user_assumption",
    )


def cogs_reduction_points(baseline: ShopBaseline, effectiveness: float = TRIM_EFFECTIVENESS) -> float:
    return round(baseline.low_margin_share_pct * effectiveness, 3)


def build_worlds(
    slice_: WorldSlice,
    baseline: ShopBaseline,
    *,
    trim_effectiveness: float = TRIM_EFFECTIVENESS,
) -> list[WorldSpec]:
    shock = cost_shock(baseline)
    reduction = cogs_reduction_points(baseline, trim_effectiveness)

    world_a = WorldSpec(
        id="A",
        label="Hold prices",
        headline="Keep your prices where they are and absorb the whole increase.",
        price_rise_pct=0.0,
        cogs_reduction_points=0.0,
        events=[shock],
        interventions=[],
    )
    world_b = WorldSpec(
        id="B",
        label=f"Raise prices {PRICE_RISE_B:g}%",
        headline=f"Pass most of the increase on with a {PRICE_RISE_B:g}% rise across the range.",
        price_rise_pct=PRICE_RISE_B,
        cogs_reduction_points=0.0,
        events=[shock],
        interventions=[
            Intervention.from_slice(
                slice_, "raise_prices", magnitude=PRICE_RISE_B, start_turn=1, duration=HORIZON_DAYS
            )
        ],
    )
    world_c = WorldSpec(
        id="C",
        label=f"Raise prices {PRICE_RISE_C:g}% + stop restocking low-margin lines",
        headline=(
            f"A smaller {PRICE_RISE_C:g}% rise, plus letting the lines that earn least sell "
            f"through and not reordering them."
        ),
        price_rise_pct=PRICE_RISE_C,
        cogs_reduction_points=reduction,
        events=[shock],
        interventions=[
            Intervention.from_slice(
                slice_, "raise_prices", magnitude=PRICE_RISE_C, start_turn=1, duration=HORIZON_DAYS
            ),
            Intervention.from_slice(
                slice_, "trim_low_margin_range", magnitude=reduction, start_turn=1, duration=HORIZON_DAYS
            ),
        ],
    )
    return [world_a, world_b, world_c]
