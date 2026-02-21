"""
Stage 2: Variable Discovery.
Input: scenario text + extracted entities
Output: dynamically inferred variables (no predefined schema).
Supports systemic, relational, and internal variables.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pipeline._llm_utils import run_llm_stage
from pipeline.errors import PipelineError

VARIABLE_SYSTEM = """You are a systems modeler.
Based on the scenario and actors, define the system state variables.

Variables must emerge from the scenario context. Do NOT use a predefined schema.
Support:
- Systemic: system-level quantities (e.g. system_stability, market_volatility)
- Relational: between entities (e.g. trust_between_A_B, cooperation_level)
- Internal: per-entity state (e.g. satisfaction, resource_level)

Do not use agent/entity names as variable names. Use 4-8 variables.
Each variable should have a numeric initial value (0-100 scale unless context suggests otherwise).

Return JSON object:
{
  "variables": { "variable_name": numeric_initial_value }
}

Output JSON only."""

VARIABLE_USER = """Scenario:
{scenario_text}

Actors:
{actors_json}"""


def _validate_variables(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "Must return a JSON object"
    if "variables" not in data:
        return "Must have 'variables' key"
    if not isinstance(data["variables"], dict):
        return "'variables' must be an object"
    vars_dict = data["variables"]
    if len(vars_dict) == 0:
        return "Must have at least one variable"
    for k, v in vars_dict.items():
        if not isinstance(k, str) or not k.strip():
            return "Variable names must be non-empty strings"
        if not isinstance(v, (int, float)):
            return f"Variable '{k}' must have numeric value"
    return None


class VariableDiscoveryEngine:
    """Discover variables dynamically from scenario and entities."""

    @staticmethod
    def discover(
        scenario_text: str,
        entities: list[dict[str, Any]],
        llm_client: Callable[..., Any],
        config: dict[str, Any],
    ) -> dict[str, float]:
        """
        Discover variables from scenario and entities.
        Returns dict of variable_name -> initial_value.
        """
        actors_json = json.dumps(
            [{"name": e.get("name"), "role": e.get("role")} for e in entities],
            ensure_ascii=False,
        )
        user = VARIABLE_USER.format(scenario_text=scenario_text, actors_json=actors_json)
        try:
            result = run_llm_stage(
                "Variable Discovery",
                user,
                VARIABLE_SYSTEM,
                llm_client,
                config,
                _validate_variables,
            )
        except ValueError as e:
            raise PipelineError("Variable Discovery", str(e)) from e

        variables = result.get("variables") or {}
        out: dict[str, float] = {}
        for k, v in variables.items():
            if isinstance(k, str) and k.strip() and isinstance(v, (int, float)):
                out[k.strip()] = float(v)
        if not out:
            raise PipelineError("Variable Discovery", "No valid variables discovered")
        return out
