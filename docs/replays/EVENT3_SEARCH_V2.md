# Event #3 search, round 2 — audited against a pre-declared contract

> Search performed **after** [H1_HELDOUT_FREEZE.md](H1_HELDOUT_FREEZE.md) and
> [EVENT3_ELIGIBILITY_CONTRACT.md](EVENT3_ELIGIBILITY_CONTRACT.md) were written, so the
> criteria could not be shaped by what the search turned up.
>
> **H1 was not run on any candidate.** Every verdict below is a data verdict.

## Outcome

**No qualifying candidate. Outcome B under §36 of the task brief.**

The binding constraint has moved. It is no longer *"local dense queue data does not exist"* —
it does exist, and this round located it. The constraint is now **retrievability**: the
qualifying datasets are either commercial, or legally open but unreachable from this
environment.

That distinction matters, and it is the main product of this search:

| Class | Meaning | Examples found |
|---|---|---|
| **A — qualifies, blocked here** | free, official, contract-satisfying, but not retrievable from this sandbox | ANTAQ (Brazil), Port of Vancouver |
| **B — qualifies, commercial** | dense and local, behind a paywall | Portcast, MarineTraffic, CEIC, S&P Global |
| **C — does not qualify** | retrievable but fails a hard requirement | everything else below |

A human with a browser can obtain a Class A dataset in minutes. See
[EVENT3_DATA_DECISION.md](EVENT3_DATA_DECISION.md).

## Candidates audited

| Event / dataset | Location | Mechanism | Local queue or delay series? | Capacity series? | Frequency | Source quality | Definition stability | Verdict |
|---|---|---|---|---|---|---|---|---|
| **ANTAQ *Estatístico Aquaviário*** | all Brazilian ports | n/a (dataset, not an event) | **Yes** — derivable per call from arrival→berthing timestamps | Yes (berthings, cargo) | **per call ⇒ any** | Government agency | Stable, documented | **Class A — qualifies on contract, HTTP 403 from this environment** |
| **Port of Vancouver metrics dashboard** | Vancouver, BC | n/a (dataset) | **Yes** — days at anchor, vessels at anchor, updated daily | Partial | Daily | Port authority | Unknown (not inspectable) | **Class A — HTTP 403; historical archive availability unverified** |
| Port of Durban anchorage waiting time (JTSCM 2026, CC BY) | Durban | congestion | **No** — qualitative study; illustrative figures only | No | n/a | Peer-reviewed journal | n/a | **Reject** — "raw data are not publicly available due to restriction of confidentiality"; also dry/break-bulk, not container |
| Durban floods, Apr 2022 | Durban | flood, landside access | No series located — press point estimates only ("queues of up to two weeks", "63 ships at anchorage") | No | irregular | Trade press | n/a | **Reject** — fails H1/H2, milestone-and-anecdote shaped, exactly the Baltimore failure |
| Ports of Auckland congestion, 2021 | Auckland | congestion | Only via commercial trackers; POAL quoted point figures ("up to five days", "9.4 days") | No | weekly (commercial) | Commercial | n/a | **Reject** — Class B, H9 |
| Indian major ports (IPA / Sagar Unnati) | India | n/a (dataset) | **Yes** — pre-berthing detention time, turnaround time, per port | Yes | **Monthly** | Government | Stable | **Reject for now** — monthly cannot resolve a multi-week event (H3); would qualify only for a multi-month disruption |
| Portcast / MarineTraffic / CEIC / GoComet | global | n/a | Yes — weekly wait times, 6–12 month history | Yes | Weekly | Commercial | Unknown | **Reject** — H9, commercial |
| S&P Global Port Performance | 500 ports | n/a | Yes — waiting and unloading times, from Jan 2017 | Yes | per call | Commercial | Documented | **Reject** — H9, commercial |
| Panama Canal drought, 2023–24 | Panama Canal | administrative capacity restriction | Wait times: 3 dated points only | Booking slots ≠ throughput | irregular | Government | Plan revised mid-event | **Reject** — carried over from round 1: fails H6 (scheduled ≠ physical) and H1; queue administratively rationed, so H1 is unfalsifiable there |
| Ningbo-Zhoushan Meishan, Aug 2021 | Ningbo | COVID terminal closure | Point estimates only (41 ships at anchor) | Partial | irregular | Trade press | n/a | **Reject** — fails H2; also same 2021 congestion regime as Yantian, so weak independence |
| Suez Canal blockage, Mar 2021 | Suez | channel obstruction | No local series | n/a | n/a | n/a | n/a | **Reject** — carried over; 6-day event, unresolvable at weekly resolution |
| Caribbean port-calls dataset (Zenodo 10380638) | Caribbean | n/a (dataset) | Port calls + berth stops — waiting time derivable | Partial | per call | Research repository | Unknown | **Reject** — no disruption event identified in coverage; a dataset without an event cannot be a replay |

### Disqualified before audit, by H7 (not independent)

San Pedro Bay / LA–Long Beach 2021–22 · Yantian 2021 · Baltimore 2024 · US manufacturing
unfilled orders. These shaped H1's formulation, parameters or prior evaluation.

## Why the two Class A candidates were not simply used

**ANTAQ.** `web3.antaq.gov.br` and `estatistica.antaq.gov.br` return HTTP 403 or fail to
connect from this environment; `basedosdados.org` mirrors the data but serves it through
BigQuery, which needs an authenticated cloud project. The data is free and open — I could not
reach it. Recording it as "unavailable" would be wrong; recording it as "used" would be
fabrication.

**Port of Vancouver.** The dashboard returns HTTP 403. Its published description matches the
contract well (daily, per-vessel days at anchor, port authority), but I could not verify
whether *historical* series are downloadable or only a live snapshot — and an unverifiable
claim cannot be the basis of a held-out test.

## Second requirement, still unmet even with the data

A dataset alone is not an Event #3. It must also carry **a disruption whose driver the frozen
model can represent honestly** (H8). The frozen model injects a *capacity* displacement only.
For Brazil the obvious candidate disruption — the May 2018 truckers' strike — is a national,
landside, arrival-side shock. Representing it as a port capacity loss would be exactly the
fabrication H8 forbids.

So acquisition must satisfy **both**: a dense local queue/waiting series **and** a
capacity-side disruption inside its coverage window.

## What was deliberately not done

- No hard requirement was weakened when the search proved difficult.
- No milestone-only event was substituted for a trajectory event.
- No global or national aggregate was accepted in place of a local series.
- No sparse monthly data was interpolated to weekly to manufacture a trajectory.
- **H1 was not run on any candidate**, so nothing here could have been chosen for
  performance.
- No commercial access was fabricated or assumed.

## Consequences

- H1 remains `experimental_no_effect`. **No new lifecycle state is appended**, because no
  held-out evaluation took place.
- The known defect *recovery dynamics trend too fast* remains `known`.
- The frozen models are untouched; the freeze hashes still verify.
- Next step is an acquisition decision, not another search:
  [EVENT3_DATA_DECISION.md](EVENT3_DATA_DECISION.md).
