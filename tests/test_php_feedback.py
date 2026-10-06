"""
"Did this help?" on the host: what is written, where, and who can read it.

  * a row is written only when an owner sends one, and it is the fixed row the page listed —
    the answers, a scrubbed free-text line, the day, the build, the invitation tag, a random id;
  * anything outside the fixed answers is refused rather than stored;
  * a contact reaches only bookings.jsonl, only with "book" chosen, a price offered and the box
    ticked — so it can be deleted without losing the evidence;
  * the maintainer reads counts per build (each browser once) and downloads CSV, as text,
    behind the admin password.

Run against the PHP source with the built-in server. No network.
"""

from __future__ import annotations

import http.cookiejar
import json
import shutil
import urllib.error
import urllib.request

import pytest

from tests.test_php_ask import PHP_ROOT, _free_port, _serve, rows

pytestmark = pytest.mark.skipif(
    shutil.which("php") is None or not (PHP_ROOT / "feedback.php").is_file(),
    reason="php CLI and the PHP bundle are needed",
)

BUILD = "wedges_php_20260927-test"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    site = tmp_path_factory.mktemp("php_fb") / "site"
    shutil.copytree(PHP_ROOT, site)
    for leftover in ("feedback", "contrib", "questions", "settings.json", "llm_usage.json"):
        target = site / "data" / leftover
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    (site / "config.php").unlink(missing_ok=True)
    (site / "VERSION.txt").write_text(BUILD + "\nbuilt for a test\n", encoding="utf-8")
    port = _free_port()
    web = _serve(["php", "-S", f"127.0.0.1:{port}", "-t", str(site)],
                 f"http://127.0.0.1:{port}/feedback.php")
    try:
        yield {"base": f"http://127.0.0.1:{port}", "site": site,
               "fb": site / "data" / "feedback" / "feedback.jsonl",
               "book": site / "data" / "feedback" / "bookings.jsonl"}
    finally:
        web.terminate()
        web.wait(timeout=10)


@pytest.fixture()
def config(env):
    """Write config.php for one test, and remove it after."""
    path = env["site"] / "config.php"

    def write(**kw):
        path.write_text("<?php return " + _php(kw) + ";\n", encoding="utf-8")
    yield write
    path.unlink(missing_ok=True)


