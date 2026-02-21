"""
Option selector: picks one action from 3 options (safe/bold/creative) using a scoring rubric.
Rule-based by default; optional LLM critic.
"""

from __future__ import annotations

from typing import Any, Callable

from schemas.meta_schema import ActionOption, OptionSet, SelectedAction


def select_option_rule_based(
    options: list[ActionOption],
    agent_id: str,
    agent_objectives: dict[str, float],
    snapshot: dict[str, Any],
    last_actions: list[str],
    *,
    instability_mode: bool = False,
) -> SelectedAction:
    """
    Score each option by alignment, plausibility, tradeoff quality, novelty, risk budget.
    Returns SelectedAction.
    """
    if not options:
        raise ValueError("options must be non-empty")
    if len(options) == 1:
        opt = options[0]
        return SelectedAction(
            agent_id=agent_id,
            chosen_option_id=opt.option_id,
            action_name=opt.action_name,
            parameters=opt.parameters,
            short_reason="Only option available",
            uncertainty=opt.uncertainty,
        )

    scores: list[tuple[float, ActionOption]] = []
    for opt in options:
        score = 0.0
        # Alignment with goals (objectives: increase_X, decrease_X, etc.)
        for obj_key, weight in agent_objectives.items():
            if obj_key and weight > 0:
                if opt.action_name.lower().startswith("increase_") and "increase" in obj_key.lower():
                    score += weight * 0.5
                elif opt.action_name.lower().startswith("decrease_") and "decrease" in obj_key.lower():
                    score += weight * 0.5
                elif opt.action_name == obj_key or obj_key in opt.action_name:
                    score += weight * 0.5
        # Plausibility: lower uncertainty is better
        score += (1.0 - opt.uncertainty) * 0.3
        # Tradeoff quality: has expected_tradeoff (mention of downside)
        if opt.expected_tradeoff and len(opt.expected_tradeoff.strip()) > 5:
            score += 0.2
        # Novelty: penalize repeating last 2-3 actions
        if opt.action_name in last_actions[-3:]:
            score -= 0.3 * (last_actions[-3:].count(opt.action_name))
        # Risk budget: penalize bold when instability high
        if instability_mode and opt.style == "bold":
            score -= 0.4
        elif instability_mode and opt.style == "creative":
            score -= 0.2
        # Slight preference for safe when unstable
        if instability_mode and opt.style == "safe":
            score += 0.2
        scores.append((score, opt))

    scores.sort(key=lambda x: -x[0])
    best = scores[0][1]
    return SelectedAction(
        agent_id=agent_id,
        chosen_option_id=best.option_id,
        action_name=best.action_name,
        parameters=best.parameters,
        short_reason=f"Best alignment and risk-adjusted score (style={best.style})",
        uncertainty=best.uncertainty,
    )


def select_option(
    option_set: OptionSet | dict[str, Any],
    agent_objectives: dict[str, float],
    snapshot: dict[str, Any],
    last_actions: list[str],
    *,
    instability_mode: bool = False,
    llm_critic: Callable[..., Any] | None = None,
) -> SelectedAction:
    """
    Select one option from OptionSet. Uses rule-based by default; LLM critic if provided.
    """
    if isinstance(option_set, dict):
        options = []
        for o in option_set.get("options", []):
            if isinstance(o, dict):
                options.append(ActionOption(**o))
            else:
                options.append(o)
        agent_id = option_set.get("agent_id", "")
    else:
        options = list(option_set.options)
        agent_id = option_set.agent_id

    if llm_critic:
        try:
            result = _select_via_llm(llm_critic, options, agent_id, agent_objectives, snapshot, last_actions)
            if result:
                return result
        except Exception:
            pass

    return select_option_rule_based(
        options,
        agent_id,
        agent_objectives,
        snapshot,
        last_actions,
        instability_mode=instability_mode,
    )


def _select_via_llm(
    llm_critic: Callable[..., Any],
    options: list[ActionOption],
    agent_id: str,
    agent_objectives: dict[str, float],
    snapshot: dict[str, Any],
    last_actions: list[str],
) -> SelectedAction | None:
    """Low-temp LLM critic returns SelectedAction JSON only."""
    prompt = f"""Agent goals: {agent_objectives}
Recent actions: {last_actions}
Key state: {list((snapshot.get("variables") or snapshot.get("global_state") or {}).items())[:8]}

Options:
{chr(10).join(f"- {o.option_id}: {o.action_name} (style={o.style}) intent={o.intent} tradeoff={o.expected_tradeoff}" for o in options)}

Pick ONE option. Output JSON only: {{"chosen_option_id": "...", "action_name": "...", "parameters": {{}}, "short_reason": "<= 2 sentences", "uncertainty": 0.0-1.0}}"""
    out = llm_critic(prompt, system="You are a strategic critic. Output only valid JSON.", as_json=True)
    if not isinstance(out, dict):
        return None
    chosen_id = out.get("chosen_option_id")
    if not chosen_id:
        return None
    opt = next((o for o in options if o.option_id == chosen_id), None)
    if not opt:
        return None
    return SelectedAction(
        agent_id=agent_id,
        chosen_option_id=chosen_id,
        action_name=out.get("action_name", opt.action_name),
        parameters=out.get("parameters", opt.parameters),
        short_reason=str(out.get("short_reason", ""))[:500],
        uncertainty=float(out.get("uncertainty", opt.uncertainty)),
    )
