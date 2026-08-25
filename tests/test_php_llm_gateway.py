"""
Compatibility with an OpenAI-shaped gateway, exercised against a real HTTP server.

The target here is AvalAI (https://api.avalai.ir/v1), which speaks the OpenAI chat-completions
shape: Bearer auth, /chat/completions, `choices[0].message.content`, and a `usage` object with
prompt_tokens / completion_tokens. Any gateway with that shape works the same way.

Two behaviours a real gateway shows that a naive client does not survive, and which no amount
of reading documentation would have settled:

  * `response_format: {"type": "json_object"}` is not universally supported — some gateways or
    the models behind them reject the whole request because of it;
  * a model wraps its JSON in a ``` fence even when told not to.

The stub below does both, deliberately, so the client's fallback and fence-stripping are held
in place by a test rather than by having been observed working once.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PHP_ROOT = ROOT / "deploy" / "php"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="php CLI not on PATH")

GATEWAY = """<?php
// Stands in for an OpenAI-shaped gateway, misbehaving the way real ones do.
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (($_SERVER['HTTP_AUTHORIZATION'] ?? '') !== 'Bearer test-key') {
    http_response_code(401);
    header('Content-Type: application/json');
    echo json_encode(['error' => ['message' => 'bad or missing Bearer token']]);
    return true;
}
if ($path === '/v1/models') {
    header('Content-Type: application/json');
    echo json_encode(['data' => [['id' => 'gpt-5.5'], ['id' => 'gpt-4o-mini']]]);
    return true;
}
if ($path !== '/v1/chat/completions') {
    http_response_code(404);
    echo 'no such endpoint';
    return true;
}
$req = json_decode(file_get_contents('php://input'), true);
if (isset($req['response_format'])) {
    http_response_code(400);
    header('Content-Type: application/json');
    echo json_encode(['error' => ['message' => "Unsupported parameter: 'response_format'."]]);
    return true;
}
header('Content-Type: application/json');
echo json_encode([
    'choices' => [['message' => ['content' => "```json\\n{\\"ok\\": true}\\n```"]]],
    'usage' => ['prompt_tokens' => 11, 'completion_tokens' => 22],
]);
return true;
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    root = tmp_path_factory.mktemp("gateway")
    router = root / "router.php"
    router.write_text(GATEWAY, encoding="utf-8")
    port = free_port()
    proc = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", str(root), str(router)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.terminate()
        pytest.skip("could not start the stub gateway")
    yield f"http://127.0.0.1:{port}/v1"
    proc.terminate()
    proc.wait(timeout=10)


def run_php(code: str, cwd: Path) -> str:
    driver = PHP_ROOT / "_test_gateway_driver.php"
    driver.write_text("<?php\n" + code, encoding="utf-8")
    try:
        proc = subprocess.run(["php", str(driver)], capture_output=True, text=True,
                              check=False, cwd=str(cwd))
    finally:
        driver.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout


def call(base_url: str, tmp_path: Path, json_mode: bool, key: str = "test-key") -> dict:
    # A scratch data dir keeps the usage log out of the working tree.
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/llm.php';
$llm = array_merge(LLM_DEFAULTS, [
    'enabled' => true, 'api_key' => '{key}', 'model' => 'gpt-5.5',
    'base_url' => '{base_url}', 'monthly_call_cap' => 0,
]);
$r = llm_chat($llm, 'system', 'user', ['json' => {'true' if json_mode else 'false'}]);
echo json_encode($r);
""", tmp_path)
    return json.loads(out)


def test_a_gateway_that_refuses_json_mode_still_works(gateway, tmp_path):
    """The client drops response_format and asks again rather than failing the feature."""
    result = call(gateway, tmp_path, json_mode=True)
    assert result["ok"], result["error"]
    assert result["usage"] == {"input_tokens": 11, "output_tokens": 22}


def test_a_fenced_reply_is_still_parsed(gateway, tmp_path):
    result = call(gateway, tmp_path, json_mode=True)
    stripped = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/i18n.php';
echo i18n_strip_fence(json_decode(<<<'JSON'
{json.dumps(result["text"])}
JSON, true));
""", tmp_path)
    assert json.loads(stripped) == {"ok": True}


def test_a_bad_key_is_reported_and_never_echoed(gateway, tmp_path):
    result = call(gateway, tmp_path, json_mode=False, key="wrong-key-secret")
    assert not result["ok"]
    assert "Bearer" in result["error"] or "token" in result["error"]
    assert "wrong-key-secret" not in result["error"]


def test_models_can_be_listed_from_the_gateway(gateway, tmp_path):
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/llm.php';
$llm = array_merge(LLM_DEFAULTS, [
    'enabled' => true, 'api_key' => 'test-key', 'model' => 'x', 'base_url' => '{gateway}',
]);
echo json_encode(llm_models($llm));
""", tmp_path)
    result = json.loads(out)
    assert result["ok"], result["error"]
    assert result["models"] == ["gpt-4o-mini", "gpt-5.5"]


def test_the_shipped_default_points_at_avalai():
    out = run_php(f"""
require '{PHP_ROOT.as_posix()}/lib/llm.php';
echo json_encode(['default' => LLM_DEFAULTS['base_url'], 'presets' => LLM_PRESETS]);
""", ROOT)
    result = json.loads(out)
    assert result["default"] == "https://api.avalai.ir/v1"
    assert result["presets"]["AvalAI"] == "https://api.avalai.ir/v1"