def _php(v) -> str:
    if isinstance(v, dict):
        return "[" + ", ".join(f"{_php(k)} => {_php(x)}" for k, x in v.items()) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def send(base: str, payload, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(base + "/feedback.php", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


def row(**over):
    base = {"wedge": "cafe", "variant": None, "lang": "fa", "demo": False, "real": "now",
            "helped": "partly", "next": "test", "hard": "monthly_cogs",
            "missing": "the 90 days felt short", "src": "assoc-1", "anon": "fbfbfbfbfbfbfbfb"}
    base.update(over)
    return base


def test_only_a_post_is_answered(env):
    try:
        with urllib.request.urlopen(env["base"] + "/feedback.php", timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 405


def test_a_sent_row_is_the_fixed_row_and_nothing_more(env):
    before = len(rows(env["fb"]))
    code, reply = send(env["base"], row(monthly_revenue=90000000, name="Cafe Nader", ip="1.2.3.4"))
    assert code == 200 and reply["ok"] is True and reply["booked"] is False
    got = rows(env["fb"])[before:]
    assert len(got) == 1
    r = got[0]
    assert set(r) == {"at", "build", "wedge", "variant", "lang", "demo", "src", "real", "helped",
                      "next", "hard", "missing", "anon"}
    assert r["build"] == BUILD and r["src"] == "assoc-1" and r["missing"] == "the 90 days felt short"
    assert len(r["at"]) == 10, "the moment was stored, not the day"
    assert "90000000" not in env["fb"].read_text("utf-8") and "Nader" not in env["fb"].read_text("utf-8")


@pytest.mark.parametrize("over,why", [
    ({"wedge": "barber"}, "unknown wedge"),
    ({"variant": "sushi"}, "unknown variant"),
    ({"helped": "very"}, "bad helped"),
    ({"next": "raise 12%"}, "bad next"),
    ({"hard": "monthly_rent"}, "bad hard"),
    ({"anon": "x"}, "bad id"),
    ({"real": None, "helped": None, "next": None, "hard": None, "missing": ""}, "empty"),
], ids=["wedge", "variant", "helped", "next", "hard", "anon", "empty"])
def test_anything_outside_the_fixed_answers_is_refused(env, over, why):
    before = len(rows(env["fb"]))
    assert send(env["base"], row(**over))[0] == 400, why
    assert len(rows(env["fb"])) == before


def test_free_text_loses_phone_numbers_and_addresses_before_it_is_written(env):
    send(env["base"], row(missing="call me 0912 345 6789 or a@b.com, see www.x.ir"))
    text = rows(env["fb"])[-1]["missing"]
    assert "0912" not in text and "a@b.com" not in text and "www.x.ir" not in text


def test_without_a_price_there_is_no_offer_and_no_contact(env):
    before = len(rows(env["book"]))
    code, reply = send(env["base"], row(offer="book", contact="0912 345 6789", keep_contact=True))
    assert code == 200 and reply["booked"] is False
    assert "offer" not in rows(env["fb"])[-1]
    assert len(rows(env["book"])) == before


def test_a_contact_is_kept_apart_and_only_with_its_box_ticked(env, config):
    config(offer_price="1,500,000 تومان")
    code, reply = send(env["base"], row(offer="book", contact="0912 345 6789"))
    assert code == 200 and reply["booked"] is False, "kept a contact whose box was not ticked"
    assert rows(env["fb"])[-1]["offer"] == "book"

    code, reply = send(env["base"], row(offer="book", contact="0912 345 6789", keep_contact=True))
    assert code == 200 and reply["booked"] is True
    b = rows(env["book"])[-1]
    assert b["contact"] == "0912 345 6789" and b["price"] == "1,500,000 تومان" and b["build"] == BUILD
    assert "0912" not in env["fb"].read_text("utf-8"), "the contact reached the answers file"

    code, reply = send(env["base"], row(offer="maybe", contact="0912 345 6789", keep_contact=True))
    assert reply["booked"] is False, "a contact was kept without a request to book"


def test_a_host_can_switch_it_off(env, config):
    config(feedback=False)
    assert send(env["base"], row())[0] == 404


def test_a_site_behind_the_password_keeps_it_behind_it(env, config):
    config(password="letmein")
    assert send(env["base"], row())[0] == 403


def test_the_report_page_is_told_whether_to_ask_and_at_what_price(env, config):
    config(password="", offer_price="$49")
    with urllib.request.urlopen(env["base"] + "/?w=cafe&lang=en", timeout=60) as r:
        page = r.read().decode("utf-8")
    assert '"feedback":true' in page and '"offer":"$49"' in page
    config(password="", feedback=False)
    with urllib.request.urlopen(env["base"] + "/?w=cafe&lang=en", timeout=60) as r:
        page = r.read().decode("utf-8")
    assert '"feedback":false' in page and '"offer":null' in page, "a cached page kept an old setting"


def _admin(env, config):
    config(admin_password="maint", password="")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.open(urllib.request.Request(env["base"] + "/admin.php", data=b"admin_password=maint",
                                       method="POST"), timeout=20)
    return opener


def test_the_maintainer_sees_counts_per_build_as_text(env, config):
    send(env["base"], row(anon="dupdupdupdupdup1", helped="no", missing="<b>bold</b> admin-fb-marker"))
    send(env["base"], row(anon="dupdupdupdupdup1", helped="yes"))
    opener = _admin(env, config)
    page = opener.open(env["base"] + "/admin.php", timeout=20).read().decode("utf-8")
    assert "What owners told us" in page and BUILD in page
    assert "Before you share the link" in page
    assert "admin-fb-marker" in page and "<b>bold</b>" not in page
    assert "&lt;b&gt;bold&lt;/b&gt;" in page


def test_counts_take_each_browser_once():
    import subprocess
    code = ("require 'lib/feedback.php';"
            "$r = [['anon'=>'a','wedge'=>'cafe','build'=>'b1','helped'=>'no'],"
            "      ['anon'=>'a','wedge'=>'cafe','build'=>'b1','helped'=>'yes'],"
            "      ['anon'=>'c','wedge'=>'cafe','build'=>'b1','helped'=>'yes','demo'=>true]];"
            "echo json_encode(feedback_summary($r));")
    out = subprocess.run(["php", "-r", code], cwd=PHP_ROOT, capture_output=True, text=True, check=True)
    s = json.loads(out.stdout)["b1"]
    assert s["owners"] == 2 and s["own_numbers"] == 1 and s["counts"]["helped"] == {"yes": 2}


def test_downloads_need_the_admin_password_and_neutralise_formulas(env, config):
    send(env["base"], row(missing="=HYPERLINK(1)"))
    try:
        urllib.request.urlopen(env["base"] + "/admin.php?export=feedback", timeout=20).read()
        locked = b""
    except urllib.error.HTTPError as e:
        locked = e.read()
    opener = _admin(env, config)
    csv = opener.open(env["base"] + "/admin.php?export=feedback", timeout=20).read().decode("utf-8-sig")
    assert csv.startswith("at,build,wedge"), "the export is not the CSV"
    assert "'=HYPERLINK(1)" in csv and ",=HYPERLINK" not in csv
    assert b"at,build,wedge" not in locked
