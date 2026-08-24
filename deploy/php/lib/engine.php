<?php
/**
 * PHP port of the deviation-space engine, restricted to the path the cafe module executes.
 *
 * Mirrors event_sim/engine.py step for step. It deliberately does NOT port stocks, forking,
 * checkpoints, provenance or the causal trace: the cafe module has no stock variables and the
 * report needs only the trajectories. Everything that does run here is a line-by-line
 * transcription, because the whole value of the port is that it produces the same numbers.
 *
 *     pressure(v,t) = sum over edges of coef(e) * dev(source(e), t - lag(e))
 *     dev(v,t+1)    = dev(v,t) + response(v) * (pressure - dev(v,t))
 *
 * An event HOLDS a variable at a displacement — it replaces the relaxed value rather than
 * adding to it. An intervention OFFSETS the observed value without entering the endogenous
 * state, so it holds its effect steady instead of ratcheting turn after turn.
 */
declare(strict_types=1);

final class Slice
{
    /** @var array<int,array<string,mixed>> */ public array $variables;
    /** @var array<int,array<string,mixed>> */ public array $edges;
    /** @var array<string,array<string,mixed>> */ public array $axes = [];
    /** @var array<int,array<string,mixed>> */ public array $interventions;
    /** @var array<string,array<int,array<string,mixed>>> */ private array $edgesByTarget = [];

    public function __construct(array $slice)
    {
        $this->variables = $slice['variables'];
        $this->edges = $slice['edges'];
        $this->interventions = $slice['interventions'];
        foreach ($slice['axes'] as $axis) {
            $this->axes[$axis['id']] = $axis;
        }
        foreach ($this->edges as $edge) {
            $this->edgesByTarget[$edge['target']][] = $edge;
        }
    }

    public function edgesInto(string $varId): array
    {
        return $this->edgesByTarget[$varId] ?? [];
    }

    public function variable(string $id): ?array
    {
        foreach ($this->variables as $v) {
            if ($v['id'] === $id) {
                return $v;
            }
        }
        return null;
    }

    /** Instantiate a library-defined intervention, overriding only its parameters. */
    public function intervention(string $id, float $magnitude, int $startTurn, int $duration): array
    {
        foreach ($this->interventions as $spec) {
            if (($spec['id'] ?? null) === $id) {
                return [
                    'id' => $id,
                    'label' => (string) ($spec['label'] ?? $id),
                    'magnitude' => $magnitude,
                    'start_turn' => $startTurn,
                    'duration' => $duration,
                    'effects_per_unit' => array_map('floatval', $spec['effects_per_unit'] ?? []),
                    'status' => (string) ($spec['status'] ?? 'expert_assumption'),
                ];
            }
        }
        throw new RuntimeException("Intervention '$id' is not defined in the slice.");
    }
}

final class Simulation
{
    private Slice $slice;
    private array $axisSettings;
    private array $events;
    private array $interventions;
    private int $turns;

    /** @var array<string,float> current values, in the variables' own units */
    private array $values = [];
    /** @var array<int,array<string,float>> observed deviation — what causal edges read */
    private array $devHistory = [];
    /** @var array<int,array<string,float>> endogenous deviation — what relaxation acts on */
    private array $endoHistory = [];
    /** @var array<string,array<int,float>> */
    private array $series = [];
    private bool $clampEngaged = false;

    public function __construct(Slice $slice, array $axisSettings, array $events, array $interventions, int $turns)
    {
        $this->slice = $slice;
        $this->axisSettings = $axisSettings;
        $this->events = $events;
        $this->interventions = $interventions;
        $this->turns = $turns;

        $dev = [];
        foreach ($slice->variables as $v) {
            $this->values[$v['id']] = (float) $v['baseline'];
            $dev[$v['id']] = 0.0;                       // value == baseline at turn 0
            $this->series[$v['id']] = [(float) $v['baseline']];
        }
        $this->devHistory[0] = $dev;
        $this->endoHistory[0] = $dev;
    }

    /** Which point of an edge's evidenced effect range this world uses. */
    private function effectSetting(array $edge): string
    {
        $axisId = $edge['axis'] ?? null;
        $axis = null;
        if ($axisId !== null && isset($this->slice->axes[$axisId])) {
            $axis = $this->slice->axes[$axisId];
        } else {
            foreach ($this->slice->axes as $a) {
                if (in_array($edge['id'], $a['applies_to'], true)) {
                    $axis = $a;
                    break;
                }
            }
        }
        if ($axis === null) {
            return 'central';
        }
        $setting = $this->axisSettings[$axis['id']] ?? $axis['default_setting'];
        $value = $axis['mapping'][$setting]['effect'] ?? null;
        if (in_array($value, ['low', 'central', 'high'], true)) {
            return (string) $value;
        }
        return in_array($setting, ['low', 'central', 'high'], true) ? (string) $setting : 'central';
    }

    /** Signed coefficient. Polarity is authoritative, regardless of how the range was written. */
    private function coefficient(array $edge, string $setting): float
    {
        $magnitude = abs((float) $edge['effect'][$setting]);
        return $edge['polarity'] === 'negative' ? -$magnitude : $magnitude;
    }

