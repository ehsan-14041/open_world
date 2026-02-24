"""
LLM action guard: extract JSON block from agent output, validate against schema,
enforce allowed_actions and known variables, sanitize numeric values.
Engine and governance see only validated/sanitized output; reasoning never passes through.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from schemas.llm_action_schema import DeltaEntry, LLMActionBlock
from schemas.strategic_action_schema import StrategicActionResponse

try:
    from config.settings import DELTA_MAGNITUDE_CAP, MAX_DELTA
except ImportError:
    DELTA_MAGNITUDE_CAP = 1000.0
    MAX_DELTA = 10.0

# Variables that must not go negative (keyword match)
NON_NEGATIVE_KEYWORDS = {
    "population", "count", "resource", "cash", "money", "fund", "stock",
    "inventory", "supply", "runway",
}

# Safe numeric range: reject or clamp values outside [-1e12, 1e12]
SAFE_NUMERIC_MIN = -1e12
SAFE_NUMERIC_MAX = 1e12


def _is_non_negative_variable(var_name: str) -> bool:
    v = (var_name or "").lower()
    return any(kw in v for kw in NON_NEGATIVE_KEYWORDS)


def _extract_json_block(text: str) -> str | None:
    """Find content after ### ACTION_JSON, strip markdown code fences, return raw string or None."""
    if not text or not isinstance(text, str):
        return None
    marker = "### ACTION_JSON"
    idx = text.find(marker)
    if idx < 0:
        return None
    raw = text[idx + len(marker) :].strip()
    # Strip optional ```json ... ```
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip() or None


