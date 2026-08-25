<?php
/**
 * The intake assistant: free text in, draft form fields out.
 *
 * What it does: reads a sentence like "we do about 32 million a month, maybe 140 orders a day,
 * the supplier just put coffee up 40%" and fills in the eight fields.
 *
 * What it does not do: run the comparison, choose a scenario, or produce any figure the owner
 * has not seen. Its output lands in the form for the owner to correct, and the engine computes
 * from whatever the owner finally submits. The model is a typist, not an analyst.
 *
 * Every number it returns must be traceable to the text: it also returns the words it read each
 * figure from, and anything it could not find is left empty rather than invented.
 */
declare(strict_types=1);

require_once __DIR__ . '/llm.php';

const ASSIST_SYSTEM = <<<'PROMPT'
You extract business figures from a short description written by a small business owner, so
they can be shown back in a form for the owner to check and correct.

Return a JSON object with exactly these keys:
  name, monthly_revenue, daily_orders, monthly_cogs, monthly_fixed_costs, cash_on_hand,
  supplier_increase_pct, low_margin_share_pct, evidence, missing, note

Rules:
- Every figure must come from the text. Use null for anything the text does not give. Never
  guess, never fill a typical value, never derive one figure from another.
- Numbers must be plain numbers: no currency symbols, no thousands separators, no words.
  Write "32 million" as 32000000 and "1.2k" as 1200. Keep the owner's own currency; do not
  convert between currencies.
- monthly_cogs is what they pay suppliers for what they sell — ingredients, stock, materials.
  It is NOT wages and NOT rent. If the text gives it as a percentage of sales and gives sales,
  you may state the percentage in `note` but still return null for monthly_cogs.
- monthly_fixed_costs is rent, wages, utilities and loans together.
- supplier_increase_pct and low_margin_share_pct are percentages: return 40 for "up 40%".
- `evidence` is an object mapping each key you filled to the exact words you read it from.
- `missing` is an array of the keys you left null.
- `note` is one short sentence for the owner about anything ambiguous, or "".

Return nothing but the JSON object.
PROMPT;

const ASSIST_FIELDS = ['monthly_revenue', 'daily_orders', 'monthly_cogs', 'monthly_fixed_costs',
                       'cash_on_hand', 'supplier_increase_pct', 'low_margin_share_pct'];

/**
 * @return array{ok:bool, error:string, fields:array, evidence:array, missing:array, note:string}
 */
function assist_extract(array $llm, string $description): array
{
    $fail = static fn (string $why): array => ['ok' => false, 'error' => $why, 'fields' => [],
                                               'evidence' => [], 'missing' => [], 'note' => ''];
    $description = trim($description);
    if ($description === '') {
        return $fail('Write a sentence or two about the business first.');
    }
    if (mb_strlen($description) > 4000) {
        $description = mb_substr($description, 0, 4000);
    }
    if (!llm_feature_on($llm, 'intake_assistant')) {
        return $fail('The intake assistant is switched off.');
    }

    $result = llm_chat($llm, ASSIST_SYSTEM, $description, ['json' => true, 'max_output_tokens' => 1200]);
    if (!$result['ok']) {
        return $fail($result['error']);
    }
    $decoded = json_decode(assist_strip_fence($result['text']), true);
    if (!is_array($decoded)) {
        return $fail('The model did not return usable JSON.');
    }

    $fields = [];
    if (isset($decoded['name']) && is_string($decoded['name']) && trim($decoded['name']) !== '') {
        $fields['name'] = mb_substr(trim($decoded['name']), 0, 80);
    }
    $missing = [];
    foreach (ASSIST_FIELDS as $key) {
        $value = $decoded[$key] ?? null;
        // A model may return "32000" or 32000; anything else is not a figure.
        if (is_string($value) && is_numeric(str_replace([',', ' '], '', $value))) {
            $value = (float) str_replace([',', ' '], '', $value);
        }
        if (!is_int($value) && !is_float($value)) {
            $missing[] = $key;
            continue;
        }
        $fields[$key] = (float) $value;
    }

    $evidence = [];
    foreach ((array) ($decoded['evidence'] ?? []) as $key => $quote) {
        if (isset($fields[$key]) && is_string($quote)) {
            $evidence[$key] = mb_substr($quote, 0, 200);
        }
    }

    return [
        'ok' => true,
        'error' => '',
        'fields' => $fields,
        'evidence' => $evidence,
        'missing' => $missing,
        'note' => is_string($decoded['note'] ?? null) ? mb_substr($decoded['note'], 0, 300) : '',
    ];
}

function assist_strip_fence(string $text): string
{
    $trimmed = trim($text);
    if (strncmp($trimmed, '```', 3) === 0) {
        $trimmed = preg_replace('/^```[a-zA-Z]*\s*/', '', $trimmed);
        $trimmed = preg_replace('/\s*```$/', '', (string) $trimmed);
    }
    return (string) $trimmed;
}
