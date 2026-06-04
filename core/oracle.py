"""
LLM Advisor (Oracle Layer): advisory-only epistemic commentary. Does not modify
simulation state, chosen_action, predicted_delta, or any engine internals.
Output is for human review and dashboard display only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)


def _safe_default_analysis(action_id: str = "") -> dict[str, Any]:
    """Return v2.5 schema default when LLM fails or is disabled."""
    return {
        "advisory_only": True,
        "action_id": action_id or "proposed_action",
        "confidence": 50,
        "expected_utility": 0.0,
        "tail_risk": 0.5,
        "mitigation_variant": {},
        "causal_learning_suggestion": None,
        "shadow_simulation_summary": None,
    }


def _snapshot_summary(snapshot: dict[str, Any], max_length: int = 400) -> str:
    """Build a short read-only summary of snapshot without importing engine modules."""
    parts: list[str] = []
    turn = snapshot.get("turn", 0)
    parts.append(f"Turn: {turn}")
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if isinstance(variables, dict) and variables:
        var_str = ", ".join(f"{k}={v}" for k, v in list(variables.items())[:10])
        parts.append("Variables: " + var_str[:280])
    derived = snapshot.get("derived") or {}
    if isinstance(derived, dict) and derived:
        parts.append("Derived: " + str(derived)[:100])
    text = " ".join(parts)
    return text[:max_length] if len(text) > max_length else text


class OracleAdvisor:
    """
    Advisory-only layer: observes snapshot, chosen_action, history_summary, predicted_delta
    and returns structured epistemic commentary. Does not mutate inputs or call propagation,
    governance, or ontology. One LLM call per evaluate().
    """

    def __init__(self, llm_client: Callable[..., Any]) -> None:
        """
        llm_client: callable used for one LLM call (e.g. prompt, system=None, *, as_json=False, max_tokens=None).
        Typically a wrapper around core.llm_client.call_llm with max_tokens=ORACLE_MAX_TOKENS.
        """
        self.llm = llm_client

    def evaluate(
        self,
        snapshot: dict[str, Any],
        chosen_action: dict[str, Any],
        history_summary: str,
        predicted_delta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Call the LLM once and return structured JSON. Does not mutate any input.
        Does not access engine internals (propagation, governance, ontology).
        Returns the exact contract schema; on failure returns a safe default with same keys.
        """
        snapshot_text = _snapshot_summary(snapshot)
        action_text = json.dumps(chosen_action, default=str)[:300] if chosen_action else "—"
        delta_line = (
            ", ".join(f"{k}:{v:+.2f}" for k, v in list((predicted_delta or {}).items())[:10])
            if predicted_delta
            else "none"
        )

        system = (
            "You are a strategic advisor for a simulation engine. You analyze proposed actions and provide "
            "epistemic commentary only. You do not change any state. Output valid JSON only."
        )
        prompt = f"""Given the current state and chosen action, provide a brief advisory in the exact JSON structure below.

Current state summary:
{snapshot_text}

Recent history (last turns):
{history_summary}

Chosen action (summary):
{action_text}

Predicted variable deltas (variable: change):
{delta_line}

Respond with a single JSON object with exactly these keys (v2.5 schema):
- "advisory_only": true (boolean)
- "action_id": string, identifier of the action being reviewed
- "confidence": integer 0-100, confidence in the outcome for the next turn
- "expected_utility": float, expected utility (reward potential × P(success) − tail_risk × P(failure))
- "tail_risk": float, estimated tail/outlier risk magnitude (0-1 or 0-100 scale)
- "mitigation_variant": object, optional mitigation or adaptive strategy if risk is high (e.g. {{"description": "...", "conditions": [...]}})
- "causal_learning_suggestion": object or null, optional {{"source": "var", "target": "var", "polarity": "positive|negative", "strength_estimate": float}}
- "shadow_simulation_summary": object or null, optional short summary of shadow sim branches if performed

Output only the JSON object, no markdown or explanation."""

        action_id = str(chosen_action.get("action_type") or chosen_action.get("action") or "proposed_action")[:200]
        try:
            result = self.llm(prompt, system=system, as_json=True)
        except Exception as e:
            _logger.warning("oracle: LLM call failed: %s", e)
            return _safe_default_analysis(action_id)

        if not result or not isinstance(result, dict):
            return _safe_default_analysis(action_id)

        confidence = result.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = result.get("confidence_score", 50)
        confidence = max(0, min(100, int(round(float(confidence))))) if isinstance(confidence, (int, float)) else 50
        expected_utility = result.get("expected_utility")
        if not isinstance(expected_utility, (int, float)):
            expected_utility = 0.0
        expected_utility = float(expected_utility)
        tail_risk = result.get("tail_risk")
        if not isinstance(tail_risk, (int, float)):
            tail_risk = 0.5
        tail_risk = max(0.0, min(100.0, float(tail_risk)))
        mitigation_variant = result.get("mitigation_variant")
        if not isinstance(mitigation_variant, dict):
            mitigation_variant = {}
        causal_learning_suggestion = result.get("causal_learning_suggestion")
        if causal_learning_suggestion is not None and not isinstance(causal_learning_suggestion, dict):
            causal_learning_suggestion = None
        shadow_simulation_summary = result.get("shadow_simulation_summary")
        if shadow_simulation_summary is not None and not isinstance(shadow_simulation_summary, dict):
            shadow_simulation_summary = None

        return {
            "advisory_only": True,
            "action_id": str(result.get("action_id") or action_id)[:200],
            "confidence": confidence,
            "expected_utility": expected_utility,
            "tail_risk": tail_risk,
            "mitigation_variant": dict(mitigation_variant),
            "causal_learning_suggestion": causal_learning_suggestion,
            "shadow_simulation_summary": shadow_simulation_summary,
        }
