"""
Detector v2 — trend-aware, causal, level-invariant.

Detector v1 assumed a stationary level and died of it: its pooled threshold of 29 vessels sat
above the maximum ever observed (26), so it could not fire, while 94% of the spread it was
built from was drift rather than day-to-day variation.

v2 replaces the single global level with a **local** one. Each day is compared against a
trailing robust baseline estimated from the days immediately before it, so a slow rise in
background anchorage utilisation moves the baseline with it and produces no signal. Only
deviations that are fast relative to the lookback survive.

Every constant here was chosen from the 56-day development set
(docs/replays/HAMPTON_ROADS_DETECTOR_V2_DATA_SPLIT.md) and frozen before any blind day was
downloaded. See HAMPTON_ROADS_DETECTOR_V2_PROTOCOL.md for the derivations.

Causality is the property to be most careful about. The baseline for day *t* uses the slice
``[t-LOOKBACK_DAYS, t-1]`` — strictly before *t*, never including it, and never centred. A
centred window would let the event being detected shape the baseline it is measured against,
which silently suppresses exactly the signal the detector exists to find.

This module imports nothing from H1, the engine, the world models, or any historical event
list, and contains no dates.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Any, Sequence

# ---------------------------------------------------------------------------------------
# Frozen parameters — derived from the development set, fixed before blind acquisition
# ---------------------------------------------------------------------------------------

#: Trailing window length, in days.
#:
#: Worst observed drift on the development set is 0.066 vessels/day. A trailing median sits
#: about (L+1)/2 days behind the present, so its lag bias is ~0.066 * 7.5 = 0.50 vessels at
#: L=14 — half the within-window deviation MAD of 1.0, and therefore small relative to the
#: noise it is measured against. L=28 would push that bias to ~0.96, i.e. a full MAD, and the
#: baseline would start reading drift as signal. L=14 also leaves 14 points for a stable
#: median and MAD, and gives the detector a 50% breakdown point: an elevated stretch of up to
#: 7 days cannot move the median of its own baseline window.
LOOKBACK_DAYS = 14

#: Minimum days that must actually be present in the lookback for a residual to be defined.
#: Below this the baseline is too thin to trust and the day simply cannot trigger.
MIN_LOOKBACK_PRESENT = 10

#: Scale floor, in vessels. A run of identical counts gives MAD 0, which would make any
#: positive deviation infinitely significant. One vessel is the smallest change the metric
#: can physically express, so it is the smallest sensible unit of surprise.
SCALE_FLOOR = 1.0

#: Residual threshold, in robust units.
#:
#: On the development set the distribution of |deviation from window median| has MAD 1.0,
#: p90 = 3 and max = 5. So 3.0 is the 90th percentile of ordinary daily deviation: unusual
#: for one day, not rare. Critically it is **inside** the empirically observed range (max 5.0)
#: — the specific failure of v1 was a threshold above anything that had ever happened.
RESIDUAL_THRESHOLD = 3.0

#: Consecutive days required above the threshold.
#:
#: The longest run of consecutive positive deviations anywhere in the development set is 3
#: days. Requiring 4 therefore demands a pattern the development period never produced, while
#: staying well under the 7-day breakdown limit implied by LOOKBACK_DAYS.
PERSISTENCE_DAYS = 4

#: Coverage-shock guard, in robust units, applied to the regional vessel count.
#:
#: AIS visibility grew 2.10x across the development period, so a rise in occupancy can be a
#: rise in what the sensors see rather than in what the port is doing. If regional deep-draft
#: presence jumps by this much on the same day, the day is marked a measurement anomaly.
#:
#: Deliberately a *flag*, not a correction: occupancy is never divided by the regional count.
#: Normalising would fold a measurement adjustment into the anomaly statistic, where it could
#: neither be audited nor switched off.
COVERAGE_GUARD_RESIDUAL = 3.0

#: A trigger window is reported as coverage-confounded when this share of its days carry the
#: measurement-anomaly flag.
COVERAGE_CONFOUND_SHARE = 0.5


@dataclass(frozen=True)
class DayResidual:
    date: str
    value: float | None
    expected: float | None
    scale: float | None
    residual: float | None
    lookback_present: int
    coverage_residual: float | None
    coverage_flag: bool

    @property
    def defined(self) -> bool:
        return self.residual is not None


@dataclass(frozen=True)
class TriggerWindow:
    start: str
    peak_date: str
    end: str
    duration_days: int
    peak_residual: float
    mean_residual: float
    peak_occupancy: float
    baseline_at_peak: float
    coverage_flagged_days: int
    coverage_confounded: bool
    triggering_metric: str = "anchorage_occupancy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _trailing(values: Sequence[float | None], i: int) -> tuple[float | None, float | None, int]:
    """Robust location and scale from the days strictly before `i`.

    The slice is ``[i - LOOKBACK_DAYS, i)``. Day `i` is excluded by construction, so the
    observation under test can never influence its own expectation.
    """
    lo = max(0, i - LOOKBACK_DAYS)
    window = [v for v in values[lo:i] if v is not None]
    if len(window) < MIN_LOOKBACK_PRESENT:
        return None, None, len(window)
    med = statistics.median(window)
    mad = statistics.median([abs(v - med) for v in window])
    return med, max(mad, SCALE_FLOOR), len(window)


def residuals(
    dates: Sequence[str],
    occupancy: Sequence[float | None],
    coverage: Sequence[float | None] | None = None,
) -> list[DayResidual]:
    """Standardised trailing residual for every day, plus the independent coverage residual.

    `dates` must be a contiguous daily axis; a missing observation is `None`, not a gap in the
    list, so that "no data" and "no vessels" stay distinguishable.
    """
    if len(dates) != len(occupancy):
        raise ValueError("dates and occupancy must be the same length")
    if coverage is not None and len(coverage) != len(dates):
        raise ValueError("coverage must be the same length as dates")

    out: list[DayResidual] = []
    for i, day in enumerate(dates):
        med, scale, present = _trailing(occupancy, i)
        value = occupancy[i]
        resid = (
            (value - med) / scale
            if (med is not None and scale is not None and value is not None)
            else None
        )

        cov_resid = None
        if coverage is not None:
            cmed, cscale, cpresent = _trailing(coverage, i)
            cval = coverage[i]
            if cmed is not None and cscale is not None and cval is not None:
                cov_resid = (cval - cmed) / cscale

        out.append(
            DayResidual(
                date=day,
                value=value,
                expected=med,
                scale=scale,
                residual=None if resid is None else round(resid, 4),
                lookback_present=present,
                coverage_residual=None if cov_resid is None else round(cov_resid, 4),
                coverage_flag=cov_resid is not None and cov_resid >= COVERAGE_GUARD_RESIDUAL,
            )
        )
    return out


def detect(rows: Sequence[DayResidual]) -> list[TriggerWindow]:
    """Maximal runs of consecutive days at or above the residual threshold.

    A day with an undefined residual breaks a run rather than extending it: an unmeasured day
    is not evidence of continued elevation.
    """
    windows: list[TriggerWindow] = []
    run: list[DayResidual] = []

    for i in range(len(rows) + 1):
        row = rows[i] if i < len(rows) else None
        elevated = (
            row is not None and row.residual is not None and row.residual >= RESIDUAL_THRESHOLD
        )
        if elevated:
            run.append(row)
            continue
        if len(run) >= PERSISTENCE_DAYS:
            windows.append(_window(run))
        run = []
    return windows


def _window(run: Sequence[DayResidual]) -> TriggerWindow:
    peak = max(run, key=lambda r: r.residual or 0.0)
    flagged = sum(1 for r in run if r.coverage_flag)
    return TriggerWindow(
        start=run[0].date,
        peak_date=peak.date,
        end=run[-1].date,
        duration_days=len(run),
        peak_residual=round(peak.residual or 0.0, 4),
        mean_residual=round(statistics.fmean([r.residual or 0.0 for r in run]), 4),
        peak_occupancy=peak.value if peak.value is not None else float("nan"),
        baseline_at_peak=round(peak.expected or 0.0, 4),
        coverage_flagged_days=flagged,
        coverage_confounded=flagged >= COVERAGE_CONFOUND_SHARE * len(run),
    )


def threshold_reachability(rows: Sequence[DayResidual]) -> dict[str, Any]:
    """Is the threshold inside the range the data actually produces?

    v1's threshold sat above every observation ever recorded, so its zero false-positive rate
    meant nothing. This reports the check explicitly rather than leaving it to be inferred
    from an absence of triggers.
    """
    defined = [r.residual for r in rows if r.residual is not None]
    if not defined:
        return {"reachable": False, "reason": "no defined residuals"}
    ordered = sorted(defined)
    above = sum(1 for v in defined if v >= RESIDUAL_THRESHOLD)
    return {
        "threshold": RESIDUAL_THRESHOLD,
        "max_observed_residual": round(max(defined), 4),
        "p99_residual": round(ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))], 4),
        "p95_residual": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 4),
        "days_at_or_above_threshold": above,
        "share_at_or_above_threshold": round(above / len(defined), 4),
        "reachable": max(defined) >= RESIDUAL_THRESHOLD,
    }
