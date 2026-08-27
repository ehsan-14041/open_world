"""
What a reader actually ends up looking at.

Every other test here reads the template or the catalogue. This one runs the page — headless
Chrome executes the script, and the DOM that comes back is the one a customer sees. That is the
only way to check the things that are only true after rendering: that the verdict sentence was
written from this run's ranking, that the badge landed on the option that actually leads, and
that the honesty copy survived the trip from catalogue to screen.

The wording of the honesty blocks is asserted verbatim and in both languages. It is the part of
the page that a redesign is most likely to quietly tidy away, so it is the part pinned hardest.
"""

from __future__ import annotations

import html as html_mod
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from event_sim.wedge.i18n import LANGUAGES, catalogue
from event_sim.wedge.registry import WEDGES

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "reports" / "demo_site"

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _chrome() -> str | None:
    for name in ("google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_CANDIDATES:
        if Path(path).is_file():
            return path
    return None


CHROME = _chrome()

pytestmark = pytest.mark.skipif(
    CHROME is None or not (SITE / "index.html").is_file(),
    reason="needs Chrome and a built demo site (scripts/build_demo_site.py)",
)

_CACHE: dict[tuple[str, str], str] = {}


def rendered(wedge_id: str, lang: str) -> str:
    """The page's DOM after its own script has run, with the script bodies stripped."""
    key = (wedge_id, lang)
    if key not in _CACHE:
        page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=9000", "--dump-dom",
             page.as_uri() + f"?lang={lang}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        assert proc.returncode == 0, proc.stderr[-800:]
        dom = proc.stdout
        # The script tags still hold the source and the data payload; neither is what a reader
        # sees, and both would satisfy a text search by accident.
        dom = re.sub(r"<script.*?</script>", " ", dom, flags=re.S)
        # Stylesheet text is not page text either, and it is full of words.
        dom = re.sub(r"<style.*?</style>", " ", dom, flags=re.S)
        assert len(dom) > 5000, f"{wedge_id}/{lang}: page did not render"
        _CACHE[key] = dom
    return _CACHE[key]


def text_of(dom: str) -> str:
    """Visible text, tags removed and entities resolved."""
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", dom))


def inner(dom: str, element_id: str) -> str:
    """The visible text of one element, including anything marked up inside it."""
    start = re.search(rf'<(\w+)[^>]*\bid="{element_id}"[^>]*>', dom)
    if not start:
        return ""
    tag, pos, depth = start.group(1), start.end(), 1
    for m in re.finditer(rf"</?{tag}\b[^>]*>", dom[pos:]):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth == 0:
            body = dom[pos:pos + m.start()]
            return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", body)).split())
    return ""


ALL = [(w, lang) for w in sorted(WEDGES) for lang in LANGUAGES]
IDS = [f"{w}-{lang}" for w, lang in ALL]


# ---- the page finished drawing ---------------------------------------------------------------

@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_page_renders_without_announcing_a_failure(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    banner = re.search(r'id="banner"[^>]*class="([^"]*)"', dom) or \
             re.search(r'class="banner([^"]*)"[^>]*id="banner"', dom)
    assert "on" not in (banner.group(1).split() if banner else []), \
        "the page put its own failure banner up"


# ---- the verdict, and the badge that agrees with it -------------------------------------------

@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_verdict_sentence_is_written_and_names_an_option(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    verdict = inner(dom, "verdict")
    assert verdict, f"{wedge_id}/{lang}: no verdict sentence"
    names = catalogue(lang)["wedges"][wedge_id]["world_short"]
    assert any(n in verdict for n in names.values()), \
        f"{wedge_id}/{lang}: the verdict names no option — {verdict!r}"
    # It must stay hedged: the sentence says what is true under the stated assumptions.
    hedge = catalogue(lang)["ui"]["verdict"].split("—")[-1].strip(" .")
    assert hedge and hedge in verdict, f"{wedge_id}/{lang}: the verdict dropped its qualifier"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_exactly_one_card_carries_the_winner_badge(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    badges = re.findall(r'class="lead-tag"[^>]*>(.*?)</div>', dom, re.S)
    assert len(badges) == 1, f"{wedge_id}/{lang}: {len(badges)} winner badges"
    assert catalogue(lang)["ui"]["best_badge"] in html_mod.unescape(badges[0])
    leads = re.findall(r'class="opt [^"]*\blead\b[^"]*"', dom)
    assert len(leads) == 1, f"{wedge_id}/{lang}: {len(leads)} cards marked as leading"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_badge_is_on_the_option_the_verdict_names(wedge_id, lang):
    """A badge on one card and a sentence naming another would be the worst of both."""
    dom = rendered(wedge_id, lang)
    card = re.search(r'<article class="opt [^"]*\blead\b[^"]*".*?</article>', dom, re.S)
    assert card, f"{wedge_id}/{lang}: no leading card"
    name = re.search(r'class="name">(.*?)</h3>', card.group(0), re.S)
    assert name, "the leading card has no name"
    full = html_mod.unescape(name.group(1)).strip()
    verdict = inner(dom, "verdict")
    short = catalogue(lang)["wedges"][wedge_id]["world_short"]
    letter = [k for k, v in catalogue(lang)["wedges"][wedge_id]["world_names"].items()
              if v.strip() == full]
    assert letter, f"{wedge_id}/{lang}: leading card {full!r} is not one of the three options"
    assert short[letter[0]] in verdict, (
        f"{wedge_id}/{lang}: badge is on {full!r} but the verdict says {verdict!r}")


# ---- the honesty copy, verbatim ---------------------------------------------------------------

@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_honesty_blocks_are_on_the_page(wedge_id, lang):
    """
    These are the sentences that stop the page overselling itself, so they are checked as
    strings rather than by intent. Rewording one is a decision, not a refactor.
    """
    dom = rendered(wedge_id, lang)
    body = text_of(dom)
    ui = catalogue(lang)["ui"]
    wedge = catalogue(lang)["wedges"][wedge_id]

    must = [
        ("what this is not", ui["not_a_prediction"]),
        ("cash is derived", ui["cash_derived"]),
        ("what it does", ui["does_title"]),
        ("what it does not do", ui["does_not"]),
        ("the count is not odds", ui["tested_cases_tooltip"]),
    ]
    for label, sentence in must:
        assert " ".join(sentence.split()) in " ".join(body.split()), \
            f"{wedge_id}/{lang}: missing the {label} line — {sentence!r}"

    # Every "this does not" item survives, not just the heading.
    for line in wedge["limits_does_not"]:
        assert " ".join(line.split()) in " ".join(body.split()), \
            f"{wedge_id}/{lang}: dropped a limitation — {line!r}"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_page_says_when_no_study_backs_the_setting(wedge_id, lang):
    """
    At a setting no study supports the page has to say so, in those words.

    The demo sits at the central setting, so which of the two sentences applies depends on the
    wedge; one of them must be there either way.
    """
    dom = rendered(wedge_id, lang)
    body = " ".join(text_of(dom).split())
    ui = catalogue(lang)["ui"]
    research_group = re.search(r'class="grp research"(.*?)</details>', dom, re.S)
    assert research_group, f"{wedge_id}/{lang}: no external-research group"
    said = " ".join(ui["no_research"].split()) in body or \
           " ".join(ui["no_research_ever"].split()) in body
    backed = bool(re.search(r"<li", research_group.group(1)))
    assert said or backed, (
        f"{wedge_id}/{lang}: the research group is empty and the page does not say why")


# ---- the evidence grouping survived the redesign ----------------------------------------------

@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_all_four_evidence_groups_are_present_and_labelled(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    ui = catalogue(lang)["ui"]
    for cls, key in (("yours", "group_yours"), ("research", "group_research"),
                     ("assume", "group_assumptions"), ("calc", "group_calculated")):
        block = re.search(rf'class="grp {cls}"(.*?)</details>', dom, re.S)
        assert block, f"{wedge_id}/{lang}: no {cls} group"
        assert ui[key] in html_mod.unescape(block.group(1)), \
            f"{wedge_id}/{lang}: the {cls} group lost its label"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_every_number_the_owner_typed_is_shown_with_the_question_that_asked_for_it(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    block = re.search(r'class="grp yours"(.*?)</details>', dom, re.S)
    assert block
    shown = html_mod.unescape(re.sub(r"<[^>]+>", " ", block.group(1)))
    intake = catalogue(lang)["wedges"][wedge_id]["intake"]
    labels = [v["label"] for v in intake.values()]
    hits = sum(1 for lbl in labels if " ".join(lbl.split()) in " ".join(shown.split()))
    assert hits >= 5, f"{wedge_id}/{lang}: only {hits} intake questions labelled the figures"


# ---- the controls still work as controls ------------------------------------------------------

@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_sensitivity_control_offers_three_settings_with_one_chosen(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    seg = re.search(r'id="seg"(.*?)</div>', dom, re.S)
    assert seg, f"{wedge_id}/{lang}: no sensitivity control"
    buttons = re.findall(r'data-v="(\w+)"[^>]*aria-pressed="(\w+)"', seg.group(1))
    assert [b[0] for b in buttons] == ["low", "central", "high"], buttons
    assert [b[1] for b in buttons].count("true") == 1, "exactly one setting is the current one"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_demo_says_it_is_a_demo(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    flag = re.search(r'id="demoflag"([^>]*)>(.*?)</span>', dom, re.S)
    assert flag, f"{wedge_id}/{lang}: no demo flag"
    assert "hidden" not in flag.group(1), "the demo report must admit it is a demo"
    assert html_mod.unescape(flag.group(2)).strip(), "the demo flag is empty"
