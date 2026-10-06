"""
Generate a decision report for any wedge — for its demo business or for a real one.

    python scripts/wedge_report.py cafe
    python scripts/wedge_report.py shop --inputs corner_store.json --out reports/corner_store
    python scripts/wedge_report.py salon --no-grid          # fast, page not interactive
    python scripts/wedge_report.py --all                    # all three demos

The inputs file holds that wedge's intake fields. Everything else — module, coefficients,
horizon, sensitivity grid — is fixed, so two businesses of the same type are compared by the
same instrument.

Runs the full sensitivity sweep (162 combinations x 3 decisions through the engine), so expect
a few minutes per wedge.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.wedge.registry import WEDGES, get  # noqa: E402
from event_sim.wedge.report import write_report  # noqa: E402


def generate(wedge_id: str, inputs: str | None, out: str | None, include_grid: bool,
             custom_elasticity: float | None = None) -> int:
    wedge = get(wedge_id)
    if inputs:
        raw = json.loads(Path(inputs).read_text(encoding="utf-8"))
        raw.setdefault("is_demo", False)
        baseline = wedge.baseline_from_dict(raw)
    else:
        baseline = wedge.demo_factory()

    problems = baseline.validate()
    if problems:
        print(f"{wedge_id}: inputs are not usable:")
        for p in problems:
            print("  -", p)
        return 2

    out_dir = Path(out) if out else Path("reports") / (
        f"{wedge_id}_demo" if baseline.is_demo else baseline.name.lower().replace(" ", "_")
    )
    t0 = time.time()
    print(f"[{wedge_id}] generating for {baseline.name} -> {out_dir}")
    paths = write_report(wedge, baseline, out_dir, include_grid=include_grid,
                         custom_elasticity=custom_elasticity)
    print(f"[{wedge_id}]   {paths['html']}")
    print(f"[{wedge_id}]   {paths['json']}")
    print(f"[{wedge_id}] done in {time.time() - t0:.0f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wedge", nargs="?", choices=sorted(WEDGES), help="which decision product")
    ap.add_argument("--all", action="store_true", help="generate every wedge's demo")
    ap.add_argument("--inputs", help="JSON file with this wedge's intake fields")
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--no-grid", action="store_true", help="skip the in-page assumption grid")
    ap.add_argument("--custom-elasticity", type=float, default=None,
                    help="use this price elasticity instead of the axis; labelled as the customer's value")
    args = ap.parse_args(argv)

    if args.all:
        if args.inputs:
            ap.error("--all generates the demo businesses; it cannot take --inputs")
        codes = [generate(w, None, None, not args.no_grid) for w in sorted(WEDGES)]
        return max(codes)
    if not args.wedge:
        ap.error("name a wedge, or pass --all")
    return generate(args.wedge, args.inputs, args.out, not args.no_grid, args.custom_elasticity)


if __name__ == "__main__":
    raise SystemExit(main())
