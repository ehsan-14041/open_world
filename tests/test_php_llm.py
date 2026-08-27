"""
The LLM layer must not be able to reach a number.

The product's claim to a customer is that its figures are not produced by a language model, and
the page says so on screen. These tests hold the boundary that makes the claim true:

  * a translation becomes one more block of copy inside the bundle, so a translated report
    carries byte-identical figures to the English one — there is nothing else it can touch;
  * a translation that damages a `{...}` slot or the inline markup is rejected rather than
    shipped, so a broken substitution cannot reach a page;
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
    """A generated language may add copy to the bundle and may change nothing else."""
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
$translation = json_decode(file_get_contents('{Path(tmp).as_posix()}/t.json'), true);
list($merged, $applied, $skipped) = i18n_merge($bundle, $translation);
file_put_contents('{out.as_posix()}', json_encode([
    'english' => $bundle,
    'other'   => $merged,
    'applied' => $applied,
    'skipped' => $skipped,
]));
""")
        pair = json.loads(out.read_text(encoding="utf-8"))

    assert pair["applied"] > 50, f"the catalogue should mostly apply (skipped {pair['skipped']})"
    english, other = pair["english"], pair["other"]

    # Everything that is not copy is the same object, key for key and byte for byte.
    assert set(english) == set(other)
    for key in english:
        if key != "i18n":
            assert english[key] == other[key], f"a translation reached {key}"

    # The English copy is untouched, and the new language really is translated.
    assert other["i18n"]["strings"]["en"] == english["i18n"]["strings"]["en"]
    block = other["i18n"]["strings"]["xx"]
    assert block["dir"] == "rtl"
    assert block["ui"]["home_lede"].startswith("TRANSLATED")
    assert block["wedge"]["headline"].startswith("TRANSLATED")
    assert {"code": "xx", "label": "Test", "dir": "rtl"} in other["i18n"]["languages"]
    assert other["i18n"]["default"] == "xx"


def test_a_translation_that_has_drifted_from_the_build_is_not_applied():
    """
    An id whose English no longer matches the build is skipped, not written.

    A maintainer's translation outlives the copy it was generated from. Writing a stale string
    into a page that has since changed would put an answer next to the wrong question.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.json"
        stale = {"code": "xx", "label": "Test", "dir": "ltr", "strings": {
            "ui.home_lede": "fine",
            "ui.no_such_key_at_all": "invented",
            "wedges.cafe.no_such_key": "invented",
        }}
        (Path(tmp) / "t.json").write_text(json.dumps(stale), encoding="utf-8")
        run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/i18n.php';
require '{PHP_ROOT.as_posix()}/lib/report.php';
$wedge = json_decode(file_get_contents('{PHP_ROOT.as_posix()}/assets/cafe.json'), true);
$bundle = build_bundle(new Slice($wedge['slice']), $wedge, new Baseline($wedge['demo'], $wedge), false);
$t = json_decode(file_get_contents('{Path(tmp).as_posix()}/t.json'), true);
list($merged, $applied, $skipped) = i18n_merge($bundle, $t);
file_put_contents('{out.as_posix()}', json_encode([
    'applied' => $applied, 'skipped' => $skipped,
    'lede' => $merged['i18n']['strings']['xx']['ui']['home_lede'],
    'keys' => array_keys($merged['i18n']['strings']['xx']['ui']),
]));
""")
        r = json.loads(out.read_text(encoding="utf-8"))

    assert r["applied"] == 1 and r["skipped"] == 2
    assert r["lede"] == "fine"
    assert "no_such_key_at_all" not in r["keys"], "a translation invented a string"


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
    # Whether the shipped copy happens to contain inline markup is a copy decision; the
    # rejection rule has to hold either way, so the specimen is built rather than found.
    with_ph = next(e for e in catalogue() if e["placeholders"])
    with_tag = {"id": "specimen", "text": "Ranked first in <b>130</b> of 162 tested cases",
                "placeholders": [], "tags": ["<b>", "</b>"]}
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
    case 'placeholder_removed':    $candidate = preg_replace('/\\{{\\w+(?::[^}}]*)?\\}}/', 'N', $text); break;
    case 'placeholder_added':      $candidate = $text . ' {{money}}'; break;
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
    """The catalogue is the authored copy, addressed by path — not text scraped off a page."""
    from event_sim.wedge.i18n import DEFAULT_LANGUAGE, catalogue as authored

    entries = catalogue()
    assert len(entries) > 50
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "a path must address exactly one string"

    source = authored(DEFAULT_LANGUAGE)
    for e in entries:
        assert "=>" not in e["text"] and "document." not in e["text"]
        node = source
        for part in e["id"].split("."):
            assert isinstance(node, dict) and part in node, f"{e['id']} is not in the catalogue"
            node = node[part]
        assert node == e["text"], f"{e['id']} has drifted from the authored copy"


def test_the_catalogue_offers_no_way_to_translate_a_setting():
    """
    Some strings are read by the page, not by a person.

    A writing direction, a numeral system or a language tag decides how the page behaves. A
    model asked to "translate" one would return something the page cannot act on, so they are
    never offered.
    """
    machine = {"ltr", "rtl", "latn", "arabext", "en", "fa"}
    for e in catalogue():
        leaf = e["id"].rsplit(".", 1)[-1]
        assert leaf not in ("dir", "numerals", "lang"), f"{e['id']} is a setting, not copy"
        assert e["text"] not in machine, f"{e['id']} carries a machine value"
