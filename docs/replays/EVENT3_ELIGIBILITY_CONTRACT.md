# Event #3 eligibility contract

> **Written before any candidate was searched for, named or inspected**, immediately after
> [H1_HELDOUT_FREEZE.md](H1_HELDOUT_FREEZE.md). Selection criteria are fixed here so a
> candidate cannot be chosen — or rejected — because of how H1 performs on it.
>
> **This contract contains no reference to model performance of any kind.** It scores data,
> not results.

## 1. Hard requirements — all must hold

A candidate qualifies only if **every** one of these is true. Failing any single one is a
rejection, not a trade-off.

| # | Requirement | Rationale |
|---|---|---|
| **H1** | At least one **local time series** for an H1-sensitive outcome: vessel queue / waiting vessels / average waiting time / anchorage wait / port or container dwell time / local transit delay. | Milestone-only events cannot test a trajectory mechanism — this is the specific failure of Baltimore. |
| **H2** | The series must show **trajectory shape**, not just a level: a pre-event baseline, onset, accumulation, a peak, and at least the start of recovery. | Peak timing and clearance timing are the metrics under test; a series without a peak cannot measure them. |
| **H3** | **Daily or weekly** frequency. Monthly accepted only if the event is long enough that monthly points still resolve accumulation and peak, and the mechanism is not erased by aggregation. | Yantian's monthly global proxy spanned a 4.5-week event with ~2 points. |
| **H4** | **Local** to the disrupted system: same port, port complex, or local maritime system. Global or national aggregates are rejected unless the event genuinely operates at that scale. | Yantian showed a global proxy can move for reasons unrelated to the event. |
| **H5** | **Stable measurement definition** across the evaluation window, or cleanly segmentable. Definition changes must be recorded and must not be spliced. | San Pedro's at-anchor definition changed mid-series when offshore drift zones were added. |
| **H6** | The metric must measure the **physical quantity**, not an administrative or scheduled proxy. Booking allocations, published schedules and quota systems are rejected as capacity measures. | Panama's official booking slots understated realised transits by roughly half. |
| **H7** | **Independence**: the event and its data must not have been used to formulate H1, test its mechanism, choose its equations, parameters, mappings, or thresholds, or in any prior evaluation. | Otherwise it is not held out. |
| **H8** | The driver must be **representable honestly** by the frozen model. If the event is primarily an arrival-side shock and the frozen model can only inject capacity, the candidate is a *mechanism-test candidate*, not a held-out replay candidate. | Fabricating a capacity loss to stand for a demand surge is fabrication. |
| **H9** | **Legally accessible** without purchase. Commercial datasets may be named but not assumed. | No fabricated access. |

### Explicitly disqualified by H7

- San Pedro Bay / Los Angeles–Long Beach, 2021–22 (used for H1 mechanism support)
- Yantian, 2021 (used in the in-sample experiment)
- Baltimore, 2024 (used in the in-sample experiment)
- US manufacturing unfilled orders (used for the H2 mechanism test)

## 2. Data-quality score — for ranking qualifying candidates only

Applied **only** to candidates that already pass every hard requirement, to choose between
them. Nine dimensions, 0–2 each, maximum 18. **No dimension refers to model output.**

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| `locality` | national/global | port complex / region | the specific terminal or port |
| `frequency` | monthly | weekly | daily or finer |
| `directness` | distant proxy | related proxy | the variable itself |
| `definition_stability` | changes mid-window | one documented change, segmentable | stable throughout |
| `source_quality` | trade press | industry provider / research institute | port authority or government |
| `baseline_coverage` | none | partial pre-event | ≥4 pre-event observations |
| `recovery_coverage` | none | peak only | peak plus drainage |
| `driver_observability` | driver unknown | driver qualitatively documented | driver quantified |
| `license_accessibility` | commercial only | public with restrictions | open/public domain |

**Minimum total to qualify: 11 of 18**, with **no zero** on `locality`, `directness`,
`definition_stability` or `license_accessibility`.

## 3. Measurement model audit — required per candidate

Every candidate must have all of these answered in writing before acceptance:

```
What exactly is measured?          Who measured it?
At what frequency?                 At what geography?
Observed or scheduled?             Is the definition stable over time?
Did methodology change mid-event?  Direct variable or proxy?
Does administrative rationing affect it?
Does the metric fall inside H1's causal scope?
```

And the quantity must be classified as exactly one of:

```
physical capacity · booking capacity · scheduled capacity · actual throughput
queue · waiting time · delay · administrative allocation
```

## 4. No event shopping

Candidates are audited **without running H1**. The first candidate that satisfies every hard
requirement and clears the score threshold is selected and frozen. If several qualify in the
same search round, the highest data-quality score wins; ties break by `locality` then
`frequency`. **H1 is never run on a candidate before selection is frozen.**

## 5. Endpoint classification, fixed before replay

Each evaluation endpoint is classified by H1's causal scope:

| Class | Meaning | Role |
|---|---|---|
| `h1_sensitive` | inside H1's causal scope — `vessel_queue` and its downstream timing | **primary gate** |
| `h1_insensitive` | outside H1's causal scope — externally imposed capacity schedules, physical reopening dates | **safety gate only** |
| `uncertain_scope` | scope genuinely unclear | exploratory; cannot determine the verdict |

H1's declared causal scope:

```
DIRECT        vessel_queue
DOWNSTREAM    shipping_delay, and timing variables downstream of it
OUTSIDE       physical reopening dates, externally imposed capacity schedules,
              administrative reopening milestones
```

The previous experiment's aggregate pooled a sensitive endpoint with a structurally
insensitive one and diluted a real signal. That is recorded as a protocol lesson; **the
previous verdict stands unchanged.**

## 6. Stopping rule

If no candidate satisfies this contract, the correct outcome is to **stop and say so**, then
produce [EVENT3_DATA_DECISION.md](EVENT3_DATA_DECISION.md) specifying what must be acquired.

**Weakening any requirement in this document because the search is hard is the one
disallowed outcome.**
