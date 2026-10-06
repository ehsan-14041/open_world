"""
What leaves the owner's browser, and what cannot.

An owner who runs the two-week price test is asked — once, next to the number, with the exact
row on screen — whether to share the measurement. These tests hold the two promises that offer
makes:

  * the row is the measurement and nothing else. Not "we do not read the other fields" but "the
    other fields have no path into the file": the row is built from a fixed list, so a client
    that posts a business's takings writes a row without them.
  * a host that does not want the data does not receive it. Deleting `contribute.php` removes
    the offer from the page, because the page only shows it where the endpoint exists.

They run against the PHP source with the built-in server and need no network and no key.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"

pytestmark = pytest.mark.skipif(
    shutil.which("php") is None or not (PHP_ROOT / "contribute.php").is_file(),
    reason="php CLI and the PHP bundle are needed",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """A throwaway copy of the bundle, so nothing here writes into the repo's own data."""
    root = tmp_path_factory.mktemp("php_contrib")
    shutil.copytree(PHP_ROOT, root / "site", dirs_exist_ok=False)
    site = root / "site"
    contrib = site / "data" / "contrib" / "measurements.jsonl"
    if contrib.exists():
        contrib.unlink()

    port = _free_port()
    proc = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", str(site)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/contribute.php", timeout=1)
            break
        except urllib.error.HTTPError:
            break                      # answering at all is enough
        except OSError:
            time.sleep(0.1)
    try:
        yield {"base": base, "site": site, "file": contrib}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def post(base: str, payload, raw: bytes | None = None) -> int:
    body = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(base + "/contribute.php", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


GOOD = {"wedge": "cafe", "variant": None, "e": 0.5, "rise": 10, "anon": "abc123def456"}


def test_a_measurement_can_be_given(server):
    assert post(server["base"], GOOD) == 200
    assert rows(server["file"]), "nothing was written"


def test_a_trade_this_build_knows_is_accepted(server):
    assert post(server["base"], dict(GOOD, variant="bakery", anon="zz99aa88bb77")) == 200
    assert any(r["variant"] == "bakery" for r in rows(server["file"]))


@pytest.mark.parametrize("bad,why", [
    ({"wedge": "barber"}, "a wedge this build does not have"),
    ({"variant": "sushi"}, "a trade this build does not have"),
    ({"e": 99}, "an elasticity that is not a measurement"),
    ({"e": -1}, "a negative elasticity"),
    ({"e": "nought"}, "an elasticity that is not a number"),
    ({"rise": 0}, "a price rise of nothing"),
    ({"rise": 500}, "a price rise nobody made"),
    ({"anon": "<script>"}, "an id that is not an id"),
    ({"anon": "x"}, "an id too short to be random"),
])
def test_a_row_that_is_not_a_measurement_is_refused(server, bad, why):
    assert post(server["base"], dict(GOOD, **bad)) == 400, f"accepted {why}"


def test_only_a_post_is_answered(server):
    try:
        with urllib.request.urlopen(server["base"] + "/contribute.php", timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 405


def test_a_body_that_is_not_json_is_refused(server):
    assert post(server["base"], None, raw=b"hello") == 400


def test_an_oversized_body_is_refused(server):
    assert post(server["base"], dict(GOOD, pad="x" * 4000)) == 413


def test_the_owners_figures_have_no_path_into_the_file(server):
    """
    The promise on screen is that takings, cash, counts and names stay on the page. This posts
    them anyway — the way a modified client or a curious tester would — and checks the written
    row. It is not that the fields are ignored; it is that the row is built from a fixed list,
    so there is nowhere for them to land.
    """
    smuggled = dict(GOOD, anon="pii000pii000pii0",
                    monthly_revenue=48600, cash_on_hand=18000, daily_orders=200,
                    name="Cafe Sahar", email="owner@example.com", ip="203.0.113.9",
                    at="1990-01-01")
    assert post(server["base"], smuggled) == 200
    row = [r for r in rows(server["file"]) if r["anon"] == "pii000pii000pii0"]
    assert len(row) == 1
    assert set(row[0]) == {"at", "wedge", "variant", "e", "rise", "anon"}, \
        f"the row grew fields: {sorted(set(row[0]) - {'at','wedge','variant','e','rise','anon'})}"
    assert row[0]["at"] != "1990-01-01", "the client set its own date"
    blob = json.dumps(rows(server["file"]))
    for leak in ("48600", "18000", "Cafe Sahar", "owner@example.com", "203.0.113.9"):
        assert leak not in blob, f"{leak!r} reached the file"


def test_the_row_carries_the_day_and_not_the_moment(server):
    """An hour-by-hour record of when owners are at the till is a movement pattern."""
    for row in rows(server["file"]):
        assert len(row["at"]) == 10 and row["at"].count("-") == 2, row["at"]


def test_a_host_that_deletes_the_endpoint_stops_being_offered_it():
    """
    The page only offers to share where a host can receive it, so removing the file is a
    complete opt-out rather than a broken button.
    """
    report = (PHP_ROOT / "lib" / "report.php").read_text("utf-8")
    assert "'contrib' => is_file(__DIR__ . '/../contribute.php')" in report, \
        "the bundle no longer reports whether this host accepts measurements"
    template = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text("utf-8")
    assert "D.contrib && measure" in template, "the page offers to share without checking"
    readme = (PHP_ROOT / "README_DEPLOY.md").read_text("utf-8")
    assert "delete `contribute.php`" in readme, "the opt-out is not documented"


def test_the_page_lists_every_field_it_will_send(server):
    """
    Consent to a row you cannot see is not consent. Every field the endpoint writes, except the
    date it stamps itself, is named on screen before the button is pressed.
    """
    from event_sim.wedge.i18n import LANGUAGES, catalogue
    template = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text("utf-8")
    for key in ("share_list_e", "share_list_rise", "share_list_kind",
                "share_list_date", "share_list_anon"):
        assert f"t('{key}')" in template, f"the page does not show {key}"
        for lang in LANGUAGES:
            assert catalogue(lang)["ui"][key].strip(), f"{lang}: {key} is empty"
    for lang in LANGUAGES:
        assert catalogue(lang)["ui"]["share_not"].strip(), f"{lang}: nothing says what is not sent"
