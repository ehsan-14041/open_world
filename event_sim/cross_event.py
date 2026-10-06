"""
Cross-event falsification: run the same frozen model against several historical events and
ask whether its failures repeat.

One event cannot separate "the model is wrong" from "that event's observable was a bad
measurement". A second event, chosen to differ on every dimension that could produce a
spurious result — year, region, trigger, background regime, and above all the measurement
method — can.

Nothing here changes the model. The point is to decide whether a change is warranted.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence


def timing_findings(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect every timing comparison from every episode into one table."""
    rows: list[dict[str, Any]] = []
    for episode_id, result in results.items():
        for row in ((result.get("evaluation") or {}).get("variables") or []):
            traj = row.get("trajectory") or {}
            if traj.get("peak_timing_error_turns") is None:
                continue
            rows.append({
                "episode": episode_id,
                "test": f"peak of {row.get('variable', traj.get('variable', 'unknown'))}",
                "kind": "peak",
                "observed_turn": (traj.get("observed_peak") or {}).get("turn"),
                "simulated_turn": (traj.get("simulated_peak") or {}).get("turn"),
                "error_turns": int(traj["peak_timing_error_turns"]),
                "evidence": "observed",
                "inside_envelope": None,
                "share_beyond": None,
                "note": "level-series peak",
            })
        for row in ((result.get("milestone_evaluation") or {}).get("milestones") or []):
            if not row.get("simulated"):
                continue
            rows.append({
                "episode": episode_id,
                "test": row["milestone"],
                "kind": row["kind"],
                "observed_turn": row["observed_turn"],
                "simulated_turn": row["simulated"]["median"],
                "error_turns": int(row["timing_error_turns"]),
                "evidence": row.get("status", "observed"),
                "inside_envelope": row.get("observed_inside_envelope"),
                "share_beyond": row.get("share_of_worlds_at_or_beyond_observed"),
                "note": row.get("verdict", ""),
            })
    return rows


#: Bias metrics specific to event simulation. A single R2 or MAE cannot express the thing
#: that actually matters for a disruption model — whether its clock runs at the right speed.
BIAS_METRIC_DEFINITIONS: dict[str, str] = {
    "peak_timing_bias": (
        "simulated peak turn - observed peak turn, per test. Negative means the model peaks "
        "EARLIER than the real world did."
    ),
    "recovery_bias": (
        "simulated recovery turn - observed recovery turn, per test. Negative means the model "
        "recovers EARLIER than the real world did."
    ),
    "aggregation": (
        "reported as the median across all scored tests in all events. A median that is "
        "consistently negative across independent events is a systematic clock error, not "
        "noise — random model error would change sign between events."
    ),
}


