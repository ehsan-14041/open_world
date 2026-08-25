"""
Sensitivity as a census, never as a probability.

Every combination on a finite, explicitly listed grid is run. The result is a COUNT of cases —
"B ranked first in 130 of the 162 combinations tested" — and it must never be rendered as a
chance, a likelihood or a confidence. Nothing here weights one combination as more plausible
than another, so nothing here licenses that reading.

What the census is genuinely good for is locating the hinge: which single assumption, moved on
its own, changes which option ranks first. That is the sentence an owner can act on.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from event_sim.wedge.compare import Comparison, run_comparison
from event_sim.wedge.spec import WedgeSpec

DECISION_METRIC = "cash_day_90"


@dataclass
class SweepPoint:
    settings: dict[str, Any]
    ranking: list[str]
    metric: dict[str, float]


@dataclass
class SensitivityResult:
    wedge: WedgeSpec
    baseline: Any
    metric: str = DECISION_METRIC
    points: list[SweepPoint] = field(default_factory=list)
    central_ranking: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.points)

    @property
    def sweep(self) -> dict[str, list[Any]]:
        return self.wedge.sweep

    def win_counts(self) -> dict[str, int]:
        out = {wid: 0 for wid in self.wedge.world_ids()}
        for p in self.points:
            out[p.ranking[0]] += 1
        return out

    def win_shares(self) -> dict[str, float]:
        return {k: v / self.n for k, v in self.win_counts().items()} if self.n else {}

    def ranking_stable(self) -> bool:
        return all(p.ranking == self.central_ranking for p in self.points)

    def top_stable(self) -> bool:
        return all(p.ranking[0] == self.central_ranking[0] for p in self.points)

    def centre(self) -> dict[str, Any]:
        return {k: vals[len(vals) // 2] for k, vals in self.sweep.items()}

    def one_at_a_time(self) -> list[dict[str, Any]]:
        """For each assumption: move it alone off centre, holding the others at centre.
        Reports whether the top choice changes and the spread of the decision metric."""
        centre = self.centre()
        rows: list[dict[str, Any]] = []
        for key, values in self.sweep.items():
            tops: list[str] = []
            spreads: list[float] = []
            for v in values:
                p = self._find({**centre, key: v})
                if p is None:
                    continue
                tops.append(p.ranking[0])
                spreads.append(p.metric["B"] - p.metric["C"])
            rows.append({
                "assumption": key,
                "label": self.wedge.sweep_labels[key],
                "values": values,
                "top_choice_by_value": tops,
                "changes_top_choice": len(set(tops)) > 1,
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
        counts = {k: 0 for k in self.sweep}
        for p in self.points:
            if p.ranking[0] == centre_top:
                continue
            for key in self.sweep:
                for alt in self.sweep[key]:
                    if alt == p.settings[key]:
                        continue
                    q = index.get(self._key({**p.settings, key: alt}))
                    if q is not None and q.ranking[0] == centre_top:
                        counts[key] += 1
                        break
        return counts

    def dominated_worlds(self) -> list[str]:
        """Options that never rank first anywhere on the grid."""
        counts = self.win_counts()
        return [wid for wid, n in counts.items() if n == 0]

    def verdict(self) -> str:
        """One sentence an owner can act on. Only says what the grid supports."""
        counts = self.win_counts()
        best = max(counts, key=lambda k: counts[k])
        best_label = self.wedge.copy["world_verdict_labels"][best]
        tail = " This is sensitivity analysis, not a probability estimate."
        if self.top_stable():
            return f"{best_label} ranked first in every one of the {self.n} assumption combinations tested." + tail
        deciders = [r["label"].lower() for r in self.one_at_a_time() if r["changes_top_choice"]]
        count_txt = f"{counts[best]} of the {self.n} assumption combinations tested"
        if deciders:
            return (
                f"{best_label} ranked first in {count_txt}. The ranking depends mainly on "
                f"{deciders[0]}" + (f" and {deciders[1]}" if len(deciders) > 1 else "") + "." + tail
            )
        return f"{best_label} ranked first in {count_txt}." + tail

    # --- internals ---------------------------------------------------------------------------

    def _key(self, settings: dict[str, Any]) -> tuple:
        return tuple(settings[k] for k in self.sweep)

    def _find(self, settings: dict[str, Any]) -> SweepPoint | None:
        want = self._key(settings)
        for p in self.points:
            if self._key(p.settings) == want:
                return p
        return None


def run_sensitivity(wedge: WedgeSpec, baseline: Any, *, metric: str = DECISION_METRIC) -> SensitivityResult:
    result = SensitivityResult(wedge=wedge, baseline=baseline, metric=metric)
    keys = list(wedge.sweep)
    axis_names = set(wedge.default_axes)

    for combo in itertools.product(*(wedge.sweep[k] for k in keys)):
        settings = dict(zip(keys, combo))
        # A swept name is either an assumption axis the engine understands, a knob the wedge
        # accepts, or a field of the baseline itself; each is applied where it belongs.
        axes = {k: v for k, v in settings.items() if k in axis_names}
        knobs = {k: float(v) for k, v in settings.items() if k in wedge.knob_defaults}
        overrides = {k: float(v) for k, v in settings.items()
                     if k not in axis_names and k not in wedge.knob_defaults}
        b = baseline.replace(**overrides) if overrides else baseline

        comp: Comparison = run_comparison(wedge, b, axis_settings=axes, **knobs)
        result.points.append(SweepPoint(
            settings=settings,
            ranking=comp.ranking(metric),
            metric={w.spec.id: float(w.metrics[metric]) for w in comp.worlds},
        ))

    cp = result._find(result.centre())
    result.central_ranking = cp.ranking if cp else result.points[0].ranking
    return result
