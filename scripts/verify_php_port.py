"""
Check that the PHP port reproduces the Python report exactly.

The PHP port only earns its place if it changes nothing. This generates a bundle both ways for
the same cafe and compares them field by field — every metric, every ledger day, every one of
the 162 grid points, and the reproducibility hashes.

    python scripts/verify_php_port.py                       # the demo cafe
    python scripts/verify_php_port.py --inputs my_cafe.json

Exit code 0 means the two agree exactly. Requires the `php` CLI on PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.wedge.registry import WEDGES  # noqa: E402
from event_sim.wedge.report import build_bundle  # noqa: E402

PHP_DRIVER = """<?php
require __DIR__ . '/lib/report.php';
$wedge = json_decode(file_get_contents(__DIR__ . '/assets/' . $argv[1] . '.json'), true);
$baseline = new Baseline(json_decode($argv[2], true), $wedge);
$bundle = build_bundle(new Slice($wedge['slice']), $wedge, $baseline, true);
file_put_contents($argv[3], json_encode($bundle, JSON_PRESERVE_ZERO_FRACTION));
"""


#: Bundle keys only the PHP host can fill in.
HOST_ONLY = ("contrib",)


def compare(py: object, php: object) -> tuple[list[str], float]:
    """Field-by-field diff. Returns (differences, worst absolute numeric difference)."""
    diffs: list[str] = []
    worst = 0.0

    def walk(a: object, b: object, path: str) -> None:
        nonlocal worst
        if isinstance(a, dict):
            if not isinstance(b, dict) or set(a) != set(b):
                missing = sorted(set(a) ^ set(b)) if isinstance(b, dict) else ["<not a dict>"]
                diffs.append(f"{path}: keys differ ({missing})")
                return
            for k in a:
                walk(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                diffs.append(f"{path}: length {len(a)} vs {len(b) if isinstance(b, list) else '?'}")
                return
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        elif a is None or isinstance(a, (bool, str)):
            if a != b:
                diffs.append(f"{path}: {a!r} vs {b!r}")
        else:
            if not isinstance(b, (int, float)) or isinstance(b, bool):
                diffs.append(f"{path}: {a!r} vs {b!r}")
                return
            d = abs(float(a) - float(b))
            worst = max(worst, d)
            if d > 0:
                diffs.append(f"{path}: {a!r} vs {b!r}")

    walk(py, php, "")
    return diffs, worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wedge", nargs="?", choices=sorted(WEDGES), help="which wedge (default: all)")
    ap.add_argument("--inputs", help="JSON file with the intake fields (default: the demo business)")
    args = ap.parse_args(argv)

    if shutil.which("php") is None:
        print("php is not on PATH; cannot verify.")
        return 2

    wedge_ids = [args.wedge] if args.wedge else sorted(WEDGES)
    if args.inputs and len(wedge_ids) != 1:
        ap.error("--inputs needs a single wedge")

    php_root = ROOT / "deploy" / "php"
    worst_overall = 0.0
    failures = 0

    for wedge_id in wedge_ids:
        wedge = WEDGES[wedge_id]
        if args.inputs:
            raw = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
            raw.setdefault("is_demo", False)
            baseline = wedge.baseline_from_dict(raw)
        else:
            baseline = wedge.demo_factory()

        print("")
        print(f"{wedge_id}: {baseline.name}")
        print("  running the PHP port ...")
        with tempfile.TemporaryDirectory() as tmp:
            driver = php_root / "_verify_driver.php"
            out = Path(tmp) / "php_bundle.json"
            driver.write_text(PHP_DRIVER, encoding="utf-8")
            try:
                proc = subprocess.run(
                    ["php", "-d", "memory_limit=512M", str(driver), wedge_id,
                     json.dumps(baseline.to_dict()), str(out)],
                    capture_output=True, text=True,
                )
            finally:
                driver.unlink(missing_ok=True)
            if proc.returncode != 0:
                print(proc.stdout, proc.stderr)
                failures += 1
                continue
            php_bundle = json.loads(out.read_text(encoding="utf-8"))

        print("  running the Python pipeline (a few minutes) ...")
        # Round-trip through JSON: build_bundle returns tuples where the written report holds
        # lists, and comparing the in-memory object would report that as a difference.
        py_bundle = json.loads(json.dumps(build_bundle(wedge, baseline)))

        # Facts about the host rather than the instrument: whether this host accepts a shared
        # measurement. The Python pipeline has no host to ask, so it carries no such key.
        for key in HOST_ONLY:
            php_bundle.pop(key, None)
        diffs, worst = compare(py_bundle, php_bundle)
        worst_overall = max(worst_overall, worst)
        fps_match = all(a["engine_fingerprint"] == b["engine_fingerprint"]
                        for a, b in zip(py_bundle["reproducibility"]["worlds"],
                                        php_bundle["reproducibility"]["worlds"]))
        print(f"  grid points compared      {len(py_bundle.get('grid', []))}")
        print(f"  worst numeric difference  {worst}")
        print(f"  engine fingerprints       {'match' if fps_match else 'DIFFER'}")
        if diffs:
            failures += 1
            print(f"  {len(diffs)} differences:")
            for d in diffs[:12]:
                print("    ", d)
        else:
            print("  identical")

    print("")
    print(f"worst numeric difference across all wedges: {worst_overall}")
    if failures:
        print(f"{failures} wedge(s) differ.")
        return 1
    print("Identical. The PHP port changes nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
