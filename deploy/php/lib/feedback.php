<?php
/**
 * What owners chose to tell us after a comparison, and who asked to book the follow-up.
 *
 * Two append-only files under data/feedback/, kept apart on purpose:
 *
 *   feedback.jsonl  one row per "send": fixed fields, the day, the build, no contact, no IP,
 *                   no business figures. Safe to read, count and hand to whoever analyses it.
 *   bookings.jsonl  only rows where the owner chose "book", typed a contact and ticked that it
 *                   may be kept. The contact is personal data: it lives in its own file so it
 *                   can be deleted on request without touching the evidence.
 *
 * The reader here counts, it does not score: the scorecard in docs/pilot decides what a count
 * means, and it was fixed before any row existed.
 */
declare(strict_types=1);

const FEEDBACK_DIR = __DIR__ . '/../data/feedback';
const FEEDBACK_FILE = FEEDBACK_DIR . '/feedback.jsonl';
const BOOKINGS_FILE = FEEDBACK_DIR . '/bookings.jsonl';
const FEEDBACK_MAX_BYTES = 8 * 1024 * 1024;

/** The answers a row may carry. Anything else is refused, not stored. */
const FEEDBACK_CHOICES = [
    'real' => ['now', 'later', 'no'],
    'helped' => ['yes', 'partly', 'no'],
    'next' => ['A', 'B', 'C', 'D', 'test', 'undecided', 'nothing'],
    'offer' => ['book', 'maybe', 'no'],
];

/** The build this host is serving, as the first line of VERSION.txt says. */
function feedback_build(): string
{
    $path = __DIR__ . '/../VERSION.txt';
    $first = is_file($path) ? strtok((string) file_get_contents($path), "\n") : '';
    $first = trim((string) $first);
    return preg_match('/^[A-Za-z0-9._ :+-]{1,80}$/', $first) ? $first : 'unknown';
}

/** The price of the paid follow-up as the host wrote it, or null when none is offered. */
function feedback_offer(array $config)
{
    $p = trim((string) ($config['offer_price'] ?? ''));
    return $p === '' ? null : mb_substr($p, 0, 60);
}

/** Whether this host asks for feedback at all. On unless config.php says otherwise. */
function feedback_on(array $config): bool
{
    return is_file(__DIR__ . '/../feedback.php') && ($config['feedback'] ?? true) !== false;
}

/** The flow's field keys for one wedge, which are the only values "hardest number" may take. */
function feedback_fields(string $wedge): array
{
    $path = __DIR__ . '/../assets/' . $wedge . '.json';
    $w = is_file($path) ? json_decode((string) file_get_contents($path), true) : null;
    $keys = [];
    foreach ((array) ($w['copy']['flow'] ?? []) as $step) {
        foreach ((array) ($step['fields'] ?? []) as $f) {
            if (is_string($f)) {
                $keys[] = $f;
            }
        }
    }
    return $keys;
}

/**
 * Check one submitted row and return [row, booking|null], or a string saying what is wrong.
 * `$known` is ['wedges' => [...], 'variants' => [...]] as trades.json declares them.
 */
