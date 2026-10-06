"""
Extract the report's translatable strings into a catalogue for the LLM translation feature.

    python scripts/extract_strings.py

The product ships two authored languages, English and Persian, in `i18n/`. A maintainer can
add a third by having a model translate it, and this is the list of strings that offer covers.

Two things make the substitution safe, and both come from the catalogue rather than from
guesswork about the page:

  * every string is addressed by its path in the catalogue (`ui.home_lede`,
    `wedges.cafe.headline`), so a translation lands on exactly one string and cannot
    accidentally match text elsewhere;
  * a string's `{...}` slots and inline tags are recorded, and a translation that loses or
    invents one is rejected at apply time rather than shipped.

What the offer cannot reach is a number. A generated language is folded into the bundle's
`i18n` block and nowhere else, so the figures, rankings, counts and fingerprints a report
carries are the same bytes in every language.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.wedge.i18n import DEFAULT_LANGUAGE, catalogue  # noqa: E402

OUT = ROOT / "deploy" / "php" / "assets" / "strings.json"

SLOT = re.compile(r"\{\w+(?::[^}]*)?\}")
TAG = re.compile(r"</?[a-zA-Z][^>]*>")

#: Paths that name a machine, not a reader. `numerals` selects a digit system and `dir` a
#: writing direction; translating either would break the page rather than localise it.
NOT_COPY = ("numerals", "dir", "lang", "icon")


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str) and path.rsplit(".", 1)[-1] not in NOT_COPY:
        yield path, node


def main() -> int:
    entries = []
    for path, text in walk(catalogue(DEFAULT_LANGUAGE)):
        if not text.strip():
            continue
        entries.append({
            "id": path,
            "text": text,
            "placeholders": SLOT.findall(text),
            "tags": TAG.findall(text),
        })

    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "a catalogue path must address exactly one string"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": DEFAULT_LANGUAGE, "strings": entries},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with_slots = sum(1 for e in entries if e["placeholders"])
    with_tags = sum(1 for e in entries if e["tags"])
    print(f"{len(entries)} strings  ({with_slots} with slots, {with_tags} with inline markup)")
    print(f"  {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
