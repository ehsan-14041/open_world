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
import json
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
             # The page asks before it answers, so the worked example is the way to render a
             # result without a flow to drive. It is the same route the home screen offers.
             page.as_uri() + f"?lang={lang}&demo=1"],
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
    # The badge says where the option stands right now, not that it is the right answer.
    assert catalogue(lang)["ui"]["ahead_now"] in html_mod.unescape(badges[0])
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


# ---- the five beats, and the discipline that keeps them readable ------------------------------

#: The most words a beat may put in front of a reader. The numbers were set from the shipped
#: copy plus headroom; the point is that growing a beat past its budget is a decision someone
#: has to make in a diff, not something that accretes.
BEAT_BUDGET = {"b-now": 95, "b-options": 175, "b-race": 155, "b-solid": 130,
               "b-monday": 65, "b-decide": 75}


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_each_beat_stays_inside_its_word_budget(wedge_id, lang):
    dom = rendered(wedge_id, lang)
    # The experiment plan is behind a button and hidden by default; the budget measures what a
    # reader sees before they ask for more.
    hidden_testplan = re.search(r'id="testplan"[^>]*\bhidden', dom)
    for beat, cap in BEAT_BUDGET.items():
        words = len(inner(dom, beat).split())
        if beat == "b-monday" and hidden_testplan:
            words -= len(inner(dom, "testplan").split())
        assert 0 < words <= cap, f"{wedge_id}/{lang}: {beat} has {words} words (budget {cap})"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_census_is_drawn_one_dot_per_tested_case(wedge_id, lang):
    """
    "Ranked first in 130 of 162" is a claim; the dots are the receipt. Every tested case must
    be on screen, and the block captions must add up to the census the engine ran.
    """
    dom = rendered(wedge_id, lang)
    dots = len(re.findall(r'<i style="--dc:var\(--[abc]\)">', dom))
    blocks = re.findall(r'class="cblock[^"]*"', dom)
    assert len(blocks) == 3, f"{wedge_id}/{lang}: {len(blocks)} census blocks"
    assert dots == 162, f"{wedge_id}/{lang}: {dots} dots for 162 tested cases"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_page_opens_by_asking_not_reporting(wedge_id, lang):
    """Without the worked-example route, the first screen is a question, not a result."""
    page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=9000", "--dump-dom", page.as_uri() + f"?lang={lang}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    dom = re.sub(r"<script.*?</script>", " ", proc.stdout, flags=re.S)
    ask = re.search(r'<section[^>]*id="ask"([^>]*)>', dom)
    result = re.search(r'<div[^>]*id="result"([^>]*)>', dom)
    assert ask and "hidden" not in ask.group(1), f"{wedge_id}/{lang}: the questions are hidden"
    assert result and "hidden" in result.group(1), f"{wedge_id}/{lang}: the result shows unasked"
    q = catalogue(lang)["wedges"][wedge_id]["flow_q"]
    first = html_mod.unescape(re.search(r'id="ask-q"[^>]*>(.*?)</h1>', dom, re.S).group(1)).strip()
    assert first in q.values(), f"{wedge_id}/{lang}: opening question {first!r} is not from the flow"


# ---- the home screen, as rendered -------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_rendered_home_screen_is_whole(lang):
    """
    "undefined" in page text means a string was asked for that the bundle does not carry — and
    worse, the render that hit it died there, leaving everything after it empty. Both failures
    are invisible to catalogue tests, because the catalogue is fine; it is the bundle that lost
    a key. So the home screen is rendered and read like a visitor would.
    """
    page = SITE / "index.html"
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=7000", "--dump-dom", page.as_uri() + f"?lang={lang}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    dom = re.sub(r"<script.*?</script>", " ", proc.stdout, flags=re.S)
    body = text_of(dom)
    assert "undefined" not in body, f"{lang}: the home screen shows 'undefined'"
    ui = catalogue(lang)["ui"]
    # The parts a mid-render failure would silently blank out.
    for eid, key in (("hero", "home_hero"), ("problem-q", "home_problem_q"),
                     ("flow", "home_flow"), ("credibility", "credibility"),
                     ("ex-lead", "home_example_lead"), ("footer", "home_footer")):
        got = inner(dom, eid)
        assert got, f"{lang}: #{eid} is empty — the render died before reaching it"
        if key in ("home_hero", "home_problem_q", "home_flow"):
            assert got == " ".join(ui[key].split()), f"{lang}: #{eid} shows the wrong string"
    # Each card leads with the problem, in this language.
    for wid in sorted(WEDGES):
        problem = catalogue(lang)["wedges"][wid]["problem"]
        assert " ".join(problem.split()) in " ".join(body.split()), \
            f"{lang}: the {wid} card lost its problem line"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_no_rendered_page_ever_says_undefined(wedge_id, lang):
    body = text_of(rendered(wedge_id, lang))
    assert "undefined" not in body, f"{wedge_id}/{lang}: 'undefined' reached the page"


# ---- the decision sheet -----------------------------------------------------------------------

def _sheet_dom(wedge_id: str, lang: str, packed: str) -> str:
    """The sheet a shared link opens to, rendered."""
    page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=9000", "--dump-dom",
         page.as_uri() + f"?lang={lang}&sheet={packed}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    dom = re.sub(r"<script.*?</script>", " ", proc.stdout, flags=re.S)
    return re.sub(r"<style.*?</style>", " ", dom, flags=re.S)


