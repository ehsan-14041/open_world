"""
Compute the Hampton Roads baseline distribution and apply the frozen power criteria.

Reads only acquired AIS extracts and the frozen measurement definition. Imports nothing from
the engine, the world models, H1, or any list of historical events.

    python scripts/hampton_roads_detectability.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.detect import anomaly, baseline, series  # noqa: E402
from event_sim.detect.sampling import baseline_days, baseline_windows  # noqa: E402
from event_sim.ingest import ais  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    region = ais.REGIONS["hampton_roads"]
    wanted = baseline_days()
    result = series.build(region, wanted)

    acquired = [d.date for d in result.days]
    missing = [d for d in wanted if d not in set(acquired)]
    missing_rate = len(missing) / len(wanted) if wanted else 1.0

    occ = [float(v) for v in result.occupancy]
    dates = [d.date for d in result.days]
    windows = [d.window for d in result.days]

    occ_dist = baseline.describe(occ)
    entries = [d.entries for d in result.days if d.entries is not None]
    exits = [d.exits for d in result.days if d.exits is not None]

    completed = result.completed_spells
    dwell = [s.duration_hours for s in completed]
    dwell_dist = baseline.describe(dwell)

    verdict = anomaly.power_verdict(
        occupancy=occ,
        p90=occ_dist.p90,
        median=occ_dist.median,
        mad=occ_dist.mad,
        completed_spells=len(completed),
        missing_rate=missing_rate,
    )

    report = {
        "sampled_windows": baseline_windows(),
        "days_wanted": len(wanted),
        "days_acquired": len(acquired),
        "days_missing": missing,
        "missing_rate": round(missing_rate, 4),
        "occupancy": occ_dist.as_dict(),
        "occupancy_histogram": baseline.value_histogram(occ),
        "dispersion_index": baseline.dispersion_index(occ),
        "autocorrelation_lag1": baseline.autocorrelation(occ, 1),
        "autocorrelation_lag2": baseline.autocorrelation(occ, 2),
        "weekday_effect": baseline.weekday_effect(dates, occ),
        "per_window": baseline.per_window(dates, windows, occ),
        "entries": baseline.describe(entries).as_dict(),
        "exits": baseline.describe(exits).as_dict(),
        "spells_total": len(result.spells),
        "spells_completed": len(completed),
        "spells_censored": len(result.spells) - len(completed),
        "dwell_hours_completed": dwell_dist.as_dict(),
        "thresholds": anomaly.thresholds_from(
            occ_dist.median, occ_dist.mad, dwell_dist.p90 if dwell else None
        ).as_dict(),
        "power_verdict": verdict.as_dict(),
        "vessels_in_region": baseline.describe(
            [d.vessels_in_region for d in result.days]
        ).as_dict(),
        "status_agreement": baseline.describe(
            [d.status_agreement_rate for d in result.days if d.status_agreement_rate is not None]
        ).as_dict(),
    }

    print(json.dumps(report, indent=2, default=str))
    out = Path("data/external/ais/hampton_roads_baseline.json")
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0 if verdict.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
