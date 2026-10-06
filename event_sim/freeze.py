"""
Semantic freeze snapshots.

A held-out test is only held out if the model provably predates the data. This module
computes a stable, semantic hash of everything that determines a replay's behaviour, so a
snapshot taken *before* Event #3 was searched for can be re-verified afterwards.

"Semantic" rather than file-level: the hash covers the fields that change dynamics
(coefficients, lags, polarities, baselines, scales, responses, stock rules, mappings) and
deliberately ignores prose fields like `description` and `notes`, so documentation can be
improved without appearing to be a model change — and so a real change cannot hide behind a
documentation edit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from event_sim.registry import get_module
from event_sim.schemas import WorldModule

#: Modules whose semantics are frozen for the held-out experiment.
FROZEN_MODULES = ("port_disruption", "port_disruption_h1_queue_experimental")


def _semantic_dict(module: WorldModule) -> dict[str, Any]:
    """Everything that changes behaviour; nothing that does not."""
    return {
        "id": module.id,
        "time_unit": module.time_unit,
        "variables": sorted(
            (
                {
                    "id": v.id,
                    "baseline": v.baseline,
                    "scale": v.scale,
                    "min": v.minimum,
                    "max": v.maximum,
                    "response": v.response,
                    "kind": v.kind,
                    "stock": dict(sorted(v.stock.items())),
                    "axis": v.axis,
                }
                for v in module.variables
            ),
            key=lambda d: str(d["id"]),
        ),
        "edges": sorted(
            (
                {
                    "id": e.id,
                    "polarity": e.polarity,
                    "effect": e.effect.to_dict(),
                    "lag": e.lag.to_dict(),
                    "mechanism_type": e.mechanism_type,
                    "axis": e.axis,
                }
                for e in module.edges
            ),
            key=lambda d: str(d["id"]),
        ),
        "axes": sorted(
            (
                {
                    "id": a.id,
                    "settings": list(a.settings),
                    "applies_to": sorted(a.applies_to),
                    "mapping": {k: dict(sorted(v.items())) for k, v in sorted(a.mapping.items())},
                }
                for a in module.axes
            ),
            key=lambda d: str(d["id"]),
        ),
        "interventions": sorted(
            (
                {
                    "id": i.get("id"),
                    "effects_per_unit": dict(sorted((i.get("effects_per_unit") or {}).items())),
                    "default_magnitude": i.get("default_magnitude"),
                }
                for i in module.interventions
            ),
            key=lambda d: str(d["id"]),
        ),
    }


def module_hash(module_id: str) -> str:
    """Stable semantic hash of one world module."""
    blob = json.dumps(_semantic_dict(get_module(module_id)), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def code_hash(*relative_paths: str) -> str:
    """Hash of the evaluation/engine source files, so scoring logic is frozen too."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for rel in sorted(relative_paths):
        path = root / rel
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    return digest.hexdigest()


#: Source files whose behaviour the held-out result depends on.
FROZEN_CODE_PATHS = (
    "event_sim/engine.py",
    "event_sim/sweep.py",
    "event_sim/historical/evaluation.py",
    "event_sim/historical/replay.py",
)


def snapshot() -> dict[str, Any]:
    """Full freeze snapshot: module semantics plus evaluation code."""
    return {
        "modules": {mid: module_hash(mid) for mid in FROZEN_MODULES},
        "evaluation_code": code_hash(*FROZEN_CODE_PATHS),
        "code_paths": list(FROZEN_CODE_PATHS),
    }


def verify(expected: dict[str, Any]) -> list[str]:
    """Return a list of drift descriptions; empty means the freeze still holds."""
    current = snapshot()
    drift: list[str] = []
    for module_id, expected_hash in (expected.get("modules") or {}).items():
        actual = current["modules"].get(module_id)
        if actual != expected_hash:
            drift.append(f"module {module_id}: {expected_hash[:12]} -> {actual[:12] if actual else 'MISSING'}")
    if expected.get("evaluation_code") and expected["evaluation_code"] != current["evaluation_code"]:
        drift.append(
            f"evaluation code: {expected['evaluation_code'][:12]} -> {current['evaluation_code'][:12]}"
        )
    return drift
