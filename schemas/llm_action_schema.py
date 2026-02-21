"""
LLM action block schema: strict JSON contract at the guard boundary.
Agents output this shape under ### ACTION_JSON; guard validates and sanitizes it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeltaEntry(BaseModel):
    """Single variable delta: variable name and numeric change."""

    variable: str = Field(..., description="World state variable name")
    change: float = Field(..., description="Relative change to apply")


class LLMActionBlock(BaseModel):
    """Strict action block: action type, actor, and list of variable deltas."""

    action: str = Field(..., description="Action type (must be in allowed_actions)")
    actor: str = Field(..., description="Agent name proposing the action")
    deltas: list[DeltaEntry] = Field(default_factory=list, description="Variable changes")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LLMActionBlock:
        """Build from dict (e.g. after guard extraction)."""
        return cls.model_validate(d)
