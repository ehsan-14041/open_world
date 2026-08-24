<?php
/**
 * The cafe layer: baseline, the three decisions, the accounting identities, the sensitivity
 * sweep and the report bundle.
 *
 * Ports event_sim/cafe/{baseline,worlds,accounting,sensitivity,evidence,report}.py. The
 * accounting deliberately lives outside the engine: the engine's only stock rule is a
 * capacity-bounded queue floored at zero, and cash must be free to go negative.
 *
 *     revenue = orders * price
 *     cogs    = orders * cogs_per_order * index/100
 *     cash(t) = cash(t-1) + gross_profit - fixed_costs_per_day
 */
declare(strict_types=1);

require_once __DIR__ . '/engine.php';
require_once __DIR__ . '/canon.php';

const DAYS_PER_MONTH = 365.0 / 12.0;

final class Baseline
{
    public string $name;
    public float $monthly_revenue;
    public float $daily_orders;
    public float $monthly_cogs;
    public float $monthly_fixed_costs;
    public float $cash_on_hand;
    public float $supplier_increase_pct;
    public float $low_margin_share_pct;
    public bool $is_demo;
    public array $notes;

    public function __construct(array $d)
    {
        $this->name = (string) ($d['name'] ?? 'Unnamed cafe');
        $this->monthly_revenue = (float) $d['monthly_revenue'];
        $this->daily_orders = (float) $d['daily_orders'];
        $this->monthly_cogs = (float) $d['monthly_cogs'];
        $this->monthly_fixed_costs = (float) $d['monthly_fixed_costs'];
        $this->cash_on_hand = (float) $d['cash_on_hand'];
        $this->supplier_increase_pct = (float) ($d['supplier_increase_pct'] ?? 30.0);
        $this->low_margin_share_pct = (float) ($d['low_margin_share_pct'] ?? 20.0);
        $this->is_demo = (bool) ($d['is_demo'] ?? false);
        $this->notes = array_values($d['notes'] ?? []);
    }

    public function withSupplierIncrease(float $pct): Baseline
    {
        $copy = clone $this;
        $copy->supplier_increase_pct = $pct;
        return $copy;
    }

    public function averageOrderValue(): float { return $this->monthly_revenue / ($this->daily_orders * DAYS_PER_MONTH); }
    public function cogsPerOrder(): float      { return $this->monthly_cogs / ($this->daily_orders * DAYS_PER_MONTH); }
    public function dailyFixedCosts(): float   { return $this->monthly_fixed_costs / DAYS_PER_MONTH; }
    public function cogsPct(): float           { return 100.0 * $this->monthly_cogs / $this->monthly_revenue; }
    public function grossMarginPct(): float    { return 100.0 - $this->cogsPct(); }
    public function monthlyGrossProfit(): float { return $this->monthly_revenue - $this->monthly_cogs; }
    public function monthlyNet(): float        { return $this->monthlyGrossProfit() - $this->monthly_fixed_costs; }
    public function netMarginPct(): float      { return 100.0 * $this->monthlyNet() / $this->monthly_revenue; }

    /** @return string[] empty when the inputs are usable */
    public function validate(): array
    {
        $p = [];
        if ($this->monthly_revenue <= 0) { $p[] = 'Monthly sales must be greater than zero.'; }
        if ($this->daily_orders <= 0) { $p[] = 'Orders per day must be greater than zero.'; }
        if ($this->monthly_cogs <= 0) { $p[] = 'Monthly ingredient cost must be greater than zero.'; }
        if ($this->monthly_revenue > 0 && $this->monthly_cogs >= $this->monthly_revenue) {
            $p[] = 'Ingredient cost must be below monthly sales.';
        }
        if ($this->monthly_fixed_costs < 0) { $p[] = 'Fixed costs cannot be negative.'; }
        if ($this->cash_on_hand < 0) { $p[] = 'Cash on hand cannot be negative.'; }
        if ($this->supplier_increase_pct < 0 || $this->supplier_increase_pct > 200) {
            $p[] = 'The supplier increase should be between 0% and 200%.';
        }
        if ($this->low_margin_share_pct < 0 || $this->low_margin_share_pct > 100) {
            $p[] = 'The low-margin share should be between 0% and 100%.';
        }
        return $p;
    }

