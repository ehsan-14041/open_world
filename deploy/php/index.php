<?php
/**
 * Three decision products, generated on the host.
 *
 * Routes:
 *   GET  /                      the chooser — "What kind of business do you run?"
 *   GET  /?w=cafe|shop|salon    that wedge's demo report
 *   GET  /?w=<id>&lang=fa       the same report with translated copy
 *   GET  /?w=<id>&new=1         the intake form
 *   POST /                      generate a report for the submitted numbers
 *   POST / (assist)             draft the form fields from a typed description
 *
 * Each report is built here — engine, accounting, 162-point sweep, rendering — by lib/, which
 * is a port of the Python pipeline verified to produce a byte-identical bundle for all three.
 * Nothing is stored except a gzip cache keyed by a hash of the wedge, the inputs and the
 * language.
 */
declare(strict_types=1);

require_once __DIR__ . '/lib/compat.php';
require_once __DIR__ . '/lib/report.php';
require_once __DIR__ . '/lib/i18n.php';
require_once __DIR__ . '/lib/assist.php';

$config   = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
$password = (string) ($config['password'] ?? '');
$heading  = (string) ($config['heading'] ?? 'Decision Comparison');
$allowCustom = (bool) ($config['allow_custom_reports'] ?? true);
$llm = llm_settings($config);

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

// A quick way to confirm which build is deployed, without opening a report.
if (isset($_GET['version'])) {
    header('Content-Type: text/plain; charset=utf-8');
    $stamp = is_file(__DIR__ . '/VERSION.txt') ? file_get_contents(__DIR__ . '/VERSION.txt') : "no VERSION.txt
";
    echo $stamp . "running on PHP " . PHP_VERSION . "
";
    exit;
}

// ---- which wedge ---------------------------------------------------------------------------
$catalogue = json_decode((string) file_get_contents(__DIR__ . '/assets/wedges.json'), true);
$available = array_column($catalogue['chooser'] ?? [], 'id');

$wedgeId = preg_replace('/[^a-z]/', '', (string) ($_GET['w'] ?? $_POST['w'] ?? ''));
if ($wedgeId === '' || !in_array($wedgeId, $available, true)) {
    // No wedge chosen: show the chooser rather than guessing which business someone runs.
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: public, max-age=300');
    $chooser = (string) file_get_contents(__DIR__ . '/assets/chooser.html');
    $chooser = str_replace('__I18N__',
        json_encode($catalogue['i18n'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $chooser);
    // The static chooser links to files; here each card is a query on this one entry point.
    foreach ($catalogue['chooser'] as $entry) {
        $chooser = str_replace("{$entry['id']}/{$entry['id']}_decision_report.html",
                               "?w={$entry['id']}", $chooser);
    }
    echo $chooser;
    exit;
}

$wedge = json_decode((string) file_get_contents(__DIR__ . "/assets/{$wedgeId}.json"), true);
if (!is_array($wedge)) {
    http_response_code(500);
    exit("assets/{$wedgeId}.json is missing or unreadable. Upload the whole bundle.");
}

// ---- inputs --------------------------------------------------------------------------------
$fields = [];
foreach ($wedge['intake_fields'] as $f) {
    $fields[$f['key']] = [$f['label'], $f['unit'], $f['hint'], $f['key'] === 'name' ? 'text' : 'number'];
}

$languages = i18n_available();
$lang = preg_replace('/[^a-z0-9_-]/i', '', (string) ($_GET['lang'] ?? $_POST['lang'] ?? ''));
$translation = $lang !== '' ? i18n_load($lang) : null;

$assistOn = llm_feature_on($llm, 'intake_assistant');
$wantsForm = isset($_GET['new']) && $allowCustom;
$action = (string) ($_POST['form_action'] ?? '');
$submitted = $_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'run' && $allowCustom;
$assisting = $_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'assist' && $allowCustom && $assistOn;

$errors = [];
$assist = null;
$description = '';
$input = $wedge['demo'];

if ($assisting) {
    $description = (string) ($_POST['description'] ?? '');
    $assist = assist_extract($llm, $description, array_keys($fields));
    if ($assist['ok']) {
        $input = array_merge($input, ['name' => 'Your business', 'is_demo' => false], $assist['fields']);
    } else {
        $errors[] = $assist['error'];
    }
    $wantsForm = true;                          // always back to the form for the owner to check
} elseif ($submitted) {
    $input = ['name' => trim((string) ($_POST['name'] ?? '')) ?: 'Your business',
              'is_demo' => false, 'notes' => []];
    foreach ($fields as $key => $meta) {
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
        $errors = (new Baseline($input, $wedge))->validate();
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

// ---- build (cached by wedge, inputs and language) -------------------------------------------
$baseline = new Baseline($input, $wedge);
$templatePath = __DIR__ . '/assets/decision_report.html';
$langStamp = $translation !== null ? ($lang . '|' . ($translation['generated'] ?? '')) : 'en';
// The code that builds the page is part of what the page is. Leaving it out of the key means a
// maintainer who updates lib/ keeps being served the version from before the update.
$libStamp = '';
foreach (glob(__DIR__ . '/lib/*.php') ?: [] as $lib) {
    $libStamp .= basename($lib) . ':' . filemtime($lib) . ';';
}
$cacheKey = hash('sha256', $wedgeId . '|' . json_encode($baseline->toDict()) . '|' . $langStamp
    . '|' . filemtime(__DIR__ . "/assets/{$wedgeId}.json") . '|' . filemtime($templatePath)
    . '|' . $libStamp);
$cacheFile = __DIR__ . '/data/cache/' . $cacheKey . '.html.gz';

$gzipped = is_file($cacheFile) ? (string) file_get_contents($cacheFile) : '';
if ($gzipped === '') {
    $template = (string) file_get_contents($templatePath);
    $bundle = build_bundle(new Slice($wedge['slice']), $wedge, $baseline, true);
    if ($translation !== null) {
        // A generated language is one more block of copy inside the bundle. It sits beside the
        // figures rather than anywhere near them, so nothing it contains can change a number.
        [$bundle, , ] = i18n_merge($bundle, $translation);
    }
    $html = str_replace('__DATA__',
        str_replace('</', '<\\/', (string) json_encode($bundle,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION)),
        $template);
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
