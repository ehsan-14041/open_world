"""
Cafe accounting — the shared identities, re-exported.

The identities themselves moved to `event_sim.wedge.accounting` when the shop and salon wedges
were added; they are unchanged, and the cafe passes no capacity limit, so the code path it
takes is exactly the one it always took.
"""

from __future__ import annotations

from event_sim.wedge.accounting import (  # noqa: F401  (re-exported)
    DAYS_PER_MONTH,
    Ledger,
    build_ledger,
    decision_metrics,
    runway_months,
)
