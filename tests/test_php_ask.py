"""
A question in the owner's own words: what reaches the provider, what reaches the file, and what
the page is allowed to say about it.

The home screen offers "ask your own question". These tests hold its three promises:

  * the provider sorts and never answers. Every field it returns is checked against this build,
    and anything unknown, out of range or inconsistent becomes "cannot answer this yet";
  * nothing is kept unless the owner ticks the box, and then as one fixed row — the text minus
    phone numbers, email and web addresses, the day, what it was sorted as, and a random id;
  * that same scrubbed text is all the provider ever sees.

They run against the PHP source with the built-in server and a fake provider that records what
it was sent. No network, no key.
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
    shutil.which("php") is None or not (PHP_ROOT / "ask.php").is_file(),
    reason="php CLI and the PHP bundle are needed",
)

#: A provider that records every request and answers by a keyword in the question.
FAKE_PROVIDER = r"""<?php
$body = (string) file_get_contents('php://input');
file_put_contents(__DIR__ . '/seen.jsonl', $body . "\n", FILE_APPEND);
$req = json_decode($body, true);
$q = (string) ($req['messages'][1]['content'] ?? '');
if (strpos($q, 'hire') !== false) {
    $a = ['fit' => 'none', 'wedge' => 'cafe', 'variant' => null, 'shock_pct' => null,
          'price_rise_pct' => null, 'reduce' => false, 'topic' => 'hiring'];
} elseif (strpos($q, 'broken') !== false) {
    $a = ['fit' => 'exact', 'wedge' => 'barber', 'variant' => 'sushi', 'shock_pct' => 900,
          'price_rise_pct' => 500, 'reduce' => 'yes', 'topic' => 'astrology',
          'answer' => 'Raise prices by 12%, you will make 4,000 more a month.'];
} elseif (strpos($q, 'mismatch') !== false) {
    $a = ['fit' => 'exact', 'wedge' => 'shop', 'variant' => 'bakery', 'shock_pct' => '25%',
          'price_rise_pct' => 7, 'reduce' => true, 'topic' => 'pricing'];
} elseif (strpos($q, 'prose') !== false) {
    header('Content-Type: application/json');
    echo json_encode(['choices' => [['message' => ['content' => 'You should raise prices.']]],
                      'usage' => ['prompt_tokens' => 1, 'completion_tokens' => 1]]);
    exit;
} else {
    $a = ['fit' => 'exact', 'wedge' => 'shop', 'variant' => null, 'shock_pct' => 25,
          'price_rise_pct' => 7, 'reduce' => true, 'topic' => 'pricing'];
}
header('Content-Type: application/json');
echo json_encode(['choices' => [['message' => ['content' => json_encode($a)]]],
                  'usage' => ['prompt_tokens' => 10, 'completion_tokens' => 5]]);
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _serve(args: list[str], probe: str) -> subprocess.Popen:
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(probe, timeout=1)
            break
        except urllib.error.HTTPError:
            break                              # answering at all is enough
        except OSError:
            time.sleep(0.1)
    return proc


def _settings(site: Path, fake_base: str, router_on: bool) -> None:
    (site / "data").mkdir(exist_ok=True)
    (site / "data" / "settings.json").write_text(json.dumps({"llm": {
        "enabled": True, "base_url": fake_base, "api_key": "test-key", "model": "fake-model",
        "timeout_seconds": 10, "max_output_tokens": 400, "monthly_call_cap": 0,
        "features": {"translation": False, "intake_assistant": False,
                     "question_router": router_on},
    }}), encoding="utf-8")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("php_ask")
    site = root / "site"
    shutil.copytree(PHP_ROOT, site)
    for leftover in ("questions", "settings.json", "llm_usage.json"):
        target = site / "data" / leftover
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    (site / "config.php").unlink(missing_ok=True)

    fake_dir = root / "provider"
    fake_dir.mkdir()
    (fake_dir / "fake.php").write_text(FAKE_PROVIDER, encoding="utf-8")
    fake_port, site_port = _free_port(), _free_port()
    fake = _serve(["php", "-S", f"127.0.0.1:{fake_port}", "-t", str(fake_dir),
                   str(fake_dir / "fake.php")], f"http://127.0.0.1:{fake_port}/")
    _settings(site, f"http://127.0.0.1:{fake_port}/v1", router_on=True)
    web = _serve(["php", "-S", f"127.0.0.1:{site_port}", "-t", str(site)],
                 f"http://127.0.0.1:{site_port}/ask.php")
    try:
        yield {"base": f"http://127.0.0.1:{site_port}", "site": site,
               "fake_base": f"http://127.0.0.1:{fake_port}/v1",
               "file": site / "data" / "questions" / "questions.jsonl",
               "seen": fake_dir / "seen.jsonl"}
    finally:
        for proc in (web, fake):
            proc.terminate()
            proc.wait(timeout=10)


