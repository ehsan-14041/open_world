# Hampton Roads detectability — verdict `HAMPTON_ROADS_LOW_POWER`

> **Outcome: STOP.** No continuous series was acquired, no anomaly detection was run, no
> candidate window exists, and H1 was not executed. The frozen model, evaluation-code and H1
> hashes are unchanged.
>
> This is a valid negative result, reached by the pre-registered analysis rather than around
> it.

## 1. What was acquired

| | |
|---|---|
| Sampling rule | frozen in [HAMPTON_ROADS_MEASUREMENT_FREEZE.md](HAMPTON_ROADS_MEASUREMENT_FREEZE.md) §5, before acquisition |
| Windows | 8 × 7 days, one per quarter, 2020-Q3 → 2022-Q2 |
| Days requested | 56 |
| Days acquired | **56 — zero missing, zero failures** |
| National AIS transferred | **17.1 GB** (56 daily files, ~284–299 MB each), 33.6 min |
| National rows scanned | ~7.2–9.0 M per day |
| Regional rows retained | 8,164 – 23,505 per day |
| Per-file provenance | SHA-256 of every national archive recorded in `data/external/ais/metadata/` |

## 2. Baseline distribution of `anchorage_occupancy`

Distinct cargo/tanker MMSI observed stationary inside a commercial anchorage, per day.

| Statistic | Value |
|---|---|
| n | 56 |
| mean | 11.48 |
| median | 9.0 |
| variance | 50.04 |
| standard deviation | 7.07 |
| MAD (pooled) | 5.0 |
| min / p10 / p25 / p75 / p90 / max | 1 / 4 / 5 / 18 / 22 / 26 |
| dispersion index (var/mean) | **4.36** |
| autocorrelation lag-1 / lag-2 | **0.932 / 0.862** |

Weekday means run 10.9 – 12.5 — no meaningful weekly cycle.

Entries: mean 1.90/day, max 6. Exits: mean 1.75/day, max 5.

### 2.1 Dwell

174 spells, of which **130 are censored** by a window edge and only **44 completed**.
Completed dwell: mean 20.9 h, median 8.6 h, p90 61.0 h, max 106.7 h.

The censoring rate is a direct consequence of 7-day windows: any vessel staying longer than
the window necessarily touches an edge. Completed spells are therefore biased toward short
stays, and the dwell figures above **understate** true dwell. They are not used in the
verdict.

## 3. The finding that decides the question

Occupancy is not stationary across the baseline. It rises monotonically:

| Window | Mean occupancy | Mean vessels in region | occupancy / in-region |
|---|---|---|---|
| 2020-Q3 | 3.29 | 28.0 | 0.117 |
| 2020-Q4 | 4.14 | 32.4 | 0.128 |
| 2021-Q1 | 5.86 | 34.9 | 0.168 |
| 2021-Q2 | 8.14 | 44.7 | 0.182 |
| 2021-Q3 | 11.29 | 48.9 | 0.231 |
| 2021-Q4 | 17.29 | 56.1 | 0.308 |
| 2022-Q1 | 21.29 | 57.6 | 0.370 |
| 2022-Q2 | 20.57 | 58.7 | 0.350 |

**Occupancy grew 6.26× while vessels in region grew 2.10×.** Roughly a factor of 2 is
attributable to more deep-draft vessels being observed at all — AIS receiver coverage and
Class-A carriage both increased over this period — and the remaining ~3× is a real rise in
the *fraction* of in-region vessels sitting in commercial anchorages. Both components are
slow drift; neither is a disruption.

### 3.1 Variance decomposition

| Component | Variance | Share |
|---|---|---|
| Total | 50.04 | 100% |
| Within-window (day-to-day noise) | 3.00 | **6.0%** |
| Between-window (trend) | 47.04 | **94.0%** |

| | |
|---|---|
| Pooled MAD (trend intact) | 5.00 |
| Within-window MAD (trend removed) | **0.857** |
| Level shift from trend alone | **18.0 vessels** |

The pooled spread this analysis was going to build a threshold from is almost entirely
drift. Day-to-day variation is nearly six times smaller than it appears.

## 4. Verdict

### 4.1 What the pre-registered criteria returned

Applied as written, without modification:

```
passed: true      reasons: []      trigger_level: 29.0      baseline_trigger_rate: 0.0
```

