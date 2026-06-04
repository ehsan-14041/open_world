from __future__ import annotations

"""
Typed provenance and effect records for one transition.

Phase 2: shared TransitionKernel and provenance model.
Kept small and dependency-light so it can be imported from both core and simulation code.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class EffectRecord(BaseModel):
    """
    Minimal shared effect shape used for provenance.

    Source/event types are intentionally generic so that delayed events, rule
    activations, shocks and future recalibration events can all be expressed
    with the same schema.
    """

    source: Literal["direct", "delayed", "event", "rule", "shock", "recalibration"] = Field(
        ...,
        description="High-level origin of this effect.",
    )
    trigger_turn: int | None = Field(
        default=None,
        description="Turn when the effect was applied (if applicable).",
    )
    origin_id: str | None = Field(
        default=None,
        description="Optional identifier (e.g. rule id, event type, shock id).",
    )
    params_or_delta: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload for this effect (params for events, delta for numeric effects).",
    )
    description: str | None = Field(
        default=None,
        description="Optional human-readable description.",
    )


class TransitionProvenance(BaseModel):
    """
    One-step transition provenance.

    Captures the full lifecycle from proposed delta through governance,
    constraints, deterministic physics, noise and post-delta effects.
    """

    proposed_delta: dict[str, float] = Field(
        default_factory=dict,
        description="Merged delta before constraints (after governance / merge).",
    )
    governance_modified_delta: dict[str, float] | None = Field(
        default=None,
        description="Delta after governance repair (if any); None if unchanged.",
    )
    constrained_delta: dict[str, float] = Field(
        default_factory=dict,
        description="Delta actually applied after soft constraints.",
    )
    propagation_trace: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Low-level propagation iterations from deterministic physics.",
    )
    noise_component: dict[str, float] = Field(
        default_factory=dict,
        description="Noise component added after deterministic physics (per variable).",
    )
    delayed_effects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Delayed events that fired this turn (raw event dicts).",
    )
    events_fired: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Events processed from the generic event queue.",
    )
    rule_effects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rule activations and their effects.",
    )
    shock_effect: dict[str, Any] | None = Field(
        default=None,
        description="Shock engine result dict (if shocks enabled this turn).",
    )
    final_variable_changes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Reconciled variable changes for this step (direct, propagation, noise, delayed, rule, shock).",
    )
    effect_records: list[EffectRecord] = Field(
        default_factory=list,
        description="Unified list of effects in canonical ordering (direct → delayed → events → rules → shocks → recalibration).",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return plain dict representation suitable for JSON serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> TransitionProvenance:
        """Robust adapter from loosely-typed dicts."""
        if not d or not isinstance(d, dict):
            return cls()
        # effect_records may come in as list[dict]; pydantic will coerce them.
        return cls.model_validate(d)

