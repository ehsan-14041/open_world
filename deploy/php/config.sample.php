<?php
/**
 * Rename this file to config.php on the server.
 *
 * password:              visitor gate. Empty ('') makes the report public. A non-empty value keeps a
 *                        pre-customer demo off the open web. It is not authentication.
 * heading:               shown on the password screen only.
 * allow_custom_reports:  false hides the intake form at ?new=1 and serves only the demo.
 * admin_password:        unlocks admin.php, where the LLM settings live. Leave empty and the admin
 *                        page refuses to load at all. Use a different value from `password`.
 *
 * The three llm_* keys are optional. Set them here if you would rather your API key lived in a PHP
 * file (which the server executes and never serves) than in data/settings.json. Anything set here
 * wins over the admin page, and the admin page shows the key as read-only.
 */
return [
    'password' => 'change-me',
    'heading'  => 'Decision Comparison',
    'allow_custom_reports' => true,

    'admin_password' => '',

    // 'llm_api_key'  => '',
    // 'llm_base_url' => 'https://api.openai.com/v1',
    // 'llm_model'    => '',
];
