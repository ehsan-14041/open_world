"""
Generate the cafe cost-shock decision report — for the demo cafe or a real one.

    python scripts/cafe_decision_report.py                          # demo cafe
    python scripts/cafe_decision_report.py --inputs my_cafe.json    # a real cafe
    python scripts/cafe_decision_report.py --inputs my_cafe.json --out reports/my_cafe

The inputs file holds the eight intake fields (see event_sim/cafe/baseline.py INTAKE_FIELDS).
Everything else — model, coefficients, horizon, sensitivity grid — is fixed, so two cafes are
compared by the same instrument.

Runs the full sensitivity sweep (162 combinations × 3 worlds through the engine), so expect a
few minutes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_sim.cafe.baseline import DEMO_CAFE, CafeBaseline  # noqa: E402
from event_sim.cafe.report import write_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", help="JSON file with the intake fields for a real cafe")
    ap.add_argument("--out", default=None, help="output directory (default: reports/cafe_demo or reports/<name>)")
    ap.add_argument("--no-grid", action="store_true", help="skip the in-page assumption grid (faster, page not interactive)")
    ap.add_argument("--reformulation-effectiveness", type=float, default=None,
                    help="COGS points saved per point of low-margin share (default 0.30); use when the owner has costed the items")
    ap.add_argument("--custom-elasticity", type=float, default=None,
                    help="use this price elasticity (e.g. 0.5) instead of the three-setting axis; labelled as the customer's value")
    args = ap.parse_args(argv)

    if args.inputs:
        raw = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        raw.setdefault("is_demo", False)
        baseline = CafeBaseline.from_dict(raw)
    else:
        baseline = DEMO_CAFE

    problems = baseline.validate()
    if problems:
        print("Inputs are not usable:")
        for p in problems:
            print("  -", p)
        return 2

    out_dir = Path(args.out) if args.out else Path("reports") / (
        "cafe_demo" if baseline.is_demo else baseline.name.lower().replace(" ", "_")
    )
    t0 = time.time()
    print(f"Generating report for {baseline.name} -> {out_dir}")
    paths = write_report(baseline, out_dir, include_grid=not args.no_grid, custom_elasticity=args.custom_elasticity,
                         reformulation_effectiveness=args.reformulation_effectiveness)
    print(f"  {paths['html']}")
    print(f"  {paths['json']}")
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
