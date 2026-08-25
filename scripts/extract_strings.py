"""
Extract the report's translatable strings into a catalogue.

Translation happens on the TEMPLATE, before the data payload is injected — so a translation
can never touch a number, a ranking or a fingerprint, by construction. This produces the list
of source strings a translator (human or model) is allowed to replace.

Two rules make the substitution safe:

  * only strings that occur EXACTLY ONCE in the template are catalogued, so a replacement
    cannot land somewhere it was not meant to;
  * `${...}` placeholders and inline tags are recorded, and a translation that loses or
    invents one is rejected at apply time rather than shipped.

The page is one file of markup and script, so a regex lexer will occasionally match between
two unrelated quotes and produce a fragment of JavaScript. Everything below the extraction is
there to throw those away — it is cheaper to drop a real string than to ship a broken page.

    python scripts/extract_strings.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html"
OUT = ROOT / "deploy" / "php" / "assets" / "strings.json"

PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
TAG = re.compile(r"</?[a-zA-Z][^>]*>")

# Text between tags, and the string / template literals the page builds its copy from.
HTML_TEXT = re.compile(r">([^<>{}$]{4,}?)<")
SINGLE_QUOTED = re.compile(r"'([^'\\\n]{8,}?)'")
BACKTICKED = re.compile(r"`([^`\\]{8,}?)`")

SKIP_PREFIXES = ("http", "__", "#", "/", "@")
# Fragments of the page's own JavaScript a loose match can pick up.
JS_TOKENS = ("=>", "===", "!==", "document.", "textContent", "querySelector", "innerHTML",
             "getElementById", "function", "return ", "var(--", "px;", "});", "addEventListener",
             "classList", "JSON.", "Math.round(", ".map(", ".join(", "=>`", "${(")
STARTS_OK = re.compile(r"[A-Z0-9]|[a-z]|<b>|<span")


def looks_like_prose(s: str) -> bool:
    text = s.strip()
    if len(text) < 8 or "\n" in text:
        return False
    if text.startswith(SKIP_PREFIXES):
        return False
    if any(token in text for token in JS_TOKENS):
        return False
    if not STARTS_OK.match(text):
        return False
    # An attribute fragment ( type="text" ) is code; prose with inline markup is not.
    if re.search(r'\w="', text) and not TAG.search(text):
        return False
    # Unbalanced brackets mean the match ran across an expression boundary.
    for opener, closer in (("(", ")"), ("[", "]"), ("{", "}")):
        if text.count(opener) != text.count(closer):
            return False
    words = re.findall(r"[A-Za-z']{2,}", TAG.sub(" ", PLACEHOLDER.sub(" ", text)))
    if len(words) < 2:
        return False
    if re.fullmatch(r"[a-z_]+(,\s*[a-z_]+)*", text):
        return False
    return True


def main() -> int:
    template = TEMPLATE.read_text(encoding="utf-8")
    body = template.split("<body>", 1)[1]
    # The page's markup only — the literal patterns below cover its scripts, and letting the
    # tag matcher loose on them picks up JavaScript.
    markup = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    markup = re.sub(r"<style.*?</style>", "", markup, flags=re.S)

    seen: dict[str, None] = {}
    for pattern, source in ((HTML_TEXT, markup), (SINGLE_QUOTED, template), (BACKTICKED, template)):
        for match in pattern.findall(source):
            text = match.strip()
            if looks_like_prose(text):
                seen.setdefault(text, None)

    entries = []
    ambiguous = 0
    for text in seen:
        if template.count(text) != 1:
            ambiguous += 1
            continue
        entries.append({
            "text": text,
            "placeholders": PLACEHOLDER.findall(text),
            "tags": TAG.findall(text),
        })
    entries.sort(key=lambda e: (-len(e["text"]), e["text"]))
    for i, e in enumerate(entries):
        e["id"] = f"s{i:03d}"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"source_language": "en", "strings": entries}, indent=1, ensure_ascii=False),
        encoding="utf-8")

    words = sum(len(re.findall(r"\S+", e["text"])) for e in entries)
    print(f"catalogued          {len(entries)} strings  ({words} words)")
    print(f"carrying ${{...}}     {sum(1 for e in entries if e['placeholders'])}")
    print(f"carrying markup     {sum(1 for e in entries if e['tags'])}")
    print(f"dropped, ambiguous  {ambiguous} (appear more than once in the template)")
    print(f"written             {OUT.relative_to(ROOT)}  {OUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
