"""
Assemble the three demos into one browsable set.

    python scripts/build_demo_site.py

Expects the three reports to exist already (scripts/wedge_report.py --all). Produces:

    reports/demo_site/index.html          the chooser screen
    reports/demo_site/<wedge>/…           each wedge's report and its data

Nothing here computes anything. It copies finished artifacts and writes the chooser, so the
reports a customer sees are byte-for-byte the ones the audit was run against.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.wedge.registry import CHOOSER  # noqa: E402

CHOOSER_TEMPLATE = ROOT / "event_sim" / "wedge" / "templates" / "chooser.html"
OUT = ROOT / "reports" / "demo_site"


def main() -> int:
    missing = []
    OUT.mkdir(parents=True, exist_ok=True)

    for entry in CHOOSER:
        wid = entry["id"]
        src = ROOT / "reports" / f"{wid}_demo"
        html = src / f"{wid}_decision_report.html"
        if not html.is_file():
            missing.append(str(html))
            continue
        dest = OUT / wid
        dest.mkdir(parents=True, exist_ok=True)
        for name in (f"{wid}_decision_report.html", f"{wid}_decision_report.json"):
            if (src / name).is_file():
                shutil.copy2(src / name, dest / name)
        print(f"  {wid:6} {html.stat().st_size:>10,} bytes")

    if missing:
        print("\nMissing reports — run: python scripts/wedge_report.py --all")
        for m in missing:
            print("  ", m)
        return 2

    shutil.copy2(CHOOSER_TEMPLATE, OUT / "index.html")
    print(f"\n  index  {(OUT / 'index.html').stat().st_size:>10,} bytes")
    print(f"\nOpen {OUT / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
