from __future__ import annotations

"""
Central version identifiers for the Open World Engine.

These versions are intentionally coarse-grained and are meant to be surfaced
in engine outputs (snapshots, traces, exports) so external systems can make
forward-compatible decisions and migrations.
"""

ENGINE_VERSION: str = "3.0.0"
SCHEMA_VERSION: str = "3.0.0"
TRACE_VERSION: str = "3.0.0"
EXTENSION_API_VERSION: str = "1.0.0"


def version_summary() -> dict[str, str]:
    """Return a small dict of the current version identifiers."""
    return {
        "engine": ENGINE_VERSION,
        "schema": SCHEMA_VERSION,
        "trace": TRACE_VERSION,
        "extension_api": EXTENSION_API_VERSION,
    }

