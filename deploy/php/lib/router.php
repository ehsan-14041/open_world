<?php
/**
 * Reading a question an owner typed, to see whether this tool can answer it with numbers.
 *
 * The model sorts; it does not answer. It is asked which of the three situations the question
 * is about, whether it names the size of the change or a price rise, and — if it fits none —
 * which topic it is. Every field it returns is checked against what this build knows, and
 * anything it gets wrong falls back to "cannot answer this yet" rather than to a guess. No word
 * or figure the owner sees comes from it: the page writes its own restatement from these
 * fields, and every number still comes from the owner's answers and the model.
 *
 * The text is scrubbed before it goes anywhere — to the provider, or to disk.
 */
declare(strict_types=1);

require_once __DIR__ . '/llm.php';

const ROUTER_TOPICS = ['hiring', 'hours', 'delivery', 'rent_move', 'marketing', 'range', 'loan_cash', 'other'];
const ROUTER_MAX_PRICE = 30.0;
const QUESTIONS_DIR = __DIR__ . '/../data/questions';
const QUESTIONS_FILE = QUESTIONS_DIR . '/questions.jsonl';

const ROUTER_SYSTEM = <<<'PROMPT'
You sort questions that small business owners type into a decision tool. You never answer the
question, never give advice, and never state or estimate any figure that is not in the text.

The tool compares three options with real numbers for exactly these situations:

  cafe   - a cafe or restaurant whose supplier / ingredient prices went up. Trades: "bakery"
           for bakeries and pastry shops, "fastfood" for fast food, burgers, sandwiches, pizza.
  shop   - a retail shop, grocery or corner store whose supplier / wholesale prices went up.
  salon  - a hair, beauty or nail salon, or a similar appointment business, where more people
           want appointments than there are slots.

For each, the options are built from two levers only: raising prices by some percent, and
trimming low-margin items (cafe: simplifying the menu; shop: dropping low-margin lines; salon:
shifting the service mix away from discounted services).

Return one JSON object with exactly these keys:
  fit            "exact" if the question is about one of those situations and those levers;
                 "near" if it is about the prices or costs of one of those businesses but not
                 exactly that situation (for example rent or wages went up, or a price cut);
                 "none" otherwise.
  wedge          "cafe", "shop" or "salon" if the business is clear, else null.
  variant        "bakery" or "fastfood" if the business is one of those, else null.
  shock_pct      how much supplier prices rose (cafe, shop) or demand rose (salon), in percent,
                 only if the text states it, else null. 25 for "up 25%".
  price_rise_pct the price rise the owner is considering, in percent, only if the text states
                 it, else null.
  reduce         true only if the owner mentions trimming items, dropping lines or changing the
                 service mix; else false.
  topic          for fit "none": one of hiring, hours, delivery, rent_move, marketing, range,
                 loan_cash, other. For "exact" or "near": "pricing".

The text may be in any language, often Persian. Return nothing but the JSON object.
PROMPT;

/** Wedges, trades, and which wedge each trade belongs to, as this build declared them. */
function router_known(): array
{
    $path = __DIR__ . '/../assets/trades.json';
    $all = is_file($path) ? json_decode((string) file_get_contents($path), true) : null;
    $base = [];
    foreach ((array) ($all['variant_base'] ?? []) as $v => $w) {
        if (is_string($v) && is_string($w)) {
            $base[$v] = $w;
        }
    }
    return [
        'wedges' => array_values(array_filter((array) ($all['wedges'] ?? []), 'is_string')),
        'variants' => array_values(array_filter((array) ($all['variants'] ?? []), 'is_string')),
        'variant_base' => $base,
    ];
}

/**
 * Remove what could identify someone: web addresses, email addresses, and digit runs long
 * enough to be a phone number — ten or more digits, in any script, however they are spaced.
 * Amounts of money stay; they are usually the question.
 */
function router_scrub(string $q): string
{
    $q = (string) preg_replace('~(?:https?://|www\.)\S+~iu', '[…]', $q);
    $q = (string) preg_replace('~[^\s@]+@[^\s@]+\.[^\s@]{2,}~u', '[…]', $q);
    $q = (string) preg_replace_callback(
        '~\+?[0-9۰-۹٠-٩][0-9۰-۹٠-٩\s().-]{8,}[0-9۰-۹٠-٩]~u',
        function ($m) {
            return preg_match_all('~[0-9۰-۹٠-٩]~u', $m[0]) >= 10 ? '[…]' : $m[0];
        },
        $q
    );
    return trim((string) preg_replace('~\s+~u', ' ', $q));
}

