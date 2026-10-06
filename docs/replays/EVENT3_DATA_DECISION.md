# Event #3 data decision memo

> Produced under §36 of the task brief after
> [EVENT3_SEARCH_V2.md](EVENT3_SEARCH_V2.md) found no retrievable qualifying candidate.
> Its purpose is to let a human decide what to acquire — **not** to justify weakening the
> validation standard.

## 1. The one-line decision

**Do not buy anything yet.** Two datasets that appear to satisfy the contract are **free and
official**, and were blocked only by this environment. Try those first; a browser and about
an hour is the whole cost.

## 2. Priority order

### Priority 1 — free, official, blocked here (try manually first)

**ANTAQ *Estatístico Aquaviário*** — Agência Nacional de Transportes Aquaviários, Brazil.

- **What it is:** per-port-call microdata for every Brazilian port — arrival at the anchorage
  area, berthing, operation start, operation end, unberthing.
- **Why it qualifies:** waiting time is *derived from timestamps*, not a published proxy, so
  it is the variable itself at whatever frequency is needed; terminal-level locality;
  government source; open licence; documented, stable definitions.
- **Where:** `https://estatistica.antaq.gov.br/ea/sense/download.html`, annual berthing
  ("Atracação") extracts. Mirrored at Base dos Dados
  (`basedosdados.org/dataset/0c94083a-c4e9-425a-bb85-71c0e0b8b352`), which requires a Google
  Cloud project for BigQuery access.
- **Blocked because:** HTTP 403 / connection failure from this environment. Not a licence
  problem.
- **Still needed after download:** a **capacity-side** disruption inside the coverage window.
  Grain-season congestion and the May 2018 truckers' strike are arrival-side or landside and
  would fail H8. Candidate capacity-side events (terminal fire, berth closure, equipment
  failure, dredging restriction, cyber incident) should be identified *from the data*, by
  looking for a throughput collapse with a documented physical cause.

**Port of Vancouver supply-chain metrics dashboard** — Vancouver Fraser Port Authority.

- **What it is:** daily container vessels at berth and at anchor, days at anchor, anchorage
  utilisation.
- **Why it qualifies:** daily, terminal-local, port authority, and *days at anchor* is
  directly an H1-sensitive metric.
- **Where:** `portvancouver.com/port-operations/supply-chain/metrics-dashboard`.
- **Blocked because:** HTTP 403 from this environment.
- **Unverified:** whether historical series are downloadable or only a live snapshot. **Check
  this first** — if it is snapshot-only, it cannot support a retrospective replay at all.

### Priority 2 — free, official, wrong resolution

**Indian Ports Association / Sagar Unnati** — monthly pre-berthing detention and turnaround
time per major port, long history, government source. Fails the frequency requirement for a
multi-week disruption. **Would qualify for a disruption lasting several months**, which is a
real possibility worth keeping in view.

### Priority 3 — commercial, only if Priorities 1–2 fail

| Provider | Product | Fit | Notes |
|---|---|---|---|
| S&P Global | Port Performance | Strong — waiting and unloading times, ~1,000 terminals, from Jan 2017 | Long history is the key advantage: several candidate events in one purchase |
| MarineTraffic | Port congestion / waiting times | Good — up to 1 year of weekly history | 1-year window may not reach a suitable past event |
| Portcast | Port congestion | Moderate — ~6 months history | Too short for retrospective validation |
| CEIC | Port congestion by port and vessel type | Moderate — weekly from 2022 | Aggregated by vessel type |
| Clarksons / Spire / project44 | AIS and port-call feeds | Strong but heavyweight | Likely overkill for one validation |

**If purchasing, buy history, not live data.** The project needs *past* disruptions with
retrospective coverage; a real-time feed is worth nothing for held-out validation.

## 3. Required fields

| Field | Requirement | Why |
|---|---|---|
| `metric` | one of `vessel_queue`, `waiting_vessels`, `average_waiting_time`, `anchorage_wait`, `port_dwell_time` | the H1-sensitive endpoint |
| resolution | **daily or weekly** | monthly cannot resolve a multi-week peak |
| geography | **terminal or port**, not national | Yantian showed an aggregate moves for other reasons |
| coverage | ≥ 4 observations pre-event, through peak, ≥ 2 after peak | needed for baseline, peak timing and clearance timing |
| `observation_type` | **observed**, not scheduled or allocated | Panama showed a schedule is not an outcome |
| `definition_version` | stable across the window, or explicitly versioned | San Pedro's definition changed mid-series |
| driver series | throughput / berth availability, same port, same period | to inject the event without guessing |
| licence | redistributable, or quotable | so the replay is reproducible from the repository |

Encoded and checkable as `event_sim/historical/dataset_contract.py`
(`DatasetRecord`, `DatasetRequirement`, `validate_dataset`).

## 4. Minimum event count

**One** qualifying event unlocks the immediate question: does frozen H1 generalise out of
sample? That is the decision currently blocked.

**Three or more** would unlock the larger one: is the early-timing defect a general property
of the model rather than of two particular events. With n=1 held out, the honest claim ceiling
is *"H1 generalised to one independent disruption"* — never *"H1 is validated"*.

## 5. Why public data has not been enough

Four searches, one consistent shape:

| Variable class | Public availability |
|---|---|
| Capacity / throughput | often available, sometimes officially and precisely |
| **Queue / waiting time** | **exists, but commercial or environment-blocked** |
| Downstream (inventory, service level) | never |

Round 1 concluded the queue layer was largely unavailable. **Round 2 revises that: it exists
and is sometimes free.** The obstacle is access, not existence — a materially more optimistic
finding, and a cheaper one to fix.

## 6. What the purchase (or download) unlocks

Precisely one scientific question:

> Does the frozen H1 queue-stock mechanism reduce peak-timing and clearance-timing error on
> an independent disruption that played no part in its formulation, support, implementation
> or prior evaluation?

Consequences of each answer:

- **Yes** → H1 becomes `heldout_supported`; the known defect may move `known → mitigated`;
  H1 becomes *eligible for default-model promotion review* — a separate human decision, not
  an automatic promotion.
- **No / worse** → H1 is recorded as failing out of sample despite good in-sample and
  mechanism evidence. That is a genuinely valuable result: it would show mechanism support
  plus in-sample improvement is **not** sufficient, which is a lesson about the method, not
  just about H1.

Either way the ambiguity that currently blocks the roadmap is resolved.

## 7. What must not happen instead

- Do not substitute another milestone-only event.
- Do not accept a national or global aggregate.
- Do not interpolate monthly data to weekly.
- Do not run H1 on candidates and keep the flattering one.
- Do not relax the contract because acquisition is inconvenient.

The current state — *no qualifying public dataset retrieved, standard intact* — is a valid
scientific outcome. A weakened standard that happens to admit available data is not.
