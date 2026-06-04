"""
WorldState: lightweight engine for cloning, applying deltas, and enforcing policy.
Used by planner for depth-2 simulation. Policy is configurable, not hard-coded.
"""

from __future__ import annotations

import copy
import random
from typing import Any

from schemas.delta_schema import Delta

from core.legacy_semantics import legacy_default_policy


# Default policy: from config/policy_default.json via legacy_semantics
DEFAULT_POLICY: dict[str, Any] = legacy_default_policy()


class DeltaValidationError(Exception):
    """Raised when a delta violates policy. Caller must handle; no auto-repair."""

    def __init__(self, message: str, delta: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.delta = delta


def load_policy_from_config(path: str | None = None) -> dict[str, Any]:
    """Load policy from config/policy_default.json. Returns DEFAULT_POLICY on failure."""
    from pathlib import Path
    import json
    if path is None:
        base = Path(__file__).resolve().parent.parent
        path = base / "config" / "policy_default.json"
    p = Path(path)
    if p.is_file():
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {**DEFAULT_POLICY, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_POLICY)


def _ensure_float_dict(d: dict[str, Any] | None) -> dict[str, float]:
    """Coerce values to float for variables."""
    out: dict[str, float] = {}
    if not d:
        return out
    for k, v in d.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


class WorldState:
    """
    Lightweight world state for planner simulation.
    clone(), apply_delta(), apply_event(), get_variable(), to_snapshot().
    Policy module: configurable protected_keys, caps, max_magnitude.
    """

    def __init__(
        self,
        *,
        entities: dict[str, dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        global_state: dict[str, Any] | None = None,
        variables: dict[str, float] | None = None,
        narrative: list[str] | None = None,
        ontology: dict[str, Any] | None = None,
        version: int = 0,
        turn: int = 0,
        policy: dict[str, Any] | None = None,
    ) -> None:
        self.entities = dict(entities or {})
        self.relations = list(relations or [])
        if variables is not None:
            self.variables = _ensure_float_dict(variables)
        else:
            self.variables = _ensure_float_dict(global_state or {})
        self.narrative = list(narrative or [])
        self.ontology = dict(ontology or {})
        self.version = version
        self.turn = turn
        self.policy = dict(policy or DEFAULT_POLICY)

    def clone(self) -> WorldState:
        """Return a deep copy of this WorldState."""
        return WorldState(
            entities=copy.deepcopy(self.entities),
            relations=copy.deepcopy(self.relations),
            variables=copy.deepcopy(self.variables),
            narrative=copy.deepcopy(self.narrative),
            ontology=copy.deepcopy(self.ontology),
            version=self.version,
            turn=self.turn,
            policy=copy.deepcopy(self.policy),
        )

    def get_variable(self, key: str) -> float | None:
        """Get variable value by key."""
        if key in self.variables:
            val = self.variables[key]
            if isinstance(val, (int, float)):
                return float(val)
        return None

    def to_snapshot(self) -> dict[str, Any]:
        """Return JSON-serializable copy of world state (compatible with WorldModel.snapshot shape)."""
        return {
            "entities": {k: dict(v) for k, v in self.entities.items()},
            "relations": [dict(r) for r in self.relations],
            "variables": dict(self.variables),
            "global_state": dict(self.variables),
            "narrative": list(self.narrative),
            "ontology": dict(self.ontology),
            "version": self.version,
            "turn": self.turn,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any], *, policy: dict[str, Any] | None = None) -> WorldState:
        """Build WorldState from a snapshot dict (e.g. from WorldModel.snapshot())."""
        variables = snapshot.get("variables") or snapshot.get("global_state") or {}
        return cls(
            entities=dict(snapshot.get("entities") or {}),
            relations=list(snapshot.get("relations") or []),
            variables=_ensure_float_dict(variables),
            narrative=list(snapshot.get("narrative") or []),
            ontology=dict(snapshot.get("ontology") or {}),
            version=int(snapshot.get("version", 0)),
            turn=int(snapshot.get("turn", 0)),
            policy=policy,
        )

    def _check_policy(self, delta: dict[str, Any]) -> None:
        """
        Check delta against policy. Raise DeltaValidationError if violated.
        No auto-repair; caller must handle.
        """
        numeric = delta.get("numeric_updates") or {}
        if not isinstance(numeric, dict):
            raise DeltaValidationError("numeric_updates must be dict", delta)

        protected = set(self.policy.get("protected_keys") or [])
        caps = self.policy.get("caps") or {}
        max_mag = float(self.policy.get("max_magnitude", 1e7))

        for key, value in numeric.items():
            if not isinstance(key, str):
                raise DeltaValidationError(f"numeric_updates key must be string: {key!r}", delta)
            if not isinstance(value, (int, float)):
                raise DeltaValidationError(f"numeric_updates value must be number: {key}={value!r}", delta)
            if abs(value) > max_mag:
                raise DeltaValidationError(f"Magnitude too large for {key}: {value}", delta)

            # Protected keys: no negative result
            key_lower = key.lower()
            if any(pk in key_lower for pk in protected):
                current = self.variables.get(key, 0)
                if isinstance(current, (int, float)):
                    new_val = current + value
                    if new_val < 0:
                        raise DeltaValidationError(
                            f"Protected variable {key} would become negative: {new_val}", delta
                        )

            # Caps: value must stay in [min, max]
            if key in caps:
                cap_range = caps[key]
                if isinstance(cap_range, (list, tuple)) and len(cap_range) >= 2:
                    lo, hi = float(cap_range[0]), float(cap_range[1])
                    current = self.variables.get(key, 0)
                    if isinstance(current, (int, float)):
                        new_val = current + value
                        if new_val < lo or new_val > hi:
                            raise DeltaValidationError(
                                f"Variable {key} would be {new_val} outside cap [{lo}, {hi}]", delta
                            )

    def apply_delta(
        self,
        delta: Delta | dict[str, Any],
        *,
        source: str | None = None,
        enforce_policy: bool = True,
    ) -> dict[str, Any]:
        """
        Apply delta to state in place.
        If enforce_policy and delta violates policy, raise DeltaValidationError.
        Returns the applied delta dict.
        """
        if isinstance(delta, Delta):
            d = delta.to_dict() if hasattr(delta, "to_dict") else delta.model_dump()
        else:
            d = dict(delta)

        if enforce_policy:
            self._check_policy(d)

        numeric = d.get("numeric_updates") or {}
        for key, value in numeric.items():
            if isinstance(value, (int, float)):
                current = self.variables.get(key, 0)
                if isinstance(current, (int, float)):
                    self.variables[key] = current + value
                else:
                    self.variables[key] = value

        for eid, attrs in (d.get("entity_updates") or {}).items():
            if eid in self.entities:
                self.entities[eid] = dict(self.entities[eid])
                self.entities[eid].update(attrs)
            else:
                self.entities[eid] = dict(attrs)

        for eid, entity in (d.get("new_entities") or {}).items():
            self.entities[eid] = dict(entity)

        for rel in (d.get("relation_updates") or []):
            self.relations.append(dict(rel))

        if d.get("rationale"):
            self.narrative.append(f"[v{self.version}] {d['rationale']}")
        self.version += 1

        return d

    def apply_event(self, event: dict[str, Any], *, probabilistic: bool = False) -> None:
        """
        Apply event effects to state.
        event: {event_type, params: {effects: [{op, key, value}, ...]}}
        probabilistic: if True, roll for each effect (e.g. base_prob).
        """
        params = event.get("params") or {}
        effects = params.get("effects") or []
        if not isinstance(effects, list):
            return

        for eff in effects:
            if not isinstance(eff, dict):
                continue
            if probabilistic and random.random() > 0.5:
                continue
            op = eff.get("op")
            key = eff.get("key")
            value = eff.get("value", 0)
            if not key:
                continue
            if op == "increase_variable":
                current = self.variables.get(key, 0)
                if isinstance(current, (int, float)) and isinstance(value, (int, float)):
                    self.variables[key] = current + value
            elif op == "decrease_variable":
                current = self.variables.get(key, 0)
                if isinstance(current, (int, float)) and isinstance(value, (int, float)):
                    self.variables[key] = current - value
            elif op == "set" or op == "set_variable":
                if isinstance(value, (int, float)):
                    self.variables[key] = float(value)
            # spawn_entity: optional, could add entity to self.entities
