"""
Package the PHP application into a folder you can upload to any PHP host.

    python scripts/build_web_bundle.py                       # ready to upload
    python scripts/build_web_bundle.py --password hunter2 --zip

The host runs the whole pipeline itself — engine, accounting, the 162-point sweep, rendering —
for all three wedges, from a port of the Python code that is verified to produce a
byte-identical bundle for each (scripts/verify_php_port.py). See deploy/php/README_DEPLOY.md.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "php"


def build(out_dir: Path, password: str | None, heading: str | None, make_zip: bool) -> dict[str, Path]:
    # Refresh the frozen instrument so a bundle can never ship a stale model or template.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_php_assets.py")],
                   check=True, capture_output=True)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(TEMPLATE, out_dir)

    # Runtime state must never travel in a bundle: settings.json can hold an API key, the cache
    # can hold a real cafe's figures, and a translation belongs to the install that made it.
    for pattern in ("data/cache/*.gz", "data/settings.json", "data/llm_usage.json",
                    "data/i18n/*.json", "config.php"):
        for leaked in out_dir.glob(pattern):
            leaked.unlink()

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

    total = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"bundle  {total:,} bytes")
    for label, path in written.items():
        print(f"{label:<7} {path}")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="output directory (default: dist/wedges_php)")
    ap.add_argument("--password", default=None, help="write config.php with this shared password")
    ap.add_argument("--heading", default=None, help="heading on the password screen")
    ap.add_argument("--zip", action="store_true", help="also produce a .zip to upload")
    args = ap.parse_args(argv)

    out_dir = Path(args.out) if args.out else ROOT / "dist" / "wedges_php"
    build(out_dir, args.password, args.heading, args.zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
