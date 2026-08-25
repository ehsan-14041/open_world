<?php
/**
 * The business layer: baseline, the three decisions, the accounting identities.
 *
 * Wedge-generic. Nothing here knows what a cafe, a shop or a salon is — the differences arrive
 * as data in assets/<wedge>.json, exported from the Python definitions. Ports
 * event_sim/wedge/{accounting,compare}.py and each wedge's worlds.py.
 *
 * The accounting deliberately lives outside the engine: the engine's only stock rule is a
 * capacity-bounded queue floored at zero, and cash must be free to go negative.
 *
 *     revenue      = units * price
 *     unit cost    = units * cost each * index/100
 *     gross profit = revenue - unit cost
 *     cash(t)      = cash(t-1) + gross profit - fixed costs per day
 *     served       = min(wanted, slots)        <- only where a wedge declares a capacity
 *
 * The file keeps its name so existing deployments' includes do not break.
 */
declare(strict_types=1);

require_once __DIR__ . '/engine.php';
require_once __DIR__ . '/canon.php';

const DAYS_PER_MONTH = 365.0 / 12.0;

/**
 * One business's figures, whatever business it is.
 *
 * Which field plays which role comes from the wedge's `copy.fields` map, so the ledger can be
 * written once: `units_per_day` is orders for a shop and appointments for a salon, and neither
 * this class nor the accounting needs to care.
 */
final class Baseline
{
    public array $values;
    private array $fields;
    private ?array $capacity;

    public function __construct(array $values, array $wedge)
    {
        $this->fields = $wedge['copy']['fields'];
        $this->capacity = $wedge['capacity'] ?? null;
        $this->values = $values;
        foreach ($values as $k => $v) {
            if ($k !== 'name' && $k !== 'is_demo' && $k !== 'notes' && is_numeric($v)) {
                $this->values[$k] = (float) $v;
            }
        }
        $this->values['name'] = (string) ($values['name'] ?? 'Unnamed business');
        $this->values['is_demo'] = (bool) ($values['is_demo'] ?? false);
        $this->values['notes'] = array_values($values['notes'] ?? []);
    }

    public function __get(string $name)
    {
        return $this->values[$name] ?? null;
    }

    public function field(string $role): float
    {
        return (float) $this->values[$this->fields[$role]];
    }

    public function withField(string $role, float $value): Baseline
    {
        $copy = $this->values;
        $copy[$this->fields[$role]] = $value;
        return new Baseline($copy, $this->wedgeShape());
    }

    public function replace(array $changes): Baseline
    {
        return new Baseline(array_merge($this->values, $changes), $this->wedgeShape());
    }

    private function wedgeShape(): array
    {
        return ['copy' => ['fields' => $this->fields], 'capacity' => $this->capacity];
    }

    public function monthlyUnits(): float   { return $this->field('units_per_day') * DAYS_PER_MONTH; }
    public function averageTicket(): float  { return $this->field('revenue') / $this->monthlyUnits(); }
    public function unitCost(): float       { return $this->field('unit_cost_total') / $this->monthlyUnits(); }
    public function dailyFixedCosts(): float { return $this->field('fixed') / DAYS_PER_MONTH; }
    public function costPct(): float        { return 100.0 * $this->field('unit_cost_total') / $this->field('revenue'); }
    public function grossMarginPct(): float { return 100.0 - $this->costPct(); }
    public function monthlyGrossProfit(): float { return $this->field('revenue') - $this->field('unit_cost_total'); }
    public function monthlyNet(): float     { return $this->monthlyGrossProfit() - $this->field('fixed'); }
    public function netMarginPct(): float   { return 100.0 * $this->monthlyNet() / $this->field('revenue'); }

    /** Slots per day, or null where the wedge has no ceiling. */
    public function capacityPerDay(): ?float
    {
        if ($this->capacity === null) {
            return null;
        }
        $u = (float) $this->values[$this->capacity['utilisation_field']];
        return $u > 0 ? ((float) $this->values[$this->capacity['units_field']]) / ($u / 100.0) : null;
    }

