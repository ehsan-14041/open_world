"""
Pre-declared detection rule and power criteria.

Every constant in this module is fixed **before** the baseline distribution has been
computed and before any continuous series has been acquired. They are expressed as functions
of robust baseline statistics rather than as absolute counts, so they can be written down
now without knowing what the numbers will turn out to be — which is the only way a threshold
can honestly be called pre-registered.

Changing any constant here after looking at candidate windows would invalidate the
detection. If a constant turns out to be wrong, the correct response is a separately named
rule with its own declaration, not an edit.

This module deliberately knows nothing about H1, the engine, the baseline world model, or
any historical event date. It sees a series of numbers and reports where they are unusual.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

# ---------------------------------------------------------------------------------------
# Frozen constants — declared before the baseline was computed
# ---------------------------------------------------------------------------------------

#: Level trigger. A day is "elevated" when occupancy >= median + K_LEVEL * max(MAD, MAD_FLOOR).
K_LEVEL = 4.0

#: MAD floor. Small-count series routinely produce MAD == 0, which would make any positive
#: deviation trigger. One vessel is the smallest change the metric can physically express,
#: so it is the smallest sensible unit of "unusual".
MAD_FLOOR = 1.0

#: Persistence. A candidate must stay elevated this many consecutive days. Set above the
#: 1-2 day scale on which anchorage occupancy naturally fluctuates, so that a transient does
#: not qualify as a disruption.
PERSISTENCE_DAYS = 5

#: Dwell trigger, applied to the p90 of completed spells in a candidate window relative to
#: the baseline p90.
K_DWELL = 2.0

# ---------------------------------------------------------------------------------------
# Frozen low-power criteria — any one of these stops the workflow
# ---------------------------------------------------------------------------------------

#: (a) the anchorage is essentially unused, so nothing can accumulate in it
LOW_POWER_MEDIAN_BELOW = 1.0
LOW_POWER_P90_BELOW = 3.0

#: (b) the rule cannot separate normal from abnormal, because normal days already fire
LOW_POWER_MAX_BASELINE_TRIGGER_RATE = 0.20

#: (c) missingness dominates
LOW_POWER_MAX_MISSING_RATE = 0.25

#: (d) dwell is unmeasurable because almost every spell is censored
LOW_POWER_MIN_COMPLETED_SPELLS = 10


@dataclass(frozen=True)
class Thresholds:
    """The concrete numbers this rule produces once a baseline exists."""

    level: float
    persistence_days: int
    dwell_p90: float | None
    baseline_median: float
    baseline_mad: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def thresholds_from(
    baseline_median: float, baseline_mad: float, baseline_dwell_p90: float | None = None
) -> Thresholds:
    """Turn baseline statistics into the concrete trigger level. Pure function of the
    frozen constants above — there is no free parameter left for an analyst to set."""
    effective_mad = max(baseline_mad, MAD_FLOOR)
    return Thresholds(
        level=baseline_median + K_LEVEL * effective_mad,
        persistence_days=PERSISTENCE_DAYS,
        dwell_p90=(baseline_dwell_p90 * K_DWELL if baseline_dwell_p90 else None),
        baseline_median=baseline_median,
        baseline_mad=baseline_mad,
    )


@dataclass(frozen=True)
class PowerVerdict:
    passed: bool
    reasons: tuple[str, ...]
    trigger_level: float
    baseline_trigger_rate: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def power_verdict(
    occupancy: Sequence[float],
    p90: float,
    median: float,
    mad: float,
    completed_spells: int,
    missing_rate: float,
) -> PowerVerdict:
    """Apply the frozen low-power criteria. Returns why it failed, not just that it did."""
    th = thresholds_from(median, mad)
    fired = sum(1 for v in occupancy if v >= th.level)
    rate = fired / len(occupancy) if occupancy else 1.0

    reasons: list[str] = []
    if median < LOW_POWER_MEDIAN_BELOW and p90 < LOW_POWER_P90_BELOW:
        reasons.append(
            f"anchorage essentially unused: median {median} < {LOW_POWER_MEDIAN_BELOW} "
            f"and p90 {p90} < {LOW_POWER_P90_BELOW}; nothing can accumulate"
        )
    if rate > LOW_POWER_MAX_BASELINE_TRIGGER_RATE:
        reasons.append(
            f"rule cannot separate normal from abnormal: {rate:.0%} of baseline days "
            f"already reach the trigger level {th.level}"
        )
    if missing_rate > LOW_POWER_MAX_MISSING_RATE:
        reasons.append(f"missingness dominates: {missing_rate:.0%} of sampled days absent")
    if completed_spells < LOW_POWER_MIN_COMPLETED_SPELLS:
        reasons.append(
            f"dwell unmeasurable: only {completed_spells} uncensored spells "
            f"(< {LOW_POWER_MIN_COMPLETED_SPELLS})"
        )

    return PowerVerdict(
        passed=not reasons,
        reasons=tuple(reasons),
        trigger_level=th.level,
        baseline_trigger_rate=round(rate, 4),
    )


@dataclass(frozen=True)
class AnomalyWindow:
    start: str
    peak_date: str
    end: str
    duration_days: int
    peak_occupancy: float
    mean_occupancy: float
    magnitude_over_threshold: float
    triggering_metric: str


def detect(
    dates: Sequence[str], occupancy: Sequence[float], thresholds: Thresholds
) -> list[AnomalyWindow]:
    """Find maximal runs of consecutive elevated days meeting the persistence requirement.

    Takes dates only to label its output. It has no calendar knowledge, no event list, and
    no way to prefer one part of the series over another.
    """
    if len(dates) != len(occupancy):
        raise ValueError("dates and occupancy must be the same length")

    windows: list[AnomalyWindow] = []
    run: list[int] = []

    for i in range(len(occupancy) + 1):
        elevated = i < len(occupancy) and occupancy[i] >= thresholds.level
        if elevated:
            run.append(i)
            continue
        if len(run) >= thresholds.persistence_days:
            peak_i = max(run, key=lambda j: occupancy[j])
            vals = [occupancy[j] for j in run]
            windows.append(
                AnomalyWindow(
                    start=dates[run[0]],
                    peak_date=dates[peak_i],
                    end=dates[run[-1]],
                    duration_days=len(run),
                    peak_occupancy=occupancy[peak_i],
                    mean_occupancy=round(sum(vals) / len(vals), 3),
                    magnitude_over_threshold=round(occupancy[peak_i] - thresholds.level, 3),
                    triggering_metric="anchorage_occupancy",
                )
            )
        run = []

    return windows
