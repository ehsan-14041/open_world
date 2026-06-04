from __future__ import annotations

from typing import Any

from core import llm_service
from core.llm_service import call_llm


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, bool]] = []

    def __call__(
        self,
        prompt: str,
        system: str | None,
        *,
        as_json: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        self.calls.append((prompt, system, as_json))
        if as_json:
            # Minimal valid object for empty schema
            return {"ok": True}
        return "ok"


def test_llm_service_cache_key_avoids_duplicate_calls() -> None:
    fake = _FakeClient()
    cache_key = "test-key"

    out1 = call_llm(
        "prompt",
        "system",
        schema={"required": [], "types": {}},
        cache_key=cache_key,
        client_fn=fake,
    )
    out2 = call_llm(
        "prompt",
        "system",
        schema={"required": [], "types": {}},
        cache_key=cache_key,
        client_fn=fake,
    )

    assert isinstance(out1, dict)
    assert out2 == out1
    # Only one underlying client call because of cache hit.
    assert len(fake.calls) == 1


def test_make_cache_key_stable_for_same_inputs() -> None:
    h1 = llm_service.make_cache_key("act", "snap-hash")
    h2 = llm_service.make_cache_key("act", "snap-hash")
    h3 = llm_service.make_cache_key("other-act", "snap-hash")

    assert h1 == h2
    assert h1 != h3