All four coded low-power criteria — anchorage unused, baseline already firing, missingness,
dwell uncensorable — returned PASS. That is recorded first, before any interpretation,
because it is what the rule said.

### 4.2 Why the honest verdict is nevertheless LOW_POWER

The coded criteria tested level, spread, missingness and censoring. **They did not test
stationarity**, and the series is strongly non-stationary. Applying them mechanically
produces a pass that does not mean what a pass is supposed to mean.

The decisive numbers:

- The frozen trigger level is **29.0**. The **maximum occupancy ever observed** across two
  years of baseline is **26**. The threshold sits 3 vessels above anything that has ever
  happened, so `baseline_trigger_rate = 0.0` reflects a rule that essentially cannot fire —
  not a rule with good separation.
- The trend alone moves the level by **18 vessels**, against a true day-to-day MAD of
  **0.86**. Any fixed-level rule applied to a longer series would therefore fire as a
  function of *when* in the trend the window sits, not whether a disruption occurred. A
  detection would be guaranteed at the late end of whatever period was acquired.

This is exactly the stopping condition the protocol lists as *"variance is comparable to any
plausible disruption magnitude"*. It is satisfied — not because occupancy is too small, but
because ordinary variation over the baseline is dominated by drift of a magnitude that
swamps the signal a multi-day disruption would produce.

**Verdict: `HAMPTON_ROADS_LOW_POWER`.**

### 4.3 What was not done, deliberately

- **No threshold was lowered or re-derived.** `K_LEVEL`, `MAD_FLOOR`, `PERSISTENCE_DAYS` and
  `K_DWELL` hold their declared values.
- **No trend-aware rule was substituted.** Detrending, differencing, or a rolling-baseline
  threshold would very likely make detection work here — and inventing one now, after seeing
  the data that motivates it, is precisely the post-hoc move this protocol exists to prevent.
  If such a rule is wanted it must be declared as a **new, separately named rule** with its
  own pre-registration, in the same way defects are superseded rather than edited.
- **No continuous 120–180 day series was acquired.** It would have cost roughly 35–55 GB to
  run a detector already known to be invalid on this series.
- **H1 was not run.**

## 5. Count-noise assessment

Requested explicitly, and it cuts the other way from what was feared.

Occupancy is *not* a fragile small count here. Median 9, p75 18, max 26 — there is ample
dynamic range, and the earlier worry that Poisson noise on counts of 3–4 would swamp any
signal is not supported once the clipped bounding box is fixed. Within-window variance is
3.00 against a within-window mean around 11, i.e. **under**-dispersed relative to a simple
count process, consistent with vessels persisting rather than arriving independently.

The pooled dispersion index of 4.36 looks over-dispersed, but §3.1 shows that is the trend,
not the counts. Reported as a description only; no distribution was fitted and no
probability was computed.

So the limitation is **not** count noise. It is non-stationarity.

## 6. Measurement risk register update

| Risk | Prior status | Now |
|---|---|---|
| `secular_trend` | *untested — requires the long series* | **CONFIRMED, severe.** 6.26× over 8 quarters; 94% of baseline variance. The decisive finding. |
| `aggregation_masking` | active — counts of 3–4 feared too small | **Retired.** Was an artifact of the clipped bounding box; true median is 9. |
| `definition_change` (geometry) | detected and bounded | unchanged — all 56 days lie inside the stable era |
| `proxy_mismatch` | active, dominant | unchanged — occupancy is still not queue length |
| `administrative_rationing` | active | unchanged, untested |
| **AIS coverage growth** | not previously registered | **NEW.** In-region deep-draft vessel counts rose 2.10× over the same period. A measurement-side trend that any future study of this dataset must handle. |

## 7. Consequences for Event #3

Hampton Roads cannot supply Event #3 under the currently frozen detection rule. Options, in
the order a future task should consider them, none of them started here:

1. Declare a trend-aware detection rule as a new pre-registration, then re-run against the
   same frozen measurement. The 56-day baseline is already acquired and is reusable.
2. Restrict the study period to a span short enough that drift is small relative to the
   signal, and re-derive the baseline within it. Note this shrinks the available history.
3. Return to region selection with stationarity added as an explicit criterion — the
   containment metric used to pick Hampton Roads never tested it.

H1 lifecycle remains `experimental_no_effect`. The known model defect remains `known`.
