# Event Simulator — how to run it

An interactive way to explore **how an event could unfold under explicit assumptions**.
It is not a predictor, and it does not produce probabilities of future events.

For the design rationale and the repository audit that produced it, see
[EVENT_SIMULATOR_ARCHITECTURE.md](EVENT_SIMULATOR_ARCHITECTURE.md).
This surface is separate from the [Operations Decision Simulator](PRODUCT_GUIDE.md), which
is unchanged.

## Run the demo

No API key, no network, no language model is involved.

```bash
python scripts/run_port_disruption.py
```

```bash
python scripts/run_port_disruption.py --turns 24 --capacity-loss -85 --duration 8
```

Web surface (engineering mode, i.e. `product_mode: false` in `config/settings.json`):

```bash
python ui.py
```

then open <http://127.0.0.1:5081/event-sim>.

## What it does

```
"What if a major container port loses 70% of capacity for six weeks?"
        ↓
World slice        world_models/supply_chain/port_disruption.json — 8 variables, 9 edges
        ↓
Evidence layer     every edge carries a status; coverage is reported, never scored
        ↓
Causal world model deviations from baseline, one hop per turn, per-edge lag
        ↓
Simulation engine  deterministic; no RNG in the step function
        ↓
Branch + compare   two worlds from one checkpoint, differing only by the intervention
        ↓
27 swept worlds    grouped into emergent trajectories, ranked pivotal assumptions
        ↓
Causal trace       read out of recorded provenance
```

## Reading the output honestly

| Output | What it means | What it does not mean |
|---|---|---|
| "Prolonged Shortage: 21 of 27 tested worlds" | 21 assumption combinations in the designed grid ended there | Not a 78% probability. The grid is not a calibrated sample |
| "recovery_rate — HIGH" | Flipping that assumption moves the outcome further than any other | Not that slow recovery is likely |
| "Coverage: 100% assumption" | No causal edge in this module carries a source yet | Not that the model is 100% wrong, and not a confidence figure |
| "Service level 0.86 at week 12" | What this model produces under these assumptions | Not what will happen |

## API

| Route | Purpose |
|---|---|
| `GET /event-sim` | Demo page |
| `GET /api/event_sim/modules` | World-module library |
| `GET /api/event_sim/slice` | Slice: included / excluded / assumptions / missing evidence / coverage |
| `POST /api/event_sim/run` | Run the vertical slice (both worlds + comparison + sweep) |
| `POST /api/event_sim/trace` | Causal trace for one variable at one turn |
| `GET /api/event_sim/evidence` | Sources, mappings, weighted coverage, gap report, data requirements, **model health** |
| `GET /api/event_sim/historical` | Historical replay episodes |
| `GET /api/event_sim/replay/<episode_id>` | Run a replay and return its evaluation |

`POST /api/event_sim/run` body (all optional): `turns`, `capacity_loss`, `duration`,
`fork_turn`, `redirect_share`, `redirect_start`, `include_sweep`, `seed`.

## Reproducibility

`EventSimulation.fingerprint()` hashes the slice, the config, the events and the
interventions. Same fingerprint ⇒ byte-identical trajectory. The step function draws no
randomness at all, so this does not depend on RNG seeding discipline.

```python
from event_sim.scenarios.port_disruption import build_baseline
a = build_baseline(turns=12).run()
b = build_baseline(turns=12).run()
assert a["final_state"] == b["final_state"]
```

## Observability: the three regimes every node must declare

The first replay established that the binding constraint on this project is not the
simulation engine but whether the real world can be **seen**. Every variable therefore
declares an `observability_class`:

| Class | Meaning | In the port model |
|---|---|---|
| `observable` | a real series for this variable exists and is obtainable | `port_capacity` |
| `proxy_observable` | the variable is not published; a stand-in is, at a stated cost | `shipping_delay`, `freight_cost`, `order_backlog`, `consumer_price_pressure` |
| `latent` | no adequate public counterpart exists; the model carries it alone | `inventory_availability`, `production_capacity`, **`service_level`** |

This is now **part of the World Model contract**, not optional metadata: `validate_module`
refuses to load a module whose variable omits `observability_class`, or declares one without
a justification in `observability_note`. It does not touch the dynamics — it changes what a
world builder can honestly claim.

**The model's headline outcome, `service_level`, is latent.** The upstream half of the chain
is visible and the downstream half is not, which is why grounding stalls at the same place
every time.