    public function toDict(): array
    {
        return [
            'name' => $this->name,
            'monthly_revenue' => $this->monthly_revenue,
            'daily_orders' => $this->daily_orders,
            'monthly_cogs' => $this->monthly_cogs,
            'monthly_fixed_costs' => $this->monthly_fixed_costs,
            'cash_on_hand' => $this->cash_on_hand,
            'supplier_increase_pct' => $this->supplier_increase_pct,
            'low_margin_share_pct' => $this->low_margin_share_pct,
            'is_demo' => $this->is_demo,
            'notes' => $this->notes,
        ];
    }

    public function summary(): array
    {
        return [
            'name' => $this->name,
            'is_demo' => $this->is_demo,
            'monthly_revenue' => py_round($this->monthly_revenue, 2),
            'daily_orders' => py_round($this->daily_orders, 1),
            'average_order_value' => py_round($this->averageOrderValue(), 2),
            'monthly_cogs' => py_round($this->monthly_cogs, 2),
            'cogs_pct' => py_round($this->cogsPct(), 1),
            'gross_margin_pct' => py_round($this->grossMarginPct(), 1),
            'monthly_fixed_costs' => py_round($this->monthly_fixed_costs, 2),
            'monthly_net' => py_round($this->monthlyNet(), 2),
            'net_margin_pct' => py_round($this->netMarginPct(), 1),
            'cash_on_hand' => py_round($this->cash_on_hand, 2),
            'supplier_increase_pct' => $this->supplier_increase_pct,
            'low_margin_share_pct' => $this->low_margin_share_pct,
        ];
    }
}

/** Percentage points of average COGS removed, from the owner's low-margin share estimate. */
function cogs_reduction_points(Baseline $b, float $effectiveness): float
{
    return py_round($b->low_margin_share_pct * $effectiveness, 3);
}

/**
 * The three decisions as engine events and interventions. These are the ONLY things allowed
 * to differ between worlds: same slice, same config, same horizon, same coefficients.
 */
function build_worlds(Slice $slice, Baseline $b, array $defaults, float $effectiveness): array
{
    $horizon = (int) $defaults['horizon_days'];
    $priseB = (float) $defaults['price_rise_b'];
    $priseC = (float) $defaults['price_rise_c'];
    $reduction = cogs_reduction_points($b, $effectiveness);

    $shock = [
        'id' => 'supplier_cost_increase',
        'label' => 'Supplier prices +' . py_g($b->supplier_increase_pct) . '%',
        'description' => 'Ingredient / input prices rise and stay at the new level for 90 days.',
        'targets' => ['input_cost' => $b->supplier_increase_pct],
        'start_turn' => 1,
        'duration' => $horizon,
        'shape' => 'step',
        'status' => 'user_assumption',
        'evidence' => [],
    ];

    return [
        [
            'id' => 'A', 'label' => 'Do nothing',
            'headline' => 'Hold prices. Absorb the full cost increase.',
            'price_rise_pct' => 0.0, 'cogs_reduction_points' => 0.0,
            'events' => [$shock], 'interventions' => [],
        ],
        [
            'id' => 'B', 'label' => 'Raise prices ' . py_g($priseB) . '%',
            'headline' => 'Pass most of the increase to customers with a ' . py_g($priseB) . '% average price rise.',
            'price_rise_pct' => $priseB, 'cogs_reduction_points' => 0.0,
            'events' => [$shock],
            'interventions' => [$slice->intervention('raise_prices', $priseB, 1, $horizon)],
        ],
        [
            'id' => 'C', 'label' => 'Raise prices ' . py_g($priseC) . '% + trim the menu',
            'headline' => 'A smaller ' . py_g($priseC) . '% price rise, plus removing or reformulating '
                . 'low-margin items to cut ingredient cost per order.',
            'price_rise_pct' => $priseC, 'cogs_reduction_points' => $reduction,
            'events' => [$shock],
            'interventions' => [
                $slice->intervention('raise_prices', $priseC, 1, $horizon),
                $slice->intervention('reformulate_menu', $reduction, 1, $horizon),
            ],
        ],
    ];
}

