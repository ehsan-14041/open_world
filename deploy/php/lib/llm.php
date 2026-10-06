<?php
/**
 * Maintainer-configured LLM access.
 *
 * Deliberate boundaries, because the product's claim is that its numbers are not produced by a
 * language model and the page says so to the customer:
 *
 *   - the model NEVER produces, adjusts or ranks a number. It translates copy, it reads a
 *     free-text description into form fields the owner then confirms, and it sorts a typed
 *     question into one of the questions the tool can answer (fields only — the page writes
 *     every word the owner reads). Nothing else.
 *   - the API key lives in a file the web server is told not to serve, and is never rendered
 *     into a page, never sent to a browser, never written to the usage log.
 *   - a visitor's page view never calls the API. Translation is generated once by the
 *     maintainer and cached to disk; serving a translated report is a file read.
 *   - with `enabled` false, or no key, every entry point here returns a plain failure and the
 *     product behaves exactly as it does without an LLM.
 *
 * The client speaks the OpenAI chat-completions shape against a configurable base URL, so it
 * works with any compatible gateway or proxy.
 */
declare(strict_types=1);

const SETTINGS_FILE = __DIR__ . '/../data/settings.json';
const USAGE_FILE = __DIR__ . '/../data/llm_usage.json';

const LLM_DEFAULTS = [
    'enabled' => false,
    'base_url' => 'https://api.avalai.ir/v1',
    'api_key' => '',
    'model' => '',
    'timeout_seconds' => 60,
    'max_output_tokens' => 4000,
    'monthly_call_cap' => 200,
    'features' => ['translation' => true, 'intake_assistant' => false, 'question_router' => false],
];

function llm_settings(array $config = []): array
{
    $stored = [];
    if (is_file(SETTINGS_FILE)) {
        $stored = json_decode((string) file_get_contents(SETTINGS_FILE), true)['llm'] ?? [];
    }
    $llm = array_merge(LLM_DEFAULTS, is_array($stored) ? $stored : []);
    $llm['features'] = array_merge(LLM_DEFAULTS['features'], $llm['features'] ?? []);

    // config.php wins over the stored settings, so a maintainer who would rather keep the key
    // in a PHP file (never served, even if the web server is misconfigured) can.
    foreach (['api_key', 'base_url', 'model'] as $key) {
        if (!empty($config['llm_' . $key])) {
            $llm[$key] = (string) $config['llm_' . $key];
            $llm['key_from_config'] = $key === 'api_key' ? true : ($llm['key_from_config'] ?? false);
        }
    }
    return $llm;
}

function llm_save_settings(array $llm): bool
{
    $all = is_file(SETTINGS_FILE)
        ? (json_decode((string) file_get_contents(SETTINGS_FILE), true) ?: [])
        : [];
    unset($llm['key_from_config']);
    $all['llm'] = $llm;
    @mkdir(dirname(SETTINGS_FILE), 0775, true);
    $ok = @file_put_contents(SETTINGS_FILE, json_encode($all, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)) !== false;
    if ($ok) {
        @chmod(SETTINGS_FILE, 0600);
    }
    return $ok;
}

/** Show a key as evidence it is set, without disclosing it. */
function llm_mask_key(string $key): string
{
    if ($key === '') {
        return 'not set';
    }
    return strlen($key) <= 8 ? str_repeat('•', strlen($key)) : substr($key, 0, 3) . str_repeat('•', 8) . substr($key, -4);
}

function llm_configured(array $llm): bool
{
    return !empty($llm['enabled']) && $llm['api_key'] !== '' && $llm['model'] !== '';
}

function llm_feature_on(array $llm, string $feature): bool
{
    return llm_configured($llm) && !empty($llm['features'][$feature]);
}

// ---- usage accounting ----------------------------------------------------------------------

function llm_usage(): array
{
    $usage = is_file(USAGE_FILE) ? json_decode((string) file_get_contents(USAGE_FILE), true) : [];
    return is_array($usage) ? $usage : [];
}

function llm_usage_this_month(string $month): int
{
    return (int) (llm_usage()[$month]['calls'] ?? 0);
}

