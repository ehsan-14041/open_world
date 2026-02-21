"""
EnvironmentAgent (EventGeneratorAgent): proposes 0-2 state-dependent events each turn.
Runs before role agents so events can influence the same turn's context.
LLM-driven dynamic palette; dry-run uses procedural generator only.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Callable

from core.llm_service import call_llm as llm_service_call
from schemas.meta_schema import NewEventProposal, ProbabilityModel

# Default event palette for rule-based dry-run
DEFAULT_EVENT_PALETTE: list[dict[str, Any]] = [
    {
        "name": "incident",
        "description": "Minor incident increases tension",
        "trigger_vars": [{"key": "tension", "op": ">", "value": 50}],
        "effects": [{"op": "increase_variable", "key": "tension", "value": 3}],
        "base_prob": 0.15,
    },
    {
        "name": "negotiation_round",
        "description": "Negotiation opportunity",
        "trigger_vars": [{"key": "stability", "op": ">", "value": 30}],
        "effects": [{"op": "increase_variable", "key": "negotiation_progress", "value": 5}],
        "base_prob": 0.1,
    },
    {
        "name": "deconfliction",
        "description": "Deconfliction reduces tension",
        "trigger_vars": [{"key": "tension", "op": ">", "value": 60}],
        "effects": [{"op": "decrease_variable", "key": "tension", "value": 5}],
        "base_prob": 0.2,
    },
    {
        "name": "external_shock",
        "description": "External shock affects stability",
        "trigger_vars": [],
        "effects": [{"op": "decrease_variable", "key": "stability", "value": 5}],
        "base_prob": 0.05,
    },
]


def _evaluate_trigger(pred: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    """Check if a trigger predicate matches the snapshot."""
    from schemas.meta_schema import evaluate_predicate
    # Wrap snapshot for predicate format (key/fact in predicate, not snapshot)
    return evaluate_predicate(pred, snapshot)


def _rule_based_propose(snapshot: dict[str, Any], max_events: int = 2) -> list[dict[str, Any]]:
    """
    Rule-based: pick 0-2 events from default palette based on variable thresholds.
    Returns list of event dicts ready for event queue.
    """
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    proposed: list[dict[str, Any]] = []
    for template in DEFAULT_EVENT_PALETTE:
        if len(proposed) >= max_events:
            break
        triggers = template.get("trigger_vars") or []
        # If no triggers, use base_prob only
        if not triggers:
            if random.random() < template.get("base_prob", 0.1):
                proposed.append({
                    "event_type": template["name"],
                    "params": {"effects": template.get("effects", [])},
                    "origin": "environment_agent",
                    "metadata": {"description": template.get("description", "")},
                })
            continue
        # All triggers must match
        all_match = all(_evaluate_trigger(t, snapshot) for t in triggers)
        if all_match and random.random() < template.get("base_prob", 0.15):
            proposed.append({
                "event_type": template["name"],
                "params": {"effects": template.get("effects", [])},
                "origin": "environment_agent",
                "metadata": {"description": template.get("description", "")},
            })
    return proposed


class EnvironmentAgent:
    """
    Proposes 0-2 events per turn. State-dependent probability.
    Dry-run: rule-based heuristics from default palette.
    LLM mode: JSON output matching NewEventProposal schema.
    """

    def __init__(
        self,
        llm_client: Callable[..., Any] | None = None,
        *,
        dry_run: bool = False,
        max_events_per_turn: int = 2,
    ) -> None:
        self.llm_client = llm_client
        self.dry_run = dry_run
        self.max_events_per_turn = max_events_per_turn

    def propose(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Propose 0-2 events for this turn.
        Returns list of event dicts: {event_type, params, origin, metadata, trigger_turn?}.
        Dry-run: procedural generator only. LLM mode: dynamic palette; on invalid output return [].
        """
        if self.dry_run or not self.llm_client:
            return _rule_based_propose(snapshot, self.max_events_per_turn)

        # LLM-driven dynamic palette: use llm_service with schema + repair-once
        prompt = self._build_prompt(snapshot)
        schema = {"required": [], "types": {"events": "list"}}
        client_fn = lambda p, s, **kw: self.llm_client(p, system=s, as_json=True)
        out = llm_service_call(
            prompt,
            system=self._system_prompt(),
            schema={"required": ["events"], "types": {"events": "list"}},
            temperature=0.5,
            retry=1,
            client_fn=client_fn,
        )
        if not isinstance(out, dict) or "events" not in out:
            return []
        events = out.get("events") or []
        if not isinstance(events, list):
            return []
        result: list[dict[str, Any]] = []
        for ev in events[: self.max_events_per_turn]:
            if isinstance(ev, dict):
                validated = self._validate_and_convert(ev, snapshot)
                if validated:
                    result.append(validated)
        return result

    def _system_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "event_palette.txt"
        if prompt_path.is_file():
            return prompt_path.read_text(encoding="utf-8").strip()
        return """You are an Environment/Event Generator for a multi-agent simulation.
Output JSON only. Propose 0-2 events per turn. Each event must have:
- name: string
- description: string
- trigger_conditions: list of {key, op, value} or {fact, op, value}
- probability_model: {base_prob, modifiers}
- effects: list of {op, key, value} (op: increase_variable, decrease_variable, set_variable)
- duration_turns: optional int
- visibility: "public"|"private_to_some"|"latent"
Events must create strategic pressure (tradeoffs), not only random noise.
Output: {"events": [NewEventProposal, ...]}"""

    def _build_prompt(self, snapshot: dict[str, Any]) -> str:
        variables = snapshot.get("variables") or snapshot.get("global_state") or {}
        return f"""Current world state (variables): {json.dumps(variables)[:800]}
Propose 0-2 events that are state-dependent. Probability should increase when key variables (e.g. tension, stability) cross thresholds.
Output JSON: {{"events": [...]}}"""

    def _validate_and_convert(self, ev: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """Validate event and convert to event queue format."""
        try:
            prob = ev.get("probability_model")
            if isinstance(prob, dict):
                prob = ProbabilityModel(**prob) if prob else ProbabilityModel()
            proposal = NewEventProposal(
                name=ev.get("name", "unknown"),
                description=ev.get("description", ""),
                trigger_conditions=ev.get("trigger_conditions", []),
                probability_model=prob,
                effects=ev.get("effects", []),
                duration_turns=ev.get("duration_turns"),
                visibility=ev.get("visibility", "public"),
            )
        except Exception:
            return None
        # Convert to event queue format
        return {
            "event_type": proposal.name,
            "params": {"effects": proposal.effects, "description": proposal.description},
            "origin": "environment_agent",
            "metadata": {
                "trigger_conditions": proposal.trigger_conditions,
                "probability_model": proposal.probability_model.model_dump() if isinstance(proposal.probability_model, ProbabilityModel) else proposal.probability_model,
            },
        }
