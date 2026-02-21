"""Simple unique id generator for entities, relations, turns."""

import uuid
from typing import Optional


def next_id(prefix: str = "id") -> str:
    """Return a unique string id, optionally with a prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