def _normalize_action_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize parsed action dict: accept action_type/agent_name, strip key whitespace."""
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = (k or "").strip() if isinstance(k, str) else str(k)
        if not key:
            continue
        # Map common LLM aliases to canonical keys
        if key == "action_type":
            out["action"] = v
        elif key == "agent_name":
            out["actor"] = v
        else:
            out[key] = v
    return out if out else data


def _is_strategic_response(data: dict[str, Any]) -> bool:
    """True if the extracted JSON looks like strategic format (chosen_action, expected_effect)."""
    return "chosen_action" in data and isinstance(data.get("expected_effect"), dict)


class LLMActionGuard:
    """
    Extract, validate, and sanitize LLM-produced action JSON.
    Enforces allowed_actions, known variables, delta magnitude cap, non-negative resources.
    When strategic_format=True or response has chosen_action/expected_effect, uses strategic schema.
    """

    def __init__(
        self,
        allowed_actions: list[str],
        *,
        delta_magnitude_cap: float | None = None,
        strategic_format: bool = False,
        max_delta: float | None = None,
    ) -> None:
        self.allowed_actions = list(allowed_actions or [])
        self.delta_magnitude_cap = delta_magnitude_cap if delta_magnitude_cap is not None else DELTA_MAGNITUDE_CAP
        self.strategic_format = bool(strategic_format)
        self.max_delta = float(max_delta) if max_delta is not None else MAX_DELTA

    def extract_json(self, llm_output: str) -> dict[str, Any]:
        """
        Extract the single JSON block from agent output (after ### ACTION_JSON).
        Returns parsed dict on success, or structured error dict: {"error": str, "stage": "extraction"}.
        """
        raw = _extract_json_block(llm_output)
        if not raw:
            return {"error": "No ### ACTION_JSON block found", "stage": "extraction"}

        # Remove trailing commas before parsing (common LLM mistake)
        raw = re.sub(r",\s*}", "}", raw)
        raw = re.sub(r",\s*]", "]", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}", "stage": "extraction"}

        if not isinstance(data, dict):
            return {"error": "ACTION_JSON must be a JSON object", "stage": "extraction"}

        # Normalize keys: handle LLM output using action_type/agent_name or whitespace-mangled keys
        data = _normalize_action_keys(data)
        return data

    def validate(
        self,
        json_action: dict[str, Any],
        world_state: dict[str, Any] | None = None,
        *,
        agent_allowed_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate against LLMActionBlock or StrategicActionResponse schema.
        Returns validated dict (action, actor, deltas; plus strategic keys if strategic).
        On failure returns {"valid": False, "errors": list[str]}.
        When agent_allowed_actions is provided, use it for action validation instead of global list.
        """
        errors: list[str] = []

        if "error" in json_action and "stage" in json_action:
            return {"valid": False, "errors": [json_action.get("error", "extraction failed")]}

        use_strategic = self.strategic_format or _is_strategic_response(json_action)
        if use_strategic:
            return self._validate_strategic(json_action, world_state or {}, agent_allowed_actions=agent_allowed_actions)

        # Legacy: action, actor, deltas
        action = json_action.get("action") or json_action.get("action_type")
        actor = json_action.get("actor") or json_action.get("agent_name")
        deltas = json_action.get("deltas")

        allowed = agent_allowed_actions if agent_allowed_actions is not None else self.allowed_actions
        if not isinstance(action, str) or not action.strip():
            errors.append("'action' must be a non-empty string")
        elif allowed and action.strip() not in allowed:
            errors.append(f"action must be one of: {allowed}")

        if not isinstance(actor, str) or not actor.strip():
            errors.append("'actor' must be a non-empty string")

        if deltas is not None and not isinstance(deltas, list):
            errors.append("'deltas' must be an array")
        elif isinstance(deltas, list):
            for i, d in enumerate(deltas):
                if not isinstance(d, dict):
                    errors.append(f"deltas[{i}] must be an object")
                else:
                    if "variable" not in d or not isinstance(d.get("variable"), str):
                        errors.append(f"deltas[{i}].variable must be a string")
                    change = d.get("change")
                    if change is not None and not isinstance(change, (int, float)):
                        errors.append(f"deltas[{i}].change must be a number")

        if errors:
            return {"valid": False, "errors": errors}

        try:
            block = LLMActionBlock(
                action=(action or "").strip(),
                actor=(actor or "").strip(),
                deltas=[DeltaEntry(variable=str(d.get("variable", "")), change=float(d.get("change", 0))) for d in (deltas or [])],
            )
            return block.to_dict()
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    def _validate_strategic(
        self,
        data: dict[str, Any],
        world_state: dict[str, Any],
        *,
        agent_allowed_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Validate strategic response and return canonical shape (action, actor, deltas + strategic extras)."""
        if data.get("error"):
            return {"valid": False, "errors": [str(data.get("error", "unknown error"))]}
        variables = world_state.get("variables") or world_state.get("global_state") or {}
        if not isinstance(variables, dict):
            variables = {}
        allowed_vars = set(variables.keys())
        allowed = agent_allowed_actions if agent_allowed_actions is not None else self.allowed_actions
        errors: list[str] = []
        chosen = (data.get("chosen_action") or "").strip()
        primary = (data.get("primary_variable") or "").strip()
        if not chosen:
            errors.append("chosen_action must be non-empty")
        elif allowed and chosen not in allowed:
            errors.append(f"chosen_action must be one of: {allowed}")
        if not primary:
            errors.append("primary_variable cannot be null and must be one of world variables")
        elif allowed_vars and primary not in allowed_vars:
            errors.append(f"primary_variable must be one of: {list(allowed_vars)}")
        prob = data.get("probability")
        if prob is not None and not isinstance(prob, (int, float)):
            errors.append("probability must be a number")
        elif isinstance(prob, (int, float)) and not (0 <= prob <= 1):
            errors.append("probability must be between 0 and 1")
        expected = data.get("expected_effect")
        if expected is not None and not isinstance(expected, dict):
            errors.append("expected_effect must be an object")
        elif isinstance(expected, dict) and allowed_vars:
            for k in expected:
                if k not in allowed_vars:
                    errors.append(f"expected_effect key '{k}' must be a world variable")
        if errors:
            return {"valid": False, "errors": errors}
        try:
            resp = StrategicActionResponse(
                chosen_action=chosen,
                primary_variable=primary,
                probability=float(prob) if prob is not None else 0.5,
                justification=str(data.get("justification") or ""),
                causal_chain=str(data.get("causal_chain") or ""),
                expected_effect=dict(data.get("expected_effect") or {}),
                relation_updates=list(data.get("relation_updates") or []),
            )
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}
        # Convert to canonical shape for loop (actor filled in sanitize with agent_name)
        deltas = [{"variable": k, "change": v} for k, v in resp.expected_effect.items()]
        return {
            "action": resp.chosen_action,
            "actor": "",  # set in sanitize from agent_name
            "deltas": deltas,
            "primary_variable": resp.primary_variable,
            "relation_updates": resp.relation_updates,
            "probability": resp.probability,
            "justification": resp.justification,
            "causal_chain": resp.causal_chain,
            "_strategic": True,
        }

    def sanitize(
        self,
        json_action: dict[str, Any],
        world_state: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Apply deterministic safety: cap delta magnitudes, clamp so non-negative
        variables stay >= 0, drop unknown variables, reject NaN/Inf.
        Returns sanitized dict (action, actor, deltas; plus strategic keys if _strategic).
        When response is strategic, agent_name is used for actor and max_delta for cap.
        """
        if "valid" in json_action and json_action.get("valid") is False:
            return json_action
        if "error" in json_action:
            return json_action

        variables = world_state.get("variables") or world_state.get("global_state") or {}
        if not isinstance(variables, dict):
            variables = {}
        allowed_vars = set(variables.keys())

        action = json_action.get("action") or json_action.get("action_type") or ""
        actor = json_action.get("actor") or json_action.get("agent_name") or ""
        if json_action.get("_strategic") and agent_name:
            actor = agent_name
        deltas_in = json_action.get("deltas") or []
        use_max_delta = json_action.get("_strategic")
        cap = self.max_delta if use_max_delta else (self.delta_magnitude_cap or 1000.0)

        sanitized_deltas: list[dict[str, Any]] = []
        for d in deltas_in:
            var = d.get("variable") if isinstance(d, dict) else None
            change = d.get("change") if isinstance(d, dict) else None

            if not isinstance(var, str) or not var.strip():
                continue
            var = var.strip()

            if allowed_vars and var not in allowed_vars:
                continue

            try:
                val = float(change) if change is not None else 0.0
            except (TypeError, ValueError):
                continue

            if not math.isfinite(val):
                continue
            val = max(SAFE_NUMERIC_MIN, min(SAFE_NUMERIC_MAX, val))

            # Magnitude cap
            if abs(val) > cap:
                val = cap if val > 0 else -cap

            # Non-negative: clamp so current + change >= 0
            current = variables.get(var)
            if _is_non_negative_variable(var) and isinstance(current, (int, float)):
                if current + val < 0:
                    val = -float(current)

            sanitized_deltas.append({"variable": var, "change": val})

        out: dict[str, Any] = {
            "action": action,
            "actor": actor,
            "deltas": sanitized_deltas,
        }
        if json_action.get("_strategic"):
            out["primary_variable"] = json_action.get("primary_variable") or ""
            out["relation_updates"] = list(json_action.get("relation_updates") or [])
            out["probability"] = json_action.get("probability", 0.5)
            out["justification"] = json_action.get("justification") or ""
            out["causal_chain"] = json_action.get("causal_chain") or ""
        return out

    def check_internal_consistency(self, extracted: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Check for conflicting or inconsistent LLM output (e.g. action_type vs primary_variable, deltas in bounds).
        Returns (ok, list of issue descriptions).
        """
        issues: list[str] = []
        action = (extracted.get("action") or extracted.get("action_type") or "").strip()
        primary = (extracted.get("primary_variable") or "").strip()
        deltas = extracted.get("deltas") or []
        delta_vars = {d.get("variable") for d in deltas if isinstance(d, dict) and d.get("variable")}
        if action.startswith("increase_") or action.startswith("decrease_"):
            inferred_var = action.replace("increase_", "").replace("decrease_", "").strip()
            if inferred_var and primary and inferred_var != primary:
                issues.append(f"action_type '{action}' implies primary_variable '{inferred_var}' but got '{primary}'")
            if inferred_var and delta_vars and inferred_var not in delta_vars:
                issues.append(f"action_type '{action}' implies variable '{inferred_var}' but deltas have {delta_vars}")
        if primary and delta_vars and primary not in delta_vars:
            issues.append(f"primary_variable '{primary}' not in deltas {delta_vars}")
        for d in deltas:
            if not isinstance(d, dict):
                continue
            ch = d.get("change")
            if ch is not None and isinstance(ch, (int, float)):
                if ch < SAFE_NUMERIC_MIN or ch > SAFE_NUMERIC_MAX:
                    issues.append(f"delta change {ch} out of safe range [{SAFE_NUMERIC_MIN}, {SAFE_NUMERIC_MAX}]")
        return (len(issues) == 0, issues)
