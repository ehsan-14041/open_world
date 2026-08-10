# ANTAQ blind event-detection protocol — pre-registered

> **Written before any ANTAQ file existed**, and therefore before any distribution, any port
> ranking, or any candidate window could be seen. Thresholds are stated in **scale-free**
> terms precisely so they can be fixed in advance of data whose magnitudes are unknown.
>
> Detection has **not** been run. Acquisition is blocked by publisher policy — see
> [ANTAQ_ACQUISITION.md](ANTAQ_ACQUISITION.md).

## 1. Purpose

Candidate disruption windows must **emerge from the data before any historical label is
attached**, so that a window cannot be drawn around an event we already wanted to find. This
document fixes the rules; running them is a later, separate step.

## 2. Hard prohibitions during detection

- **H1 output is not consulted.** Detection imports nothing from `event_sim.engine`, and
  runs before any replay.
- **Known event dates are not used** to define, centre, extend or trim a window.
- **No port is pre-selected.** Ports enter or leave on the quality filter in §4 only.
- Thresholds below are **not** revised after seeing results. If detection yields nothing,
  that is the finding.

## 3. Series to construct per port

Daily first; weekly only if the simulator's resolution demands it, and by a declared
aggregation (§7).

```
arrivals            count of calls whose arrival timestamp falls in the period
berthings           count of calls whose berthing timestamp falls in the period
departures          count of calls whose unberthing timestamp falls in the period
waiting_vessels     count of calls with arrival <= t < berthing      (a stock)
mean_wait           mean  (berthing - arrival) over calls berthing in the period
median_wait         median of the same
p90_wait            90th percentile of the same
```

These are **different observables and are never conflated**. A rise in `mean_wait` is not a
rise in `waiting_vessels`; either can move without the other.

> All seven are conditional on the §5 semantic gate. If ANTAQ's data dictionary does not
> establish that the arrival timestamp marks entry into the port's queue system, none of
> `waiting_vessels`, `mean_wait`, `median_wait` or `p90_wait` may be constructed at all.

## 4. Port quality filter — applied before detection

A port is excluded, with the reason recorded, if any holds:

| Criterion | Threshold |
|---|---|
| Too few calls | median < **20 calls per month** across the window |
| Missing timestamps | > **10%** of calls missing arrival or berthing |
| Unstable reporting | any calendar month with **zero** calls where neighbours exceed the median |
| Insufficient baseline | < **24 months** of usable history before the first candidate |
| Unexplained gap | any gap > **14 consecutive days** with zero calls |

## 5. Detection rules — thresholds fixed here

All are scale-free, computed against each port's own **trailing 52-week baseline**, with a
robust centre and spread (median and MAD, so an anomaly does not inflate its own baseline).

A **candidate window** opens when either rule fires and closes per §6.

**Rule A — congestion spike**

```
robust_z(series, t) = ( x(t) − median_52w ) / ( 1.4826 × MAD_52w )

fires when robust_z >= 3.0 for >= 2 consecutive periods
on waiting_vessels  OR  p90_wait
```

**Rule B — throughput collapse**

```
fires when berthings(t) <= 0.6 × median_52w  for >= 2 consecutive periods
```

Two consecutive periods in both rules, so a single reporting glitch cannot open a window.

**Accumulation-and-recovery requirement.** A window is retained only if it shows the full
arc: a rise, a maximum strictly inside the window, and a return to within **1.5 robust-z**
of baseline before the window closes. A window that never recovers inside the data is
recorded as *truncated* and is **not** eligible as Event #3 — clearance timing cannot be
measured from it.

## 6. Window boundaries

```
start   first period where the rule fires
peak    period of maximum robust_z on the triggering series
end     first period after the peak with robust_z < 1.5 sustained for 2 periods
```

Baseline context extends 8 periods before `start`; recovery context 8 periods after `end`.

## 7. Aggregation, if weekly is required

Declared now so it cannot be chosen later to favour a result:

| Series | Daily → weekly rule | Information lost |
|---|---|---|
| `arrivals`, `berthings`, `departures` | **sum** | within-week distribution |
| `waiting_vessels` | **mean of daily stock** | within-week peak; a stock cannot be summed |
| `mean_wait`, `median_wait` | **call-weighted mean** over calls berthing that week | within-week spread |
| `p90_wait` | **recomputed from the week's calls**, never averaged from daily p90s | — |

## 8. Measurement-regime discontinuities

Before any window is accepted, check for a pipeline artefact masquerading as a disruption:

- new or retired port/terminal codes at the window boundary
- a change in column set or file layout between annual extracts
- a step change in missingness
- a change in the share of calls carrying each timestamp
- a port appearing or disappearing entirely

Any of these makes the window **rejected as a measurement-regime change**, not a disruption,
and is filed against `definition_change` in the measurement-risk registry.

## 9. Ranking — data quality only

Applied only to windows surviving §5–§8, to order them. **No dimension refers to any model
output, and H1 is not run until selection is frozen.**

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| signal strength | peak z 3–4 | 4–6 | > 6 |
| duration | < 2 periods | 2–4 | > 4 |
| baseline quality | < 24 months | 24–48 | > 48 months |
| recovery visibility | truncated | recovery reached | recovery plus 8 clean periods |
| locality | port group only | port | terminal resolvable |
| measurement completeness | > 10% missing | 5–10% | < 5% |
| driver observability | none | qualitative | quantified restriction |
| definition stability | change inside window | change nearby | stable |

Ties break by signal strength, then baseline quality, then recovery visibility.

## 10. Only afterwards: historical identification

Once, and only once, candidate windows exist **as dates produced by the data**, research what
happened. The ordering is recorded in the output so it can be checked later.

Each candidate is then classified:

```
capacity_side   an exogenous reduction in ability to serve  (closure, outage, obstruction)
arrival_side    an exogenous increase in demand             (surge, diversion, seasonality)
mixed           both, not separately identifiable
unknown         no external explanation found
```

**A throughput drop alone does not establish capacity loss.** Throughput is endogenous — it
falls when arrivals fall. Capacity-side classification requires external evidence of a
restriction, and the magnitude must come from that evidence, not from the observed
throughput decline. Where magnitude is uncertain, a range is carried.

## 11. Consequences by class

| Class | Outcome |
|---|---|
| `capacity_side` | proceed to the frozen eligibility contract |
| `arrival_side` | **stop before replay.** The frozen event interface injects capacity only; encoding an arrival surge as capacity loss is fabrication. Record in `ARRIVAL_PRESSURE_DRIVER_REQUIREMENT.md`. |
| `mixed` | unsuitable for clean held-out validation; keep as a future stress-test candidate |
| `unknown` | not eligible — an unexplained window cannot be injected honestly |

## 12. What running this protocol cannot do

It cannot make ANTAQ qualify. It can only report which windows exist and which class they
fall into. If every window is arrival-side, or none recovers inside the data, or the
semantic gate never opens, then ANTAQ does not contain a usable Event #3 — a valid result,
recorded rather than worked around.
