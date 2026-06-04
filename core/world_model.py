"""
WorldModel: composite state with causal variable graph (variables, causal_links), entities, relations,
narrative, ontology, version, turn. apply_delta applies numeric_updates then propagates along causal_links;
snapshot/load_snapshot expose both variables and global_state (alias) for backward compatibility.
"""

from __future__ import annotations

import random
from typing import Any

from schemas.delta_schema import Delta

try:
    from config.settings import ENABLE_UNCERTAINTY
except ImportError:
    ENABLE_UNCERTAINTY = False

try:
    from core.physics_core import apply_delta_deterministic
except ImportError:
    apply_delta_deterministic = None  # type: ignore[misc, assignment]
try:
    from world.delayed_events import DelayedEvent, apply_delayed_events_for_turn
except ImportError:
    DelayedEvent = None  # type: ignore[misc, assignment]
    apply_delayed_events_for_turn = None  # type: ignore[misc, assignment]
try:
    from core.event_queue import process_events_for_turn
except ImportError:
    process_events_for_turn = None  # type: ignore[misc, assignment]
try:
    from model.valuespec import clamp_state_to_specs
except ImportError:
    clamp_state_to_specs = None  # type: ignore[misc, assignment]


def _get_prop_decay() -> float:
    try:
        from config.settings import PROPAGATION_DECAY_FACTOR
        return PROPAGATION_DECAY_FACTOR
    except ImportError:
        return 1.0


def _get_prop_sig() -> float:
    try:
        from config.settings import PROPAGATION_SIGNIFICANCE_THRESHOLD
        return PROPAGATION_SIGNIFICANCE_THRESHOLD
    except ImportError:
        return 1e-6


def _ensure_float_dict(d: dict[str, Any] | None) -> dict[str, float]:
    """Coerce values to float for variables; non-numeric keys skipped."""
    out: dict[str, float] = {}
    if not d:
        return out
    for k, v in d.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def _identify_primary_variable(
    action_type: str | None,
    delta: Delta,
    numeric_updates: dict[str, float],
) -> str | None:
    """
    Identify primary variable from action_type or Delta.
    - For increase_X/decrease_X patterns: extract X as primary
    - For other action types: use largest magnitude variable in numeric_updates
    - If delta has primary_variable set, use that
    """
    # Check if delta explicitly specifies primary variable
    if delta.primary_variable:
        return delta.primary_variable
    
    # Try to extract from action_type
    if action_type:
        at = action_type.strip()
        if at.startswith("increase_"):
            var = at[len("increase_"):].strip()
            if var and var in numeric_updates:
                return var
        elif at.startswith("decrease_"):
            var = at[len("decrease_"):].strip()
            if var and var in numeric_updates:
                return var
    
    # Fallback: use largest magnitude variable
    if numeric_updates:
        return max(numeric_updates.items(), key=lambda x: abs(x[1]))[0]
    
    return None


