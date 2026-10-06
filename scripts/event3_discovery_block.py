"""
Run frozen Detector v3 over one Event #3 discovery block.

Detection only. Consults no historical source, imports nothing from H1, the engine or the
world models, and changes no detector parameter.

    python scripts/event3_discovery_block.py --block 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.detect import baseline, detector_v3 as dv3, discovery as dsc, series  # noqa: E402
from event_sim.ingest import ais  # noqa: E402

MIN_ACQUIRED_SHARE = 0.90


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", type=int, required=True)
    args = ap.parse_args(argv)

    blocks = {b.index: b for b in dsc.discovery_blocks()}
    if args.block not in blocks:
        ap.error(f"block {args.block} not in the frozen universe {sorted(blocks)}")
    block = blocks[args.block]

    region = ais.REGIONS["hampton_roads"]
    all_days = block.all_days
    built = series.build(region, all_days)
    by = {d.date: d for d in built.days}

    occ = [float(by[d].anchorage_occupancy) if d in by else None for d in all_days]
    ves = [float(by[d].vessels_in_region) if d in by else None for d in all_days]
    den = [by[d].messages_per_vessel if d in by else None for d in all_days]
    foo = [float(by[d].region_cells) if d in by else None for d in all_days]

    acquired = sum(1 for v in occ if v is not None)
    if acquired / len(all_days) < MIN_ACQUIRED_SHARE:
        print(json.dumps({
            "outcome": "MEASUREMENT_INTEGRITY_FAILURE",
            "reason": "acquisition below tolerance",
            "days_wanted": len(all_days), "days_acquired": acquired,
        }, indent=2))
        return 2

    rows = dv3.occupancy_residuals(all_days, occ)
    regimes = dv3.classify_series(all_days, ves, den, foo)
    windows = dv3.detect_occupancy(rows)

    # Warmup days are acquired but are never discovery days: a trigger may only be reported if
    # it starts on or after the block's first discovery day.
    windows = [w for w in windows if w.start >= block.discovery_start]
    verdicts = dv3.classify_windows(windows, rows, regimes)

    resid_by_date = {r.date: r.residual for r in rows}
    enriched = []
    for w in verdicts:
        rec = dsc.find_recovery(all_days, [resid_by_date[d] for d in all_days], w.end)
        d = w.as_dict()
        d["residual_trajectory"] = [
            resid_by_date[x] for x in all_days if w.start <= x <= w.end
        ]
        d["recovery_observed"] = rec is not None
        d["recovery_completed_on"] = rec
        enriched.append(d)

    discovery_rows = [r for r in rows if r.date >= block.discovery_start]
    defined = [r.residual for r in discovery_rows if r.residual is not None]
    disc_dates = {r.date for r in discovery_rows if r.residual is not None}

    artifacts = {}
    for d in all_days:
        p = ais.METADATA_DIR / f"hampton_roads_{d}.json"
        if p.exists():
            artifacts[d] = json.loads(p.read_text(encoding="utf-8"))["national_sha256"]
    ledger_hash = hashlib.sha256(
        json.dumps(artifacts, sort_keys=True).encode()
    ).hexdigest()

    report = {
        "block": block.index,
        "span": list(block.span),
        "warmup": [block.warmup_start, block.warmup_end],
        "discovery": [block.discovery_start, block.discovery_end],
        "days_acquired": acquired,
        "days_wanted": len(all_days),
        "discovery_days_evaluable": len(defined),
        "detector_semantic_hash": "49ed3b935527f1fb000ad348c411c5049070b672eb01eea69e4f457e97022f73",
        "artifact_set_sha256": ledger_hash,
        "occupancy_distribution": baseline.describe([v for v in occ if v is not None]).as_dict(),
        "residual_distribution": baseline.describe(defined).as_dict(),
        "threshold_reachability": dv3.threshold_reachability(discovery_rows),
        "coverage_regime_counts": dict(
            Counter(g.regime for g in regimes if g.date in disc_dates)
        ),
        "trigger_count": len(enriched),
        "trigger_windows": enriched,
    }

    print(json.dumps(report, indent=2, default=str))
    out = Path(f"data/external/ais/event3_discovery_block_{block.index}.json")
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
