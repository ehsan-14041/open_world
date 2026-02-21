"""
Noisy observation: agents observe real world state through a configurable noise filter.
observed_value = real_value + small_noise (Gaussian). noise_scale=0 for deterministic.
"""

from __future__ import annotations

import random
from typing import Any


def observe(
    world_snapshot: dict[str, Any],
    noise_scale: float = 0.0,
    rng: random.Random | None = None,
) -> dict[str, float]:
    """
    Read real variables from snapshot (variables or global_state) and add optional Gaussian noise.
    Returns dict of variable name -> observed value (float). noise_scale=0 gives deterministic output.
    """
    gs = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
    if not isinstance(gs, dict):
        return {}
    rng = rng or random.Random()
    out: dict[str, float] = {}
    for k, v in gs.items():
        if not isinstance(v, (int, float)):
            continue
        val = float(v)
        if noise_scale > 0:
            val = val + rng.gauss(0, noise_scale)
        out[k] = val
    return out
