"""
Delta attribution: compute self_effect_per_agent from delta_raw_per_agent and delta_applied.
Handles sign conflicts and proportional allocation.
"""

from __future__ import annotations

from typing import Any

EPS = 1e-12


def compute_self_effect_per_agent(
    delta_raw_per_agent: dict[str, dict[str, float]],
    delta_after_merge: dict[str, float],
    delta_applied: dict[str, float],
) -> dict[str, dict[str, float]]:
    """
    Compute agent-attributed effects (self_effect) from raw deltas and applied deltas.
    - If delta_after_merge[var] != 0: proportional share by delta_raw[agent][var] / delta_after_merge[var]
    - If sign conflicts (cancellations): allocate by abs(delta_raw) / sum(abs(contribs))
    """
    self_effect: dict[str, dict[str, float]] = {agent: {} for agent in delta_raw_per_agent}

    for var, applied_val in delta_applied.items():
        if not isinstance(applied_val, (int, float)):
            continue
        applied_val = float(applied_val)

        merged = delta_after_merge.get(var, 0.0)
        if not isinstance(merged, (int, float)):
            merged = 0.0
        merged = float(merged)

        # Collect per-agent contributions for this var
        contribs: dict[str, float] = {}
        for agent, raw in delta_raw_per_agent.items():
            v = raw.get(var)
            if isinstance(v, (int, float)) and abs(float(v)) > EPS:
                contribs[agent] = float(v)

        if not contribs:
            continue

        sum_abs = sum(abs(c) for c in contribs.values())
        if sum_abs < EPS:
            continue

        # Sign conflicts: merged has different sign than some contribs, or |merged| < sum_abs
        has_sign_conflict = abs(merged) < sum_abs - EPS or (
            merged > 0 and any(c < 0 for c in contribs.values())
        ) or (merged < 0 and any(c > 0 for c in contribs.values()))

        if has_sign_conflict:
            # Allocate by absolute contribution share
            for agent, raw_val in contribs.items():
                share = abs(raw_val) / sum_abs
                self_effect[agent][var] = applied_val * share
        else:
            # Proportional: self_effect = delta_applied * (delta_raw / delta_after_merge)
            if abs(merged) < EPS:
                # Avoid div by zero; distribute equally
                n = len(contribs)
                for agent in contribs:
                    self_effect[agent][var] = applied_val / n
            else:
                for agent, raw_val in contribs.items():
                    self_effect[agent][var] = applied_val * (raw_val / merged)

    return self_effect


def merge_delta_raw(
    delta_raw_per_agent: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Merge per-agent raw deltas: delta_after_merge[var] = sum of delta_raw[*][var]."""
    merged: dict[str, float] = {}
    for agent, raw in delta_raw_per_agent.items():
        for var, val in raw.items():
            if isinstance(val, (int, float)):
                merged[var] = merged.get(var, 0.0) + float(val)
    return merged