function llm_record_call(string $month, int $inputTokens, int $outputTokens): void
{
    $usage = llm_usage();
    $row = $usage[$month] ?? ['calls' => 0, 'input_tokens' => 0, 'output_tokens' => 0];
    $usage[$month] = [
        'calls' => $row['calls'] + 1,
        'input_tokens' => $row['input_tokens'] + $inputTokens,
        'output_tokens' => $row['output_tokens'] + $outputTokens,
    ];
    @mkdir(dirname(USAGE_FILE), 0775, true);
    @file_put_contents(USAGE_FILE, json_encode($usage, JSON_PRETTY_PRINT));
}

// ---- the call ------------------------------------------------------------------------------

/**
 * One chat completion.
 *
 * @return array{ok:bool, text:string, error:string, usage:array}
 */
function llm_chat(array $llm, string $system, string $user, array $options = []): array
{
    $fail = static function ($why) {
        return ['ok' => false, 'text' => '', 'error' => $why, 'usage' => []];
    };

    if (!llm_configured($llm)) {
        return $fail('The LLM is not configured. Set a key and a model in the admin page.');
    }
    $month = gmdate('Y-m');
    $cap = (int) $llm['monthly_call_cap'];
    if ($cap > 0 && llm_usage_this_month($month) >= $cap) {
        return $fail("The monthly cap of $cap calls has been reached. Raise it in the admin page if that is intended.");
    }

    $wantsJson = !empty($options['json']);
    $body = [
        'model' => $llm['model'],
        'messages' => [
            ['role' => 'system', 'content' => $system],
            ['role' => 'user', 'content' => $user],
        ],
        'max_tokens' => (int) ($options['max_output_tokens'] ?? $llm['max_output_tokens']),
        'temperature' => $options['temperature'] ?? 0,
    ];
    if ($wantsJson) {
        $body['response_format'] = ['type' => 'json_object'];
    }

    $url = rtrim((string) $llm['base_url'], '/') . '/chat/completions';
    $payload = json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $headers = ['Content-Type: application/json', 'Authorization: Bearer ' . $llm['api_key']];
    $timeout = max(5, (int) $llm['timeout_seconds']);

    [$raw, $status, $transportError] = llm_post($url, $payload, $headers, $timeout);
    if ($transportError !== '') {
        return $fail($transportError);
    }
    $decoded = json_decode((string) $raw, true);

    // Not every gateway or model behind one accepts response_format. Rather than make the
    // maintainer discover that through a failure, drop the hint and ask once more — both
    // callers already tolerate a reply that is JSON without being promised as JSON.
    if ($wantsJson && ($status < 200 || $status >= 300)
        && stripos(json_encode($decoded['error'] ?? []), 'response_format') !== false) {
        unset($body['response_format']);
        $retryPayload = json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        [$raw, $status, $transportError] = llm_post($url, $retryPayload, $headers, $timeout);
        if ($transportError !== '') {
            return $fail($transportError);
        }
        $decoded = json_decode((string) $raw, true);
    }

    if ($status < 200 || $status >= 300) {
        $message = $decoded['error']['message'] ?? ('HTTP ' . $status);
        // Never echo the request back; it carries the key in a header.
        return $fail('The provider rejected the request: ' . llm_redact((string) $message, (string) $llm['api_key']));
    }
    $text = $decoded['choices'][0]['message']['content'] ?? null;
    if (!is_string($text) || $text === '') {
        return $fail('The provider returned no text. Check the model name.');
    }

    $usage = [
        'input_tokens' => (int) ($decoded['usage']['prompt_tokens'] ?? 0),
        'output_tokens' => (int) ($decoded['usage']['completion_tokens'] ?? 0),
    ];
    llm_record_call($month, $usage['input_tokens'], $usage['output_tokens']);
    return ['ok' => true, 'text' => $text, 'error' => '', 'usage' => $usage];
}

/** A key echoed back inside an error message must not reach a page. */
function llm_redact(string $text, string $key): string
{
    return $key === '' ? $text : str_replace($key, '[redacted]', $text);
}

