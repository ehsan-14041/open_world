"""
Package a generated cafe report into a folder you can upload to any PHP host.

    python scripts/build_web_bundle.py                                  # the demo report
    python scripts/build_web_bundle.py --report reports/corner_bean     # a real cafe
    python scripts/build_web_bundle.py --password hunter2 --zip

The report is a self-contained static page. PHP is used only to gzip it (about 1 MB -> 75 KB)
and, optionally, to keep it behind a shared password. See deploy/php/README_DEPLOY.md.
"""

from __future__ import annotations

import argparse
import gzip
import secrets
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "php"


def build(report_dir: Path, out_dir: Path, password: str | None, heading: str | None,
          make_zip: bool) -> dict[str, Path]:
    html = report_dir / "cafe_decision_report.html"
    if not html.is_file():
        raise SystemExit(f"No report at {html}. Generate one first with scripts/cafe_decision_report.py.")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(TEMPLATE, out_dir)

    raw = html.read_bytes()
    # A random name keeps the payload unreachable on servers that ignore .htaccess (nginx, the
    # PHP dev server), where a fixed data/report.html.gz would walk straight around the gate.
    # mtime=0 so the gzip body itself is reproducible.
    payload = out_dir / "data" / f"report-{secrets.token_hex(8)}.html.gz"
    payload.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))

    if password:
        sample = (out_dir / "config.sample.php").read_text(encoding="utf-8")
        cfg = sample.replace("'change-me'", repr(password).replace('"', "'"))
        cfg = cfg.replace("Rename this file to config.php on the server.",
                          "Written by scripts/build_web_bundle.py.")
        if heading:
            cfg = cfg.replace("'Decision Comparison'", repr(heading).replace('"', "'"))
        (out_dir / "config.php").write_text(cfg, encoding="utf-8")

    written = {"dir": out_dir}
    if make_zip:
        archive = out_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(out_dir.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(out_dir))
        written["zip"] = archive

    gz = payload.stat().st_size
    print(f"report  {len(raw):>9,} bytes -> {gz:,} bytes gzipped")
    for label, path in written.items():
        print(f"{label:<7} {path}")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default="reports/cafe_demo", help="directory holding cafe_decision_report.html")
    ap.add_argument("--out", default=None, help="output directory (default: dist/<report name>_web)")
    ap.add_argument("--password", default=None, help="write config.php with this shared password")
    ap.add_argument("--heading", default=None, help="heading on the password screen")
    ap.add_argument("--zip", action="store_true", help="also produce a .zip to upload")
    args = ap.parse_args(argv)

    report_dir = Path(args.report)
    out_dir = Path(args.out) if args.out else ROOT / "dist" / f"{report_dir.name}_web"
    build(report_dir, out_dir, args.password, args.heading, args.zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
