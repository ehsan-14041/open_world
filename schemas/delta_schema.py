"""
Delta schema: normalized world changes produced by WorldModelAgent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Delta(BaseModel):
    """World delta: numeric updates, entity/relation changes, meta_proposals, rationale."""

    numeric_updates: dict[str, float] = Field(default_factory=dict, description="Global state key -> delta (relative) or absolute")
    entity_updates: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Entity id -> attr updates")
    new_entities: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Entity id -> full entity dict")
    relation_updates: list[dict[str, Any]] = Field(default_factory=list, description="List of {from, to, type, ...}")
    meta_proposals: list[dict[str, Any]] = Field(default_factory=list, description="Ontology addition requests")
    rationale: str = Field(default="", description="Why this delta")
    effects_duration: int | None = Field(default=None, description="Optional turns for effect to apply")
    mitigation: str | None = Field(default=None, description="If requested change infeasible, suggested mitigation")
    delay_turns: int | None = Field(default=None, description="If set, effect is applied after this many turns (delayed)")
    probability: float | None = Field(default=None, description="Optional probability in [0,1] for delayed effect to fire")
    primary_variable: str | None = Field(default=None, description="Primary variable affected by this action (for causal mapping)")
    action_type: str | None = Field(default=None, description="Action type that generated this delta (for tracking)")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Delta:
        """Build Delta from dict (e.g. from LLM JSON)."""
        return cls.model_validate(d)
