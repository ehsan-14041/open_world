"""
Language is presentation, and the tests are what keep it that way.

Two claims are being defended here, and they fail differently:

  * **completeness** — every customer-facing string exists in both languages, and the Persian
    build does not leak untranslated English. A half-translated screen reads as broken rather
    than as English, which is worse than not offering the language at all.
  * **invariance** — switching language cannot move a figure, a ranking, a count or a
    fingerprint. That is structural: both languages travel inside one bundle whose numbers were
    computed once, so a switch is a re-render. These tests assert the structure actually holds.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from event_sim.wedge.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    bundle_for,
    catalogue,
    chooser_bundle,
    missing_keys,
)
from event_sim.wedge.registry import WEDGES

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html"
CHOOSER = ROOT / "event_sim" / "wedge" / "templates" / "chooser.html"

#: Words that mean the Persian build is showing English it should not.
LEAKED_ENGLISH = re.compile(r"\b(the|your|and|price|cost|order|customer|business|assumption|"
                            r"decision|month|cash|ranked|tested|sensitivity|elasticity)\b", re.I)

#: `{cost}` is a slot, not a word: it is filled at render time with that wedge's own translated
#: term. Checking it for English would flag the machinery instead of the copy.
PLACEHOLDER = re.compile(r"\{\w+\}")


def prose(text: str) -> str:
    """The part of a string a reader actually sees as language."""
    return PLACEHOLDER.sub(" ", text)


#: Implementation vocabulary that must never reach customer copy in either language.
INTERNAL_TERMS = ("ai_hypothesis", "literature_backed", "expert_assumption", "user_assumption",
                  "WorldModule", "worldmodule", "elasticity coefficient", "causal graph",
                  "stock node", "relaxation", "intervention", "simulation engine",
                  "sensitivity grid", "evidence ladder", "fingerprint")


# ---- completeness ---------------------------------------------------------------------------

def test_every_language_has_every_key():
    result = missing_keys()
    for name, keys in result.items():
        assert keys == [], f"{name}: {keys[:12]}"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_no_string_is_left_empty(lang):
    empty = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and not node.strip():
            empty.append(path)

    walk(catalogue(lang))
    assert not empty, f"{lang} has empty strings: {empty}"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_persian_build_does_not_leak_english(wedge_id):
    """Every Persian string a customer reads must actually be Persian."""
    fa = catalogue("fa")["wedges"][wedge_id]
    leaks = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            # An icon or a bare letter is not language.
            if LEAKED_ENGLISH.search(prose(node)):
                leaks.append(f"{path}: {node[:70]}")

    walk(fa)
    assert not leaks, f"untranslated English in the Persian {wedge_id} copy:\n  " + "\n  ".join(leaks)


def test_the_persian_ui_does_not_leak_english():
    ui = catalogue("fa")["ui"]
    leaks = [f"{k}: {v[:70]}" for k, v in ui.items()
             if isinstance(v, str) and LEAKED_ENGLISH.search(prose(v))]
    assert not leaks, "untranslated English in the Persian interface:\n  " + "\n  ".join(leaks)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_no_internal_vocabulary_reaches_customer_copy(lang):
    blob = json.dumps(catalogue(lang), ensure_ascii=False).lower()
    found = [term for term in INTERNAL_TERMS if term.lower() in blob]
    assert not found, f"{lang} customer copy uses implementation vocabulary: {found}"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_intake_field_is_asked_as_a_question(wedge_id, lang):
    """The form should read like someone talking, not like a database schema."""
    wedge = WEDGES[wedge_id]
    text = catalogue(lang)["wedges"][wedge_id]["intake"]
    for field in wedge.intake_fields:
        key = field["key"]
        assert key in text, f"{lang}/{wedge_id}: no copy for intake field {key}"
        assert text[key]["label"].strip(), f"{lang}/{wedge_id}.{key}: empty label"
        assert text[key]["hint"].strip(), f"{lang}/{wedge_id}.{key}: empty hint"
        assert key not in text[key]["label"], (
            f"{lang}/{wedge_id}.{key}: the label is the field name, not a question")


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_swept_assumption_has_a_readable_name(wedge_id, lang):
    """The influence list is read by a customer; a raw key there is a bug."""
    wedge = WEDGES[wedge_id]
    labels = catalogue(lang)["wedges"][wedge_id]["sweep_labels"]
    for key in wedge.copy["grid_key_fields"]:
        assert key in labels, f"{lang}/{wedge_id}: no readable name for {key}"
        assert labels[key].strip()


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
@pytest.mark.parametrize("lang", LANGUAGES)
def test_each_wedge_names_its_three_choices_in_every_language(wedge_id, lang):
    text = catalogue(lang)["wedges"][wedge_id]
    for block in ("world_names", "world_short", "world_verdict_labels"):
        assert set(text[block]) == {"A", "B", "C"}, f"{lang}/{wedge_id}.{block}"
        for v in text[block].values():
            assert v.strip()


# ---- invariance -----------------------------------------------------------------------------

@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_catalogue_holds_no_model_values(wedge_id):
    """
    A number that differs between languages would be a model value hiding in a translation.

    Digits in copy are fine — "10%" is part of a decision's name — but the DIGITS THEMSELVES
    must match once Persian numerals are folded back to Latin, or the two languages are
    describing different decisions.
    """
    def digits(node):
        blob = json.dumps(node, ensure_ascii=False)
        blob = blob.translate({0x06F0 + i: str(i) for i in range(10)})
        blob = blob.translate({0x0660 + i: str(i) for i in range(10)})
        return sorted(re.findall(r"\d+(?:\.\d+)?", blob))

    en = catalogue("en")["wedges"][wedge_id]
    fa = catalogue("fa")["wedges"][wedge_id]
    for block in ("world_names", "world_short", "world_verdict_labels"):
        assert digits(en[block]) == digits(fa[block]), (
            f"{wedge_id}.{block}: the two languages name different numbers")


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_switching_language_cannot_touch_the_numbers(wedge_id):
    """
    The structural guarantee: one bundle, computed once, carrying every language.

    There is no per-language computation to disagree, and nothing under `i18n` is read by the
    arithmetic. This asserts both halves.
    """
    bundle = bundle_for(wedge_id)
    assert set(bundle["strings"]) == set(LANGUAGES)
    # No language block may contain anything the arithmetic reads.
    for lang, block in bundle["strings"].items():
        assert set(block) <= {"dir", "label", "numerals", "ui", "wedge", "all_wedges"}, lang
    # The structural copy (which the arithmetic DOES read) is not per-language at all.
    wedge = WEDGES[wedge_id]
    structural = {k for k, v in wedge.copy.items() if not callable(v)}
    for key in ("fields", "grid_key_fields", "summary_fields", "research_settings",
                "primary_axis", "sens_values"):
        assert key in structural, f"{wedge_id}: {key} must stay outside the catalogues"
    for lang in LANGUAGES:
        assert not (set(catalogue(lang)["wedges"][wedge_id]) & {"fields", "grid_key_fields",
                    "summary_fields", "research_settings", "primary_axis", "sens_values"}), (
            f"{lang}/{wedge_id}: structure leaked into a translation")


def test_both_directions_are_declared():
    assert catalogue("en")["dir"] == "ltr"
    assert catalogue("fa")["dir"] == "rtl"
    for entry in bundle_for("cafe")["languages"]:
        assert entry["dir"] in ("ltr", "rtl")


# ---- the pages actually use the layer -------------------------------------------------------

def test_the_report_page_reads_every_string_from_the_catalogue():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "D.i18n" in html, "the page must take its strings from the bundle"
    assert "localStorage.setItem('dc_lang'" in html, "the language choice must persist"
    assert "document.documentElement.dir = L.dir" in html, "direction must follow the language"
    assert "navigator.languages" in html, "the browser's language is a reasonable default"
    # Nothing user-visible should be hard-coded in the markup.
    body = html.split("<body>", 1)[1].split("<script", 1)[0]
    text = re.sub(r"<[^>]+>", " ", body)
    words = [x for x in re.findall(r"[A-Za-z]{4,}", text) if x.lower() not in ("business",)]
    assert not words, f"hard-coded English in the page body: {words[:10]}"


def test_the_home_screen_reads_every_string_from_the_catalogue():
    html = CHOOSER.read_text(encoding="utf-8")
    assert "__I18N__" in html, "the chooser must be filled from the catalogue"
    body = html.split("<body>", 1)[1].split("<script", 1)[0]
    text = re.sub(r"<[^>]+>", " ", body)
    words = re.findall(r"[A-Za-z]{4,}", text)
    assert not words, f"hard-coded English on the home screen: {words[:10]}"


def test_the_home_screen_offers_all_three_businesses_in_both_languages():
    bundle = chooser_bundle()
    for lang in LANGUAGES:
        wedges = bundle["strings"][lang]["wedges"]
        assert set(wedges) == set(WEDGES)
        for wid, x in wedges.items():
            assert x["business"].strip() and x["question"].strip() and x["icon"].strip()
            assert x["question"].rstrip().endswith("?") or x["question"].rstrip().endswith("؟"), (
                f"{lang}/{wid}: the chooser should ask a question")


# ---- the evidence registry is copy too -------------------------------------------------------

def _registry(wedge):
    return wedge.build_registry(wedge.demo_factory(), axis_settings=dict(wedge.default_axes),
                                custom_elasticity=None, **wedge.knob_defaults)


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_assumption_row_is_named_in_every_language(wedge_id, lang):
    """A row of the evidence table is read by a customer; English there is a bug."""
    text = catalogue(lang)["wedges"][wedge_id]["assumptions"]
    for a in _registry(WEDGES[wedge_id]):
        assert a.key in text, f"{lang}/{wedge_id}: no copy for assumption {a.key}"
        assert text[a.key]["label"].strip()


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_translated_assumption_values_keep_the_same_slots(wedge_id):
    """
    A value's words are translated; the figures it shows are not.

    Each prose value is a pattern with slots the page fills from the model's own numbers, so a
    translation that dropped, renamed or invented a slot would be showing a different quantity.
    """
    slots = re.compile(r"\{(\w+)(?::[^}]*)?\}")
    en = catalogue("en")["wedges"][wedge_id]["assumptions"]
    fa = catalogue("fa")["wedges"][wedge_id]["assumptions"]
    for key, row in en.items():
        assert set(row) == set(fa[key]), f"{wedge_id}.{key}: the two languages carry different parts"
        if "text" in row:
            assert sorted(slots.findall(row["text"])) == sorted(slots.findall(fa[key]["text"])), (
                f"{wedge_id}.{key}: the Persian value fills different slots")
        if "map" in row:
            assert set(row["map"]) == set(fa[key]["map"]), f"{wedge_id}.{key}: settings differ"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_translated_assumption_values_state_the_same_numbers(wedge_id):
    """Any digit written into the copy itself must survive the translation unchanged."""
    def digits(node):
        blob = json.dumps(node, ensure_ascii=False)
        blob = blob.translate({0x06F0 + i: str(i) for i in range(10)})
        # Format specifiers are machinery, not quantities.
        blob = re.sub(r"\{\w+:[^}]*\}", " ", blob)
        return sorted(re.findall(r"\d+(?:\.\d+)?", blob))

    en = catalogue("en")["wedges"][wedge_id]["assumptions"]
    fa = catalogue("fa")["wedges"][wedge_id]["assumptions"]
    for key, row in en.items():
        for part in ("text", "map"):
            if part in row:
                assert digits(row[part]) == digits(fa[key][part]), (
                    f"{wedge_id}.{key}.{part}: the two languages state different numbers")


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_page_can_rebuild_every_value_it_is_shown(wedge_id):
    """
    The page re-renders values rather than recomputing them, so each row must carry both how it
    was built and the figures it was built from. A row missing either would silently fall back
    to the English string the generator produced.
    """
    known = {"literal", "money", "money_with_pct", "g", "fixed", "axis", "template"}
    for a in _registry(WEDGES[wedge_id]):
        spec = a.value_spec
        assert spec and spec["kind"] in known, f"{wedge_id}.{a.key}: unrenderable value"
        assert a.value_ctx is not None
        if spec["kind"] == "axis":
            assert a.value_ctx["setting"] in spec["map"], f"{wedge_id}.{a.key}"
        for field in ("field", "pct_of"):
            if field in spec:
                assert spec[field] in a.value_ctx, f"{wedge_id}.{a.key}: {spec[field]} not carried"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_persian_evidence_table_does_not_leak_english(wedge_id):
    fa = catalogue("fa")["wedges"][wedge_id]["assumptions"]
    leaks = []
    for key, row in fa.items():
        for part, value in row.items():
            for text in ([value] if isinstance(value, str) else list(value.values())):
                if LEAKED_ENGLISH.search(prose(text)):
                    leaks.append(f"{key}.{part}: {text[:60]}")
    assert not leaks, f"untranslated English in the Persian {wedge_id} evidence:\n  " + "\n  ".join(leaks)


def test_the_evidence_classes_are_named_in_every_language():
    """`Assumption` is an internal token; the customer sees a phrase in their own language."""
    from event_sim.wedge.evidence import ASSUMPTION, CUSTOMER, DERIVED, RESEARCH
    for lang in LANGUAGES:
        labels = catalogue(lang)["ui"]["klass_labels"]
        for klass in (CUSTOMER, RESEARCH, ASSUMPTION, DERIVED):
            assert labels.get(klass, "").strip(), f"{lang}: no name for the {klass} class"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_swept_setting_is_named_in_every_language(lang):
    """The advanced controls offer settings by name; `central` is not a name."""
    labels = catalogue(lang)["ui"]["setting_labels"]
    seen = set()
    for wedge in WEDGES.values():
        for a in _registry(wedge):
            if a.value_spec and a.value_spec["kind"] == "axis":
                seen.add(a.value_ctx["setting"])
    seen |= {"low", "central", "high", "slow", "fast"}
    for setting in sorted(seen):
        assert labels.get(setting, "").strip(), f"{lang}: no name for the {setting} setting"


# ---- the generated explanation has to read like a sentence ------------------------------------

#: Words that continue a sentence. A paragraph opening with one is answering a clause that was
#: never written — which is what happens when a branch pushes only its second half.
CONTINUATIONS = {
    "en": ("and", "but", "so", "then", "however", "though", "because"),
    "fa": ("و", "اما", "پس", "ولی", "چون", "بنابراین"),
}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_explanation_never_opens_mid_sentence(lang):
    """
    Every clause the explanation can start with must be able to start one.

    `whyText` composes a paragraph from an opening clause and a continuation. The opening
    clauses are the ones the page may put first; if any of them is a continuation, some real
    combination of results produces a fragment — and it will be the combination where demand
    behaved unusually, which is exactly when a reader is looking closely.
    """
    ui = catalogue(lang)["ui"]
    openers = ("why_lose_units", "why_demand_grows", "why_demand_holds")
    for key in openers:
        first = prose(ui[key]).strip().split()[0].strip(",،").lower()
        assert first not in CONTINUATIONS[lang], (
            f"{lang}/{key} opens with {first!r}, so it cannot start the explanation")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_clause_the_explanation_uses_exists(lang):
    ui = catalogue(lang)["ui"]
    for key in ("why_lose_units", "why_demand_grows", "why_demand_holds", "why_gain",
                "why_gain_capacity", "why_capacity_full", "why_price_through", "why_cost",
                "why_vs_a", "why_gap"):
        assert ui.get(key, "").strip(), f"{lang}: {key} is missing"


def test_the_page_picks_an_opening_clause_for_every_way_demand_can_move():
    """Falling, flat and rising demand each need their own opening, or one of them fragments."""
    html = TEMPLATE.read_text(encoding="utf-8")
    why = html[html.index("function whyText"):]
    why = why[:why.index("\n}")]
    for key in ("why_lose_units", "why_demand_grows", "why_demand_holds"):
        assert key in why, f"whyText never uses {key}"
