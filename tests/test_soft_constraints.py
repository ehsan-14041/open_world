"""Tests: soft constraints (rate_limit, diminishing returns, hard clip). Backward compat when no variable_specs."""

from __future__ import annotations

from core.soft_constraints import apply_all_constraints, apply_soft_constraints, apply_hard_clip


def test_no_specs_backward_compat() -> None:
    """No variable_specs -> no change to deltas."""
    variables = {"x": 50}
    pending = {"x": 10}
    out = apply_all_constraints(variables, None, pending)
    assert out == {"x": 10.0}


def test_rate_limit() -> None:
    """Rate limit clamps per-var change."""
    variables = {"tension": 50}
    specs = {"tension": {"rate_limit": 5}}
    pending = {"tension": 20}
    out = apply_soft_constraints(variables, specs, pending)
    assert out["tension"] == 5.0


def test_change_budget() -> None:
    """Change budget scales down when exceeded."""
    variables = {"a": 0, "b": 0}
    pending = {"a": 10, "b": 10}
    out = apply_soft_constraints(variables, None, pending, change_budget=10.0)
    total = sum(abs(v) for v in out.values())
    assert total <= 10.01


def test_hard_clip() -> None:
    """Hard clip enforces min/max."""
    variables = {"x": 95}
    specs = {"x": {"min": 0, "max": 100, "clip": True}}
    pending = {"x": 20}
    out = apply_hard_clip(variables, specs, pending)
    assert variables["x"] + out["x"] <= 100
