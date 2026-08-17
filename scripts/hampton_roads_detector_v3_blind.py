"""
Run frozen Detector v3 once over its blind sample.

Reports measurement stability first, occupancy detection second, and attaches an
independently computed coverage regime to every trigger. Performs no historical research and
imports nothing from H1, the engine, or the world models.

    python scripts/hampton_roads_detector_v3_blind.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.detect import baseline, detector_v3 as dv3, series  # noqa: E402
from event_sim.detect.sampling import v3_blind_days  # noqa: E402
from event_sim.ingest import ais  # noqa: E402

MIN_ACQUIRED_SHARE = 0.90


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    region = ais.REGIONS["hampton_roads"]
    days = v3_blind_days()
    built = series.build(region, days)
    by = {d.date: d for d in built.days}

    # Contiguous axis; a missing day is None, never a gap.
    occ: list[float | None] = [
        float(by[d].anchorage_occupancy) if d in by else None for d in days
    ]
    vessels: list[float | None] = [
        float(by[d].vessels_in_region) if d in by else None for d in days
    ]
    density: list[float | None] = [by[d].messages_per_vessel if d in by else None for d in days]
    footprint: list[float | None] = [
        float(by[d].region_cells) if d in by else None for d in days
    ]

    acquired = sum(1 for v in occ if v is not None)
    if acquired / len(days) < MIN_ACQUIRED_SHARE:
        print(json.dumps({
            "outcome": "STOP_INCOMPLETE_ACQUISITION",
            "days_wanted": len(days), "days_acquired": acquired,
        }, indent=2))
        return 2

    rows = dv3.occupancy_residuals(days, occ)
    regimes = dv3.classify_series(days, vessels, density, footprint)
    windows = dv3.detect_occupancy(rows)
    verdicts = dv3.classify_windows(windows, rows, regimes)
    trigger_days = sum(w.duration_days for w in windows)
    validity = dv3.evaluate_validity(rows, regimes, trigger_days)

    defined = [r.residual for r in rows if r.residual is not None]
    evaluable_dates = {r.date for r in rows if r.residual is not None}

    report = {
        "outcome": validity["outcome"],
        "recommend_stop_hampton_roads": validity["recommend_stop_hampton_roads"],
        "days_wanted": len(days),
        "days_acquired": acquired,
        "days_missing": [d for d, v in zip(days, occ) if v is None],
        "evaluable_days": validity["evaluable_days"],
        "frozen_parameters": {
            "LOOKBACK_DAYS": dv3.LOOKBACK_DAYS,
            "RESIDUAL_THRESHOLD": dv3.RESIDUAL_THRESHOLD,
            "PERSISTENCE_DAYS": dv3.PERSISTENCE_DAYS,
            "V_SHIFT": dv3.V_SHIFT,
            "M_ABRUPT": dv3.M_ABRUPT,
            "S_ABRUPT": dv3.S_ABRUPT,
            "M_STABLE": dv3.M_STABLE,
            "S_STABLE": dv3.S_STABLE,
        },
        # --- measurement stability, reported before any event interpretation -------------
        "coverage_regime_counts": dict(
            Counter(g.regime for g in regimes if g.date in evaluable_dates)
        ),
        "uncertain_day_share": validity["uncertain_day_share"],
        "abrupt_day_share": validity["abrupt_day_share"],
        "coverage_diagnostics": {
            "vessels_in_region": baseline.describe(
                [v for v in vessels if v is not None]
            ).as_dict(),
            "messages_per_vessel": baseline.describe(
                [v for v in density if v is not None]
            ).as_dict(),
            "region_cells": baseline.describe(
                [v for v in footprint if v is not None]
            ).as_dict(),
        },
        # --- occupancy detection ---------------------------------------------------------
        "occupancy_distribution": baseline.describe([v for v in occ if v is not None]).as_dict(),
        "residual_distribution": baseline.describe(defined).as_dict(),
        "threshold_reachability": validity["threshold_reachability"],
        "trigger_count": len(windows),
        "trigger_days": trigger_days,
        "trigger_day_share": validity["trigger_day_share"],
        "trigger_windows": [w.as_dict() for w in verdicts],
        "median_residual": validity["median_residual"],
        "third_drift": validity["third_drift"],
        "criteria": validity["checks"],
    }

    print(json.dumps(report, indent=2, default=str))
    out = Path("data/external/ais/hampton_roads_detector_v3_blind.json")
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
