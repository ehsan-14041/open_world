from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NarrativeFact:
    """
    Atomic, structured statement used as an input to renderers and narrators.

    Examples:
    - kind="delta_summary", data={"delta": {...}}
    - kind="outcome", data={"label": "Strategic Success", "net_progress": 1.2}
    - kind="actor_performance", data={"actor": "...", "role": "Stabilizer", ...}
    """

    kind: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "data": dict(self.data)}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "NarrativeFact":
        return cls(kind=str(raw.get("kind", "")), data=dict(raw.get("data") or {}))


@dataclass
class NarrativeTag:
    """
    Abstract tag for interpretive labels.

    Examples:
    - kind="direction", value="Stabilizing"
    - kind="outcome_label", value="Strategic Success"
    - kind="actor_role", value="agent_a:Stabilizer"
    """

    kind: str
    value: str
    weight: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"kind": self.kind, "value": self.value}
        if self.weight is not None:
            out["weight"] = float(self.weight)
        return out

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "NarrativeTag":
        return cls(
            kind=str(raw.get("kind", "")),
            value=str(raw.get("value", "")),
            weight=float(raw["weight"]) if "weight" in raw and isinstance(raw["weight"], (int, float)) else None,
        )


@dataclass
class TurnNarrativeInputs:
    """
    Canonical per-turn narrative inputs: facts + tags + lightweight metadata.

    This is the primary interface between the engine core and any narrative
    renderer (deterministic or LLM-based). It remains domain-agnostic and
    is safe to serialize for UI or export layers.
    """

    turn: Optional[int]
    facts: List[NarrativeFact] = field(default_factory=list)
    tags: List[NarrativeTag] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn": self.turn,
            "facts": [f.to_dict() for f in self.facts],
            "tags": [t.to_dict() for t in self.tags],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "TurnNarrativeInputs":
        facts_raw = raw.get("facts") or []
        tags_raw = raw.get("tags") or []
        return cls(
            turn=raw.get("turn"),
            facts=[NarrativeFact.from_dict(f) for f in facts_raw if isinstance(f, dict)],
            tags=[NarrativeTag.from_dict(t) for t in tags_raw if isinstance(t, dict)],
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class RunNarrativeInputs:
    """
    Optional run-level narrative inputs constructed from a full trace.
    This can be produced from accumulated TurnNarrativeInputs plus
    final snapshot metadata.
    """

    facts: List[NarrativeFact] = field(default_factory=list)
    tags: List[NarrativeTag] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self.facts],
            "tags": [t.to_dict() for t in self.tags],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RunNarrativeInputs":
        facts_raw = raw.get("facts") or []
        tags_raw = raw.get("tags") or []
        return cls(
            facts=[NarrativeFact.from_dict(f) for f in facts_raw if isinstance(f, dict)],
            tags=[NarrativeTag.from_dict(t) for t in tags_raw if isinstance(t, dict)],
            metadata=dict(raw.get("metadata") or {}),
        )

