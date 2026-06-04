from __future__ import annotations

from simulation.loop import SimulationLoop


def test_run_streaming_emits_versions_block(tmp_path) -> None:
    loop = SimulationLoop(scenario_data={"initial_state": {}, "relations": [], "causal_links": [], "events": []})
    gen = loop.run_streaming(steps=1, snapshot_out_path=str(tmp_path / "snap.json"), delay_between_rounds=0.0)
    # Exhaust generator
    last = None
    for item in gen:
        last = item
    assert last is not None
    assert isinstance(last, dict)
    assert "versions" in last
    versions = last["versions"]
    assert isinstance(versions, dict)
    assert "engine" in versions and "schema" in versions and "trace" in versions

