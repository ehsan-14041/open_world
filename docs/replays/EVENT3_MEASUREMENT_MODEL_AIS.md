# AIS measurement model — what is observed, what is reconstructed, what is refused

> Written **before** any event detection, so that the definition of the measurement cannot
> be adjusted after seeing which windows it makes interesting.
>
> Implementation: [`event_sim/ingest/ais.py`](../../event_sim/ingest/ais.py),
> [`event_sim/ingest/cfr_anchorage.py`](../../event_sim/ingest/cfr_anchorage.py).

## 1. The distinction this whole document exists to protect

AIS broadcasts position, speed, heading, and a crew-entered navigational status. It does
**not** broadcast intent. A stationary ship inside an anchorage may be waiting for a berth —
or waiting for weather, cargo documents, a crew change, a tide, a repair, or a charterer's
instruction.

Therefore:

| Emitted | Not emitted |
|---|---|
| `anchorage_occupancy` — distinct cargo/tanker vessels observed stationary inside a legally designated anchorage on a given day | `vessel_queue` — vessels waiting for berth service |

Occupancy is an observation. A queue is an interpretation. The gap between them is exactly
the kind of gap this project has already been caught by once, when Panama's booking-slot
numbers turned out to be official, precise, and the wrong quantity.

This is enforced in code, not just in prose. `assert_not_queue_named` raises
`MeasurementError` on `vessel_queue`, `queue`, `queue_length`, `ships_waiting`,
`vessels_waiting` and `waiting_vessels`, so the distinction cannot be lost to a later
rename.

Node classification for anything built on this series: **`proxy_observable`**, never
`observable`.

## 2. Geometry comes from the law, not from the data

Fitting an anchorage polygon to where ships were observed to sit would be circular — the
boundary would be derived from the behaviour it is meant to measure, and a congestion event
would quietly redraw its own definition.

So geometry comes from **33 CFR Part 110**, the federal regulation that defines U.S.
anchorage grounds by explicit latitude/longitude, retrieved from the eCFR versioner API
(public, no key). It is authoritative, entirely independent of AIS, and — critically —
**versioned by effective date**.

### 2.1 That versioning turned `definition_change` from an assumption into a test

`definition_change` is one of the nine registered measurement risks. Normally it is an
unknown one hopes is small. Here it can be checked directly by diffing revisions, and the
check found real changes:

| Section | Finding |
|---|---|
| 110.197 (Bolivar Roads) | area (C) went from 4 to 8 vertices; change falls between **2018-03-01 and 2018-06-01** |
| 110.168 (Hampton Roads) | definition fingerprint changes between **2020-04-01 and 2020-07-01**; stable 2020-07 → 2024 |

**Consequence, binding on any study window:** a Hampton Roads window must lie entirely
within **2020-07-01 → present**, or entirely before 2020-04-01. A window straddling the
change is not comparable with itself, and no amount of statistical care fixes that.

This constraint was derived mechanically, before any event was considered.

## 3. Port selection, on measurement validity alone

The obvious selection criterion — vessel density — is the wrong one. What matters is
whether the *independent* legal geometry actually contains the fleet that waits. If it does
not, the measurement is unusable no matter how many vessels are present.

Containment was measured on a real national AIS snapshot (2022-01-01, 75,775 records,
1,531 distinct deep-draft vessels), as the distance from each stationary cargo/tanker vessel
to the nearest of 824 designated anchorage coordinates parsed from Part 110:

| Region | Stationary vessels | Within 2 km | Beyond 10 km | Median km |
|---|---|---|---|---|
| **Hampton Roads / Norfolk** | 20 | 16 | **0** | **0.9** |
| San Francisco Bay | 34 | 29 | 0 | 1.1 |
| New York / New Jersey | 16 | 5 | 0 | 3.1 |
| Charleston | 11 | 0 | 0 | 8.0 |
| Houston / Galveston | 120 | 0 | **111** | **30.3** |
| Puget Sound | 34 | 3 | 25 | 33.2 |
| Savannah | 8 | 0 | 8 | 109.4 |

### 3.1 Houston was rejected, and it was the highest-density candidate

Houston had by far the most stationary deep-draft vessels (120) and led every raw-density
ranking. It fails completely on containment: 111 of 120 vessels lay more than 10 km from any
designated anchorage. A full day's reconstruction confirmed it — **occupancy = 2** against
roughly 55 vessels self-reporting at anchor in the same region.

The reason is structural, not a parsing artifact: 33 CFR 110 designates only Bolivar Roads
(110.197) near Houston. There is **no Houston Ship Channel anchorage section at all**.
Deep-draft vessels wait for Houston in offshore areas carrying no Part 110 designation, so
no AIS-independent legal boundary exists to measure them.

The available fix — drawing a polygon around where ships were observed to wait — is exactly
the circularity §2 forbids, so it was not done. Houston is recorded in `REJECTED_REGIONS`
with its reason rather than quietly dropped.

