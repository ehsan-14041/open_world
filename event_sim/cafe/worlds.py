"""
The shock, and the three decisions — as engine events and interventions.

These are the ONLY things allowed to differ between worlds. Baseline, module, coefficients,
axis settings, horizon and engine are shared by construction: every world is built from the
same slice object and the same SimulationConfig, and a test asserts the shared fingerprint
components match. That invariance is the product.

World C's menu reformulation needs one derived number: how many percentage points of COGS
can be removed by dropping low-margin items. It is derived from the owner's estimate of the
low-margin share by a fixed conversion factor, and that factor is an expert assumption that
the sensitivity analysis sweeps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from event_sim.engine import Intervention
from event_sim.schemas import EventDefinition, WorldSlice

from event_sim.cafe.baseline import CafeBaseline

HORIZON_DAYS = 90
MODULE_ID = "cafe_cost_shock_v1"

#: Percentage points of average COGS removed per percentage point of orders on low-margin
#: items. 0.30 means dropping items that make up 20% of orders trims average ingredient cost
#: by 6 points. EXPERT ASSUMPTION: low-margin items are taken to carry roughly 2.5x the
#: average ingredient share, so removing or reformulating them moves the average by about
#: 0.3 points per point of share. Swept in sensitivity at 0.15 / 0.30 / 0.45.
REFORMULATION_EFFECTIVENESS = 0.30

#: Price rises compared. Fixed by the product definition.
PRICE_RISE_B = 10.0
PRICE_RISE_C = 5.0


@dataclass(frozen=True)
class WorldSpec:
    id: str
    label: str
    headline: str
    price_rise_pct: float
    cogs_reduction_points: float
    events: list[EventDefinition] = field(default_factory=list)
    interventions: list[Intervention] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "headline": self.headline,
            "price_rise_pct": self.price_rise_pct,
            "cogs_reduction_points": self.cogs_reduction_points,
            "events": [e.to_dict() for e in self.events],
            "interventions": [i.to_dict() for i in self.interventions],
        }


def cost_shock(baseline: CafeBaseline) -> EventDefinition:
    """The shared shock: supplier prices step up and stay up for the whole horizon."""
    return EventDefinition(
        id="supplier_cost_increase",
        label=f"Supplier prices +{baseline.supplier_increase_pct:g}%",
        description="Ingredient / input prices rise and stay at the new level for 90 days.",
        targets={"input_cost": float(baseline.supplier_increase_pct)},
        start_turn=1,
        duration=HORIZON_DAYS,
        shape="step",
        status="user_assumption",
    )


def cogs_reduction_points(
    baseline: CafeBaseline, effectiveness: float = REFORMULATION_EFFECTIVENESS
) -> float:
    return round(baseline.low_margin_share_pct * effectiveness, 3)


def build_worlds(
    slice_: WorldSlice,
    baseline: CafeBaseline,
    *,
    reformulation_effectiveness: float = REFORMULATION_EFFECTIVENESS,
) -> list[WorldSpec]:
    shock = cost_shock(baseline)
    reduction = cogs_reduction_points(baseline, reformulation_effectiveness)

    world_a = WorldSpec(
        id="A",
        label="Do nothing",
        headline="Hold prices. Absorb the full cost increase.",
        price_rise_pct=0.0,
        cogs_reduction_points=0.0,
        events=[shock],
        interventions=[],
    )
    world_b = WorldSpec(
        id="B",
        label=f"Raise prices {PRICE_RISE_B:g}%",
        headline=f"Pass most of the increase to customers with a {PRICE_RISE_B:g}% average price rise.",
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
        label=f"Raise prices {PRICE_RISE_C:g}% + trim the menu",
        headline=(
            f"A smaller {PRICE_RISE_C:g}% price rise, plus removing or reformulating "
            f"low-margin items to cut ingredient cost per order."
        ),
        price_rise_pct=PRICE_RISE_C,
        cogs_reduction_points=reduction,
        events=[shock],
        interventions=[
            Intervention.from_slice(
                slice_, "raise_prices", magnitude=PRICE_RISE_C, start_turn=1, duration=HORIZON_DAYS
            ),
            Intervention.from_slice(
                slice_, "reformulate_menu", magnitude=reduction, start_turn=1, duration=HORIZON_DAYS
            ),
        ],
    )
    return [world_a, world_b, world_c]