class WorldModel:
    """Composite world state: variables (causal graph), causal_links, entities, relations, narrative, ontology, version, turn, delayed_events. global_state in snapshot is alias of variables."""

    def __init__(
        self,
        *,
        entities: dict[str, dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        global_state: dict[str, Any] | None = None,
        variables: dict[str, float] | None = None,
        causal_links: list[dict[str, Any]] | None = None,
        narrative: list[str] | None = None,
        ontology: dict[str, Any] | None = None,
        version: int = 0,
        turn: int = 0,
        delayed_events: list[Any] | None = None,
        events: list[dict[str, Any]] | None = None,
    ):
        self.entities = dict(entities or {})
        self.relations = list(relations or [])
        # Primary store: variables (causal variable graph). Accept either variables or global_state for backward compat.
        if variables is not None:
            self.variables = _ensure_float_dict(variables)
        else:
            self.variables = _ensure_float_dict(global_state or {})
        self.causal_links = list(causal_links or [])
        self.narrative = list(narrative or [])
        self.ontology = dict(ontology or {})
        self.version = version
        self.turn = turn
        self.delayed_events: list[Any] = list(delayed_events or [])
        self.events: list[dict[str, Any]] = list(events or [])

    @property
    def global_state(self) -> dict[str, Any]:
        """Backward compatibility: same as variables so existing readers (governance, agents) keep working."""
        return self.variables

    def _apply_final_noise(
        self,
        primary_variable: str | None,
        primary_delta: float | None,
        all_changes: dict[str, float],
    ) -> dict[str, float]:
        """
        Apply Gaussian noise as final stage after deterministic + propagation.
        Noise magnitude must be < 20% of primary delta.
        Returns noise component dictionary for logging.
        """
        noise_component: dict[str, float] = {}
        
        if not ENABLE_UNCERTAINTY or not primary_variable or primary_delta is None:
            return noise_component
        
        primary_delta_abs = abs(primary_delta)
        max_noise_magnitude = primary_delta_abs * 0.2  # 20% constraint
        
        for var, delta in all_changes.items():
            if not isinstance(delta, (int, float)):
                continue
            
            # Calculate volatility scale (simple: use 10% of current value or 1.0)
            current_val = abs(self.variables.get(var, 0.0))
            volatility_scale = max(1.0, current_val * 0.1) if current_val > 0 else 1.0
            
            # Generate noise with constraint
            noise = random.gauss(0, volatility_scale)
            noise = max(-max_noise_magnitude, min(max_noise_magnitude, noise))
            
            # Apply noise
            self.variables[var] = self.variables.get(var, 0.0) + noise
            noise_component[var] = noise
        
        return noise_component

    def apply_delta(
        self,
        delta: Delta,
        action_type: str | None = None,
        *,
        variable_specs: dict[str, dict[str, Any]] | None = None,
        propagation_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Apply a validated Delta with structured causal mapping:
        1. Identify primary variable
        2. Apply primary effect first
        3. Apply deterministic propagation (structural causal_links only, damping, epsilon)
        4. Apply noise at final stage
        5. Return structured outcome with primary_effect, secondary_effects, noise_component, propagation_trace
        
        Returns structured outcome dict with:
        - primary_effect: {"var": str, "delta": float, "source": "direct"}
        - secondary_effects: [{"var": str, "delta": float, "source": "propagation"}, ...]
        - noise_component: {"var": str, "noise": float, ...}
        - variable_changes: [...] (backward compat)
        - propagation_trace: [...] (iter, from, to, weight, delta_source, delta_contrib)
        """
        # Extract numeric updates
        direct_changes: dict[str, float] = {}
        for key, value in (delta.numeric_updates or {}).items():
            if isinstance(value, (int, float)):
                direct_changes[key] = float(value)

        # Optional granularity cap: keep only top-K variables by magnitude to reduce compute
        try:
            from config.settings import DELTA_APPLY_GRANULARITY
            cap = DELTA_APPLY_GRANULARITY
        except ImportError:
            cap = None
        if cap is not None and isinstance(cap, int) and cap > 0 and len(direct_changes) > cap:
            top_keys = sorted(direct_changes.keys(), key=lambda k: abs(direct_changes[k]), reverse=True)[:cap]
            direct_changes = {k: direct_changes[k] for k in top_keys}

        primary_variable = _identify_primary_variable(
            action_type or delta.action_type,
            delta,
            direct_changes,
        )

        primary_effect: dict[str, Any] | None = None
        secondary_effects: list[dict[str, Any]] = []
        noise_component: dict[str, float] = {}
        variable_changes: list[dict[str, Any]] = []
        propagation_trace: list[dict[str, Any]] = []

        # Step 1: Deterministic physics via unified core (pre-update snapshot, no noise)
        if direct_changes and apply_delta_deterministic is not None:
            snapshot = {
                "variables": dict(self.variables),
                "global_state": dict(self.variables),
            }
            result = apply_delta_deterministic(
                snapshot,
                delta,
                list(self.causal_links),
                variable_specs=variable_specs,
                action_type=action_type or delta.action_type,
                propagation_params=propagation_params,
            )
            new_vars = result.get("variables") or result.get("global_state") or {}
            propagation_trace = result.get("propagation_trace") or []
            prev_vars = snapshot["variables"]
            self.variables.update(new_vars)

            for var, new_val in new_vars.items():
                if not isinstance(new_val, (int, float)):
                    continue
                prev_val = prev_vars.get(var, 0)
                if not isinstance(prev_val, (int, float)):
                    prev_val = 0.0
                delta_val = float(new_val) - float(prev_val)
                if abs(delta_val) < 1e-12:
                    continue
                entry = {"var": var, "delta": delta_val, "source": "propagation" if var != primary_variable else "direct"}
                variable_changes.append(entry)
                if var == primary_variable:
                    primary_effect = {"var": var, "delta": delta_val, "source": "direct"}
                else:
                    secondary_effects.append({"var": var, "delta": delta_val, "source": "propagation"})
            if primary_variable and not primary_effect and primary_variable in new_vars:
                pv = new_vars[primary_variable]
                pprev = prev_vars.get(primary_variable, 0)
                primary_effect = {"var": primary_variable, "delta": float(pv) - float(pprev), "source": "direct"}
        elif direct_changes:
            # Fallback when physics_core not available
            primary_variable = primary_variable or (max(direct_changes.items(), key=lambda x: abs(x[1]))[0] if direct_changes else None)
            for key, val in direct_changes.items():
                current = self.variables.get(key, 0)
                if isinstance(current, (int, float)):
                    self.variables[key] = current + val
                else:
                    self.variables[key] = val
                src = "direct" if key == primary_variable else "direct"
                variable_changes.append({"var": key, "delta": float(val), "source": src})
                if key == primary_variable:
                    primary_effect = {"var": key, "delta": float(val), "source": "direct"}
                else:
                    secondary_effects.append({"var": key, "delta": float(val), "source": src})

        # Step 2: Apply noise at final stage (after deterministic physics)
        all_changed_vars = {e["var"]: e["delta"] for e in variable_changes}
        if primary_variable and primary_effect and ENABLE_UNCERTAINTY:
            primary_delta_val = primary_effect["delta"]
            noise_component = self._apply_final_noise(
                primary_variable,
                primary_delta_val,
                all_changed_vars,
            )
            for var, noise_val in noise_component.items():
                self.variables[var] = self.variables.get(var, 0.0) + noise_val
                variable_changes.append({"var": var, "delta": float(noise_val), "source": "noise"})

        # Mandatory post-propagation/drift clamp: no variable may violate bounds
        if variable_specs and clamp_state_to_specs is not None:
            self.variables = clamp_state_to_specs(dict(self.variables), variable_specs)

        # Entity updates (patch existing) and new entities - gated by DELTA_APPLY_ENTITIES
        try:
            from config.settings import DELTA_APPLY_ENTITIES
            apply_entities = DELTA_APPLY_ENTITIES
        except ImportError:
            apply_entities = True
        if apply_entities:
            for eid, attrs in (delta.entity_updates or {}).items():
                if eid in self.entities:
                    self.entities[eid].update(attrs)
                else:
                    self.entities[eid] = dict(attrs)
            for eid, entity in (delta.new_entities or {}).items():
                self.entities[eid] = dict(entity)

        # Relation updates - gated by DELTA_APPLY_RELATIONS
        try:
            from config.settings import DELTA_APPLY_RELATIONS
            apply_relations = DELTA_APPLY_RELATIONS
        except ImportError:
            apply_relations = True
        if apply_relations:
            for rel in (delta.relation_updates or []):
                self.relations.append(dict(rel))

        if delta.rationale:
            self.narrative.append(f"[v{self.version}] {delta.rationale}")
        self.version += 1

        outcome = {
            "primary_effect": primary_effect,
            "secondary_effects": secondary_effects,
            "noise_component": noise_component,
            "variable_changes": variable_changes,
            "propagation_trace": propagation_trace,
        }
        try:
            from core.propagation import primary_propagation_check
            ok, msg = primary_propagation_check(self, outcome, primary_variable=primary_variable)
            if not ok:
                outcome["propagation_check"] = {"ok": False, "message": msg}
            else:
                outcome["propagation_check"] = {"ok": True}
        except ImportError:
            outcome["propagation_check"] = {"ok": True}
        return outcome

    def process_delayed_events(self) -> list[dict[str, Any]]:
        """Apply delayed events and generic event_queue for current turn. Returns list of triggered event records for trace."""
        triggered: list[dict[str, Any]] = []
        if apply_delayed_events_for_turn is not None and DelayedEvent is not None:
            applied_delayed = apply_delayed_events_for_turn(self, self.turn, self.delayed_events)
            for e in applied_delayed:
                triggered.append({
                    "trigger_turn": self.turn,
                    "event_type": "apply_delta",
                    "origin": getattr(e, "source_action", ""),
                    "metadata": {"source": "delayed_event"},
                })
        if process_events_for_turn is not None:
            triggered.extend(process_events_for_turn(self, self.turn, self.events))
        return triggered

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-serializable copy of full world state. Exposes variables and global_state (alias) for backward compat."""
        gs = dict(self.variables)
        out = {
            "entities": {k: dict(v) for k, v in self.entities.items()},
            "relations": [dict(r) for r in self.relations],
            "variables": dict(self.variables),
            "global_state": gs,
            "causal_links": [dict(l) for l in self.causal_links],
            "narrative": list(self.narrative),
            "ontology": dict(self.ontology),
            "version": self.version,
            "turn": self.turn,
        }
        if self.delayed_events and DelayedEvent is not None:
            out["delayed_events"] = [
                e.to_dict() if hasattr(e, "to_dict") else e for e in self.delayed_events
            ]
        out["events"] = list(self.events)
        return out

    def load_snapshot(self, d: dict[str, Any]) -> None:
        """Restore state from a snapshot dict. Accepts variables or global_state (backward compat)."""
        self.entities = {k: dict(v) for k, v in (d.get("entities") or {}).items()}
        self.relations = [dict(r) for r in (d.get("relations") or [])]
        self.variables = _ensure_float_dict(d.get("variables") or d.get("global_state") or {})
        self.causal_links = list(d.get("causal_links") or [])
        self.narrative = list(d.get("narrative") or [])
        self.ontology = dict(d.get("ontology") or {})
        self.version = int(d.get("version", 0))
        self.turn = int(d.get("turn", 0))
        if DelayedEvent is not None and d.get("delayed_events"):
            self.delayed_events = [DelayedEvent.from_dict(e) for e in d["delayed_events"]]
        else:
            self.delayed_events = []
        self.events = list(d.get("events") or [])
