"""
Ensemble runner for the Robustness & Failure-Mode engine.

Runs the EXISTING SimulationLoop N times, each with a perturbed scenario, and
collects per-run trajectories. Does not modify the loop. Each member is a fresh,
independent SimulationLoop instance.

Note on concurrency: SimulationLoop.run() touches process-global state
(narrative memory, versioning), so members are run sequentially by default to
keep results clean and reproducible. `max_workers` is accepted for forward
compatibility but sequential execution is used when global-state safety matters.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from simulation.loop import SimulationLoop
from simulation.perturbation import perturb_scenario, DEFAULT_PERTURB_CONFIG
from core.narrative_engine import classify_outcome, _get_goal_vars_and_direction_for_agent


@dataclass
class RunResult:
    run_id: int
    perturbation: dict[str, float]
    trajectory: list[dict[str, Any]]       # per-turn post_state
    final_state: dict[str, Any]
    regime_sequence: list[str]
    outcome_label: str
    goal_score: float
    perturbed_initial_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "perturbation": self.perturbation,
            "regime_sequence": self.regime_sequence,
            "outcome_label": self.outcome_label,
            "goal_score": self.goal_score,
            "final_state": self.final_state,
        }


def _extract_state(snapshot: dict[str, Any]) -> dict[str, float]:
    """Pull the numeric variable map from a snapshot (variables or global_state)."""
    if not isinstance(snapshot, dict):
        return {}
    vars_ = snapshot.get("variables")
    if not isinstance(vars_, dict):
        vars_ = snapshot.get("global_state") or {}
    return {k: float(v) for k, v in vars_.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def aggregate_goal_vars(scenario: dict[str, Any]) -> list[tuple[str, int]]:
    """Aggregate (var, direction) goal tuples across all agents in the scenario."""
    seen: set[tuple[str, int]] = set()
    goals: list[tuple[str, int]] = []
    for agent in (scenario or {}).get("initial_agents") or []:
        if not isinstance(agent, dict):
            continue
        agent_goals = {
            "objectives": agent.get("objectives") or {},
            "long_term_goals": agent.get("long_term_goals") or [],
        }
        for pair in _get_goal_vars_and_direction_for_agent(agent_goals):
            if pair not in seen:
                seen.add(pair)
                goals.append(pair)
    return goals


def run_member(
    scenario: dict[str, Any],
    *,
    run_id: int,
    seed: int,
    steps: int,
    dry_run: bool,
    perturb_config: dict[str, float] | None,
    goal_vars: list[tuple[str, int]],
    base_initial: dict[str, float] | None = None,
    delay_between_rounds: float = 0.0,
) -> RunResult:
    """Run a single perturbed simulation and extract a RunResult."""
    rng = random.Random(seed)
    perturbed, record = perturb_scenario(scenario, rng, perturb_config)

    # SimulationLoop consumes the GLOBAL `random` module (drift/shock draws), so seed
    # it per member to make the whole ensemble reproducible. Also seed numpy if present.
    random.seed(seed)
    try:
        import numpy as _np  # type: ignore
        _np.random.seed(seed % (2**32 - 1))
    except Exception:
        pass

    loop = SimulationLoop(scenario_data=perturbed, dry_run=dry_run)
    res = loop.run(
        steps=steps,
        return_turns=True,
        return_provenance=True,
        silent=True,
        delay_between_rounds=delay_between_rounds,
    )

    provenance = res.get("provenance") or []
    trajectory: list[dict[str, Any]] = []
    regime_sequence: list[str] = []
    for pe in provenance:
        tr = (pe.get("turn_record") or {}) if isinstance(pe, dict) else {}
        post = tr.get("post_state") or {}
        trajectory.append(_extract_state(post) if post else {})
        regime_sequence.append(str(pe.get("regime", "NORMAL")) if isinstance(pe, dict) else "NORMAL")

    initial_state = _extract_state({"variables": perturbed.get("initial_state") or {}})
    final_state = _extract_state(res.get("final") or {})

    delta_total: dict[str, float] = {}
    for var, fv in final_state.items():
        iv = initial_state.get(var)
        if isinstance(iv, (int, float)):
            delta_total[var] = fv - iv

    # Scale-invariant goal score: sum *percent* changes, normalized by the BASE
    # (unperturbed) initial value — constant across runs — so perturbing a goal
    # variable's start does not create a spurious denominator correlation in the
    # pivotal-assumption step. delta is the actual move from the perturbed start.
    base_initial = base_initial or initial_state
    goal_score = 0.0
    for var, direction in goal_vars:
        d = delta_total.get(var)
        bv = base_initial.get(var)
        if isinstance(d, (int, float)) and isinstance(bv, (int, float)):
            denom = abs(bv) if abs(bv) > 1e-9 else 1.0
            goal_score += (float(d) / denom) * direction

    final_regime = regime_sequence[-1] if regime_sequence else "NORMAL"
    try:
        outcome = classify_outcome(delta_total, goal_vars, scenario, final_regime).get("outcome", "")
    except Exception:
        outcome = ""

    return RunResult(
        run_id=run_id,
        perturbation=record,
        trajectory=trajectory,
        final_state=final_state,
        regime_sequence=regime_sequence,
        outcome_label=str(outcome),
        goal_score=goal_score,
        perturbed_initial_state=initial_state,
    )


def run_ensemble(
    scenario: dict[str, Any],
    *,
    runs: int = 20,
    steps: int = 5,
    dry_run: bool = True,
    perturb_config: dict[str, float] | None = None,
    base_seed: int = 1000,
    max_workers: int = 1,
    delay_between_rounds: float = 0.0,
    inter_member_delay: float = 0.0,
) -> list[RunResult]:
    """
    Run `runs` perturbed members of `scenario`. Returns a list of RunResult.

    Reproducible: same (scenario, base_seed, perturb_config) -> identical results.
    Members run sequentially for global-state safety (see module docstring).

    Rate-limit control (live/LLM mode): `delay_between_rounds` spaces out the per-turn
    LLM calls inside each run, and `inter_member_delay` (with light jitter) spaces out
    the runs themselves, so an ensemble of LLM runs does not burst into HTTP 429s.
    Both default to 0.0 (dry-run needs no throttling).
    """
    cfg = {**DEFAULT_PERTURB_CONFIG, **(perturb_config or {})}
    goal_vars = aggregate_goal_vars(scenario)
    base_initial = _extract_state({"variables": (scenario or {}).get("initial_state") or {}})
    members: list[RunResult] = []
    n = max(1, runs)
    for i in range(n):
        if inter_member_delay > 0 and i > 0:
            # jittered backoff between runs (random.Random is seeded per member inside
            # run_member, so use the module random here for jitter only)
            import random as _r
            time.sleep(inter_member_delay * (0.75 + 0.5 * _r.random()))
        member = run_member(
            scenario,
            run_id=i,
            seed=base_seed + i,
            steps=steps,
            dry_run=dry_run,
            perturb_config=cfg,
            goal_vars=goal_vars,
            base_initial=base_initial,
            delay_between_rounds=delay_between_rounds,
        )
        members.append(member)
    return members
