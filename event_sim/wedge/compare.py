"""
One slice, one config, three runs.

The commercial claim is controlled comparison: same business, same assumptions, same model,
different decision. That is enforced structurally here rather than promised in prose — every
world is built from the same slice object and the same SimulationConfig, and only the events
and interventions differ. `shared_fingerprint` hashes exactly the parts that must not differ,
so a test can assert they did not.
"""

from __future__ import annotations

import copy as copy_module
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from event_sim.engine import EventSimulation, SimulationConfig, build_simulation
from event_sim.freeze import module_hash
from event_sim.schemas import WorldSlice
from event_sim.world_builder import build_slice

from event_sim.wedge.accounting import Ledger, build_ledger, decision_metrics
from event_sim.wedge.spec import WedgeSpec, WorldSpec


@dataclass
class WorldResult:
    spec: WorldSpec
    sim: EventSimulation
    ledger: Ledger
    metrics: dict[str, Any]
    fingerprint: str
    trajectory_fingerprint: str = ""
    index_vars: tuple[str, ...] = ()

    def indices(self) -> dict[str, list[float]]:
        return {name: self.sim.series(name) for name in self.index_vars}


@dataclass
class Comparison:
    baseline: Any
    axis_settings: dict[str, str]
    knobs: dict[str, float]
    custom_elasticity: float | None
    wedge_id: str = ""
    module_id: str = ""
    horizon_days: int = 90
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
            "wedge_id": self.wedge_id,
            "module_id": self.module_id,
            "module_semantic_hash": self.module_semantic_hash,
            "horizon_days": self.horizon_days,
            "axis_settings": dict(self.axis_settings),
            "lag_setting": "central",
            "knobs": dict(self.knobs),
            # Also spread flat: a wedge's knob is part of how its report reads, and readers
            # written against a single wedge look for it by name.
            **{k: v for k, v in self.knobs.items()},
            "custom_elasticity": self.custom_elasticity,
            "baseline": self.baseline.to_dict(),
            "shared_fingerprint": self.shared_fingerprint,
            "worlds": [
                {"spec": w.spec.to_dict(), "engine_fingerprint": w.fingerprint,
                 "trajectory_fingerprint": w.trajectory_fingerprint}
                for w in self.worlds
            ],
        }


def wedge_slice(wedge: WedgeSpec, custom_elasticity: float | None) -> WorldSlice:
    """The shared slice. A custom elasticity is applied in memory only, never to disk."""
    s = build_slice([wedge.module_id], question=wedge.slice_question)
    if custom_elasticity is not None:
        s = copy_module.deepcopy(s)
        for e in s.edges:
            if e.id == wedge.elasticity_edge:
                val = abs(float(custom_elasticity))
                e.effect.low = e.effect.central = e.effect.high = val
                e.status = "user_assumption"
    return s


def shared_fingerprint(slice_: WorldSlice, cfg: SimulationConfig) -> str:
    """Hash of everything the three worlds must share. Events/interventions excluded."""
    payload = {
        "slice": _trajectory_slice(slice_),
        "config": cfg.to_dict(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _trajectory_slice(slice_: WorldSlice) -> list[dict[str, Any]]:
    """The parts of a slice that actually determine a trajectory."""
    return ([v.to_dict() for v in slice_.variables]
            + [e.to_dict() for e in slice_.edges]
            + [a.to_dict() for a in slice_.axes])


def trajectory_fingerprint(slice_: WorldSlice, cfg: SimulationConfig,
                           events: Any, interventions: Any) -> str:
    """
    Hash of everything that determines ONE world's trajectory — and nothing else.

    The engine's own `EventSimulation.fingerprint()` hashes the whole slice dict, which
    includes `excluded_systems`: a list of every other module present in the repository. That
    makes it change when an unrelated module is added, even though no coefficient, lag,
    variable, event or intervention moved. Adding the shop and salon modules did exactly that
    to the cafe's engine fingerprints, while its module hash, its shared fingerprint and every
    one of its numbers stayed identical.

    The engine's fingerprint is deliberately left alone — it is frozen scientific
    infrastructure, and its behaviour is conservative in the safe direction: it can report a
    difference that does not exist, never an equivalence that does not. This is the companion
    figure a report can be checked against across repository states.
    """
    payload = {
        "slice": _trajectory_slice(slice_),
        "config": cfg.to_dict(),
        "events": [e.to_dict() for e in events],
        "interventions": [i.to_dict() for i in interventions],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run_comparison(
    wedge: WedgeSpec,
    baseline: Any,
    *,
    axis_settings: dict[str, str] | None = None,
    custom_elasticity: float | None = None,
    **knobs: float,
) -> Comparison:
    problems = baseline.validate()
    if problems:
        raise ValueError("; ".join(problems))

    resolved = dict(wedge.knob_defaults)
    resolved.update({k: v for k, v in knobs.items() if v is not None})

    slice_ = wedge_slice(wedge, custom_elasticity)
    axes = dict(wedge.default_axes)
    axes.update(axis_settings or {})
    cfg = SimulationConfig(turns=wedge.horizon_days, axis_settings=axes,
                           lag_setting="central", label=wedge.id)

    comparison = Comparison(
        baseline=baseline,
        axis_settings=axes,
        knobs=resolved,
        custom_elasticity=custom_elasticity,
        wedge_id=wedge.id,
        module_id=wedge.module_id,
        horizon_days=wedge.horizon_days,
        module_semantic_hash=module_hash(wedge.module_id),
        shared_fingerprint=shared_fingerprint(slice_, cfg),
    )

    capacity = wedge.capacity_per_day(baseline, **resolved) if wedge.capacity_per_day else None

    for spec in wedge.build_worlds(slice_, baseline, **resolved):
        sim = build_simulation(slice_, config=cfg, events=spec.events, interventions=spec.interventions)
        sim.run()
        ledger = build_ledger(
            baseline,
            demand_index=sim.series(wedge.demand_var),
            price_index=sim.series(wedge.price_var),
            cogs_index=sim.series(wedge.unit_cost_var),
            capacity_per_day=capacity,
        )
        comparison.worlds.append(WorldResult(
            spec=spec,
            sim=sim,
            ledger=ledger,
            metrics=decision_metrics(ledger, baseline, horizon=wedge.horizon_days),
            fingerprint=sim.fingerprint(),
            trajectory_fingerprint=trajectory_fingerprint(slice_, cfg, spec.events, spec.interventions),
            index_vars=wedge.index_vars,
        ))
    return comparison
