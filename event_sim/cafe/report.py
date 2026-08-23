"""
Build the report bundle and render the customer-facing HTML.

The bundle is one JSON object holding everything the page needs and everything a reviewer
needs to reproduce it: the baseline, the three worlds' engine trajectories, the decision
metrics, the sensitivity census, the assumption registry with sources, and the
reproducibility record with module hash and engine fingerprints.

The HTML is self-contained. Its JavaScript never invents a number: it reads engine index
trajectories from the embedded grid and applies the same accounting identities as
`accounting.py`. The central case computed in Python is embedded alongside, and the page
checks its own arithmetic against it on load — if they disagree the page says so rather
than showing a number.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from event_sim.cafe.baseline import INTAKE_FIELDS, CafeBaseline
from event_sim.cafe.evidence import SOURCES, class_counts, registry
from event_sim.cafe.run import Comparison, run_comparison
from event_sim.cafe.sensitivity import SWEEP, SWEEP_LABELS, SensitivityResult, run_sensitivity
from event_sim.cafe.worlds import cogs_reduction_points

TEMPLATE = Path(__file__).resolve().parent / "templates" / "decision_report.html"


def _series(w: Any, key: str, nd: int = 3) -> list[float]:
    return [round(float(x), nd) for x in w.sim.series(key)]


def _grid(baseline: CafeBaseline, sens: SensitivityResult) -> list[dict[str, Any]]:
    """Engine trajectories for every swept combination, keyed by what the page can select.

    Index trajectories do not depend on the money inputs at all — only on the supplier
    increase, the axis settings and the COGS reduction points — so the page can apply any
    owner's money inputs to them exactly. The reduction is keyed in points, and the page
    snaps the owner's low-margin share to the nearest tested value and says so.
    """
    out: list[dict[str, Any]] = []
    for p in sens.points:
        s = p.settings
        b = replace(baseline, supplier_increase_pct=float(s["supplier_increase_pct"]))
        comp = run_comparison(
            b,
            axis_settings={
                "price_sensitivity": s["price_sensitivity"],
                "cogs_pass_through": s["cogs_pass_through"],
                "demand_adjustment_speed": s["demand_adjustment_speed"],
            },
            reformulation_effectiveness=float(s["reformulation_effectiveness"]),
        )
        out.append({
            "key": {
                "price_sensitivity": s["price_sensitivity"],
                "cogs_pass_through": s["cogs_pass_through"],
                "supplier_increase_pct": float(s["supplier_increase_pct"]),
                "reduction_points": cogs_reduction_points(b, float(s["reformulation_effectiveness"])),
                "demand_adjustment_speed": s["demand_adjustment_speed"],
            },
            "worlds": {
                w.spec.id: {"demand": _series(w, "demand"), "cogs": _series(w, "cogs_per_order"),
                            "price": _series(w, "menu_price", 2)}
                for w in comp.worlds
            },
        })
    return out


def build_bundle(baseline: CafeBaseline, *, comparison: Comparison | None = None,
                 sensitivity: SensitivityResult | None = None, include_grid: bool = True) -> dict[str, Any]:
    comp = comparison or run_comparison(baseline)
    sens = sensitivity or run_sensitivity(baseline)
    reg = registry(baseline, axis_settings=comp.axis_settings,
                   reformulation_effectiveness=comp.reformulation_effectiveness,
                   custom_elasticity=comp.custom_elasticity)
    oat = sens.one_at_a_time()
    bundle: dict[str, Any] = {
        "generated_for": baseline.name,
        "is_demo": baseline.is_demo,
        "baseline": baseline.summary(),
        "baseline_raw": baseline.to_dict(),
        "intake_fields": INTAKE_FIELDS,
        "worlds": [
            {
                "id": w.spec.id, "label": w.spec.label, "headline": w.spec.headline,
                "price_rise_pct": w.spec.price_rise_pct,
                "cogs_reduction_points": w.spec.cogs_reduction_points,
                "metrics": {k: (None if v is None else (round(v, 4) if isinstance(v, float) else v))
                            for k, v in w.metrics.items()},
                "ledger": {
                    "cash": [round(x, 2) for x in w.ledger.cash],
                    "gross_margin_pct": [round(x, 3) for x in w.ledger.gross_margin_pct],
                    "orders": [round(x, 2) for x in w.ledger.orders],
                    "revenue": [round(x, 2) for x in w.ledger.revenue],
                },
                "indices": {k: [round(x, 3) for x in v] for k, v in w.indices().items()},
            }
            for w in comp.worlds
        ],
        "central_ranking": comp.ranking(),
        "net_benefit_vs_a": {k: round(v, 2) for k, v in comp.net_benefit_vs_a().items()},
        "sensitivity": {
            "metric": sens.metric,
            "n": sens.n,
            "win_counts": sens.win_counts(),
            "win_shares": {k: round(v, 4) for k, v in sens.win_shares().items()},
            "top_stable": sens.top_stable(),
            "ranking_stable": sens.ranking_stable(),
            "verdict": sens.verdict(),
            "one_at_a_time": oat,
            "flip_attribution": sens.flip_attribution(),
            "sweep": SWEEP,
            "sweep_labels": SWEEP_LABELS,
            "points": [{"settings": p.settings, "ranking": p.ranking, "metric": p.metric} for p in sens.points],
        },
        "assumptions": [a.to_dict() for a in reg],
        "assumption_class_counts": class_counts(reg),
        "sources": SOURCES,
        "reproducibility": comp.reproducibility_record(),
        "language": {
            "scenario_not_forecast": "This is a scenario comparison under stated assumptions, not a forecast.",
        },
    }
    if include_grid:
        bundle["grid"] = _grid(baseline, sens)
    return bundle


def render_html(bundle: dict[str, Any]) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(bundle, separators=(",", ":")).replace("</", "<\\/")
    return template.replace("__DATA__", payload)


def write_report(baseline: CafeBaseline, out_dir: Path, *, include_grid: bool = True,
                 custom_elasticity: float | None = None,
                 reformulation_effectiveness: float | None = None) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    kw: dict[str, Any] = {}
    if custom_elasticity is not None:
        kw["custom_elasticity"] = custom_elasticity
    if reformulation_effectiveness is not None:
        kw["reformulation_effectiveness"] = reformulation_effectiveness
    comp = run_comparison(baseline, **kw) if kw else None
    bundle = build_bundle(baseline, comparison=comp, include_grid=include_grid)
    stem = "cafe_decision_report"
    paths = {
        "json": out_dir / f"{stem}.json",
        "html": out_dir / f"{stem}.html",
    }
    paths["json"].write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    paths["html"].write_text(render_html(bundle), encoding="utf-8")
    return paths
