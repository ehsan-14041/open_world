"""
What a wedge has to declare.

A wedge is a decision product: one business type, one thing that changed, three options. This
is the whole contract between a wedge and the shared machinery — everything else (the engine
run, the accounting, the sweep, the report) is common code.

Keeping the contract this small is the point. If a new wedge needs the shared code to grow a
special case, that is a signal the wedge does not fit the engine, not a signal to add a flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from event_sim.engine import Intervention
from event_sim.schemas import EventDefinition, WorldSlice


@dataclass(frozen=True)
class WorldSpec:
    """One option being compared. Only events and interventions may differ between worlds."""

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


@dataclass(frozen=True)
class WedgeSpec:
    """One decision product."""

    #: Short identifier used in URLs, report paths and the registry.
    id: str
    #: Customer-facing business type, e.g. "Cafe / Restaurant".
    business: str
    #: The plain-language question on the chooser screen.
    question: str
    #: World module this wedge runs.
    module_id: str
    horizon_days: int
    default_axes: dict[str, str]

    #: Engine variables the accounting reads. Named by role, not by wedge vocabulary.
    demand_var: str
    price_var: str
    unit_cost_var: str
    #: Every variable recorded in the report's `indices` block.
    index_vars: tuple[str, ...]

    #: Edge whose coefficient a custom elasticity replaces, when an owner brings evidence.
    elasticity_edge: str

    #: Question passed to the slice builder — recorded, not used for arithmetic.
    slice_question: str

    #: builds the three worlds: (slice, baseline, **knobs) -> [WorldSpec, WorldSpec, WorldSpec]
    build_worlds: Callable[..., list[WorldSpec]]
    #: builds the assumption registry: (baseline, axis_settings, **knobs) -> [Assumption, ...]
    build_registry: Callable[..., list[Any]]
    #: the swept assumption grid: name -> list of tested values
    sweep: dict[str, list[Any]]
    #: customer-facing names for the swept assumptions
    sweep_labels: dict[str, str]
    #: literature this wedge relies on
    sources: list[dict[str, str]]
    #: the intake form
    intake_fields: list[dict[str, str]]
    #: the demo business
    demo_factory: Callable[[], Any]
    #: baseline constructor from a plain dict
    baseline_from_dict: Callable[[dict[str, Any]], Any]

    #: knobs the wedge accepts beyond the axes, with their defaults — swept and reported.
    knob_defaults: dict[str, float] = field(default_factory=dict)

    #: If set, the accounting clips units served to this many per day: (baseline, **knobs) -> float
    capacity_per_day: Callable[..., float] | None = None

    #: Customer-facing copy for the report. Read by the page; never affects arithmetic.
    copy: dict[str, Any] = field(default_factory=dict)

    def world_ids(self) -> tuple[str, str, str]:
        return ("A", "B", "C")
