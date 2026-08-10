"""
Acquire the AIS days named by the frozen sampling rule.

Each national daily file is ~284 MB, so this is bandwidth-bound rather than CPU-bound. A
small thread pool overlaps the downloads; the cap is deliberately modest because the
publisher is a public agency serving these files for free.

Days already present are skipped, so the script is resumable and re-running it is cheap.

    python scripts/fetch_ais_baseline.py [--workers 4] [--region hampton_roads]
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.detect.sampling import baseline_days  # noqa: E402
from event_sim.ingest import ais  # noqa: E402

#: Concurrent downloads. Kept low on purpose: NOAA serves these at no charge.
DEFAULT_WORKERS = 4


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--region", default="hampton_roads")
    args = parser.parse_args(argv)

    region = ais.REGIONS[args.region]
    days = baseline_days()

    pending = [
        d for d in days if not (ais.DAILY_DIR / f"{region.name}_{d}.csv").exists()
    ]
    print(f"{len(days)} sampled days, {len(pending)} to fetch, {args.workers} workers")
    if not pending:
        return 0

    started = time.time()
    done = failed = 0
    total_bytes = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(ais.fetch_day, d, region): d for d in pending}
        for fut in as_completed(futures):
            day = futures[fut]
            try:
                rec = fut.result()
            except Exception as exc:  # noqa: BLE001 - reported per day, never silent
                failed += 1
                print(f"  FAILED {day}: {type(exc).__name__}: {exc}", flush=True)
                continue
            done += 1
            total_bytes += rec["national_bytes"]
            elapsed = time.time() - started
            print(
                f"  [{done + failed}/{len(pending)}] {day} "
                f"kept={rec['regional_rows_kept']:>6} mmsi={rec['distinct_mmsi']:>3} "
                f"({elapsed / 60:.1f} min elapsed)",
                flush=True,
            )

    print(
        f"done: {done} fetched, {failed} failed, "
        f"{total_bytes / 1e9:.1f} GB transferred in {(time.time() - started) / 60:.1f} min"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
