"""
Stage 4: Strategic Incentive Modeling.
Input: entities + variables
Output: per-entity strategic model with weighted preferences, trade-offs.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pipeline._llm_utils import run_llm_stage
from pipeline.errors import PipelineError

INCENTIVE_SYSTEM = """You are designing autonomous strategic agents.
For each actor, define a strategic model with:
- objectives: weighted preferences over variables (e.g. {"increase_stability": 0.6, "decrease_tension": 0.4})
- trade_offs: optional list of trade-offs (e.g. ["willing_to_sacrifice_growth_for_stability"])
- capabilities: list of capability tags for action matching (e.g. ["diplomatic", "military", "mediator", "regulator"])
- risk_tolerance: float 0-1 (optional, default 0.5)
- aggressiveness: float 0-1 (optional, default 0.5)
- strategic_constraints: optional list of constraints (e.g. ["cannot_escalate_if_trust_below_30"])

Avoid simplistic linear goals when the scenario implies complexity (e.g. multi-stakeholder).
Allow multi-dimensional preferences. Weights should sum to roughly 0.5-1.0 per actor.
Capabilities should match the actor's role and enable action filtering.

Return JSON object:
{
  "actor_name": {
    "objectives": { "increase_X": weight, "decrease_Y": weight },
    "trade_offs": ["optional"],
    "capabilities": ["diplomatic", "mediator"],
    "risk_tolerance": 0.5,
    "aggressiveness": 0.5,
    "strategic_constraints": ["optional"]
  }
}

Each objective must reference an existing world variable. Output JSON only."""

INCENTIVE_USER = """Actors:
{actors_json}

World Variables:
{variables_json}

Scenario context:
{scenario_text}"""


def _validate_incentives(
    data: Any,
    actor_names: list[str],
    variable_names: set[str],
) -> str | None:
    if not isinstance(data, dict):
        return "Must return a JSON object"
    for name in actor_names:
        if name not in data:
            return f"Must include actor '{name}'"
        prof = data[name]
        if not isinstance(prof, dict):
            return f"Profile for '{name}' must be an object"
        if "objectives" not in prof:
            return f"Profile for '{name}' must have 'objectives'"
        obj = prof.get("objectives")
        if not isinstance(obj, dict):
            return f"Objectives for '{name}' must be an object"
        for key in obj:
            if key.startswith("increase_"):
                var = key[9:]
                if var and var not in variable_names:
                    return f"Objective '{key}' references unknown variable '{var}'"
            elif key.startswith("decrease_"):
                var = key[9:]
                if var and var not in variable_names:
                    return f"Objective '{key}' references unknown variable '{var}'"
    return None


class IncentiveModeler:
    """Model strategic incentives per entity."""

    @staticmethod
    def model(
        entities: list[dict[str, Any]],
        variables: dict[str, float],
        scenario_text: str,
        llm_client: Callable[..., Any],
        config: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """
        Model incentives per entity.
        Returns dict[entity_name, {objectives, trade_offs, risk_tolerance, aggressiveness}].
        """
        actor_names = [e.get("name") for e in entities if e.get("name")]
        variable_names = set(variables.keys())
        if not actor_names:
            return {}

        actors_json = json.dumps(
            [{"name": e.get("name"), "role": e.get("role")} for e in entities],
            ensure_ascii=False,
        )
        variables_json = json.dumps(variables, ensure_ascii=False)
        user = INCENTIVE_USER.format(
            actors_json=actors_json,
            variables_json=variables_json,
            scenario_text=(scenario_text or "")[:2000],
        )

        def validator(data: Any) -> str | None:
            return _validate_incentives(data, actor_names, variable_names)

        try:
            result = run_llm_stage(
                "Incentive Modeling",
                user,
                INCENTIVE_SYSTEM,
                llm_client,
                config,
                validator,
            )
        except ValueError as e:
            # LLM returned empty/invalid JSON or validation failed: use minimal default incentives
            var_list = list(variable_names)
            first_var = var_list[0] if var_list else "outcome"
            result = {}
            for name in actor_names:
                result[name] = {
                    "objectives": {f"increase_{first_var}": 0.5} if first_var else {"stability": 0.5},
                    "trade_offs": [],
                    "capabilities": ["general"],
                    "risk_tolerance": 0.5,
                    "aggressiveness": 0.5,
                    "strategic_constraints": [],
                }

        incentives: dict[str, dict[str, Any]] = {}
        for name in actor_names:
            prof = result.get(name)
            if not isinstance(prof, dict):
                continue
            objectives = prof.get("objectives") or {}
            if not isinstance(objectives, dict):
                objectives = {}
            caps = prof.get("capabilities")
            if not isinstance(caps, list):
                caps = []
            constraints = prof.get("strategic_constraints")
            if not isinstance(constraints, list):
                constraints = []
            incentives[name] = {
                "objectives": objectives,
                "trade_offs": prof.get("trade_offs") if isinstance(prof.get("trade_offs"), list) else [],
                "capabilities": [str(c) for c in caps if c],
                "risk_tolerance": float(prof.get("risk_tolerance", 0.5)) if prof.get("risk_tolerance") is not None else 0.5,
                "aggressiveness": float(prof.get("aggressiveness", 0.5)) if prof.get("aggressiveness") is not None else 0.5,
                "strategic_constraints": [str(c) for c in constraints if c],
            }
        return incentives