/** Daily business quantities for one world. Index 0 is the day before the shock. */
function build_ledger(Baseline $b, array $demandIndex, array $priceIndex, array $cogsIndex): array
{
    $n = min(count($demandIndex), count($priceIndex), count($cogsIndex));
    $led = ['days' => [], 'orders' => [], 'price' => [], 'revenue' => [], 'cogs' => [],
            'gross_profit' => [], 'gross_margin_pct' => [], 'net' => [], 'cash' => []];
    $cash = $b->cash_on_hand;
    $fixed = $b->dailyFixedCosts();
    $aov = $b->averageOrderValue();
    $cpo = $b->cogsPerOrder();

    for ($day = 0; $day < $n; $day++) {
        $orders = $b->daily_orders * $demandIndex[$day] / 100.0;
        $price = $aov * $priceIndex[$day] / 100.0;
        $revenue = $orders * $price;
        $cogs = $orders * $cpo * $cogsIndex[$day] / 100.0;
        $gp = $revenue - $cogs;
        $net = $gp - $fixed;
        if ($day > 0) {
            $cash += $net;                       // day 0 is the position before the shock
        }
        $led['days'][] = $day;
        $led['orders'][] = $orders;
        $led['price'][] = $price;
        $led['revenue'][] = $revenue;
        $led['cogs'][] = $cogs;
        $led['gross_profit'][] = $gp;
        $led['gross_margin_pct'][] = $revenue > 0 ? 100.0 * $gp / $revenue : 0.0;
        $led['net'][] = $net;
        $led['cash'][] = $cash;
    }
    return $led;
}

function window_sum(array $led, string $key, int $start, int $end): float
{
    $total = 0.0;
    for ($i = $start; $i <= $end; $i++) {
        $total += $led[$key][$i];
    }
    return $total;
}

