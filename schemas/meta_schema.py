"""
Meta-action schemas: ActionOption, OptionSet, SelectedAction, meta proposals,
DeltaPlan, and predicates. Domain-agnostic; optional additions for high-emergence.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Option style for multi-option generation ---
OptionStyle = Literal["safe", "bold", "creative"]

# --- Variable scale for NewVariableProposal ---
VariableScale = Literal["ratio_0_1", "score_0_100", "unbounded", "custom"]

# --- Polarity for causal links ---
Polarity = Literal["positive", "negative", "mixed"]

# --- Event visibility ---
EventVisibility = Literal["public", "private_to_some", "latent"]


class ActionOption(BaseModel):
    """One candidate action proposal from an agent."""

    agent_id: str = Field(..., description="Agent identifier")
    option_id: str = Field(..., description="Unique option id within OptionSet")
    style: OptionStyle = Field(..., description="safe, bold, or creative")
    action_name: str = Field(..., description="Must be in allowed_actions or propose_new_* meta-action")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Free-form JSON parameters")
    intent: str = Field(default="", description="Short intent description")
    expected_tradeoff: str = Field(..., description="Must mention at least one downside")
    uncertainty: float = Field(0.5, ge=0.0, le=1.0, description="Uncertainty 0..1")


class OptionSet(BaseModel):
    """What an agent returns each turn: exactly 3 options."""

    agent_id: str = Field(..., description="Agent identifier")
    options: list[ActionOption] = Field(..., min_length=3, max_length=3, description="Exactly 3 ActionOptions")


class SelectedAction(BaseModel):
    """Selector output: chosen option with reason."""

    agent_id: str = Field(..., description="Agent identifier")
    chosen_option_id: str = Field(..., description="ID of the chosen ActionOption")
    action_name: str = Field(..., description="Action type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameters for the action")
    short_reason: str = Field(default="", max_length=500, description="<= 2 sentences")
    uncertainty: float = Field(0.5, ge=0.0, le=1.0, description="Uncertainty 0..1")


# --- Predicate for trigger conditions ---
class KeyPredicate(BaseModel):
    """Predicate on a variable: key, op, value."""

    key: str = Field(..., description="Variable key")
    op: str = Field(..., description="Comparison: >, <, >=, <=, ==, !=")
    value: float | int | str | bool = Field(..., description="Value to compare")


class FactPredicate(BaseModel):
    """Predicate on a fact: fact, op, value."""

    fact: str = Field(..., description="Fact key")
    op: str = Field(..., description="Comparison: >, <, >=, <=, ==, !=")
    value: Any = Field(..., description="Value to compare")


# --- Probability model for events ---
class ProbabilityModel(BaseModel):
    """State-dependent probability: base + modifiers."""

    base_prob: float = Field(0.1, ge=0.0, le=1.0, description="Base probability")
    modifiers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="e.g. [{'key': 'tension', 'op': '>', 'value': 60, 'add': 0.2}]",
    )


# --- Meta proposals ---
class NewActionSpecProposal(BaseModel):
    """Proposal to register a new action spec."""

    name: str = Field(..., description="Action name (valid identifier)")
    description: str = Field(default="", description="Short description")
    parameters_schema: dict[str, Any] = Field(default_factory=dict, description="JSON schema-like dict")
    expected_effects: str = Field(default="", description="Short expected effects")
    safety_constraints: list[str] = Field(default_factory=list, description="Safety constraints")
    requires_approval: bool = Field(True, description="Whether approval is required")


class VariableSpecs(BaseModel):
    """Optional variable specs: min, max, clip, soft_max, softness, rate_limit."""

    min: float | None = None
    max: float | None = None
    clip: bool = False
    soft_max: float | None = None
    softness: float | None = None
    rate_limit: float | None = None


class NewVariableProposal(BaseModel):
    """Proposal to add a new variable to world state."""

    name: str = Field(..., description="Variable name (valid identifier)")
    description: str = Field(default="", description="Short description")
    scale: VariableScale = Field(default="score_0_100", description="Scale type")
    custom_min: float | None = None
    custom_max: float | None = None
    initial_value: float = Field(0.0, description="Initial value")
    variable_specs: VariableSpecs | None = None


class NewCausalLinkProposal(BaseModel):
    """Proposal to add/adjust a causal link."""

    from_key: str = Field(..., description="Source variable")
    to_key: str = Field(..., description="Target variable")
    polarity: Polarity = Field(default="positive", description="positive, negative, or mixed")
    strength: float = Field(0.5, ge=0.0, le=1.0, description="Strength 0..1")
    lag: int = Field(0, ge=0, description="Lag in turns")
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="Confidence 0..1")
    rationale_short: str = Field(default="", description="Short rationale")


class NewEventProposal(BaseModel):
    """Proposal for a new event template or one-off event."""

    name: str = Field(..., description="Event name")
    description: str = Field(default="", description="Short description")
    trigger_conditions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of predicates: {key/fact, op, value}",
    )
    probability_model: ProbabilityModel | dict[str, Any] = Field(
        default_factory=lambda: ProbabilityModel(),
        description="Base prob + modifiers",
    )
    effects: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Delta ops: increase_variable, decrease_variable, set_variable, etc.",
    )
    duration_turns: int | None = None
    visibility: EventVisibility = Field(default="public", description="public, private_to_some, latent")


class DeltaPlan(BaseModel):
    """Engine-executable effects with confidence and justification."""

    deltas: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ops: increase_variable, decrease_variable, set_variable, set_fact, create_variable, create_causal_link, enqueue_event, register_action",
    )
    confidence: float = Field(0.7, ge=0.0, le=1.0, description="Confidence 0..1")
    justification_short: str = Field(default="", max_length=500, description="<= 2 sentences")


def evaluate_predicate(predicate: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    """Evaluate a simple predicate against a world snapshot. Returns True if predicate matches."""
    if not isinstance(predicate, dict):
        return False
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    facts = snapshot.get("facts") or {}
    if "key" in predicate:
        val = variables.get(predicate["key"])
        op = predicate.get("op", "==")
        target = predicate.get("value")
        return _compare(val, op, target)
    if "fact" in predicate:
        val = facts.get(predicate["fact"])
        op = predicate.get("op", "==")
        target = predicate.get("value")
        return _compare(val, op, target)
    return False


def _compare(val: Any, op: str, target: Any) -> bool:
    """Compare val op target."""
    try:
        if op == "==":
            return val == target
        if op == "!=":
            return val != target
        if op in (">", "<", ">=", "<=") and isinstance(val, (int, float)) and isinstance(target, (int, float)):
            if op == ">":
                return val > target
            if op == "<":
                return val < target
            if op == ">=":
                return val >= target
            if op == "<=":
                return val <= target
    except (TypeError, ValueError):
        pass
    return False
