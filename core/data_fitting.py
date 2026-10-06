"""
Coefficient fitting from real time-series data (the "make it real" core).

Today the ops causal weights in `adapters/ops_scenario_builder._ARCHETYPE_CAUSAL` are
domain *guesses*. This module fits those weights from a customer's own historical
time series, keeping the archetype STRUCTURE (which variables connect — domain
knowledge) but estimating the WEIGHTS from data (standardized lagged regression).

It also backtests: fit on early weeks, predict held-out weeks, report R²/MAPE. That
turns "made-up coefficient" into "reproduces your last N weeks within X%" — the single
thing that converts this from a toy into sellable sensitivity analysis.

No pandas dependency (numpy + stdlib csv only). Pure functions; the fitted links plug
straight into `build_scenario(..., fitted_links=...)`, leaving the robustness/RDM
engine unchanged.
"""

from __future__ import annotations

import csv
import math
from typing import Any

import numpy as np

from adapters.ops_scenario_builder import _ARCHETYPE_CAUSAL


# ---------- data loading ----------

def load_csv(path: str, delimiter: str | None = None) -> list[dict[str, float]]:
    """Load a time-series CSV (one row per period) into a list of numeric dicts.
    delimiter is auto-detected (',' vs ';' vs '\\t') from the header if not given."""
    rows: list[dict[str, float]] = []
    if delimiter is None:
        with open(path, encoding="utf-8-sig") as f:
            first = f.readline()
        delimiter = max([",", ";", "\t"], key=lambda d: first.count(d))
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f, delimiter=delimiter):
            row: dict[str, float] = {}
            for k, v in raw.items():
                if k is None:
                    continue
                try:
                    row[k.strip()] = float(v)
                except (TypeError, ValueError):
                    continue
            if row:
                rows.append(row)
    return rows


def _series(rows: list[dict[str, float]], var: str) -> np.ndarray | None:
    vals = [r.get(var) for r in rows]
    if any(v is None for v in vals) or len(vals) < 3:
        return None
    return np.asarray(vals, dtype=float)


def _zdelta(arr: np.ndarray) -> tuple[np.ndarray, float, float]:
    """First difference, then z-score. Returns (z, mean_delta, std_delta)."""
    d = np.diff(arr)
    mu, sd = float(d.mean()), float(d.std())
    z = (d - mu) / sd if sd > 1e-9 else np.zeros_like(d)
    return z, mu, sd


def _edges_for(but: str) -> list[dict[str, Any]]:
    return _ARCHETYPE_CAUSAL.get(but, _ARCHETYPE_CAUSAL["general_ops"])


# ---------- fitting ----------

