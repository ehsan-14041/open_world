<?php
/**
 * The sensitivity sweep, the assumption registry and the report bundle.
 *
 * Wedge-generic. Ports event_sim/wedge/{sensitivity,evidence,report}.py. The sweep is a CENSUS
 * over a chosen grid — every combination is run, none is weighted as more likely than another —
 * so the result is a count of cases, never a probability.
 *
 * The registry is rendered from the same declarative spec the Python side renders, exported in
 * assets/<wedge>.json. That is deliberate: the registry is the most prose-heavy part of a
 * wedge, and writing it twice would guarantee the two drifted.
 */
declare(strict_types=1);

require_once __DIR__ . '/cafe.php';

const CUSTOMER = 'Customer input';
const RESEARCH = 'External research';
const ASSUMPTION_CLASS = 'Assumption';
const DERIVED = 'Derived';
const LADDER = [
    CUSTOMER => 'user_assumption',
    RESEARCH => 'literature_backed',
    ASSUMPTION_CLASS => 'expert_assumption',
    DERIVED => 'derived',
];

/**
 * Split a swept name into where it belongs: an assumption axis the engine understands, a knob
 * the wedge accepts, or a field of the baseline itself.
 */
function split_settings(array $wedge, array $settings): array
{
    $axisNames = array_keys($wedge['defaults']['axis_settings']);
    $knobNames = array_keys($wedge['defaults']['knobs']);
    $axes = [];
    $knob = null;
    $overrides = [];
    foreach ($settings as $k => $v) {
        if (in_array($k, $axisNames, true)) {
            $axes[$k] = $v;
        } elseif (in_array($k, $knobNames, true)) {
            $knob = (float) $v;
        } else {
            $overrides[$k] = (float) $v;
        }
    }
    return [$axes, $knob, $overrides];
}

/** Every combination of the swept assumptions, each re-run for all three decisions. */
function run_sensitivity(Slice $slice, array $wedge, Baseline $baseline): array
{
    $sweep = $wedge['sweep'];
    $keys = array_keys($sweep);
    $points = [];

    $combos = [[]];
    foreach ($keys as $k) {                      // same nesting order as itertools.product
        $next = [];
        foreach ($combos as $prefix) {
            foreach ($sweep[$k] as $v) {
                $next[] = array_merge($prefix, [$k => $v]);
            }
        }
        $combos = $next;
    }

    $defaultKnob = (float) reset($wedge['defaults']['knobs']);
    foreach ($combos as $settings) {
        [$axes, $knob, $overrides] = split_settings($wedge, $settings);
        $b = $overrides ? $baseline->replace($overrides) : $baseline;
        $comp = run_comparison($slice, $wedge, $b, $axes, $knob ?? $defaultKnob);

        $metric = [];
        foreach ($comp['worlds'] as $w) {
            $metric[$w['spec']['id']] = (float) $w['metrics']['cash_day_90'];
        }
        $points[] = [
            'settings' => $settings,
            'ranking' => ranking($comp),
            'metric' => $metric,
            'comparison' => $comp,
            'baseline' => $b,
        ];
    }

    $centre = [];
    foreach ($sweep as $k => $vals) {
        $centre[$k] = $vals[intdiv(count($vals), 2)];
    }
    $centrePoint = sweep_find($points, $keys, $centre);

    return [
        'metric' => 'cash_day_90',
        'points' => $points,
        'sweep' => $sweep,
        'keys' => $keys,
        'centre' => $centre,
        'central_ranking' => $centrePoint !== null ? $centrePoint['ranking'] : $points[0]['ranking'],
    ];
}

function sweep_find(array $points, array $keys, array $settings): ?array
{
    foreach ($points as $p) {
        $match = true;
        foreach ($keys as $k) {
            if ($p['settings'][$k] != $settings[$k]) {
                $match = false;
                break;
            }
        }
        if ($match) {
            return $p;
        }
    }
    return null;
}

function win_counts(array $sens): array
{
    $out = ['A' => 0, 'B' => 0, 'C' => 0];
    foreach ($sens['points'] as $p) {
        $out[$p['ranking'][0]]++;
    }
    return $out;
}

function top_stable(array $sens): bool
{
    foreach ($sens['points'] as $p) {
        if ($p['ranking'][0] !== $sens['central_ranking'][0]) {
            return false;
        }
    }
    return true;
}