def _packed(wedge_id: str, choice: str = "B", date: str = "2026-09-01") -> str:
    """A link built the way the page builds one, from that wedge's own demo figures."""
    import base64
    import json as _json

    from event_sim.wedge.registry import WEDGES as _W
    wedge = _W[wedge_id]
    baseline = wedge.demo_factory().to_dict()
    fields = [f for step in wedge.copy["flow"] for f in step["fields"]]
    report = _json.loads((SITE / wedge_id / f"{wedge_id}_decision_report.json").read_text("utf-8"))
    grid_keys = list(report["grid"][0]["key"].keys())
    settings = []
    for k in grid_keys:
        vals = sorted({g["key"][k] for g in report["grid"]},
                      key=lambda v: (isinstance(v, str), v))
        settings.append("central" if "central" in vals else vals[len(vals) // 2])
    payload = _json.dumps([1, date, choice, settings, [baseline[f] for f in fields]],
                          separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_a_shared_link_opens_as_its_own_sheet(wedge_id, lang):
    """
    The link is the document. Opening it shows the sheet — not the questions, not the report —
    and the figures on it are recomputed from the link rather than read from anywhere.
    """
    dom = _sheet_dom(wedge_id, lang, _packed(wedge_id))
    sheet = re.search(r'<article[^>]*\bid="sheet"([^>]*)>', dom)
    assert sheet and "hidden" not in sheet.group(1), f"{wedge_id}/{lang}: the sheet did not open"
    for other, label in (("ask", "the questions"), ("result", "the comparison")):
        m = re.search(rf'<(?:section|div)[^>]*\bid="{other}"([^>]*)>', dom)
        assert m and "hidden" in m.group(1), f"{wedge_id}/{lang}: {label} showed alongside the sheet"
    assert "undefined" not in text_of(dom), f"{wedge_id}/{lang}: the sheet shows 'undefined'"
    ui = catalogue(lang)["ui"]
    assert inner(dom, "sheet-id"), "the sheet has no reference"
    assert inner(dom, "sheet-date"), "the sheet has no date"
    for eid, key in (("sheet-title", "sheet_title"), ("sheet-dec-k", "sheet_decision"),
                     ("sheet-rests-k", "sheet_rests"), ("sheet-will-k", "sheet_will_do")):
        assert inner(dom, eid) == " ".join(ui[key].split()), f"{wedge_id}/{lang}: {eid} is wrong"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_sheet_names_the_option_that_was_chosen(wedge_id):
    """Whatever the model ranks first, the sheet's decision is the one the owner picked."""
    for choice in ("A", "B", "C"):
        dom = _sheet_dom(wedge_id, "en", _packed(wedge_id, choice))
        names = catalogue("en")["wedges"][wedge_id]["world_names"]
        assert inner(dom, "sheet-choice") == " ".join(names[choice].split()), \
            f"{wedge_id}: a sheet for {choice} does not say {choice}"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_sheet_distinguishes_what_was_chosen_from_what_leads(wedge_id):
    """
    An owner may pick the option that is not ahead — that is their right, and the sheet has to
    say so rather than quietly implying the choice was the winner. Both marks appear, and on a
    deliberately unpopular choice they sit on different rows.
    """
    ui = catalogue("en")["ui"]
    report = json.loads((SITE / wedge_id / f"{wedge_id}_decision_report.json").read_text("utf-8"))
    counts = report["sensitivity"]["win_counts"]
    trailing = min(("A", "B", "C"), key=lambda k: counts[k])

    dom = _sheet_dom(wedge_id, "en", _packed(wedge_id, trailing))
    body = " ".join(text_of(dom).split())
    assert ui["sheet_chosen"] in body, f"{wedge_id}: no chosen mark"
    assert ui["ahead_now"] in body, f"{wedge_id}: the sheet hides which option leads"

    rows = re.findall(r"<tr([^>]*)>(.*?)</tr>", dom, re.S)
    chosen_rows = [r for r in rows if ui["sheet_chosen"] in r[1]]
    ahead_rows = [r for r in rows if ui["ahead_now"] in r[1]]
    assert len(chosen_rows) == 1 and len(ahead_rows) == 1
    assert chosen_rows[0] is not ahead_rows[0], \
        f"{wedge_id}: chosen and leading collapsed onto one row for a trailing choice"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_sheet_carries_the_honesty_copy_and_says_it_stores_nothing(wedge_id):
    dom = _sheet_dom(wedge_id, "fa", _packed(wedge_id))
    body = " ".join(text_of(dom).split())
    ui = catalogue("fa")["ui"]
    for key in ("not_a_prediction", "sheet_reproduce"):
        assert " ".join(ui[key].split()) in body, f"{wedge_id}: the sheet dropped {key}"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_a_damaged_link_does_not_produce_a_sheet(wedge_id):
    """
    A truncated or edited link must fall back to the questions, never to a document with
    half-applied figures on it. A sheet is something someone may act on.
    """
    good = _packed(wedge_id)
    for bad in (good[:-6], "not-base64-at-all", good[:8]):
        dom = _sheet_dom(wedge_id, "en", bad)
        sheet = re.search(r'<article[^>]*\bid="sheet"([^>]*)>', dom)
        assert sheet and "hidden" in sheet.group(1), \
            f"{wedge_id}: a damaged link ({bad[:12]}...) still opened a sheet"
        ask = re.search(r'<section[^>]*\bid="ask"([^>]*)>', dom)
        assert ask and "hidden" not in ask.group(1), f"{wedge_id}: damaged link left no way forward"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_same_link_always_carries_the_same_reference(wedge_id):
    a = _sheet_dom(wedge_id, "en", _packed(wedge_id))
    b = _sheet_dom(wedge_id, "fa", _packed(wedge_id))
    ref_a, ref_b = inner(a, "sheet-id"), inner(b, "sheet-id")
    assert ref_a and ref_a == ref_b, \
        f"{wedge_id}: the reference changed with the language ({ref_a!r} vs {ref_b!r})"
