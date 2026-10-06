"""
Cafe report — a thin binding onto the shared bundle builder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from event_sim.wedge.report import TEMPLATE, render_html  # noqa: F401  (re-exported)
from event_sim.wedge.report import build_bundle as _build
from event_sim.wedge.report import write_report as _write
from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.wedge import CAFE_WEDGE


def build_bundle(baseline: CafeBaseline, *, comparison: Any = None, sensitivity: Any = None,
                 include_grid: bool = True) -> dict[str, Any]:
    return _build(CAFE_WEDGE, baseline, comparison=comparison, sensitivity=sensitivity,
                  include_grid=include_grid)


def write_report(baseline: CafeBaseline, out_dir: Path, *, include_grid: bool = True,
                 custom_elasticity: float | None = None,
                 reformulation_effectiveness: float | None = None) -> dict[str, Path]:
    return _write(CAFE_WEDGE, baseline, out_dir, include_grid=include_grid,
                  custom_elasticity=custom_elasticity,
                  reformulation_effectiveness=reformulation_effectiveness)
