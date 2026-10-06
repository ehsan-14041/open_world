"""
The PHP port must change nothing.

The port exists so an owner's report can be generated on a PHP-only host, for any of the
three wedges. That is only
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
from event_sim.wedge.compare import run_comparison as run_wedge
from event_sim.wedge.registry import WEDGES

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"
FROZEN = PHP_ROOT / "assets"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="php CLI not on PATH")

DRIVER = """<?php
require __DIR__ . '/lib/report.php';
$wedge = json_decode(file_get_contents(__DIR__ . '/assets/' . $argv[1] . '.json'), true);
$slice = new Slice($wedge['slice']);
$baseline = new Baseline(json_decode($argv[2], true), $wedge);
$comp = run_comparison($slice, $wedge, $baseline, [], (float) reset($wedge['defaults']['knobs']));
$out = ['ranking' => ranking($comp), 'worlds' => []];
foreach ($comp['worlds'] as $w) {
    $out['worlds'][$w['spec']['id']] = [
        'metrics' => $w['metrics'],
        'indices' => $w['indices'],
        'cash' => $w['ledger']['cash'],
        'fingerprint' => $w['fingerprint'],
        'trajectory_fingerprint' => $w['trajectory_fingerprint'],
    ];
}
echo json_encode($out, JSON_PRESERVE_ZERO_FRACTION);
"""

#: Every wedge's demo, plus one non-demo cafe — the PHP host must serve all three.
CASES = (
    [("cafe", DEMO_CAFE)]
    + [(wid, w.demo_factory()) for wid, w in sorted(WEDGES.items()) if wid != "cafe"]
    + [("cafe", replace(DEMO_CAFE, name="Corner Bean", monthly_revenue=32000.0, daily_orders=140.0,
                        monthly_cogs=11200.0, monthly_fixed_costs=20500.0, cash_on_hand=6000.0,
                        supplier_increase_pct=40.0, low_margin_share_pct=30.0, is_demo=False,
                        notes=[]))]
)


def _php(wedge_id: str, baseline) -> dict:
    with tempfile.TemporaryDirectory():
        driver = PHP_ROOT / "_test_driver.php"
        driver.write_text(DRIVER, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["php", "-d", "memory_limit=512M", str(driver), wedge_id,
                 json.dumps(baseline.to_dict())],
                capture_output=True, text=True, check=False,
            )
        finally:
            driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


@pytest.mark.parametrize("wedge_id,baseline", CASES, ids=lambda x: x if isinstance(x, str) else x.name)
def test_php_reproduces_the_engine_trajectories_exactly(wedge_id, baseline):
    php = _php(wedge_id, baseline)
    comp = run_wedge(WEDGES[wedge_id], baseline)

    assert php["ranking"] == comp.ranking()
    for w in comp.worlds:
        got = php["worlds"][w.spec.id]
        for key, series in w.indices().items():
            assert len(got["indices"][key]) == len(series)
            for day, (a, b) in enumerate(zip(series, got["indices"][key])):
                assert a == pytest.approx(b, abs=1e-9), f"{w.spec.id} {key} day {day}"


@pytest.mark.parametrize("wedge_id,baseline", CASES, ids=lambda x: x if isinstance(x, str) else x.name)
def test_php_reproduces_the_accounting_and_the_decision_metrics(wedge_id, baseline):
    php = _php(wedge_id, baseline)
    comp = run_wedge(WEDGES[wedge_id], baseline)

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


@pytest.mark.parametrize("wedge_id,baseline", CASES, ids=lambda x: x if isinstance(x, str) else x.name)
def test_php_reproduces_the_reproducibility_hashes(wedge_id, baseline):
    """A fingerprint that differs would mean the two are not the same instrument."""
    php = _php(wedge_id, baseline)
    comp = run_wedge(WEDGES[wedge_id], baseline)
    frozen = json.loads((FROZEN / f"{wedge_id}.json").read_text(encoding="utf-8"))

    assert frozen["module_semantic_hash"] == comp.module_semantic_hash
    assert frozen["shared_fingerprint"] == comp.shared_fingerprint
    for w in comp.worlds:
        got = php["worlds"][w.spec.id]
        assert got["fingerprint"] == w.fingerprint, w.spec.id
        # The registry-independent one has to match too, or a report generated on the host
        # could not be checked against one generated here across repository states.
        assert got["trajectory_fingerprint"] == w.trajectory_fingerprint, w.spec.id


def test_frozen_assets_are_current():
    """The host gets whatever was last exported; a stale export would ship an old model."""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_php_assets.py")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    template = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text(encoding="utf-8")
    assert (PHP_ROOT / "assets" / "decision_report.html").read_text(encoding="utf-8") == template
    for wedge_id, wedge in WEDGES.items():
        frozen = json.loads((FROZEN / f"{wedge_id}.json").read_text(encoding="utf-8"))
        assert frozen["demo"] == wedge.demo_factory().to_dict()
        assert frozen["module_id"] == wedge.module_id
        assert frozen["registry_spec"], f"{wedge_id} exported no registry spec"
        assert len(frozen["sweep"]) == len(wedge.sweep)
        assert frozen["research_settings"] == wedge.copy["research_settings"]


REGISTRY_DRIVER = """<?php
require __DIR__ . '/lib/report.php';
$wedge = json_decode(file_get_contents(__DIR__ . '/assets/' . $argv[1] . '.json'), true);
$baseline = new Baseline(json_decode($argv[2], true), $wedge);
$axes = $wedge['defaults']['axis_settings'];
echo json_encode(evidence_registry($baseline, $wedge, $axes,
    (float) reset($wedge['defaults']['knobs'])), JSON_PRESERVE_ZERO_FRACTION);
"""


def _php_registry(wedge_id: str, baseline) -> list:
    driver = PHP_ROOT / "_test_registry_driver.php"
    driver.write_text(REGISTRY_DRIVER, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["php", "-d", "memory_limit=512M", str(driver), wedge_id,
             json.dumps(baseline.to_dict())],
            capture_output=True, text=True, check=False,
        )
    finally:
        driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


@pytest.mark.parametrize("wedge_id,baseline", CASES, ids=lambda x: x if isinstance(x, str) else x.name)
def test_php_reproduces_the_evidence_registry(wedge_id, baseline):
    """
    Where every number came from has to be the same story on both hosts.

    The registry is prose as well as arithmetic, and the page now re-renders each value in the
    reader's language from the spec and the figures behind it. A host that shipped the sentence
    but not the figures would quietly fall back to English.
    """
    wedge = WEDGES[wedge_id]
    py = wedge.build_registry(baseline, axis_settings=dict(wedge.default_axes),
                              custom_elasticity=None, **wedge.knob_defaults)
    php = _php_registry(wedge_id, baseline)

    assert [a.key for a in py] == [r["key"] for r in php]
    for expected, got in zip(py, php):
        where = f"{wedge_id}.{expected.key}"
        assert got["label"] == expected.label, where
        assert got["value"] == expected.value, where
        assert got["klass"] == expected.klass, where
        assert got["ladder_status"] == expected.to_dict()["ladder_status"], where
        # Both halves of what the page re-renders from.
        assert got["value_spec"] == expected.value_spec, where
        assert set(got["value_ctx"]) == set(expected.value_ctx), f"{where}: different figures carried"
        for name, value in expected.value_ctx.items():
            other = got["value_ctx"][name]
            if isinstance(value, float):
                assert abs(other - value) < 1e-9, f"{where}.{name}: {other} != {value}"
            else:
                assert other == value, f"{where}.{name}"