/** The quantities a cafe owner would actually use to choose. */
function decision_metrics(array $led, Baseline $b, int $horizon = 90): array
{
    $last = min($horizon, count($led['days']) - 1);
    $tailStart = max(1, $last - 29);
    $tailDays = $last - $tailStart + 1;
    $scale = DAYS_PER_MONTH / $tailDays;

    $monthlyRevenue = window_sum($led, 'revenue', $tailStart, $last) * $scale;
    $monthlyGp = window_sum($led, 'gross_profit', $tailStart, $last) * $scale;
    $monthlyNet = window_sum($led, 'net', $tailStart, $last) * $scale;
    $monthlyOrders = window_sum($led, 'orders', $tailStart, $last) * $scale;

    $worstMarginDay = 1;
    for ($d = 1; $d <= $last; $d++) {
        if ($led['gross_margin_pct'][$d] < $led['gross_margin_pct'][$worstMarginDay]) {
            $worstMarginDay = $d;
        }
    }
    $minCashDay = 0;
    for ($d = 0; $d <= $last; $d++) {
        if ($led['cash'][$d] < $led['cash'][$minCashDay]) {
            $minCashDay = $d;
        }
    }
    $firstNegative = null;
    $goesNegative = false;
    for ($d = 0; $d <= $last; $d++) {
        if ($led['cash'][$d] < 0) {
            $goesNegative = true;
            if ($firstNegative === null) {
                $firstNegative = $d;
            }
        }
    }
    if ($monthlyNet >= 0) {
        $runway = null;
    } elseif ($led['cash'][$last] <= 0) {
        $runway = 0.0;
    } else {
        $runway = $led['cash'][$last] / (-$monthlyNet);
    }

    return [
        'monthly_revenue' => $monthlyRevenue,
        'monthly_gross_profit' => $monthlyGp,
        'monthly_net' => $monthlyNet,
        'monthly_orders' => $monthlyOrders,
        'gross_margin_pct_end' => $led['gross_margin_pct'][$last],
        'worst_gross_margin_pct' => $led['gross_margin_pct'][$worstMarginDay],
        'worst_gross_margin_day' => $worstMarginDay,
        'orders_change_pct' => 100.0 * ($led['orders'][$last] / $led['orders'][0] - 1.0),
        'revenue_change_pct' => 100.0 * ($monthlyRevenue / $b->monthly_revenue - 1.0),
        'cash_day_30' => $led['cash'][min(30, $last)],
        'cash_day_90' => $led['cash'][$last],
        'cash_change_90' => $led['cash'][$last] - $led['cash'][0],
        'min_cash' => $led['cash'][$minCashDay],
        'min_cash_day' => $minCashDay,
        'cash_goes_negative' => $goesNegative,
        'first_negative_day' => $firstNegative,
        'runway_months_at_end' => $runway,
        'cumulative_gross_profit_90' => window_sum($led, 'gross_profit', 1, $last),
        'cumulative_net_90' => window_sum($led, 'net', 1, $last),
    ];
}

/** One slice, one config, three runs. */
function run_comparison(Slice $slice, array $frozen, Baseline $b, array $axisSettings, float $effectiveness): array
{
    $defaults = $frozen['defaults'];
    $horizon = (int) $defaults['horizon_days'];
    $settings = array_merge($defaults['axis_settings'], $axisSettings);
    foreach ($slice->axes as $axis) {
        if (!isset($settings[$axis['id']])) {
            $settings[$axis['id']] = $axis['default_setting'];
        }
    }

    $worlds = [];
    foreach (build_worlds($slice, $b, $defaults, $effectiveness) as $spec) {
        $sim = new Simulation($slice, $settings, $spec['events'], $spec['interventions'], $horizon);
        $sim->run();
        $led = build_ledger($b, $sim->series('demand'), $sim->series('menu_price'), $sim->series('cogs_per_order'));
        $worlds[] = [
            'spec' => $spec,
            'indices' => [
                'input_cost' => $sim->series('input_cost'),
                'cogs_per_order' => $sim->series('cogs_per_order'),
                'menu_price' => $sim->series('menu_price'),
                'demand' => $sim->series('demand'),
            ],
            'ledger' => $led,
            'metrics' => decision_metrics($led, $b, $horizon),
            'fingerprint' => engine_fingerprint($frozen, $spec['events'], $spec['interventions']),
        ];
    }
    return ['worlds' => $worlds, 'axis_settings' => $settings, 'reformulation_effectiveness' => $effectiveness];
}

/** World ids, best first, on a metric where higher is better. Ties keep A, B, C order. */
function ranking(array $comp, string $key = 'cash_day_90'): array
{
    $rows = [];
    foreach ($comp['worlds'] as $i => $w) {
        $rows[] = [$w['spec']['id'], $w['metrics'][$key], $i];
    }
    usort($rows, function ($x, $y) {
        if ($x[1] === $y[1]) {
            return $x[2] <=> $y[2];              // stable, like Python's sorted
        }
        return $y[1] <=> $x[1];
    });
    return array_map(fn ($r) => $r[0], $rows);
}

function world_by_id(array $comp, string $id): array
{
    foreach ($comp['worlds'] as $w) {
        if ($w['spec']['id'] === $id) {
            return $w;
        }
    }
    throw new RuntimeException("No world $id");
}
