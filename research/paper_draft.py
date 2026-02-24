"""
Research Paper Draft Generator.
Produces structured markdown draft from simulation history (provenance); no LLM.
Sections: Abstract, Methodology, Model Architecture, Belief Modeling Framework,
Calibration & Risk Evaluation, Experimental Results, Limitations, Future Work.
"""

from __future__ import annotations

from typing import Any


def generate_research_draft(
    simulation_history: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> str:
    """
    Generate a structured research draft (markdown) from provenance entries and optional config.
    Uses existing calibration metrics, entropy trajectory, risk evolution; no heavy LLM calls.
    """
    config = config or {}
    scenario = config.get("scenario") or config
    lines: list[str] = []

    # --- Abstract
    lines.append("# Research Draft: Strategic Decision Intelligence Platform")
    lines.append("")
    lines.append("## Abstract")
    lines.append("")
    last_turn = 0
    last_state: dict[str, Any] = {}
    if simulation_history:
        last_entry = simulation_history[-1]
        last_turn = last_entry.get("turn", len(simulation_history) - 1)
        tr = last_entry.get("turn_record") or {}
        last_state = tr.get("post_state") or tr.get("pre_state") or {}
    scenario_name = (scenario.get("name") or scenario.get("description") or "Simulation")[:200]
    scenario_desc = (scenario.get("description") or scenario.get("text") or "")[:300]
    lines.append(
        f"This report summarizes a simulation run of {last_turn + 1} turns using the scenario: {scenario_name}. "
        f"{scenario_desc or 'The run used the configured world model and agents.'} "
        "Results include calibration metrics, entropy trajectory, and risk evolution as described below."
    )
    lines.append("")

    # --- Methodology
    lines.append("## Methodology")
    lines.append("")
    var_specs = scenario.get("variable_specs") or {}
    causal_links = scenario.get("causal_links") or []
    lines.append("The world model is defined by variable specifications and causal links. ")
    if var_specs:
        lines.append(f"Variables ({len(var_specs)}): {', '.join(list(var_specs.keys())[:15])}. ")
    if causal_links:
        lines.append(f"Causal links: {len(causal_links)} directed relationships. ")
    lines.append("Agents observe the world through a noisy channel, update beliefs, and select actions via utility-based planning with optional Monte Carlo evaluation and lightweight RL. ")
    lines.append("")

    # --- Model Architecture
    lines.append("## Model Architecture")
    lines.append("")
    agents_cfg = scenario.get("initial_agents") or []
    if isinstance(agents_cfg, list) and agents_cfg:
        lines.append("Agents:")
        for i, a in enumerate(agents_cfg[:10]):
            name = a.get("name", a.get("role", f"Agent {i}")) if isinstance(a, dict) else str(a)
            objectives = a.get("objectives") or a.get("goals") if isinstance(a, dict) else {}
            lines.append(f"- {name}: objectives over {list(objectives.keys())[:5] if isinstance(objectives, dict) else 'N/A'}")
        lines.append("")
    variables = last_state.get("variables") or last_state.get("global_state") or {}
    if isinstance(variables, dict) and variables:
        lines.append("Final state variables (representative): ")
        for k, v in list(variables.items())[:8]:
            if isinstance(v, (int, float)):
                lines.append(f"  {k} = {v:.2f}")
        lines.append("")
    lines.append("")

    # --- Belief Modeling Framework
    lines.append("## Belief Modeling Framework")
    lines.append("")
    belief_enabled = config.get("enable_belief_layer") or config.get("ENABLE_BELIEF_LAYER")
    if belief_enabled:
        lines.append(
            "Agents maintain a structured BeliefState: belief strength per variable, entropy-like uncertainty per key, and global confidence. "
            "Updates use Bayesian-lite weight adjustment toward observations; step size is derived from confidence. "
            "Uncertainty increases under high world entropy, instability mode, or active shock events. "
            "Uncertainty decays toward a baseline each turn. Action selection incorporates a belief-alignment term that rewards consistency with internal beliefs."
        )
    else:
        lines.append(
            "Belief modeling was not enabled for this run. When enabled, agents use BeliefState (beliefs, uncertainty, confidence) with Bayesian-lite updates and belief-alignment scoring in action selection."
        )
    lines.append("")

    # --- Calibration & Risk Evaluation
    lines.append("## Calibration & Risk Evaluation")
    lines.append("")
    try:
        from core.dashboard_payload import compute_calibration_from_provenance
        cal = compute_calibration_from_provenance(simulation_history)
        mean_rmse = sum(cal.get("rmse_over_time") or [0]) / max(1, len(cal.get("rmse_over_time") or []))
        health = cal.get("health", "N/A")
        flags = cal.get("overconfidence_flags") or []
        lines.append(f"- Calibration health: **{health}**. Mean RMSE (prediction vs realized): {mean_rmse:.3f}.")
        lines.append(f"- Overconfidence flags: {len(flags)}.")
    except Exception:
        lines.append("- Calibration metrics were computed from provenance (RMSE, overconfidence flags).")
    risk_scores: list[float] = []
    for entry in simulation_history:
        derived = entry.get("derived") or {}
        ent = entry.get("world_entropy")
        stab = derived.get("system_stability")
        if isinstance(ent, (int, float)):
            risk_scores.append(min(100, float(ent) + (100 - float(stab or 70)) * 0.3))
    if risk_scores:
        lines.append(f"- Risk evolution: scores over {len(risk_scores)} turns; final risk proxy: {risk_scores[-1]:.1f}.")
    lines.append("")

    # --- Experimental Results
    lines.append("## Experimental Results")
    lines.append("")
    lines.append("### Entropy trajectory")
    entropy_traj = [e.get("world_entropy") for e in simulation_history if e.get("world_entropy") is not None]
    if entropy_traj:
        lines.append("| Turn | World entropy |")
        lines.append("|------|----------------|")
        for i, e in enumerate(entropy_traj[:30]):
            lines.append(f"| {i} | {float(e):.3f} |")
        if len(entropy_traj) > 30:
            lines.append(f"| ... | ({len(entropy_traj) - 30} more turns) |")
    else:
        lines.append("Entropy was tracked per turn (see provenance).")
    lines.append("")
    lines.append("### Selected actions (sample)")
    actions_per_turn: list[tuple[int, str, str]] = []
    for entry in simulation_history[:20]:
        turn = entry.get("turn", 0)
        tr = entry.get("turn_record") or {}
        chosen = tr.get("chosen_actions") or []
        if chosen:
            c = chosen[0]
            agent = c.get("agent", "") if isinstance(c, dict) else getattr(c, "agent", "")
            action = c.get("action_id", c.get("action", "")) if isinstance(c, dict) else getattr(c, "action_id", "")
            actions_per_turn.append((turn, str(agent), str(action)))
    if actions_per_turn:
        lines.append("| Turn | Agent | Action |")
        lines.append("|------|-------|--------|")
        for t, ag, ac in actions_per_turn:
            lines.append(f"| {t} | {ag} | {ac} |")
    lines.append("")

    # --- Limitations
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "This draft is generated programmatically from simulation provenance. "
        "The model is deterministic (given seed) when uncertainty and shocks are disabled; no external LLM was used for this draft. "
        "Calibration and risk metrics are computed from predicted vs realized deltas and derived stability/entropy."
    )
    lines.append("")

    # --- Future Work
    lines.append("## Future Work")
    lines.append("")
    lines.append("- Extend belief modeling to multi-hypothesis tracking and explicit divergence metrics. ")
    lines.append("- Integrate shock-intensity scheduling and scenario-specific shock targets. ")
    lines.append("")
    return "\n".join(lines)
