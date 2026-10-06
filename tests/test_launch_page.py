"""
The launch build's two additions to the page, held to what they promise.

  * The census counts every tested supplier increase, including ones the owner never gave. Beside
    it, the same count with the increase held at the owner's own figure — and that count must be
    the one the Python pipeline gives for it, not an approximation.
  * After a decision sheet, a host that can take answers asks "did this help?". Nothing leaves
    the page until the owner presses send; the row sent is exactly the row listed, and it never
    carries a business figure. The card never appears under a sheet someone else sent, or on a
    static build that has nowhere to send it.
"""

from __future__ import annotations

import dataclasses
import html as html_mod
import json
import re
import subprocess

import pytest

from event_sim.wedge.i18n import LANGUAGES, catalogue
from event_sim.wedge.registry import WEDGES

from tests.test_decision_page_dom import (CHROME, SITE, _packed, _packed_owner, _sheet_dom, inner,
                                          rendered)
from tests.test_decision_page_dom import pytestmark  # noqa: F401  (needs Chrome and the demo site)


# ---- the count at the owner's own increase ------------------------------------------------------

def _report(wedge_id: str) -> dict:
    return json.loads((SITE / wedge_id / f"{wedge_id}_decision_report.json").read_text("utf-8"))


def _counts(note: str) -> tuple[int, int, int, int]:
    """(n, total) of the whole census, then (n, total) at the owner's own increase."""
    nums = [int(x.replace(",", "")) for x in re.findall(r"[0-9][0-9,]*", note)]
    return nums[0], nums[1], nums[2], nums[3]


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_the_count_at_the_owners_own_increase_is_that_slice_of_the_census(wedge_id):
    """For a report's own figures the increase is a tested size, so the count at it must be
    exactly the census points at that size where the leading option ranks first."""
    rep = _report(wedge_id)
    shock_key = rep["copy"]["fields"]["shock"]
    own = rep["baseline_raw"][shock_key]
    note = " ".join(inner(rendered(wedge_id, "en"), "count-note").split())
    assert 'id="count-own"' in rendered(wedge_id, "en"), f"{wedge_id}: no count at the owner's increase"
    n, total, n_own, total_own = _counts(html_mod.unescape(re.sub(r"<[^>]+>", " ", note)))
    wins = rep["sensitivity"]["win_counts"]
    lead = [k for k, v in wins.items() if v == n]
    assert len(lead) == 1 and total == rep["sensitivity"]["n"], (note, wins)
    at_own = [p for p in rep["sensitivity"]["points"] if p["settings"][shock_key] == own]
    assert total_own == len(at_own) and total_own < total
    assert n_own == sum(1 for p in at_own if p["ranking"][0] == lead[0]), note
    assert f"{own:g}%" in note, "the note does not name the owner's own increase"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_count_at_the_owners_own_increase_is_written_in_each_language(lang):
    dom = rendered("cafe", lang)
    own = inner(dom, "count-own")
    assert own.strip(), f"{lang}: the count at the owner's increase is empty"
    tpl = catalogue(lang)["ui"]["census_own"]
    for word in re.sub(r"\{\w+\}", " ", tpl).split():
        assert word in own, f"{lang}: {word!r} missing from {own!r}"


def test_between_the_tested_sizes_the_count_is_the_pipelines_count_at_that_increase():
    """At an increase no precomputed run carries (25% for a cafe tested at 20/30/40%), the page's
    engine runs every other assumption at the owner's own figure. The Python pipeline, swept at
    that one increase, must give the same count."""
    from event_sim.wedge.sensitivity import run_sensitivity
    wedge = WEDGES["cafe"]
    raw = dict(wedge.demo_factory().to_dict(), supplier_increase_pct=25.0, is_demo=False)
    swept = dataclasses.replace(wedge, sweep=dict(wedge.sweep, supplier_increase_pct=[25.0]))
    truth = run_sensitivity(swept, wedge.baseline_from_dict(raw))

    dom = _sheet_dom("cafe", "en", _packed_owner("cafe", {"supplier_increase_pct": 25.0}))
    note = html_mod.unescape(re.sub(r"<[^>]+>", " ", inner(dom, "count-note")))
    n, total, n_own, total_own = _counts(note)
    assert "25%" in note
    assert total_own == truth.n, (note, truth.n)
    # The page counts the option leading under the owner's own figures: the pipeline's centre.
    lead = truth.central_ranking[0]
    assert n_own == truth.win_counts()[lead], \
        f"page counts {n_own} of {total_own} for {lead}; pipeline gives {truth.win_counts()}"


