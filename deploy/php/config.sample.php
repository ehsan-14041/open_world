<?php
/**
 * Rename this file to config.php on the server.
 *
 * password: leave empty ('') to make the page public. Any non-empty value puts the report
 *           behind a single shared password — enough to keep a pre-customer demo off the open
 *           web and out of search results. It is not authentication; do not put anything
 *           genuinely confidential behind it.
 * heading:  shown on the password screen only.
 * allow_custom_reports: false hides the intake form at ?new=1 and serves only the demo.
 */
return [
    'password' => 'change-me',
    'heading'  => 'Decision Comparison',
    'allow_custom_reports' => true,
];
