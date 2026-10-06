<?php
/**
 * Translating the report's copy — never its numbers.
 *
 * A report bundle carries its languages inside it: one set of figures, computed once, and a
 * block of copy per language. A generated translation becomes another such block and nothing
 * else. That is the guarantee — not an ordering that has to be preserved by whoever edits the
 * page next, but the shape of the thing itself. No figure, ranking, count or fingerprint lives
 * under `i18n`, so a translation has nothing to reach.
 *
 * Each catalogued string is addressed by its path in the catalogue and carries its `{...}`
 * slots and its inline tags. A translation that drops one, invents one, or reorders the tag
 * structure is rejected and the English is kept for that string — a page in two languages is a
 * smaller failure than a page with a broken number or unclosed markup.
 */
declare(strict_types=1);

require_once __DIR__ . '/llm.php';

const I18N_DIR = __DIR__ . '/../data/i18n';
const CATALOGUE = __DIR__ . '/../assets/strings.json';
/** The language the catalogue is written in, and the base every translation starts from. */
const I18N_SOURCE = 'en';

/** Languages the maintainer has generated a translation for. */
function i18n_available(): array
{
    $out = [];
    foreach (glob(I18N_DIR . '/*.json') ?: [] as $path) {
        $data = json_decode((string) file_get_contents($path), true);
        if (!is_array($data) || empty($data['strings'])) {
            continue;
        }
        $code = basename($path, '.json');
        $out[$code] = [
            'code' => $code,
            'label' => (string) ($data['label'] ?? $code),
            'dir' => ($data['dir'] ?? 'ltr') === 'rtl' ? 'rtl' : 'ltr',
            'translated' => count($data['strings']),
            'total' => count(i18n_catalogue()),
            'generated' => (string) ($data['generated'] ?? ''),
            'model' => (string) ($data['model'] ?? ''),
        ];
    }
    ksort($out);
    return $out;
}

function i18n_catalogue(): array
{
    static $cache = null;
    if ($cache === null) {
        $data = is_file(CATALOGUE) ? json_decode((string) file_get_contents(CATALOGUE), true) : [];
        $cache = $data['strings'] ?? [];
    }
    return $cache;
}

function i18n_load(string $code): ?array
{
    $path = I18N_DIR . '/' . preg_replace('/[^a-z0-9_-]/i', '', $code) . '.json';
    if (!is_file($path)) {
        return null;
    }
    $data = json_decode((string) file_get_contents($path), true);
    return is_array($data) ? $data : null;
}

/**
 * A translation is usable only if it keeps every placeholder and every tag of the original.
 *
 * @return string '' when acceptable, otherwise the reason it was rejected
 */
function i18n_reject_reason(array $entry, string $translated): string
{
    if (trim($translated) === '') {
        return 'empty';
    }
    $placeholders = $entry['placeholders'] ?? [];
    foreach ($placeholders as $p) {
        if (substr_count($translated, $p) !== substr_count($entry['text'], $p)) {
            return 'placeholder ' . $p . ' lost or duplicated';
        }
    }
    if (preg_match_all('/\{\w+(?::[^}]*)?\}/', $translated, $found)) {
        if (count($found[0]) !== count($placeholders)) {
            return 'invented a placeholder';
        }
    } elseif ($placeholders) {
        return 'placeholders removed';
    }
    $originalTags = $entry['tags'] ?? [];
    preg_match_all('#</?[a-zA-Z][^>]*>#', $translated, $translatedTags);
    if (count($translatedTags[0]) !== count($originalTags)) {
        return 'inline markup changed';
    }
    foreach ($originalTags as $i => $tag) {
        if (($translatedTags[0][$i] ?? '') !== $tag) {
            return 'inline markup changed';
        }
    }
    return '';
}

/**
 * Fold a stored translation into the bundle as one more language.
 *
 * Every string starts as its English original, so a partly-translated language is a readable
 * page rather than a page with holes. Only `$bundle['i18n']` is touched.
 *
 * @return array{0:array, 1:int, 2:int} [bundle, applied, skipped]
 */
function i18n_merge(array $bundle, array $translation): array
{
    if (!isset($bundle['i18n']['strings'][I18N_SOURCE])) {
        return [$bundle, 0, 0];
    }
    $code = preg_replace('/[^a-z0-9-]/i', '', (string) ($translation['code'] ?? ''));
    if ($code === '' || $code === I18N_SOURCE) {
        return [$bundle, 0, 0];
    }
    $dir = ($translation['dir'] ?? 'ltr') === 'rtl' ? 'rtl' : 'ltr';
    $label = (string) ($translation['label'] ?? $code);

    $block = $bundle['i18n']['strings'][I18N_SOURCE];
    $block['dir'] = $dir;
    $block['label'] = $label;

    $byId = [];
    foreach (i18n_catalogue() as $entry) {
        $byId[$entry['id']] = $entry;
    }
    $applied = 0;
    $skipped = 0;
    foreach (($translation['strings'] ?? []) as $id => $translated) {
        $entry = $byId[$id] ?? null;
        if ($entry === null || !is_string($translated)) {
            $skipped++;
            continue;                                     // catalogue changed since generation
        }
        if (i18n_reject_reason($entry, $translated) !== '') {
            $skipped++;
            continue;
        }
        if (i18n_set_path($block, (string) $id, $translated, $entry['text'])) {
            $applied++;
        } else {
            $skipped++;
        }
    }

    $bundle['i18n']['strings'][$code] = $block;
    $bundle['i18n']['languages'][] = ['code' => $code, 'label' => $label, 'dir' => $dir];
    $bundle['i18n']['default'] = $code;
    return [$bundle, $applied, $skipped];
}

