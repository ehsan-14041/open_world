"""
Strategic agent response schema: chosen_action, primary_variable, probability,
justification, causal_chain, expected_effect, relation_updates.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RelationUpdateEntry(BaseModel):
    """Single relation update: from, to, type, optional rationale."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(..., alias="from", description="Source actor name")
    to: str = Field(..., description="Target actor name")
    type: str = Field(default="", description="Relation type")
    rationale: str = Field(default="", description="Short rationale")


class StrategicActionResponse(BaseModel):
    """
    Strategic agent response: one action per turn with expected effects and causal chain.
    If the agent cannot produce a valid response, use error field only.
    """

    chosen_action: str = Field(..., description="Action type (must be in allowed_actions)")
    primary_variable: str = Field(..., description="Primary variable from world_variables")
    probability: float = Field(0.5, ge=0.0, le=1.0, description="Confidence 0.0-1.0")
    justification: str = Field(default="", description="Short rationale (<= 60 words)")
    causal_chain: str = Field(default="", description="One-line causal chain")
    expected_effect: dict[str, float] = Field(
        default_factory=dict,
        description="Variable name -> signed delta",
    )
    relation_updates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {from, to, type, rationale}",
    )
    error: str | None = Field(default=None, description="If set, response is invalid")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StrategicActionResponse:
        return cls.model_validate(d)
