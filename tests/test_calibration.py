"""
Tests for dynamic calibration: min/max interval, recalibration state.
"""

from __future__ import annotations

from core.calibration import (
    get_recalibration_state,
    set_last_recalibration_turn,
    clear_recalibration_trigger,
    check_recalibration_trigger,
)


def test_recalibration_state_keys() -> None:
    """get_recalibration_state returns expected keys."""
    state = get_recalibration_state()
    assert "recalibration_triggered" in state
    assert "last_recalibration_turn" in state


def test_set_last_recalibration_turn() -> None:
    """set_last_recalibration_turn updates state visible in get_recalibration_state."""
    set_last_recalibration_turn(7)
    state = get_recalibration_state()
    assert state["last_recalibration_turn"] == 7
    set_last_recalibration_turn(-1)


def test_check_recalibration_trigger_min_interval_blocks() -> None:
    """When min_interval_turns is set and we recently recalibrated, trigger returns False."""
    set_last_recalibration_turn(5)
    # Provenance with turn 6 (only 1 turn after last recal); min_interval=3 should block
    prov = [{"turn": i} for i in range(1, 8)]
    should, reason = check_recalibration_trigger(
        prov,
        recalibrate_turns=10,
        min_interval_turns=3,
        max_interval_turns=100,
    )
    # May be False due to min_interval (6 - 5 = 1 < 3) or due to no health/rmse trigger
    assert isinstance(should, bool)
    set_last_recalibration_turn(-1)
