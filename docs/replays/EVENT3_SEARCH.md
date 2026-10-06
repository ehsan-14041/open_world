# Event #3 search — record of a failed acquisition, and one trap found

**Condition set for event #3:** a local time series — weekly or daily, not milestones — for
**at least two** variables: throughput/capacity **and** queue/delay. That density is what
would let H1 (queue-as-stock) and H2 (backlog persistence) be told apart, because both
predict a *shape*, not just a later peak.

**Outcome: not met.** No port disruption was found with dense local series on two variables.
This is the third consecutive hunt to stop at the same wall, and the pattern is now specific
enough to state as a rule rather than an anecdote.

---

## Candidates assessed

### 1. Panama Canal drought, 2023–24 — **rejected**

By far the best *capacity* data in the project. The Canal Authority publishes official
**Advisory to Shipping** notices giving exact dated booking-slot counts
([A-48-2023](https://pancanal.com/wp-content/uploads/2023/01/ADV48-2023-Reduction-in-Transits-Due-to-the-Ongoing-Deficit-in-Precipitation-in-the-Canal-Watershed.pdf),
read in full), independently confirmed by the
[US EIA](https://www.eia.gov/todayinEnergy/detail.php?id=61443):

| Effective | Booking slots/day |
|---|---|
| from 30 Jul 2023 | ~32 (from 36 normal) |
| 3–6 Nov 2023 | 25 |
| 7–30 Nov 2023 | 24 |
| 1–31 Dec 2023 | 22 |
| 1–31 Jan 2024 | 20 *(later revised up to 24)* |
| from 1 Feb 2024 | 18 |

Rejected for three reasons, each sufficient on its own:

**(a) The obvious capacity proxy is wrong by about a factor of two.** Booking slots are the
*reservable* portion of transits, not total throughput. While slots were 20–22, **actual
transits ran at 32.6/day in January 2024 and 34.8/day in February** — close to normal.
Injecting "capacity −50%" from the slot count would have simulated a disruption roughly
twice the real one, and the replay would have "failed" for a reason that had nothing to do
with the model. This is the single most valuable thing this search produced, and it is a
**measurement-model** failure, not a data-availability one: the number is published,
official, precise — and still the wrong quantity.

**(b) The published schedule is a forward plan, not a record.** The 20 slots announced for
January 2024 were revised upward to 24 in mid-December. An advisory states intent; realised
capacity is a different series.

**(c) The mechanism is disanalogous in exactly the place under test.** The canal rations
demand administratively through a booking and auction system, so the queue cannot
free-run. Observed wait times *fell* through the deepest cuts — 9.09 days (Aug 2023) →
3.1 days (end 2023) → 20.9 hours canal-waters time (Feb 2024) — while slots were still being
reduced, because traffic rerouted and bookings rationed the rest. A queue held down by
administrative rationing is the worst possible place to test whether queues accumulate like
a stock. **H1 would have been unfalsifiable here.**

Delay data was in any case only three dated points, not a series.

### 2. US West Coast congestion, 2021–22 — **rejected**

Has the densest queue series in container shipping: the Marine Exchange of Southern
California published **daily** counts of container ships waiting, running from a low of 9
(June 2021) to an all-time high of 109 (9 January 2022) and back to zero (November 2022) —
a textbook accumulate-and-drain curve, alongside locally published port throughput.

Rejected because **the shock is demand-side**. Capacity did not fall; import volume surged.
This model can only inject a capacity displacement, so representing the event would mean
injecting a fictitious capacity shock to stand for a demand surge. That is fabrication, not
modelling.

Worth recording for later: this dataset is the natural place to test H1 **as a mechanism
question rather than a replay** — does a real port queue behave like a stock with a finite
drain rate? That test needs no simulation at all, and does not require the model to be able
to inject the event.

### 3. Ningbo-Zhoushan Meishan closure, August 2021 — **rejected**

Correct mechanism and a clean 3-week closure, but it sits inside the same 2021 global
congestion wave that already confounded Yantian, shares its data sources, and yields only
scattered point estimates (41 ships at anchor; weekly port calls down 22%, 188→146). It
would not have been independent of benchmark #1.

---

## The pattern, now stated as a rule

Three hunts, three domains, one shape:

| Variable class | Availability |
|---|---|
| Capacity / throughput | **often available**, sometimes officially and precisely |
| Queue / delay | point estimates, or dense only where the shock is the wrong kind |
| Downstream (inventory, service level) | **never** |

And a corollary the Panama case added: *available* is not the same as *correct*. Booking
slots are published, official and precise — and are not the variable the model means. The
gap between a published number and the quantity a model needs is where a
**measurement model** belongs, and it is a distinct failure mode from missing data.

## What event #3 must contain

A future search should stop early unless a candidate satisfies all of:

1. **A capacity-side shock**, so the model can inject it without inventing a demand variable.
2. **Realised throughput**, weekly or finer, for the affected node — not administrative
   allocations, plans, or reservable quotas.
3. **A queue or delay series** for the same node, weekly or finer, spanning the full
   accumulate → peak → drain arc. Points only at the peak cannot distinguish H1 from H3.
4. **No administrative rationing** of the queue during the episode.
5. **Regime independence** from Yantian 2021 and Baltimore 2024.

Realistically this means either a national port authority that publishes weekly operational
statistics, or a commercial AIS/port-call dataset (Spire, MarineTraffic, project44,
Clarksons) under licence — which moves event #3 from a research task to a procurement one.

## Consequence for the plan

The sequence the model needs — calibrate on events 1–2, freeze, evaluate on a held-out event
3 — **cannot begin yet**. The four structural hypotheses in `event_sim/cross_event.py`
remain declared and unimplemented, which is the correct state: with two events, adopting one
would fit the benchmarks rather than find the mechanism.

The measured defect stands and is now reported on the product surface as a
[Known Model Defect](../EVENT_SIMULATOR.md#model-health): *recovery dynamics currently trend
too fast, median −6 turns across two independent disruptions, never late.*