def bias_metrics(findings: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """
    Peak Timing Bias and Recovery Bias, aggregated across every event.

    These are the Event-Simulator-specific metrics: a disruption model can have excellent
    correlation and still be useless if it says the trough arrives in week 3 when it arrives
    in week 12. Reported separately because they answer different questions — when does it
    get worst, and when is it over.
    """
    scored = [f for f in findings if f["evidence"] == "observed"]

    def _summarise(rows: Sequence[dict[str, Any]], label: str) -> dict[str, Any]:
        errors = sorted(int(r["error_turns"]) for r in rows)
        if not errors:
            return {"metric": label, "n": 0, "median": None, "verdict": "untested"}
        median = errors[len(errors) // 2]
        same_sign = all(e < 0 for e in errors) or all(e > 0 for e in errors)
        episodes = {r["episode"] for r in rows}
        return {
            "metric": label,
            "n": len(errors),
            "errors": errors,
            "median": median,
            "min": errors[0],
            "max": errors[-1],
            "episodes": sorted(episodes),
            "all_same_sign": same_sign,
            "systematic": same_sign and len(episodes) >= 2,
            "verdict": (
                "systematically early" if median < 0 and same_sign and len(episodes) >= 2
                else "systematically late" if median > 0 and same_sign and len(episodes) >= 2
                else "no consistent bias"
            ),
        }

    peak_rows = [f for f in scored if f["kind"] == "peak"]
    recovery_rows = [f for f in scored if f["kind"] != "peak"]
    peak = _summarise(peak_rows, "peak_timing_bias")
    recovery = _summarise(recovery_rows, "recovery_bias")
    combined = _summarise(scored, "combined_timing_bias")

    return {
        "peak_timing_bias": peak,
        "recovery_bias": recovery,
        "combined_timing_bias": combined,
        "definitions": dict(BIAS_METRIC_DEFINITIONS),
        "headline": (
            f"median timing bias {combined['median']:+d} turns across "
            f"{combined['n']} scored tests in {len(combined.get('episodes', []))} events"
            if combined["median"] is not None else "no scored timing tests"
        ),
    }


def cross_event_diagnosis(
    episode_ids: Sequence[str],
    run_pipeline: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """
    Replay every episode against the SAME frozen model and report whether the same failure
    appears in more than one.

    `run_pipeline` is injected so this module stays independent of the CLI.
    """
    results = {eid: run_pipeline(eid) for eid in episode_ids}
    findings = timing_findings(results)
    scored = [f for f in findings if f["evidence"] == "observed"]
    too_early = [f for f in scored if f["error_turns"] < 0]
    too_late = [f for f in scored if f["error_turns"] > 0]
    episodes_with_early = {f["episode"] for f in too_early}

    strict_failures = [f for f in findings if f.get("inside_envelope") is False]

    return {
        "episodes": list(episode_ids),
        "results": results,
        "timing_findings": findings,
        "bias": bias_metrics(findings),
        "scored_timing_tests": len(scored),
        "tests_too_early": len(too_early),
        "tests_too_late": len(too_late),
        "episodes_showing_early_bias": sorted(episodes_with_early),
        "pattern_repeats": len(episodes_with_early) >= 2,
        "strict_envelope_failures": strict_failures,
        "verdict": (
            "consistent directional bias across independent events"
            if len(episodes_with_early) >= 2
            else "no repeated pattern across events"
        ),
        "model_frozen": True,
    }


class DataSplitError(ValueError):
    """Raised when a train/held-out split would not support an honest evaluation."""


#: Minimum events required before a structural hypothesis may be adopted: at least one to
#: calibrate on and one genuinely held out.
MIN_EVENTS_FOR_HELD_OUT = 3


def declare_split(
    calibration_events: Sequence[str],
    held_out_events: Sequence[str],
    *,
    available: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Declare a train / held-out split BEFORE fitting anything, and refuse dishonest ones.

    Freezing the split up front is the whole defence against the failure this project has
    already documented once: fit on the benchmarks, report the fit as validation. The split
    is returned as a record so it can be written into a calibration provenance entry and
    compared against later — a split that changes after seeing results is not a split.

    Refuses when:
      - an event appears in both sides (leakage);
      - the held-out side is empty;
      - fewer than MIN_EVENTS_FOR_HELD_OUT events exist in total;
      - a named event is not available.
    """
    cal, held = list(calibration_events), list(held_out_events)
    known = set(available) if available is not None else set(cal) | set(held)

    overlap = set(cal) & set(held)
    if overlap:
        raise DataSplitError(
            f"events {sorted(overlap)} appear in both the calibration and held-out sets; "
            f"that is leakage, not a split"
        )
    if not held:
        raise DataSplitError(
            "the held-out set is empty. Evaluating on the events a hypothesis was fitted to "
            "is in-sample fit, and must never be reported as validation."
        )
    if not cal:
        raise DataSplitError("the calibration set is empty; nothing would be fitted")
    unknown = (set(cal) | set(held)) - known
    if unknown:
        raise DataSplitError(f"unknown events: {sorted(unknown)}")
    total = len(set(cal) | set(held))
    if total < MIN_EVENTS_FOR_HELD_OUT:
        raise DataSplitError(
            f"{total} event(s) available; at least {MIN_EVENTS_FOR_HELD_OUT} are required "
            f"before a structural hypothesis can be calibrated on some and honestly "
            f"evaluated on another. See docs/replays/EVENT3_SEARCH.md."
        )
    return {
        "calibration_events": sorted(cal),
        "held_out_events": sorted(held),
        "declared_before_fitting": True,
        "rule": (
            "The split is fixed before any hypothesis is fitted. Results on held-out events "
            "are the only ones reportable as validation; results on calibration events are "
            "in-sample fit."
        ),
    }


def evaluate_hypothesis(
    hypothesis_id: str,
    split: dict[str, Any],
    baseline_bias: dict[str, Any],
    candidate_bias: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare a structural candidate against the current model on the HELD-OUT events only.

    A candidate is accepted only if it reduces the absolute median timing bias out of
    sample. Improving in-sample fit counts for nothing here — that is the specific mistake
    this scaffolding exists to prevent.
    """
    base = baseline_bias.get("combined_timing_bias", {}).get("median")
    cand = candidate_bias.get("combined_timing_bias", {}).get("median")
    if base is None or cand is None:
        return {
            "hypothesis": hypothesis_id,
            "verdict": "not evaluable",
            "reason": "no scored timing tests on the held-out events",
        }
    improved = abs(cand) < abs(base)
    return {
        "hypothesis": hypothesis_id,
        "held_out_events": split["held_out_events"],
        "baseline_median_bias": base,
        "candidate_median_bias": cand,
        "absolute_improvement": abs(base) - abs(cand),
        "verdict": "accept" if improved else "reject",
        "reason": (
            "reduces absolute median timing bias on held-out events"
            if improved else
            "does not reduce absolute median timing bias out of sample"
        ),
        "caveat": (
            "A single held-out event is weak evidence. Accepting a structural change also "
            "requires that it not degrade direction or magnitude validity."
        ),
    }


#: Lifecycle of a structural hypothesis. A hypothesis only advances on evidence, and being
#: supported by independent data is NOT the same as being adopted into the model.
HYPOTHESIS_STATUS = (
    "declared",                  # plausible, untested
    "independently_supported",   # consistent with observed behaviour, outside our engine
    "not_supported",             # tested, predicted signature absent — but the test was
                                 # underpowered, so it is NOT deleted
    "rejected",                  # contradicted by an adequate test; delete it
    "implemented_experimental",  # built as an alternative module, main model untouched
    "experimental_no_effect",    # implemented and replayed; pre-registered rule not met
    "experimental_worse",        # implemented and replayed; degraded the model
    "experimental_mitigating",   # implemented and replayed; pre-registered rule met in-sample
    "historically_validated",    # improved timing on a HELD-OUT event
)

#: Competing structural explanations for a persistent "too fast" bias.
STRUCTURAL_HYPOTHESES: list[dict[str, str]] = [
    {
        "id": "H1",
        "name": "Queue as a stock",
        "status": "experimental_no_effect",
        "evidence": (
            "IMPLEMENTED EXPERIMENTALLY as world_models/supply_chain/"
            "port_disruption_h1_queue_experimental.json and replayed against the frozen "
            "baseline (docs/replays/H1_EXPERIMENT_RESULTS.md). Four of five pre-registered "
            "criteria passed; criterion 1 (combined median timing bias must move >=2 turns) "
            "failed because it moved 1 turn. SUBSTANTIVELY the mechanism worked: on Yantian, "
            "the only event whose metric can move, peak timing error went -9 -> -5 weeks, "
            "peak magnitude error +3.32 -> +1.39, envelope coverage 0.00 -> 0.50 and "
            "correlation -0.15 -> +0.69; Baltimore's milestone is on port_capacity and was "
            "predicted in advance to be mechanically frozen. The combined-median aggregator "
            "was a poor pre-registration choice with only two scored tests, and is NOT being "
            "changed retroactively. "
            "ORIGINAL MECHANISM EVIDENCE: docs/replays/H1_QUEUE_MECHANISM.md — a real port "
            "queue (San Pedro Bay, "
            "Jun-Oct 2021) rises with non-decaying increments, which relaxation toward a "
            "steady driver cannot produce; relaxation would require the driver to have "
            "tripled over months when it was flat. Tested with no simulation involved."
        ),
        "mechanism": (
            "A `vessel_queue` stock accumulates while capacity is below demand and drains at "
            "a finite rate afterwards, so delay persists after capacity has recovered. A "
            "reopened port is not a cleared queue."
        ),
        "test": "fit the drain rate on one event, predict the other event's recovery week out-of-sample",
    },
    {
        "id": "H2",
        "name": "Backlog persistence",
        "status": "not_supported",
        "evidence": (
            "docs/replays/H2_BACKLOG_MECHANISM.md — tested on US manufacturing unfilled "
            "orders excluding transportation (Census M3 via FRED, public domain). At matched "
            "capacity utilisation, DETRENDED backlog cover is LOWER on the down-leg than the "
            "up-leg (mean gap -0.022 months), the opposite of the path dependence a stock "
            "predicts. The uncontrolled persistence comparison looked supportive (+28%) and "
            "was entirely secular trend. NOT deleted: a national aggregate averages together "
            "industries that are accumulating and draining, so the test is underpowered for "
            "a node-level claim."
        ),
        "mechanism": (
            "`order_backlog` already exists but relaxes toward causal pressure rather than "
            "integrating a flow imbalance. Making it a true stock would delay downstream peaks "
            "without changing any effect size."
        ),
        "test": "same held-out design; compare against H1 on the same events",
    },
    {
        "id": "H3",
        "name": "Lag structure understated",
        "status": "declared",
        "evidence": (
            "untested, and deprioritised: H1's support means the timing error has a "
            "mechanistic explanation that does not require simply lengthening lags."
        ),
        "mechanism": "Effect sizes are roughly right but every declared lag is too short.",
        "test": "re-estimate lags only, leaving effect ranges frozen",
    },
    {
        "id": "H4",
        "name": "Recovery asymmetry",
        "status": "declared",
        "evidence": (
            "untested. Note a queue stock produces onset/recovery asymmetry naturally, so "
            "H4 may be a consequence of H1 rather than an independent mechanism."
        ),
        "mechanism": (
            "Onset and recovery currently share one `response` parameter per variable. Real "
            "recovery is plausibly slower than onset."
        ),
        "test": "split into separate onset and recovery rates; check whether onset timing degrades",
    },
]
