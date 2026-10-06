<?php
/**
 * A question in the owner's own words.
 *
 * The home screen offers a box: "ask your own question". What arrives here is sorted — if the
 * maintainer has switched the router on — into one of the questions this tool can answer with
 * numbers, or a topic it cannot. It is never answered here, and nothing in the reply is prose
 * from the provider: the page builds its sentence from the checked fields.
 *
 * It is kept only if the owner ticked "keep my question", and then as one fixed row:
 *
 *   * the text, after phone numbers, email and web addresses are removed — the same scrubbed
 *     text is all the provider ever sees;
 *   * the day, not the moment; the language; what it was sorted as;
 *   * a random id the browser made, different from the one a shared measurement carries, so
 *     the two files cannot be joined. No IP address, no business figures.
 *
 * A host that does not want questions deletes this file; the box disappears.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/compat.php';
require_once __DIR__ . '/lib/router.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const ASK_MAX_BYTES = 8 * 1024 * 1024;
const ASK_MAX_BODY = 4096;
const ASK_MAX_CHARS = 600;

function ask_fail(int $code, string $why): void
{
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $why]);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    ask_fail(405, 'post only');
}

$config = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
// A site behind the demo password keeps this behind it too, or anyone could spend its calls.
if ((string) ($config['password'] ?? '') !== '') {
    session_start();
    if (empty($_SESSION['unlocked'])) {
        ask_fail(403, 'locked');
    }
}

$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > ASK_MAX_BODY) {
    ask_fail(413, 'too large');
}
$in = json_decode((string) $raw, true);
if (!is_array($in)) {
    ask_fail(400, 'not json');
}

$q = trim((string) preg_replace('~\s+~u', ' ', (string) ($in['q'] ?? '')));
if (mb_strlen($q) < 3) {
    ask_fail(400, 'empty');
}
if (mb_strlen($q) > ASK_MAX_CHARS) {
    $q = mb_substr($q, 0, ASK_MAX_CHARS);
}
$lang = (string) ($in['lang'] ?? '');
if (!preg_match('/^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/i', $lang)) {
    $lang = 'und';
}
$keep = ($in['keep'] ?? false) === true;
$anon = (string) ($in['anon'] ?? '');
if ($keep && !preg_match('/^[a-z0-9]{8,32}$/', $anon)) {
    ask_fail(400, 'bad id');
}

// Scrubbed before it goes anywhere: to the provider, or to disk.
$clean = router_scrub($q);
$route = router_route(llm_settings($config), $clean, router_known());
$routed = !empty($route['routed']);
$fit = $routed ? $route['fit'] : 'unrouted';

$kept = false;
if ($keep) {
    if (!is_dir(QUESTIONS_DIR)) {
        @mkdir(QUESTIONS_DIR, 0775, true);
    }
    $full = is_file(QUESTIONS_FILE) && filesize(QUESTIONS_FILE) > ASK_MAX_BYTES;
    if (is_dir(QUESTIONS_DIR) && !$full) {
        // The row, in full. The page lists the same things before the owner ticks the box.
        $row = [
            'at' => gmdate('Y-m-d'),
            'lang' => strtolower($lang),
            'q' => $clean,
            'fit' => $fit,
            'topic' => $routed ? $route['topic'] : null,
            'wedge' => $routed ? $route['wedge'] : null,
            'variant' => $routed ? $route['variant'] : null,
            'anon' => $anon,
        ];
        $line = json_encode($row, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n";
        $kept = @file_put_contents(QUESTIONS_FILE, $line, FILE_APPEND | LOCK_EX) !== false;
    }
}

echo json_encode([
    'ok' => true,
    'routed' => $routed,
    'fit' => $fit,
    'wedge' => $routed ? $route['wedge'] : null,
    'variant' => $routed ? $route['variant'] : null,
    'shock' => $routed ? $route['shock'] : null,
    'price' => $routed ? $route['price'] : null,
    'reduce' => $routed ? $route['reduce'] : false,
    'topic' => $routed ? $route['topic'] : null,
    'kept' => $kept,
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
