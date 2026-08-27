"""
Freeze the parts of each wedge the PHP port must not re-derive.

The PHP engine reproduces the *arithmetic*. Everything that is a fixed property of an
instrument — the parsed slice, the canonical JSON blobs the reproducibility hashes are taken
over, the module hash, the shared fingerprint, the sweep, the sources, the page's wording and
the assumption registry — is exported here from the Python definitions themselves, so the two
implementations cannot drift on anything except the arithmetic, which is verified separately.

The registry in particular is exported as a SPEC rather than as rendered text: both languages
render the same spec, so the prose exists once.

    python scripts/export_php_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.engine import SimulationConfig  # noqa: E402
from event_sim.freeze import module_hash  # noqa: E402
from event_sim.wedge.accounting import DAYS_PER_MONTH  # noqa: E402
from event_sim.wedge.compare import _trajectory_slice, shared_fingerprint, wedge_slice  # noqa: E402
from event_sim.wedge.i18n import bundle_for, chooser_bundle  # noqa: E402
from event_sim.wedge.registry import CHOOSER, WEDGES  # noqa: E402
from event_sim.wedge.spec import WedgeSpec  # noqa: E402

OUT = ROOT / "deploy" / "php" / "assets"

#: Per-wedge shapes the PHP side needs in order to build the three worlds from data. The event
#: always lands on an exogenous driver, never on a variable an edge feeds — see the note in the
#: salon module about what happens otherwise.
WORLD_SHAPES = {
    "cafe": {
        "event": {"id": "supplier_cost_increase", "target": "input_cost",
                  "magnitude_field": "supplier_increase_pct",
                  "label": "Supplier prices +{shock}%",
                  "description": "Ingredient / input prices rise and stay at the new level for 90 days."},
        "reduction": {"share_field": "low_margin_share_pct", "knob": "reformulation_effectiveness"},
        "levers": {"price": "raise_prices", "reduce": "reformulate_menu"},
    },
    "shop": {
        "event": {"id": "supplier_cost_increase", "target": "supplier_cost",
                  "magnitude_field": "supplier_increase_pct",
                  "label": "Supplier prices +{shock}%",
                  "description": "Wholesale / supplier prices rise and stay at the new level for 90 days."},
        "reduction": {"share_field": "low_margin_share_pct", "knob": "trim_effectiveness"},
        "levers": {"price": "raise_prices", "reduce": "trim_low_margin_range"},
    },
    "salon": {
        "event": {"id": "demand_increase", "target": "market_demand",
                  "magnitude_field": "demand_growth_pct",
                  "label": "Appointments wanted +{shock}%",
                  "description": "Demand for appointments rises and stays at the new level for 90 days."},
        "reduction": {"share_field": "low_margin_share_pct", "knob": "mix_effectiveness"},
        "levers": {"price": "raise_prices", "reduce": "shift_service_mix"},
    },
}


def freeze(wedge: WedgeSpec) -> dict:
    s = wedge_slice(wedge, None)
    settings = dict(wedge.default_axes)
    for axis in s.axes:
        settings.setdefault(axis.id, axis.default_setting())
    cfg = SimulationConfig(turns=wedge.horizon_days, axis_settings=settings,
                           lag_setting="central", label=wedge.id)

    module = json.loads((ROOT / "world_models" / "small_business" / f"{wedge.module_id}.json")
                        .read_text(encoding="utf-8"))
    registry_mod = __import__(f"event_sim.{wedge.id}.evidence", fromlist=["REGISTRY_SPEC"])
    worlds_mod = __import__(f"event_sim.{wedge.id}.worlds", fromlist=["PRICE_RISE_B"])

    return {
        "wedge": {"id": wedge.id, "business": wedge.business, "question": wedge.question,
                  "module_id": wedge.module_id},
        "copy": {k: v for k, v in wedge.copy.items() if not callable(v)},
        # Every language travels with the instrument, so the host never translates anything at
        # request time and a language switch cannot reach the arithmetic.
        "i18n": bundle_for(wedge.id),
        "module_id": wedge.module_id,
        "module_semantic_hash": module_hash(wedge.module_id),
        "shared_fingerprint": shared_fingerprint(s, cfg),
        # Exact byte-strings Python would produce for the constant halves of the fingerprint
        # payload. PHP concatenates the varying halves around them; see lib/canon.php.
        "canonical": {
            "slice": json.dumps(s.to_dict(), sort_keys=True, default=str),
            # The registry-independent half, for the trajectory fingerprint.
            "trajectory_slice": json.dumps(_trajectory_slice(s), sort_keys=True, default=str),
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
        "roles": {
            "demand_var": wedge.demand_var,
            "price_var": wedge.price_var,
            "unit_cost_var": wedge.unit_cost_var,
            "index_vars": list(wedge.index_vars),
        },
        "defaults": {
            "horizon_days": wedge.horizon_days,
            "days_per_month": DAYS_PER_MONTH,
            "axis_settings": dict(wedge.default_axes),
            "knobs": dict(wedge.knob_defaults),
            "price_rise_b": worlds_mod.PRICE_RISE_B,
            "price_rise_c": worlds_mod.PRICE_RISE_C,
        },
        "worlds": {
            **WORLD_SHAPES[wedge.id],
            "options": [
                {"id": w.id, "label": w.label, "headline": w.headline,
                 "price_rise_pct": w.price_rise_pct,
                 "uses_reduction": w.cogs_reduction_points > 0 or w.id == "C"}
                for w in wedge.build_worlds(s, wedge.demo_factory(), **wedge.knob_defaults)
            ],
        },
        "capacity": ({"units_field": wedge.copy["fields"]["units_per_day"],
                      "utilisation_field": wedge.copy["fields"]["utilisation"]}
                     if wedge.capacity_per_day else None),
        "registry_spec": registry_mod.REGISTRY_SPEC,
        "research_settings": registry_mod.RESEARCH_SETTINGS,
        "sweep": wedge.sweep,
        "sweep_labels": wedge.sweep_labels,
        "sources": wedge.sources,
        "intake_fields": wedge.intake_fields,
        "demo": wedge.demo_factory().to_dict(),
        "language": {
            "scenario_not_forecast":
                "This is a scenario comparison under stated assumptions, not a forecast.",
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "wedges.json").write_text(
        json.dumps({"chooser": CHOOSER, "i18n": chooser_bundle()}, indent=1, ensure_ascii=False),
        encoding="utf-8")

    for wedge_id, wedge in WEDGES.items():
        data = freeze(wedge)
        path = OUT / f"{wedge_id}.json"
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{wedge_id:6} module {data['module_semantic_hash'][:12]}  "
              f"shared {data['shared_fingerprint'][:12]}  "
              f"{len(data['registry_spec'])} registry rows  {path.stat().st_size:>8,} bytes")

    template = ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html"
    (OUT / "decision_report.html").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    chooser = ROOT / "event_sim" / "wedge" / "templates" / "chooser.html"
    (OUT / "chooser.html").write_text(chooser.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{'page':6} {(OUT / 'decision_report.html').stat().st_size:>8,} bytes template, "
          f"{(OUT / 'chooser.html').stat().st_size:,} bytes chooser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
