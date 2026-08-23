"""
Which assumption could change the decision?

A full factorial over the uncertain, high-impact assumptions, each varied across a
defensible range. For every combination the three worlds are re-run through the same engine
and ranked. The output is not a distribution and not a probability: it is a census of the
tested assumption space — in how many tested combinations does each world come first, and
which single assumption, when moved on its own, most often changes the answer.

That framing is deliberate. "World B wins in 61% of tested combinations" is a statement
about the grid we chose, and it is reported as such. It is still far more useful to an owner
than a single central estimate presented as if it were precise.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from typing import Any

from event_sim.cafe.baseline import CafeBaseline
from event_sim.cafe.run import DEFAULT_AXES, Comparison, run_comparison

#: The assumptions swept, and the values each takes. Centre of each list is the default.
SWEEP: dict[str, list[Any]] = {
    "price_sensitivity": ["low", "central", "high"],
    "cogs_pass_through": ["low", "central"],
    "supplier_increase_pct": [20.0, 30.0, 40.0],
    "reformulation_effectiveness": [0.15, 0.30, 0.45],
    "demand_adjustment_speed": ["slow", "central", "fast"],
}

#: Customer-facing names for the swept assumptions.
SWEEP_LABELS: dict[str, str] = {
    "price_sensitivity": "How price-sensitive customers are",
    "cogs_pass_through": "How much of the supplier increase reaches your costs",
    "supplier_increase_pct": "How large the supplier increase actually is",
    "reformulation_effectiveness": "How much trimming the menu really saves",
    "demand_adjustment_speed": "How quickly customers react",
}

DECISION_METRIC = "cash_day_90"


@dataclass
class SweepPoint:
    settings: dict[str, Any]
    ranking: list[str]
    metric: dict[str, float]


@dataclass
class SensitivityResult:
    baseline: CafeBaseline
    metric: str
    points: list[SweepPoint] = field(default_factory=list)
    central_ranking: list[str] = field(default_factory=list)

    # --- summaries -------------------------------------------------------------------------

    @property
    def n(self) -> int:
        return len(self.points)

    def win_counts(self) -> dict[str, int]:
        out = {"A": 0, "B": 0, "C": 0}
        for p in self.points:
            out[p.ranking[0]] += 1
        return out

    def win_shares(self) -> dict[str, float]:
        return {k: v / self.n for k, v in self.win_counts().items()} if self.n else {}

    def ranking_stable(self) -> bool:
        return all(p.ranking == self.central_ranking for p in self.points)

    def top_stable(self) -> bool:
        return all(p.ranking[0] == self.central_ranking[0] for p in self.points)

    def one_at_a_time(self) -> list[dict[str, Any]]:
        """For each assumption: move it alone off centre, holding the others at centre.
        Reports whether the top choice changes and the spread of the decision metric."""
        centre = {k: vals[len(vals) // 2] for k, vals in SWEEP.items()}
        centre_point = self._find(centre)
        rows: list[dict[str, Any]] = []
        for key, values in SWEEP.items():
            tops: list[str] = []
            spreads: list[float] = []
            for v in values:
                settings = {**centre, key: v}
                p = self._find(settings)
                if p is None:
                    continue
                tops.append(p.ranking[0])
                spreads.append(p.metric["B"] - p.metric["C"])
            flips = len(set(tops)) > 1
            rows.append({
                "assumption": key,
                "label": SWEEP_LABELS[key],
                "values": values,
                "top_choice_by_value": tops,
                "changes_top_choice": flips,
                "b_minus_c_range": (min(spreads), max(spreads)) if spreads else (0.0, 0.0),
                "influence": (max(spreads) - min(spreads)) if spreads else 0.0,
            })
        rows.sort(key=lambda r: (-int(r["changes_top_choice"]), -r["influence"]))
        return rows

    def flip_attribution(self) -> dict[str, int]:
        """Across the whole grid: for each assumption, how many points differ from the
        central top choice AND share every other setting with a point that agrees with it.
        A count of how often that assumption alone is the deciding one."""
        centre_top = self.central_ranking[0]
        index = {self._key(p.settings): p for p in self.points}
        counts = {k: 0 for k in SWEEP}
        for p in self.points:
            if p.ranking[0] == centre_top:
                continue
            for key in SWEEP:
                for alt in SWEEP[key]:
                    if alt == p.settings[key]:
                        continue
                    q = index.get(self._key({**p.settings, key: alt}))
                    if q is not None and q.ranking[0] == centre_top:
                        counts[key] += 1
                        break
        return counts

    def verdict(self) -> str:
        """One sentence a cafe owner can act on. Only says what the grid supports."""
        shares = self.win_shares()
        best = max(shares, key=shares.get)
        best_label = {"A": "Doing nothing", "B": "Raising prices 10%", "C": "A 5% rise plus trimming the menu"}[best]
        if self.top_stable():
            return f"{best_label} comes out ahead in every one of the {self.n} assumption combinations tested."
        oat = self.one_at_a_time()
        deciders = [r["label"].lower() for r in oat if r["changes_top_choice"]]
        share_txt = f"{100 * shares[best]:.0f}% of the {self.n} combinations tested"
        if deciders:
            return (
                f"{best_label} comes out ahead in {share_txt}. The choice depends mainly on "
                f"{deciders[0]}" + (f" and {deciders[1]}" if len(deciders) > 1 else "") + "."
            )
        return f"{best_label} comes out ahead in {share_txt}."

    # --- internals ---------------------------------------------------------------------------

    @staticmethod
    def _key(settings: dict[str, Any]) -> tuple:
        return tuple(settings[k] for k in SWEEP)

    def _find(self, settings: dict[str, Any]) -> SweepPoint | None:
        want = self._key(settings)
        for p in self.points:
            if self._key(p.settings) == want:
                return p
        return None


def run_sensitivity(baseline: CafeBaseline, *, metric: str = DECISION_METRIC) -> SensitivityResult:
    result = SensitivityResult(baseline=baseline, metric=metric)
    keys = list(SWEEP)
    for combo in itertools.product(*(SWEEP[k] for k in keys)):
        settings = dict(zip(keys, combo))
        b = replace(baseline, supplier_increase_pct=float(settings["supplier_increase_pct"]))
        axes = {
            **DEFAULT_AXES,
            "price_sensitivity": settings["price_sensitivity"],
            "cogs_pass_through": settings["cogs_pass_through"],
            "demand_adjustment_speed": settings["demand_adjustment_speed"],
        }
        comp: Comparison = run_comparison(
            b, axis_settings=axes, reformulation_effectiveness=float(settings["reformulation_effectiveness"])
        )
        result.points.append(
            SweepPoint(
                settings=settings,
                ranking=comp.ranking(metric),
                metric={w.spec.id: float(w.metrics[metric]) for w in comp.worlds},
            )
        )
    centre = {k: vals[len(vals) // 2] for k, vals in SWEEP.items()}
    cp = result._find(centre)
    result.central_ranking = cp.ranking if cp else result.points[0].ranking
    return result
