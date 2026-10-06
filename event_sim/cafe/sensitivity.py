"""
Cafe sensitivity — a thin binding onto the shared census.

The grid, the metric and the one-at-a-time analysis are shared; only the swept values and
their customer-facing labels are the cafe's own, and those live in `event_sim.cafe.wedge`.
"""

from __future__ import annotations

from typing import Any

from event_sim.wedge.sensitivity import (  # noqa: F401  (re-exported)
    DECISION_METRIC,
    SensitivityResult,
    SweepPoint,
)
from event_sim.wedge.sensitivity import run_sensitivity as _run
from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.wedge import CAFE_WEDGE, SWEEP, SWEEP_LABELS  # noqa: F401


def run_sensitivity(baseline: CafeBaseline, *, metric: str = DECISION_METRIC) -> SensitivityResult:
    return _run(CAFE_WEDGE, baseline, metric=metric)
