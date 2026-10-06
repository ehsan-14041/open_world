#!/usr/bin/env python3
"""
H1 experiment: frozen baseline vs baseline + vessel-queue stock, on the existing replays.

    python scripts/run_h1_experiment.py
    python scripts/run_h1_experiment.py --write-report

Runs both models over identical historical inputs and applies the acceptance rule
pre-registered in docs/replays/H1_EXPERIMENT_PROTOCOL.md. The rule is evaluated in code so
it cannot be quietly reinterpreted after the fact.

Deterministic. No LLM. No parameter is fitted here — the new H1 parameters are swept over
the ranges declared in the protocol, with one shared configuration across both events.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

from event_sim.cross_event import bias_metrics  # noqa: E402
from event_sim.historical import (  # noqa: E402
    InsufficientObservationsError,
    evaluate_replay,
    load_episode,
    load_milestones,
    load_observations,
    milestone_evaluation,
    replay_episode,
)

BASELINE_MODULE = "port_disruption"
EXPERIMENTAL_MODULE = "port_disruption_h1_queue_experimental"
EPISODES = ("yantian_2021", "baltimore_2024")
REPORTS_DIR = _PROJECT_ROOT / "docs" / "replays"

#: Pre-registered thresholds. Changing these after results exist would void the experiment.
MIN_COMBINED_IMPROVEMENT_TURNS = 2
MAX_TOLERATED_DEGRADATION_TURNS = 1


def run_arm(module: str) -> dict:
    """Run both episodes against one model and collect every metric the protocol names."""
    findings, per_event = [], {}
    for episode_id in EPISODES:
        episode = load_episode(episode_id)
        replay = replay_episode(episode, modules=[module])
        entry: dict = {"episode": episode_id, "series": {}}

        try:
            evaluation = evaluate_replay(replay, load_observations(episode_id))
            for row in evaluation["variables"]:
                traj = row["trajectory"]
                findings.append({"episode": episode_id, "kind": "peak", "evidence": "observed",
                                 "error_turns": traj["peak_timing_error_turns"]})
                entry["level"] = {
                    "variable": row["variable"],
                    "peak_timing_error": traj["peak_timing_error_turns"],
                    "peak_magnitude_error": traj["peak_magnitude_error"],
                    "direction_match": traj["direction_match"],
                    "coverage_rate": row["coverage_rate"],
                    "inside": row["inside"], "scored": row["scored_points"],
                    "first_divergence_turn": row["first_divergence_turn"],
                    "mae": traj["mae"], "normalized_mae": traj["normalized_mae"],
                    "correlation": traj["correlation"],
                    "simulated_peak_turn": traj["simulated_peak"]["turn"],
                    "observed_peak_turn": traj["observed_peak"]["turn"],
                }
        except InsufficientObservationsError:
            entry["level"] = None

        milestones = load_milestones(episode_id)
        if milestones:
            result = milestone_evaluation(replay, milestones)
            entry["milestones"] = []
            for row in result["milestones"]:
                if not row.get("simulated"):
                    continue
                entry["milestones"].append({
                    "id": row["milestone"], "scored": row["scored"],
                    "observed_turn": row["observed_turn"],
                    "simulated_median": row["simulated"]["median"],
                    "timing_error": row["timing_error_turns"], "verdict": row["verdict"],
                })
                if row.get("scored"):
                    findings.append({"episode": episode_id, "kind": row["kind"],
                                     "evidence": "observed",
                                     "error_turns": row["timing_error_turns"]})

        # representative central world, for the dynamics narrative
        central = next(
            (w for w in replay["worlds"]
             if w["config"]["axis_settings"].get("recovery_rate") == "central"),
            replay["worlds"][0],
        )
        for name in ("port_capacity", "vessel_queue", "shipping_delay", "order_backlog",
                     "inventory_availability", "service_level"):
            if name in central["series"]:
                entry["series"][name] = central["series"][name]
        per_event[episode_id] = entry

    return {"module": module, "findings": findings, "per_event": per_event,
            "bias": bias_metrics(findings)}


def apply_acceptance_rule(baseline: dict, experimental: dict) -> dict:
    """
    The pre-registered rule from H1_EXPERIMENT_PROTOCOL.md §5, evaluated mechanically.

    Criterion 1 gates on the COMBINED median. That aggregation was chosen before results
    existed; it is applied here exactly as written.
    """
    base_med = baseline["bias"]["combined_timing_bias"]["median"]
    exp_med = experimental["bias"]["combined_timing_bias"]["median"]
    movement = abs(base_med) - abs(exp_med)  # positive = toward zero

    per_event, sensitive_ok, insensitive_ok = {}, True, True
    for episode_id in EPISODES:
        b = [f for f in baseline["findings"] if f["episode"] == episode_id]
        e = [f for f in experimental["findings"] if f["episode"] == episode_id]
        b_err = b[0]["error_turns"] if b else None
        e_err = e[0]["error_turns"] if e else None
        if b_err is None or e_err is None:
            continue
        change = abs(b_err) - abs(e_err)
        sensitive = b_err != e_err
        per_event[episode_id] = {"baseline": b_err, "experimental": e_err,
                                 "improvement_turns": change, "moved": sensitive}
        if sensitive and change <= 0:
            sensitive_ok = False
        if not sensitive and change < -MAX_TOLERATED_DEGRADATION_TURNS:
            insensitive_ok = False

    def _direction(arm: dict) -> bool:
        return all(v["level"]["direction_match"] for v in arm["per_event"].values() if v.get("level"))

    direction_ok = _direction(experimental) >= _direction(baseline)

    magnitude_ok = True
    magnitude_notes = []
    for episode_id, entry in experimental["per_event"].items():
        base_entry = baseline["per_event"][episode_id]
        if not entry.get("level") or not base_entry.get("level"):
            continue
        if (base_entry["level"]["coverage_rate"] or 0) > 0 and (entry["level"]["coverage_rate"] or 0) == 0:
            magnitude_ok = False
            magnitude_notes.append(f"{episode_id}: envelope coverage collapsed to zero")
        b_peak = abs(base_entry["level"]["peak_magnitude_error"])
        e_peak = abs(entry["level"]["peak_magnitude_error"])
        if b_peak > 0 and e_peak > 2 * b_peak:
            magnitude_ok = False
            magnitude_notes.append(f"{episode_id}: peak magnitude error more than doubled")

    criteria = {
        "1_combined_timing_moves_toward_zero_by_2_or_more": movement >= MIN_COMBINED_IMPROVEMENT_TURNS,
        "2_sensitive_events_improve_insensitive_not_degraded": sensitive_ok and insensitive_ok,
        "3_direction_validity_preserved": direction_ok,
        "4_no_magnitude_blow_up": magnitude_ok,
        "5_no_retuning_one_shared_config": True,  # structurally guaranteed; asserted by tests
    }
    passed = all(criteria.values())

    if passed:
        verdict = "experimental_mitigating"
    elif movement <= -MIN_COMBINED_IMPROVEMENT_TURNS or not direction_ok or not magnitude_ok:
        verdict = "experimental_worse"
    else:
        verdict = "experimental_no_effect"

    return {
        "baseline_combined_median": base_med,
        "experimental_combined_median": exp_med,
        "combined_movement_toward_zero_turns": movement,
        "per_event": per_event,
        "criteria": criteria,
        "verdict": verdict,
        "magnitude_notes": magnitude_notes,
        "rule_reference": "docs/replays/H1_EXPERIMENT_PROTOCOL.md §5 (pre-registered)",
    }


def render_console(baseline: dict, experimental: dict, decision: dict) -> str:
    out: list[str] = []
    rule = lambda t: f"\n{t}\n{'-' * len(t)}"  # noqa: E731
    out.append("H1 EXPERIMENT — frozen baseline vs baseline + vessel-queue stock")
    out.append(f"baseline module    : {BASELINE_MODULE}")
    out.append(f"experimental module: {EXPERIMENTAL_MODULE}")

    out.append(rule("TIMING (sign preserved; negative = model is early)"))
    out.append(f"  {'Event':<18}{'Baseline':>10}{'H1':>10}{'Delta':>10}   Interpretation")
    for episode_id, row in decision["per_event"].items():
        interp = ("improved" if row["improvement_turns"] > 0 else
                  "unchanged" if row["improvement_turns"] == 0 else "worse")
        out.append(f"  {episode_id:<18}{row['baseline']:>+10d}{row['experimental']:>+10d}"
                   f"{row['improvement_turns']:>+10d}   {interp}")
    out.append(f"  {'combined median':<18}{decision['baseline_combined_median']:>+10d}"
               f"{decision['experimental_combined_median']:>+10d}"
               f"{decision['combined_movement_toward_zero_turns']:>+10d}")

    out.append(rule("SECONDARY METRICS"))
    for episode_id in EPISODES:
        b, e = baseline["per_event"][episode_id].get("level"), experimental["per_event"][episode_id].get("level")
        if not b or not e:
            out.append(f"  {episode_id}: no level observations (milestone-only)")
            continue
        out.append(f"  {episode_id} [{b['variable']}]")
        for key, fmt in (("coverage_rate", "{:.2f}"), ("peak_magnitude_error", "{:+.2f}"),
                         ("mae", "{:.2f}"), ("normalized_mae", "{:.2f}"), ("correlation", "{:+.3f}"),
                         ("simulated_peak_turn", "w{}"), ("first_divergence_turn", "w{}")):
            out.append(f"    {key:<22} {fmt.format(b[key]):>8}  ->  {fmt.format(e[key]):>8}")
        out.append(f"    {'direction_match':<22} {str(b['direction_match']):>8}  ->  {str(e['direction_match']):>8}")

    out.append(rule("QUEUE DYNAMICS (experimental, central assumptions)"))
    for episode_id in EPISODES:
        series = experimental["per_event"][episode_id]["series"]
        queue = series.get("vessel_queue")
        if not queue:
            continue
        capacity, delay = series["port_capacity"], series["shipping_delay"]
        recovered = next((t for t in range(2, len(capacity)) if capacity[t] >= 95.0), None)
        out.append(f"  {episode_id}: queue peaks {max(queue):.2f} at w{queue.index(max(queue))}, "
                   f"capacity>=95% at w{recovered}, queue still {queue[recovered]:.2f} then, "
                   f"delay peaks at w{delay.index(max(delay))}, queue at end {queue[-1]:.2f}")

    out.append(rule("PRE-REGISTERED ACCEPTANCE RULE"))
    for name, ok in decision["criteria"].items():
        out.append(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for note in decision["magnitude_notes"]:
        out.append(f"    note: {note}")
    out.append(f"\n  VERDICT: {decision['verdict'].upper()}")
    out.append(f"  ({decision['rule_reference']})")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    baseline = run_arm(BASELINE_MODULE)
    experimental = run_arm(EXPERIMENTAL_MODULE)
    decision = apply_acceptance_rule(baseline, experimental)

    if args.json:
        print(json.dumps({"baseline": baseline, "experimental": experimental,
                          "decision": decision}, indent=2, default=str))
    else:
        print(render_console(baseline, experimental, decision))

    if args.write_report:
        from event_sim.h1_report import render_h1_results

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / "H1_EXPERIMENT_RESULTS.md"
        path.write_text(render_h1_results(baseline, experimental, decision) + "\n", encoding="utf-8")
        print(f"\nReport written to {path.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
