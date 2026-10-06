"""
Event Simulator engine: deterministic, lag-aware evolution of a WorldSlice.

Reused from the existing engine (no duplication):
  - core.world_model.WorldModel        state container + snapshot()/load_snapshot()
  - simulation.checkpoints.CheckpointStore   branching and rollback
  - schemas.provenance.TransitionProvenance / EffectRecord   per-turn provenance
  - model.valuespec.clamp_state_to_specs     bounds enforcement

Why this module does not call core/propagation.py: that function propagates a *delta*
across the whole graph within one turn and ignores edge `delay`. An event cascade needs
the opposite — one hop per turn, each edge firing after its own lag. See
docs/EVENT_SIMULATOR_ARCHITECTURE.md §3.

The evolution rule (deviations from baseline, dev = (value - baseline) / scale):

    pressure(v, t)  = Σ  coef(e) · dev(source(e), t − lag(e))     over edges e → v
    dev(v, t+1)     = dev(v, t) + response(v) · (pressure(v, t) − dev(v, t))

with two overrides applied in order:
  - an active *event* holds its targets at the injected displacement (the event is a
    stated fact about the world, not a pressure to be relaxed toward);
  - an active *intervention* adds an offset on top.

No randomness is drawn anywhere in this module. Reproducibility does not depend on RNG
discipline: the same slice + config + events + interventions produce byte-identical
trajectories on any machine.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from core.world_model import WorldModel
from model.valuespec import clamp_state_to_specs
from schemas.provenance import EffectRecord, TransitionProvenance
from simulation.checkpoints import CheckpointStore

from event_sim.schemas import (
    AssumptionAxis,
    CausalEdgeEvidence,
    EventDefinition,
    WorldSlice,
)

#: Contributions below this magnitude (in deviation units) are recorded but flagged
#: negligible, so the causal trace stays readable.
NEGLIGIBLE_CONTRIBUTION = 1e-9


@dataclass
class Intervention:
    """
    A lever applied by the engine. Actors (human or agent) choose an intervention id and a
    magnitude; they never write a variable and never supply an effect size — the effect
    per unit comes from the world module, where it carries an evidence status.
    """

    id: str
    magnitude: float = 1.0
    start_turn: int = 1
    duration: int = 1
    effects_per_unit: dict[str, float] = field(default_factory=dict)
    label: str = ""
    status: str = "expert_assumption"

    def active_at(self, turn: int) -> bool:
        return self.start_turn <= turn < self.start_turn + max(1, self.duration)

    def offsets_at(self, turn: int) -> dict[str, float]:
        if not self.active_at(turn):
            return {}
        return {k: float(v) * float(self.magnitude) for k, v in self.effects_per_unit.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "magnitude": self.magnitude,
            "start_turn": self.start_turn,
            "duration": self.duration,
            "effects_per_unit": dict(self.effects_per_unit),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Intervention:
        return cls(
            id=str(d.get("id") or "intervention"),
            magnitude=float(d.get("magnitude", 1.0)),
            start_turn=int(d.get("start_turn", 1)),
            duration=int(d.get("duration", 1)),
            effects_per_unit={str(k): float(v) for k, v in (d.get("effects_per_unit") or {}).items()},
            label=str(d.get("label") or d.get("id") or ""),
            status=str(d.get("status") or "expert_assumption"),
        )

    @classmethod
    def from_slice(
        cls,
        slice_: WorldSlice,
        intervention_id: str,
        *,
        magnitude: float | None = None,
        start_turn: int | None = None,
        duration: int | None = None,
    ) -> Intervention:
        """Instantiate a library-defined intervention, overriding only its parameters."""
        for spec in slice_.interventions:
            if spec.get("id") == intervention_id:
                return cls(
                    id=intervention_id,
                    label=str(spec.get("label") or intervention_id),
                    magnitude=float(magnitude if magnitude is not None else spec.get("default_magnitude", 1.0)),
                    start_turn=int(start_turn if start_turn is not None else spec.get("default_start_turn", 1)),
                    duration=int(duration if duration is not None else spec.get("default_duration", 1)),
                    effects_per_unit={
                        str(k): float(v) for k, v in (spec.get("effects_per_unit") or {}).items()
                    },
                    status=str(spec.get("status") or "expert_assumption"),
                )
        raise KeyError(
            f"Intervention {intervention_id!r} is not defined in slice {slice_.id!r}. "
            f"Available: {[i.get('id') for i in slice_.interventions]}"
        )


@dataclass
class SimulationConfig:
    """
    One fully specified world. `axis_settings` names a point on every uncertain assumption
    axis, which is what makes a swept world attributable ("this trajectory needs slow
    recovery AND no alternative capacity") rather than an anonymous ensemble member.
    """

    turns: int = 12
    axis_settings: dict[str, str] = field(default_factory=dict)
    lag_setting: str = "central"  # low = fastest transmission, high = slowest
    label: str = "baseline"
    seed: int = 0  # recorded for reproducibility contracts; the engine draws no randomness

    def to_dict(self) -> dict[str, Any]:
        return {
            "turns": self.turns,
            "axis_settings": dict(self.axis_settings),
            "lag_setting": self.lag_setting,
            "label": self.label,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SimulationConfig:
        return cls(
            turns=int(d.get("turns", 12)),
            axis_settings={str(k): str(v) for k, v in (d.get("axis_settings") or {}).items()},
            lag_setting=str(d.get("lag_setting") or "central"),
            label=str(d.get("label") or "baseline"),
            seed=int(d.get("seed", 0)),
        )


class EventSimulation:
    """
    One world: a slice, a configuration, injected events, applied interventions, and the
    trajectory that follows. Branching is done with `fork()`, which restores a checkpoint
    so two branches provably start from the same state.
    """

    def __init__(
        self,
        slice_: WorldSlice,
        config: SimulationConfig | None = None,
        *,
        events: Sequence[EventDefinition] | None = None,
        interventions: Sequence[Intervention] | None = None,
        branch_id: str = "root",
        parent_id: str | None = None,
        fork_turn: int = 0,
    ) -> None:
        self.slice = slice_
        self.config = config or SimulationConfig()
        self.events: list[EventDefinition] = list(events or [])
        self.interventions: list[Intervention] = list(interventions or [])
        self.branch_id = branch_id
        self.parent_id = parent_id
        self.fork_turn = fork_turn

        self._specs = slice_.variable_specs()
        self._axes: dict[str, AssumptionAxis] = {a.id: a for a in slice_.axes}
        self._edges_by_target: dict[str, list[CausalEdgeEvidence]] = {}
        for edge in slice_.edges:
            self._edges_by_target.setdefault(edge.target, []).append(edge)

        # causal_links is deliberately empty: WorldModel.apply_delta's same-turn
        # propagation must not double-count this engine's lagged propagation.
        self.world = WorldModel(
            variables=slice_.baseline_state(),
            causal_links=[],
            events=[e for ev in self.events for e in ev.to_engine_events()],
            turn=0,
        )
        self.checkpoints = CheckpointStore(max_count=max(8, self.config.turns + 2))

        self.provenance: list[dict[str, Any]] = []
        self.trajectory: list[dict[str, Any]] = []
        # Two histories, deliberately separate:
        #   _dev_history  — observed deviation, what causal edges read and the trace reports
        #   _endo_history — endogenous deviation, what relaxation acts on
        # An exogenous offset (an active intervention) contributes to the observed value
        # but must NOT be folded into the state that relaxes, or it would be re-added every
        # turn and ratchet the variable upward.
        self._dev_history: list[dict[str, float]] = [self._deviations(self.world.variables)]
        self._endo_history: list[dict[str, float]] = [dict(self._dev_history[0])]
        self._record_turn_state(turn=0, note="baseline")
        self._checkpoint()

    # -- resolution of assumption settings ------------------------------------------------

    def effect_setting_for_edge(self, edge: CausalEdgeEvidence) -> str:
        """Which point of the edge's evidenced effect range this world uses."""
        if edge.axis and edge.axis in self._axes:
            axis = self._axes[edge.axis]
            setting = self.config.axis_settings.get(axis.id, axis.default_setting())
            return axis.effect_setting(setting)
        for axis in self._axes.values():
            if edge.id in axis.applies_to:
                setting = self.config.axis_settings.get(axis.id, axis.default_setting())
                return axis.effect_setting(setting)
        return "central"

    def response_for_variable(self, var_id: str) -> float:
        """Per-turn response rate, after any assumption axis bound to this variable."""
        var = self.slice.variable(var_id)
        if var is None:
            return 0.0
        multiplier = 1.0
        for axis in self._axes.values():
            if var_id in axis.applies_to or var.axis == axis.id:
                setting = self.config.axis_settings.get(axis.id, axis.default_setting())
                multiplier *= axis.response_multiplier(setting)
        return max(0.0, min(1.0, var.response * multiplier))

    # -- deviation space ------------------------------------------------------------------

    def _deviations(self, values: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for var in self.slice.variables:
            value = float(values.get(var.id, var.baseline))
            out[var.id] = (value - var.baseline) / var.scale
        return out

    def _values(self, devs: dict[str, float]) -> dict[str, float]:
        return {
            v.id: v.baseline + v.scale * float(devs.get(v.id, 0.0))
            for v in self.slice.variables
        }

    # -- H1 experimental: stock (conservation) variables ------------------------------------

    def surge_for_variable(self, var: Any) -> float:
        """
        Processing headroom above nominal capacity while a queue exists, from the assumption
        axis bound to the stock (if any). A port clearing a backlog can work above its
        nominal weekly rate — overtime, extra gangs, extended windows.
        """
        axis_id = (var.stock or {}).get("surge_axis")
        default = float((var.stock or {}).get("surge", 1.0))
        if not axis_id or axis_id not in self._axes:
            return default
        axis = self._axes[axis_id]
        setting = self.config.axis_settings.get(axis_id, axis.default_setting())
        value = (axis.mapping.get(setting) or {}).get("surge")
        return float(value) if isinstance(value, (int, float)) else default

    def _step_stock(self, var: Any, previous_level: float) -> dict[str, float]:
        """
        Conservation update for a stock variable (H1).

            processed(t)  = min(queue(t) + arrivals(t), processing_capacity(t))
            queue(t+1)    = max(0, queue(t) + arrivals(t) - processed(t))

        Invariants this guarantees by construction:
          * the queue can never go negative;
          * it persists across turns — nothing clears it but processing;
          * restoring capacity does not delete it, it only raises the drain rate;
          * processing is bounded by capacity, so clearing is mechanically constrained.

        `processing_capacity` is read from another variable's current level (normally
        `port_capacity`), divided by `capacity_scale` to convert an index to normal-flow
        units, and multiplied by the surge headroom.
        """
        cfg = var.stock or {}
        arrivals = float(cfg.get("inflow", 1.0))
        capacity_variable = str(cfg.get("capacity_variable") or "")
        capacity_scale = float(cfg.get("capacity_scale", 100.0)) or 1.0

        raw_capacity = float(self.world.variables.get(capacity_variable, 0.0)) if capacity_variable else 0.0
        nominal = max(0.0, raw_capacity / capacity_scale)
        surge = self.surge_for_variable(var)
        capacity = nominal * surge

        available = max(0.0, previous_level) + arrivals
        processed = min(available, capacity)
        next_level = max(0.0, previous_level + arrivals - processed)
        return {
            "arrivals": arrivals,
            "nominal_capacity": nominal,
            "surge": surge,
            "processing_capacity": capacity,
            "processed": processed,
            "previous_level": previous_level,
            "next_level": next_level,
            "net_change": next_level - previous_level,
        }

    def _dev_at(self, var_id: str, turn: int) -> float:
        """Deviation of a variable at an earlier turn (0 before the run started)."""
        if turn < 0 or turn >= len(self._dev_history):
            return 0.0
        return float(self._dev_history[turn].get(var_id, 0.0))

    # -- evolution ------------------------------------------------------------------------

    def step(self) -> dict[str, Any]:
        """Advance one turn. Returns the turn record."""
        t = self.world.turn
        next_turn = t + 1
        current_endo = dict(self._endo_history[t])

        holds: dict[str, tuple[float, EventDefinition]] = {}
        for event in self.events:
            for var_id, magnitude in event.magnitude_at(next_turn).items():
                var = self.slice.variable(var_id)
                if var is None:
                    continue
                holds[var_id] = (magnitude / var.scale, event)

        offsets: dict[str, list[tuple[float, Intervention]]] = {}
        for iv in self.interventions:
            for var_id, magnitude in iv.offsets_at(next_turn).items():
                var = self.slice.variable(var_id)
                if var is None:
                    continue
                offsets.setdefault(var_id, []).append((magnitude / var.scale, iv))

        new_dev: dict[str, float] = {}
        new_endo: dict[str, float] = {}
        offset_by_var: dict[str, float] = {}
        contributions: dict[str, list[dict[str, Any]]] = {}
        effect_records: list[EffectRecord] = []
        stock_records: dict[str, dict[str, float]] = {}

        for var in self.slice.variables:
            vid = var.id
            pressure = 0.0
            var_contribs: list[dict[str, Any]] = []
            for edge in self._edges_by_target.get(vid, []):
                # A conservation edge is realised by the stock rule below, not by a linear
                # coefficient. It stays in the graph so evidence coverage still counts it and
                # the causal trace still shows it, but it must not also propagate linearly —
                # that would double-count the mechanism.
                if edge.mechanism_type == "conservation":
                    continue
                setting = self.effect_setting_for_edge(edge)
                coef = edge.coefficient(setting)
                lag = edge.lag.effective(self.config.lag_setting)
                source_turn = t - lag
                source_dev = self._dev_at(edge.source, source_turn)
                contribution = coef * source_dev
                pressure += contribution
                var_contribs.append({
                    "edge": edge.id,
                    "source": edge.source,
                    "target": vid,
                    "polarity": edge.polarity,
                    "coefficient": coef,
                    "effect_setting": setting,
                    "lag": lag,
                    "source_turn": max(0, source_turn),
                    "source_deviation": source_dev,
                    "contribution": contribution,
                    "evidence_status": edge.status,
                    "confidence": edge.confidence,
                    "axis": edge.axis,
                    "negligible": abs(contribution) < NEGLIGIBLE_CONTRIBUTION,
                })
                if abs(contribution) >= NEGLIGIBLE_CONTRIBUTION:
                    effect_records.append(EffectRecord(
                        source="delayed" if lag > 0 else "direct",
                        trigger_turn=next_turn,
                        origin_id=edge.id,
                        params_or_delta={
                            "contribution_deviation": contribution,
                            "coefficient": coef,
                            "effect_setting": setting,
                            "lag": lag,
                            "source_turn": max(0, source_turn),
                            "evidence_status": edge.status,
                        },
                        description=f"Causal edge {edge.id} ({edge.status})",
                    ))

            if var.kind == "stock":
                # H1: conservation instead of relaxation. The stock reads the CURRENT level
                # (not a deviation) so the accounting stays in the variable's own units.
                record = self._step_stock(var, float(self.world.variables.get(vid, var.baseline)))
                stock_records[vid] = record
                relaxed = (record["next_level"] - var.baseline) / var.scale
                response = 0.0
                effect_records.append(EffectRecord(
                    source="rule",
                    trigger_turn=next_turn,
                    origin_id=f"stock:{vid}",
                    params_or_delta=dict(record),
                    description=f"Conservation update for stock {vid}",
                ))
            else:
                response = self.response_for_variable(vid)
                endo = current_endo.get(vid, 0.0)
                relaxed = endo + response * (pressure - endo)

            held = vid in holds
            if held:
                hold_dev, event = holds[vid]
                base_dev = hold_dev
                effect_records.append(EffectRecord(
                    source="event",
                    trigger_turn=next_turn,
                    origin_id=event.id,
                    params_or_delta={
                        "variable": vid,
                        "displacement": hold_dev * var.scale,
                        "displacement_deviation": hold_dev,
                        "shape": event.shape,
                        "evidence_status": event.status,
                    },
                    description=f"Injected event {event.id} holds {vid}",
                ))
            else:
                base_dev = relaxed

            offset_total = 0.0
            for offset_dev, iv in offsets.get(vid, []):
                offset_total += offset_dev
                effect_records.append(EffectRecord(
                    source="direct",
                    trigger_turn=next_turn,
                    origin_id=iv.id,
                    params_or_delta={
                        "variable": vid,
                        "offset": offset_dev * var.scale,
                        "offset_deviation": offset_dev,
                        "magnitude": iv.magnitude,
                        "evidence_status": iv.status,
                    },
                    description=f"Intervention {iv.id} offsets {vid}",
                ))

            new_endo[vid] = base_dev
            offset_by_var[vid] = offset_total
            new_dev[vid] = base_dev + offset_total
            contributions[vid] = var_contribs

        pre_values = dict(self.world.variables)
        raw_values = self._values(new_dev)
        clamped_values = clamp_state_to_specs(dict(raw_values), self._specs)
        clamped_vars = sorted(
            v for v in raw_values
            if abs(float(clamped_values.get(v, 0.0)) - float(raw_values[v])) > 1e-12
        )
        # Clamping is authoritative: fold it back into deviation space so history stays
        # consistent with the values the trace reports. The exogenous offset is then
        # subtracted back out of the endogenous state, so an intervention holds its effect
        # steady rather than compounding it turn after turn.
        final_dev = self._deviations(clamped_values)
        final_endo = {vid: final_dev[vid] - offset_by_var.get(vid, 0.0) for vid in final_dev}

        self.world.variables = {k: float(v) for k, v in clamped_values.items()}
        self.world.turn = next_turn
        self.world.version += 1
        self._dev_history.append(final_dev)
        self._endo_history.append(final_endo)

        variable_records: list[dict[str, Any]] = []
        for var in self.slice.variables:
            vid = var.id
            variable_records.append({
                "variable": vid,
                "label": var.label,
                "unit": var.unit,
                "value": float(clamped_values[vid]),
                "previous_value": float(pre_values.get(vid, var.baseline)),
                "change": float(clamped_values[vid]) - float(pre_values.get(vid, var.baseline)),
                "deviation": final_dev[vid],
                "baseline": var.baseline,
                "response": self.response_for_variable(vid),
                "held_by_event": vid in holds,
                "intervention_offset": sum(o for o, _ in offsets.get(vid, [])) * var.scale,
                "clamped": vid in clamped_vars,
                "contributions": contributions.get(vid, []),
            })

        provenance = TransitionProvenance(
            proposed_delta={
                v["variable"]: v["change"] for v in variable_records if abs(v["change"]) > 1e-12
            },
            constrained_delta={
                v["variable"]: v["change"] for v in variable_records if abs(v["change"]) > 1e-12
            },
            propagation_trace=[c for recs in contributions.values() for c in recs if not c["negligible"]],
            events_fired=[
                e.to_dict() for e in self.events if e.magnitude_at(next_turn)
            ],
            final_variable_changes=[
                {"var": v["variable"], "delta": v["change"], "source": "event_sim"}
                for v in variable_records
                if abs(v["change"]) > 1e-12
            ],
            effect_records=effect_records,
        )

        turn_record: dict[str, Any] = {
            "turn": next_turn,
            "branch_id": self.branch_id,
            "time_unit": self.slice.time_unit,
            "state": {k: float(v) for k, v in clamped_values.items()},
            "variables": variable_records,
            "events_active": [e.id for e in self.events if e.magnitude_at(next_turn)],
            "interventions_active": [iv.id for iv in self.interventions if iv.active_at(next_turn)],
            "clamped_variables": clamped_vars,
        }
        if stock_records:
            turn_record["stocks"] = {k: dict(v) for k, v in stock_records.items()}
        self.trajectory.append(turn_record)
        self.provenance.append({
            "turn": next_turn,
            "branch_id": self.branch_id,
            "config": self.config.to_dict(),
            "transition": provenance.to_dict(),
            "contributions": contributions,
        })
        self._checkpoint()
        return turn_record

    def run(self, turns: int | None = None) -> dict[str, Any]:
        """Run to completion (or `turns` more turns) and return the run result."""
        target = self.config.turns if turns is None else self.world.turn + turns
        while self.world.turn < target:
            self.step()
        return self.result()

    # -- state, checkpoints, branching ------------------------------------------------------

    def _record_turn_state(self, *, turn: int, note: str) -> None:
        var_records = [
            {
                "variable": v.id,
                "label": v.label,
                "unit": v.unit,
                "value": float(self.world.variables.get(v.id, v.baseline)),
                "previous_value": float(self.world.variables.get(v.id, v.baseline)),
                "change": 0.0,
                "deviation": self._dev_history[-1].get(v.id, 0.0),
                "baseline": v.baseline,
                "response": self.response_for_variable(v.id),
                "held_by_event": False,
                "intervention_offset": 0.0,
                "clamped": False,
                "contributions": [],
            }
            for v in self.slice.variables
        ]
        self.trajectory.append({
            "turn": turn,
            "branch_id": self.branch_id,
            "time_unit": self.slice.time_unit,
            "state": {k: float(v) for k, v in self.world.variables.items()},
            "variables": var_records,
            "events_active": [],
            "interventions_active": [],
            "clamped_variables": [],
            "note": note,
        })

    def _checkpoint(self) -> None:
        """Push a checkpoint using the shared CheckpointStore (no second state store)."""
        snapshot = self.world.snapshot()
        snapshot["event_sim"] = {
            "dev_history": [dict(d) for d in self._dev_history],
            "endo_history": [dict(d) for d in self._endo_history],
            "config": self.config.to_dict(),
            "branch_id": self.branch_id,
        }
        self.checkpoints.push(
            self.world.turn,
            snapshot,
            copy.deepcopy(self.provenance),
            copy.deepcopy(self.trajectory),
        )

    def fork(
        self,
        turn: int,
        *,
        branch_id: str,
        label: str = "",
        interventions: Sequence[Intervention] | None = None,
        config: SimulationConfig | None = None,
    ) -> EventSimulation:
        """
        Create an independent branch from the checkpoint at `turn`.

        Both the parent and the branch continue from *identical* state — the branch is
        restored from the shared CheckpointStore, not re-simulated. The parent is not
        mutated in any way.
        """
        checkpoint = self.checkpoints.get_for_turn(turn)
        if checkpoint is None:
            raise ValueError(
                f"No checkpoint at turn {turn} (available: "
                f"{[c['turn'] for c in self.checkpoints._checkpoints]})"  # noqa: SLF001 - diagnostic only
            )
        snapshot = copy.deepcopy(checkpoint["snapshot"])
        extra = snapshot.pop("event_sim", {})

        branch_config = config or SimulationConfig(
            turns=self.config.turns,
            axis_settings=dict(self.config.axis_settings),
            lag_setting=self.config.lag_setting,
            label=label or branch_id,
            seed=self.config.seed,
        )
        branch = EventSimulation(
            self.slice,
            branch_config,
            events=[copy.deepcopy(e) for e in self.events],
            interventions=[copy.deepcopy(i) for i in self.interventions] + list(interventions or []),
            branch_id=branch_id,
            parent_id=self.branch_id,
            fork_turn=turn,
        )
        branch.world.load_snapshot(snapshot)
        branch._dev_history = [dict(d) for d in extra.get("dev_history", [])] or [
            branch._deviations(branch.world.variables)
        ]
        branch._endo_history = [dict(d) for d in extra.get("endo_history", [])] or [
            dict(branch._dev_history[-1])
        ]
        branch.provenance = copy.deepcopy(checkpoint.get("provenance_slice") or [])
        branch.trajectory = copy.deepcopy(checkpoint.get("action_trace_slice") or [])
        for record in branch.trajectory:
            record["forked_from"] = self.branch_id
        branch.checkpoints.clear()
        branch._checkpoint()
        return branch

    # -- output ---------------------------------------------------------------------------

    def fingerprint(self) -> str:
        """
        Stable hash of everything that determines the trajectory. Two runs with the same
        fingerprint must produce identical output; the reproducibility test asserts it.
        """
        payload = {
            "slice": self.slice.to_dict(),
            "config": self.config.to_dict(),
            "events": [e.to_dict() for e in self.events],
            "interventions": [i.to_dict() for i in self.interventions],
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def state(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.world.variables.items()}

    def series(self, variable: str) -> list[float]:
        """Value of one variable at every turn, index = turn."""
        return [float(rec["state"].get(variable, 0.0)) for rec in self.trajectory]

    def result(self) -> dict[str, Any]:
        """Full run result: framed as a trajectory under stated assumptions, not a forecast."""
        return {
            "branch_id": self.branch_id,
            "parent_id": self.parent_id,
            "fork_turn": self.fork_turn,
            "label": self.config.label,
            "fingerprint": self.fingerprint(),
            "config": self.config.to_dict(),
            "slice_id": self.slice.id,
            "time_unit": self.slice.time_unit,
            "turns": self.world.turn,
            "events": [e.to_dict() for e in self.events],
            "interventions": [i.to_dict() for i in self.interventions],
            "trajectory": copy.deepcopy(self.trajectory),
            "final_state": self.state(),
            "coverage": dict(self.slice.coverage),
            "framing": (
                "One trajectory under the stated assumptions. Not a prediction and not a "
                "probability: change an assumption setting and this trajectory changes."
            ),
        }


def build_simulation(
    slice_: WorldSlice,
    *,
    config: SimulationConfig | None = None,
    events: Sequence[EventDefinition] | None = None,
    interventions: Sequence[Intervention] | None = None,
) -> EventSimulation:
    """Convenience constructor with axis defaults filled in for any unset axis."""
    cfg = config or SimulationConfig()
    settings = dict(cfg.axis_settings)
    for axis in slice_.axes:
        settings.setdefault(axis.id, axis.default_setting())
    cfg = SimulationConfig(
        turns=cfg.turns,
        axis_settings=settings,
        lag_setting=cfg.lag_setting,
        label=cfg.label,
        seed=cfg.seed,
    )
    return EventSimulation(slice_, cfg, events=events, interventions=interventions)
