# ANTAQ acquisition — blocked by publisher policy, not by technology

> **Outcome: no ANTAQ data was obtained. No schema audit, queue reconstruction, event
> detection, qualification or replay was performed.** Everything downstream of acquisition
> in this task is gated on files that do not exist locally.
>
> This is a §39 stop condition (*"No real ANTAQ data"*), reached honestly.

## 1. Local search result

Searched the repository, `data/external/`, the working tree and the session scratchpad for
`ANTAQ`, `atracacao`, `atracações`, `port calls`, `berthing`, `Brazil port`.

**No ANTAQ artifact exists locally.** The only matches were this project's own prior
documents referring to ANTAQ as a candidate. `data/external/` contains only
`uci_daily_demand.csv` and `user_ops_sample.csv` from earlier fitting work.

## 2. Why automated acquisition stopped

The previous round recorded ANTAQ as "HTTP 403 from this environment" and inferred an
environment restriction. **That inference was wrong, and the correction matters.**

`robots.txt` on every ANTAQ data host contains:

```
User-agent: ClaudeBot
Disallow: /
```

Verified on all three:

| Host | Role | ClaudeBot |
|---|---|---|
| `estatistica.antaq.gov.br` | Estatístico Aquaviário bulk download | `Disallow: /` |
| `sdpv2.antaq.gov.br` | SDP data platform | `Disallow: /` |
| `aquarela.antaq.gov.br` | Qlik statistical dashboard | `Disallow: /` |

All three additionally carry Cloudflare content signals `ai-train=no, use=reference`.

So the 403 was **policy being enforced, not a misconfiguration**. ANTAQ has deliberately
excluded AI crawlers from its data platforms.

### What was therefore not done

- No `User-Agent` was spoofed to evade a directive that names this crawler.
- The in-app browser was not used to fetch content from a host that disallows AI agents;
  driving a browser does not change who is asking.
- No mirror was used to obtain content the publisher declined to serve to this agent.

**Nothing here restricts a human.** `robots.txt` governs automated crawlers. The data is
public, free, and openly licensed; a person opening these pages in their own browser is
doing exactly what the publisher intends. The block applies to me, not to you.

## 3. Human acquisition instructions

Precise enough to complete without a further research round.

### Step 1 — open the download page

<https://estatistica.antaq.gov.br/ea/sense/download.html>

Reached from the official index at
<https://www.gov.br/antaq/pt-br/assuntos/estatistica> → *Estatístico Aquaviário*.

### Step 2 — download the berthing (*Atracação*) extracts

Dataset: **Estatístico Aquaviário — Atracação** (one archive per year).

| Setting | Value |
|---|---|
| Years needed | **2017 – 2024** (eight years; see §4 for why) |
| Format | ZIP per year, containing delimited text (`.txt`, semicolon-separated) |
| Expected archive name | `<YEAR>Atracacao.zip` — **unverified**, see the caveat below |
| Companion tables | If offered alongside: `Carga` (cargo) and any port/terminal lookup. Take them; they are needed to distinguish cargo lines from vessel calls. |

> **Caveat on filenames.** The `<YEAR>Atracacao.zip` pattern comes from links seen in search
> results before the block was identified; the endpoints themselves were never reachable, so
> the naming is **an expectation, not a verified fact**. Download whatever the page actually
> offers for those years and place it as-is — the audit harness discovers filenames rather
> than assuming them.

### Step 3 — place the files unmodified

```
data/external/antaq/raw/          <- put the downloaded ZIPs here, unchanged
data/external/antaq/derived/      <- created by the pipeline; never edited by hand
data/external/antaq/metadata/     <- checksums and retrieval notes
```

Do not unzip, rename, re-encode or convert to CSV. The raw layer is immutable; the ingest
step reads archives directly and writes only into `derived/`.

### Step 4 — record provenance

```bash
python -m event_sim.ingest.antaq register --retrieved-by "<your name>" --retrieved-at 2026-08-10
```

Writes `metadata/manifest.json` with per-file SHA-256, size, byte count and retrieval date.

### Step 5 — audit the real schema

```bash
python -m event_sim.ingest.antaq audit
```

Profiles every column — observed examples, inferred type, missingness, cardinality — and
writes `docs/replays/ANTAQ_DATA_AUDIT.md`. **It reports; it does not assume.** In particular
it will not label any column pair as queue entry/exit. That interpretation requires the
official *dicionário de dados*, which must be downloaded from the same page and read.

### Step 6 — only then, detection

Thresholds are already pre-registered in
[ANTAQ_EVENT_DETECTION_PROTOCOL.md](ANTAQ_EVENT_DETECTION_PROTOCOL.md), written **before**
any data existed, so detection cannot be tuned to produce a convenient window.

## 4. Why 2017–2024, and not the whole archive

| Requirement | Consequence |
|---|---|
| Pre-event baseline for anomaly detection | ≥ 2 clean years before any candidate window |
| Avoid confounding everything with one regime | must span both pre-COVID and post-COVID normality; 2020–22 alone would make every port anomalous simultaneously |
| Independence from prior evidence | must not rely on 2021 congestion, which shaped H1 |
| Recovery phase visible | window must extend well past any candidate disruption |
| Detection needs several candidates | one or two years would likely yield none |

2017–2024 gives roughly three pre-pandemic years, the pandemic period as an explicitly
flagged regime, and two-plus years of post-pandemic normality. Earlier years can be added
later if detection finds too few candidates; downloading the full archive first would be
premature.

## 5. What this does *not* establish

- It does **not** establish that ANTAQ can measure waiting time. That depends on whether an
  arrival timestamp genuinely marks entry into the port's queue system, which is a
  documentation question no one has yet answered.
- It does **not** establish that a qualifying Event #3 exists in the data.
- It does **not** advance H1. Lifecycle remains `experimental_no_effect`; the known defect
  remains `known`.

## 6. If ANTAQ turns out not to work

Reasons the audit could still reject it, all recorded in advance:

```
timestamps do not mean queue entry/exit
reporting regime unstable across years
no candidate window has a recovery phase
no independently identifiable driver
only arrival-side events present
capacity magnitude unobservable
candidate windows confounded
```

Any of these is a valid outcome. The fallback is
[EVENT3_DATA_DECISION.md](EVENT3_DATA_DECISION.md), whose Priority-1 alternative — Port of
Vancouver daily days-at-anchor — remains unverified for historical archive availability and
should be checked by the same human in the same sitting.


---

## Update (second acquisition attempt) — see ANTAQ_ACQUISITION_BLOCKER.md

A full self-acquisition attempt was made and exhausted every legitimate official route:
the federal catalog's designated endpoint (`web3.antaq.gov.br`) is **NXDOMAIN — the host no
longer exists**, confirmed by dados.gov.br's own link monitor; the live successor
(`estatistica.antaq.gov.br`) excludes this agent by name in robots.txt; the federal API is
key-gated. Full evidence: [ANTAQ_ACQUISITION_BLOCKER.md](ANTAQ_ACQUISITION_BLOCKER.md).

Two corrections to the instructions above, from the official catalog entry:

1. The catalogued artifact is one consolidated **`estatistico.zip`** (2010→current, monthly),
   not necessarily per-year `<YEAR>Atracacao.zip` files — download whichever the live page
   actually offers.
2. The data dictionary is a concrete named artifact: **`MetadadosMovimentacao.zip`**. It is
   required, not optional — semantics binding cannot start without it.
3. Licence is confirmed **ODbL**, so downloaded raw files may be committed with attribution.
