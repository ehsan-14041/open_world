"""
The PHP port must change nothing.

The port exists so a cafe owner's report can be generated on a PHP-only host. That is only
worth having if it is the same instrument: same trajectories, same metrics, same
reproducibility hashes. These tests compare the two implementations directly and fail if they
diverge at all.

The full 162-point comparison lives in scripts/verify_php_port.py — it is too slow for the
suite because the Python side records a causal trace the report never uses. What is checked
here is the engine path, the accounting, the fingerprints, and that the frozen assets shipped
to the host are not stale.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from event_sim.cafe.baseline import DEMO_CAFE
from event_sim.cafe.run import run_comparison

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"
FROZEN = PHP_ROOT / "assets" / "frozen.json"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="php CLI not on PATH")

DRIVER = """<?php
require __DIR__ . '/lib/report.php';
$frozen = json_decode(file_get_contents(__DIR__ . '/assets/frozen.json'), true);
$slice = new Slice($frozen['slice']);
$baseline = new Baseline(json_decode($argv[1], true));
$comp = run_comparison($slice, $frozen, $baseline, [], (float) $frozen['defaults']['reformulation_effectiveness']);
$out = ['ranking' => ranking($comp), 'worlds' => []];
foreach ($comp['worlds'] as $w) {
    $out['worlds'][$w['spec']['id']] = [
        'metrics' => $w['metrics'],
        'indices' => $w['indices'],
        'cash' => $w['ledger']['cash'],
        'fingerprint' => $w['fingerprint'],
    ];
}
echo json_encode($out, JSON_PRESERVE_ZERO_FRACTION);
"""

CAFES = [
    DEMO_CAFE,
    replace(DEMO_CAFE, name="Corner Bean", monthly_revenue=32000.0, daily_orders=140.0,
            monthly_cogs=11200.0, monthly_fixed_costs=20500.0, cash_on_hand=6000.0,
            supplier_increase_pct=40.0, low_margin_share_pct=30.0, is_demo=False, notes=[]),
]


def _php(baseline) -> dict:
    with tempfile.TemporaryDirectory():
        driver = PHP_ROOT / "_test_driver.php"
        driver.write_text(DRIVER, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["php", "-d", "memory_limit=512M", str(driver), json.dumps(baseline.to_dict())],
                capture_output=True, text=True, check=False,
            )
        finally:
            driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


@pytest.mark.parametrize("baseline", CAFES, ids=lambda b: b.name)
def test_php_reproduces_the_engine_trajectories_exactly(baseline):
    php = _php(baseline)
    comp = run_comparison(baseline)

    assert php["ranking"] == comp.ranking()
    for w in comp.worlds:
        got = php["worlds"][w.spec.id]
        for key, series in w.indices().items():
            assert len(got["indices"][key]) == len(series)
            for day, (a, b) in enumerate(zip(series, got["indices"][key])):
                assert a == pytest.approx(b, abs=1e-9), f"{w.spec.id} {key} day {day}"


@pytest.mark.parametrize("baseline", CAFES, ids=lambda b: b.name)
def test_php_reproduces_the_accounting_and_the_decision_metrics(baseline):
    php = _php(baseline)
    comp = run_comparison(baseline)

    for w in comp.worlds:
        got = php["worlds"][w.spec.id]
        for day, (a, b) in enumerate(zip(w.ledger.cash, got["cash"])):
            assert a == pytest.approx(b, abs=1e-6), f"{w.spec.id} cash day {day}"
        for key, value in w.metrics.items():
            other = got["metrics"][key]
            if value is None or isinstance(value, bool):
                assert value == other, key
            else:
                assert float(value) == pytest.approx(float(other), abs=1e-6), key


@pytest.mark.parametrize("baseline", CAFES, ids=lambda b: b.name)
def test_php_reproduces_the_reproducibility_hashes(baseline):
    """A fingerprint that differs would mean the two are not the same instrument."""
    php = _php(baseline)
    comp = run_comparison(baseline)
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))

    assert frozen["module_semantic_hash"] == comp.module_semantic_hash
    assert frozen["shared_fingerprint"] == comp.shared_fingerprint
    for w in comp.worlds:
        assert php["worlds"][w.spec.id]["fingerprint"] == w.fingerprint, w.spec.id


def test_frozen_assets_are_current():
    """The host gets whatever was last exported; a stale export would ship an old model."""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_php_assets.py")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    template = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text(encoding="utf-8")
    assert (PHP_ROOT / "assets" / "decision_report.html").read_text(encoding="utf-8") == template
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert frozen["demo_cafe"]["monthly_revenue"] == DEMO_CAFE.monthly_revenue
    assert len(frozen["slice"]["variables"]) == 4
    assert len(frozen["slice"]["edges"]) == 2
