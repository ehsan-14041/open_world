"""
The pages a café owner uses, checked for the things that stop someone using them at all.

For every screen an owner passes through — the questions, the result with its reveals open, the
decision sheet and the "did this help?" card — in both languages and both colour themes:

  * every control has a name a screen reader can say;
  * no id is used twice (labels and aria references would point at the wrong thing);
  * headings do not skip a level;
  * text meets WCAG AA contrast: 4.5:1, or 3:1 for large text.

The probe is tests/a11y_probe.js. It reads computed styles, so text drawn over a pseudo-element
(the chosen segment of the sensitivity control) is exempted there by name, not guessed at here.
Tap-target size is not asserted: the one small control is a link inside a sentence, which WCAG
exempts.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import subprocess
from pathlib import Path

import pytest

from event_sim.wedge.i18n import LANGUAGES
from event_sim.wedge.registry import WEDGES

from tests.test_decision_page_dom import CHROME, SITE
from tests.test_decision_page_dom import pytestmark  # noqa: F401  (needs Chrome and the demo site)

PROBE = (Path(__file__).parent / "a11y_probe.js").read_text("utf-8")
THEMES = ("light", "dark")

OPEN_ALL = ("document.querySelectorAll('details').forEach(function(d){ d.open = true; });"
            "var b = document.getElementById('uk-try'); if(b) b.click();")
MAKE_SHEET = ("var p = document.querySelector('#picks .pick'); if(p) p.click();"
              "setTimeout(function(){ var r = document.querySelector('input[name=\"fb-offer\"][value=\"book\"]');"
              " if(r){ r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }"
              " document.querySelectorAll('#fb details').forEach(function(d){ d.open = true; }); }, 300);")

STATES = {"questions": ("", ""), "result": ("demo=1", OPEN_ALL), "sheet": ("demo=1", MAKE_SHEET)}


def _audit(tmp_path, wedge_id: str, lang: str, theme: str, state: str) -> dict:
    query, act = STATES[state]
    page = (SITE / wedge_id / f"{wedge_id}_decision_report.html").read_text("utf-8")
    # The feedback card appears only where a host can take answers; switch that on so it is seen.
    head = '<script id="data" type="application/json">{'
    page = page.replace(head, head + '"feedback":true,"offer":"1,500,000 تومان",', 1)
    page = page.replace("</body>",
                        "<script>setTimeout(function(){" + act + "}, 1200);</script>"
                        + "<script>" + PROBE.replace("__WAIT__", "2600") + "</script></body>")
    copy = tmp_path / f"a11y_{wedge_id}_{lang}_{theme}_{state}.html"
    copy.write_text(page, encoding="utf-8")
    proc = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--window-size=390,900",
         "--virtual-time-budget=10000", "--dump-dom",
         copy.as_uri() + f"?lang={lang}&theme={theme}&" + query],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    m = re.search(r'data-audit="([^"]*)"', proc.stdout)
    assert m, f"the probe never ran: {proc.stderr[-300:]}"
    return json.loads(html_mod.unescape(m.group(1)))


CASES = [(w, lang, theme, state) for w in sorted(WEDGES) for lang in LANGUAGES
         for theme in THEMES for state in STATES
         if w == "cafe" or state == "result"]          # every screen for the pilot trade


@pytest.mark.parametrize("wedge_id,lang,theme,state", CASES,
                         ids=["-".join(c) for c in CASES])
def test_the_page_can_be_read_and_operated(tmp_path, wedge_id, lang, theme, state):
    a = _audit(tmp_path, wedge_id, lang, theme, state)
    where = f"{wedge_id}/{lang}/{theme}/{state}"
    assert a["lang"] == lang and a["dir"] == ("rtl" if lang == "fa" else "ltr"), where
    assert not a["noName"], f"{where}: controls without a name: {a['noName']}"
    assert not a["dup"], f"{where}: ids used twice: {a['dup']}"
    assert not a["headings"], f"{where}: skipped heading levels: {a['headings']}"
    assert not a["contrast"], f"{where}: text below AA contrast: {a['contrast']}"
