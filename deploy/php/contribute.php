<?php
/**
 * One measurement, given on purpose.
 *
 * When an owner runs the two-week price test, the number they get back is the one thing this
 * product cannot look up anywhere: how much custom their own customers give up when the price
 * moves. Enough of those, and the borrowed estimate from a 2010 study of eating out in the
 * United States can be replaced with something measured here.
 *
 * That is only worth having if it is given rather than taken, so:
 *
 *   * nothing is sent unless the owner presses the button, and the page shows them the exact
 *     row first;
 *   * the row carries the measurement and nothing else — no revenue, no cash, no order counts,
 *     no name, no address, no IP. Those are on the owner's screen and they stay there;
 *   * the anonymous id is generated in the browser and is the only thing tying two rows
 *     together. It identifies a browser, not a person, and it exists so a repeated submission
 *     can be recognised rather than counted twice;
 *   * the file lives under data/, which the shipped .htaccess denies to the web.
 *
 * No database: a shared host has one of these more often than it has the other, and an
 * append-only file is easier to reason about and to hand over.
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

const CONTRIB_DIR = __DIR__ . '/data/contrib';
const CONTRIB_FILE = CONTRIB_DIR . '/measurements.jsonl';
const CONTRIB_MAX_BYTES = 4 * 1024 * 1024;   // ~30k rows; past that the host has a real dataset
const CONTRIB_MAX_BODY = 2048;

/** Wedges and trades a row may name, as this build declared them. */
function contrib_known(): array
{
    $path = __DIR__ . '/assets/trades.json';
    $all = is_file($path) ? json_decode((string) file_get_contents($path), true) : null;
    return [
        'wedges' => array_values(array_filter((array) ($all['wedges'] ?? []), 'is_string')),
        'variants' => array_values(array_filter((array) ($all['variants'] ?? []), 'is_string')),
    ];
}

function contrib_fail(int $code, string $why): void
{
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $why]);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    contrib_fail(405, 'post only');
}

$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > CONTRIB_MAX_BODY) {
    contrib_fail(413, 'too large');
}
$in = json_decode((string) $raw, true);
if (!is_array($in)) {
    contrib_fail(400, 'not json');
}

$known = contrib_known();
$wedge = (string) ($in['wedge'] ?? '');
$variant = isset($in['variant']) && $in['variant'] !== null ? (string) $in['variant'] : null;
$e = $in['e'] ?? null;
$rise = $in['rise'] ?? null;
$anon = (string) ($in['anon'] ?? '');

if (!in_array($wedge, $known['wedges'], true)) {
    contrib_fail(400, 'unknown wedge');
}
if ($variant !== null && !in_array($variant, $known['variants'], true)) {
    contrib_fail(400, 'unknown variant');
}
// An elasticity outside this range is not a measurement, it is a typo or a broken client.
if (!is_numeric($e) || !is_finite((float) $e) || (float) $e < 0 || (float) $e > 10) {
    contrib_fail(400, 'elasticity out of range');
}
if (!is_numeric($rise) || (float) $rise <= 0 || (float) $rise > 100) {
    contrib_fail(400, 'rise out of range');
}
if (!preg_match('/^[a-z0-9]{8,32}$/', $anon)) {
    contrib_fail(400, 'bad id');
}

if (!is_dir(CONTRIB_DIR)) {
    @mkdir(CONTRIB_DIR, 0775, true);
}
if (!is_dir(CONTRIB_DIR) || (is_file(CONTRIB_FILE) && !is_writable(CONTRIB_FILE))) {
    contrib_fail(503, 'not accepting');
}
if (is_file(CONTRIB_FILE) && filesize(CONTRIB_FILE) > CONTRIB_MAX_BYTES) {
    contrib_fail(507, 'full');
}

// The row, in full. This is every field that is written, and the page shows the owner the same
// list before they press anything.
$row = [
    'at' => gmdate('Y-m-d'),          // the day, not the moment: an hour is a movement pattern
    'wedge' => $wedge,
    'variant' => $variant,
    'e' => round((float) $e, 4),
    'rise' => round((float) $rise, 2),
    'anon' => $anon,
];

$line = json_encode($row, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n";
$ok = @file_put_contents(CONTRIB_FILE, $line, FILE_APPEND | LOCK_EX) !== false;
if (!$ok) {
    contrib_fail(503, 'could not write');
}

echo json_encode(['ok' => true]);