function feedback_clean(array $in, array $known, $offer, string $build, callable $scrub)
{
    $wedge = (string) ($in['wedge'] ?? '');
    if (!in_array($wedge, $known['wedges'], true)) {
        return 'unknown wedge';
    }
    $variant = isset($in['variant']) && $in['variant'] !== null ? (string) $in['variant'] : null;
    if ($variant !== null && !in_array($variant, $known['variants'], true)) {
        return 'unknown variant';
    }
    $lang = strtolower((string) ($in['lang'] ?? ''));
    if (!preg_match('/^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/', $lang)) {
        $lang = 'und';
    }
    $anon = (string) ($in['anon'] ?? '');
    if (!preg_match('/^[a-z0-9]{8,32}$/', $anon)) {
        return 'bad id';
    }
    $src = isset($in['src']) && $in['src'] !== null ? strtolower((string) $in['src']) : null;
    if ($src !== null && !preg_match('/^[a-z0-9_-]{1,24}$/', $src)) {
        $src = null;
    }

    $row = [
        'at' => gmdate('Y-m-d'),          // the day, not the moment
        'build' => $build,
        'wedge' => $wedge,
        'variant' => $variant,
        'lang' => $lang,
        'demo' => ($in['demo'] ?? false) === true,
        'src' => $src,
    ];
    foreach (FEEDBACK_CHOICES as $k => $allowed) {
        if ($k === 'offer' && $offer === null) {
            continue;
        }
        $v = $in[$k] ?? null;
        if ($v !== null && !in_array($v, $allowed, true)) {
            return 'bad ' . $k;
        }
        $row[$k] = $v;
    }
    $hard = $in['hard'] ?? null;
    if ($hard !== null && $hard !== 'none' && !in_array($hard, feedback_fields($wedge), true)) {
        return 'bad hard';
    }
    $row['hard'] = $hard;

    $missing = trim((string) preg_replace('~\s+~u', ' ', (string) ($in['missing'] ?? '')));
    if (mb_strlen($missing) > 500) {
        $missing = mb_substr($missing, 0, 500);
    }
    // The same scrub as a typed question: phone numbers, email and web addresses are removed
    // before the text is written anywhere. The contact field below is the only exception.
    $missing = $missing === '' ? null : $scrub($missing);
    $row['missing'] = $missing === '' ? null : $missing;
    $row['anon'] = $anon;

    $answered = false;
    foreach (['real', 'helped', 'next', 'hard', 'missing', 'offer'] as $k) {
        if (($row[$k] ?? null) !== null) {
            $answered = true;
        }
    }
    if (!$answered) {
        return 'empty';
    }

    $booking = null;
    $contact = trim((string) ($in['contact'] ?? ''));
    if ($offer !== null && $row['offer'] === 'book' && $contact !== '') {
        $booking = [
            'at' => $row['at'],
            'build' => $build,
            'wedge' => $wedge,
            'variant' => $variant,
            'lang' => $lang,
            'src' => $src,
            'price' => $offer,
            'contact' => mb_substr((string) preg_replace('~[\x00-\x1F\x7F]~u', '', $contact), 0, 120),
            'anon' => $anon,
        ];
    }
    return [$row, $booking];
}

/** Append one JSON row, or return false. */
function feedback_append(string $file, array $row): bool
{
    if (!is_dir(FEEDBACK_DIR)) {
        @mkdir(FEEDBACK_DIR, 0775, true);
    }
    if (!is_dir(FEEDBACK_DIR) || (is_file($file) && filesize($file) > FEEDBACK_MAX_BYTES)) {
        return false;
    }
    $line = json_encode($row, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n";
    return @file_put_contents($file, $line, FILE_APPEND | LOCK_EX) !== false;
}

/** Every row of a JSONL file, oldest first. A damaged line is skipped, not fatal. */
function feedback_rows(string $file): array
{
    if (!is_file($file)) {
        return [];
    }
    $out = [];
    foreach (file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [] as $line) {
        $row = json_decode($line, true);
        if (is_array($row)) {
            $out[] = $row;
        }
    }
    return $out;
}

/**
 * Counts for the admin page: per build, and within it per answer. Repeated sends from one
 * browser are counted once — its latest row — so a keen owner is one owner.
 */
function feedback_summary(array $rows): array
{
    $latest = [];
    foreach ($rows as $r) {
        $latest[(string) ($r['anon'] ?? '') . '|' . (string) ($r['wedge'] ?? '')] = $r;
    }
    $out = [];
    foreach ($latest as $r) {
        $b = (string) ($r['build'] ?? 'unknown');
        if (!isset($out[$b])) {
            $out[$b] = ['owners' => 0, 'own_numbers' => 0, 'counts' => [], 'src' => []];
        }
        $out[$b]['owners']++;
        if (empty($r['demo'])) {
            $out[$b]['own_numbers']++;
        }
        foreach (['real', 'helped', 'next', 'hard', 'offer'] as $k) {
            $v = $r[$k] ?? null;
            if ($v === null) {
                continue;
            }
            $out[$b]['counts'][$k][(string) $v] = ($out[$b]['counts'][$k][(string) $v] ?? 0) + 1;
        }
        $s = (string) ($r['src'] ?? '-');
        $out[$b]['src'][$s] = ($out[$b]['src'][$s] ?? 0) + 1;
    }
    krsort($out);
    return $out;
}

/** Rows as CSV text, columns in a fixed order. */
function feedback_csv(array $rows, array $cols): string
{
    $fh = fopen('php://temp', 'r+');
    fputcsv($fh, $cols);
    foreach ($rows as $r) {
        $line = [];
        foreach ($cols as $c) {
            $v = $r[$c] ?? '';
            $v = is_bool($v) ? ($v ? '1' : '0') : (string) $v;
            // A cell a spreadsheet would read as a formula is written as text.
            if ($v !== '' && strpos('=+-@', $v[0]) !== false) {
                $v = "'" . $v;
            }
            $line[] = $v;
        }
        fputcsv($fh, $line);
    }
    rewind($fh);
    return (string) stream_get_contents($fh);
}
