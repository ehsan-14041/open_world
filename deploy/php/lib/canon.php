<?php
/**
 * Python-compatible number formatting and canonical JSON.
 *
 * The reproducibility hashes are SHA-256 over `json.dumps(payload, sort_keys=True)`, so the
 * PHP side has to agree with CPython byte for byte. Two places it would not, by default:
 *
 *   - json_encode(100.0) gives "100", Python gives "100.0";
 *   - PHP's json separators are ",", ":" and Python's defaults are ", ", ": ".
 *
 * The constant halves of the payload (the slice, the config) are exported from Python itself
 * by scripts/export_php_assets.py, so only the small varying halves — the events and the
 * interventions — are encoded here. A test asserts the resulting hashes match Python's.
 */
declare(strict_types=1);

/**
 * Python's round(): round-half-to-even on the exact binary value.
 *
 * PHP's round() is half-away-from-zero and would disagree on exact ties (round(0.0625, 3)
 * gives 0.063 where Python gives 0.062). sprintf('%.Nf') rounds ties to even, so it agrees.
 */
function py_round(float $x, int $digits = 0): float
{
    return (float) sprintf('%.' . $digits . 'f', $x);
}

/** Python's repr() of a float, which is what json.dumps emits. */
function py_float(float $x): string
{
    if (is_nan($x) || is_infinite($x)) {
        throw new RuntimeException('Cannot encode a non-finite float.');
    }
    $s = json_encode($x);                        // shortest round-trip, same algorithm as Python
    if (strpos($s, 'e') !== false || strpos($s, 'E') !== false) {
        // PHP writes 1.0e-7, Python writes 1e-07.
        [$mantissa, $exponent] = preg_split('/[eE]/', $s);
        $mantissa = rtrim(rtrim($mantissa, '0'), '.');
        $sign = $exponent[0] === '-' ? '-' : '+';
        $digits = ltrim($exponent, '+-');
        $digits = strlen($digits) < 2 ? str_pad($digits, 2, '0', STR_PAD_LEFT) : $digits;
        return $mantissa . 'e' . $sign . $digits;
    }
    if (strpos($s, '.') === false) {
        $s .= '.0';                              // 100 -> 100.0
    }
    return $s;
}

/** Python's format(x, 'g'). */
function py_g(float $x): string
{
    return sprintf('%g', $x);
}

/** Python's format(x, ',.Nf') — thousands separators, round-half-even. */
function py_thousands(float $x, int $digits = 0): string
{
    return number_format(py_round($x, $digits), $digits, '.', ',');
}

/**
 * json.dumps(value, sort_keys=True) with CPython's default separators.
 *
 * Distinguishes int from float the way Python does, so pass floats as floats. An empty
 * array is encoded as a list, not an object — see the note in the body.
 */
function py_json($value): string
{
    if ($value === null) {
        return 'null';
    }
    if (is_bool($value)) {
        return $value ? 'true' : 'false';
    }
    if (is_int($value)) {
        return (string) $value;
    }
    if (is_float($value)) {
        return py_float($value);
    }
    if (is_string($value)) {
        return json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }
    if (is_array($value)) {
        if (count($value) === 0) {
            // PHP cannot tell [] from {}. Every empty container in the fingerprint payload is
            // a list (an event's `evidence`, a world's `interventions`), so encode it as one.
            return '[]';
        }
        $isList = array_keys($value) === range(0, count($value) - 1);
        if ($isList) {
            return '[' . implode(', ', array_map('py_json', $value)) . ']';
        }
        $keys = array_keys($value);
        sort($keys, SORT_STRING);                // sort_keys=True
        $parts = [];
        foreach ($keys as $k) {
            $parts[] = py_json((string) $k) . ': ' . py_json($value[$k]);
        }
        return '{' . implode(', ', $parts) . '}';
    }
    throw new RuntimeException('Cannot encode ' . gettype($value));
}

/**
 * Hash of everything that determines a trajectory, matching EventSimulation.fingerprint().
 *
 * payload = {"config": ..., "events": ..., "interventions": ..., "slice": ...} with sorted
 * keys, so the four members appear in that order and the two constant ones are spliced in as
 * the exact strings Python produced.
 */
function engine_fingerprint(array $frozen, array $events, array $interventions): string
{
    return _fingerprint($frozen['canonical']['slice'], $frozen, $events, $interventions);
}

/**
 * The registry-independent companion figure.
 *
 * The engine's own fingerprint hashes the whole slice dict, which includes `excluded_systems` —
 * a list of every other module in the repository — so it moves when an unrelated module is
 * added even though no coefficient did. This one covers only what determines a trajectory.
 */
function trajectory_fingerprint(array $frozen, array $events, array $interventions): string
{
    return _fingerprint($frozen['canonical']['trajectory_slice'], $frozen, $events, $interventions);
}

function _fingerprint(string $sliceBlob, array $frozen, array $events, array $interventions): string
{
    $eventDicts = [];
    foreach ($events as $e) {
        $eventDicts[] = [
            'id' => $e['id'],
            'label' => $e['label'] !== '' ? $e['label'] : $e['id'],
            'description' => $e['description'],
            'targets' => array_map('floatval', $e['targets']),
            'start_turn' => (int) $e['start_turn'],
            'duration' => (int) $e['duration'],
            'shape' => $e['shape'],
            'status' => $e['status'],
            'evidence' => [],
        ];
    }
    $ivDicts = [];
    foreach ($interventions as $iv) {
        $ivDicts[] = [
            'id' => $iv['id'],
            'label' => $iv['label'] !== '' ? $iv['label'] : $iv['id'],
            'magnitude' => (float) $iv['magnitude'],
            'start_turn' => (int) $iv['start_turn'],
            'duration' => (int) $iv['duration'],
            'effects_per_unit' => array_map('floatval', $iv['effects_per_unit']),
            'status' => $iv['status'],
        ];
    }
    $payload = '{"config": ' . $frozen['canonical']['config']
        . ', "events": ' . py_json($eventDicts)
        . ', "interventions": ' . py_json($ivDicts)
        . ', "slice": ' . $sliceBlob . '}';
    return hash('sha256', $payload);
}
