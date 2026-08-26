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
import datetime
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "php"

#: Kept in step with lib/compat.php.
PHP_FLOOR = "7.1"


def build_stamp() -> dict[str, str]:
    """
    What this build is, in a form that survives a download.

    A dirty tree is marked, because a zip built from uncommitted changes cannot be traced back
    to anything and should not look as though it can.
    """
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=str(ROOT),
                              capture_output=True, text=True).stdout.strip()

    commit = git("rev-parse", "--short", "HEAD") or "nogit"
    dirty = bool(git("status", "--porcelain"))
    now = datetime.datetime.now()
    version = now.strftime("%Y%m%d-%H%M") + "-" + commit + ("-dirty" if dirty else "")
    return {"version": version, "commit": commit, "dirty": dirty,
            "built": now.strftime("%Y-%m-%d %H:%M")}


def build(out_dir: Path, password: str | None, heading: str | None, make_zip: bool) -> dict[str, Path]:
    # Refresh the frozen instruments so a bundle can never ship a stale model or template.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_php_assets.py")],
                   check=True, capture_output=True)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(TEMPLATE, out_dir)

    # Runtime state must never travel in a bundle: settings.json can hold an API key, the cache
    # can hold a real business's figures, and a translation belongs to the install that made it.
    for pattern in ("data/cache/*.gz", "data/settings.json", "data/llm_usage.json",
                    "data/i18n/*.json", "config.php"):
        for leaked in out_dir.glob(pattern):
            leaked.unlink()

    # A plain-text stamp, so "did my upload actually land?" is answerable by opening a URL.
    # Static on purpose: when PHP cannot parse the app, nothing dynamic can answer that.
    stamp = build_stamp()
    lines = [
        "version " + stamp["version"],
        "build   " + stamp["built"],
        "commit  " + stamp["commit"] + (" (uncommitted changes)" if stamp["dirty"] else ""),
        "php     needs " + PHP_FLOOR + " or newer",
        "wedges  cafe, shop, salon",
        "",
        "The zip this came from is named after `version` above. If they disagree, or if the",
        "build date is older than your upload, the files on the server were not replaced.",
        "",
    ]
    (out_dir / "VERSION.txt").write_text("\n".join(lines), encoding="utf-8")

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
        # The filename carries the version. Successive downloads that all share one name are
        # how the wrong build ends up on a server, which is not a hypothetical.
        archive = out_dir.parent / (out_dir.name + "_" + stamp["version"] + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(out_dir.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(out_dir))
        written["zip"] = archive

    total = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"version {stamp['version']}")
    print(f"bundle  {total:,} bytes   php {PHP_FLOOR}+")
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
