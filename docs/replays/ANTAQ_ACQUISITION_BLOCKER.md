# ANTAQ acquisition blocker — evidence that no permitted automated route exists

> Produced under §22 of the acquisition task, after exhausting every legitimate official
> route available to this agent. **No ANTAQ data was obtained.** This document exists to
> prove the negative properly, not to excuse a shallow search.
>
> Evidence gathered 2026-08-09/10. Every claim below was verified in-session, not recalled.

## 1. Summary

The dataset is real, open (ODbL), and officially catalogued. It cannot be acquired by this
agent because the two distribution hosts fail in two *different* ways:

- the **officially designated download host no longer exists in DNS**, and
- the **live successor host explicitly disallows this agent by name** in robots.txt.

Neither failure is technical timidity: the first is confirmed by the Brazilian federal
portal's own uptime monitor, the second is an access policy I will not evade.

## 2. What the official catalog says

Source: the federal open-data portal entry
[`dados.gov.br/dados/conjuntos-dados/estatistico-aquaviario-ea`](https://dados.gov.br/dados/conjuntos-dados/estatistico-aquaviario-ea)
(rendered in-browser; its public metadata API response read directly from the page's own
network traffic — not by calling the keyed API).

| Fact | Value |
|---|---|
| Dataset | *Estatístico Aquaviário (EA)* — port-call and cargo movement microdata |
| Coverage | **2010 → current year, updated monthly** |
| Licence | **Open Data Commons Open Database License (ODbL)** — stated explicitly |
| Format | TXT inside ZIP |
| Data resource | `https://web3.antaq.gov.br/ea/txt/estatistico.zip` (consolidated, 2,128 downloads) |
| Dictionary resource | `https://web3.antaq.gov.br/ea/txt/MetadadosMovimentacao.zip` — typed `DICIONARIO_DE_DADOS` (758 downloads) |
| Portal's own link check | **`"urlCheckFormatado": "Erro na conexão"`, `"urlDisponivel": false` — for both resources** |
| Portal status flag | *Desatualizado* (outdated) |
| Responsible unit | Gerência de Estatística e Avaliação de Desempenho, `gea@antaq.gov.br` |

Two corrections to this project's earlier assumptions, worth recording:

1. The catalogued artifact is **one consolidated `estatistico.zip`**, not per-year
   `<YEAR>Atracacao.zip` files (the live portal page may still offer per-year extracts;
   unverifiable from here).
2. The data dictionary has a concrete name — **`MetadadosMovimentacao.zip`** — which is
   exactly the artifact the semantics-binding stage requires.

## 3. Every route attempted, and why each failed

| # | Route | Class | Result | Evidence |
|---|---|---|---|---|
| 1 | Local files (`data/external/antaq/raw/`, Downloads, Desktop, Documents, drive roots, recent archives) | local | **absent** | directory listings; only `.gitkeep` |
| 2 | `web3.antaq.gov.br/ea/txt/estatistico.zip` — the URL the federal catalog publishes | direct official download | **NXDOMAIN** — `nslookup: Non-existent domain`; curl `code=000` in ~30 ms (no TCP), 2 attempts | this session |
| 3 | `web3.antaq.gov.br/ea/txt/MetadadosMovimentacao.zip` | direct official download | same NXDOMAIN | this session |
| 4 | Federal portal's own monitor for routes 2–3 | corroboration | `Erro na conexão`, `urlDisponivel: false` | catalog API payload |
| 5 | `estatistica.antaq.gov.br` (live successor portal) | official portal | **policy block**: robots.txt contains `User-agent: ClaudeBot / Disallow: /` plus Cloudflare content signals `ai-train=no` | fetched robots.txt |
| 6 | `sdpv2.antaq.gov.br` | official SDP platform | same explicit `ClaudeBot Disallow: /` | fetched robots.txt |
| 7 | `aquarela.antaq.gov.br` | official dashboard | same explicit `ClaudeBot Disallow: /` | fetched robots.txt |
| 8 | `dados.gov.br` catalog page + its public page-level API | federal open-data | **accessible — but hosts metadata only**; both byte-level resources point at the dead host (route 2) | this session |
| 9 | `dados.gov.br` programmatic API | federal API | **401** — requires a registered API key; account creation is something I am prohibited from doing | probed twice |
| 10 | `dados.antaq.gov.br`, `api.antaq.gov.br` | hypothetical official endpoints | do not resolve | probed |
| 11 | Base dos Dados (BigQuery mirror) | third-party | **excluded by task rule** (not an official channel) and requires an authenticated cloud project regardless | — |

### What was deliberately not done

- No User-Agent spoofing against hosts 5–7; no browser-driving at them. The publisher
  named this agent and excluded it; changing the tool does not change who is asking.
- No third-party re-uploads or mirrors.
- No account registration to obtain the dados.gov.br API key.

## 4. Is there an official API? Another official distribution?

Checked. The federal portal **is** the alternative official distribution, and it delegates
the bytes to the dead host. Its programmatic API is key-gated (route 9); its page-level
metadata is open but contains no data bytes. No `dados.antaq.gov.br` or `api.antaq.gov.br`
exists. The live estatistica portal presumably serves the same `/ea/txt/` artifacts, but it
is the host that excludes this agent by name — so that presumption stays unverified.

## 5. The irony, stated for the record

The federal catalog's *designated* public endpoint (web3) excludes no one — it is simply
dead. The *working* portal (estatistica) excludes AI agents. So the only permitted door is
off its hinges, and the only working door is marked "not you." A human familiar with the
dataset would go straight through the second door in a browser, exactly as ANTAQ intends.

## 6. Consequence and the one remaining path

Self-acquisition is exhausted. Per the task's central rule, documenting this accurately is
the correct outcome — not pretending, and not evading.

**Human download (15 minutes), updated with what this round established:**

1. Open `https://estatistica.antaq.gov.br/ea/sense/download.html` in a normal browser.
2. Download whatever *Atracação* data artifacts it offers — either the consolidated
   `estatistico.zip` or per-year extracts if listed. Coverage needed: **2017–2024** at
   minimum (the consolidated file covers 2010→current, which is fine).
3. **Also download `MetadadosMovimentacao.zip`** (or however the page labels the
   *metadados/dicionário de dados*). Without it, semantics binding cannot proceed and the
   whole dataset stays scientifically unusable.
4. Place all files unmodified in `data/external/antaq/raw/`.
5. Run `python -m event_sim.ingest.antaq register --retrieved-by "<name>" --retrieved-at <date>`.

Licence is confirmed ODbL, so once obtained the raw files may be committed to the
repository with attribution — a stronger position than most sources in this project.

## 7. Status unchanged

No data ⇒ no audit, no semantics binding, no eligibility verdict, no event detection. H1
remains `experimental_no_effect`; the known defect remains `known`; frozen model hashes
verify; `ANTAQ_DATA_AUDIT.md` and `ANTAQ_SEMANTICS_BINDING.md` deliberately do not exist.
