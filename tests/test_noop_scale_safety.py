"""
Regression: a no-op ("steady") action must not apply catastrophic, scale-blind deltas
to large-magnitude variables that have no explicit variable_spec.

Root cause (fixed): core/soft_constraints.apply_hard_clip applied DEFAULT_VARIABLE_SPEC
(min=0, max=100) to ANY unspecified variable, so an unspecified mrr=10000 was clamped
to 100 — recorded as a delta of -9900 (a 99% wipe) on a steady no-op turn.
Fix: _effective_spec only applies the default [0,100] guard to variables whose current
value is plausibly on that normalized scale; large-scale variables are left unbounded.
"""

from __future__ import annotations

from schemas.scenario_schema import normalize_scenario
from simulation.loop import SimulationLoop


def _noop_scenario() -> dict:
    return normalize_scenario({
        "description": "isolated no-op",
        "initial_state": {"mrr": 10000.0, "headcount": 50.0},
        # mrr deliberately has NO spec (large scale); headcount is specced and normal.
        "variable_specs": {"headcount": {"min": 0, "max": 500}},
        "initial_agents": [{"name": "op", "role": "Operator", "objectives": {"mrr": 1.0}}],
        "allowed_actions": ["steady"],
    })


def test_steady_does_not_catastrophically_clamp_large_variable() -> None:
    res = SimulationLoop(scenario_data=_noop_scenario(), dry_run=True).run(
        steps=3, return_provenance=True, silent=True, delay_between_rounds=0.0,
    )
    # The fixed bug produced delta_applied[mrr] == -9900 (99% of value) on a no-op turn.
    for pe in res["provenance"]:
        d = (pe.get("turn_record") or {}).get("delta_applied") or {}
        mrr_delta = d.get("mrr", 0.0)
        assert abs(mrr_delta) < 100.0, f"catastrophic scale-blind delta on no-op: {mrr_delta}"


def test_steady_keeps_large_variable_essentially_flat() -> None:
    res = SimulationLoop(scenario_data=_noop_scenario(), dry_run=True).run(
        steps=5, return_provenance=True, silent=True, delay_between_rounds=0.0,
    )
    final = res["final"].get("variables") or res["final"].get("global_state") or {}
    mrr = final.get("mrr")
    # Broken behavior collapsed mrr to ~100 (99% loss). After all three scale-aware
    # fixes (clamp, min-delta nudge, STOCK decay) a no-op leaves mrr essentially flat:
    # only the negligible bounded liveliness nudge remains (< 1%).
    assert mrr is not None and abs(mrr - 10000.0) < 100.0, f"mrr drifted on no-op: {mrr}"


def test_large_unspecified_variable_has_no_default_decay() -> None:
    """Layer 3: physics_core must not apply the default 1%/turn STOCK decay to a
    large-scale unspecified variable (it would erode it toward baseline)."""
    from core.physics_core import _get_spec_decay
    assert _get_spec_decay("mrr", {}, current_value=10000.0) == 0.0      # large -> no decay
    assert _get_spec_decay("satisfaction", {}, current_value=80.0) == 0.01  # normalized -> default
    assert _get_spec_decay("x", {"x": {"decay": 0.05}}, current_value=10000.0) == 0.05  # explicit wins


def test_specced_normal_variable_still_clamped() -> None:
    """The default guard must still protect genuinely normalized unspecified variables."""
    from core.soft_constraints import apply_hard_clip
    # 'satisfaction' has no spec and sits at 95 (normalized scale): a +20 delta must clamp to 100.
    out = apply_hard_clip({"satisfaction": 95.0}, {}, {"satisfaction": 20.0})
    assert out["satisfaction"] == 5.0  # 100 - 95


def test_large_unspecified_variable_not_clamped() -> None:
    from core.soft_constraints import apply_hard_clip
    # mrr=10000 with no spec: a 0 delta must stay 0 (not become -9900).
    out = apply_hard_clip({"mrr": 10000.0}, {}, {"mrr": 0.0})
    assert out["mrr"] == 0.0