/** A percentage the model read from the text, or null if it is not one this build can use. */
function router_number($v, float $lo, float $hi, bool $includeLo)
{
    if (is_string($v)) {
        $v = str_replace([',', ' ', '%'], '', $v);
    }
    if (!is_numeric($v)) {
        return null;
    }
    $f = (float) $v;
    if (!is_finite($f) || $f > $hi || $f < $lo || (!$includeLo && $f <= $lo)) {
        return null;
    }
    return round($f, 1);
}

/**
 * The model's reply, reduced to what this build can act on. Pure, so it can be tested without
 * a provider: anything unknown, out of range or inconsistent becomes "cannot answer this yet".
 */
function router_validate($decoded, array $known): array
{
    $out = ['fit' => 'none', 'wedge' => null, 'variant' => null, 'shock' => null,
            'price' => null, 'reduce' => false, 'topic' => 'other'];
    if (!is_array($decoded)) {
        return $out;
    }
    $wedge = $decoded['wedge'] ?? null;
    if (is_string($wedge) && in_array($wedge, $known['wedges'], true)) {
        $out['wedge'] = $wedge;
    }
    $variant = $decoded['variant'] ?? null;
    if ($out['wedge'] !== null && is_string($variant) && in_array($variant, $known['variants'], true)
        && ($known['variant_base'][$variant] ?? null) === $out['wedge']) {
        $out['variant'] = $variant;
    }
    $fit = $decoded['fit'] ?? null;
    if (($fit === 'exact' || $fit === 'near') && $out['wedge'] !== null) {
        $out['fit'] = $fit;
        $out['topic'] = 'pricing';
        $out['shock'] = router_number($decoded['shock_pct'] ?? null, 0.0, 100.0, false);
        $out['price'] = router_number($decoded['price_rise_pct'] ?? null, 0.0, ROUTER_MAX_PRICE, true);
        $out['reduce'] = ($decoded['reduce'] ?? false) === true;
        return $out;
    }
    $topic = $decoded['topic'] ?? 'other';
    $out['topic'] = (is_string($topic) && in_array($topic, ROUTER_TOPICS, true)) ? $topic : 'other';
    return $out;
}

function router_strip_fence(string $text): string
{
    $trimmed = trim($text);
    if (strncmp($trimmed, '```', 3) === 0) {
        $trimmed = (string) preg_replace('/^```[a-zA-Z]*\s*/', '', $trimmed);
        $trimmed = (string) preg_replace('/\s*```$/', '', $trimmed);
    }
    return $trimmed;
}

/** Sort one (already scrubbed) question. `routed` is false whenever the provider was not used. */
function router_route(array $llm, string $clean, array $known): array
{
    if (!llm_feature_on($llm, 'question_router')) {
        return ['routed' => false];
    }
    $result = llm_chat($llm, ROUTER_SYSTEM, $clean, ['json' => true, 'max_output_tokens' => 300]);
    if (!$result['ok']) {
        return ['routed' => false];
    }
    $decoded = json_decode(router_strip_fence($result['text']), true);
    if (!is_array($decoded)) {
        return ['routed' => false];
    }
    return array_merge(['routed' => true], router_validate($decoded, $known));
}

/** The kept questions, newest first, with counts — for the maintainer's page. */
function router_read_questions(int $limit = 50): array
{
    $out = ['total' => 0, 'by_fit' => [], 'by_topic' => [], 'rows' => []];
    if (!is_file(QUESTIONS_FILE)) {
        return $out;
    }
    $lines = file(QUESTIONS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [];
    foreach ($lines as $line) {
        $row = json_decode($line, true);
        if (!is_array($row)) {
            continue;
        }
        $out['total']++;
        $fit = (string) ($row['fit'] ?? '?');
        $topic = (string) ($row['topic'] ?? '-');
        $out['by_fit'][$fit] = ($out['by_fit'][$fit] ?? 0) + 1;
        $out['by_topic'][$topic] = ($out['by_topic'][$topic] ?? 0) + 1;
        $out['rows'][] = $row;
    }
    arsort($out['by_fit']);
    arsort($out['by_topic']);
    $out['rows'] = array_slice(array_reverse($out['rows']), 0, $limit);
    return $out;
}
