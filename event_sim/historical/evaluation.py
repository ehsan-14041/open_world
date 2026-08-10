"""
Replay evaluation: score a simulated envelope against what actually happened.

Design decisions that matter more than the arithmetic:

- **No single global R².** A disruption trajectory is judged on questions a planner would
  actually ask: did it move the right way, when did it peak, how far off was the peak, did
  recovery come too early or too late. Those are reported per variable.
- **Only `observed` points are scored.** Context points (used to initialise the model) and
  anything weaker than a measurement are excluded, so the model cannot be graded against
  its own starting condition. If nothing scoreable remains, this module raises rather than
  returning a flattering empty result.
- **Envelope coverage is not a probability.** Coverage says the observed path fell inside
  the range of tested assumption combinations. That range is a designed grid, not a
  calibrated distribution, so coverage is never reported as a confidence level.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from event_sim.schemas import HistoricalObservation, ObservedMilestone


class InsufficientObservationsError(ValueError):
    """Raised when there is nothing gradeable — never silently return a score of zero."""


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _scoreable(observations: Sequence[HistoricalObservation]) -> tuple[list[HistoricalObservation], list[dict[str, Any]]]:
    kept, skipped = [], []
    for obs in observations:
        if obs.is_scoreable():
            kept.append(obs)
        else:
            skipped.append({
                "variable": obs.variable, "turn": obs.turn,
                "status": obs.status, "reason": "not a scoreable observation",
            })
    return kept, skipped


def _direction(values: Sequence[float]) -> str:
    if len(values) < 2:
        return "flat"
    delta = values[-1] - values[0]
    if delta > 1e-9:
        return "up"
    if delta < -1e-9:
        return "down"
    return "flat"


def _peak_index(values: Sequence[float], baseline: float) -> int:
    """Index of the largest absolute departure from baseline."""
    if not values:
        return 0
    return max(range(len(values)), key=lambda i: abs(values[i] - baseline))


def _correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


# --------------------------------------------------------------------------------------
# Per-variable metrics
# --------------------------------------------------------------------------------------


def envelope_coverage(
    envelope: dict[str, Any],
    observations: Sequence[HistoricalObservation],
    *, tolerance: float = 0.0,
) -> dict[str, Any]:
    """
    Share of observed points inside the simulated envelope, plus where it first escaped.

    `tolerance` widens the band by a fraction of its own width before testing; report it
    whenever it is non-zero, because a widened band is a weaker claim.
    """
    variable = envelope.get("variable")
    points = sorted((o for o in observations if o.variable == variable), key=lambda o: o.turn)
    inside, outside = 0, []
    first_divergence: int | None = None
    widths: list[float] = []

    for obs in points:
        turn = obs.turn
        if turn >= len(envelope.get("low", [])):
            continue
        low, high = float(envelope["low"][turn]), float(envelope["high"][turn])
        widths.append(high - low)
        pad = (high - low) * tolerance
        if low - pad <= obs.value <= high + pad:
            inside += 1
        else:
            distance = (obs.value - high) if obs.value > high else (low - obs.value)
            outside.append({
                "turn": turn, "date": obs.date, "observed": obs.value,
                "envelope": [low, high], "distance": distance,
                "direction": "above" if obs.value > high else "below",
            })
            if first_divergence is None:
                first_divergence = turn

    scored = inside + len(outside)
    return {
        "variable": variable,
        "scored_points": scored,
        "inside": inside,
        "outside": outside,
        "coverage_rate": (inside / scored) if scored else None,
        "first_divergence_turn": first_divergence,
        "mean_envelope_width": (sum(widths) / len(widths)) if widths else None,
        "tolerance": tolerance,
        "interpretation": (
            "Coverage means the observed path fell inside the range of tested assumption "
            "combinations. It is not a probability and not a confidence level."
        ),
    }


def trajectory_metrics(
    envelope: dict[str, Any],
    observations: Sequence[HistoricalObservation],
    *, baseline: float | None = None,
) -> dict[str, Any]:
    """
    Shape metrics against the envelope median: direction, peak magnitude and timing,
    recovery timing, MAE, normalised MAE and correlation.

    Every metric is computed only on turns where an observation exists, and each is
    returned as None rather than 0 when there are too few points to support it — an absent
    metric is more useful than a fabricated one.
    """
    variable = envelope.get("variable")
    median = envelope.get("median") or []
    points = sorted((o for o in observations if o.variable == variable), key=lambda o: o.turn)
    points = [p for p in points if 0 <= p.turn < len(median)]

    if not points:
        return {"variable": variable, "scored_points": 0, "note": "no scoreable observations"}

    obs_values = [p.value for p in points]
    sim_values = [float(median[p.turn]) for p in points]
    turns = [p.turn for p in points]
    base = float(baseline if baseline is not None else (median[0] if median else obs_values[0]))

    errors = [abs(o - s) for o, s in zip(obs_values, sim_values)]
    mae = sum(errors) / len(errors)
    obs_span = max(obs_values) - min(obs_values)
    observed_range = abs(obs_span) if abs(obs_span) > 1e-9 else None

    obs_peak_i = _peak_index(obs_values, base)
    sim_peak_i = _peak_index(sim_values, base)

    out: dict[str, Any] = {
        "variable": variable,
        "scored_points": len(points),
        "observed_turns": turns,
        "observed": obs_values,
        "simulated_median": sim_values,
        "direction_observed": _direction(obs_values),
        "direction_simulated": _direction(sim_values),
        "direction_match": _direction(obs_values) == _direction(sim_values),
        "mae": mae,
        "normalized_mae": (mae / observed_range) if observed_range else None,
        "correlation": _correlation(obs_values, sim_values),
        "baseline_used": base,
        "observed_peak": {"turn": turns[obs_peak_i], "value": obs_values[obs_peak_i],
                          "departure_from_baseline": obs_values[obs_peak_i] - base},
        "simulated_peak": {"turn": turns[sim_peak_i], "value": sim_values[sim_peak_i],
                           "departure_from_baseline": sim_values[sim_peak_i] - base},
        "peak_timing_error_turns": turns[sim_peak_i] - turns[obs_peak_i],
        "peak_magnitude_error": sim_values[sim_peak_i] - obs_values[obs_peak_i],
    }

    obs_recovery = _recovery_turn(turns, obs_values, base)
    sim_recovery = _recovery_turn(turns, sim_values, base)
    out["observed_recovery_turn"] = obs_recovery
    out["simulated_recovery_turn"] = sim_recovery
    out["recovery_timing_error_turns"] = (
        (sim_recovery - obs_recovery) if (obs_recovery is not None and sim_recovery is not None) else None
    )
    if obs_recovery is None:
        out["recovery_note"] = "observed series had not returned toward baseline within the window"
    return out


def _recovery_turn(turns: Sequence[int], values: Sequence[float], baseline: float,
                   *, threshold: float = 0.25) -> int | None:
    """
    First turn after the peak at which the series has come back within `threshold` of its
    peak departure from baseline. None when it never does inside the window.
    """
    if not values:
        return None
    peak_i = _peak_index(values, baseline)
    peak_departure = values[peak_i] - baseline
    if abs(peak_departure) < 1e-9:
        return None
    for i in range(peak_i + 1, len(values)):
        if abs(values[i] - baseline) <= abs(peak_departure) * threshold:
            return turns[i]
    return None


# --------------------------------------------------------------------------------------
# Whole-replay evaluation
# --------------------------------------------------------------------------------------


def evaluate_replay(
    replay: dict[str, Any],
    observations: Sequence[HistoricalObservation],
    *, tolerance: float = 0.0,
) -> dict[str, Any]:
    """
    Score a replay. Raises InsufficientObservationsError when nothing is scoreable, rather
    than returning a meaningless perfect result.
    """
    scored, skipped = _scoreable(observations)
    if not scored:
        raise InsufficientObservationsError(
            f"No scoreable observations ({len(skipped)} records skipped: context points and "
            f"non-observed values are never graded). Historical validation requires real "
            f"measured series; see event_sim/historical/observations/README.md."
        )

    slice_ = replay.get("slice")
    per_variable: list[dict[str, Any]] = []
    for variable, envelope in (replay.get("envelope") or {}).items():
        points = [o for o in scored if o.variable == variable]
        if not points:
            continue
        var_def = slice_.variable(variable) if slice_ is not None else None
        baseline = var_def.baseline if var_def is not None else None
        coverage = envelope_coverage(envelope, points, tolerance=tolerance)
        metrics = trajectory_metrics(envelope, points, baseline=baseline)
        per_variable.append({**coverage, "trajectory": metrics,
                             "unit": (var_def.unit if var_def else ""),
                             "sources": sorted({p.source for p in points if p.source})})

    evaluated_vars = {r["variable"] for r in per_variable}
    all_vars = set((replay.get("envelope") or {}).keys())
    total_scored = sum(int(r["scored_points"]) for r in per_variable)
    total_inside = sum(int(r["inside"]) for r in per_variable)
    divergences = [r["first_divergence_turn"] for r in per_variable if r["first_divergence_turn"] is not None]

    return {
        "episode": (replay.get("episode") or {}).get("id"),
        "world_count": replay.get("world_count"),
        "variables": per_variable,
        "evaluated_variables": sorted(evaluated_vars),
        "unevaluated_variables": sorted(all_vars - evaluated_vars),
        "scored_points": total_scored,
        "skipped_records": skipped,
        "overall_coverage_rate": (total_inside / total_scored) if total_scored else None,
        "first_divergence_turn": (min(divergences) if divergences else None),
        "framing": (
            "Containment, direction and timing against observed history. This is a "
            "falsification test of the model's assumption range, not a forecast accuracy "
            "score, and it covers only the variables for which observations exist."
        ),
        "warning": (
            f"Only {len(evaluated_vars)} of {len(all_vars)} variables could be evaluated. "
            f"Unevaluated: {sorted(all_vars - evaluated_vars)}."
            if evaluated_vars != all_vars else ""
        ),
    }


# --------------------------------------------------------------------------------------
# Milestone (timing) evaluation
# --------------------------------------------------------------------------------------


def _milestone_turn(
    series: Sequence[float],
    milestone: ObservedMilestone,
    baseline: float,
    *, shock_turn: int = 1,
) -> int | None:
    """When the simulated series hits a milestone, or None if it never does in the window."""
    if not series:
        return None
    kind = milestone.kind
    if kind == "peak":
        return max(range(len(series)), key=lambda i: abs(series[i] - baseline))
    if kind == "threshold_cross_up" and milestone.threshold is not None:
        return next((i for i, v in enumerate(series) if v >= milestone.threshold), None)
    if kind == "threshold_cross_down" and milestone.threshold is not None:
        return next((i for i, v in enumerate(series) if v <= milestone.threshold), None)
    # recovery_to_baseline
    band = abs(baseline) * milestone.tolerance
    return next(
        (i for i in range(shock_turn, len(series)) if abs(series[i] - baseline) <= band),
        None,
    )


def milestone_evaluation(
    replay: dict[str, Any],
    milestones: Sequence[ObservedMilestone],
) -> dict[str, Any]:
    """
    Test the model in the TIME dimension: for each dated milestone, when does each swept
    world reach it, and does the observed date fall inside that range?

    This is the counterpart to `envelope_coverage`, which can only test levels. A model can
    sit inside a level envelope while being badly wrong about when things happen — and the
    Yantian replay showed that is the failure mode that actually matters here.
    """
    slice_ = replay.get("slice")
    worlds = replay.get("worlds") or []
    scored = [m for m in milestones if m.is_scoreable()]
    reported = [m for m in milestones if not m.is_scoreable()]

    rows: list[dict[str, Any]] = []
    for milestone in list(scored) + list(reported):
        var_def = slice_.variable(milestone.variable) if slice_ is not None else None
        baseline = var_def.baseline if var_def is not None else 0.0
        turns: list[int] = []
        never = 0
        for world in worlds:
            series = world.get("series", {}).get(milestone.variable)
            if not series:
                continue
            turn = _milestone_turn(series, milestone, baseline)
            if turn is None:
                never += 1
            else:
                turns.append(turn)
        if not turns:
            rows.append({
                "milestone": milestone.id, "variable": milestone.variable,
                "kind": milestone.kind, "observed_turn": milestone.observed_turn,
                "date": milestone.date, "status": milestone.status,
                "simulated": None,
                "note": "no simulated world reached this milestone inside the window",
            })
            continue
        turns.sort()
        median = turns[len(turns) // 2]
        inside = turns[0] <= milestone.observed_turn <= turns[-1]
        # "Inside the envelope" is a weak statement when the observed value sits at the
        # extreme edge. The share of tested worlds at or beyond the observed date says how
        # much of the assumption space the real world actually needed.
        at_or_beyond = sum(1 for t in turns if t >= milestone.observed_turn) + never
        share_beyond = at_or_beyond / (len(turns) + never) if (turns or never) else 0.0
        rows.append({
            "milestone": milestone.id,
            "variable": milestone.variable,
            "kind": milestone.kind,
            "observed_turn": milestone.observed_turn,
            "date": milestone.date,
            "status": milestone.status,
            "source": milestone.source,
            "simulated": {"earliest": turns[0], "median": median, "latest": turns[-1],
                          "worlds_never_reaching": never},
            "timing_error_turns": median - milestone.observed_turn,
            "observed_inside_envelope": inside,
            "worlds_at_or_beyond_observed": at_or_beyond,
            "share_of_worlds_at_or_beyond_observed": share_beyond,
            "verdict": (
                ("inside, but at the extreme edge" if share_beyond <= 0.1 else "inside")
                if inside
                else ("simulated too early" if turns[-1] < milestone.observed_turn
                      else "simulated too late")
            ),
            "scored": milestone.is_scoreable(),
            "note": milestone.note,
        })

    graded = [r for r in rows if r.get("scored") and r.get("simulated")]
    return {
        "milestones": rows,
        "scored_count": len(graded),
        "inside_count": sum(1 for r in graded if r["observed_inside_envelope"]),
        "median_timing_error_turns": (
            sorted(r["timing_error_turns"] for r in graded)[len(graded) // 2] if graded else None
        ),
        "framing": (
            "Timing test. The simulated range is the spread across tested assumption "
            "combinations, not a confidence interval. A negative timing error means the "
            "model reached the milestone earlier than the real world did."
        ),
    }


def directional_accuracy(
    envelope: dict[str, Any],
    observations: Sequence[HistoricalObservation],
) -> dict[str, Any]:
    """Turn-over-turn direction agreement between the envelope median and observation."""
    variable = envelope.get("variable")
    points = sorted((o for o in observations if o.variable == variable), key=lambda o: o.turn)
    median = envelope.get("median") or []
    if len(points) < 2:
        return {"variable": variable, "compared": 0, "agreement": None}
    agree = compared = 0
    for prev, curr in zip(points, points[1:]):
        if curr.turn >= len(median) or prev.turn >= len(median) or prev.turn < 0:
            continue
        observed_dir = curr.value - prev.value
        modelled_dir = float(median[curr.turn]) - float(median[prev.turn])
        if abs(observed_dir) < 1e-12 and abs(modelled_dir) < 1e-12:
            agree += 1
        elif observed_dir * modelled_dir > 0:
            agree += 1
        compared += 1
    return {
        "variable": variable,
        "compared": compared,
        "agreement": (agree / compared) if compared else None,
    }
