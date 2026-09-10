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
TEMPLATE = ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html"

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
#: b-own was measured at 136 words at most (shop, English, an option none of the three uses).
BEAT_BUDGET = {"b-now": 95, "b-options": 175, "b-own": 155, "b-race": 155, "b-solid": 130,
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
    # A wedge with trades sharing its model opens by asking which one; the rest open on a figure.
    opening = set(q.values()) | {catalogue(lang)["ui"]["flow_kind_q"]}
    assert first in opening, f"{wedge_id}/{lang}: opening question {first!r} is not from the flow"


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


# ---- the experiment loop ----------------------------------------------------------------------

def _packed_measured(wedge_id: str, e: float, choice: str = "B",
                     band: str = "low", date: str = "2026-09-07") -> str:
    """A link from an owner who ran the test and reported what it said."""
    import base64
    import json as _json

    from event_sim.wedge.registry import WEDGES as _W
    wedge = _W[wedge_id]
    baseline = wedge.demo_factory().to_dict()
    fields = [f for step in wedge.copy["flow"] for f in step["fields"]]
    report = _json.loads((SITE / wedge_id / f"{wedge_id}_decision_report.json").read_text("utf-8"))
    grid_keys = list(report["grid"][0]["key"].keys())
    primary = report["copy"]["primary_axis"]
    settings = []
    for k in grid_keys:
        if k == primary:
            settings.append(band)
            continue
        vals = sorted({g["key"][k] for g in report["grid"]},
                      key=lambda v: (isinstance(v, str), v))
        settings.append("central" if "central" in vals else vals[len(vals) // 2])
    payload = _json.dumps([1, date, choice, settings, [baseline[f] for f in fields],
                           [e, 10, date]], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_a_measured_sheet_records_what_the_owner_measured(wedge_id, lang):
    dom = _sheet_dom(wedge_id, lang, _packed_measured(wedge_id, 0.5))
    ui = catalogue(lang)["ui"]
    sec = re.search(r'<section[^>]*\bid="sheet-meas-sec"([^>]*)>', dom)
    assert sec and "hidden" not in sec.group(1), f"{wedge_id}/{lang}: the sheet hides the measurement"
    assert inner(dom, "sheet-meas-k") == " ".join(ui["sheet_measured"].split())
    assert inner(dom, "sheet-meas"), "the measurement line is empty"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_a_sheet_without_a_measurement_does_not_claim_one(wedge_id):
    dom = _sheet_dom(wedge_id, "en", _packed(wedge_id))
    sec = re.search(r'<section[^>]*\bid="sheet-meas-sec"([^>]*)>', dom)
    assert sec and "hidden" in sec.group(1), f"{wedge_id}: an unmeasured sheet shows a measurement"


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_page_never_claims_to_have_simulated_the_exact_measurement(wedge_id):
    """
    The browser carries 162 precomputed worlds at three settings, not the engine. A measured
    elasticity is shown exactly and the comparison is run at the nearest setting that was
    actually tested — and the page has to say which one, or it is implying a run that never
    happened.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "function bandFor" in html, "nothing maps a measurement onto the tested settings"
    for lang in LANGUAGES:
        band = catalogue(lang)["ui"]["measured_band"]
        assert "{band}" in band, f"{lang}: the page does not name the setting it ran"
        caveat = catalogue(lang)["ui"]["measured_caveat"]
        assert caveat.strip(), f"{lang}: the measurement carries no caveat about what it covers"


def test_the_measurement_is_arithmetic_the_owner_could_check():
    """
    Share of custom lost over share the price moved — nothing else. Demand that did not fall
    reads as zero rather than as a negative elasticity, because "they did not leave" is a real
    outcome of the test and not an error in it.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    body = html[html.index("function elasticityFrom"):]
    body = body[:body.index("\n}")]
    assert "(before - after) / before" in body, "the formula is not the one the owner would use"
    assert "risePct / 100" in body
    assert "Math.max(0," in body, "a test where nobody left must read as zero, not as a negative"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_measurement_is_the_owners_number_not_a_model_assumption(lang):
    """
    The engine reclassifies a supplied elasticity as customer input rather than expert
    assumption (render_registry in event_sim/wedge/evidence.py). The page has to agree with it
    about whose number it is, or the evidence table would credit the model for the owner's work.
    """
    from event_sim.wedge.evidence import CUSTOMER, render_registry
    import inspect
    src = inspect.getsource(render_registry)
    assert "custom_elasticity is not None" in src, "the engine no longer accepts a supplied elasticity"
    assert "klass = CUSTOMER" in src, "the engine no longer reclassifies a supplied elasticity"
    assert CUSTOMER == "Customer input"

    html = TEMPLATE.read_text(encoding="utf-8")
    assert "yours.push([t('measured_row')" in html, \
        "a measured elasticity is not filed under the owner's own numbers"
    assert catalogue(lang)["ui"]["measured_row"].strip()


# ---- trades that share a model ----------------------------------------------------------------

def _packed_variant(wedge_id: str, variant: str | None, choice: str = "B") -> str:
    """A link identical in every figure, differing only in which trade it is written for."""
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
    body = [1, "2026-09-07", choice, settings, [baseline[f] for f in fields]]
    if variant:
        body.append(None)          # no measurement
        body.append(variant)
    payload = _json.dumps(body, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


VARIANT_CASES = [(v, lang) for v in ("bakery", "fastfood") for lang in LANGUAGES]
VARIANT_IDS = [f"{v}-{lang}" for v, lang in VARIANT_CASES]


@pytest.mark.parametrize("variant,lang", VARIANT_CASES, ids=VARIANT_IDS)
def test_a_variant_changes_the_words_and_not_one_figure(variant, lang):
    """
    A bakery and a cafe facing the same input-cost rise are the same question in different
    words. The variant carries no numbers, and this is what says so: two sheets built from
    identical figures, one written for the trade and one not, must agree on every number on
    the page and disagree on what the business is called.
    """
    plain = _sheet_dom("cafe", lang, _packed_variant("cafe", None))
    var = _sheet_dom("cafe", lang, _packed_variant("cafe", variant))

    def figures(dom):
        return re.findall(r"[-−+]?[\d٠-٩۰-۹][\d٠-٩۰-۹,،٬.٫]*", inner(dom, "sheet-cmp"))

    assert figures(plain) == figures(var), f"{variant}/{lang}: a variant moved a figure"

    names = catalogue(lang)["wedges"]["cafe"]
    over = names["variants"][variant]
    assert " ".join(over["business"].split()) in " ".join(text_of(var).split()), \
        f"{variant}/{lang}: the sheet does not name the trade"
    if "world_names" in over:
        assert inner(var, "sheet-choice") == " ".join(over["world_names"]["B"].split())
    else:
        assert inner(var, "sheet-choice") == " ".join(names["world_names"]["B"].split())


@pytest.mark.parametrize("variant,lang", VARIANT_CASES, ids=VARIANT_IDS)
def test_a_variant_says_how_far_the_research_had_to_travel(variant, lang):
    """
    The elasticity is borrowed from research on eating out. For a bakery selling a staple, and
    for a fast-food shop with a substitute on the next corner, that borrowing is a longer reach
    than it is for a cafe — and each variant has to say so in its own words rather than inherit
    a note written about somewhere else.
    """
    over = catalogue(lang)["wedges"]["cafe"]["variants"][variant]
    base_note = catalogue(lang)["wedges"]["cafe"]["sources_note"]
    assert "sources_note" in over, f"{variant}/{lang}: inherits the cafe's transfer note"
    assert over["sources_note"].strip() != base_note.strip()
    # And it is the variant's own note that the page would show, not the cafe's.
    assert over["sources_note"].strip(), f"{variant}/{lang}: empty transfer note"


@pytest.mark.parametrize("variant", ["bakery", "fastfood"])
def test_the_flow_asks_which_trade_before_anything_else(variant):
    """The trade is chosen in the flow, so a bakery owner never has to know a URL parameter."""
    from event_sim.wedge.registry import WEDGES as _W
    flow = _W["cafe"].copy["flow"]
    assert flow[0].get("variants") is True, "the cafe flow does not open by asking the trade"
    assert flow[0]["fields"] == [], "the trade question must not write a model input"
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "data-var=" in html, "the flow offers no way to pick a trade"
    for lang in LANGUAGES:
        assert catalogue(lang)["ui"]["flow_kind_q"].strip()
        assert variant in catalogue(lang)["wedges"]["cafe"]["variants"]


# ---- a figure that cannot be right, caught where it was typed ---------------------------------

DRIVER = """
<script>
/* Types an answer into every step and taps the first choice on the rest, then reports where the
   flow ended up. It is the only way to test the flow: the questions are the page's own script. */
setTimeout(function(){
  var vals = __VALS__, n = 0;
  var iv = setInterval(function(){
    n++;
    if(n > 12 || !document.getElementById('result').hidden){
      clearInterval(iv);
      var d = document.createElement('div');
      d.id = 'probe';
      d.setAttribute('data-result', document.getElementById('result').hidden ? 'no' : 'yes');
      d.setAttribute('data-err', document.getElementById('ask-err').textContent);
      d.setAttribute('data-bad', String(document.querySelectorAll('#ask-body input.bad').length));
      d.setAttribute('data-on', String(document.querySelectorAll('#ask-body input[data-k]').length
        ? document.querySelector('#ask-body input[data-k]').dataset.k : ''));
      document.body.appendChild(d);
      return;
    }
    var body = document.getElementById('ask-body');
    var ins = body.querySelectorAll('input[data-k]');
    if(ins.length){
      Array.prototype.forEach.call(ins, function(i){
        if(vals[i.dataset.k] !== undefined) i.value = vals[i.dataset.k]; });
      document.getElementById('ask-next').click();
    } else {
      var c = body.querySelector('.choice');
      if(c) c.click();
    }
  }, 250);
}, 400);
</script>
"""


def driven(wedge_id: str, lang: str, vals: dict, tmp_path) -> dict:
    """Run the page's own flow, answering with `vals`, and read the probe it leaves behind."""
    page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
    copy = tmp_path / "driven.html"
    body = page.read_text(encoding="utf-8")
    copy.write_text(
        body.replace("</body>", DRIVER.replace("__VALS__", json.dumps(vals)) + "</body>"),
        encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=12000", "--dump-dom", copy.as_uri() + f"?lang={lang}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, proc.stderr[-800:]
    m = re.search(r'<div id="probe"([^>]*)>', proc.stdout)
    assert m, "the flow never settled"
    return dict(re.findall(r'data-(\w+)="([^"]*)"', m.group(1)))


def _fields(wedge_id):
    return WEDGES[wedge_id].copy["fields"]


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_costs_above_sales_are_refused_on_the_screen_they_were_typed_on(wedge_id, lang, tmp_path):
    """
    Someone who enters a cost larger than their sales has made a mistake the page can name —
    most likely one of the two is not a monthly figure. Refusing at the last question, with a
    sentence that names neither number, leaves them with nowhere to go: "back" lands on a
    question that has nothing to do with what is wrong. So the refusal happens on the costs
    screen, with the figure still on it, and it says why.
    """
    F = _fields(wedge_id)
    vals = {F["revenue"]: 80000000, F["units_per_day"]: 60, F["unit_cost_total"]: 90000000,
            F["fixed"]: 20000000, F["cash"]: 15000000,
            F.get("low_margin", "_"): 20, F.get("utilisation", "_"): 70}
    probe = driven(wedge_id, lang, vals, tmp_path)
    ui = catalogue(lang)["ui"]
    assert probe["result"] == "no", "a comparison was drawn from figures that cannot be right"
    assert probe["on"] == F["unit_cost_total"], \
        f"stopped on {probe['on']!r}, not the screen the cost was typed on"
    assert ui["err_cost_high"].strip() in probe["err"], "the refusal does not state the rule"
    assert ui["err_cost_high_why"].strip() in probe["err"], \
        "the refusal does not say what to change"
    assert int(probe["bad"]) >= 1, "the figure at fault is not marked"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_figures_that_hold_together_reach_the_comparison(wedge_id, lang, tmp_path):
    """The same drive with a cost below sales must not be stopped by the new check."""
    F = _fields(wedge_id)
    vals = {F["revenue"]: 80000000, F["units_per_day"]: 60, F["unit_cost_total"]: 30000000,
            F["fixed"]: 20000000, F["cash"]: 15000000,
            F.get("low_margin", "_"): 20, F.get("utilisation", "_"): 70}
    probe = driven(wedge_id, lang, vals, tmp_path)
    assert probe["result"] == "yes", f"the flow refused good figures: {probe['err']!r}"


# ---- the owner's own option ----------------------------------------------------------------------

def page_with(wedge_id: str, lang: str, query: str) -> str:
    """The page opened on a URL of its own, scripts and styles stripped as in `rendered`."""
    page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=12000", "--dump-dom", page.as_uri() + f"?lang={lang}&{query}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, proc.stderr[-800:]
    dom = re.sub(r"<script.*?</script>", " ", proc.stdout, flags=re.S)
    return re.sub(r"<style.*?</style>", " ", dom, flags=re.S)


def _grid_size(wedge_id: str) -> int:
    data = json.loads((SITE / wedge_id / f"{wedge_id}_decision_report.json").read_text("utf-8"))
    return int(data.get("sensitivity", {}).get("n", 162))


def _card_money(dom: str, letter: str) -> str:
    m = re.search(r'<article class="opt w' + letter + r'\b[^"]*".*?<div class="money(?: neg)?"[^>]*>(.*?)</div>',
                  dom, re.S)
    assert m, f"no card for option {letter}"
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split())


def _price_rise(wedge_id: str, letter: str) -> float:
    assets = json.loads((ROOT / "deploy" / "php" / "assets" / f"{wedge_id}.json").read_text("utf-8"))
    return next(float(o["price_rise_pct"]) for o in assets["worlds"]["options"] if o["id"] == letter)


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_browser_rebuilds_every_precomputed_case_before_it_runs_one_of_its_own(wedge_id, lang):
    """
    The own option runs on a copy of the model in the reader's browser. It is only allowed to
    because that copy first rebuilt all three options at every tested case on the page and
    matched them — and the page states the result on its root for anyone to check.
    """
    dom = rendered(wedge_id, lang)
    root = re.search(r"<html\b[^>]*>", dom).group(0)
    assert 'data-engine="ok"' in root, f"{wedge_id}/{lang}: the browser model failed its check: {root}"
    checked = int(re.search(r'data-engine-checked="(\d+)"', root).group(1))
    assert checked == 3 * _grid_size(wedge_id), f"only {checked} cases were rebuilt"
    worst = float(re.search(r'data-engine-worst="([^"]+)"', root).group(1))
    assert worst <= 0.0101, f"worst disagreement {worst}"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_the_own_option_set_to_an_options_levers_gives_that_options_figure(wedge_id, lang):
    """It opens on the second option's lever, so the first thing it shows is the model agreeing
    with itself — and it only says "exactly the same" because the figure is."""
    dom = rendered(wedge_id, lang)
    assert not re.search(r'id="b-own"[^>]*\bhidden', dom), "the own-option beat is hidden"
    assert inner(dom, "own-money") == _card_money(dom, "B")
    short_b = catalogue(lang)["wedges"][wedge_id]["world_short"]["B"]
    assert catalogue(lang)["ui"]["own_same"].replace("{x}", short_b) in inner(dom, "own-vs")


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_own_option_with_the_third_options_levers_gives_its_figure(wedge_id):
    c = _price_rise(wedge_id, "C")
    dom = page_with(wedge_id, "en", f"demo=1&own={c:g},1")
    assert inner(dom, "own-money") == _card_money(dom, "C")
    assert 'id="own-line"' in dom, "the owner's option is not drawn in the race"
    assert 'data-p="D"' in dom, "the owner's option cannot be chosen"


@pytest.mark.parametrize("wedge_id,lang", ALL, ids=IDS)
def test_an_own_option_none_of_the_three_uses_is_worked_out_and_named(wedge_id, lang):
    dom = page_with(wedge_id, lang, "demo=1&own=13,0")
    text = text_of(dom)
    assert "undefined" not in text and "NaN" not in text
    vs = inner(dom, "own-vs")
    same_prefix = catalogue(lang)["ui"]["own_same"].split("{x}")[0].strip()
    assert vs and same_prefix not in vs, "a lever none of the three uses was called one of them"
    assert inner(dom, "own-money") not in {_card_money(dom, k) for k in "ABC"}
    assert re.search(r"[0-9۰-۹]", inner(dom, "own-census")), "no count of tested cases"


SHEET_DRIVER = """
<script>
setTimeout(function(){
  var b = document.querySelector('.pick[data-p="D"]');
  if(b) b.click();
  setTimeout(function(){
    var d = document.createElement('div');
    d.id = 'probe';
    d.setAttribute('data-sheet', document.getElementById('sheet').hidden ? 'no' : 'yes');
    d.setAttribute('data-rows', String(document.querySelectorAll('#sheet-cmp tr').length));
    d.setAttribute('data-choice', document.getElementById('sheet-choice').textContent);
    d.setAttribute('data-url', location.search);
    document.body.appendChild(d);
  }, 700);
}, 1500);
</script>
"""


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_an_own_option_can_be_the_decision_and_the_link_keeps_it(wedge_id, tmp_path):
    """The sheet names the owner's own option and compares it with the three; the link alone —
    without the page's memory — opens the same sheet."""
    page = SITE / wedge_id / f"{wedge_id}_decision_report.html"
    copy = tmp_path / "sheet.html"
    copy.write_text(page.read_text("utf-8").replace("</body>", SHEET_DRIVER + "</body>"),
                    encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=12000", "--dump-dom", copy.as_uri() + "?lang=en&demo=1&own=13,1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    m = re.search(r'<div id="probe"([^>]*)>', proc.stdout)
    assert m, "the sheet was never made"
    probe = {k: html_mod.unescape(v) for k, v in re.findall(r'data-(\w+)="([^"]*)"', m.group(1))}
    assert probe["sheet"] == "yes" and probe["rows"] == "4", probe
    assert "13" in probe["choice"]
    packed = re.search(r"sheet=([A-Za-z0-9_-]+)", probe["url"]).group(1)
    again = page_with(wedge_id, "en", f"sheet={packed}")
    assert not re.search(r'id="sheet"[^>]*\bhidden', again), "the link did not open as a sheet"
    assert inner(again, "sheet-choice") == probe["choice"]


def test_a_size_of_change_that_came_with_a_question_is_shown_on_its_step():
    """A routed question can carry the size of the change. It is shown filled in on its own
    step — in the "other" box when it is not one of the offered choices — never skipped."""
    dom = page_with("shop", "en", "shock=22")
    assert not re.search(r'<section id="ask"[^>]*\bhidden', dom), "the flow did not open"
    other = re.search(r'<div class="otherwrap" id="otherwrap"([^>]*)>(.*?)</div>', dom, re.S)
    assert other and "hidden" not in other.group(1), "the figure was not shown"
    assert 'value="22"' in other.group(2)
    assert re.search(r'class="choice other on"', dom)


# ---- the question box on the home screen -----------------------------------------------------------

HOME = SITE / "index.html"
FAKE_FETCH = """<script>window.fetch = function(){ return Promise.resolve({ok: true,
  json: function(){ return Promise.resolve(__REPLY__); }}); };</script>"""
HOME_DRIVER = """
<script>
setTimeout(function(){
  document.getElementById('ask-q').value = 'supplier up 25%, raise 7% and drop the low-margin lines?';
  document.getElementById('ask-keep').checked = true;
  document.getElementById('ask-go').click();
}, 400);
</script>
"""


def home(lang: str, tmp_path, cfg=None, reply=None) -> str:
    body = HOME.read_text("utf-8")
    if cfg is not None:
        body, n = re.subn(r'(<script id="ask-cfg" type="application/json">).*?(</script>)',
                          lambda m: m.group(1) + json.dumps(cfg) + m.group(2), body, count=1,
                          flags=re.S)
        assert n == 1, "the home screen has no question-box switch"
    if reply is not None:
        body = body.replace("<head>", "<head>" + FAKE_FETCH.replace("__REPLY__", json.dumps(reply)), 1)
        body = body.replace("</body>", HOME_DRIVER + "</body>")
    copy = tmp_path / f"home_{lang}.html"
    copy.write_text(body, encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=6000", "--dump-dom", copy.as_uri() + f"?lang={lang}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, proc.stderr[-800:]
    dom = re.sub(r"<script.*?</script>", " ", proc.stdout, flags=re.S)
    return re.sub(r"<style.*?</style>", " ", dom, flags=re.S)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_static_home_does_not_offer_a_box_it_cannot_send(lang, tmp_path):
    dom = home(lang, tmp_path)
    assert re.search(r'id="askbox"[^>]*\bhidden', dom), "a box with nowhere to send to is shown"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_where_the_host_takes_questions_the_box_says_what_happens_to_them(lang, tmp_path):
    ui = catalogue(lang)["ui"]
    dom = home(lang, tmp_path, cfg={"on": True, "route": True})
    assert not re.search(r'id="askbox"[^>]*\bhidden', dom)
    assert inner(dom, "ask-route-note") == " ".join(ui["ask_route_note"].split())
    assert inner(dom, "ask-keep-why") == " ".join(ui["ask_keep_why"].split())
    assert "undefined" not in text_of(dom)
    # Kept is never the default.
    assert not re.search(r'id="ask-keep"[^>]*\bchecked', dom)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_sorted_question_leads_to_the_page_that_answers_it(lang, tmp_path):
    reply = {"ok": True, "routed": True, "fit": "exact", "wedge": "shop", "variant": None,
             "shock": 25, "price": 7, "reduce": True, "topic": "pricing", "kept": True}
    dom = home(lang, tmp_path, cfg={"on": True, "route": True}, reply=reply)
    link = re.search(r'<a class="ask-link shop" id="ask-link" href="([^"]+)"', dom)
    assert link, "no way on to the page that answers it"
    href = html_mod.unescape(link.group(1))
    assert "shop" in href and "shock=25" in href and "own=7%2C1" in href
    shock = "۲۵" if lang == "fa" else "25"
    situation = catalogue(lang)["wedges"]["shop"]["what_changed"].replace("{shock}", shock).rstrip(" .۔")
    assert " ".join(situation.split()) in inner(dom, "ask-link")
    assert catalogue(lang)["ui"]["ask_kept"] in text_of(dom)
    assert "undefined" not in text_of(dom)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_question_it_cannot_answer_says_so_and_names_the_topic(lang, tmp_path):
    reply = {"ok": True, "routed": True, "fit": "none", "wedge": None, "variant": None,
             "shock": None, "price": None, "reduce": False, "topic": "hiring", "kept": False}
    dom = home(lang, tmp_path, cfg={"on": True, "route": True}, reply=reply)
    ui = catalogue(lang)["ui"]
    expected = ui["ask_fit_none"].replace("{topic}", ui["ask_topics"]["hiring"])
    assert " ".join(expected.split()) in " ".join(text_of(dom).split())
    assert 'id="ask-link"' not in dom, "offered a way on for a question it cannot answer"
