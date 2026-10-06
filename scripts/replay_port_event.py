#!/usr/bin/env python3
"""
One-command historical replay of a port disruption.

    python scripts/replay_port_event.py yantian_2021
    python scripts/replay_port_event.py yantian_2021 --write-report
    python scripts/replay_port_event.py --list

Runs the whole pipeline from repository state, with no notebook and no manual step:

    load episode  →  verify no hindsight leakage  →  load evidence + observations
                  →  inject event  →  run the assumption sweep  →  evaluate envelope
                  →  attempt calibration  →  evidence gap report  →  markdown report

Deterministic: the same episode file produces byte-identical output. Nothing here calls a
language model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Reports contain arrows and en-dashes; a Windows console defaults to cp1252 and would
# raise UnicodeEncodeError on print. Files are always written as UTF-8 regardless.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

from event_sim import sweep  # noqa: E402
from event_sim.evidence import (  # noqa: E402
    data_requirements,
    evidence_gap_report,
    source_summary,
    validate_slice_provenance,
    weighted_coverage,
)
from event_sim.evidence.coverage import merge_influence  # noqa: E402
from event_sim.historical import (  # noqa: E402
    InsufficientObservationsError,
    available_episodes,
    calibrate_episode,
    evaluate_replay,
    load_episode,
    load_milestones,
    load_observations,
    milestone_evaluation,
    observation_metadata,
    replay_episode,
)
from event_sim.cross_event import (  # noqa: E402
    STRUCTURAL_HYPOTHESES,
    cross_event_diagnosis,
)
from event_sim.model_health import model_health, render_model_health  # noqa: E402

REPORTS_DIR = _PROJECT_ROOT / "docs" / "replays"
OUTCOME_VARIABLE = "service_level"


def run_pipeline(episode_id: str, *, tolerance: float = 0.0) -> dict:
    """Full replay pipeline. Returns everything the report needs."""
    episode = load_episode(episode_id)
    observations = load_observations(episode_id)
    milestones = load_milestones(episode_id)
    obs_meta = observation_metadata(episode_id)

    replay = replay_episode(episode)             # raises on hindsight leakage
    slice_ = replay["slice"]

    provenance_errors = validate_slice_provenance(slice_.edges)

    try:
        evaluation = evaluate_replay(replay, observations, tolerance=tolerance)
        evaluation_error = ""
    except InsufficientObservationsError as exc:
        evaluation, evaluation_error = {}, str(exc)

    milestone_result = milestone_evaluation(replay, milestones) if milestones else {}

    pivotal = sweep.pivotal_assumptions(replay["worlds"], outcome_variable=OUTCOME_VARIABLE)
    coverage = weighted_coverage(slice_.edges, merge_influence(slice_, pivotal))
    gaps = evidence_gap_report(slice_, pivotal=pivotal)
    requirements = data_requirements(gaps, slice_)
    calibration = calibrate_episode(episode, observations)

    health = model_health(
        slice_, pivotal=pivotal, gap_report=gaps,
        replays=[{"episode": episode.id, "evaluation": evaluation, "milestones": milestone_result}],
    )

    return {
        "episode": episode,
        "observations": observations,
        "milestones": milestones,
        "milestone_evaluation": milestone_result,
        "model_health": health,
        "observation_metadata": obs_meta,
        "replay": replay,
        "evaluation": evaluation,
        "evaluation_error": evaluation_error,
        "pivotal": pivotal,
        "coverage": coverage,
        "gaps": gaps,
        "data_requirements": requirements,
        "calibration": calibration,
        "provenance_errors": provenance_errors,
        "sources": source_summary(),
    }


def render_console(result: dict) -> str:
    ep = result["episode"]
    out: list[str] = []
    rule = lambda t: f"\n{t}\n{'-' * len(t)}"  # noqa: E731

    out.append(f"HISTORICAL REPLAY: {ep.title}")
    out.append(f"episode={ep.id}  start={ep.start_date}  cutoff={ep.knowledge_cutoff}  turns={ep.turns}")

    hind = result["replay"]["hindsight_check"]
    out.append(rule("NO-HINDSIGHT CHECK"))
    out.append(f"  knowledge cutoff: {hind['knowledge_cutoff']}")
    for entry in hind["initial_state_checked"]:
        out.append(
            f"  {entry['variable']:<22} available {entry['available_at']} "
            f"(period {entry['refers_to_period'] or 'n/a'})  {'OK' if entry['ok'] else 'LEAK'}"
        )
    later = [o for o in hind["observations"] if o["published_after_cutoff"]]
    out.append(f"  {len(later)} observation(s) published after the cutoff — evaluation only, as intended")

    out.append(rule("EVIDENCE"))
    cov = result["coverage"]
    for group, label in cov["group_labels"].items():
        out.append(
            f"  {label:<45} {cov['by_group'].get(group, 0):>2} edges "
            f"({100 * cov['shares'].get(group, 0):5.1f}%)  "
            f"weighted {100 * cov['weighted']['shares'].get(group, 0):5.1f}%"
        )
    out.append(f"  sources in registry: {len(result['sources'])}")
    if result["provenance_errors"]:
        out.append("  PROVENANCE ERRORS:")
        out.extend(f"    {e}" for e in result["provenance_errors"])
    else:
        out.append("  every edge's declared status is supported by its provenance")

    out.append(rule("REPLAY"))
    replay = result["replay"]
    out.append(f"  {replay['world_count']} worlds (full assumption grid)")
    env = replay["envelope"].get("shipping_delay")
    if env:
        out.append("  shipping_delay envelope (days), by week:")
        out.append("    week " + "".join(f"{t:>7}" for t in env["turns"]))
        out.append("    low  " + "".join(f"{v:>7.2f}" for v in env["low"]))
        out.append("    med  " + "".join(f"{v:>7.2f}" for v in env["median"]))
        out.append("    high " + "".join(f"{v:>7.2f}" for v in env["high"]))

    out.append(rule("EVALUATION"))
    ev = result["evaluation"]
    if result["evaluation_error"]:
        out.append(f"  NOT EVALUATED: {result['evaluation_error']}")
    else:
        out.append(f"  scored points: {ev['scored_points']}  overall coverage: {ev['overall_coverage_rate']}")
        out.append(f"  evaluated variables  : {ev['evaluated_variables']}")
        out.append(f"  UNEVALUATED variables: {ev['unevaluated_variables']}")
        for row in ev["variables"]:
            t = row["trajectory"]
            out.append(f"  [{row['variable']}] ({row['unit']})")
            out.append(f"    envelope coverage    : {row['inside']}/{row['scored_points']} points inside")
            out.append(f"    first divergence     : week {row['first_divergence_turn']}")
            out.append(f"    direction            : observed {t['direction_observed']} / simulated {t['direction_simulated']} -> {'MATCH' if t['direction_match'] else 'MISMATCH'}")
            out.append(f"    peak timing error    : {t['peak_timing_error_turns']:+d} weeks (obs week {t['observed_peak']['turn']}, sim week {t['simulated_peak']['turn']})")
            out.append(f"    peak magnitude error : {t['peak_magnitude_error']:+.2f}")
            out.append(f"    MAE / normalised MAE : {t['mae']:.2f} / {t['normalized_mae']:.2f}" if t.get("normalized_mae") is not None else f"    MAE                  : {t['mae']:.2f}")
            corr = t.get("correlation")
            out.append(f"    correlation          : {corr:.3f}" if corr is not None else "    correlation          : n/a")
            if t.get("recovery_note"):
                out.append(f"    recovery             : {t['recovery_note']}")

    ms = result.get("milestone_evaluation") or {}
    if ms.get("milestones"):
        out.append(rule("MILESTONE (TIMING) EVALUATION"))
        for row in ms["milestones"]:
            sim = row.get("simulated")
            if not sim:
                out.append(f"  {row['milestone']:<24} {row.get('note', 'not reached by any world')}")
                continue
            out.append(
                f"  {row['milestone']:<24} observed week {row['observed_turn']:>2} ({row['date']}, {row['status']})"
                f"  simulated [{sim['earliest']}..{sim['latest']}] median {sim['median']}"
                f"  error {row['timing_error_turns']:+d} weeks  -> {row['verdict']}"
            )
            if row.get("share_of_worlds_at_or_beyond_observed") is not None:
                out.append(
                    f"      only {row['worlds_at_or_beyond_observed']} of "
                    f"{len(result['replay']['worlds'])} tested worlds were this slow or slower "
                    f"({row['share_of_worlds_at_or_beyond_observed']:.0%})"
                )
        out.append(f"  {ms['framing']}")

    out.append(rule("CALIBRATION"))
    cal = result["calibration"]
    out.append(f"  attempted {cal['attempted']} edges, calibrated {cal['calibrated']}")
    for skip in cal["not_identifiable"]:
        out.append(f"    refused {skip['edge']}: {skip['reason']}")
    for rec in cal["records"]:
        out.append(
            f"    {rec['edge_id']}: {rec['prior_range']['central']} -> "
            f"{rec['calibrated_range']['central']:.3f} (moved {rec['movement']:.3f})"
        )
    out.append(f"  {cal['limitation']}")

    out.append(rule("PIVOTAL ASSUMPTIONS x EVIDENCE"))
    for row in result["gaps"]["gaps"]:
        out.append(
            f"  {row['edge']:<45} influence {row['influence_rank']:<7} "
            f"evidence {row['evidence']:<7} status {row['status']}"
        )
    critical = result["gaps"]["high_influence_low_evidence"]
    out.append(f"  high-influence / low-evidence edges: {[r['edge'] for r in critical] or 'none'}")

    out.append(rule("WHAT WOULD MOST IMPROVE THIS MODEL"))
    for req in result["data_requirements"]:
        variables = ", ".join(f"{c['variable']} ({c['unit']})" for c in req["collect"])
        out.append(f"  {req['edge']}: collect {variables}")
        out.append(f"      because {req['why']}; holder: {req['likely_holder']}")

    out.append("")
    out.append(render_model_health(result["model_health"]))

    return "\n".join(out)


def render_report(result: dict) -> str:
    """Markdown replay report — intended to be readable as scientific audit material."""
    ep = result["episode"]
    replay = result["replay"]
    ev = result["evaluation"]
    cov = result["coverage"]
    cal = result["calibration"]
    hind = replay["hindsight_check"]

    lines: list[str] = []
    a = lines.append

    a(f"# Historical replay — {ep.title}")
    a("")
    a("> Generated by `python scripts/replay_port_event.py "
      f"{ep.id} --write-report`. Deterministic: rerunning reproduces this file exactly.")
    a("")
    a("## Event")
    a("")
    a(f"- **Episode id:** `{ep.id}`")
    a(f"- **Modules:** {', '.join(ep.modules)}")
    a(f"- **Event start:** {ep.start_date} (week 1)")
    a(f"- **Knowledge cutoff:** {ep.knowledge_cutoff}")
    a(f"- **Evaluation window:** {ep.evaluation_window.get('from')} → {ep.evaluation_window.get('to')}")
    a(f"- **Simulated horizon:** {ep.turns} weeks")
    a("")
    a("**Why this event was chosen**")
    a("")
    for reason in ep.why_this_event:
        a(f"- {reason}")
    a("")
    a("**Injected event**")
    a("")
    a("| Phase | Weeks | port_capacity | Shape | Status |")
    a("|---|---|---|---|---|")
    for e in ep.all_events():
        span = f"{e.start_turn}–{e.start_turn + e.duration - 1}"
        target = ", ".join(f"{k} {v:+.0f}" for k, v in e.targets.items())
        a(f"| `{e.id}` | {span} | {target} | {e.shape} | {e.status} |")
    a("")
    a(f"> {ep.event_status_note}")
    a("")

    a("## Knowledge cutoff and hindsight")
    a("")
    a(f"{hind['rule']}")
    a("")
    a("| Initialised variable | Value source | Refers to | Published | Admissible |")
    a("|---|---|---|---|---|")
    for entry in hind["initial_state_checked"]:
        a(f"| `{entry['variable']}` | `{entry['source_id']}` | {entry['refers_to_period'] or '—'} "
          f"| {entry['available_at']} | {'yes' if entry['ok'] else '**NO**'} |")
    a("")
    prov = ep.initial_state_provenance.get("shipping_delay", {})
    if prov.get("note"):
        a(f"> {prov['note']}")
        a("")

    a("## Observation sources")
    a("")
    a("| Source | Type | Publisher | Published | Accessed |")
    a("|---|---|---|---|---|")
    for s in result["sources"]:
        a(f"| `{s['id']}` | {s['type']} | {s['publisher']} | {s.get('published_at') or '—'} "
          f"| {s['accessed_at']} |")
    a("")
    a(f"> {result['observation_metadata'].get('note', '')}")
    a("")
    a(f"**Turn mapping rule:** {result['observation_metadata'].get('turn_mapping_rule', '')}")
    a("")
    a("**Observed series used for scoring**")
    a("")
    a("| Variable | Week | Date | Value | Unit | Source | Published |")
    a("|---|---|---|---|---|---|---|")
    for obs in result["observations"]:
        if not obs.is_scoreable():
            continue
        a(f"| `{obs.variable}` | {obs.turn} | {obs.date} | {obs.value} | {obs.unit} "
          f"| `{obs.source}` | {obs.available_at} |")
    a("")
    a("**Variables with no observations** (not evaluated)")
    a("")
    for item in result["observation_metadata"].get("not_observed", []):
        a(f"- `{item['variable']}` — {item['reason']}")
    a("")

    a("## World slice and evidence coverage")
    a("")
    a("| Evidence group | Edges | Share | Influence-weighted share |")
    a("|---|---|---|---|")
    for group, label in cov["group_labels"].items():
        a(f"| {label} | {cov['by_group'].get(group, 0)} | {100 * cov['shares'].get(group, 0):.0f}% "
          f"| {100 * cov['weighted']['shares'].get(group, 0):.0f}% |")
    a("")
    a(f"> Weighting method: {cov['weighted']['weighting_method']}")
    a("")
    if result["provenance_errors"]:
        a("**Provenance errors**")
        a("")
        for err in result["provenance_errors"]:
            a(f"- {err}")
    else:
        a("Every edge's declared evidence status is supported by its provenance "
          "(`event_sim.evidence.registry.validate_slice_provenance`).")
    a("")

    a("## Simulation envelope")
    a("")
    a(f"{replay['world_count']} worlds were run — one per combination of assumption settings. "
      "The envelope is the range across those worlds; it is not a confidence interval.")
    a("")
    for variable in ("shipping_delay",):
        env = replay["envelope"].get(variable)
        if not env:
            continue
        a(f"**`{variable}`**")
        a("")
        a("| Week | " + " | ".join(str(t) for t in env["turns"]) + " |")
        a("|---" * (len(env["turns"]) + 1) + "|")
        a("| low | " + " | ".join(f"{v:.2f}" for v in env["low"]) + " |")
        a("| median | " + " | ".join(f"{v:.2f}" for v in env["median"]) + " |")
        a("| high | " + " | ".join(f"{v:.2f}" for v in env["high"]) + " |")
        a("")

    a("## Evaluation")
    a("")
    if result["evaluation_error"]:
        a(f"**Not evaluated:** {result['evaluation_error']}")
    else:
        a(f"- **Scored points:** {ev['scored_points']}")
        a(f"- **Overall envelope coverage:** {ev['overall_coverage_rate']:.0%}"
          if ev["overall_coverage_rate"] is not None else "- **Overall envelope coverage:** n/a")
        a(f"- **Evaluated variables:** {', '.join(ev['evaluated_variables'])}")
        a(f"- **Unevaluated variables:** {', '.join(ev['unevaluated_variables'])}")
        a("")
        for row in ev["variables"]:
            t = row["trajectory"]
            a(f"### `{row['variable']}` ({row['unit']})")
            a("")
            a("| Metric | Value |")
            a("|---|---|")
            a(f"| Envelope coverage | {row['inside']} of {row['scored_points']} points inside |")
            a(f"| First divergence | week {row['first_divergence_turn']} |")
            a(f"| Mean envelope width | {row['mean_envelope_width']:.2f} |")
            a(f"| Direction observed / simulated | {t['direction_observed']} / {t['direction_simulated']} "
              f"({'match' if t['direction_match'] else 'MISMATCH'}) |")
            a(f"| Observed peak | {t['observed_peak']['value']:.2f} at week {t['observed_peak']['turn']} |")
            a(f"| Simulated peak | {t['simulated_peak']['value']:.2f} at week {t['simulated_peak']['turn']} |")
            a(f"| Peak timing error | {t['peak_timing_error_turns']:+d} weeks |")
            a(f"| Peak magnitude error | {t['peak_magnitude_error']:+.2f} |")
            a(f"| MAE | {t['mae']:.2f} |")
            if t.get("normalized_mae") is not None:
                a(f"| Normalised MAE | {t['normalized_mae']:.2f} |")
            if t.get("correlation") is not None:
                a(f"| Correlation | {t['correlation']:.3f} |")
            a(f"| Observed recovery | {t.get('observed_recovery_turn') if t.get('observed_recovery_turn') is not None else 'not reached in window'} |")
            a(f"| Simulated recovery | week {t.get('simulated_recovery_turn')} |")
            a("")
            for point in row["outside"]:
                a(f"- Week {point['turn']} ({point['date']}): observed {point['observed']:.2f} "
                  f"fell **{point['direction']}** the envelope [{point['envelope'][0]:.2f}, "
                  f"{point['envelope'][1]:.2f}] by {abs(point['distance']):.2f}")
            a("")

    a("## Calibration")
    a("")
    a(f"- Attempted: {cal['attempted']} edges")
    a(f"- Calibrated: {cal['calibrated']} edges")
    a("")
    if cal["not_identifiable"]:
        a("**Refused (not identifiable from this episode):**")
        a("")
        a("| Edge | Reason |")
        a("|---|---|")
        for skip in cal["not_identifiable"]:
            a(f"| `{skip['edge']}` | {skip['reason']} |")
        a("")
    for rec in cal["records"]:
        a(f"**`{rec['edge_id']}`** — prior central {rec['prior_range']['central']} → "
          f"calibrated {rec['calibrated_range']['central']:.3f} (moved {rec['movement']:.3f}, "
          f"cap {rec['max_movement_allowed']:.3f})")
        a("")
    a(f"> {cal['limitation']}")
    a("")
    a("No coefficient in `world_models/supply_chain/port_disruption.json` was modified by "
      "this replay. Calibration records are written to `event_sim/evidence_data/calibrations.json`; "
      "promoting an edge is a separate, deliberate human step.")
    a("")

    a("## Pivotal assumptions vs evidence")
    a("")
    a("| Edge | Influence | Evidence | Status | Priority |")
    a("|---|---|---|---|---|")
    for row in result["gaps"]["gaps"]:
        a(f"| `{row['edge']}` | {row['influence_rank']} | {row['evidence']} | {row['status']} "
          f"| {row['priority']:.3f} |")
    a("")
    a(f"> {result['gaps']['priority_formula']}")
    a("")
    critical = result["gaps"]["high_influence_low_evidence"]
    if critical:
        a("**High influence, low evidence — the top research priorities:**")
        a("")
        for row in critical:
            a(f"- `{row['edge']}` — influence {row['influence_rank']}, evidence {row['evidence']} ({row['status']})")
    else:
        a("No edge is simultaneously ranked HIGH influence and LOW evidence.")
    a("")

    a("## What would most improve this model")
    a("")
    for req in result["data_requirements"]:
        variables = ", ".join(f"`{c['variable']}` ({c['unit']})" for c in req["collect"])
        a(f"- **{req['edge']}** — collect {variables} at weekly frequency. {req['why']}. "
          f"Likely holder: {req['likely_holder']}.")
    a("")

    a("## Limitations")
    a("")
    a("- One episode only: calibration and evaluation share the same window, so nothing here "
      "is out-of-sample validation.")
    a("- The only scoreable series is a **global monthly aggregate** standing in for a "
      "**single-port weekly** variable. See mapping `map_delay_from_si_global`.")
    a("- Mid-2021 container shipping was disrupted by many simultaneous causes; movement in "
      "the observed series cannot be attributed to this port.")
    a("- Six of the model's eight variables have no observations at all, including the "
      "headline outcome `service_level`.")
    a("- The injected event's magnitude comes from reported operating-capacity percentages, "
      "not measured throughput.")
    return "\n".join(lines)


def render_cross_event(diag: dict) -> str:
    """Markdown diagnosis report: does the same failure appear on an independent event?"""
    lines: list[str] = []
    a = lines.append

    a("# Cross-event diagnosis — is the failure in the model or in the measurement?")
    a("")
    a("> Generated by `python scripts/replay_port_event.py --cross-event --write-report`. "
      "The world model was **frozen** across both replays: no coefficient, lag, polarity or "
      "topology was changed between them.")
    a("")
    a("## Why a second event was necessary")
    a("")
    a("The Yantian 2021 replay produced a large timing error (-9 weeks). A single event "
      "cannot distinguish two explanations:")
    a("")
    a("1. **The model is wrong** — its post-shock persistence is too weak, so everything peaks "
      "and recovers too early.")
    a("2. **The measurement was wrong** — the only obtainable observable was a global monthly "
      "aggregate standing in for a single-port weekly variable.")
    a("")
    a("A second event, chosen to differ on every dimension that could produce a spurious "
      "result, separates them.")
    a("")
    a("| | Yantian 2021 | Baltimore 2024 |")
    a("|---|---|---|")
    a("| Year | 2021 | 2024 |")
    a("| Region | South China | US East Coast |")
    a("| Trigger | COVID labour absence | physical channel blockage |")
    a("| Background regime | global congestion wave | normal conditions |")
    a("| Capacity loss | to ~30% of normal | to zero |")
    a("| Duration | ~4.5 weeks | ~11 weeks |")
    a("| Observable tested | global monthly delay (proxy) | dated local restoration milestones |")
    a("| Capacity path | injected in phases | **model output** |")
    a("")
    a("The two replays share no data source, no observable and no measurement method.")
    a("")
    a("## Every timing test, both events")
    a("")
    a("| Episode | Test | Observed week | Simulated (median) | Error | Inside envelope | Evidence |")
    a("|---|---|---|---|---|---|---|")
    for f in diag["timing_findings"]:
        inside = ("—" if f["inside_envelope"] is None
                  else ("yes" if f["inside_envelope"] else "**no**"))
        a(f"| `{f['episode']}` | {f['test']} | {f['observed_turn']} | {f['simulated_turn']} "
          f"| {f['error_turns']:+d} | {inside} | {f['evidence']} |")
    a("")
    a("## Bias metrics")
    a("")
    a("A single R² or MAE cannot express the thing that matters for a disruption model — "
      "whether its clock runs at the right speed. Two Event-Simulator-specific metrics:")
    a("")
    bias = diag["bias"]
    a("| Metric | n | Errors (turns) | Median | Episodes | Verdict |")
    a("|---|---|---|---|---|---|")
    for key in ("peak_timing_bias", "recovery_bias", "combined_timing_bias"):
        row = bias[key]
        if not row.get("n"):
            a(f"| `{key}` | 0 | — | — | — | untested |")
            continue
        a(f"| `{key}` | {row['n']} | {', '.join(f'{e:+d}' for e in row['errors'])} "
          f"| **{row['median']:+d}** | {', '.join(row['episodes'])} | {row['verdict']} |")
    a("")
    for name, text in bias["definitions"].items():
        a(f"- **{name}** — {text}")
    a("")
    a(f"**{bias['headline']}.**")
    a("")

    a("## Verdict")
    a("")
    a(f"- Scored timing tests: **{diag['scored_timing_tests']}**")
    a(f"- Tests where the model was too early: **{diag['tests_too_early']}**")
    a(f"- Tests where the model was too late: **{diag['tests_too_late']}**")
    a(f"- Episodes showing the early bias: **{', '.join(diag['episodes_showing_early_bias'])}**")
    a(f"- Pattern repeats across independent events: "
      f"**{'YES' if diag['pattern_repeats'] else 'no'}**")
    a("")
    a("**Every timing error in both events has the same sign: the model is too fast.** That "
      "bias survives a change of year, continent, trigger, background regime and — most "
      "importantly — of measurement method. It is therefore not an artefact of the Yantian "
      "proxy alone.")
    a("")
    a("### What this does NOT establish")
    a("")
    a("- Baltimore's **hard observed milestone (week 11) is INSIDE the simulated envelope** — "
      "about a third of the tested worlds were that slow or slower. The model's *central* case "
      "is 6 weeks early, but its assumption range does contain the truth. That is a biased "
      "median, not a strict falsification.")
    a("- The only Baltimore test falling strictly outside the envelope is `normal_operations`, "
      "and that milestone is recorded as **reported, not observed** (an expectation published "
      "before the fact), so it is deliberately excluded from the scored count.")
    a("- Two events is a pattern, not a proof.")
    a("")
    a("So the honest statement is: **a consistent directional bias, reproduced on an "
      "independent event and an independent measurement method — not yet a strict "
      "falsification.**")
    a("")
    a("## Competing structural hypotheses")
    a("")
    a("The bias is consistent with the topology lacking an accumulating stock. The model is "
      "shaped `shock → propagation → relaxation`, so when the shock is released every variable "
      "begins returning to baseline immediately. The real sequence appears closer to "
      "`shock → queue accumulation → congestion → downstream backlog → capacity returns → "
      "backlog keeps propagating → delayed peak → clearing`. **A reopened port is not a "
      "cleared queue.**")
    a("")
    a("| # | Hypothesis | Mechanism | How it would be tested |")
    a("|---|---|---|---|")
    for h in STRUCTURAL_HYPOTHESES:
        a(f"| {h['id']} | **{h['name']}** | {h['mechanism']} | {h['test']} |")
    a("")
    a("**None of these has been implemented, and no coefficient was changed.** Adopting one "
      "now — on two events, with the fitting window equal to the evaluation window — would be "
      "exactly the overfitting this project has already documented once "
      "(`docs/FITTING_FINDINGS.md`).")
    a("")
    a("## What this replaces")
    a("")
    a("The Yantian report concluded the failure was most likely the measurement. Baltimore "
      "removes that as a *sufficient* explanation: the same bias appears with a completely "
      "different measurement method, on a variable the model actually outputs rather than one "
      "we injected. The measurement problem is real and remains the binding constraint on "
      "validation, but the structural hypothesis is now at least as credible.")
    a("")
    a("## Next experiment")
    a("")
    a("1. Add a **third** disruption with a locally observed series, not just milestones.")
    a("2. Implement H1 and H2 as *alternative* modules, leaving the current module untouched.")
    a("3. Fit each candidate on one event and evaluate on a **held-out** event.")
    a("4. Adopt a structural change only if it improves held-out timing error, and record it "
      "as a calibration record with its prior preserved.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode_id", nargs="?", help="historical episode id (see --list)")
    parser.add_argument("--list", action="store_true", help="list available episodes")
    parser.add_argument("--write-report", action="store_true", help="write docs/replays/<id>.md")
    parser.add_argument("--tolerance", type=float, default=0.0, help="widen the envelope by this fraction before testing coverage")
    parser.add_argument("--json", action="store_true", help="emit the raw evaluation payload as JSON")
    parser.add_argument("--cross-event", action="store_true",
                        help="replay every episode against the frozen model and diagnose repeated failures")
    args = parser.parse_args()

    if args.cross_event:
        episode_ids = [str(e["id"]) for e in available_episodes()]
        if len(episode_ids) < 2:
            print("Cross-event diagnosis needs at least two episodes.")
            return 1
        diag = cross_event_diagnosis(episode_ids, run_pipeline)
        report = render_cross_event(diag)
        print(report)
        if args.write_report:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            path = REPORTS_DIR / "CROSS_EVENT_DIAGNOSIS.md"
            path.write_text(report + "\n", encoding="utf-8")
            print(f"\nReport written to {path.relative_to(_PROJECT_ROOT)}")
        return 0

    if args.list or not args.episode_id:
        episodes = available_episodes()
        if not episodes:
            print("No historical episodes are defined. See event_sim/historical/events/README.md.")
            return 1
        print("Available episodes:")
        for ep in episodes:
            print(f"  {ep['id']:<20} {ep['title']}  (start {ep['start_date']}, cutoff {ep['knowledge_cutoff']})")
        return 0

    result = run_pipeline(args.episode_id, tolerance=args.tolerance)

    if args.json:
        payload = {
            "evaluation": result["evaluation"],
            "calibration": result["calibration"],
            "gaps": result["gaps"],
            "coverage": result["coverage"],
            "hindsight_check": result["replay"]["hindsight_check"],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render_console(result))

    if args.write_report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / f"{args.episode_id}.md"
        path.write_text(render_report(result) + "\n", encoding="utf-8")
        print(f"\nReport written to {path.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
