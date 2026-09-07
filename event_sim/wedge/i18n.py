"""
The bilingual layer.

Language is presentation state and nothing else. Both languages travel inside every report, so
switching one is a re-render, not a re-run: no figure, ranking, count or fingerprint can move,
because the numbers were computed once and the switch never touches them. That is a structural
guarantee rather than a promise, and a test asserts it.

What lives where:

    i18n/<lang>.json    every customer-facing string, authored per language
    wedge.copy          structure only — which field plays which role, which grid key, which
                        settings a study actually backs

Nothing in the catalogues is a model value: no coefficient, no elasticity, no threshold. If a
number needs to differ between languages it is a formatting question, and formatting is done at
render time from one underlying figure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

I18N_DIR = Path(__file__).resolve().parent.parent.parent / "i18n"

#: The languages the product ships in. A new one is a file, not a code change.
LANGUAGES: tuple[str, ...] = ("en", "fa")
DEFAULT_LANGUAGE = "en"


def _load(lang: str) -> dict[str, Any]:
    path = I18N_DIR / f"{lang}.json"
    if not path.is_file():
        raise KeyError(f"No catalogue for language {lang!r} (looked in {path})")
    return json.loads(path.read_text(encoding="utf-8"))


def catalogue(lang: str) -> dict[str, Any]:
    """The whole catalogue for one language."""
    if lang not in _CACHE:
        _CACHE[lang] = _load(lang)
    return _CACHE[lang]


_CACHE: dict[str, dict[str, Any]] = {}


def ui(lang: str) -> dict[str, str]:
    return catalogue(lang)["ui"]


def wedge_text(lang: str, wedge_id: str) -> dict[str, Any]:
    return catalogue(lang)["wedges"][wedge_id]


def direction(lang: str) -> str:
    return catalogue(lang)["dir"]


def languages() -> list[dict[str, str]]:
    """What the language switcher offers."""
    return [{"code": code, "label": catalogue(code)["label"], "dir": catalogue(code)["dir"]}
            for code in LANGUAGES]


def bundle_for(wedge_id: str) -> dict[str, Any]:
    """
    Every language's strings for one wedge, in the shape the page reads.

    The page holds all of them and swaps between them locally, so a language change never asks
    the server for anything and never re-enters the model.
    """
    out: dict[str, Any] = {"languages": languages(), "default": DEFAULT_LANGUAGE, "strings": {}}
    for code in LANGUAGES:
        cat = catalogue(code)
        out["strings"][code] = {
            "dir": cat["dir"],
            "label": cat["label"],
            # Which digits a reader expects. The figure is one number either way; only its
            # rendering differs, which is the whole point of keeping language presentational.
            "numerals": cat.get("numerals", "latn"),
            "ui": cat["ui"],
            "wedge": cat["wedges"][wedge_id],
            # Every business's name, so the switcher in the header can label the other two
            # without the page having to fetch anything.
            "all_wedges": {wid: {"business": x["business"], "business_short": x["business_short"],
                                 "icon": x["icon"]} for wid, x in cat["wedges"].items()},
        }
    return out


def chooser_bundle() -> dict[str, Any]:
    """The home screen's strings, for every language and every wedge."""
    out: dict[str, Any] = {"languages": languages(), "default": DEFAULT_LANGUAGE, "strings": {}}
    for code in LANGUAGES:
        cat = catalogue(code)
        out["strings"][code] = {
            "dir": cat["dir"],
            "label": cat["label"],
            "numerals": cat.get("numerals", "latn"),
            "ui": cat["ui"],
            # `problem` names the situation on each card; `world_names` lets the worked
            # example promise exactly the three decisions the next page delivers.
            "wedges": {wid: {k: v for k, v in w.items()
                             if k in ("business", "business_short", "question", "icon", "noun",
                                      "problem", "world_names", "business_covers")}
                       for wid, w in cat["wedges"].items()},
        }
    return out


def missing_keys() -> dict[str, list[str]]:
    """
    Keys present in the reference language but absent elsewhere, and the reverse.

    A half-translated screen is worse than an untranslated one: it reads as broken rather than
    as English. This is what the translation-completeness test checks.
    """
    def flatten(node: Any, prefix: str = "") -> set[str]:
        keys: set[str] = set()
        if isinstance(node, dict):
            for k, v in node.items():
                keys |= flatten(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(node, list):
            keys.add(prefix + "[]")
        else:
            keys.add(prefix)
        return keys

    reference = flatten(catalogue(DEFAULT_LANGUAGE))
    out: dict[str, list[str]] = {}
    for code in LANGUAGES:
        if code == DEFAULT_LANGUAGE:
            continue
        here = flatten(catalogue(code))
        out[f"missing_in_{code}"] = sorted(reference - here)
        out[f"extra_in_{code}"] = sorted(here - reference)
    return out
