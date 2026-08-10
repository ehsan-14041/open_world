"""
Assumption sweep, emergent trajectories, and pivotal-assumption analysis.

Three deliberate departures from the existing `simulation/ensemble.py` +
`simulation/robustness.py` stack (which stays untouched and keeps serving the Ops product):

1. **The grid is designed, not sampled.** Every world is one named combination of
   assumption settings. There is no RNG, so a result can always be reproduced *and*
   attributed to the assumptions that produced it.
2. **Counts, never probabilities.** A grid of assumption combinations is not a sample from
   a calibrated distribution, so "18 of 27 tested worlds" is the only honest statement.
   `Trajectory` carries `world_count`; nothing here emits a probability.
3. **Grouping is a deterministic outcome rule**, not clustering. Rules are declared up
   front, evaluated on the final state, and reported with the conditions that defined them.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from event_sim.engine import EventSimulation, Intervention, SimulationConfig, build_simulation
from event_sim.schemas import EventDefinition, Trajectory, WorldSlice


@dataclass
class OutcomeRule:
    """
    A named qualitative outcome. `test` receives the final state and the full result dict
    and returns True when the world belongs to this trajectory. Rules are evaluated in
    order; the first match wins, so the list is a decision list, not a scoring function.
    """

    id: str
    label: str
    description: str
    test: Callable[[dict[str, float], dict[str, Any]], bool]
    conditions: list[str]


def sweep_configs(slice_: WorldSlice, *, turns: int, lag_setting: str = "central", seed: int = 0) -> list[SimulationConfig]:
    """Full factorial over every assumption axis in the slice (deterministic order)."""
    axes = list(slice_.axes)
    if not axes:
        return [SimulationConfig(turns=turns, lag_setting=lag_setting, label="single", seed=seed)]
    combos = itertools.product(*[axis.settings for axis in axes])
    configs: list[SimulationConfig] = []
    for combo in combos:
        settings = {axis.id: value for axis, value in zip(axes, combo)}
        label = " / ".join(f"{axis.id}={settings[axis.id]}" for axis in axes)
        configs.append(SimulationConfig(
            turns=turns,
            axis_settings=settings,
            lag_setting=lag_setting,
            label=label,
            seed=seed,
        ))
    return configs


def run_sweep(
    slice_: WorldSlice,
    *,
    events: Sequence[EventDefinition],
    interventions: Sequence[Intervention] | None = None,
    turns: int = 12,
    lag_setting: str = "central",
    seed: int = 0,
) -> list[dict[str, Any]]:
    """
    Run every assumption combination. Returns one result dict per world, each carrying its
    `config.axis_settings`, so every downstream statement can name the assumptions behind it.
    """
    worlds: list[dict[str, Any]] = []
    for i, config in enumerate(sweep_configs(slice_, turns=turns, lag_setting=lag_setting, seed=seed)):
        sim = build_simulation(
            slice_,
            config=config,
            events=[EventDefinition.from_dict(e.to_dict()) for e in events],
            interventions=[Intervention.from_dict(iv.to_dict()) for iv in (interventions or [])],
        )
        result = sim.run()
        result["world_index"] = i
        result["series"] = {
            v.id: [float(rec["state"][v.id]) for rec in sim.trajectory] for v in slice_.variables
        }
        worlds.append(result)
    return worlds


# --------------------------------------------------------------------------------------
# Trajectory grouping
# --------------------------------------------------------------------------------------


def port_disruption_rules(slice_: WorldSlice) -> list[OutcomeRule]:
    """
    Outcome rules for the port-disruption slice, stated in the model's own units.

    The thresholds are presentation choices (what counts as "prolonged"), declared here in
    one place rather than buried in a scoring function, and reported with every trajectory.
    """
    service = slice_.variable("service_level")
    baseline = service.baseline if service else 0.95

    def _min_service(result: dict[str, Any]) -> float:
        return min(result["series"]["service_level"])

    def _final_service(state: dict[str, float]) -> float:
        return float(state.get("service_level", baseline))

    def _recovered(state: dict[str, float], result: dict[str, Any]) -> bool:
        return _final_service(state) >= baseline - 0.02

    return [
        OutcomeRule(
            id="rapid_recovery",
            label="Rapid Recovery",
            description="Service level dips but is back within 2 points of baseline by the end of the window.",
            test=lambda state, result: _recovered(state, result),
            conditions=[f"final service_level >= {baseline - 0.02:.2f}"],
        ),
        OutcomeRule(
            id="logistics_cascade",
            label="Logistics Cascade",
            description="Freight and delay stay elevated and service level is still depressed at the end of the window.",
            test=lambda state, result: (
                float(state.get("freight_cost", 100.0)) > 115.0
                and _final_service(state) < baseline - 0.02
            ),
            conditions=[
                "final freight_cost > 115",
                f"final service_level < {baseline - 0.02:.2f}",
            ],
        ),
        OutcomeRule(
            id="prolonged_shortage",
            label="Prolonged Shortage",
            description="Service level remains materially below baseline at the end of the window without a freight spike.",
            test=lambda state, result: _final_service(state) < baseline - 0.02,
            conditions=[f"final service_level < {baseline - 0.02:.2f}"],
        ),
        OutcomeRule(
            id="contained",
            label="Contained",
            description="No rule above matched: the disruption stayed within normal operating variation.",
            test=lambda state, result: True,
            conditions=["no other rule matched"],
        ),
    ]


def group_trajectories(
    worlds: Sequence[dict[str, Any]],
    rules: Sequence[OutcomeRule],
) -> list[Trajectory]:
    """
    Assign every swept world to the first matching outcome rule.

    `critical_assumptions` lists the axis settings shared by *every* member of a
    trajectory — i.e. the conditions a world must satisfy to land here. That is the
    product's actual answer to "what would have to be true".
    """
    buckets: dict[str, list[dict[str, Any]]] = {r.id: [] for r in rules}
    for world in worlds:
        state = world["final_state"]
        for rule in rules:
            if rule.test(state, world):
                buckets[rule.id].append(world)
                break

    trajectories: list[Trajectory] = []
    for rule in rules:
        members = buckets[rule.id]
        if not members:
            continue
        configs = [dict(m["config"]["axis_settings"]) for m in members]
        shared: list[str] = []
        if configs:
            for axis_id in configs[0]:
                values = {c.get(axis_id) for c in configs}
                if len(values) == 1:
                    shared.append(f"{axis_id} = {values.pop()}")
        representative = min(members, key=lambda m: int(m["world_index"]))
        trajectories.append(Trajectory(
            id=rule.id,
            label=rule.label,
            description=rule.description,
            member_configs=configs,
            conditions=list(rule.conditions),
            critical_assumptions=shared,
            failure_points=_failure_points(members),
            representative={
                "world_index": representative["world_index"],
                "label": representative["config"]["label"],
                "final_state": representative["final_state"],
                "fingerprint": representative["fingerprint"],
            },
        ))
    trajectories.sort(key=lambda t: -t.world_count)
    return trajectories


def _failure_points(members: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Where and when things broke, across members of a trajectory: the worst level reached
    per variable and the turn it happened, reported as a range across the member worlds.
    """
    if not members:
        return []
    out: list[dict[str, Any]] = []
    variables = list(members[0]["series"].keys())
    for vid in variables:
        troughs = [(min(m["series"][vid]), m["series"][vid].index(min(m["series"][vid]))) for m in members]
        peaks = [(max(m["series"][vid]), m["series"][vid].index(max(m["series"][vid]))) for m in members]
        baseline = members[0]["series"][vid][0]
        worst_low = min(t[0] for t in troughs)
        worst_high = max(p[0] for p in peaks)
        if abs(worst_low - baseline) >= abs(worst_high - baseline):
            value, turn = min(troughs, key=lambda t: t[0])
            direction = "trough"
        else:
            value, turn = max(peaks, key=lambda p: p[0])
            direction = "peak"
        if abs(value - baseline) < 1e-9:
            continue
        out.append({
            "variable": vid,
            "direction": direction,
            "worst_value": value,
            "turn": turn,
            "baseline": baseline,
            "deviation_from_baseline": value - baseline,
        })
    out.sort(key=lambda d: -abs(float(d["deviation_from_baseline"]) / (abs(float(d["baseline"])) or 1.0)))
    return out


