"""
Run the three worlds through the real engine and translate to business quantities.

One slice, one config, three runs. The reproducibility record stores everything needed to
regenerate each trajectory byte-for-byte: module id and semantic hash, axis settings, lag
setting, horizon, the event and intervention dicts, and the engine fingerprint.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from event_sim.engine import EventSimulation, SimulationConfig, build_simulation
from event_sim.freeze import module_hash
from event_sim.schemas import WorldSlice
from event_sim.world_builder import build_slice

from event_sim.cafe.accounting import Ledger, build_ledger, decision_metrics
from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.worlds import (
    HORIZON_DAYS,
    MODULE_ID,
    REFORMULATION_EFFECTIVENESS,
    WorldSpec,
    build_worlds,
)

DEFAULT_AXES: dict[str, str] = {
    "price_sensitivity": "central",
    "cogs_pass_through": "central",
    "demand_adjustment_speed": "central",
}


@dataclass
class WorldResult:
    spec: WorldSpec
    sim: EventSimulation
    ledger: Ledger
    metrics: dict[str, Any]
    fingerprint: str

    def indices(self) -> dict[str, list[float]]:
        return {
            "input_cost": self.sim.series("input_cost"),
            "cogs_per_order": self.sim.series("cogs_per_order"),
            "menu_price": self.sim.series("menu_price"),
            "demand": self.sim.series("demand"),
        }


@dataclass
class Comparison:
    baseline: CafeBaseline
    axis_settings: dict[str, str]
    reformulation_effectiveness: float
    custom_elasticity: float | None
    worlds: list[WorldResult] = field(default_factory=list)
    module_semantic_hash: str = ""
    shared_fingerprint: str = ""

    def by_id(self, world_id: str) -> WorldResult:
        for w in self.worlds:
            if w.spec.id == world_id:
                return w
        raise KeyError(world_id)

    def ranking(self, key: str = "cash_day_90") -> list[str]:
        """World ids, best first, on a metric where higher is better."""
        return [w.spec.id for w in sorted(self.worlds, key=lambda w: -w.metrics[key])]

    def net_benefit_vs_a(self, key: str = "cash_day_90") -> dict[str, float]:
        a = self.by_id("A").metrics[key]
        return {w.spec.id: w.metrics[key] - a for w in self.worlds}

    def reproducibility_record(self) -> dict[str, Any]:
        return {
            "module_id": MODULE_ID,
            "module_semantic_hash": self.module_semantic_hash,
            "horizon_days": HORIZON_DAYS,
            "axis_settings": dict(self.axis_settings),
            "lag_setting": "central",
            "reformulation_effectiveness": self.reformulation_effectiveness,
            "custom_elasticity": self.custom_elasticity,
            "baseline": self.baseline.to_dict(),
            "shared_fingerprint": self.shared_fingerprint,
            "worlds": [
                {"spec": w.spec.to_dict(), "engine_fingerprint": w.fingerprint}
                for w in self.worlds
            ],
        }


def _slice(custom_elasticity: float | None) -> WorldSlice:
    """The shared slice. A custom elasticity is applied in memory only, never to disk."""
    s = build_slice([MODULE_ID], question="Ingredient costs rose. Which response?")
    if custom_elasticity is not None:
        s = copy.deepcopy(s)
        for e in s.edges:
            if e.id == "menu_price->demand":
                val = abs(float(custom_elasticity))
                e.effect.low = e.effect.central = e.effect.high = val
                e.status = "user_assumption"
    return s


def _shared_fingerprint(slice_: WorldSlice, cfg: SimulationConfig) -> str:
    """Hash of everything the three worlds must share. Events/interventions excluded."""
    payload = {
        "slice": [v.to_dict() for v in slice_.variables]
        + [e.to_dict() for e in slice_.edges]
        + [a.to_dict() for a in slice_.axes],
        "config": cfg.to_dict(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run_comparison(
    baseline: CafeBaseline,
    *,
    axis_settings: dict[str, str] | None = None,
    reformulation_effectiveness: float = REFORMULATION_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> Comparison:
    problems = baseline.validate()
    if problems:
        raise ValueError("; ".join(problems))

    axes = {**DEFAULT_AXES, **(axis_settings or {})}
    slice_ = _slice(custom_elasticity)
    cfg = SimulationConfig(turns=HORIZON_DAYS, axis_settings=axes, lag_setting="central", label="cafe")
    specs = build_worlds(slice_, baseline, reformulation_effectiveness=reformulation_effectiveness)

    comp = Comparison(
        baseline=baseline,
        axis_settings=axes,
        reformulation_effectiveness=reformulation_effectiveness,
        custom_elasticity=custom_elasticity,
        module_semantic_hash=module_hash(MODULE_ID),
        shared_fingerprint=_shared_fingerprint(slice_, cfg),
    )

    for spec in specs:
        sim = build_simulation(slice_, config=cfg, events=spec.events, interventions=spec.interventions)
        sim.run()
        ledger = build_ledger(
            baseline,
            demand_index=sim.series("demand"),
            price_index=sim.series("menu_price"),
            cogs_index=sim.series("cogs_per_order"),
        )
        comp.worlds.append(
            WorldResult(
                spec=spec,
                sim=sim,
                ledger=ledger,
                metrics=decision_metrics(ledger, baseline, horizon=HORIZON_DAYS),
                fingerprint=sim.fingerprint(),
            )
        )
    return comp
