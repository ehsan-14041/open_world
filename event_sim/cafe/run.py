"""
Cafe comparison — a thin binding onto the shared wedge machinery.

The cafe was the reference implementation, and the code that ran it now lives in
`event_sim.wedge` so the shop and the salon run through exactly the same path. This module
keeps the cafe's own entry points so existing callers and tests are unaffected.
"""

from __future__ import annotations

from typing import Any

from event_sim.wedge.compare import (  # noqa: F401  (re-exported)
    Comparison,
    WorldResult,
    run_comparison as _run,
    shared_fingerprint as _shared_fingerprint_impl,
    wedge_slice,
)
from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.wedge import CAFE_WEDGE, DEFAULT_AXES  # noqa: F401
from event_sim.cafe.worlds import REFORMULATION_EFFECTIVENESS


def _slice(custom_elasticity: float | None):
    return wedge_slice(CAFE_WEDGE, custom_elasticity)


def _shared_fingerprint(slice_, cfg) -> str:
    return _shared_fingerprint_impl(slice_, cfg)


def run_comparison(
    baseline: CafeBaseline,
    *,
    axis_settings: dict[str, str] | None = None,
    reformulation_effectiveness: float = REFORMULATION_EFFECTIVENESS,
    custom_elasticity: float | None = None,
) -> Comparison:
    return _run(
        CAFE_WEDGE,
        baseline,
        axis_settings=axis_settings,
        custom_elasticity=custom_elasticity,
        reformulation_effectiveness=reformulation_effectiveness,
    )
