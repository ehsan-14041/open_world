"""
World module registry: discover and load world_models/<domain>/<id>.json.

Loading always validates through event_sim.evidence.validate_module, so a module that
overclaims its evidence cannot enter a simulation at all.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from event_sim.evidence import validate_module
from event_sim.schemas import WorldModule

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORLD_MODELS_DIR = _PROJECT_ROOT / "world_models"


class ModuleNotFoundError(KeyError):
    """Raised when a requested world module id does not exist in the library."""


def _module_paths(root: Path | None = None) -> list[Path]:
    base = root or WORLD_MODELS_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob("*/*.json") if p.is_file())


def load_module_file(path: str | Path) -> WorldModule:
    """Load and validate a single module file."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    module = WorldModule.from_dict(data)
    validate_module(module)
    return module


@lru_cache(maxsize=1)
def _registry() -> dict[str, WorldModule]:
    out: dict[str, WorldModule] = {}
    for path in _module_paths():
        module = load_module_file(path)
        out[module.id] = module
    return out


def clear_cache() -> None:
    """Drop the cached registry (tests and module authoring)."""
    _registry.cache_clear()


def available_modules() -> list[dict[str, Any]]:
    """Summary of every module in the library, for the API / module browser."""
    return [
        {
            "id": m.id,
            "domain": m.domain,
            "title": m.title,
            "time_unit": m.time_unit,
            "version": m.version,
            "geography": list(m.geography),
            "variable_count": len(m.variables),
            "edge_count": len(m.edges),
            "axes": [a.id for a in m.axes],
            "description": m.description,
        }
        for m in sorted(_registry().values(), key=lambda m: (m.domain, m.id))
    ]


def get_module(module_id: str) -> WorldModule:
    """Fetch a validated module by id."""
    reg = _registry()
    if module_id not in reg:
        raise ModuleNotFoundError(
            f"Unknown world module {module_id!r}. Available: {sorted(reg)}"
        )
    return reg[module_id]


def modules_for_domain(domain: str) -> list[WorldModule]:
    """All modules in a domain (economy, supply_chain, energy, ...)."""
    return [m for m in _registry().values() if m.domain == domain]