A third evidence hunt added a corollary: *available* is not the same as *correct*. The Panama
Canal publishes exact official daily booking-slot counts — and they are the wrong quantity,
low by roughly a factor of two against realised transits. See
[the event #3 search record](replays/EVENT3_SEARCH.md).

## Historical replay

Two real disruptions have been replayed against the **same frozen model**:

```bash
python scripts/replay_port_event.py yantian_2021 --write-report
python scripts/replay_port_event.py baltimore_2024 --write-report
python scripts/replay_port_event.py --cross-event --write-report
```

This runs the whole pipeline from repository state — load episode, verify no hindsight
leakage, load sourced observations, inject the event, sweep 27 assumption worlds, evaluate
the envelope, attempt calibration, produce the evidence-gap report, and write
[docs/replays/yantian_2021.md](replays/yantian_2021.md). No notebook, no manual step, no
language model.

**Both results are negative, and that is the point.**

| Event | Test | Observed | Simulated | Error |
|---|---|---|---|---|
| Yantian 2021 | peak of `shipping_delay` | week 12 | week 3 | **−9 weeks** |
| Baltimore 2024 | full channel restored | week 11 | week 5 (median) | **−6 weeks** |
| Baltimore 2024 | normal operations *(reported)* | week 16 | week 5 (median) | **−11 weeks** |

**Every timing error has the same sign: the model is too fast.** Benchmark #2 was chosen to
differ from the first on every dimension that could produce a spurious result — different
year, continent, trigger, background regime, and crucially a different *measurement method*
(dated local milestones instead of a global monthly proxy). In Baltimore the capacity
recovery path is a model **output**, not an injected input, so the comparison is a real test.

Stated precisely, without overclaiming: Baltimore's hard observed milestone is still
*inside* the simulated envelope (about a third of tested worlds were that slow), so this is
a **consistent directional bias reproduced on an independent event — not yet a strict
falsification**. See [the cross-event diagnosis](replays/CROSS_EVENT_DIAGNOSIS.md).

The leading structural explanation is that the model is shaped
`shock → propagation → relaxation` while reality looks more like
`shock → queue accumulation → … → delayed peak → clearing`. **A reopened port is not a
cleared queue.** Four competing hypotheses are tracked in `event_sim/cross_event.py`;
**none has been implemented and no coefficient has been changed**, because with two events
the fitting window equals the evaluation window and adopting one would be the overfitting
already documented in [FITTING_FINDINGS.md](FITTING_FINDINGS.md).

## Mechanism test — H1, without any simulation

A third event with the required local time series could not be sourced
([search record](replays/EVENT3_SEARCH.md)). But H1 — that a queue is a **stock** that
integrates an imbalance, rather than a variable relaxing toward pressure — is a claim about
the real world, and can be tested directly on independent data:

```bash
python scripts/test_queue_mechanism.py --write-report
```

Nothing in `event_sim/mechanism/` imports the engine; a hypothesis that only looks good
inside our own simulator has not been tested.

**Result: [H1 SUPPORTED](replays/H1_QUEUE_MECHANISM.md).** Container ships at anchor in San
Pedro Bay rose 9 → 18 → 29 → 40 → 61 over June–October 2021 — increments of **+9, +11, +11,
+21**, which do not decay. Relaxation closes a fixed fraction of a shrinking gap each period,
so under a steady driver its increments *must* shrink. The decisive check needs no fit at
all: for relaxation to produce this curve the driver would have had to rise **about
threefold** over exactly the months when Port of LA import volume was flat. The
one-parameter stock form also fits better than the two-parameter relaxation form
(SSE 116 vs 178).

This does **not** show that adding a queue stock will fix the timing bias — that still needs
a held-out event. H1 therefore moves from `declared` to `independently_supported`, not to
`implemented`.

### H2 — tested the same way, and **not supported**

```bash
python scripts/test_queue_mechanism.py --h2 --write-report
```

H2 says `order_backlog` should integrate too. A backlog has no clean build phase under a
flat driver, so the shape argument does not apply; the distinctive signature of a stock is
**path dependence**, tested as hysteresis on US manufacturing unfilled orders excluding
transportation (Census M3 + Fed capacity utilisation, public domain, stored in the repo).

Two traps had to be avoided, and both mattered:

- **Circularity** — Census *derives* New Orders as Shipments + ΔUnfilled, so New Orders
  cannot be the driver (identity verified to ~1.1%). Fed capacity utilisation is used instead.
- **Trend** — the uncontrolled comparison shows backlog cover **+28%** when pressure returns
  to its starting level, which looks like strong support. Detrended and restricted to one
  cycle, the gap **reverses**: −0.022 months, the wrong sign.

**[H2 NOT SUPPORTED](replays/H2_BACKLOG_MECHANISM.md)** — but marked `not_supported`, not
`rejected`, and not deleted: a national aggregate averages together industries that are
accumulating and draining, so the test is underpowered for a node-level claim.

The test also exposed a **definitional defect**: `order_backlog` conflates cargo physically
waiting at the port (integrates — H1, supported) with unfulfilled customer orders (not shown
to integrate — H2). One variable cannot carry both.

| Hypothesis | Status | Evidence |
|---|---|---|
| H1 queue as a stock | **independently_supported** | real port queue rises with non-decaying increments |
| H2 backlog persistence | **not_supported** | detrended hysteresis has the wrong sign; test underpowered |
| H3 lag structure understated | declared | untested, deprioritised — H1 explains the bias mechanistically |
| H4 recovery asymmetry | declared | untested, may be a consequence of H1 |

So the sketched topology `queue_stock → delay → backlog_stock → inventory → service` is
**half-supported**. Building both legs at once would smuggle an untested mechanism in behind
a tested one.

### H1 implemented experimentally — and what happened

```bash
python scripts/run_h1_experiment.py --write-report
```

The supported leg only (`vessel_queue`) was built as a **separate experimental module**,
`port_disruption_h1_queue_experimental`. The baseline is untouched and still the default.
Acceptance criteria were [pre-registered](replays/H1_EXPERIMENT_PROTOCOL.md) before the
replays were run, and are evaluated in code.

| | Baseline | H1 | Δ |
|---|---|---|---|
| Yantian — peak timing | −9 wk | **−5 wk** | +4 |
| Yantian — peak magnitude error | +3.32 | **+1.39** | better |
| Yantian — envelope coverage | 0.00 | **0.50** | better |
| Yantian — correlation | −0.15 | **+0.69** | better |
| Baltimore — recovery milestone | −6 wk | −6 wk | 0 (predicted) |
| **Combined median** | −6 wk | −5 wk | **+1** |

**Verdict: [`experimental_no_effect`](replays/H1_EXPERIMENT_RESULTS.md)** — four of five
criteria pass; criterion 1 required the *combined median* to move ≥2 turns and it moved 1.

The mechanism itself worked exactly as H1 says it should: the queue survives the return of
capacity, so delay peaks in week 8–9 rather than week 3, with **no hardcoded recovery
delay**. Baltimore was unchanged because its only scored milestone is on `port_capacity`,
which sits *upstream* of the queue — an insensitivity the protocol predicted in advance.

The failing criterion was a **bad aggregator choice of mine**: gating on the median of two
tests, one of which I had already predicted would be frozen. It is applied as written
anyway, because re-scoring an experiment after seeing its results destroys the only thing
pre-registration is for. The fix belongs in the *next* protocol, not this one.

**The default production model is unchanged, and the known defect stays `known`, not
`mitigated`.**

### Held-out validation — attempted, blocked on data

The next step was a genuine held-out test: does frozen H1 improve an independent disruption
that played no part in its formulation, support, implementation or prior evaluation?

The models were frozen first ([H1_HELDOUT_FREEZE.md](replays/H1_HELDOUT_FREEZE.md), with
semantic hashes pinned by a test), the eligibility contract was written before searching
([EVENT3_ELIGIBILITY_CONTRACT.md](replays/EVENT3_ELIGIBILITY_CONTRACT.md)), and candidates
were audited **without running H1 on any of them**.

**Result: no qualifying candidate — [Outcome B](replays/EVENT3_SEARCH_V2.md).** But the
finding changed shape. Round 1 concluded that dense local queue data largely does not exist.
Round 2 found that **it does exist and is sometimes free** — ANTAQ (Brazil) publishes
per-call arrival and berthing timestamps for every port; the Port of Vancouver publishes
daily days-at-anchor. Both returned HTTP 403 from this environment. The blocker is *access*,
not existence, which is a cheaper problem.

No held-out evaluation ran, so **H1's status did not advance** and no new lifecycle state was
appended. What to acquire, and what it would settle, is in
[EVENT3_DATA_DECISION.md](replays/EVENT3_DATA_DECISION.md).

**Follow-up: the ANTAQ blocker is publisher policy, not environment.** Every ANTAQ data host
serves `robots.txt` containing `User-agent: ClaudeBot / Disallow: /`. The earlier HTTP 403
was that policy being enforced. Nothing was worked around — no user-agent was spoofed, no
browser was driven at a host that excludes AI agents. `robots.txt` governs crawlers, not
people: the data stays public, free and openly licensed, and a human can download it
normally. Instructions, the required years and why, are in
[ANTAQ_ACQUISITION.md](replays/ANTAQ_ACQUISITION.md).

The ingestion pipeline is built and waiting (`python -m event_sim.ingest.antaq status`), and
is **schema-agnostic on purpose** — the real ANTAQ schema has never been seen, so it profiles
columns rather than mapping them, and a hard gate refuses to derive waiting time or
reconstruct a queue until a human records what each timestamp means, citing ANTAQ's own data
dictionary. Two timestamps are not a queue measurement until the publisher says what they
are. Detection thresholds are already
[pre-registered](replays/ANTAQ_EVENT_DETECTION_PROTOCOL.md).

### Endpoint causal scope

The in-sample experiment's gate failed because it pooled an endpoint H1 controls with one it
structurally cannot move. Endpoints now carry an explicit scope class, fixed before results
exist:

| Class | Role |
|---|---|
| `h1_sensitive` — `vessel_queue`, `shipping_delay` | **primary efficacy gate** |
| `h1_insensitive` — `port_capacity` | **safety gate only** — must not move |
| `uncertain_scope` — everything downstream of `shipping_delay` | exploratory, never decisive |

`assert_aggregatable()` refuses to pool endpoints across scopes or metric semantics. Shared
units are not shared meaning. The previous verdict stands unchanged; the flaw is recorded in
the [protocol-lesson registry](../event_sim/protocol_lessons.py), never rescored.

### Measurement-risk registry

Four separate measurement failures — Yantian's global monthly proxy, Panama's official-but-
wrong booking slots, San Pedro's mid-series definition change, H2's secular trend — are now a
[checklist of nine risks](../event_sim/evidence/measurement_risk.py) that a future variable
mapping must answer, rather than four anecdotes in four reports.

## Bias metrics

A single R² or MAE cannot express what matters for a disruption model — whether its **clock**
runs at the right speed. Two Event-Simulator-specific metrics, aggregated across events:

| Metric | Meaning | Current value |
|---|---|---|
| `peak_timing_bias` | simulated peak turn − observed peak turn | −9 (Yantian) |
| `recovery_bias` | simulated recovery turn − observed recovery turn | −6 (Baltimore) |
| `combined_timing_bias` | median across all scored tests | **−6, systematically early** |

A median that keeps its sign across independent events is a systematic clock error, not
noise: random model error would change sign between events.

## Model Health

Evidence coverage alone said how much evidence a model carries, but nothing about whether
it works or whether the world can be seen. `event_sim/model_health.py` reports three axes:

```
MODEL HEALTH
  Evidence coverage        FAILED     100% of influence rests on assumptions
  Observability            MEDIUM     1 observable · 4 proxy · 3 latent
  Proxy dependence         HIGH
  Historical validation    FAILED     events tested: yantian_2021, baltimore_2024
  Directional validity     GOOD
  Timing validity          FAILED     median |error| 6 weeks
  Magnitude validity       FAILED     0% envelope coverage
```

Plus a **Known Model Defect** entry, raised only when a defect has been measured on two or
more independent events:

> **Recovery dynamics currently trend too fast.** Across 2 independent historical
> disruptions the model reaches peaks and recoveries a median of 6 turns earlier than
> observed, and never later. Status: known, measured, **not fixed**.
> Affects: any conclusion about *when* an effect peaks or clears.
> Still safe for: direction of effect, and relative comparison between interventions.
> Leading explanation: H1, now independently supported.

A defect is **never deleted** once measured. It advances
`known → mitigated → historically_validated → superseded`, each transition requiring
evidence and recorded in its `history`, so the model keeps its scientific history rather
than quietly appearing to have always worked.

Every rating comes from a stated deterministic rule over evidence and replay results; none
is assigned by a model. The purpose is not to score the model well — it is to say exactly
which parts of an answer to distrust, which is the thing an LLM cannot do about its own
output.

### The rules that make it a real test

| Rule | Enforced by |
|---|---|
| Nothing published after the knowledge cutoff may initialise the world | `validate_no_hindsight` raises `HindsightLeakageError` |
| Only directly observed measurements are scored | `HistoricalObservation.is_scoreable()`; context points are excluded |
| Replay uses the same engine as forward simulation | `replay_episode` calls `event_sim.sweep.run_sweep` on the same slice |
| Calibration cannot overwrite a prior | `CalibrationRecord` stores `prior_range` beside `calibrated_range` |
| Unidentifiable parameters are refused, not fitted | `check_identifiability` returns a reason instead of a number |
| A status must be backed by its provenance | `event_sim.evidence.registry.validate_edge_provenance` |

The no-hindsight rule has a visible cost in the result: the only admissible baseline for
`shipping_delay` was the March 2021 figure (published 27 April), because the April figure —
though it describes a pre-event month — was not published until 31 May, six days after the
event began. The model therefore starts 0.30 days above the actual May level.

## Evidence layer

```
event_sim/evidence/
    validation.py   module validation; unweighted coverage
    schema.py       EvidenceSource · ProxyMapping · FittingProvenance · CalibrationRecord
    registry.py     file-backed source store + status-vs-provenance rules
    coverage.py     evidence strength, influence weighting, gap report, data requirements
    transforms.py   named unit conversions (raw values are never overwritten)
event_sim/evidence_data/
    sources.json    8 sources, each actually retrieved and read
    mappings.json   real metric → simulation variable, with stated limitations
```

**Evidence strength is arithmetic, not judgement.** The low/medium/high label comes from a
published rule over source type, source count, calibration records and proxy usage — no
model assigns it. `GET /api/event_sim/evidence` returns the rule alongside every label.

**Weighted coverage** counts each edge in proportion to its influence on the outcome, so a
well-sourced but inconsequential edge cannot make the model look grounded.

**The gap report** is the core product output: which assumption matters most, and how well
do we actually know it. For this model the answer is `port_capacity → order_backlog` —
HIGH influence, LOW evidence, expert assumption.

## Adding a world module

1. Write `world_models/<domain>/<id>.json` — see [the library contract](../world_models/README.md).
2. Give every edge a `status`. If you have no source, say `expert_assumption` and leave
   `evidence: []`. `event_sim/evidence.py` will reject an unsourced strong status.
3. `python -m pytest tests/test_event_sim_world_model.py` validates every shipped module.

## Extending

- **New event, same world:** build an `EventDefinition` and pass it to `build_simulation`.
- **New intervention:** add it to the module's `interventions`; the engine reads the effect
  per unit from there. An actor supplies only an id and a magnitude — never an effect size.
- **Historical validation:** add an episode under `event_sim/historical/events/` and an
  observed series under `event_sim/historical/observations/`, then
  `evaluate_replay(replay_episode(episode), observations)`. Both directories ship empty:
  no historical dataset was invented, and evaluation raises rather than scoring against
  non-observed values.

## Current limitations

- **All nine edges remain `expert_assumption`.** The grounding effort attached eight real
  sources and one real replay, and *none of it justified promoting a single edge*. The
  evidence audit predicted a ceiling of three reachable edges; the replay reached zero,
  because the two upstream edges into `shipping_delay` are not separately identifiable from
  one event and every other target has no observations. Coverage still reads 100%
  assumption, and that is the honest number.
- **Two historical episodes, no held-out event.** Calibration and evaluation would share
  the same window, so there is still no out-of-sample validation and no edge can honestly
  claim `historically_calibrated`. A third event is what would let a structural hypothesis
  be fitted on one and tested on another.
- **The model is systematically too fast**, on both events. This is a known, measured,
  unfixed defect — deliberately left unfixed until a held-out event can adjudicate between
  the four competing structural hypotheses.
- **Six of eight variables have no observations**, including the headline outcome
  `service_level`. The downstream half of the model is firm-internal and cannot be grounded
  in public data at all — see the audit, §3.
- **One module in the library.** `excluded_systems` therefore reads "no other module",
  which understates what a real analysis would need to exclude.
- **No actors.** Interventions are applied by the user or the API, not chosen by agents.
  The interface for actors is reserved but deliberately unbuilt (see the architecture doc §6).
- **`redirect_cargo` offsets capacity unconditionally**, so leaving it active past the
  disruption would push throughput above normal. The demo ends it with the disruption plus
  a four-week tail.
