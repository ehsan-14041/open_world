<?php
/**
 * Serves the cafe decision report on any PHP host.
 *
 * The report itself is a self-contained static page; PHP is here only to gzip it (1 MB -> ~75 KB)
 * and to keep a pre-customer demo off the open web behind a shared password.
 *
 * Set the password in config.php. With no config.php the page is public.
 */
declare(strict_types=1);

$config   = is_file(__DIR__ . '/config.php') ? (require __DIR__ . '/config.php') : [];
$password = (string) ($config['password'] ?? '');
$heading  = (string) ($config['heading'] ?? 'Decision Comparison');
// The payload carries a random name chosen at build time, so it stays unreachable even on a
// server that ignores .htaccess (nginx, the PHP dev server). Never link to it directly.
$found  = glob(__DIR__ . '/data/report-*.html.gz');
$report = $found ? $found[0] : '';

if ($report === '') {
    http_response_code(500);
    exit('The report file is missing from data/. Upload the whole bundle, not just index.php.');
}

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
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            if (hash_equals($password, (string) ($_POST['password'] ?? ''))) {
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

header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header($password !== '' ? 'Cache-Control: no-store, private' : 'Cache-Control: public, max-age=300');

$wantsGzip = stripos((string) ($_SERVER['HTTP_ACCEPT_ENCODING'] ?? ''), 'gzip') !== false;
$serverGzip = (bool) ini_get('zlib.output_compression');

if ($wantsGzip && !$serverGzip) {
    header('Content-Encoding: gzip');
    header('Vary: Accept-Encoding');
    header('Content-Length: ' . (string) filesize($report));
    readfile($report);
    exit;
}

if (!function_exists('gzdecode')) {
    http_response_code(500);
    exit('This host has no zlib extension. Ask the host to enable it, or serve the uncompressed report.');
}
echo gzdecode((string) file_get_contents($report));
