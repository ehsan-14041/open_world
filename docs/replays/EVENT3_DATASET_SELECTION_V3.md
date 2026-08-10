# Event #3 dataset selection (V3) — choosing a source, before choosing an event

> **Written before any event discovery.** No candidate event was identified, no window was
> chosen, and H1 was not run, while this document was being produced. The selection criteria
> below are all measurement-quality criteria; none of them refers to how well H1 might
> perform on the resulting data.
>
> This supersedes the ANTAQ line of work, which ended at
> [ANTAQ_ACQUISITION_BLOCKER.md](ANTAQ_ACQUISITION_BLOCKER.md) — dataset real, openly
> licensed, and unobtainable by this agent.

## 1. Why the previous attempt failed, and what that changed

ANTAQ was chosen on *paper* qualities: microdata, long history, explicit berthing
timestamps, open licence. It failed on the one quality nobody had checked — whether the
bytes could actually be fetched. The designated federal endpoint was NXDOMAIN and the live
successor excludes this agent by name.

So this round inverts the order. **Accessibility is tested first, with real bytes, and a
candidate that cannot be downloaded is not a candidate** regardless of how good its
documentation looks.

## 2. Candidates and the accessibility test

### Candidate A — United States National AIS (NOAA / BOEM / USCG Marine Cadastre)

| Check | Result |
|---|---|
| `robots.txt` policy | `coast.noaa.gov/robots.txt` is `User-agent: *` with specific Disallows (`/downloads/`, `/internal/`, `*.tif`, `*.img`, `*.gdb`, `*.laz`). **`/htdata/` is not disallowed.** No ClaudeBot exclusion on any host. |
| Endpoint | `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2022/AIS_2022_01_01.zip` |
| HTTP | **200**, `Content-Type: application/zip`, `Content-Length: 283943322` |
| Bytes actually retrieved | **283,943,322 bytes**, SHA-256 `bbc1aa2550245264b98e0de59eddebf705250899151f6ef5c3457f1c595f3c9c` |
| Contents parsed | 7,239,758 rows, single member `AIS_2022_01_01.csv` |
| Registration / key / payment | none |
| Licence | US Government work, public domain |

Real header, read from the file rather than from documentation:

```
MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,
VesselType,Status,Length,Width,Draft,Cargo,TransceiverClass
```

**Accessible: proven.** Three separate days were downloaded end-to-end during this round.

### Candidate B — Ulsan Port Authority via `data.go.kr`

| Check | Result |
|---|---|
| `robots.txt` | `User-agent: *`, allow-all — no policy obstacle |
| Portal reachable | yes, `fileData.do` returns 200 |
| Vessel-operation datasets | distribution is **OpenAPI** (`openapi.do`); the probed dataset returned **404** and the documented access path requires a service key |
| Service key | obtained by registering an account — **an action I am not permitted to take** |
| File-based alternatives | the vessel datasets available as direct file download are **monthly** aggregates (월별 선박 입항 현황) or accident records, not daily operational states |
| Page gating markers | 로그인 ×22, 활용신청 ×9, 인증키 ×5 |

**Not accessible to this agent, and the openly downloadable subset is monthly.** Either
fact alone disqualifies it; together they are decisive. This is a *policy and resolution*
failure, not a technical one — a registered human could obtain a key in minutes.

### Candidate C — BTS Port Performance Freight Statistics (found while checking A)

Worth recording because it looked ideal and is not. `data.bts.gov` is a fully open Socrata
portal, no key, and it publishes **vessel dwell times** — apparently the exact quantity this
project has been unable to find anywhere. The schema settles it:

```
month, year, hours, quarter, q_year, month_year
```

Monthly, and pooled across the **top 25 U.S. ports** with no per-port breakdown. It fails
temporal resolution and it fails local specificity in precisely the way the Yantian replay
already failed (`geographic_mismatch`). Rejected — but it remains the right external
reference for methodology validation, since BTS derives these numbers from the same AIS.

## 3. Scoring on the ten criteria

Criteria are the ones set in the task, in its order. Scores are `+` adequate, `~` marginal,
`-` inadequate.

| # | Criterion | A: National AIS | B: Ulsan | C: BTS PPFSP |
|---|---|---|---|---|
| 1 | Measurement directness | `~` positions only; states must be reconstructed | `+` explicit entry/berth states *if* reachable | `+` dwell hours, directly |
| 2 | Historical depth | `+` 2015 → present, daily | `~` unverified | `+` 2019 → present |
| 3 | Temporal resolution | `+` sub-minute | `-` monthly for the open subset | `-` monthly |
| 4 | Local specificity | `+` per-vessel coordinates; any port | `+` single port | `-` top-25 pooled |
| 5 | Event-driver observability | `~` capacity/closure not in AIS; needs an independent driver source | `~` unknown | `-` no driver |
| 6 | Recovery observability | `+` same series continues indefinitely | `~` unknown | `+` continues |
| 7 | Documentation quality | `+` published schema + BTS methodology | `~` Korean-language, partly gated | `+` documented |
| 8 | Reproducibility | `+` stable URLs, checksummable | `-` key-gated | `+` stable |
| 9 | Licensing | `+` public domain | `~` KOGL, needs registration | `+` public domain |
| 10 | **Actual accessibility** | `+` **proven with 284 MB** | `-` **blocked** | `+` proven |

**Selected: Candidate A, United States National AIS.**

It is the only candidate that is both accessible and locally resolved. Candidate B would
have been preferred on criterion 1 had it been reachable — the task's own §5 says to prefer
direct operational observations over reconstruction — but an unreachable dataset scores
nothing on criterion 10, and that criterion is the whole lesson of the ANTAQ round.

## 4. What selecting AIS costs

This is not a free win, and the cost lands squarely on criterion 1.

ANTAQ was attractive because it contained *events*: a berthing timestamp is a record that
something happened. AIS contains no events at all — only where vessels were and how fast
they were moving. Every operational state must be **reconstructed**, and reconstruction is
inference, not observation.

The consequence is stated plainly and enforced in code: the resulting series is
`anchorage_occupancy`, **not** `vessel_queue`. AIS cannot distinguish a ship waiting for a
berth from one anchored for weather, crew, documents, or repair, because intent is not
transmitted. The measurement model and its limits are in
[EVENT3_MEASUREMENT_MODEL_AIS.md](EVENT3_MEASUREMENT_MODEL_AIS.md).

## 5. Status

Dataset selected. **Event #3 has not been selected.** No anomaly detection has been run, no
window has been proposed, and H1 has not been executed. The frozen model hashes, the
eligibility contract and the H1 lifecycle state (`experimental_no_effect`) are unchanged by
this document.
