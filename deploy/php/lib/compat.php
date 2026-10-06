<?php
/**
 * Fail readably on a PHP that is too old, instead of with a parse error.
 *
 * This file is deliberately written in PHP 5-era syntax so it can be parsed by anything, and
 * it is included FIRST — before any file that uses newer syntax. PHP parses a whole file at
 * include time, so a version check sitting inside a modern file never gets the chance to run:
 * the parse error happens first, and the visitor sees a raw path from your server.
 *
 * The rest of the bundle targets PHP 7.1. Arrow functions and typed properties (both 7.4) were
 * deliberately kept out for exactly this reason — shared hosts are often years behind.
 */

define('WEDGE_MIN_PHP', '7.1.0');

if (version_compare(PHP_VERSION, WEDGE_MIN_PHP, '<')) {
    header('Content-Type: text/html; charset=utf-8');
    http_response_code(500);
    $have = htmlspecialchars(PHP_VERSION, ENT_QUOTES);
    $need = htmlspecialchars(WEDGE_MIN_PHP, ENT_QUOTES);
    echo <<<HTML
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>This host needs a newer PHP</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#F7F6F1;color:#1E2A30;
     font:17px/1.6 "Segoe UI",system-ui,-apple-system,sans-serif}
.box{max-width:520px;background:#fff;border:1px solid #DFE2DB;border-radius:16px;padding:32px}
h1{font-size:24px;margin:0 0 12px}
code{background:#EFEEE7;padding:2px 6px;border-radius:4px;font-size:15px}
ol{padding-left:20px} li{margin:6px 0}
p{color:#5B6B72}
</style></head><body><div class="box">
<h1>This host is running PHP $have</h1>
<p>The comparison needs <strong>PHP $need or newer</strong>. Nothing is wrong with the upload —
   the PHP version selected for this domain is simply older than the code.</p>
<ol>
  <li>Open your hosting control panel (DirectAdmin, cPanel or Plesk).</li>
  <li>Find <strong>PHP Version Selector</strong> — in DirectAdmin it is usually under
      <em>Account Manager</em>, in cPanel under <em>Select PHP Version</em>.</li>
  <li>Pick <strong>PHP 8.1</strong> or newer for this domain, and save.</li>
  <li>Reload this page.</li>
</ol>
<p>PHP 7.3 and everything before it stopped receiving security fixes years ago, so this is worth
   changing whether or not you use this tool.</p>
</div></body></html>
HTML;
    exit;
}