/** @return array{0:string,1:int,2:string} body, status, transport error */
function llm_post(string $url, string $payload, array $headers, int $timeout): array
{
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_CONNECTTIMEOUT => min(15, $timeout),
        ]);
        $raw = curl_exec($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = $raw === false ? ('Could not reach the provider: ' . curl_error($ch)) : '';
        curl_close($ch);
        return [(string) $raw, $status, $error];
    }

    if (!ini_get('allow_url_fopen')) {
        return ['', 0, 'This host has neither cURL nor allow_url_fopen, so it cannot call an API.'];
    }
    $context = stream_context_create(['http' => [
        'method' => 'POST',
        'header' => implode("\r\n", $headers),
        'content' => $payload,
        'timeout' => $timeout,
        'ignore_errors' => true,
    ]]);
    $raw = @file_get_contents($url, false, $context);
    $status = 0;
    foreach ($http_response_header ?? [] as $line) {
        if (preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $m)) {
            $status = (int) $m[1];
        }
    }
    if ($raw === false) {
        return ['', $status, 'Could not reach the provider.'];
    }
    return [(string) $raw, $status, ''];
}

/**
 * Model ids this key can actually use, from the OpenAI-compatible /models endpoint.
 *
 * Not every gateway exposes it. When it is missing the maintainer simply types the id, so a
 * failure here is reported as "could not list" rather than treated as a broken configuration.
 *
 * @return array{ok:bool, models:array<int,string>, error:string}
 */
function llm_models(array $llm): array
{
    if ($llm['api_key'] === '') {
        return ['ok' => false, 'models' => [], 'error' => 'Set an API key first.'];
    }
    $url = rtrim((string) $llm['base_url'], '/') . '/models';
    $headers = ['Authorization: Bearer ' . $llm['api_key']];
    $timeout = max(5, (int) $llm['timeout_seconds']);

    [$raw, $status, $transportError] = llm_get($url, $headers, $timeout);
    if ($transportError !== '') {
        return ['ok' => false, 'models' => [], 'error' => $transportError];
    }
    $decoded = json_decode((string) $raw, true);
    if ($status < 200 || $status >= 300 || !isset($decoded['data'])) {
        $message = $decoded['error']['message'] ?? ('HTTP ' . $status);
        return ['ok' => false, 'models' => [],
                'error' => 'Could not list models (' . llm_redact((string) $message, (string) $llm['api_key'])
                    . '). Type the model id instead.'];
    }
    $models = [];
    foreach ($decoded['data'] as $row) {
        if (!empty($row['id'])) {
            $models[] = (string) $row['id'];
        }
    }
    sort($models, SORT_NATURAL | SORT_FLAG_CASE);
    return ['ok' => true, 'models' => $models, 'error' => ''];
}

/** @return array{0:string,1:int,2:string} body, status, transport error */
function llm_get(string $url, array $headers, int $timeout): array
{
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_CONNECTTIMEOUT => min(15, $timeout),
        ]);
        $raw = curl_exec($ch);
        $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = $raw === false ? ('Could not reach the provider: ' . curl_error($ch)) : '';
        curl_close($ch);
        return [(string) $raw, $status, $error];
    }
    if (!ini_get('allow_url_fopen')) {
        return ['', 0, 'This host has neither cURL nor allow_url_fopen, so it cannot call an API.'];
    }
    $context = stream_context_create(['http' => [
        'method' => 'GET', 'header' => implode("

", $headers),
        'timeout' => $timeout, 'ignore_errors' => true,
    ]]);
    $raw = @file_get_contents($url, false, $context);
    $status = 0;
    foreach ($http_response_header ?? [] as $line) {
        if (preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $m)) {
            $status = (int) $m[1];
        }
    }
    return $raw === false ? ['', $status, 'Could not reach the provider.'] : [(string) $raw, $status, ''];
}

/** Base URLs known to speak this shape, offered in the admin page. */
const LLM_PRESETS = [
    'AvalAI' => 'https://api.avalai.ir/v1',
    'OpenAI' => 'https://api.openai.com/v1',
];

/** A cheap round trip that proves the key, the base URL and the model name all work. */
function llm_test(array $llm): array
{
    $result = llm_chat($llm, 'Reply with the single word: ready', 'Say ready.',
        ['max_output_tokens' => 16]);
    if ($result['ok']) {
        $result['text'] = trim($result['text']);
    }
    return $result;
}
