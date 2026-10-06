#!/usr/bin/env python3
"""
CLI demo of the Event Simulator vertical slice.

    python scripts/run_port_disruption.py
    python scripts/run_port_disruption.py --turns 24 --capacity-loss -85 --duration 8
    python scripts/run_port_disruption.py --json > run.json

Prints the same payload the /event-sim page renders: world slice, evidence coverage,
timeline, branch comparison, causal trace, emergent trajectories, pivotal assumptions.
No API key and no network access are required — nothing here calls a language model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.scenarios import port_disruption  # noqa: E402


def _rule(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


def render(payload: dict) -> str:
    out: list[str] = []
    out.append(f"QUESTION: {payload['question']}")
    out.append(payload["framing"])

    slice_ = payload["slice"]
    cov = payload["coverage"]
    out.append(_rule("WORLD SLICE"))
    out.append(f"Included : {', '.join(slice_['included_systems'])}")
    excluded = slice_["excluded_systems"]
    out.append(f"Excluded : {', '.join(excluded) if excluded else 'no other module in the library'}")
    out.append(f"Variables: {len(slice_['variables'])}   Causal edges: {len(slice_['edges'])}")

    out.append(_rule("EVIDENCE COVERAGE"))
    for group, label in cov["group_labels"].items():
        count = cov["by_group"].get(group, 0)
        share = 100 * cov["shares"].get(group, 0.0)
        out.append(f"  {label:<45} {count:>3} edges  {share:5.1f}%")
    out.append(f"  {cov['disclaimer']}")
    if cov["weakly_evidenced"]:
        out.append("  ** This model rests mainly on stated assumptions. Read every trajectory as conditional. **")

    world_a = payload["worlds"]["world_a"]
    ids = [v["variable"] for v in world_a["trajectory"][0]["variables"]]
    out.append(_rule(f"TIMELINE — {world_a['label']}"))
    out.append("  week " + "".join(f"{i[:13]:>14}" for i in ids))
    for rec in world_a["trajectory"]:
        row = "".join(f"{rec['state'][i]:>14.2f}" for i in ids)
        marks = ",".join(rec.get("events_active", []) + rec.get("interventions_active", []))
        out.append(f"  {rec['turn']:>4} {row}  {marks}")

    cmp_ = payload["comparison"]
    out.append(_rule("COMPARE WORLDS"))
    out.append(
        f"  Forked at week {cmp_['fork_turn']} · identical starting state: "
        f"{'VERIFIED' if cmp_['identical_at_fork'] else 'MISMATCH'} · "
        f"identical assumptions: {'VERIFIED' if cmp_['same_assumptions'] else 'NO'}"
    )
    out.append(f"  {'Variable':<26}{'A final':>12}{'B final':>12}{'Diff':>12}{'Peak diff':>14}")
    for row in cmp_["variables"]:
        out.append(
            f"  {row['variable']:<26}{row['final_a']:>12.2f}{row['final_b']:>12.2f}"
            f"{row['final_difference']:>+12.2f}{row['peak_difference']:>+11.2f} (w{row['peak_turn']})"
        )
    for line in payload["comparison_summary"]:
        out.append(f"  - {line}")

    out.append(_rule("CAUSAL TRACE (from execution provenance, not narration)"))
    out.append(payload["causal_trace_text"])

    sweep = payload.get("sweep")
    if sweep:
        out.append(_rule("EMERGENT TRAJECTORIES"))
        for traj in sweep["trajectories"]:
            out.append(f"  {traj['label']} — {traj['world_count']} of {sweep['world_count']} tested worlds")
            out.append(f"      {traj['description']}")
            out.append(f"      conditions: {'; '.join(traj['conditions'])}")
            if traj["critical_assumptions"]:
                out.append(f"      requires  : {'; '.join(traj['critical_assumptions'])}")
            for fp in traj["failure_points"][:3]:
                out.append(
                    f"      failure   : {fp['variable']} {fp['direction']} {fp['worst_value']:.2f} at week {fp['turn']}"
                )
        out.append(f"  {sweep['framing']}")

        pivotal = sweep["pivotal_assumptions"]
        out.append(_rule("PIVOTAL ASSUMPTIONS"))
        out.append(f"  What would have to be different for {pivotal['outcome_variable']} to change?")
        for axis in pivotal["axes"]:
            flips = "flips trajectory" if axis["changes_trajectory"] else ""
            out.append(
                f"  {axis['axis']:<24}{axis['rank']:<8}span {axis['influence']:.4f}   "
                f"{axis['worst_setting']} -> {axis['best_setting']}   {flips}"
            )
        out.append(f"  {pivotal['framing']}")

    out.append(_rule("MISSING EVIDENCE"))
    for item in slice_["missing_evidence"][:6]:
        out.append(f"  {item['edge']:<45} {item['status']:<20} needs: {item['needs']}")

    out.append(f"\nReproducible: fingerprint {world_a['fingerprint'][:16]}… (rerun with the same arguments to reproduce exactly)")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--turns", type=int, default=port_disruption.DEFAULT_TURNS)
    parser.add_argument("--capacity-loss", type=float, default=port_disruption.DEFAULT_CAPACITY_LOSS)
    parser.add_argument("--duration", type=int, default=port_disruption.DEFAULT_DURATION)
    parser.add_argument("--fork-turn", type=int, default=2)
    parser.add_argument("--redirect-share", type=float, default=0.3)
    parser.add_argument("--redirect-start", type=int, default=3)
    parser.add_argument("--no-sweep", action="store_true", help="skip the assumption sweep")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="emit the raw payload as JSON")
    args = parser.parse_args()

    payload = port_disruption.run_vertical_slice(
        turns=args.turns,
        capacity_loss=args.capacity_loss,
        duration=args.duration,
        fork_turn=args.fork_turn,
        redirect_share=args.redirect_share,
        redirect_start=args.redirect_start,
        include_sweep=not args.no_sweep,
        seed=args.seed,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