    /** @return string[] empty when the inputs are usable */
    public function validate(): array
    {
        $p = [];
        if ($this->field('revenue') <= 0) { $p[] = 'Monthly sales must be greater than zero.'; }
        if ($this->field('units_per_day') <= 0) { $p[] = 'The daily count must be greater than zero.'; }
        if ($this->field('unit_cost_total') <= 0) { $p[] = 'Monthly cost must be greater than zero.'; }
        if ($this->field('revenue') > 0 && $this->field('unit_cost_total') >= $this->field('revenue')) {
            $p[] = 'Cost must be below monthly sales.';
        }
        if ($this->field('fixed') < 0) { $p[] = 'Fixed costs cannot be negative.'; }
        if ($this->field('cash') < 0) { $p[] = 'Cash on hand cannot be negative.'; }
        if ($this->capacity !== null) {
            $u = (float) $this->values[$this->capacity['utilisation_field']];
            if ($u <= 0 || $u > 100) { $p[] = 'How full the diary is must be between 1% and 100%.'; }
        }
        return $p;
    }

    public function toDict(): array { return $this->values; }

    /**
     * The baseline block, from the wedge's own declaration of what is worth showing.
     * Mirrors summarise() in event_sim/wedge/report.py — one declaration, two renderers.
     */
    public function summary(array $wedge): array
    {
        $fields = $this->fields;
        $out = ['name' => $this->values['name'], 'is_demo' => $this->values['is_demo']];
        foreach ($wedge['copy']['summary_fields'] as [$name, $source, $dp]) {
            switch ($source) {
                case 'average_ticket':   $value = $this->averageTicket(); break;
                case 'cost_pct':         $value = $this->costPct(); break;
                case 'gross_margin_pct': $value = $this->grossMarginPct(); break;
                case 'monthly_net':      $value = $this->monthlyNet(); break;
                case 'net_margin_pct':   $value = $this->netMarginPct(); break;
                case 'capacity_per_day': $value = $this->capacityPerDay() ?? 0.0; break;
                default:
                    $value = isset($fields[$source])
                        ? $this->values[$fields[$source]]
                        : $this->values[$source];
            }
            $out[$name] = $dp === null ? $value : py_round((float) $value, (int) $dp);
        }
        return $out;
    }
}

/** Percentage points of unit cost removed, from the owner's low-margin share estimate. */
function reduction_points(Baseline $b, array $wedge, float $effectiveness): float
{
    $share = (float) $b->values[$wedge['worlds']['reduction']['share_field']];
    return py_round($share * $effectiveness, 3);
}

/**
 * The three decisions as engine events and interventions — the ONLY things allowed to differ
 * between worlds. Everything else is shared by construction.
 */
function build_worlds(Slice $slice, Baseline $b, array $wedge, float $effectiveness): array
{
    $defaults = $wedge['defaults'];
    $shape = $wedge['worlds'];
    $horizon = (int) $defaults['horizon_days'];
    $shock = (float) $b->values[$shape['event']['magnitude_field']];
    $reduction = reduction_points($b, $wedge, $effectiveness);

    $event = [
        'id' => $shape['event']['id'],
        'label' => str_replace('{shock}', py_g($shock), $shape['event']['label']),
        'description' => $shape['event']['description'],
        'targets' => [$shape['event']['target'] => $shock],
        'start_turn' => 1,
        'duration' => $horizon,
        'shape' => 'step',
        'status' => 'user_assumption',
        'evidence' => [],
    ];

    $worlds = [];
    foreach ($shape['options'] as $opt) {
        $interventions = [];
        if ($opt['price_rise_pct'] > 0) {
            $interventions[] = $slice->intervention($shape['levers']['price'],
                (float) $opt['price_rise_pct'], 1, $horizon);
        }
        if (!empty($opt['uses_reduction'])) {
            $interventions[] = $slice->intervention($shape['levers']['reduce'], $reduction, 1, $horizon);
        }
        $worlds[] = [
            'id' => $opt['id'],
            'label' => $opt['label'],
            'headline' => $opt['headline'],
            'price_rise_pct' => (float) $opt['price_rise_pct'],
            'cogs_reduction_points' => !empty($opt['uses_reduction']) ? $reduction : 0.0,
            'events' => [$event],
            'interventions' => $interventions,
        ];
    }
    return $worlds;
}