San Francisco Bay was rejected separately: containment is fine, but 33 CFR 110.224 spans San
Pablo Bay, Carquinez Strait, Suisun Bay and the Sacramento River — roughly 100 km of inland
waterway. That geometry describes a river system, not a port approach, and fails local
specificity.

> **Qualification added later.** This containment statistic used *all* Part 110 coordinates,
> including the four Naval anchorages, and counted every stationary vessel regardless of
> navigational status. Most stationary deep-draft vessels at Hampton Roads report `Status 5`
> (moored alongside a berth), not `Status 1` (at anchor). So 0.9 km measures proximity to
> designated water, not use of the commercial anchorages, and it is **not** evidence that
> commercial occupancy is high. See
> [HAMPTON_ROADS_MEASUREMENT_FREEZE.md](HAMPTON_ROADS_MEASUREMENT_FREEZE.md) §2.2.

**Selected region: Hampton Roads (33 CFR 110.168).** Best containment, tight port-approach
geometry. Of its 15 parsed anchorages, 4 are Naval and 1 is Commercial Explosives; those are
excluded, leaving 10 commercial anchorages (F, G, H, I, J, K, M, N, Q, R).

## 4. Reconstruction rules, fixed in advance

1. **Geometry is external** — Part 110 polygons only, never fitted to observations.
2. **Vessel class** — AIS VesselType 70–89 (cargo, tanker) only. This is what removes the
   inland towboat traffic that dominates raw record counts on river systems.
3. **Stationarity** — speed over ground below **0.5 knots**. A ship transiting a polygon is
   not occupying it.
4. **Presence, not persistence** — a vessel counts for a day if it satisfies (1)–(3) at any
   sampled instant. The metric is distinct-MMSI occupancy, not vessel-hours.
5. **Non-commercial anchorages excluded** — naval and explosives anchorages hold vessels for
   reasons unrelated to port service.
6. **Self-reported status is a cross-check, never the definition.** AIS `Status` is keyed in
   by the crew. It is recorded, and its agreement with the geometric reconstruction is
   reported, because disagreement is diagnostic — but the measurement stands on geometry and
   speed, which are observed rather than declared.

## 5. Validation on real days

> **Superseded.** The figures below were computed with a hand-set region bounding box that
> excluded anchorage R entirely and clipped anchorage I, so they cover 8 of the 10 commercial
> anchorages and are **undercounts**. The box is now derived from the geometry; see
> [HAMPTON_ROADS_MEASUREMENT_FREEZE.md](HAMPTON_ROADS_MEASUREMENT_FREEZE.md) §2.1. Kept here
> rather than edited away, because they are what the pipeline-validation claim rested on.

| Date | Vessels in region | `anchorage_occupancy` | Status agreement |
|---|---|---|---|
| 2022-01-01 | 40 | 4 (undercount) | 0.996 |
| 2022-06-15 | 40 | 3 (undercount) | 0.471 |

Acquisition cost: ~284 MB and ~94 s per day. The national file is streamed to a temporary
path, filtered to the region, and deleted; only the regional extract (~70 k rows) and a
provenance record with the national SHA-256 persist.

## 6. Registered measurement risks

| Risk | Status here |
|---|---|
| `definition_change` | **Detected and bounded** (§2.1). Windows constrained to 2020-07 onward. |
| `proxy_mismatch` | **Active and unresolved.** Occupancy is not queue length. This is the dominant risk and the reason for `proxy_observable`. |
| `circular_measurement` | **Mitigated by construction** — geometry is legal, not fitted. |
| `geographic_mismatch` | **Mitigated** — per-vessel coordinates, single port approach. |
| `temporal_aggregation` | **Low** — daily from sub-minute observations. |
| `scheduled_vs_observed` | **Not applicable** — AIS is observed, not scheduled. |
| `administrative_rationing` | **Active.** If a port meters arrivals offshore, vessels never enter the designated anchorage and occupancy understates waiting. |
| `aggregation_masking` | **Active.** Occupancy of 3–4 on normal days is a small count; Poisson noise is material and the dynamic range for detecting an event is narrow. |
| `secular_trend` | **Untested** — requires the long series, which has not been acquired. |

## 7. What has *not* been established

- **No Event #3 exists yet.** No anomaly detection has been run. Detection requires a
  multi-month daily series; at ~94 s/day a 120-day window is roughly 3 hours of bulk
  acquisition, which has not been performed.
- **No driver source has been secured.** AIS shows vessels, not the cause of a disruption.
  Per the task's §23, if the driver cannot be represented honestly, the outcome is
  `EVENT3_DRIVER_GAP.md`, not a driver invented to fit.
- **H1 has not been run** and its lifecycle state remains `experimental_no_effect`.
- **The normal-day occupancy level (3–4) may prove too low** to separate an event from
  counting noise. That is a real risk to the whole approach and is not yet resolved.