/** Options that never rank first anywhere on the grid. */
function dominated_worlds(array $sens): array
{
    $out = [];
    foreach (win_counts($sens) as $id => $n) {
        if ($n === 0) {
            $out[] = $id;
        }
    }
    return $out;
}

function ranking_stable(array $sens): bool
{
    foreach ($sens['points'] as $p) {
        if ($p['ranking'] !== $sens['central_ranking']) {
            return false;
        }
    }
    return true;
}

/**
 * For each assumption: move it alone off centre, holding the others at centre. Reports whether
 * the top choice changes and the spread of the decision metric.
 */
function one_at_a_time(array $sens, array $labels): array
{
    $rows = [];
    foreach ($sens['sweep'] as $key => $values) {
        $tops = [];
        $spreads = [];
        foreach ($values as $v) {
            $p = sweep_find($sens['points'], $sens['keys'], array_merge($sens['centre'], [$key => $v]));
            if ($p === null) {
                continue;
            }
            $tops[] = $p['ranking'][0];
            $spreads[] = $p['metric']['B'] - $p['metric']['C'];
        }
        $rows[] = [
            'assumption' => $key,
            'label' => $labels[$key],
            'values' => $values,
            'top_choice_by_value' => $tops,
            'changes_top_choice' => count(array_unique($tops)) > 1,
            'b_minus_c_range' => $spreads ? [min($spreads), max($spreads)] : [0.0, 0.0],
            'influence' => $spreads ? max($spreads) - min($spreads) : 0.0,
        ];
    }
    usort($rows, function ($a, $b) {
        $flip = ((int) $b['changes_top_choice']) <=> ((int) $a['changes_top_choice']);
        return $flip !== 0 ? $flip : ($b['influence'] <=> $a['influence']);
    });
    return $rows;
}

/**
 * Across the whole grid: for each assumption, how many points differ from the central top
 * choice AND share every other setting with a point that agrees with it — a count of how often
 * that assumption alone is the deciding one.
 */
function flip_attribution(array $sens): array
{
    $centreTop = $sens['central_ranking'][0];
    $counts = [];
    foreach ($sens['sweep'] as $k => $_) {
        $counts[$k] = 0;
    }
    foreach ($sens['points'] as $p) {
        if ($p['ranking'][0] === $centreTop) {
            continue;
        }
        foreach ($sens['sweep'] as $key => $values) {
            foreach ($values as $alt) {
                if ($alt == $p['settings'][$key]) {
                    continue;
                }
                $q = sweep_find($sens['points'], $sens['keys'], array_merge($p['settings'], [$key => $alt]));
                if ($q !== null && $q['ranking'][0] === $centreTop) {
                    $counts[$key]++;
                    break;
                }
            }
        }
    }
    return $counts;
}

/** One sentence an owner can act on. Only says what the grid supports. */
function sensitivity_verdict(array $sens, array $oat, array $wedge): string
{
    $counts = win_counts($sens);
    $n = count($sens['points']);
    $best = array_keys($counts, max($counts))[0];
    $bestLabel = $wedge['copy']['world_verdict_labels'][$best];
    $tail = ' This is sensitivity analysis, not a probability estimate.';

    if (top_stable($sens)) {
        return "$bestLabel ranked first in every one of the $n assumption combinations tested." . $tail;
    }
    $deciders = [];
    foreach ($oat as $r) {
        if ($r['changes_top_choice']) {
            $deciders[] = strtolower($r['label']);
        }
    }
    $countTxt = "{$counts[$best]} of the $n assumption combinations tested";
    if ($deciders) {
        $s = "$bestLabel ranked first in $countTxt. The ranking depends mainly on {$deciders[0]}";
        if (count($deciders) > 1) {
            $s .= " and {$deciders[1]}";
        }
        return $s . '.' . $tail;
    }
    return "$bestLabel ranked first in $countTxt." . $tail;
}

// ---- the assumption registry, rendered from the shared spec ---------------------------------