def ask(base: str, payload, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(base + "/ask.php", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def seen(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


Q = "my supplier put prices up 25%, should I raise mine 7% and drop the low-margin lines?"


# ---- the door ---------------------------------------------------------------------------------

def test_only_a_post_is_answered(env):
    try:
        with urllib.request.urlopen(env["base"] + "/ask.php", timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    assert code == 405


@pytest.mark.parametrize("payload,raw,code", [
    (None, b"hello", 400),
    ({"q": "  ", "lang": "en"}, None, 400),
    ({"q": "x" * 5000, "lang": "en"}, None, 413),
    ({"q": Q, "lang": "en", "keep": True, "anon": "<script>"}, None, 400),
], ids=["not-json", "empty", "oversized", "bad-id"])
def test_a_request_that_is_not_a_question_is_refused(env, payload, raw, code):
    assert ask(env["base"], payload, raw)[0] == code


# ---- sorting, never answering -------------------------------------------------------------------

def test_a_question_this_tool_can_answer_is_sorted_into_it(env):
    status, r = ask(env["base"], {"q": Q, "lang": "en", "keep": False})
    assert status == 200 and r["routed"] is True
    assert (r["fit"], r["wedge"], r["shock"], r["price"], r["reduce"]) == ("exact", "shop", 25.0, 7.0, True)


def test_a_question_it_cannot_answer_is_named_as_such(env):
    status, r = ask(env["base"], {"q": "should I hire a second barista?", "lang": "en"})
    assert status == 200
    assert (r["fit"], r["topic"]) == ("none", "hiring")
    assert r["shock"] is None and r["price"] is None


def test_what_this_build_does_not_know_becomes_cannot_answer_yet(env):
    """A wedge that does not exist, a trade from nowhere, numbers out of range, a made-up topic
    and a field that is an answer in disguise — none of it survives."""
    status, r = ask(env["base"], {"q": "broken question", "lang": "en"})
    assert status == 200
    assert r["fit"] == "none" and r["wedge"] is None and r["variant"] is None
    assert r["topic"] == "other" and r["price"] is None and r["shock"] is None
    assert "answer" not in r and "4,000" not in json.dumps(r)


def test_a_trade_must_belong_to_the_business_it_is_named_with(env):
    status, r = ask(env["base"], {"q": "mismatch question", "lang": "en"})
    assert status == 200
    assert r["wedge"] == "shop" and r["variant"] is None, "a bakery was attached to a shop"
    assert r["shock"] == 25.0, "a percentage written as text was not read as one"


def test_prose_from_the_provider_is_not_passed_on(env):
    status, r = ask(env["base"], {"q": "prose please", "lang": "en"})
    assert status == 200
    assert r["routed"] is False and r["fit"] == "unrouted"
    assert "raise" not in json.dumps(r).lower()


def test_with_the_router_off_the_provider_is_never_called(env):
    _settings(env["site"], env["fake_base"], router_on=False)
    try:
        before = seen(env["seen"])
        status, r = ask(env["base"], {"q": "router is off, " + Q, "lang": "en"})
        assert status == 200 and r["routed"] is False and r["fit"] == "unrouted"
        assert seen(env["seen"]) == before, "the provider was called with the router off"
    finally:
        _settings(env["site"], env["fake_base"], router_on=True)


# ---- keeping, only on consent -------------------------------------------------------------------

def test_a_question_that_is_not_kept_leaves_no_trace(env):
    marker = "not-kept-marker"
    status, r = ask(env["base"], {"q": Q + " " + marker, "lang": "en", "keep": False,
                                  "anon": "abc123def456"})
    assert status == 200 and r["kept"] is False
    assert marker not in json.dumps(rows(env["file"]))


def test_a_kept_question_is_one_fixed_row(env):
    """
    The row is built from a fixed list, so a client that posts a business's takings, a name or a
    date of its own writes a row without them.
    """
    smuggled = {"q": Q + " kept-marker", "lang": "fa", "keep": True, "anon": "k3j9x0aa11bb22cc",
                "monthly_revenue": 48600, "name": "Cafe Sahar", "ip": "203.0.113.9",
                "at": "1990-01-01", "email": "owner@example.com"}
    status, r = ask(env["base"], smuggled)
    assert status == 200 and r["kept"] is True
    row = [x for x in rows(env["file"]) if "kept-marker" in x["q"]]
    assert len(row) == 1
    assert set(row[0]) == {"at", "lang", "q", "fit", "topic", "wedge", "variant", "anon"}
    assert row[0]["at"] != "1990-01-01" and len(row[0]["at"]) == 10
    assert (row[0]["fit"], row[0]["wedge"], row[0]["lang"]) == ("exact", "shop", "fa")
    blob = json.dumps(rows(env["file"]), ensure_ascii=False)
    for leak in ("48600", "Cafe Sahar", "203.0.113.9", "1990-01-01"):
        assert leak not in blob, f"{leak!r} reached the file"


def test_contact_details_reach_neither_the_provider_nor_the_file(env):
    q = ("تأمین‌کننده ۲۵٪ گران کرده. شمارهٔ من ۰۹۱۲ ۳۴۵ ۶۷۸۹ است، ایمیل owner@example.com "
         "و سایت https://example.ir/menu — ماهی ۳۰۰ میلیون فروش دارم scrub-marker")
    status, r = ask(env["base"], {"q": q, "lang": "fa", "keep": True, "anon": "scrub00scrub00"})
    assert status == 200 and r["kept"] is True
    row = [x for x in rows(env["file"]) if "scrub-marker" in x["q"]][0]
    sent = seen(env["seen"])
    for secret in ("۰۹۱۲", "۶۷۸۹", "owner@example.com", "example.ir"):
        assert secret not in row["q"], f"{secret} was kept"
        assert secret not in sent, f"{secret} was sent to the provider"
    # The amount is the question; it stays.
    assert "۳۰۰ میلیون" in row["q"]


def test_the_measurement_and_the_question_carry_different_ids():
    """The two files must not be joinable through the browser id."""
    home = (ROOT / "event_sim" / "wedge" / "templates" / "chooser.html").read_text(encoding="utf-8")
    report = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text(encoding="utf-8")
    assert "'dc_anon_q'" in home and "'dc_anon_q'" not in report
    assert "'dc_anon'" in report and "'dc_anon'" not in home


# ---- where it is offered -------------------------------------------------------------------------

def test_the_home_screen_offers_the_box_only_where_this_host_takes_questions(env):
    with urllib.request.urlopen(env["base"] + "/", timeout=20) as r:
        html = r.read().decode("utf-8")
    assert '<script id="ask-cfg" type="application/json">{"on":true,"route":true}</script>' in html
    readme = (PHP_ROOT / "README_DEPLOY.md").read_text("utf-8")
    assert "delete `ask.php`" in readme, "the opt-out is not documented"


def test_a_site_behind_the_password_keeps_the_box_behind_it(env):
    cfg = env["site"] / "config.php"
    cfg.write_text("<?php return ['password' => 'letmein'];\n", encoding="utf-8")
    try:
        assert ask(env["base"], {"q": Q, "lang": "en"})[0] == 403
    finally:
        cfg.unlink()


def test_the_maintainer_reads_kept_questions_as_text_never_as_markup(env):
    """The list in admin.php shows what strangers typed. It must arrive as text."""
    import http.cookiejar
    qfile = env["file"]
    qfile.parent.mkdir(parents=True, exist_ok=True)
    planted = {"at": "2026-09-10", "lang": "en", "q": "<script>alert(1)</script> admin-marker",
               "fit": "none", "topic": "other", "wedge": None, "variant": None, "anon": "adm00adm00adm0"}
    with qfile.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(planted) + "\n")
    cfg = env["site"] / "config.php"
    cfg.write_text("<?php return ['admin_password' => 'maint'];\n", encoding="utf-8")
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        opener.open(urllib.request.Request(env["base"] + "/admin.php",
                                           data=b"admin_password=maint", method="POST"), timeout=20)
        page = opener.open(env["base"] + "/admin.php", timeout=20).read().decode("utf-8")
        assert "Questions owners asked" in page
        assert "admin-marker" in page, "the kept question is not listed"
        assert "<script>alert(1)</script>" not in page
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
        assert 'name="feature_question_router"' in page, "the router cannot be switched"
    finally:
        cfg.unlink()