# --------------------------------------------------------------------------------------
# Pivotal assumptions
# --------------------------------------------------------------------------------------


def pivotal_assumptions(
    worlds: Sequence[dict[str, Any]],
    *,
    outcome_variable: str,
    trajectories: Sequence[Trajectory] | None = None,
) -> dict[str, Any]:
    """
    Which uncertain assumption changes the conclusion the most?

    For each axis, the outcome variable's final value is averaged over all worlds sharing
    each setting of that axis; the axis's **influence** is the span between its best and
    worst setting average. Because the grid is full-factorial and balanced, every other
    axis is averaged out equally, so the span is a clean main effect.

    Also reported: whether flipping the axis alone changes which *trajectory* a world lands
    in (`changes_trajectory`) — the outcome the user actually cares about.
    """
    if not worlds:
        return {"outcome_variable": outcome_variable, "axes": []}

    axis_ids = sorted({k for w in worlds for k in w["config"]["axis_settings"]})
    finals = {int(w["world_index"]): float(w["final_state"].get(outcome_variable, 0.0)) for w in worlds}
    overall_span = max(finals.values()) - min(finals.values()) if finals else 0.0

    traj_of_world: dict[str, str] = {}
    for traj in trajectories or []:
        for member in traj.member_configs:
            traj_of_world[_config_key(member)] = traj.id

    rows: list[dict[str, Any]] = []
    for axis_id in axis_ids:
        by_setting: dict[str, list[float]] = {}
        for world in worlds:
            setting = str(world["config"]["axis_settings"].get(axis_id))
            by_setting.setdefault(setting, []).append(finals[int(world["world_index"])])
        means = {s: sum(vals) / len(vals) for s, vals in by_setting.items() if vals}
        if not means:
            continue
        best = max(means, key=lambda s: means[s])
        worst = min(means, key=lambda s: means[s])
        influence = means[best] - means[worst]

        changes_trajectory = False
        if traj_of_world:
            # Group worlds that are identical except for this axis; if such a group spans
            # more than one trajectory, flipping this assumption alone changes the answer.
            groups: dict[str, set[str]] = {}
            for world in worlds:
                others = {k: v for k, v in world["config"]["axis_settings"].items() if k != axis_id}
                traj_id = traj_of_world.get(_config_key(world["config"]["axis_settings"]), "")
                groups.setdefault(_config_key(others), set()).add(traj_id)
            changes_trajectory = any(len(v) > 1 for v in groups.values())

        rows.append({
            "axis": axis_id,
            "influence": abs(influence),
            "relative_influence": (abs(influence) / overall_span) if overall_span else 0.0,
            "best_setting": best,
            "best_outcome": means[best],
            "worst_setting": worst,
            "worst_outcome": means[worst],
            "setting_means": means,
            "changes_trajectory": changes_trajectory,
        })

    rows.sort(key=lambda r: -float(r["influence"]))
    for row in rows:
        rel = float(row["relative_influence"])
        row["rank"] = "HIGH" if rel >= 0.5 else ("MEDIUM" if rel >= 0.2 else "LOW")

    return {
        "outcome_variable": outcome_variable,
        "outcome_span_across_worlds": overall_span,
        "world_count": len(worlds),
        "axes": rows,
        "framing": (
            "Influence is the span of the outcome between an assumption's best and worst "
            "setting, averaged over all other assumptions. It answers 'what would have to "
            "be different for the conclusion to change', not 'how likely is each setting'."
        ),
    }


def _config_key(settings: dict[str, Any]) -> str:
    return "|".join(f"{k}={settings[k]}" for k in sorted(settings))


def envelope(worlds: Sequence[dict[str, Any]], variable: str) -> dict[str, Any]:
    """
    Min/max/median band across all swept worlds per turn — the trajectory envelope used by
    the UI and by historical replay evaluation. Explicitly a range across tested
    assumption combinations, not a confidence interval.
    """
    if not worlds:
        return {"variable": variable, "turns": [], "low": [], "high": [], "median": []}
    series = [w["series"][variable] for w in worlds if variable in w["series"]]
    length = min(len(s) for s in series)
    lows, highs, medians = [], [], []
    for t in range(length):
        column = sorted(s[t] for s in series)
        lows.append(column[0])
        highs.append(column[-1])
        medians.append(column[len(column) // 2])
    return {
        "variable": variable,
        "turns": list(range(length)),
        "low": lows,
        "high": highs,
        "median": medians,
        "world_count": len(series),
        "framing": "Range across tested assumption combinations; not a confidence interval.",
    }
