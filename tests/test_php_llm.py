"""
The LLM layer must not be able to reach a number.

The product's claim to a customer is that its figures are not produced by a language model, and
the page says so on screen. These tests hold the boundary that makes the claim true:

  * translation runs on the template, before the data payload exists, so a translated report
    carries a byte-identical payload to the English one;
  * a translation that damages a `${...}` placeholder or the inline markup is rejected rather
    than shipped, so a broken substitution cannot reach a page;
  * with no configuration, every entry point declines and the product is unchanged.

They run against the PHP source directly and need no network and no API key.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"
CATALOGUE = PHP_ROOT / "assets" / "strings.json"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="php CLI not on PATH")


def run_php(code: str) -> str:
    driver = PHP_ROOT / "_test_llm_driver.php"
    driver.write_text("<?php\n" + code, encoding="utf-8")
    try:
        proc = subprocess.run(["php", str(driver)], capture_output=True, text=True, check=False)
    finally:
        driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout


def catalogue() -> list[dict]:
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))["strings"]


def test_a_translation_cannot_reach_the_data_payload():
    """The payload is injected after substitution, so the two languages must agree exactly."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pair.json"
        entries = catalogue()
        fake = {e["id"]: "TRANSLATED " + e["text"] for e in entries}
        translation = {"code": "xx", "label": "Test", "dir": "rtl", "strings": fake}
        (Path(tmp) / "t.json").write_text(json.dumps(translation), encoding="utf-8")

        run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/i18n.php';
require '{PHP_ROOT.as_posix()}/lib/report.php';
$wedge = json_decode(file_get_contents('{PHP_ROOT.as_posix()}/assets/cafe.json'), true);
$bundle = build_bundle(new Slice($wedge['slice']), $wedge, new Baseline($wedge['demo'], $wedge), false);
$data = str_replace('</', '<\\\\/', json_encode($bundle, JSON_PRESERVE_ZERO_FRACTION));
$template = file_get_contents('{PHP_ROOT.as_posix()}/assets/decision_report.html');
$translation = json_decode(file_get_contents('{Path(tmp).as_posix()}/t.json'), true);
list($translated, $applied, $skipped) = i18n_apply($template, $translation);
file_put_contents('{out.as_posix()}', json_encode([
    'english' => str_replace('__DATA__', $data, $template),
    'other'   => str_replace('__DATA__', $data, $translated),
    'applied' => $applied,
]));
""")
        pair = json.loads(out.read_text(encoding="utf-8"))

    assert pair["applied"] > 50, "the catalogue should mostly apply"
    marker = '<script id="data" type="application/json">'

    def payload(html: str) -> str:
        return html.split(marker, 1)[1].split("</script>", 1)[0]

    assert payload(pair["english"]) == payload(pair["other"])
    assert "TRANSLATED" not in payload(pair["other"])
    assert 'dir="rtl"' in pair["other"]
    # The copy really was replaced — both in the markup and in the script that renders it.
    assert "TRANSLATED" in pair["other"].split(marker, 1)[0]
    after_payload = pair["other"].split(marker, 1)[1].split("</script>", 1)[1]
    assert "TRANSLATED" in after_payload


@pytest.mark.parametrize("corruption,expect_rejected", [
    ("faithful", False),
    ("placeholder_removed", True),
    ("placeholder_added", True),
    ("placeholder_duplicated", True),
    ("tag_removed", True),
    ("tag_added", True),
    ("empty", True),
])
def test_a_damaged_translation_is_rejected(corruption, expect_rejected):
    entries = catalogue()
    with_ph = next(e for e in entries if e["placeholders"])
    with_tag = next(e for e in entries if e["tags"])
    entry = with_tag if corruption.startswith("tag") else with_ph

    payload = json.dumps({"entry": entry, "corruption": corruption})
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/i18n.php';
$in = json_decode(<<<'JSON'
{payload}
JSON, true);
$entry = $in['entry'];
$text = $entry['text'];
switch ($in['corruption']) {{
    case 'faithful':               $candidate = 'XX ' . $text; break;
    case 'placeholder_removed':    $candidate = preg_replace('/\\$\\{{[^}}]*\\}}/', 'N', $text); break;
    case 'placeholder_added':      $candidate = $text . ' ${{money(1)}}'; break;
    case 'placeholder_duplicated': $candidate = $text . ' ' . $entry['placeholders'][0]; break;
    case 'tag_removed':            $candidate = strip_tags($text); break;
    case 'tag_added':              $candidate = '<b>' . $text . '</b>'; break;
    case 'empty':                  $candidate = '   '; break;
}}
echo i18n_reject_reason($entry, $candidate);
""")
    assert (out.strip() != "") is expect_rejected, f"{corruption}: {out!r}"


def test_nothing_is_called_when_the_llm_is_not_configured():
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/assist.php';
$off = array_merge(LLM_DEFAULTS, ['enabled' => false, 'api_key' => 'x', 'model' => 'm']);
$noKey = array_merge(LLM_DEFAULTS, ['enabled' => true, 'api_key' => '', 'model' => 'm']);
echo json_encode([
    'configured_off'   => llm_configured($off),
    'configured_nokey' => llm_configured($noKey),
    'chat_off'         => llm_chat($off, 's', 'u')['ok'],
    'assist_off'       => assist_extract($off, 'we do 30000 a month', ['monthly_revenue'])['ok'],
    'feature_off'      => llm_feature_on($off, 'translation'),
]);
""")
    result = json.loads(out)
    assert result == {"configured_off": False, "configured_nokey": False, "chat_off": False,
                      "assist_off": False, "feature_off": False}


def test_an_api_key_is_never_rendered_in_full():
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/llm.php';
echo json_encode([
    'masked'  => llm_mask_key('sk-verysecretkeyvalue1234'),
    'short'   => llm_mask_key('abc'),
    'unset'   => llm_mask_key(''),
    'redact'  => llm_redact('bad key sk-verysecretkeyvalue1234 rejected', 'sk-verysecretkeyvalue1234'),
]);
""")
    result = json.loads(out)
    assert "verysecretkey" not in result["masked"]
    assert "verysecretkey" not in result["redact"]
    assert result["unset"] == "not set"
    assert set(result["short"]) == {"•"}


def test_the_catalogue_holds_copy_and_not_code():
    entries = catalogue()
    assert len(entries) > 50
    for e in entries:
        text = e["text"]
        assert "=>" not in text and "document." not in text and "textContent" not in text
        assert text[0].isalpha() or text.startswith("<")
    # Every catalogued string must appear exactly once in the template, or substitution is unsafe.
    template = (ROOT / "event_sim" / "cafe" / "templates" / "decision_report.html").read_text(encoding="utf-8")
    for e in entries:
        assert template.count(e["text"]) == 1, e["id"]