/** One row's value. Mirrors render_value() in event_sim/wedge/evidence.py. */
function render_value(array $kind, array $ctx): string
{
    switch ($kind['kind']) {
        case 'literal':
            return (string) $kind['text'];
        case 'money':
            return py_thousands((float) $ctx[$kind['field']], (int) ($kind['dp'] ?? 0));
        case 'money_with_pct':
            return py_thousands((float) $ctx[$kind['field']])
                . ' (' . sprintf('%.0f', py_round((float) $ctx[$kind['pct_of']], 0)) . '% of sales)';
        case 'g':
            return ($kind['prefix'] ?? '') . py_g((float) $ctx[$kind['field']]) . ($kind['suffix'] ?? '');
        case 'fixed':
            return ($kind['prefix'] ?? '')
                . sprintf('%.' . (int) ($kind['dp'] ?? 1) . 'f', py_round((float) $ctx[$kind['field']], (int) ($kind['dp'] ?? 1)))
                . ($kind['suffix'] ?? '');
        case 'axis':
            $setting = $ctx['axis_settings'][$kind['axis']] ?? 'central';
            return (string) $kind['map'][$setting];
        case 'template':
            return render_template((string) $kind['text'], $ctx);
    }
    throw new RuntimeException('unknown registry value kind ' . $kind['kind']);
}

/** The `{name:spec}` subset Python's str.format uses in the registry specs. */
function render_template(string $text, array $ctx): string
{
    return preg_replace_callback('/\{(\w+)(?::([^}]*))?\}/', function ($m) use ($ctx) {
        $value = $ctx[$m[1]];
        $spec = $m[2] ?? '';
        if ($spec === '' || $spec === null) {
            return (string) $value;
        }
        if ($spec === 'g') {
            return py_g((float) $value);
        }
        if (preg_match('/^\.(\d+)f$/', $spec, $f)) {
            return sprintf('%.' . $f[1] . 'f', py_round((float) $value, (int) $f[1]));
        }
        if (preg_match('/^,\.(\d+)f$/', $spec, $f)) {
            return py_thousands((float) $value, (int) $f[1]);
        }
        throw new RuntimeException("unsupported format spec {$spec}");
    }, $text);
}

/** The customer-facing classification of every number behind the comparison. */
function evidence_registry(Baseline $b, array $wedge, array $axisSettings, float $effectiveness,
                           ?float $customElasticity = null): array
{
    $ctx = $b->toDict();
    $ctx['axis_settings'] = $axisSettings;
    foreach ($wedge['defaults']['knobs'] as $name => $_) {
        $ctx[$name] = $effectiveness;
    }
    // The derived quantities a spec may refer to, under the names the spec uses.
    $reduction = reduction_points($b, $wedge, $effectiveness);
    $ctx['reduction'] = $reduction;
    $ctx['cogs_pct'] = $b->costPct();
    $ctx['variable_cost_pct'] = $b->costPct();
    $ctx['average_order_value'] = $b->averageTicket();
    $ctx['average_ticket'] = $b->averageTicket();
    $ctx['cogs_per_order'] = $b->unitCost();
    $ctx['unit_cost'] = $b->unitCost();
    $ctx['capacity_per_day'] = $b->capacityPerDay() ?? 0.0;
    $ctx['demand_cost'] = ((float) demand_cost_ratio($wedge)) * $reduction;
    $ctx['price_gain'] = ((float) price_gain_ratio($wedge)) * $reduction;

    $research = $wedge['research_settings'];
    $out = [];
    foreach ($wedge['registry_spec'] as $row) {
        $klass = $row['klass'];
        $value = render_value($row['value'], $ctx);
        $source = $row['source'] ?? '';
        if (!empty($row['elasticity'])) {
            $setting = $axisSettings[$row['value']['axis'] ?? 'price_sensitivity'] ?? 'central';
            $klass = in_array($setting, $research, true) ? RESEARCH : ASSUMPTION_CLASS;
            if ($customElasticity !== null) {
                $value = sprintf('%.2f', abs($customElasticity)) . ' (your value)';
                $klass = CUSTOMER;
                $source = '';
            }
            if ($klass !== RESEARCH) {
                $source = $row['assumption_source'] ?? ($klass === CUSTOMER ? $source : '');
            }
        }
        $out[] = [
            'key' => $row['key'], 'label' => $row['label'], 'value' => $value,
            'klass' => $klass, 'swept' => (bool) ($row['swept'] ?? false),
            'note' => $row['note'] ?? '', 'source' => $source,
            'ladder_status' => LADDER[$klass],
        ];
    }
    return $out;
}

