"""
WorldModelAgent: normalize_proposal(proposal, world_snapshot) -> Delta.
LLM-first with repair-once. Validation guard: _validate_delta; if invalid return None.
CRITICAL: No rule-based fallback. If LLM fails after retry or validation fails, return None.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.llm_service import call_llm as llm_service_call
from schemas.delta_schema import Delta
from schemas.proposal_schema import Proposal

_logger = logging.getLogger(__name__)

DELTA_SCHEMA = {
    "required": ["numeric_updates", "rationale"],
    "types": {
        "numeric_updates": "dict",
        "entity_updates": "dict",
        "new_entities": "dict",
        "relation_updates": "list",
        "meta_proposals": "list",
        "rationale": "str",
    },
}

# Protected keys: variables that must not go negative
_PROTECTED_KEYWORDS = {"population", "people", "resource", "cash", "count"}


def _validate_delta(delta: dict[str, Any], world_snapshot: dict[str, Any]) -> bool:
    """
    Lightweight validation guard. Returns False if invalid.
    - numeric_updates exists and is dict
    - At least one numeric key besides primary OR mitigation set
    - Keys strings, values numbers
    - Magnitudes not absurd (>1e7)
    - If key looks like population/resource and resulting value < 0 -> invalid
    """
    numeric = delta.get("numeric_updates")
    if not isinstance(numeric, dict):
        return False
    variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    # At least one secondary tradeoff (>=2 keys) OR mitigation set
    if len(numeric) < 2 and not delta.get("mitigation"):
        return False

    for key, value in numeric.items():
        if not isinstance(key, str):
            return False
        if not isinstance(value, (int, float)):
            return False
        if abs(value) > 1e7:
            return False
        key_lower = key.lower()
        if any(pk in key_lower for pk in _PROTECTED_KEYWORDS):
            current = variables.get(key, 0)
            if isinstance(current, (int, float)):
                new_val = current + value
                if new_val < 0:
                    return False
    return True


def _load_delta_system_prompt() -> str:
    """Load delta normalizer prompt from prompts/delta_normalizer.txt."""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "delta_normalizer.txt"
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8").strip()
    return """You are a world-model normalizer. Convert an agent Proposal into a precise Delta (world change).
Output ONLY a single JSON object with: numeric_updates (dict), entity_updates (dict), new_entities (dict), relation_updates (list), meta_proposals (list), rationale (string), effects_duration (number or null), mitigation (string or null).
Constraints: (1) Every action MUST affect at least two variables. (2) No negative population or resources. (3) If infeasible, set mitigation."""


class WorldModelAgent:
    """Normalizes proposals to Deltas. LLM-first; validation guard; no rule-based fallback."""

    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def normalize_proposal(
        self,
        proposal: Proposal,
        world_snapshot: dict[str, Any],
        *,
        action_tradeoffs: dict[str, dict[str, float]] | None = None,
        variable_tradeoffs: dict[str, dict[str, float]] | None = None,
        temperature: float = 0.1,
        cache_key: str | None = None,
    ) -> Delta | None:
        """
        Return Delta from proposal. LLM first; repair-once; validation guard.
        If invalid after validation: log CRITICAL, return None. No rule-based fallback.

        Hot-path budgeting notes:
        - The state description passed to the LLM is deliberately truncated to
          keep prompts short in tight simulation loops.
        - Callers are encouraged to pass a cache_key (via llm_service.make_cache_key)
          when the same (snapshot, action, agent) triplet is queried repeatedly.
        """
        # Compact representation of global_state for token budget friendliness
        state_spec = json.dumps(world_snapshot.get("global_state", {}) or {})[:800]
        proposal_json = (
            proposal.to_dict()
            if hasattr(proposal, "to_dict")
            else {
                "action_type": getattr(proposal, "action_type", ""),
                "agent_name": getattr(proposal, "agent_name", ""),
                "rationale": getattr(proposal, "rationale", ""),
                "parameters": getattr(proposal, "parameters", {}),
            }
        )
        user = f"""State spec (relevant keys): {state_spec}

Proposal: {json.dumps(proposal_json)}

Produce the Delta JSON:"""

        system = _load_delta_system_prompt()
        client_fn = lambda p, s, **kw: self.llm_client(p, system=s, as_json=True)

        out = llm_service_call(
            user,
            system=system,
            schema=DELTA_SCHEMA,
            temperature=temperature,
            retry=1,
            cache_key=cache_key,
            client_fn=client_fn,
        )

        if not isinstance(out, dict):
            _logger.critical(
                "CRITICAL_WARNING: WorldModelAgent normalize_proposal returned non-dict. "
                "Returning NULL action."
            )
            return None

        try:
            delta = Delta.from_dict(out)
        except Exception as e:
            _logger.critical(
                "CRITICAL_WARNING: WorldModelAgent Delta.from_dict failed: %s. Returning NULL action.",
                e,
            )
            return None

        delta_dict = delta.to_dict() if hasattr(delta, "to_dict") else out
        if not _validate_delta(delta_dict, world_snapshot):
            action_type = getattr(proposal, "action_type", "") or proposal_json.get("action_type", "")
            agent_name = getattr(proposal, "agent_name", "") or proposal_json.get("agent_name", "")
            _logger.critical(
                "CRITICAL_WARNING: WorldModelAgent _validate_delta failed for action '%s' by agent '%s'. "
                "Returning NULL action.",
                action_type,
                agent_name,
            )
            return None

        return delta
