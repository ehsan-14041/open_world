<?php
/**
 * "Did this help?" — answered on purpose, after a decision sheet.
 *
 * The page lists every field of the row before the owner presses send, and this file writes
 * exactly that list and nothing more: fixed answers, a scrubbed free-text line, the day, the
 * build this host is serving, the invitation tag the owner arrived with (if any), and a random
 * id the browser made for this purpose alone. No IP address, no business figures, no name.
 *
 * A contact is written only when the owner chose "book", typed one, and ticked that it may be
 * kept — and then to a separate file, so it can be deleted on request without losing the answer.
 *
 * A host that does not want feedback sets 'feedback' => false in config.php, or deletes this
 * file; the card disappears either way.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/compat.php';
require_once __DIR__ . '/lib/router.php';
require_once __DIR__ . '/lib/feedback.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

const FEEDBACK_MAX_BODY = 4096;

function feedback_fail(int $code, string $why): void
{
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $why]);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    feedback_fail(405, 'post only');
}

$config = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
if (!feedback_on($config)) {
    feedback_fail(404, 'off');
}
if ((string) ($config['password'] ?? '') !== '') {
    session_start();
    if (empty($_SESSION['unlocked'])) {
        feedback_fail(403, 'locked');
    }
}

$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > FEEDBACK_MAX_BODY) {
    feedback_fail(413, 'too large');
}
$in = json_decode((string) $raw, true);
if (!is_array($in)) {
    feedback_fail(400, 'not json');
}

$trades = is_file(__DIR__ . '/assets/trades.json')
    ? json_decode((string) file_get_contents(__DIR__ . '/assets/trades.json'), true) : [];
$known = [
    'wedges' => array_values(array_filter((array) ($trades['wedges'] ?? []), 'is_string')),
    'variants' => array_values(array_filter((array) ($trades['variants'] ?? []), 'is_string')),
];

// A contact comes only with the box beside it ticked; without it the answer is kept, the contact not.
if (($in['keep_contact'] ?? false) !== true) {
    unset($in['contact']);
}
$clean = feedback_clean($in, $known, feedback_offer($config), feedback_build(), 'router_scrub');
if (is_string($clean)) {
    feedback_fail(400, $clean);
}
[$row, $booking] = $clean;

if (!feedback_append(FEEDBACK_FILE, $row)) {
    feedback_fail(503, 'not accepting');
}
$booked = $booking !== null && feedback_append(BOOKINGS_FILE, $booking);

echo json_encode(['ok' => true, 'booked' => $booked]);