/** Ratios the interventions encode, read back off the module so they exist in one place. */
function demand_cost_ratio(array $wedge): float
{
    foreach ($wedge['slice']['interventions'] as $iv) {
        if ($iv['id'] === $wedge['worlds']['levers']['reduce']) {
            foreach ($iv['effects_per_unit'] as $var => $per) {
                if ($var === $wedge['roles']['demand_var']) {
                    return abs((float) $per);
                }
            }
        }
    }
    return 0.0;
}

function price_gain_ratio(array $wedge): float
{
    foreach ($wedge['slice']['interventions'] as $iv) {
        if ($iv['id'] === $wedge['worlds']['levers']['reduce']) {
            foreach ($iv['effects_per_unit'] as $var => $per) {
                if ($var === $wedge['roles']['price_var']) {
                    return abs((float) $per);
                }
            }
        }
    }
    return 0.0;
}

function round_list(array $xs, int $nd): array
{
    return array_map(function ($x) use ($nd) {
        return py_round((float) $x, $nd);
    }, $xs);
}

/** Everything the page needs, in the shape the template's JavaScript expects. */
function build_bundle(Slice $slice, array $wedge, Baseline $baseline, bool $includeGrid = true): array
{
    $defaults = $wedge['defaults'];
    $effectiveness = (float) reset($defaults['knobs']);
    $knobNames = array_keys($defaults['knobs']);
    $knobName = (string) $knobNames[0];
    $comp = run_comparison($slice, $wedge, $baseline, [], $effectiveness);
    $sens = run_sensitivity($slice, $wedge, $baseline);
    $oat = one_at_a_time($sens, $wedge['sweep_labels']);
    $reg = evidence_registry($baseline, $wedge, $comp['axis_settings'], $effectiveness);

    $classCounts = [];
    foreach ($reg as $a) {
        $classCounts[$a['klass']] = ($classCounts[$a['klass']] ?? 0) + 1;
    }

    $worlds = [];
    foreach ($comp['worlds'] as $w) {
        $metrics = [];
        foreach ($w['metrics'] as $k => $v) {
            $metrics[$k] = is_float($v) ? py_round($v, 4) : $v;
        }
        $ledger = [
            'cash' => round_list($w['ledger']['cash'], 2),
            'gross_margin_pct' => round_list($w['ledger']['gross_margin_pct'], 3),
            'orders' => round_list($w['ledger']['orders'], 2),
            'revenue' => round_list($w['ledger']['revenue'], 2),
        ];
        if ($w['ledger']['utilisation_pct']) {
            $ledger['utilisation_pct'] = round_list($w['ledger']['utilisation_pct'], 2);
            $ledger['turned_away'] = round_list($w['ledger']['turned_away'], 3);
        }
        $indices = [];
        foreach ($w['indices'] as $name => $series) {
            $indices[$name] = round_list($series, 3);
        }
        $worlds[] = [
            'id' => $w['spec']['id'],
            'label' => $w['spec']['label'],
            'headline' => $w['spec']['headline'],
            'price_rise_pct' => $w['spec']['price_rise_pct'],
            'cogs_reduction_points' => $w['spec']['cogs_reduction_points'],
            'metrics' => $metrics,
            'ledger' => $ledger,
            'indices' => $indices,
        ];
    }

    $aMetric = world_by_id($comp, 'A')['metrics']['cash_day_90'];
    $netBenefit = [];
    foreach ($comp['worlds'] as $w) {
        $netBenefit[$w['spec']['id']] = py_round($w['metrics']['cash_day_90'] - $aMetric, 2);
    }
    $counts = win_counts($sens);
    $n = count($sens['points']);
    $shares = [];
    foreach ($counts as $k => $v) {
        $shares[$k] = py_round($v / $n, 4);
    }

    $points = [];
    foreach ($sens['points'] as $p) {
        $points[] = ['settings' => $p['settings'], 'ranking' => $p['ranking'], 'metric' => $p['metric']];
    }

    $bundle = [
        'wedge' => $wedge['wedge'],
        'copy' => $wedge['copy'],
        'generated_for' => $baseline->name,
        'is_demo' => $baseline->is_demo,
        'baseline' => $baseline->summary($wedge),
        'baseline_raw' => $baseline->toDict(),
        'intake_fields' => $wedge['intake_fields'],
        'worlds' => $worlds,
        'central_ranking' => ranking($comp),
        'net_benefit_vs_a' => $netBenefit,
        'sensitivity' => [
            'metric' => $sens['metric'],
            'n' => $n,
            'win_counts' => $counts,
            'win_shares' => $shares,
            'top_stable' => top_stable($sens),
            'ranking_stable' => ranking_stable($sens),
            'dominated_worlds' => dominated_worlds($sens),
            'verdict' => sensitivity_verdict($sens, $oat, $wedge),
            'one_at_a_time' => $oat,
            'flip_attribution' => flip_attribution($sens),
            'sweep' => $wedge['sweep'],
            'sweep_labels' => $wedge['sweep_labels'],
            'points' => $points,
        ],
        'assumptions' => $reg,
        'assumption_class_counts' => $classCounts,
        'sources' => $wedge['sources'],
        'reproducibility' => [
            'wedge_id' => $wedge['wedge']['id'],
            'module_id' => $wedge['module_id'],
            'module_semantic_hash' => $wedge['module_semantic_hash'],
            'horizon_days' => (int) $defaults['horizon_days'],
            'axis_settings' => $defaults['axis_settings'],
            'lag_setting' => 'central',
            'knobs' => [$knobName => $effectiveness],
            $knobName => $effectiveness,
            'custom_elasticity' => null,
            'baseline' => $baseline->toDict(),
            'shared_fingerprint' => $wedge['shared_fingerprint'],
            'worlds' => array_map(function ($w) {
                return [
                'spec' => [
                    'id' => $w['spec']['id'],
                    'label' => $w['spec']['label'],
                    'headline' => $w['spec']['headline'],
                    'price_rise_pct' => $w['spec']['price_rise_pct'],
                    'cogs_reduction_points' => $w['spec']['cogs_reduction_points'],
                    'events' => $w['spec']['events'],
                    'interventions' => $w['spec']['interventions'],
                ],
                'engine_fingerprint' => $w['fingerprint'],
                'trajectory_fingerprint' => $w['trajectory_fingerprint'],
                ];
            }, $comp['worlds']),
        ],
        'language' => $wedge['language'],
    ];

    if ($includeGrid) {
        // Index trajectories do not depend on the owner's money at all — only on the shock, the
        // axis settings and the intervention sizes — so the page can apply any owner's figures
        // to them exactly.
        $grid = [];
        foreach ($sens['points'] as $p) {
            $s = $p['settings'];
            [$axes, $knob, $overrides] = split_settings($wedge, $s);
            $b = $p['baseline'];
            $gw = [];
            foreach ($p['comparison']['worlds'] as $w) {
                $gw[$w['spec']['id']] = [
                    'demand' => round_list($w['indices'][$wedge['roles']['demand_var']], 3),
                    'cogs' => round_list($w['indices'][$wedge['roles']['unit_cost_var']], 3),
                    'price' => round_list($w['indices'][$wedge['roles']['price_var']], 2),
                ];
            }
            $grid[] = ['key' => grid_key($wedge, $b, $s, $knob ?? $effectiveness), 'worlds' => $gw];
        }
        $bundle['grid'] = $grid;
    }
    return $bundle;
}

/** The keys the page selects a grid point by. Mirrors each wedge's _grid_key in Python. */
function grid_key(array $wedge, Baseline $b, array $settings, float $knob): array
{
    $key = [];
    foreach ($wedge['copy']['grid_key_fields'] as $name => $source) {
        if ($source === 'reduction') {
            $key[$name] = reduction_points($b, $wedge, $knob);
        } elseif (is_array($source)) {
            $key[$name] = (float) $settings[$source['float']];
        } else {
            $key[$name] = $settings[$source];
        }
    }
    return $key;
}

/** Fill the template. Mirrors report.render_html: compact separators, escaped `</`. */
function render_html(array $bundle, string $templatePath): string
{
    $template = file_get_contents($templatePath);
    $payload = json_encode($bundle, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
    $payload = str_replace('</', '<\\/', $payload);
    return str_replace('__DATA__', $payload, $template);
}