# ---- "did this help?" ------------------------------------------------------------------------------

FB_DRIVER = """
<script>
window.__sent = null;
window.fetch = function(url, opts){
  window.__sent = {url: String(url), body: opts && opts.body};
  return Promise.resolve({ok: true, json: function(){ return Promise.resolve({ok: true}); }});
};
var VALS = __VALS__;
function fire(el, kind){ el.dispatchEvent(new Event(kind, {bubbles: true})); }
function choose(name, v){
  var el = document.querySelector('input[name="' + name + '"][value="' + v + '"]');
  if(!el) return false;
  el.checked = true; fire(el, 'change'); return true;
}
setTimeout(function(){
  var probe = {};
  if(VALS.pick){ var p = document.querySelector('#picks .pick[data-p="' + VALS.pick + '"]'); if(p) p.click(); }
  if(VALS.rerender){ document.getElementById('sheet-back'); }
  setTimeout(function(){
    var fb = document.getElementById('fb');
    probe.shown = !fb.hidden;
    if(!fb.hidden && VALS.answer){
      probe.goInitially = document.getElementById('fb-go').disabled;
      probe.chose = [choose('fb-real', 'now'), choose('fb-helped', 'partly'), choose('fb-next', 'test')];
      var hs = document.getElementById('fb-hard'); hs.value = VALS.hard; fire(hs, 'change');
      var m = document.getElementById('fb-miss'); m.value = VALS.miss; fire(m, 'input');
      probe.offerShown = !document.getElementById('fb-offer').hidden;
      if(VALS.book){
        choose('fb-offer', 'book');
        var c = document.getElementById('fb-contact'); c.value = VALS.contact; fire(c, 'input');
        if(VALS.tick){ var k = document.getElementById('fb-contact-ok'); k.checked = true; fire(k, 'change'); }
      }
      probe.list = document.getElementById('fb-list').textContent;
      document.getElementById('fb-go').click();
    }
    setTimeout(function(){
      probe.sent = window.__sent;
      probe.title = document.getElementById('fb-t').textContent;
      probe.formHidden = document.getElementById('fb-form').hidden;
      document.body.setAttribute('data-probe', JSON.stringify(probe));
    }, 600);
  }, 900);
}, 1500);
</script>
"""


