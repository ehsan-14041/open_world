"""
The report bundle: everything the page needs, in one JSON payload.

Shared by every wedge. The page is a static file plus this payload, which is why a report can
be emailed, archived or opened offline and still be the same report.

Two structural choices carry the product's honesty:

  * `grid` holds the engine's index trajectories for every swept combination. Those indices do
    not depend on the owner's money at all — only on the shock, the axis settings and the
    intervention sizes — so the page can apply any owner's figures to them exactly, and the
    sensitivity count shown is recomputed for THAT business rather than inherited from a demo.

  * `reproducibility` records the module hash, the shared fingerprint and a per-world engine
    fingerprint. Two worlds that differ in anything other than their intervention would show
    different shared fingerprints, so the comparison's central claim is checkable rather than
    asserted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from event_sim.wedge.compare import Comparison, run_comparison, wedge_slice
from event_sim.wedge.evidence import class_counts
from event_sim.wedge.i18n import bundle_for
from event_sim.wedge.sensitivity import SensitivityResult, run_sensitivity
from event_sim.wedge.spec import WedgeSpec

TEMPLATE = Path(__file__).resolve().parent.parent / "cafe" / "templates" / "decision_report.html"


def summarise(wedge: WedgeSpec, baseline: Any) -> dict[str, Any]:
    """
    The baseline block, from the wedge's own declaration of what is worth showing.

    Declarative because the PHP host renders the same block; a summary written twice would be
    a summary that eventually disagreed with itself.
    """
    derived = {
        "average_ticket": lambda b: b.average_ticket if hasattr(b, "average_ticket") else b.average_order_value,
        "cost_pct": lambda b: getattr(b, "cogs_pct", None) or b.variable_cost_pct,
        "gross_margin_pct": lambda b: b.gross_margin_pct,
        "monthly_net": lambda b: b.monthly_net,
        "net_margin_pct": lambda b: b.net_margin_pct,
        "capacity_per_day": lambda b: b.capacity_per_day,
    }
    fields = wedge.copy["fields"]
    raw = baseline.to_dict()
    out: dict[str, Any] = {"name": baseline.name, "is_demo": baseline.is_demo}
    for name, source, dp in wedge.copy["summary_fields"]:
        if source in derived:
            value = derived[source](baseline)
        elif source in fields:
            value = raw[fields[source]]
        else:
            value = raw[source]
        out[name] = round(float(value), dp) if dp is not None else value
    return out


def _round_series(values: Any, nd: int = 3) -> list[float]:
    return [round(float(x), nd) for x in values]


def frozen_slice(wedge: WedgeSpec) -> dict[str, Any]:
    """
    The causal slice as plain data: variables, edges, the assumption axes and the two levers.

    It is the same block the PHP host is shipped, and it travels inside every report so the
    browser can run an option nobody precomputed. The page only lets it do that after it has
    rebuilt every precomputed case from this block and matched the originals.
    """
    s = wedge_slice(wedge, None)
    return {
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
    }


def wedge_roles(wedge: WedgeSpec) -> dict[str, Any]:
    """Which slice variable is demand, price and unit cost — the three the ledger reads."""
    return {
        "demand_var": wedge.demand_var,
        "price_var": wedge.price_var,
        "unit_cost_var": wedge.unit_cost_var,
        "index_vars": list(wedge.index_vars),
    }


def _grid(wedge: WedgeSpec, baseline: Any, sens: SensitivityResult) -> list[dict[str, Any]]:
    """Engine trajectories for every swept combination, keyed by what the page can select."""
    out: list[dict[str, Any]] = []
    axis_names = set(wedge.default_axes)
    for p in sens.points:
        s = p.settings
        axes = {k: v for k, v in s.items() if k in axis_names}
        knobs = {k: float(v) for k, v in s.items() if k in wedge.knob_defaults}
        overrides = {k: float(v) for k, v in s.items()
                     if k not in axis_names and k not in wedge.knob_defaults}
        b = baseline.replace(**overrides) if overrides else baseline
        comp = run_comparison(wedge, b, axis_settings=axes, **knobs)
        out.append({
            "key": wedge.copy["grid_key"](b, s, comp),
            "worlds": {
                w.spec.id: {
                    "demand": _round_series(w.sim.series(wedge.demand_var)),
                    "cogs": _round_series(w.sim.series(wedge.unit_cost_var)),
                    "price": _round_series(w.sim.series(wedge.price_var), 2),
                }
                for w in comp.worlds
            },
        })
    return out


def build_bundle(
    wedge: WedgeSpec,
    baseline: Any,
    *,
    comparison: Comparison | None = None,
    sensitivity: SensitivityResult | None = None,
    include_grid: bool = True,
) -> dict[str, Any]:
    comp = comparison or run_comparison(wedge, baseline)
    sens = sensitivity or run_sensitivity(wedge, baseline)
    reg = wedge.build_registry(baseline, axis_settings=comp.axis_settings,
                              custom_elasticity=comp.custom_elasticity, **comp.knobs)
    oat = sens.one_at_a_time()

    bundle: dict[str, Any] = {
        "wedge": {
            "id": wedge.id,
            "business": wedge.business,
            "question": wedge.question,
            "module_id": wedge.module_id,
        },
        # Structure only — which field plays which role, which grid key, which settings a
        # study backs. Every customer-facing string lives in `i18n`, in every language.
        "copy": {k: v for k, v in wedge.copy.items() if not callable(v)},
        "i18n": bundle_for(wedge.id),
        "generated_for": baseline.name,
        "is_demo": baseline.is_demo,
        "baseline": summarise(wedge, baseline),
        "baseline_raw": baseline.to_dict(),
        "intake_fields": wedge.intake_fields,
        # The model itself, so an option the owner makes up can be run in their browser.
        "slice": frozen_slice(wedge),
        "roles": wedge_roles(wedge),
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
                    **({"utilisation_pct": [round(x, 2) for x in w.ledger.utilisation_pct],
                        "turned_away": [round(x, 3) for x in w.ledger.turned_away]}
                       if w.ledger.capacity_limited else {}),
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
            "dominated_worlds": sens.dominated_worlds(),
            "verdict": sens.verdict(),
            "one_at_a_time": oat,
            "flip_attribution": sens.flip_attribution(),
            "sweep": wedge.sweep,
            "sweep_labels": wedge.sweep_labels,
            "points": [{"settings": p.settings, "ranking": p.ranking, "metric": p.metric}
                       for p in sens.points],
        },
        "assumptions": [a.to_dict() for a in reg],
        "assumption_class_counts": class_counts(reg),
        "sources": wedge.sources,
        "reproducibility": comp.reproducibility_record(),
        "language": {
            "scenario_not_forecast":
                "This is a scenario comparison under stated assumptions, not a forecast.",
        },
    }
    if include_grid:
        bundle["grid"] = _grid(wedge, baseline, sens)
    return bundle


def render_html(bundle: dict[str, Any]) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(bundle, separators=(",", ":")).replace("</", "<\\/")
    return template.replace("__DATA__", payload)


def write_report(wedge: WedgeSpec, baseline: Any, out_dir: Path, *, include_grid: bool = True,
                 custom_elasticity: float | None = None, **knobs: float) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    kw = {k: v for k, v in knobs.items() if v is not None}
    comp = (run_comparison(wedge, baseline, custom_elasticity=custom_elasticity, **kw)
            if (kw or custom_elasticity is not None) else None)
    bundle = build_bundle(wedge, baseline, comparison=comp, include_grid=include_grid)
    stem = f"{wedge.id}_decision_report"
    paths = {"json": out_dir / f"{stem}.json", "html": out_dir / f"{stem}.html"}
    paths["json"].write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    paths["html"].write_text(render_html(bundle), encoding="utf-8")
    return paths
