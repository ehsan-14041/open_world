"""
Freeze the parts of the instrument the PHP port must not re-derive.

The PHP engine reproduces the *arithmetic*. Everything that is a fixed property of the
instrument — the parsed slice, the canonical JSON blobs the reproducibility hashes are taken
over, the module hash, the shared fingerprint, the sweep, the sources — is exported here from
the Python definitions themselves, so the two implementations cannot drift on anything except
the arithmetic, which is verified separately.

    python scripts/export_php_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.cafe.baseline import DAYS_PER_MONTH, DEMO_CAFE, INTAKE_FIELDS  # noqa: E402
from event_sim.cafe.evidence import SOURCES  # noqa: E402
from event_sim.cafe.run import DEFAULT_AXES, _shared_fingerprint, _slice  # noqa: E402
from event_sim.cafe.sensitivity import SWEEP, SWEEP_LABELS  # noqa: E402
from event_sim.cafe.worlds import (  # noqa: E402
    HORIZON_DAYS,
    MODULE_ID,
    PRICE_RISE_B,
    PRICE_RISE_C,
    REFORMULATION_EFFECTIVENESS,
)
from event_sim.engine import SimulationConfig  # noqa: E402
from event_sim.freeze import module_hash  # noqa: E402

OUT = ROOT / "deploy" / "php" / "assets"


def main() -> int:
    s = _slice(None)
    cfg = SimulationConfig(turns=HORIZON_DAYS, axis_settings=dict(DEFAULT_AXES),
                           lag_setting="central", label="cafe")
    # build_simulation fills defaults for any axis the caller left unset; do the same here so
    # the canonical config blob is the one the engine actually hashes.
    settings = dict(cfg.axis_settings)
    for axis in s.axes:
        settings.setdefault(axis.id, axis.default_setting())
    cfg = SimulationConfig(turns=cfg.turns, axis_settings=settings, lag_setting=cfg.lag_setting,
                           label=cfg.label, seed=cfg.seed)

    frozen = {
        "module_id": MODULE_ID,
        "module_semantic_hash": module_hash(MODULE_ID),
        "shared_fingerprint": _shared_fingerprint(s, cfg),
        # Exact byte-strings Python would produce for the constant halves of the fingerprint
        # payload. PHP concatenates the varying halves around them; see lib/canon.php.
        "canonical": {
            "slice": json.dumps(s.to_dict(), sort_keys=True, default=str),
            "config": json.dumps(cfg.to_dict(), sort_keys=True, default=str),
        },
        "slice": {
            "variables": [
                {"id": v.id, "label": v.label, "unit": v.unit, "baseline": v.baseline,
                 "scale": v.scale, "min": v.minimum, "max": v.maximum,
                 "response": v.response, "kind": v.kind, "axis": v.axis}
                for v in s.variables
            ],
            "edges": [
                {"id": e.id, "source": e.source, "target": e.target, "polarity": e.polarity,
                 "mechanism_type": e.mechanism_type, "axis": e.axis,
                 "effect": {k: e.effect.value_for(k) for k in ("low", "central", "high")},
                 # lag_setting is fixed at "central" for this product, so resolve it once
                 "lag": e.lag.effective("central")}
                for e in s.edges
            ],
            "axes": [
                {"id": a.id, "settings": list(a.settings), "applies_to": list(a.applies_to),
                 "mapping": {k: dict(v) for k, v in a.mapping.items()},
                 "default_setting": a.default_setting()}
                for a in s.axes
            ],
            "interventions": [dict(i) for i in s.interventions],
        },
        "defaults": {
            "horizon_days": HORIZON_DAYS,
            "days_per_month": DAYS_PER_MONTH,
            "axis_settings": dict(DEFAULT_AXES),
            "reformulation_effectiveness": REFORMULATION_EFFECTIVENESS,
            "price_rise_b": PRICE_RISE_B,
            "price_rise_c": PRICE_RISE_C,
        },
        "demo_cafe": DEMO_CAFE.to_dict(),
        "sweep": SWEEP,
        "sweep_labels": SWEEP_LABELS,
        "sources": SOURCES,
        "intake_fields": INTAKE_FIELDS,
        "language": {
            "scenario_not_forecast":
                "This is a scenario comparison under stated assumptions, not a forecast.",
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    template = ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html"
    (OUT / "decision_report.html").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"module hash        {frozen['module_semantic_hash'][:16]}")
    print(f"shared fingerprint {frozen['shared_fingerprint'][:16]}")
    print(f"variables {len(frozen['slice']['variables'])}  edges {len(frozen['slice']['edges'])}"
          f"  axes {len(frozen['slice']['axes'])}  interventions {len(frozen['slice']['interventions'])}")
    for p in (OUT / "frozen.json", OUT / "decision_report.html"):
        print(f"{p.stat().st_size:>9,}  {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