def _fb(tmp_path, wedge_id: str = "cafe", *, host: dict | None, vals: dict, query: str = "demo=1",
        name: str = "fb.html") -> dict:
    page = (SITE / wedge_id / f"{wedge_id}_decision_report.html").read_text("utf-8")
    if host is not None:
        head = '<script id="data" type="application/json">{'
        assert page.count(head) == 1
        page = page.replace(head, head + json.dumps(host)[1:-1] + ",", 1)
    page = page.replace("</body>", FB_DRIVER.replace("__VALS__", json.dumps(vals)) + "</body>")
    copy = tmp_path / name
    copy.write_text(page, encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=12000", "--dump-dom", copy.as_uri() + "?lang=en&" + query],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    m = re.search(r'data-probe="([^"]*)"', proc.stdout)
    assert m, "the page never settled"
    return json.loads(html_mod.unescape(m.group(1)))


ANSWER = {"pick": "B", "answer": True, "hard": "monthly_cogs",
          "miss": "the 90 days felt short", "book": False, "tick": False, "contact": ""}
HOST = {"feedback": True, "offer": None}


def test_a_static_build_never_asks(tmp_path):
    probe = _fb(tmp_path, host=None, vals={"pick": "B"})
    assert probe["shown"] is False


def test_after_a_sheet_of_their_own_the_owner_is_asked_and_nothing_is_sent_until_they_press(tmp_path):
    probe = _fb(tmp_path, host=HOST, vals=ANSWER)
    assert probe["shown"] is True
    assert probe["goInitially"] is True, "send was possible before anything was answered"
    assert probe["chose"] == [True, True, True]
    assert probe["offerShown"] is False, "a follow-up was offered with no price set"
    sent = probe["sent"]
    assert sent and sent["url"] == "feedback.php"
    row = json.loads(sent["body"])
    assert set(row) == {"wedge", "variant", "lang", "demo", "real", "helped", "next", "hard",
                        "missing", "src", "anon"}
    assert (row["real"], row["helped"], row["next"], row["hard"]) == ("now", "partly", "test", "monthly_cogs")
    assert row["wedge"] == "cafe" and row["demo"] is True and row["src"] is None
    assert re.fullmatch(r"[a-z0-9]{16}", row["anon"])
    assert probe["formHidden"] is True
    assert probe["title"] == catalogue("en")["ui"]["fb_thanks_t"]


def test_the_row_sent_carries_no_business_figure(tmp_path):
    probe = _fb(tmp_path, host=HOST, vals=ANSWER)
    body = probe["sent"]["body"]
    demo = WEDGES["cafe"].demo_factory().to_dict()
    for k, v in demo.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 100:
            assert f"{v:g}" not in body and str(int(v)) not in body, f"{k} reached the row"


def test_what_is_listed_is_what_is_sent(tmp_path):
    probe = _fb(tmp_path, host=HOST, vals=ANSWER)
    ui = catalogue("en")["ui"]
    for key in ("fb_real_now", "fb_helped_partly", "fb_next_test", "fb_numbers_demo"):
        assert ui[key] in probe["list"], f"{key} is not listed"
    assert "the 90 days felt short" in probe["list"]
    assert json.loads(probe["sent"]["body"])["anon"] in probe["list"]


def test_a_contact_is_sent_only_with_its_box_ticked(tmp_path):
    host = {"feedback": True, "offer": "$49"}
    untick = _fb(tmp_path, host=host, name="a.html",
                 vals=dict(ANSWER, book=True, tick=False, contact="owner@example.com"))
    row = json.loads(untick["sent"]["body"])
    assert untick["offerShown"] is True
    assert row["offer"] == "book" and row["contact"] is None and row["keep_contact"] is False
    assert "owner@example.com" not in untick["list"]

    tick = _fb(tmp_path, host=host, name="b.html",
               vals=dict(ANSWER, book=True, tick=True, contact="owner@example.com"))
    row = json.loads(tick["sent"]["body"])
    assert row["contact"] == "owner@example.com" and row["keep_contact"] is True
    assert "owner@example.com" in tick["list"]


def test_the_invitation_tag_travels_only_inside_the_row(tmp_path):
    probe = _fb(tmp_path, host=HOST, vals=ANSWER, query="demo=1&src=Assoc-1")
    assert json.loads(probe["sent"]["body"])["src"] == "assoc-1"
    bad = _fb(tmp_path, host=HOST, vals=ANSWER, query="demo=1&src=%3Cscript%3E", name="bad.html")
    assert json.loads(bad["sent"]["body"])["src"] is None


def test_a_sheet_someone_else_sent_does_not_ask(tmp_path):
    probe = _fb(tmp_path, host=HOST, vals={}, query="sheet=" + _packed("cafe"))
    assert probe["shown"] is False


# ---- the keyboard ---------------------------------------------------------------------------------

ENTER_DRIVER = """
<script>
setTimeout(function(){
  var step = document.getElementById('ask-progress').textContent;
  var choice = document.querySelector('#ask-body .choice');
  choice.focus();
  var ev = new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
  choice.dispatchEvent(ev);
  setTimeout(function(){
    document.body.setAttribute('data-probe', JSON.stringify({
      prevented: ev.defaultPrevented, before: step,
      after: document.getElementById('ask-progress').textContent,
      focus: document.activeElement === choice}));
  }, 400);
}, 1500);
</script>
"""


@pytest.mark.parametrize("wedge_id", sorted(WEDGES))
def test_enter_on_a_choice_is_left_to_the_choice(tmp_path, wedge_id):
    """Enter on a focused choice must press that choice. The step's own Enter handler used to take
    it, skip the owner's answer and carry on with the default."""
    page = (SITE / wedge_id / f"{wedge_id}_decision_report.html").read_text("utf-8")
    copy = tmp_path / "enter.html"
    copy.write_text(page.replace("</body>", ENTER_DRIVER + "</body>"), encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--virtual-time-budget=6000", "--dump-dom", copy.as_uri() + "?lang=en"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    m = re.search(r'data-probe="([^"]*)"', proc.stdout)
    assert m, "the page never settled"
    probe = json.loads(html_mod.unescape(m.group(1)))
    assert probe["prevented"] is False, "the step handler swallowed Enter on a choice"
    assert probe["before"] == probe["after"], "Enter on a choice moved on without choosing it"
