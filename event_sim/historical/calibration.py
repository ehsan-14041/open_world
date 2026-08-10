"""
Minimal, interpretable, provenance-preserving calibration.

    prior effect range → historical replay → compare observed vs simulated
                       → candidate range   → replay again → calibration record

Design constraints, all of which exist to stop this from becoming a curve-fitter:

- **The prior is never overwritten.** A `CalibrationRecord` stores `prior_range` and
  `calibrated_range` side by side, so a reader can always see what moved and by how much.
- **Movement is capped.** A single historical episode may not move a coefficient more than
  `max_movement_fraction` of its prior range. A replay that "wants" a much larger move is
  telling us the structure is wrong, not that the coefficient is.
- **Identifiability is checked first.** An edge that cannot be separated from another edge
  in this episode, or that has too few observations, returns `not_identifiable` and is
  left alone. Returning no number is a valid — often the correct — outcome.
- **Search is a coarse grid, not an optimiser.** The method has to be explainable to
  someone who does not trust it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from event_sim import sweep
from event_sim.evidence.registry import CALIBRATION_PATH, clear_cache
from event_sim.evidence.schema import CalibrationRecord
from event_sim.historical.evaluation import trajectory_metrics
from event_sim.historical.replay import HistoricalEpisode, build_replay_slice
from event_sim.schemas import CausalEdgeEvidence, HistoricalObservation, WorldSlice

#: An edge needs at least this many scoreable observations on its target before a single
#: episode may move it. Below this, the coefficient is not identifiable from this event.
MIN_OBSERVATIONS = 3

#: Maximum fraction of the prior [low, high] width the central value may move.
MAX_MOVEMENT_FRACTION = 0.5

#: Coarse multiplicative grid searched around the prior central value.
CANDIDATE_MULTIPLIERS = (0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0)


@dataclass
class CalibrationOutcome:
    """Result of attempting to calibrate one edge against one episode."""

    edge_id: str
    identifiable: bool
    reason: str
    record: CalibrationRecord | None = None
    diagnostics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "identifiable": self.identifiable,
            "reason": self.reason,
            "record": self.record.to_dict() if self.record else None,
            "diagnostics": dict(self.diagnostics or {}),
        }


def _observations_for(
    observations: Sequence[HistoricalObservation], variable: str
) -> list[HistoricalObservation]:
    return sorted(
        (o for o in observations if o.variable == variable and o.is_scoreable()),
        key=lambda o: o.turn,
    )


def check_identifiability(
    edge: CausalEdgeEvidence,
    slice_: WorldSlice,
    observations: Sequence[HistoricalObservation],
) -> tuple[bool, str, dict[str, Any]]:
    """
    Can this episode constrain this edge at all?

    Three ways the answer is no, each of which the calibration loop must respect rather
    than fit through:

    1. **No observations** on the edge's target variable.
    2. **Too few observations** (< MIN_OBSERVATIONS) to distinguish a coefficient from noise.
    3. **Confounded** — another edge into the same target is driven by the same upstream
       shock in the same window, so movement cannot be attributed between them.
    """
    target_obs = _observations_for(observations, edge.target)
    diagnostics: dict[str, Any] = {
        "target": edge.target,
        "observation_count": len(target_obs),
        "observation_turns": [o.turn for o in target_obs],
    }

    if not target_obs:
        return False, f"no observations exist for the target variable {edge.target!r}", diagnostics
    if len(target_obs) < MIN_OBSERVATIONS:
        return False, (
            f"only {len(target_obs)} observation(s) on {edge.target!r}; "
            f"at least {MIN_OBSERVATIONS} are required to move a coefficient"
        ), diagnostics

    siblings = [e for e in slice_.edges_into(edge.target) if e.id != edge.id]
    diagnostics["sibling_edges"] = [e.id for e in siblings]
    if siblings:
        shocked = {v.id for v in slice_.variables}
        # A sibling is confounding when its own source traces back to the same driver.
        confounded = [e.id for e in siblings if e.source in shocked]
        if confounded:
            diagnostics["confounded_with"] = confounded
            return False, (
                f"{edge.target!r} also receives {confounded} in the same window; a single "
                f"episode cannot attribute movement between them"
            ), diagnostics

    return True, "identifiable from this episode", diagnostics


def _score_candidate(
    episode: HistoricalEpisode,
    slice_: WorldSlice,
    observations: Sequence[HistoricalObservation],
    target_variable: str,
) -> dict[str, Any]:
    """Replay the slice and return the fit of the envelope median to observation."""
    worlds = sweep.run_sweep(slice_, events=episode.all_events(), turns=episode.turns)
    env = sweep.envelope(worlds, target_variable)
    var_def = slice_.variable(target_variable)
    metrics = trajectory_metrics(
        env, _observations_for(observations, target_variable),
        baseline=(var_def.baseline if var_def else None),
    )
    return {"mae": metrics.get("mae"), "metrics": metrics, "envelope": env}


def calibrate_edge(
    episode: HistoricalEpisode,
    edge_id: str,
    observations: Sequence[HistoricalObservation],
    *,
    max_movement_fraction: float = MAX_MOVEMENT_FRACTION,
    multipliers: Sequence[float] = CANDIDATE_MULTIPLIERS,
) -> CalibrationOutcome:
    """
    Attempt to calibrate one edge against one episode.

    Method: coarse grid over multiples of the prior central coefficient; for each candidate,
    replay the whole assumption sweep and score the envelope median against observation by
    mean absolute error; keep the best candidate that stays within the movement cap.
    """
    slice_ = build_replay_slice(episode)
    edge = next((e for e in slice_.edges if e.id == edge_id), None)
    if edge is None:
        return CalibrationOutcome(edge_id, False, f"edge {edge_id!r} is not in this slice")

    identifiable, reason, diagnostics = check_identifiability(edge, slice_, observations)
    if not identifiable:
        return CalibrationOutcome(edge_id, False, reason, diagnostics=diagnostics)

    prior = edge.effect.to_dict()
    prior_width = abs(prior["high"] - prior["low"]) or abs(prior["central"]) or 1.0
    cap = prior_width * max_movement_fraction

    results: list[dict[str, Any]] = []
    for multiplier in multipliers:
        candidate_central = prior["central"] * multiplier
        if abs(candidate_central - prior["central"]) > cap:
            results.append({"multiplier": multiplier, "central": candidate_central,
                            "rejected": "exceeds movement cap"})
            continue
        trial = build_replay_slice(episode)
        trial_edge = next(e for e in trial.edges if e.id == edge_id)
        span = (prior["high"] - prior["low"]) / 2.0
        trial_edge.effect.central = candidate_central
        trial_edge.effect.low = candidate_central - span
        trial_edge.effect.high = candidate_central + span
        score = _score_candidate(episode, trial, observations, edge.target)
        results.append({
            "multiplier": multiplier,
            "central": candidate_central,
            "mae": score["mae"],
            "direction_match": score["metrics"].get("direction_match"),
        })

    scored = [r for r in results if r.get("mae") is not None]
    if not scored:
        return CalibrationOutcome(
            edge_id, False,
            "no candidate produced a scoreable fit within the movement cap",
            diagnostics={**diagnostics, "candidates": results},
        )

    best = min(scored, key=lambda r: float(r["mae"]))
    baseline_fit = next((r for r in scored if r["multiplier"] == 1.0), None)
    improvement = (
        (float(baseline_fit["mae"]) - float(best["mae"])) / float(baseline_fit["mae"])
        if baseline_fit and float(baseline_fit["mae"]) > 1e-12 else None
    )

    warnings: list[str] = []
    if len(_observations_for(observations, edge.target)) < 5:
        warnings.append(
            f"short series: {len(_observations_for(observations, edge.target))} observations — "
            f"the calibrated value is weakly determined"
        )
    if improvement is not None and improvement < 0.05:
        warnings.append(
            "moving this coefficient improved fit by less than 5%; the prior is retained "
            "as the calibrated central value because the data does not distinguish them"
        )
        best = baseline_fit or best

    span = (prior["high"] - prior["low"]) / 2.0
    calibrated = {
        "low": float(best["central"]) - span,
        "central": float(best["central"]),
        "high": float(best["central"]) + span,
    }

    record = CalibrationRecord(
        edge_id=edge_id,
        calibration_event_id=episode.id,
        method=(
            f"coarse multiplicative grid over the prior central coefficient "
            f"({list(multipliers)}), scored by mean absolute error of the sweep envelope "
            f"median against observed values; movement capped at "
            f"{max_movement_fraction:.0%} of the prior range width"
        ),
        prior_range=prior,
        calibrated_range=calibrated,
        data_used=sorted({o.source for o in _observations_for(observations, edge.target) if o.source}),
        fit_quality={
            "best_mae": best.get("mae"),
            "prior_mae": (baseline_fit or {}).get("mae"),
            "relative_improvement": improvement,
            "candidates": results,
        },
        n_observations=len(_observations_for(observations, edge.target)),
        max_movement_allowed=cap,
        identifiable=True,
        warnings=warnings,
        notes=(
            "Single-episode calibration. In-sample by construction: with one historical "
            "event there is no held-out event, so this must not be reported as validation."
        ),
    )
    return CalibrationOutcome(edge_id, True, "calibrated", record=record, diagnostics=diagnostics)


def calibrate_episode(
    episode: HistoricalEpisode,
    observations: Sequence[HistoricalObservation],
    *,
    edge_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Attempt calibration for every candidate edge in an episode.

    Returns outcomes for all of them, including the ones that were refused — a refusal is
    a result, and hiding it would misrepresent how much of the model the episode touched.
    """
    slice_ = build_replay_slice(episode)
    targets = list(edge_ids) if edge_ids else [e.id for e in slice_.edges]
    outcomes = [calibrate_edge(episode, edge_id, observations) for edge_id in targets]
    calibrated = [o for o in outcomes if o.identifiable]
    return {
        "episode": episode.id,
        "attempted": len(outcomes),
        "calibrated": len(calibrated),
        "not_identifiable": [
            {"edge": o.edge_id, "reason": o.reason} for o in outcomes if not o.identifiable
        ],
        "outcomes": [o.to_dict() for o in outcomes],
        "records": [o.record.to_dict() for o in calibrated if o.record],
        "limitation": (
            "One historical episode means calibration and evaluation share the same window. "
            "This is in-sample fitting and must not be reported as out-of-sample validation. "
            "A second independent episode is required before any edge can honestly claim "
            "'historically_calibrated'."
        ),
    }


def write_calibration_records(records: Sequence[dict[str, Any]], *, path: Path | None = None) -> Path:
    """
    Persist calibration records, appending rather than replacing.

    Calibration never rewrites the world module: the module keeps its prior coefficients,
    and the calibration file records what a replay suggested. Promoting an edge is a
    separate, deliberate human step.
    """
    target = path or CALIBRATION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        existing = list(data.get("calibrations") or []) if isinstance(data, dict) else list(data)
    payload = {
        "_note": (
            "Calibration records. Each preserves the prior range alongside the calibrated "
            "range. World modules are NOT rewritten by calibration; promoting an edge to "
            "'historically_calibrated' is a separate human decision that must satisfy "
            "event_sim.evidence.registry.validate_edge_provenance."
        ),
        "calibrations": existing + [dict(r) for r in records],
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    clear_cache()
    return target
