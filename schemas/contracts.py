"""
Canonical typed contracts for the Open World Engine.
Provides SimulationSpec, State, ActionSpec, EventSpec, ConstraintSpec, TraceEntry, TransitionResult
with from_dict/to_dict and adapters for legacy dict shapes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Re-export Delta for contract documentation; defined in delta_schema.
from schemas.delta_schema import Delta

__all__ = [
    "SimulationSpec",
    "State",
    "ActionSpec",
    "EventSpec",
    "ConstraintSpec",
    "TraceEntry",
    "TransitionResult",
    "Delta",
    "simulation_spec_from_scenario",
    "state_from_dict",
    "action_spec_from_dict",
    "event_spec_from_dict",
    "constraint_spec_from_variable_spec",
    "trace_entry_from_dict",
]


# --- SimulationSpec: scenario-derived run config ---


class SimulationSpec(BaseModel):
    """Typed run config derived from scenario + config. No UI/product fields."""

    description: str = Field(default="", description="Scenario description")
    initial_state: dict[str, Any] = Field(default_factory=dict, description="Initial variables/state")
    relations: list[dict[str, Any]] = Field(default_factory=list, description="Relations list")
    allowed_actions: list[str] = Field(default_factory=list, description="Allowed action type names")
    governance: dict[str, Any] = Field(default_factory=dict, description="Governance config")
    causal_links: list[dict[str, Any]] = Field(default_factory=list, description="Causal links")
    rules: list[dict[str, Any]] = Field(default_factory=list, description="Condition/effect rules")
    events: list[dict[str, Any]] = Field(default_factory=list, description="Scenario events (EventSpec-like dicts)")
    action_tradeoffs: dict[str, Any] = Field(default_factory=dict, description="Action tradeoff matrix")
    variable_tradeoffs: dict[str, Any] = Field(default_factory=dict, description="Variable tradeoffs")
    strategy_classes: dict[str, Any] = Field(default_factory=dict, description="Strategy class config")
    variable_specs: dict[str, Any] = Field(default_factory=dict, description="Variable specs (ConstraintSpec-like)")
    enable_meta_actions: bool = Field(default=False, description="Whether meta actions are enabled")
    agent_response_format: str = Field(default="legacy", description="legacy | strategic | option_set")
    initial_agents: list[dict[str, Any]] = Field(default_factory=list, description="Optional initial agent configs")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SimulationSpec:
        return cls.model_validate(d)


def simulation_spec_from_scenario(scenario: dict[str, Any]) -> SimulationSpec:
    """Build SimulationSpec from normalized scenario dict. Use after normalize_scenario()."""
    return SimulationSpec(
        description=scenario.get("description", ""),
        initial_state=dict(scenario.get("initial_state") or {}),
        relations=list(scenario.get("relations") or []),
        allowed_actions=list(scenario.get("allowed_actions") or []),
        governance=dict(scenario.get("governance") or {}),
        causal_links=list(scenario.get("causal_links") or []),
        rules=list(scenario.get("rules") or []),
        events=list(scenario.get("events") or []),
        action_tradeoffs=dict(scenario.get("action_tradeoffs") or {}),
        variable_tradeoffs=dict(scenario.get("variable_tradeoffs") or {}),
        strategy_classes=dict(scenario.get("strategy_classes") or {}),
        variable_specs=dict(scenario.get("variable_specs") or {}),
        enable_meta_actions=bool(scenario.get("enable_meta_actions", False)),
        agent_response_format=str(scenario.get("agent_response_format", "legacy")),
        initial_agents=list(scenario.get("initial_agents") or []),
    )


# --- State: world state snapshot ---


class State(BaseModel):
    """Canonical world state snapshot. Aligns with model/state and world/world_state shapes."""

    variables: dict[str, Any] = Field(default_factory=dict, description="Variable id -> value")
    global_state: dict[str, Any] = Field(default_factory=dict, description="Alias for variables")
    causal_links: list[dict[str, Any]] = Field(default_factory=list, description="Causal graph edges")
    entities: dict[str, Any] = Field(default_factory=dict, description="Entity id -> entity dict")
    relations: list[dict[str, Any]] = Field(default_factory=list, description="Relations")
    version: int = Field(default=0, description="State version")
    turn: int = Field(default=0, description="Current turn")
    narrative: list[str] = Field(default_factory=list, description="Optional narrative lines")
    ontology: dict[str, Any] = Field(default_factory=dict, description="Optional ontology")

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        if not d.get("global_state") and d.get("variables"):
            d["global_state"] = d["variables"]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> State:
        if not isinstance(d, dict):
            return cls()
        variables = dict(d.get("variables") or d.get("global_state") or {})
        return cls(
            variables=variables,
            global_state=dict(d.get("global_state") or variables),
            causal_links=list(d.get("causal_links") or []),
            entities=dict(d.get("entities") or {}),
            relations=list(d.get("relations") or []),
            version=int(d.get("version", 0)),
            turn=int(d.get("turn", 0)),
            narrative=list(d.get("narrative") or []),
            ontology=dict(d.get("ontology") or {}),
        )


def state_from_dict(snapshot: dict[str, Any]) -> State:
    """Adapter: build State from legacy snapshot dict."""
    return State.from_dict(snapshot)


# --- ActionSpec: abstract action (increase_variable, decrease_variable, set_variable, adjust_variable) ---


class ActionSpec(BaseModel):
    """Abstract action spec for action_interpreter. No domain-specific variable names."""

    type: str = Field(default="", description="increase_variable | decrease_variable | set_variable | adjust_variable")
    target: str | None = Field(default=None, description="Target variable (alias: variable)")
    variable: str | None = Field(default=None, description="Target variable")
    magnitude: float = Field(default=5.0, description="Effect magnitude")
    variance: float | None = Field(default=None, description="Optional variance when uncertainty enabled")
    success_probability: float | None = Field(default=None, description="Optional success probability")
    direction: str | None = Field(default=None, description="For adjust_variable: increase | decrease")
    effect: dict[str, Any] | None = Field(default=None, description="Nested effect for legacy compatibility")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActionSpec:
        if not isinstance(d, dict):
            return cls()
        # Flatten nested effect for validation
        effect = d.get("effect")
        if isinstance(effect, dict):
            out = dict(d)
            out.setdefault("type", effect.get("type") or d.get("type") or "")
            out.setdefault("target", effect.get("variable") or d.get("target") or d.get("variable"))
            out.setdefault("variable", effect.get("variable") or d.get("variable") or d.get("target"))
            out.setdefault("magnitude", effect.get("value") if effect.get("value") is not None else d.get("magnitude", 5.0))
            out.setdefault("direction", effect.get("direction") or d.get("direction"))
            out.setdefault("variance", effect.get("variance") or d.get("variance"))
            out.setdefault("success_probability", effect.get("success_probability") or d.get("success_probability"))
            d = out
        return cls.model_validate({k: v for k, v in d.items() if k in cls.model_fields})


def action_spec_from_dict(d: dict[str, Any] | None) -> ActionSpec | None:
    """Adapter: build ActionSpec from free-form dict (e.g. Proposal.action_spec). Returns None if invalid."""
    if not d or not isinstance(d, dict):
        return None
    try:
        return ActionSpec.from_dict(d)
    except Exception:
        return None


# --- EventSpec: scenario-defined event ---


class EventSpec(BaseModel):
    """Scenario-defined event: fires at trigger_turn with params."""

    event_type: str = Field(default="", description="Handler key in event_queue registry")
    trigger_turn: int = Field(default=0, description="Turn when event fires")
    params: dict[str, Any] = Field(default_factory=dict, description="Passed to handler")
    priority: int = Field(default=0, description="Lower = higher priority")
    origin: str = Field(default="", description="Optional origin label")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventSpec:
        if not isinstance(d, dict):
            return cls()
        return cls(
            event_type=str(d.get("event_type", "")),
            trigger_turn=int(d.get("trigger_turn", 0)),
            params=dict(d.get("params") or {}),
            priority=int(d.get("priority", 0)),
            origin=str(d.get("origin", "")),
            metadata=dict(d.get("metadata") or {}),
        )


def event_spec_from_dict(d: dict[str, Any]) -> EventSpec:
    """Adapter: build EventSpec from scenario event dict."""
    return EventSpec.from_dict(d)


# --- ConstraintSpec: variable-level constraints (min, max, non_negative, protected) ---


class ConstraintSpec(BaseModel):
    """Variable-level constraints. Source of truth for bounds and flags; legacy variable_specs map here."""

    min: float | None = Field(default=None, description="Minimum value")
    max: float | None = Field(default=None, description="Maximum value")
    rate_limit: float | None = Field(default=None, description="Max absolute delta per step")
    soft_max: float | None = Field(default=None, description="Soft cap")
    softness: float | None = Field(default=None, description="Soft constraint strength")
    non_negative: bool = Field(default=False, description="If True, value must be >= 0")
    protected: bool = Field(default=False, description="If True, block negative outcomes (policy)")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ConstraintSpec:
        if not d or not isinstance(d, dict):
            return cls()
        return cls(
            min=float(d["min"]) if d.get("min") is not None else None,
            max=float(d["max"]) if d.get("max") is not None else None,
            rate_limit=float(d["rate_limit"]) if d.get("rate_limit") is not None else None,
            soft_max=float(d["soft_max"]) if d.get("soft_max") is not None else None,
            softness=float(d["softness"]) if d.get("softness") is not None else None,
            non_negative=bool(d.get("non_negative", False)),
            protected=bool(d.get("protected", False)),
        )


def constraint_spec_from_variable_spec(var_spec: dict[str, Any] | None) -> ConstraintSpec:
    """Build ConstraintSpec from legacy variable_specs entry or ValueSpec-like dict."""
    if not var_spec or not isinstance(var_spec, dict):
        return ConstraintSpec()
    scale = var_spec.get("scale")
    if isinstance(scale, dict):
        min_val = scale.get("min")
        max_val = scale.get("max")
    else:
        min_val = var_spec.get("min")
        max_val = var_spec.get("max")
    return ConstraintSpec(
        min=float(min_val) if min_val is not None else None,
        max=float(max_val) if max_val is not None else None,
        rate_limit=float(var_spec["rate_limit"]) if var_spec.get("rate_limit") is not None else None,
        soft_max=float(var_spec["soft_max"]) if var_spec.get("soft_max") is not None else None,
        softness=float(var_spec["softness"]) if var_spec.get("softness") is not None else None,
        non_negative=bool(var_spec.get("non_negative", False)),
        protected=bool(var_spec.get("protected", False)),
    )


# --- TraceEntry: canonical action trace entry ---


class TraceEntry(BaseModel):
    """Canonical action trace entry. Matches trace_log/action_trace shape."""

    turn: int = Field(default=0, description="Turn number")
    agent_id: str = Field(default="", description="Agent identifier")
    action: dict[str, Any] = Field(default_factory=dict, description="Action descriptor")
    delta_raw: dict[str, float] = Field(default_factory=dict, description="Raw delta before constraints")
    delta_applied: dict[str, float] = Field(default_factory=dict, description="Applied delta")
    expected_utility: float | None = Field(default=None, description="Expected utility at decision time")
    realized_utility: float | None = Field(default=None, description="Realized utility after step")
    belief_basis: dict[str, Any] | None = Field(default=None, description="Optional belief snapshot")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceEntry:
        return cls.model_validate(d)


def trace_entry_from_dict(d: dict[str, Any]) -> TraceEntry:
    """Adapter: build TraceEntry from legacy action_trace entry dict."""
    return TraceEntry.from_dict(d)


# --- TransitionResult: result of one step (optional, for tests/future loop) ---


class TransitionResult(BaseModel):
    """Result of one simulation step. Optional in Phase 1; used for tests or thin loop helper."""

    state_before: dict[str, Any] = Field(default_factory=dict, description="Snapshot before step")
    state_after: dict[str, Any] = Field(default_factory=dict, description="Snapshot after step")
    delta_applied: dict[str, Any] = Field(default_factory=dict, description="Delta that was applied")
    events_fired: list[dict[str, Any]] = Field(default_factory=list, description="Events processed this turn")
    trace_entries: list[dict[str, Any]] = Field(default_factory=list, description="Trace entries this step")
    governance_rejects: list[str] = Field(default_factory=list, description="Optional rejection reasons")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TransitionResult:
        return cls.model_validate(d)
