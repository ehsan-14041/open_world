<?php
/**
 * The sensitivity sweep, the evidence registry and the report bundle.
 *
 * Ports event_sim/cafe/{sensitivity,evidence,report}.py. The sweep is a CENSUS over a chosen
 * grid — every combination is run, none is weighted as more likely than another — so the
 * result is a count of cases, never a probability.
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

/** Every combination of the swept assumptions, each re-run for all three decisions. */
function run_sensitivity(Slice $slice, array $frozen, Baseline $baseline): array
{
    $sweep = $frozen['sweep'];
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

    foreach ($combos as $settings) {
        $b = $baseline->withSupplierIncrease((float) $settings['supplier_increase_pct']);
        $comp = run_comparison($slice, $frozen, $b, [
            'price_sensitivity' => $settings['price_sensitivity'],
            'cogs_pass_through' => $settings['cogs_pass_through'],
            'demand_adjustment_speed' => $settings['demand_adjustment_speed'],
        ], (float) $settings['reformulation_effectiveness']);

        $metric = [];
        foreach ($comp['worlds'] as $w) {
            $metric[$w['spec']['id']] = (float) $w['metrics']['cash_day_90'];
        }
        $points[] = [
            'settings' => $settings,
            'ranking' => ranking($comp),
            'metric' => $metric,
            'comparison' => $comp,
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
 * For each assumption: move it alone off centre, holding the others at centre. Reports
 * whether the top choice changes and the spread of the decision metric.
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
 * choice AND share every other setting with a point that agrees with it — a count of how
 * often that assumption alone is the deciding one.
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

/** One sentence a cafe owner can act on. Only says what the grid supports. */
function sensitivity_verdict(array $sens, array $oat): string
{
    $counts = win_counts($sens);
    $n = count($sens['points']);
    $best = array_keys($counts, max($counts))[0];
    $labels = ['A' => 'Doing nothing', 'B' => 'Raising prices 10%', 'C' => 'A 5% rise plus trimming the menu'];
    $bestLabel = $labels[$best];
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

/** The customer-facing classification of every number behind the comparison. */
function evidence_registry(Baseline $b, array $axisSettings, float $effectiveness, array $defaults): array
{
    $ps = $axisSettings['price_sensitivity'] ?? 'central';
    $elasticity = ['low' => '0.50', 'central' => '0.81', 'high' => '1.60'][$ps];
    $elasticityClass = $ps === 'central' ? RESEARCH : ASSUMPTION_CLASS;
    $passThrough = ['low' => '70%', 'central' => '100%', 'high' => '100%'][$axisSettings['cogs_pass_through'] ?? 'central'];
    $speed = [
        'slow' => 'about a month to half-react',
        'central' => 'about two weeks to half-react',
        'fast' => 'about a week to half-react',
    ][$axisSettings['demand_adjustment_speed'] ?? 'central'];
    $reduction = cogs_reduction_points($b, $effectiveness);
    $priceB = py_g((float) $defaults['price_rise_b']);
    $priceC = py_g((float) $defaults['price_rise_c']);

    $rows = [
        ['monthly_revenue', 'Current monthly sales', py_thousands($b->monthly_revenue), CUSTOMER, false, ''],
        ['daily_orders', 'Orders per day', py_thousands($b->daily_orders), CUSTOMER, false, ''],
        ['monthly_cogs', 'Monthly ingredient cost',
            py_thousands($b->monthly_cogs) . ' (' . sprintf('%.0f', py_round($b->cogsPct(), 0)) . '% of sales)', CUSTOMER, false, ''],
        ['monthly_fixed_costs', 'Monthly fixed costs (incl. wages)', py_thousands($b->monthly_fixed_costs), CUSTOMER, false,
            'Treated as unchanged over 90 days.'],
        ['cash_on_hand', 'Cash available today', py_thousands($b->cash_on_hand), CUSTOMER, false, ''],
        ['supplier_increase_pct', 'Supplier cost increase', '+' . py_g($b->supplier_increase_pct) . '%', CUSTOMER, true,
            'Tested at 20%, 30% and 40%.'],
        ['low_margin_share_pct', 'Share of orders on low-margin items', py_g($b->low_margin_share_pct) . '%', CUSTOMER, false, ''],
        ['price_sensitivity', 'Price sensitivity of customers', $elasticity, $elasticityClass, true,
            'A 1% price rise eventually reduces orders by this percentage. Low 0.50 / central 0.81 / high 1.60. '
            . 'This is the assumption most likely to change the decision.'],
        ['cogs_pass_through', 'Share of supplier increase reaching your costs', $passThrough, ASSUMPTION_CLASS, true,
            '100% by definition unless you can substitute, renegotiate or have fixed-price contracts (tested at 70%).'],
        ['cogs_lag', 'Delay before higher prices reach your costs', 'about 7 days (stock on hand)', ASSUMPTION_CLASS, false,
            'Fresh inventory turns over in roughly a week; costs then rise over a few more days.'],
        ['demand_adjustment_speed', 'How quickly customers react to a price change', $speed, ASSUMPTION_CLASS, true, ''],
        ['reformulation_effectiveness', 'Ingredient-cost saving from trimming the menu',
            py_g($reduction) . ' points off average ingredient cost (' . sprintf('%.2f', py_round($effectiveness, 2))
            . ' per point of low-margin share)', ASSUMPTION_CLASS, true,
            'Tested at half and one-and-a-half times this rate.'],
        ['reformulation_demand_cost', 'Orders lost from removing items',
            sprintf('%.1f', py_round(0.33 * $reduction, 1)) . '% of orders', ASSUMPTION_CLASS, false,
            'One third of the ingredient-cost saving, in points of orders: customers who came for the removed items.'],
        ['price_rises', 'Price rises compared', "B: +$priceB%   C: +$priceC%", CUSTOMER, false,
            'The decisions being compared; fixed by the question.'],
        ['horizon', 'Comparison horizon', '90 days', ASSUMPTION_CLASS, false,
            'Long enough for costs and most of the customer reaction to land; short enough that wages and rent can be '
            . 'treated as fixed. Slow customer reactions are not fully visible within it.'],
        ['average_order_value', 'Average order value', py_thousands($b->averageOrderValue(), 2), DERIVED, false,
            'Monthly sales divided by monthly orders.'],
        ['cogs_per_order', 'Ingredient cost per order', py_thousands($b->cogsPerOrder(), 2), DERIVED, false, ''],
    ];

    $out = [];
    foreach ($rows as $r) {
        $a = ['key' => $r[0], 'label' => $r[1], 'value' => $r[2], 'klass' => $r[3], 'swept' => $r[4],
              'note' => $r[5], 'source' => '', 'ladder_status' => LADDER[$r[3]]];
        if ($r[0] === 'price_sensitivity') {
            $a['source'] = 'andreyeva2010; bijmolt2005 (upper reference)';
        }
        $out[] = $a;
    }
    return $out;
}

function round_list(array $xs, int $nd): array
{
    return array_map(fn ($x) => py_round((float) $x, $nd), $xs);
}

/** Everything the page needs, in the shape the template's JavaScript expects. */
function build_bundle(Slice $slice, array $frozen, Baseline $baseline, bool $includeGrid = true): array
{
    $defaults = $frozen['defaults'];
    $effectiveness = (float) $defaults['reformulation_effectiveness'];
    $comp = run_comparison($slice, $frozen, $baseline, [], $effectiveness);
    $sens = run_sensitivity($slice, $frozen, $baseline);
    $oat = one_at_a_time($sens, $frozen['sweep_labels']);
    $reg = evidence_registry($baseline, $comp['axis_settings'], $effectiveness, $defaults);

    $classCounts = [];
    foreach ($reg as $a) {
        $classCounts[$a['klass']] = ($classCounts[$a['klass']] ?? 0) + 1;
    }

    $worlds = [];
    foreach ($comp['worlds'] as $w) {
        $metrics = [];
        foreach ($w['metrics'] as $k => $v) {
            $metrics[$k] = (is_float($v)) ? py_round($v, 4) : $v;
        }
        $worlds[] = [
            'id' => $w['spec']['id'],
            'label' => $w['spec']['label'],
            'headline' => $w['spec']['headline'],
            'price_rise_pct' => $w['spec']['price_rise_pct'],
            'cogs_reduction_points' => $w['spec']['cogs_reduction_points'],
            'metrics' => $metrics,
            'ledger' => [
                'cash' => round_list($w['ledger']['cash'], 2),
                'gross_margin_pct' => round_list($w['ledger']['gross_margin_pct'], 3),
                'orders' => round_list($w['ledger']['orders'], 2),
                'revenue' => round_list($w['ledger']['revenue'], 2),
            ],
            'indices' => [
                'input_cost' => round_list($w['indices']['input_cost'], 3),
                'cogs_per_order' => round_list($w['indices']['cogs_per_order'], 3),
                'menu_price' => round_list($w['indices']['menu_price'], 3),
                'demand' => round_list($w['indices']['demand'], 3),
            ],
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
        'generated_for' => $baseline->name,
        'is_demo' => $baseline->is_demo,
        'baseline' => $baseline->summary(),
        'baseline_raw' => $baseline->toDict(),
        'intake_fields' => $frozen['intake_fields'],
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
            'verdict' => sensitivity_verdict($sens, $oat),
            'one_at_a_time' => $oat,
            'flip_attribution' => flip_attribution($sens),
            'sweep' => $frozen['sweep'],
            'sweep_labels' => $frozen['sweep_labels'],
            'points' => $points,
        ],
        'assumptions' => $reg,
        'assumption_class_counts' => $classCounts,
        'sources' => $frozen['sources'],
        'reproducibility' => [
            'module_id' => $frozen['module_id'],
            'module_semantic_hash' => $frozen['module_semantic_hash'],
            'horizon_days' => (int) $defaults['horizon_days'],
            'axis_settings' => $defaults['axis_settings'],
            'lag_setting' => 'central',
            'reformulation_effectiveness' => $effectiveness,
            'custom_elasticity' => null,
            'baseline' => $baseline->toDict(),
            'shared_fingerprint' => $frozen['shared_fingerprint'],
            'worlds' => array_map(fn ($w) => [
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
            ], $comp['worlds']),
        ],
        'language' => $frozen['language'],
    ];

    if ($includeGrid) {
        // Index trajectories do not depend on the money inputs at all — only on the supplier
        // increase, the axis settings and the COGS reduction points — so the page can apply
        // any owner's money to them exactly.
        $grid = [];
        foreach ($sens['points'] as $p) {
            $s = $p['settings'];
            $b = $baseline->withSupplierIncrease((float) $s['supplier_increase_pct']);
            $gw = [];
            foreach ($p['comparison']['worlds'] as $w) {
                $gw[$w['spec']['id']] = [
                    'demand' => round_list($w['indices']['demand'], 3),
                    'cogs' => round_list($w['indices']['cogs_per_order'], 3),
                    'price' => round_list($w['indices']['menu_price'], 2),
                ];
            }
            $grid[] = [
                'key' => [
                    'price_sensitivity' => $s['price_sensitivity'],
                    'cogs_pass_through' => $s['cogs_pass_through'],
                    'supplier_increase_pct' => (float) $s['supplier_increase_pct'],
                    'reduction_points' => cogs_reduction_points($b, (float) $s['reformulation_effectiveness']),
                    'demand_adjustment_speed' => $s['demand_adjustment_speed'],
                ],
                'worlds' => $gw,
            ];
        }
        $bundle['grid'] = $grid;
    }
    return $bundle;
}

/** Fill the template. Mirrors report.render_html: compact separators, escaped `</`. */
function render_html(array $bundle, string $templatePath): string
{
    $template = file_get_contents($templatePath);
    $payload = json_encode($bundle, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
    $payload = str_replace('</', '<\\/', $payload);
    return str_replace('__DATA__', $payload, $template);
}