def fit_weights(rows: list[dict[str, float]], business_unit_type: str = "distribution",
                *, structure: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Fit causal-link weights from `rows`, keeping a fixed STRUCTURE. By default the structure
    is the vertical's archetype graph; pass `structure` (list of {from,to}) to fit an
    arbitrary graph (e.g. to test the fitter on any real dataset).
    Returns {fitted_links, per_target_r2, mean_r2, n_samples, warnings}.

    Method: for each target Y with declared parents, standardized least-squares of ΔY on
    the parents' Δ (contemporaneous — propagation is within-period). Standardized betas
    are the engine's [-1, 1] weights; sign and relative magnitude are the reliable signal.
    """
    edges = structure if structure is not None else _edges_for(business_unit_type)
    targets: dict[str, list[str]] = {}
    for e in edges:
        targets.setdefault(e["to"], []).append(e["from"])

    fitted_links: list[dict[str, Any]] = []
    per_target_r2: dict[str, float] = {}
    warnings: list[str] = []
    n_samples = max(0, len(rows) - 1)

    for y, parents in targets.items():
        ys = _series(rows, y)
        present = [p for p in parents if _series(rows, p) is not None]
        missing = [p for p in parents if p not in present]
        for m in missing:
            warnings.append(f"'{m}'→'{y}': column missing, kept archetype weight")
        if ys is None or not present:
            # fall back to archetype weights for this target
            for e in edges:
                if e["to"] == y:
                    fitted_links.append({"from": e["from"], "to": y, "weight": e["weight"], "_source": "archetype"})
            continue

        zy, _, _ = _zdelta(ys)
        cols = [_zdelta(_series(rows, p))[0] for p in present]
        X = np.column_stack(cols)
        if X.shape[0] < X.shape[1] + 2:
            warnings.append(f"target '{y}': only {X.shape[0]} samples for {X.shape[1]} parents — weak fit")
        try:
            betas, *_ = np.linalg.lstsq(X, zy, rcond=None)
        except Exception:
            betas = np.zeros(len(present))
        pred = X @ betas
        ss_res = float(((zy - pred) ** 2).sum())
        ss_tot = float(((zy - zy.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
        per_target_r2[y] = round(r2, 3)
        for p, b in zip(present, betas):
            fitted_links.append({"from": p, "to": y, "weight": round(float(max(-1.0, min(1.0, b))), 3), "_source": "fitted"})
        # archetype fallback for missing parents
        for m in missing:
            wm = next((e["weight"] for e in edges if e["from"] == m and e["to"] == y), 0.0)
            fitted_links.append({"from": m, "to": y, "weight": wm, "_source": "archetype"})

    mean_r2 = round(float(np.mean(list(per_target_r2.values()))), 3) if per_target_r2 else 0.0
    return {
        "fitted_links": fitted_links,
        "per_target_r2": per_target_r2,
        "mean_r2": mean_r2,
        "n_samples": n_samples,
        "warnings": warnings,
    }


# ---------- backtest ----------

def backtest(rows: list[dict[str, float]], business_unit_type: str = "distribution",
             holdout_frac: float = 0.3, *, structure: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Honest validation: fit on the early portion, then one-step-ahead predict each target
    on the held-out tail and compare to actual. Returns per-target and overall R²/MAPE.
    Pass `structure` to backtest an arbitrary graph (else the vertical archetype).
    """
    n = len(rows)
    if n < 8:
        return {"ok": False, "reason": f"need >= 8 periods to backtest, got {n}"}
    split = max(4, int(n * (1 - holdout_frac)))
    train, _ = rows[:split], rows[split:]
    edges = structure if structure is not None else _edges_for(business_unit_type)
    targets: dict[str, list[str]] = {}
    for e in edges:
        targets.setdefault(e["to"], []).append(e["from"])

    fit = fit_weights(train, business_unit_type, structure=structure)
    wmap = {(l["from"], l["to"]): l["weight"] for l in fit["fitted_links"]}

    per_target: dict[str, dict[str, float]] = {}
    all_actual, all_pred = [], []
    for y, parents in targets.items():
        ys = _series(rows, y)
        present = [p for p in parents if _series(rows, p) is not None]
        if ys is None or not present:
            continue
        # train standardization stats
        _, muY, sdY = _zdelta(ys[:split])
        parent_stats = {p: _zdelta(_series(rows, p)[:split])[1:] for p in present}
        if sdY < 1e-9:
            continue
        actual_levels, pred_levels = [], []
        for t in range(split, n):  # one-step-ahead on holdout
            dY_z = 0.0
            for p in present:
                muP, sdP = parent_stats[p]
                if sdP < 1e-9:
                    continue
                dXp = rows[t][p] - rows[t - 1][p]
                dY_z += wmap.get((p, y), 0.0) * ((dXp - muP) / sdP)
            dY_hat = dY_z * sdY + muY
            pred_levels.append(rows[t - 1][y] + dY_hat)
            actual_levels.append(rows[t][y])
        a, pr = np.asarray(actual_levels), np.asarray(pred_levels)
        ss_res = float(((a - pr) ** 2).sum())
        ss_tot = float(((a - a.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
        denom = np.where(np.abs(a) > 1e-9, np.abs(a), 1.0)
        mape = float(np.mean(np.abs((a - pr) / denom)) * 100)
        per_target[y] = {"r2": round(r2, 3), "mape_pct": round(mape, 2), "n": len(a)}
        all_actual.extend(actual_levels)
        all_pred.extend(pred_levels)

    if not all_actual:
        return {"ok": False, "reason": "no predictable targets with present parents"}
    a, pr = np.asarray(all_actual), np.asarray(all_pred)
    ss_res = float(((a - pr) ** 2).sum())
    ss_tot = float(((a - a.mean()) ** 2).sum())
    overall_r2 = round(1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0, 3)
    return {
        "ok": True,
        "overall_r2": overall_r2,
        "per_target": per_target,
        "train_periods": split,
        "holdout_periods": n - split,
        "verdict": ("strong" if overall_r2 >= 0.6 else "moderate" if overall_r2 >= 0.3 else "weak"),
    }


# ---------- levels + ridge (honest predictive validation, decoupled from engine weights) ----------

def _winsorize_fit(col: np.ndarray, lo_pct: float = 2.5, hi_pct: float = 97.5) -> tuple[float, float]:
    return float(np.percentile(col, lo_pct)), float(np.percentile(col, hi_pct))


def backtest_levels(
    rows: list[dict[str, float]],
    structure: list[dict[str, Any]],
    *,
    holdout_frac: float = 0.3,
    alpha: float = 1.0,
    robust: bool = False,
) -> dict[str, Any]:
    """
    Predictive backtest using ridge-regularized regression in LEVELS (with intercept),
    not the engine's standardized-delta / [-1,1]-clamped weights. This measures the
    honest predictive ceiling of the structure on real data, separate from whether the
    coefficients fit the engine's weight representation. alpha = ridge strength.

    robust=True winsorizes each feature/target column to its train [2.5, 97.5] percentile
    band before fitting — neutralizing the outliers that real ERP exports are full of
    (the chaos test showed 8% outliers crush the non-robust fit). Clip bounds come from
    train only (no leakage); holdout is clipped to those bounds.
    """
    n = len(rows)
    if n < 8:
        return {"ok": False, "reason": f"need >= 8 periods, got {n}"}
    split = max(4, int(n * (1 - holdout_frac)))
    targets: dict[str, list[str]] = {}
    for e in structure:
        targets.setdefault(e["to"], []).append(e["from"])

    all_a, all_p, per_target = [], [], {}
    for y, parents in targets.items():
        ys = _series(rows, y)
        present = [p for p in parents if _series(rows, p) is not None]
        if ys is None or not present:
            continue
        Xall = np.column_stack([_series(rows, p) for p in present] + [np.ones(n)])
        ys = ys.copy()
        if robust:
            # winsorize each feature column and the target to train percentile bounds
            for j in range(Xall.shape[1] - 1):
                lo, hi = _winsorize_fit(Xall[:split, j])
                Xall[:, j] = np.clip(Xall[:, j], lo, hi)
            ylo, yhi = _winsorize_fit(ys[:split])
            ys = np.clip(ys, ylo, yhi)
        # standardize features (not intercept) on train for stable ridge
        Xtr, ytr = Xall[:split], ys[:split]
        mu = Xtr[:, :-1].mean(0); sd = Xtr[:, :-1].std(0); sd[sd < 1e-9] = 1.0
        def _z(M):
            Z = M.copy(); Z[:, :-1] = (M[:, :-1] - mu) / sd; return Z
        Xtr_z = _z(Xtr)
        k = Xtr_z.shape[1]
        ridge = alpha * np.eye(k); ridge[-1, -1] = 0.0  # don't penalize intercept
        beta = np.linalg.solve(Xtr_z.T @ Xtr_z + ridge, Xtr_z.T @ ytr)
        yp = _z(Xall[split:]) @ beta; ya = ys[split:]
        ss_res = float(((ya - yp) ** 2).sum()); ss_tot = float(((ya - ya.mean()) ** 2).sum())
        r2 = round(1 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0, 3)
        per_target[y] = {"r2": r2, "n": len(ya)}
        all_a.extend(ya.tolist()); all_p.extend(yp.tolist())

    if not all_a:
        return {"ok": False, "reason": "no predictable targets"}
    a, pr = np.asarray(all_a), np.asarray(all_p)
    overall = round(1 - ((a - pr) ** 2).sum() / max(1e-9, ((a - a.mean()) ** 2).sum()), 3)
    return {"ok": True, "overall_r2": overall, "per_target": per_target,
            "verdict": ("strong" if overall >= 0.6 else "moderate" if overall >= 0.3 else "weak")}


# ---------- synthetic data (validate the fitter recovers known weights) ----------

def synthesize_ops_history(
    business_unit_type: str = "distribution",
    weeks: int = 60,
    *,
    seed: int = 7,
    noise: float = 0.25,
    true_weights: dict[tuple[str, str], float] | None = None,
) -> tuple[list[dict[str, float]], dict[tuple[str, str], float]]:
    """
    Generate a realistic ops time series from KNOWN weights, so the fitter can be
    validated (does it recover them?). Returns (rows, true_weights).

    Built in standardized-delta space (each Δ ~ unit variance) so standardized regression
    recovers the weights' sign and relative magnitude; levels are mapped to realistic
    ranges for the CSV (z-scoring in the fitter is invariant to that mapping).
    """
    rng = np.random.default_rng(seed)
    edges = _edges_for(business_unit_type)
    tw = true_weights or {(e["from"], e["to"]): e["weight"] for e in edges}

    targets: dict[str, list[str]] = {}
    for e in edges:
        targets.setdefault(e["to"], []).append(e["from"])
    all_vars = {v for e in edges for v in (e["from"], e["to"])}
    roots = [v for v in all_vars if v not in targets]

    # topological order
    order: list[str] = list(roots)
    pending = [v for v in all_vars if v not in roots]
    guard = 0
    while pending and guard < 100:
        guard += 1
        for v in list(pending):
            if all(p in order for p in targets.get(v, [])):
                order.append(v)
                pending.remove(v)
    order.extend(pending)  # any residual (cycle) appended

    # standardized delta series per var
    d: dict[str, np.ndarray] = {}
    for v in roots:
        d[v] = rng.standard_normal(weeks)
    for v in order:
        if v in roots:
            continue
        acc = np.zeros(weeks)
        for p in targets.get(v, []):
            if p in d:
                acc += tw.get((p, v), 0.0) * d[p]
        d[v] = acc + noise * rng.standard_normal(weeks)

    # realistic level ranges
    base = {
        "weekly_demand": 650, "inventory_on_hand": 10000, "safety_stock": 3500,
        "lead_time_days": 26, "fill_rate": 0.92, "unit_cost": 24, "supplier_risk": 0.45,
        "capacity_utilization": 0.7, "holding_cost_weekly": 13000, "stockout_risk": 0.05,
        "backlog_weeks": 0.5,
    }
    scale = {
        "weekly_demand": 40, "inventory_on_hand": 600, "safety_stock": 150,
        "lead_time_days": 2.5, "fill_rate": 0.02, "unit_cost": 1.2, "supplier_risk": 0.05,
        "capacity_utilization": 0.04, "holding_cost_weekly": 500, "stockout_risk": 0.02,
        "backlog_weeks": 0.15,
    }
    rows: list[dict[str, float]] = []
    levels = {v: float(base.get(v, 50.0)) for v in all_vars}
    for t in range(weeks):
        for v in all_vars:
            levels[v] = levels[v] + scale.get(v, 1.0) * float(d[v][t])
        rows.append({v: round(levels[v], 4) for v in all_vars})
    return rows, tw


def corrupt_rows(
    rows: list[dict[str, float]],
    *,
    seed: int = 0,
    noise: float = 0.0,
    missing: float = 0.0,
    outlier: float = 0.0,
    lag_cols: list[str] | None = None,
    lag: int = 0,
    seasonality_col: str | None = None,
    seasonality: float = 0.0,
    regime_shift: float = 0.0,
    regime_col: str | None = None,
) -> list[dict[str, float]]:
    """
    Return a DEGRADED copy of `rows` to simulate dirty real-world data. Models the mess
    a real ERP export brings, so we can see how much fitted signal survives:
      - noise: multiplicative gaussian (each value *= 1 + N(0, noise))
      - missing: fraction of cells dropped, then forward-filled (typical cleaning)
      - outlier: fraction of cells spiked x3-5
      - lag: shift driver columns `lag` periods (breaks the same-period assumption)
      - seasonality: add a sinusoid to `seasonality_col` (amplitude = seasonality*std)
      - regime_shift: scale the second half of `regime_col` by (1 + regime_shift)
    """
    rng = np.random.default_rng(seed)
    cols = list(rows[0].keys())
    data = {c: np.array([r[c] for r in rows], float) for c in cols}
    n = len(rows)

    if lag and lag_cols:
        for c in lag_cols:
            if c in data:
                shifted = np.empty(n); shifted[:lag] = data[c][0]; shifted[lag:] = data[c][:-lag]
                data[c] = shifted
    if seasonality and seasonality_col in data:
        amp = seasonality * (data[seasonality_col].std() or 1.0)
        data[seasonality_col] = data[seasonality_col] + amp * np.sin(np.arange(n) * 2 * np.pi / 13.0)
    if regime_shift and regime_col in data:
        half = n // 2
        data[regime_col][half:] = data[regime_col][half:] * (1.0 + regime_shift)
    if noise:
        for c in cols:
            data[c] = data[c] * (1.0 + rng.normal(0, noise, n))
    if outlier:
        for c in cols:
            mask = rng.random(n) < outlier
            data[c][mask] = data[c][mask] * rng.uniform(3, 5, mask.sum())
    if missing:
        for c in cols:
            mask = rng.random(n) < missing
            arr = data[c].copy()
            for i in range(n):
                if mask[i]:
                    arr[i] = arr[i - 1] if i > 0 else arr[i]  # forward-fill
            data[c] = arr

    return [{c: float(data[c][i]) for c in cols} for i in range(n)]


def write_csv(rows: list[dict[str, float]], path: str) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