/**
 * Write one translated string at its catalogue path.
 *
 * The path is followed into the copy the page actually reads, and the write only happens where
 * the English original is still sitting. A catalogue that has drifted from the build therefore
 * skips the string instead of overwriting something else with it.
 */
function i18n_set_path(array &$block, string $path, string $value, string $expected): bool
{
    $parts = explode('.', $path);
    // The catalogue is rooted at the language; a bundle nests a wedge's copy under `wedge`.
    if (($parts[0] ?? '') === 'wedges') {
        if (count($parts) < 3 || !isset($block['wedge'])) {
            return false;
        }
        array_splice($parts, 0, 2, ['wedge']);
    }
    $node = &$block;
    $last = array_pop($parts);
    foreach ($parts as $part) {
        if (!is_array($node) || !array_key_exists($part, $node)) {
            return false;
        }
        $node = &$node[$part];
    }
    if (!is_array($node) || !array_key_exists($last, $node) || $node[$last] !== $expected) {
        return false;
    }
    $node[$last] = $value;
    return true;
}

// ---- generation ----------------------------------------------------------------------------

const TRANSLATION_SYSTEM = <<<'PROMPT'
You translate the interface copy of a financial decision tool for small business owners.

Rules, in order of importance:
1. Preserve every ${...} placeholder EXACTLY as written, including the code inside the braces.
   They are substituted with figures at run time. Never translate, reorder inside, or remove them.
2. Preserve every HTML tag exactly as written, in the same order.
3. This tool compares scenarios; it does not predict. Never translate a hedged phrase into a
   confident one. "ranks first under current assumptions" must not become "is best" or "is
   recommended"; "sensitivity count, not a probability" must keep that distinction.
4. Use the plain vocabulary a shop owner uses for money, not accounting jargon.
5. Keep the length close to the original where you can; this text sits in a fixed layout.

You receive a JSON object of id -> English string. Return a JSON object with the SAME ids and
the translated strings as values. Return nothing but that JSON object.
PROMPT;

/**
 * Translate the catalogue in batches and write data/i18n/<code>.json.
 *
 * @return array{ok:bool, error:string, applied:int, skipped:int, batches:int, rejected:array}
 */
function i18n_generate(array $llm, string $code, string $label, string $dir, int $batchSize = 25): array
{
    $catalogue = i18n_catalogue();
    if (!$catalogue) {
        return ['ok' => false, 'error' => 'assets/strings.json is missing or empty.',
                'applied' => 0, 'skipped' => 0, 'batches' => 0, 'rejected' => []];
    }
    $code = preg_replace('/[^a-z0-9_-]/i', '', $code);
    if ($code === '') {
        return ['ok' => false, 'error' => 'Give the language a code, such as fa.',
                'applied' => 0, 'skipped' => 0, 'batches' => 0, 'rejected' => []];
    }

    $strings = [];
    $rejected = [];
    $batches = 0;
    foreach (array_chunk($catalogue, max(1, $batchSize)) as $chunk) {
        $ask = [];
        foreach ($chunk as $entry) {
            $ask[$entry['id']] = $entry['text'];
        }
        $prompt = "Target language: $label ($code).\n\n"
            . json_encode($ask, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        $result = llm_chat($llm, TRANSLATION_SYSTEM, $prompt, ['json' => true, 'max_output_tokens' => 4000]);
        $batches++;
        if (!$result['ok']) {
            return ['ok' => false, 'error' => $result['error'], 'applied' => count($strings),
                    'skipped' => count($rejected), 'batches' => $batches, 'rejected' => $rejected];
        }
        $decoded = json_decode(i18n_strip_fence($result['text']), true);
        if (!is_array($decoded)) {
            return ['ok' => false, 'error' => 'The model did not return usable JSON.',
                    'applied' => count($strings), 'skipped' => count($rejected),
                    'batches' => $batches, 'rejected' => $rejected];
        }
        foreach ($chunk as $entry) {
            $translated = $decoded[$entry['id']] ?? null;
            if (!is_string($translated)) {
                $rejected[$entry['id']] = 'missing from the reply';
                continue;
            }
            $reason = i18n_reject_reason($entry, $translated);
            if ($reason !== '') {
                $rejected[$entry['id']] = $reason;
                continue;
            }
            $strings[$entry['id']] = $translated;
        }
    }

    @mkdir(I18N_DIR, 0775, true);
    $payload = [
        'code' => $code,
        'label' => $label !== '' ? $label : $code,
        'dir' => $dir === 'rtl' ? 'rtl' : 'ltr',
        'generated' => gmdate('c'),
        'model' => (string) $llm['model'],
        'catalogue_size' => count($catalogue),
        'strings' => $strings,
    ];
    $ok = @file_put_contents(I18N_DIR . '/' . $code . '.json',
        json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)) !== false;

    return [
        'ok' => $ok,
        'error' => $ok ? '' : 'Could not write data/i18n/. Make the folder writable.',
        'applied' => count($strings),
        'skipped' => count($rejected),
        'batches' => $batches,
        'rejected' => $rejected,
    ];
}

/** Models sometimes wrap JSON in a code fence even when told not to. */
function i18n_strip_fence(string $text): string
{
    $trimmed = trim($text);
    if (strncmp($trimmed, '```', 3) === 0) {
        $trimmed = preg_replace('/^```[a-zA-Z]*\s*/', '', $trimmed);
        $trimmed = preg_replace('/\s*```$/', '', (string) $trimmed);
    }
    return (string) $trimmed;
}
