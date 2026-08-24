<?php
/**
 * The cafe decision comparison, generated on the host.
 *
 * Routes:
 *   GET  /            the demo cafe
 *   GET  /?new=1      the intake form
 *   POST /            generate a report for the submitted numbers
 *
 * The report is built here — engine, accounting, 162-point sweep, rendering — by lib/, which
 * is a port of the Python pipeline verified to produce a byte-identical bundle. Nothing is
 * stored except an optional gzip cache keyed by a hash of the inputs.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/report.php';

$config   = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
$password = (string) ($config['password'] ?? '');
$heading  = (string) ($config['heading'] ?? 'Decision Comparison');
$allowCustom = (bool) ($config['allow_custom_reports'] ?? true);

// ---- password gate -------------------------------------------------------------------------
if ($password !== '') {
    session_start();
    if (isset($_GET['logout'])) {
        $_SESSION = [];
        session_destroy();
        header('Location: ' . strtok($_SERVER['REQUEST_URI'], '?'));
        exit;
    }
    if (empty($_SESSION['unlocked'])) {
        $error = '';
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['password'])) {
            if (hash_equals($password, (string) $_POST['password'])) {
                session_regenerate_id(true);
                $_SESSION['unlocked'] = true;
                header('Location: ' . $_SERVER['REQUEST_URI']);
                exit;
            }
            usleep(700000);          // deliberate delay; this is a demo gate, not authentication
            $error = 'That is not the password.';
        }
        header('Content-Type: text/html; charset=utf-8');
        header('Cache-Control: no-store');
        include __DIR__ . '/unlock.php';
        exit;
    }
}

// ---- inputs --------------------------------------------------------------------------------
const FIELDS = [
    'name' => ['Business name', '', 'Only used on the report.', 'text'],
    'monthly_revenue' => ['Monthly sales', '$', 'A typical month, before the cost increase.', 'number'],
    'daily_orders' => ['Orders per day', '', 'Average transactions a day.', 'number'],
    'monthly_cogs' => ['Monthly ingredient cost', '$', 'What you pay suppliers for what you sell. Not wages, not rent.', 'number'],
    'monthly_fixed_costs' => ['Monthly fixed costs', '$', 'Rent, wages, utilities, loans.', 'number'],
    'cash_on_hand' => ['Cash available', '$', 'In the business account today.', 'number'],
    'supplier_increase_pct' => ['Supplier cost increase', '%', 'As a percentage of your ingredient cost.', 'number'],
    'low_margin_share_pct' => ['Orders on low-margin items', '%', 'A rough guess is fine — it is tested as an assumption.', 'number'],
];

$frozen = json_decode((string) file_get_contents(__DIR__ . '/assets/frozen.json'), true);
if (!is_array($frozen)) {
    http_response_code(500);
    exit('assets/frozen.json is missing or unreadable. Upload the whole bundle.');
}

$wantsForm = isset($_GET['new']) && $allowCustom;
$submitted = $_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['monthly_revenue']) && $allowCustom;
$errors = [];
$input = $frozen['demo_cafe'];

if ($submitted) {
    $input = ['name' => trim((string) ($_POST['name'] ?? '')) ?: 'Your cafe', 'is_demo' => false, 'notes' => []];
    foreach (FIELDS as $key => $meta) {
        if ($key === 'name') {
            continue;
        }
        $raw = str_replace([',', ' '], '', (string) ($_POST[$key] ?? ''));
        if ($raw === '' || !is_numeric($raw)) {
            $errors[] = $meta[0] . ' must be a number.';
            $input[$key] = 0.0;
        } else {
            $input[$key] = (float) $raw;
        }
    }
    if (!$errors) {
        $errors = (new Baseline($input))->validate();
    }
    if ($errors) {
        $wantsForm = true;
    }
}

if ($wantsForm) {
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    include __DIR__ . '/intake.php';
    exit;
}

// ---- build (cached by a hash of the inputs) ------------------------------------------------
$baseline = new Baseline($input);
$cacheKey = hash('sha256', json_encode($baseline->toDict()) . '|' . filemtime(__DIR__ . '/assets/frozen.json')
    . '|' . filemtime(__DIR__ . '/assets/decision_report.html'));
$cacheFile = __DIR__ . '/data/cache/' . $cacheKey . '.html.gz';

$gzipped = is_file($cacheFile) ? (string) file_get_contents($cacheFile) : '';
if ($gzipped === '') {
    $slice = new Slice($frozen['slice']);
    $bundle = build_bundle($slice, $frozen, $baseline, true);
    $html = render_html($bundle, __DIR__ . '/assets/decision_report.html');
    $gzipped = (string) gzencode($html, 9);
    @mkdir(__DIR__ . '/data/cache', 0775, true);
    @file_put_contents($cacheFile, $gzipped);     // best effort; a read-only host just rebuilds
}

header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header(($password !== '' || !$baseline->is_demo) ? 'Cache-Control: no-store, private' : 'Cache-Control: public, max-age=300');

$wantsGzip = stripos((string) ($_SERVER['HTTP_ACCEPT_ENCODING'] ?? ''), 'gzip') !== false;
if ($wantsGzip && !ini_get('zlib.output_compression')) {
    header('Content-Encoding: gzip');
    header('Vary: Accept-Encoding');
    header('Content-Length: ' . (string) strlen($gzipped));
    echo $gzipped;
} else {
    echo gzdecode($gzipped);
}