    /** Per-turn response rate, after any assumption axis bound to this variable. */
    private function response(array $var): float
    {
        $multiplier = 1.0;
        foreach ($this->slice->axes as $axis) {
            if (in_array($var['id'], $axis['applies_to'], true) || ($var['axis'] ?? null) === $axis['id']) {
                $setting = $this->axisSettings[$axis['id']] ?? $axis['default_setting'];
                $m = $axis['mapping'][$setting]['response_multiplier'] ?? null;
                if (is_numeric($m) && (float) $m > 0) {
                    $multiplier *= (float) $m;
                }
            }
        }
        return max(0.0, min(1.0, ((float) $var['response']) * $multiplier));
    }

    private function devAt(string $varId, int $turn): float
    {
        if ($turn < 0 || $turn >= count($this->devHistory)) {
            return 0.0;
        }
        return (float) ($this->devHistory[$turn][$varId] ?? 0.0);
    }

    /** Displacement each event applies to its targets at `turn` (empty when inactive). */
    private function eventMagnitudes(int $turn): array
    {
        $out = [];
        foreach ($this->events as $event) {
            $active = $turn >= $event['start_turn'] && $turn < $event['start_turn'] + max(1, $event['duration']);
            if (!$active) {
                continue;
            }
            $dur = max(1, $event['duration']);
            if ($event['shape'] === 'pulse') {
                $factor = $turn === $event['start_turn'] ? 1.0 : 0.0;
            } elseif ($event['shape'] === 'ramp') {
                $factor = min(1.0, ($turn - $event['start_turn'] + 1) / (float) $dur);
            } else {
                $factor = 1.0;
            }
            if ($factor === 0.0) {
                continue;
            }
            foreach ($event['targets'] as $varId => $magnitude) {
                $out[$varId] = (float) $magnitude * $factor;
            }
        }
        return $out;
    }

    private function interventionOffsets(int $turn): array
    {
        $out = [];
        foreach ($this->interventions as $iv) {
            $active = $turn >= $iv['start_turn'] && $turn < $iv['start_turn'] + max(1, $iv['duration']);
            if (!$active) {
                continue;
            }
            foreach ($iv['effects_per_unit'] as $varId => $perUnit) {
                $out[$varId] = ($out[$varId] ?? 0.0) + (float) $perUnit * (float) $iv['magnitude'];
            }
        }
        return $out;
    }

    private function step(int $t): void
    {
        $nextTurn = $t + 1;
        $currentEndo = $this->endoHistory[$t];

        $holds = [];
        foreach ($this->eventMagnitudes($nextTurn) as $varId => $magnitude) {
            $var = $this->slice->variable($varId);
            if ($var !== null) {
                $holds[$varId] = $magnitude / (float) $var['scale'];
            }
        }
        $offsets = [];
        foreach ($this->interventionOffsets($nextTurn) as $varId => $magnitude) {
            $var = $this->slice->variable($varId);
            if ($var !== null) {
                $offsets[$varId] = $magnitude / (float) $var['scale'];
            }
        }

        $newDev = [];
        $offsetByVar = [];
        foreach ($this->slice->variables as $var) {
            $vid = $var['id'];
            $pressure = 0.0;
            foreach ($this->slice->edgesInto($vid) as $edge) {
                // A conservation edge is realised by the stock rule, not by a linear
                // coefficient; propagating it here as well would double-count the mechanism.
                if (($edge['mechanism_type'] ?? '') === 'conservation') {
                    continue;
                }
                $setting = $this->effectSetting($edge);
                $pressure += $this->coefficient($edge, $setting) * $this->devAt($edge['source'], $t - (int) $edge['lag']);
            }

            $endo = (float) ($currentEndo[$vid] ?? 0.0);
            $relaxed = $endo + $this->response($var) * ($pressure - $endo);

            // An event holds the variable at its displacement; it replaces relaxation.
            $baseDev = array_key_exists($vid, $holds) ? $holds[$vid] : $relaxed;
            $offsetTotal = $offsets[$vid] ?? 0.0;

            $offsetByVar[$vid] = $offsetTotal;
            $newDev[$vid] = $baseDev + $offsetTotal;
        }

        // Clamping is authoritative: fold it back into deviation space so history stays
        // consistent with the values reported. The exogenous offset is then subtracted back
        // out of the endogenous state, so an intervention holds its effect steady.
        $finalDev = [];
        $finalEndo = [];
        foreach ($this->slice->variables as $var) {
            $vid = $var['id'];
            $raw = (float) $var['baseline'] + (float) $var['scale'] * $newDev[$vid];
            $clamped = $raw;
            if ($var['min'] !== null && $clamped < (float) $var['min']) {
                $clamped = (float) $var['min'];
            }
            if ($var['max'] !== null && $clamped > (float) $var['max']) {
                $clamped = (float) $var['max'];
            }
            if (abs($clamped - $raw) > 1e-12) {
                $this->clampEngaged = true;
            }
            $this->values[$vid] = $clamped;
            $finalDev[$vid] = ($clamped - (float) $var['baseline']) / (float) $var['scale'];
            $finalEndo[$vid] = $finalDev[$vid] - $offsetByVar[$vid];
            $this->series[$vid][] = $clamped;
        }
        $this->devHistory[$nextTurn] = $finalDev;
        $this->endoHistory[$nextTurn] = $finalEndo;
    }

    public function run(): void
    {
        for ($t = 0; $t < $this->turns; $t++) {
            $this->step($t);
        }
    }

    public function series(string $varId): array
    {
        return $this->series[$varId];
    }

    public function clampEngaged(): bool
    {
        return $this->clampEngaged;
    }
}
