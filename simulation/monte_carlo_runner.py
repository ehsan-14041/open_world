"""
Batch Monte Carlo runner: N independent simulations with different seeds.
Aggregates variable trajectories and SSI for uncertainty and risk estimation.
"""

from __future__ import annotations

import random
from typing import Any

try:
    from simulation.loop import SimulationLoop
except ImportError:
    SimulationLoop = None  # type: ignore[misc, assignment]


def run_batch_monte_carlo(
    scenario_path: str | None = None,
    scenario_data: dict[str, Any] | None = None,
    steps: int = 5,
    n_runs: int = 10,
    seeds: list[int] | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run n_runs independent simulations (K steps each), each with its own seed.
    Returns: runs (list of per-run provenance/snapshots), summary (mean, std, q10, q90 per variable and SSI).
    """
    if SimulationLoop is None:
        return {"runs": [], "summary": {}}
    if seeds is None:
        rng = random.Random()
        seeds = [rng.randint(1, 2**31 - 1) for _ in range(n_runs)]
    else:
        n_runs = len(seeds)
    runs: list[dict[str, Any]] = []
    all_ssi: list[float] = []
    var_trajectories: dict[str, list[list[float]]] = {}

    for i, seed in enumerate(seeds[:n_runs]):
        try:
            import os
            env_before = os.environ.get("RANDOM_SEED")
            os.environ["RANDOM_SEED"] = str(seed)
            loop = SimulationLoop(
                scenario_path=scenario_path,
                scenario_data=scenario_data,
                dry_run=dry_run,
            )
            result = loop.run(steps=steps, return_provenance=True, return_turns=True, silent=True)
            if env_before is not None:
                os.environ["RANDOM_SEED"] = env_before
            else:
                os.environ.pop("RANDOM_SEED", None)
        except Exception:
            if env_before is not None:
                os.environ["RANDOM_SEED"] = env_before
            else:
                os.environ.pop("RANDOM_SEED", None)
            runs.append({"seed": seed, "error": True})
            continue
        final = result.get("final") or {}
        provenance = result.get("provenance") or []
        turns = result.get("turns") or []
        variables = final.get("variables") or final.get("global_state") or {}
        if isinstance(variables, dict):
            for var, val in variables.items():
                if isinstance(val, (int, float)):
                    if var not in var_trajectories:
                        var_trajectories[var] = []
                    var_trajectories[var].append(float(val))
        for p in provenance:
            ssi = p.get("ssi")
            if ssi is not None and isinstance(ssi, (int, float)):
                all_ssi.append(float(ssi))
        runs.append({"seed": seed, "final": final, "provenance": provenance, "turns": turns})

    def _agg(vals: list[float]) -> dict[str, float]:
        if not vals:
            return {"mean": 0.0, "std": 0.0, "q10": 0.0, "q90": 0.0}
        s = sorted(vals)
        n = len(s)
        mean = sum(s) / n
        variance = sum((x - mean) ** 2 for x in s) / n if n else 0
        std = variance ** 0.5
        q10 = s[int(0.1 * n)] if n else 0.0
        q90 = s[int(0.9 * (n - 1))] if n > 1 else s[0]
        return {"mean": mean, "std": std, "q10": q10, "q90": q90}

    summary: dict[str, Any] = {}
    if all_ssi:
        summary["ssi"] = _agg(all_ssi)
    for var, run_vals in var_trajectories.items():
        if run_vals:
            summary[f"variable_{var}"] = _agg(run_vals)
    return {"runs": runs, "summary": summary}
