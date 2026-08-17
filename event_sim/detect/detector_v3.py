"""
Detector v3 — occupancy anomaly detection plus an explicit coverage-regime model.

Detector v2's occupancy logic worked and is kept unchanged: a 14-day causal trailing baseline,
robust residual, threshold 3.0, persistence 4. On 170 unseen days it produced a median
residual of 0.0, drift of 0.33, and a tail frequency of 9.4% against a design target of ~10%.
There is no measurement reason to redesign it, so v3 imports it rather than restating it —
which also makes "unchanged" checkable rather than asserted.

What v2 lacked was a model of the *observation environment*. It could tell that a trigger
coincided with a coverage jump, but not whether that jump meant more ships or better sensors.
v3 adds that model, and adds it **beside** the occupancy statistic rather than inside it.

The temptation this module exists to refuse
-------------------------------------------

The obvious fix for a coverage-confounded trigger is to divide occupancy by the regional
vessel count, or to regress one on the other and call the residual the "true" queue. Both are
refused here, and not for stylistic reasons: either operation silently converts an observable
into a model-corrected latent quantity. The number would keep the name `anchorage_occupancy`
while no longer being anything anyone observed, and the correction would be un-auditable
because it would have been applied before anyone could see it.

So coverage is *context*. It classifies the day, it never edits the day's measurement.

    occupancy anomaly detector  +  independent coverage-regime classifier
                                ↓
                        candidate classification

Traffic change is not measurement change
----------------------------------------

A rise in `vessels_in_region` has at least three explanations: more traffic, better AIS
observation, or both. The classifier separates them by asking whether the *character* of
observation changed alongside the count:

  * more vessels, report density and spatial footprint steady   -> traffic (`gradual_shift`)
  * report density or footprint jumps                           -> observation regime change
  * count moves while character is also unsettled               -> `uncertain`, honestly

`uncertain` is a first-class outcome. A classifier that always decides is not more informative
than one that admits when it cannot.

Every constant is derived from the spent v1/v2 datasets and frozen before any v3 blind day was
acquired — see docs/replays/HAMPTON_ROADS_DETECTOR_V3_PROTOCOL.md.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Any, Sequence

from event_sim.detect.detector_v2 import (
    LOOKBACK_DAYS,
    MIN_LOOKBACK_PRESENT,
    PERSISTENCE_DAYS,
    RESIDUAL_THRESHOLD,
    SCALE_FLOOR,
    DayResidual,
    detect as detect_occupancy,
    residuals as occupancy_residuals,
    threshold_reachability,
)

__all__ = [
    "LOOKBACK_DAYS", "MIN_LOOKBACK_PRESENT", "PERSISTENCE_DAYS", "RESIDUAL_THRESHOLD",
    "SCALE_FLOOR", "detect_occupancy", "occupancy_residuals", "threshold_reachability",
    "CoverageRegime", "classify_regime", "classify_series", "window_regime",
    "WindowVerdict", "evaluate_validity",
]

# ---------------------------------------------------------------------------------------
# Frozen coverage-regime parameters
#
# Derived from |trailing residual| distributions over the spent v1/v2 data:
#
#   diagnostic             median   p75    p90    p95    max
#   vessels_in_region       1.29    2.50   3.67   4.50   10.00
#   messages_per_vessel     1.19    1.94   2.99   3.85    6.46
#   region_cells            1.17    2.23   3.85   4.62    9.10
# ---------------------------------------------------------------------------------------

#: Vessel-count movement that counts as a shift at all (~p90 of its residual).
V_SHIFT = 3.5

#: Report-density movement indicating the observation *character* changed (~p95).
M_ABRUPT = 4.0

#: Spatial-footprint movement indicating the observation *character* changed (~p95).
S_ABRUPT = 4.5

#: Below these, report density and footprint are "approximately steady" (~p75).
M_STABLE = 2.0
S_STABLE = 2.5

#: Days of one regime required for a trigger window to take that regime. An absolute count,
#: deliberately not a share: v2 failed on a share evaluated over 2 windows, where the statistic
#: could only take the values {0, 0.5, 1.0}.
WINDOW_REGIME_MIN_DAYS = 2


class CoverageRegime:
    STABLE = "stable"
    GRADUAL_SHIFT = "gradual_shift"
    ABRUPT_MEASUREMENT_SHIFT = "abrupt_measurement_shift"
    UNCERTAIN = "uncertain"

    #: Most severe last. Used to pick a window's regime.
    SEVERITY = (STABLE, GRADUAL_SHIFT, UNCERTAIN, ABRUPT_MEASUREMENT_SHIFT)


#: Candidate classification produced by pairing an occupancy trigger with a regime.
REGIME_TO_CANDIDATE = {
    CoverageRegime.STABLE: "candidate_port_anomaly",
    CoverageRegime.GRADUAL_SHIFT: "candidate_with_context",
    CoverageRegime.ABRUPT_MEASUREMENT_SHIFT: "measurement_confounded",
    CoverageRegime.UNCERTAIN: "uncertain",
}


@dataclass(frozen=True)
class RegimeDay:
    date: str
    regime: str
    vessel_residual: float | None
    density_residual: float | None
    footprint_residual: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_regime(
    vessel_residual: float | None,
    density_residual: float | None,
    footprint_residual: float | None,
) -> str:
    """Classify one day's observation environment from three trailing residuals.

    Order matters. A change in the character of observation outranks a change in its volume,
    because a sensor that started reporting differently invalidates the count it produces.
    """
    if vessel_residual is None or density_residual is None or footprint_residual is None:
        return CoverageRegime.UNCERTAIN

    v, m, s = abs(vessel_residual), abs(density_residual), abs(footprint_residual)

    if m >= M_ABRUPT or s >= S_ABRUPT:
        return CoverageRegime.ABRUPT_MEASUREMENT_SHIFT
    if v >= V_SHIFT and m < M_STABLE and s < S_STABLE:
        # More vessels, same observation character: traffic, not instrumentation.
        return CoverageRegime.GRADUAL_SHIFT
    if v >= V_SHIFT:
        # The count moved and the character is not clean enough to attribute it. Say so.
        return CoverageRegime.UNCERTAIN
    return CoverageRegime.STABLE


def classify_series(
    dates: Sequence[str],
    vessels: Sequence[float | None],
    density: Sequence[float | None],
    footprint: Sequence[float | None],
) -> list[RegimeDay]:
    """Per-day regimes, using the same causal trailing-residual machinery as occupancy."""
    v = occupancy_residuals(dates, vessels)
    m = occupancy_residuals(dates, density)
    s = occupancy_residuals(dates, footprint)
    return [
        RegimeDay(
            date=dates[i],
            regime=classify_regime(v[i].residual, m[i].residual, s[i].residual),
            vessel_residual=v[i].residual,
            density_residual=m[i].residual,
            footprint_residual=s[i].residual,
        )
        for i in range(len(dates))
    ]


def window_regime(regimes: Sequence[str]) -> str:
    """A window's regime: the most severe one occurring on at least WINDOW_REGIME_MIN_DAYS.

    Absolute day counts, never a share of windows. This is the specific defect that failed
    Detector v2, and the fix is structural rather than a different number.
    """
    counts = {r: list(regimes).count(r) for r in set(regimes)}
    for regime in reversed(CoverageRegime.SEVERITY):
        if counts.get(regime, 0) >= WINDOW_REGIME_MIN_DAYS:
            return regime
    return CoverageRegime.STABLE


@dataclass(frozen=True)
class WindowVerdict:
    start: str
    peak_date: str
    end: str
    duration_days: int
    peak_residual: float
    mean_residual: float
    peak_occupancy: float
    baseline_at_peak: float
    occupancy_trajectory: list[float]
    coverage_regime: str
    candidate_class: str
    regime_days: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_windows(
    windows: Sequence[Any], rows: Sequence[DayResidual], regimes: Sequence[RegimeDay]
) -> list[WindowVerdict]:
    by_date_regime = {r.date: r.regime for r in regimes}
    by_date_row = {r.date: r for r in rows}
    out: list[WindowVerdict] = []
    for w in windows:
        dates = [r.date for r in rows if w.start <= r.date <= w.end]
        day_regimes = [by_date_regime.get(d, CoverageRegime.UNCERTAIN) for d in dates]
        regime = window_regime(day_regimes)
        out.append(
            WindowVerdict(
                start=w.start,
                peak_date=w.peak_date,
                end=w.end,
                duration_days=w.duration_days,
                peak_residual=w.peak_residual,
                mean_residual=w.mean_residual,
                peak_occupancy=w.peak_occupancy,
                baseline_at_peak=w.baseline_at_peak,
                occupancy_trajectory=[
                    by_date_row[d].value for d in dates if d in by_date_row
                ],
                coverage_regime=regime,
                candidate_class=REGIME_TO_CANDIDATE[regime],
                regime_days={r: day_regimes.count(r) for r in sorted(set(day_regimes))},
            )
        )
    return out


# ---------------------------------------------------------------------------------------
# Pre-registered validity criteria — all evaluated at the DAY level
#
# v2's gate was a share over 2 windows, whose support was {0, 0.5, 1.0}. Every criterion here
# is a rate over evaluable days (n in the hundreds) or a structural property, so none of them
# degenerates at small trigger counts.
# ---------------------------------------------------------------------------------------

V2_MAX_TRIGGER_DAY_SHARE = 0.15
V3_MAX_UNCERTAIN_DAY_SHARE = 0.25
V4_MAX_ABRUPT_DAY_SHARE = 0.15
V6_MEDIAN_RESIDUAL_BOUND = 0.5
V6_MAX_THIRD_DRIFT = 1.0

#: Failure outcomes that mean the *measurement environment* is uninterpretable rather than
#: that this particular implementation has a narrow defect. Reaching one of these is the
#: project-level exit condition for Hampton Roads.
STOP_HAMPTON_ROADS_OUTCOMES = (
    "DETECTOR_V3_MEASUREMENT_UNSTABLE",
    "DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS",
)


def evaluate_validity(
    rows: Sequence[DayResidual],
    regimes: Sequence[RegimeDay],
    trigger_days: int,
) -> dict[str, Any]:
    """Apply the frozen criteria and map to an outcome. Pure function of the inputs."""
    defined = [r.residual for r in rows if r.residual is not None]
    evaluable = len(defined)
    if not evaluable:
        return {"outcome": "DETECTOR_V3_INCONCLUSIVE", "reason": "no defined residuals"}

    considered = [g for g in regimes if g.date in {r.date for r in rows if r.residual is not None}]
    counts = {r: sum(1 for g in considered if g.regime == r) for r in CoverageRegime.SEVERITY}

    uncertain_share = counts[CoverageRegime.UNCERTAIN] / evaluable
    abrupt_share = counts[CoverageRegime.ABRUPT_MEASUREMENT_SHIFT] / evaluable
    trigger_share = trigger_days / evaluable

    third = max(1, evaluable // 3)
    median_resid = statistics.median(defined)
    drift = abs(statistics.median(defined[:third]) - statistics.median(defined[-third:]))

    reach = threshold_reachability(rows)
    distinct_regimes = sum(1 for c in counts.values() if c)

    checks = {
        "V1_threshold_reachable": bool(reach["reachable"]),
        "V2_not_too_sensitive": trigger_share <= V2_MAX_TRIGGER_DAY_SHARE,
        "V3_interpretable": uncertain_share <= V3_MAX_UNCERTAIN_DAY_SHARE,
        "V4_measurement_stable": abrupt_share <= V4_MAX_ABRUPT_DAY_SHARE,
        "V5_classifier_discriminates": distinct_regimes >= 2,
        "V6_baseline_adapts": (
            abs(median_resid) <= V6_MEDIAN_RESIDUAL_BOUND and drift <= V6_MAX_THIRD_DRIFT
        ),
    }

    if not checks["V1_threshold_reachable"]:
        outcome = "DETECTOR_V3_TOO_INSENSITIVE"
    elif not checks["V2_not_too_sensitive"]:
        outcome = "DETECTOR_V3_TOO_SENSITIVE"
    elif not checks["V3_interpretable"]:
        outcome = "DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS"
    elif not (checks["V4_measurement_stable"] and checks["V5_classifier_discriminates"]):
        outcome = "DETECTOR_V3_MEASUREMENT_UNSTABLE"
    elif not checks["V6_baseline_adapts"]:
        outcome = "DETECTOR_V3_INCONCLUSIVE"
    else:
        outcome = "DETECTOR_V3_VALID"

    return {
        "outcome": outcome,
        "checks": checks,
        "evaluable_days": evaluable,
        "regime_counts": counts,
        "uncertain_day_share": round(uncertain_share, 4),
        "abrupt_day_share": round(abrupt_share, 4),
        "trigger_day_share": round(trigger_share, 4),
        "median_residual": round(median_resid, 4),
        "third_drift": round(drift, 4),
        "threshold_reachability": reach,
        "recommend_stop_hampton_roads": outcome in STOP_HAMPTON_ROADS_OUTCOMES,
    }
