"""
Stage 1: Entity Extraction.
Input: raw scenario text
Output: structured list of real named actors (no placeholder naming).
"""

from __future__ import annotations

from typing import Any, Callable

from pipeline._llm_utils import is_placeholder_name, run_llm_stage
from pipeline.errors import PipelineError

ENTITY_SYSTEM = """You are a geopolitical and multi-agent systems analyst.
Extract the key actors implied by the scenario.

CRITICAL: Use real, canonical entity names derived from the scenario context.
- Examples: "gulf_coast", "federal_regulator", "local_community", "oil_company", "environmental_coalition"
- Do NOT use placeholder names like actor_1, agent_2, faction_a, agent_1, actor_2.
- Each name must be a short, descriptive snake_case identifier that reflects the entity's role in the scenario.

Return a JSON object with an "entities" key containing an array of objects. Each object has:
- name (short identifier, snake_case, must be scenario-specific)
- role (descriptive string)
- power_level (float 0-1)
- alignment (string, optional)

Example: {"entities": [{"name": "oil_company", "role": "...", "power_level": 0.7}]}
Max 4 actors. Output JSON only."""

ENTITY_USER = """Scenario:
{scenario_text}"""


def _unwrap_to_array(data: Any) -> Any:
    """Extract array from LLM response. API uses json_object so model may return {"entities": [...]}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Check known keys first
        for key in ("entities", "actors", "results", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        # Fallback: use first dict value that is a list (handles {"data": [...], etc.)
        for val in data.values():
            if isinstance(val, list):
                return val
    return data


def _validate_entities(data: Any) -> str | None:
    data = _unwrap_to_array(data)
    if not isinstance(data, list):
        return "Must return a JSON array"
    if len(data) == 0:
        return "Must return at least one actor"
    for i, el in enumerate(data):
        if not isinstance(el, dict):
            return f"Element {i} must be an object"
        if "name" not in el or not isinstance(el.get("name"), str):
            return f"Element {i} must have string 'name'"
        if "role" not in el or not isinstance(el.get("role"), str):
            return f"Element {i} must have string 'role'"
        name = (el.get("name") or "").strip()
        if is_placeholder_name(name):
            return f"Element {i} has invalid placeholder name '{name}'. Use real scenario-derived names."
    return None


class EntityExtractor:
    """Extract real named entities from scenario text."""

    @staticmethod
    def extract(
        scenario_text: str,
        llm_client: Callable[..., Any],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Extract entities from scenario text.
        Returns list of dicts with name, role, power_level, alignment.
        Raises PipelineError on validation failure or placeholder names.
        """
        user = ENTITY_USER.format(scenario_text=scenario_text)
        retry_prompt = 'Your previous output was invalid. Return a JSON object with an "entities" key containing an array of objects (each with name, role, power_level).'
        try:
            result = run_llm_stage(
                "Entity Extraction",
                user,
                ENTITY_SYSTEM,
                llm_client,
                config,
                _validate_entities,
                retry_prompt=retry_prompt,
            )
        except ValueError as e:
            raise PipelineError("Entity Extraction", str(e)) from e

        result = _unwrap_to_array(result)
        entities: list[dict[str, Any]] = []
        for el in result:
            if not isinstance(el, dict):
                continue
            name = (el.get("name") or "").strip()
            if not name or is_placeholder_name(name):
                raise PipelineError(
                    "Entity Extraction",
                    f"Invalid entity name '{name}'. Placeholder names (actor_1, agent_2, etc.) are not allowed.",
                )
            entities.append({
                "name": name,
                "role": (el.get("role") or name).strip(),
                "power_level": float(el.get("power_level", 0.5)) if el.get("power_level") is not None else 0.5,
                "alignment": (el.get("alignment") or "").strip() or None,
            })
        return entities