/** Daily business quantities for one world. Index 0 is the day before anything changes. */
function build_ledger(Baseline $b, array $demandIndex, array $priceIndex, array $cogsIndex,
                      ?float $capacity = null): array
{
    $n = min(count($demandIndex), count($priceIndex), count($cogsIndex));
    $led = ['days' => [], 'orders' => [], 'price' => [], 'revenue' => [], 'cogs' => [],
            'gross_profit' => [], 'gross_margin_pct' => [], 'net' => [], 'cash' => [],
            'demanded' => [], 'turned_away' => [], 'utilisation_pct' => []];
    $cash = $b->field('cash');
    $fixed = $b->dailyFixedCosts();
    $ticket = $b->averageTicket();
    $unit = $b->unitCost();
    $units = $b->field('units_per_day');

    for ($day = 0; $day < $n; $day++) {
        $wanted = $units * $demandIndex[$day] / 100.0;
        if ($capacity === null) {
            $orders = $wanted;
        } else {
            $orders = min($wanted, $capacity);
            $led['demanded'][] = $wanted;
            $led['turned_away'][] = max(0.0, $wanted - $orders);
            $led['utilisation_pct'][] = $capacity > 0 ? 100.0 * $orders / $capacity : 0.0;
        }
        $price = $ticket * $priceIndex[$day] / 100.0;
        $revenue = $orders * $price;
        $cogs = $orders * $unit * $cogsIndex[$day] / 100.0;
        $gp = $revenue - $cogs;
        $net = $gp - $fixed;
        if ($day > 0) {
            $cash += $net;                       // day 0 is the position before anything changes
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

/** The quantities an owner would actually use to choose. */
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

    $metrics = [
        'monthly_revenue' => $monthlyRevenue,
        'monthly_gross_profit' => $monthlyGp,
        'monthly_net' => $monthlyNet,
        'monthly_orders' => $monthlyOrders,
        'gross_margin_pct_end' => $led['gross_margin_pct'][$last],
        'worst_gross_margin_pct' => $led['gross_margin_pct'][$worstMarginDay],
        'worst_gross_margin_day' => $worstMarginDay,
        'orders_change_pct' => 100.0 * ($led['orders'][$last] / $led['orders'][0] - 1.0),
        'revenue_change_pct' => 100.0 * ($monthlyRevenue / $b->field('revenue') - 1.0),
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

    // Capacity figures exist only where a capacity limit was applied, so a wedge without one
    // produces exactly the metric set it would have without this code path.
    if ($led['utilisation_pct']) {
        $capacity = $led['utilisation_pct'][$last] > 0
            ? $led['orders'][$last] / ($led['utilisation_pct'][$last] / 100.0) : 0.0;
        $metrics['utilisation_pct_end'] = $led['utilisation_pct'][$last];
        $metrics['utilisation_pct_start'] = $led['utilisation_pct'][0];
        $metrics['turned_away_per_day_end'] = $led['turned_away'][$last];
        $metrics['turned_away_per_day_start'] = $led['turned_away'][0];
        $metrics['demanded_change_pct'] = 100.0 * ($led['demanded'][$last] / $led['demanded'][0] - 1.0);
        $metrics['revenue_per_slot_end'] = $capacity > 0 ? $led['revenue'][$last] / $capacity : 0.0;
        $metrics['gross_profit_per_slot_end'] = $capacity > 0 ? $led['gross_profit'][$last] / $capacity : 0.0;
        $metrics['monthly_turned_away'] = window_sum($led, 'turned_away', $tailStart, $last) * $scale;
    }
    return $metrics;
}

/** One slice, one config, three runs. */
function run_comparison(Slice $slice, array $wedge, Baseline $b, array $axisSettings, float $effectiveness): array
{
    $defaults = $wedge['defaults'];
    $roles = $wedge['roles'];
    $horizon = (int) $defaults['horizon_days'];
    $settings = array_merge($defaults['axis_settings'], $axisSettings);
    foreach ($slice->axes as $axis) {
        if (!isset($settings[$axis['id']])) {
            $settings[$axis['id']] = $axis['default_setting'];
        }
    }
    $capacity = $b->capacityPerDay();

    $worlds = [];
    foreach (build_worlds($slice, $b, $wedge, $effectiveness) as $spec) {
        $sim = new Simulation($slice, $settings, $spec['events'], $spec['interventions'], $horizon);
        $sim->run();
        $led = build_ledger($b, $sim->series($roles['demand_var']), $sim->series($roles['price_var']),
                            $sim->series($roles['unit_cost_var']), $capacity);
        $indices = [];
        foreach ($roles['index_vars'] as $name) {
            $indices[$name] = $sim->series($name);
        }
        $worlds[] = [
            'spec' => $spec,
            'indices' => $indices,
            'ledger' => $led,
            'metrics' => decision_metrics($led, $b, $horizon),
            'fingerprint' => engine_fingerprint($wedge, $spec['events'], $spec['interventions']),
            'trajectory_fingerprint' => trajectory_fingerprint($wedge, $spec['events'], $spec['interventions']),
        ];
    }
    return ['worlds' => $worlds, 'axis_settings' => $settings, 'effectiveness' => $effectiveness];
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
