"""
Scenario parser: convert free-text scenario description to valid scenario JSON
using the 5-stage pipeline. Validates output against config/scenarios schema.

All LLM paths go through: parse_scenario_text -> pipeline -> ModelSerializer -> normalize_scenario.
"""

from __future__ import annotations

from typing import Any

from core.llm_service import call_llm as llm_service_call
from pipeline.orchestrator import run_pipeline
from pipeline.errors import PipelineError
from schemas.scenario_schema import normalize_scenario, validate_scenario

try:
    from config.settings import DEBUG_LLM
except Exception:
    DEBUG_LLM = False


def parse_scenario_text(text: str, *, use_llm: bool = True) -> dict[str, Any]:
    """
    Convert free-text scenario to scenario JSON.
    If use_llm is True, runs the 5-stage pipeline. If False, returns a minimal valid scenario.
    Raises ValueError on pipeline or validation failure.
    """
    text = (text or "").strip()
    if not text:
        return _default_scenario("Empty scenario")

    if not use_llm:
        return _default_scenario(text)

    def llm_client(prompt: str, system: str | None = None, *, as_json: bool = False) -> Any:
        """
        Pipeline-wide LLM entrypoint.

        - When as_json=True, we request JSON via llm_service with a permissive schema so
          that parsing/repair is centralized while allowing each stage to own structure.
        - When as_json=False, we use llm_service in text mode.
        """
        if as_json:
            return llm_service_call(
                prompt,
                system=system or "",
                schema={"required": [], "types": {}},
                temperature=None,
                max_tokens=None,
                usage_tier="scenario_pipeline",
            ) or {}
        out = llm_service_call(
            prompt,
            system=system or "",
            schema=None,
            temperature=None,
            max_tokens=None,
            usage_tier="scenario_pipeline",
        )
        return out or ""

    config = {"debug_llm": DEBUG_LLM}
    try:
        scenario = run_pipeline(text, llm_client, config)
    except PipelineError as e:
        raise ValueError(f"Scenario pipeline failed: {e}") from e

    errors = validate_scenario(scenario)
    if errors:
        raise ValueError("Scenario validation failed: " + "; ".join(errors))

    return normalize_scenario(scenario)


def _default_scenario(description: str) -> dict[str, Any]:
    """Minimal valid scenario when use_llm=False. No placeholder names (actor_1, agent_2)."""
    variables = ["primary_metric", "secondary_metric", "system_health"]
    initial_state = {v: 50.0 for v in variables}

    agents = [
        {"name": "participant_a", "role": "Participant A", "objectives": {"increase_primary_metric": 0.5, "decrease_secondary_metric": 0.3}},
        {"name": "participant_b", "role": "Participant B", "objectives": {"increase_secondary_metric": 0.5, "decrease_primary_metric": 0.3}},
        {"name": "participant_c", "role": "Participant C", "objectives": {"increase_system_health": 0.6}},
    ]

    allowed_actions = [f"increase_{v}" for v in variables] + [f"decrease_{v}" for v in variables] + ["adjust_variable"]

    return normalize_scenario({
        "description": description,
        "initial_agents": agents,
        "initial_state": initial_state,
        "relations": [],
        "allowed_actions": allowed_actions,
    })
