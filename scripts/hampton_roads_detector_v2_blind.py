"""
Run frozen Detector v2 over the blind sample and apply the pre-registered criteria.

Reads only AIS extracts and the frozen measurement definition. Imports nothing from H1, the
engine, the world models, or any list of historical events, and consults no historical source.

    python scripts/hampton_roads_detector_v2_blind.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.detect import baseline, detector_v2 as dv2, series  # noqa: E402
from event_sim.detect.sampling import blind_days  # noqa: E402
from event_sim.ingest import ais  # noqa: E402

#: Pre-registered acquisition tolerance (protocol §7).
MIN_ACQUIRED_SHARE = 0.90

#: Pre-registered blind criteria (protocol §8).
C2_MAX_TRIGGER_SHARE = 0.10
C3_MEDIAN_RESIDUAL_BOUND = 0.5
C3_MAX_THIRD_DRIFT = 1.0
C5_MAX_CONFOUNDED_SHARE = 0.5


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    region = ais.REGIONS["hampton_roads"]
    wanted = blind_days()
    built = series.build(region, wanted)

    # Contiguous daily axis: a missing day is None, never a gap, so "no data" and "no
    # vessels" stay distinguishable.
    by_date = {d.date: d for d in built.days}
    occupancy: list[float | None] = [
        float(by_date[d].anchorage_occupancy) if d in by_date else None for d in wanted
    ]
    coverage: list[float | None] = [
        float(by_date[d].vessels_in_region) if d in by_date else None for d in wanted
    ]

    acquired = sum(1 for v in occupancy if v is not None)
    share = acquired / len(wanted)
    if share < MIN_ACQUIRED_SHARE:
        print(json.dumps({
            "outcome": "STOP_INCOMPLETE_ACQUISITION",
            "days_wanted": len(wanted), "days_acquired": acquired,
            "acquired_share": round(share, 4), "required": MIN_ACQUIRED_SHARE,
        }, indent=2))
        return 2

    rows = dv2.residuals(wanted, occupancy, coverage)
    windows = dv2.detect(rows)
    reach = dv2.threshold_reachability(rows)

    defined = [r.residual for r in rows if r.residual is not None]
    evaluable = len(defined)
    trigger_days = sum(w.duration_days for w in windows)
    trigger_share = trigger_days / evaluable if evaluable else 0.0

    third = max(1, evaluable // 3)
    first_third = statistics.median(defined[:third])
    last_third = statistics.median(defined[-third:])
    median_resid = statistics.median(defined)

    confounded = [w for w in windows if w.coverage_confounded]
    confounded_share = len(confounded) / len(windows) if windows else 0.0

    c1 = reach["reachable"]
    c2 = trigger_share <= C2_MAX_TRIGGER_SHARE
    c3 = (
        abs(median_resid) <= C3_MEDIAN_RESIDUAL_BOUND
        and abs(first_third - last_third) <= C3_MAX_THIRD_DRIFT
    )
    c4 = dv2.PERSISTENCE_DAYS < dv2.LOOKBACK_DAYS / 2
    c5 = confounded_share < C5_MAX_CONFOUNDED_SHARE

    if not c1:
        outcome = "DETECTOR_V2_TOO_INSENSITIVE"
    elif not c2:
        outcome = "DETECTOR_V2_TOO_SENSITIVE"
    elif not c5:
        outcome = "DETECTOR_V2_COVERAGE_CONFOUNDED"
    elif not c3:
        outcome = "DETECTOR_V2_INCONCLUSIVE"
    else:
        live = [w for w in windows if not w.coverage_confounded]
        outcome = "DETECTOR_V2_VALID_EVENT_FOUND" if live else "DETECTOR_V2_VALID_NO_EVENT"

    report = {
        "outcome": outcome,
        "days_wanted": len(wanted),
        "days_acquired": acquired,
        "days_missing": [d for d, v in zip(wanted, occupancy) if v is None],
        "evaluable_days": evaluable,
        "frozen_parameters": {
            "LOOKBACK_DAYS": dv2.LOOKBACK_DAYS,
            "MIN_LOOKBACK_PRESENT": dv2.MIN_LOOKBACK_PRESENT,
            "SCALE_FLOOR": dv2.SCALE_FLOOR,
            "RESIDUAL_THRESHOLD": dv2.RESIDUAL_THRESHOLD,
            "PERSISTENCE_DAYS": dv2.PERSISTENCE_DAYS,
            "COVERAGE_GUARD_RESIDUAL": dv2.COVERAGE_GUARD_RESIDUAL,
        },
        "occupancy_distribution": baseline.describe(
            [v for v in occupancy if v is not None]
        ).as_dict(),
        "coverage_distribution": baseline.describe(
            [v for v in coverage if v is not None]
        ).as_dict(),
        "residual_distribution": baseline.describe(defined).as_dict(),
        "threshold_reachability": reach,
        "trigger_count": len(windows),
        "trigger_days": trigger_days,
        "trigger_share_of_evaluable": round(trigger_share, 4),
        "trigger_windows": [w.as_dict() for w in windows],
        "coverage_flagged_days": sum(1 for r in rows if r.coverage_flag),
        "coverage_confounded_windows": len(confounded),
        "criteria": {
            "C1_threshold_reachable": c1,
            "C2_not_constantly_triggering": c2,
            "C3_baseline_adapts": c3,
            "C4_events_survive_adaptation": c4,
            "C5_not_coverage_dominated": c5,
        },
        "c3_detail": {
            "median_residual": round(median_resid, 4),
            "first_third_median": round(first_third, 4),
            "last_third_median": round(last_third, 4),
            "drift": round(abs(first_third - last_third), 4),
        },
    }

    print(json.dumps(report, indent=2, default=str))
    out = Path("data/external/ais/hampton_roads_detector_v2_blind.json")
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
