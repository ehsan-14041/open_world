"""
Mechanism tests: falsify a structural hypothesis against real data, WITHOUT a simulation.

The Event Simulator's replays test the whole model at once, which makes them poor at
answering "is this one mechanism right?". A mechanism test isolates a single structural
claim and asks whether independently observed behaviour is consistent with it.

This package is deliberately independent of the simulator: it imports nothing from
`event_sim.engine` and never runs a world. A hypothesis that only looks good inside our own
engine has not been tested.
"""

from event_sim.mechanism.backlog_stock import (
    H2_PREDICTION,
    BacklogSeries,
    compare_h2,
    hysteresis_test,
    load_backlog_series,
    persistence_test,
)
from event_sim.mechanism.queue_stock import (
    CANDIDATES,
    QueueObservation,
    compare_candidates,
    fit_relaxation,
    fit_stock,
    implied_driver_growth,
    load_queue_series,
    shape_diagnostics,
)

__all__ = [
    "CANDIDATES",
    "H2_PREDICTION",
    "BacklogSeries",
    "compare_h2",
    "hysteresis_test",
    "load_backlog_series",
    "persistence_test",
    "QueueObservation",
    "compare_candidates",
    "fit_relaxation",
    "fit_stock",
    "implied_driver_growth",
    "load_queue_series",
    "shape_diagnostics",
]
