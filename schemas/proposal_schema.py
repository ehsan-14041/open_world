"""
Proposal schema: JSON-serializable structure emitted by RoleAgents.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Proposal(BaseModel):
    """Agent proposal: action_type + parameters (legacy) or abstract action_spec (type, target, magnitude)."""

    agent_name: str = Field(..., description="Name of the proposing agent")
    action_type: str = Field(..., description="Type of action (e.g. launch_discount_campaign); ignored if action_spec is set")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    rationale: str | list[str] = Field(default="", description="Reasoning or bullet points")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence in [0, 1]")
    action_spec: dict[str, Any] | None = Field(default=None, description="Abstract action: type (e.g. increase_variable), target, magnitude. If set, core uses action interpreter.")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Proposal:
        """Build Proposal from dict (e.g. from LLM JSON)."""
        return cls.model_validate(d)
