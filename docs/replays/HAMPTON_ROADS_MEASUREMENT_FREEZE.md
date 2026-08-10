# Hampton Roads measurement freeze

> Written **before** acquiring the detectability sample, and before any anomaly detection.
> Every rule below is fixed. None of it may be changed after inspecting candidate windows —
> if a rule turns out to be wrong, the correct response is a new, separately named
> measurement with its own freeze document, not an edit to this one.

## 1. Geometry

| Field | Value |
|---|---|
| Regulation | **33 CFR 110.168** — Hampton Roads, Virginia and adjacent waters |
| eCFR effective date | **2022-01-01** |
| Source URL | `https://www.ecfr.gov/api/versioner/v1/full/2022-01-01/title-33.xml?part=110` |
| Source SHA-256 | `5ce1f3b7ccbaaddd7c57c3242794a079a4ae7814d428fff55a9c06106784e5b9` |
| Source bytes | 676,745 |
| Frozen artifact | `data/external/ais/geometry/hampton_roads_110.168_2022-01-01.json` |
| Artifact SHA-256 | `7baa46a782ede9dd7fd760a13e164a05246844158f4004c408f55032546dfce7` |
| Coordinate system | WGS84 decimal degrees, (lat, lon) |

### 1.1 Included — 10 commercial anchorages

`F` (4), `G` (7), `H` (5), `I` (9), `J` (7), `K` (7), `M` (6), `N` (8), `Q` (4), `R` (5)
— vertex counts in parentheses.

### 1.2 Excluded — 5 anchorages

| Label | Designation | Why excluded |
|---|---|---|
| A | Naval Anchorage | vessels occupy it for reasons unrelated to port service |
| B | Naval Anchorage | as above |
| C | Naval Anchorage | as above |
| D | Naval Anchorage | as above |
| E | Commercial Explosives Anchorage | occupancy is driven by cargo handling rules, not berth availability |

Exclusion is by the `commercial` property on the parsed polygon, which tests the bracketed
CFR designation for `naval` or `explosive`. It is not a hand-maintained label list.

### 1.3 Radius-defined berths are not polygons

Part 110 defines several berths (e.g. `Anchorage Berth F-1`) as a circle of given radius
about a centre point. These are skipped. A single centre coordinate is not a vertex list,
and treating it as one would invent area that the regulation does not state.

### 1.4 Validity era

The 110.168 definition fingerprint changes between **2020-04-01** and **2020-07-01**
(established by diffing eCFR revisions, before any measurement). It is then stable through
at least 2024-01-01.

**Binding rule: every study window must lie entirely on or after 2020-07-01.** A window
straddling the change is not comparable with itself.

## 2. Observation filters

| Rule | Value |
|---|---|
| Region pre-filter (bounding box) | **derived from the §1.1 polygons** + 0.02° margin → lat 36.8227 – 37.3394, lon −76.4727 – −76.0633. Not a hand-set constant; see §2.1. |
| Vessel class | AIS `VesselType` **70–89** (70–79 cargo, 80–89 tanker) |
| Stationarity | `SOG` < **0.5** knots |
| Containment | point-in-polygon against §1.1 polygons only |
| `TransceiverClass` filter | **none applied** — stated as a choice, not an oversight. The vessel-class filter already selects deep-draft commercial traffic. |
| `Status` (navigational status) | **not used as a criterion.** Recorded, and its agreement with the geometric reconstruction is reported as a diagnostic. It is crew-entered, so it is a declaration rather than an observation. |
| Malformed rows | a row whose `MMSI` is empty, or whose `LAT`/`LON`/`SOG` will not parse as float, is **skipped**, never imputed |

### 2.1 Amendment — the bounding box was a second, silent definition

**Amended 2026-08-10, after acquiring 9 sample days and before computing any baseline
statistic or running any detection.** Recorded here rather than quietly corrected.

The first version of this document set the pre-filter box as a literal: lat 36.80 – 37.10,
lon −76.45 – −75.95. Checking the polygons against it showed:

| Anchorage | Extent | Against the old box |
|---|---|---|
| **R** | lat 37.1522 – 37.3194 | **entirely outside** — never measured at all |
| **I** | lon to −76.4527 | clipped by ~240 m |

So the measurement covered **8 of the 10 anchorages this document names**, while claiming
10. The box had become an independent second definition of the study area, free to disagree
with the geometry.

The fix is structural rather than numeric: `Region` no longer carries a box, and
`region_bbox()` derives it from the commercial polygons plus a margin, so the two cannot
diverge again. A test asserts every commercial polygon lies inside the derived box.

All extracts fetched under the old box were **deleted and re-acquired**; none of them
contributed to any statistic in this or any other document. Two consequences elsewhere:

- The occupancy figures 4 (2022-01-01) and 3 (2022-06-15) quoted in
  [EVENT3_MEASUREMENT_MODEL_AIS.md](EVENT3_MEASUREMENT_MODEL_AIS.md) §5 were computed under
  the clipped box and are therefore **undercounts**. They are superseded.
- The region-containment comparison that selected Hampton Roads is separately qualified in
  §2.2.

This amendment predates any baseline number and any candidate window, so it changes no
threshold and cannot have been motivated by a result.

### 2.2 Qualification on the region-selection metric

Hampton Roads was chosen partly on a containment statistic — median distance from a
stationary deep-draft vessel to the nearest designated anchorage coordinate, 0.9 km. That
statistic used **all** Part 110 coordinates, including the four Naval anchorages, and it
counted every stationary vessel regardless of navigational status.

Inspecting a sample day shows why that matters: of 17 stationary deep-draft vessels in the
region, most reported `Status 5` (**moored**, i.e. alongside a berth) rather than `Status 1`
(at anchor), and none were inside a commercial anchorage polygon.

So the containment figure was measuring *proximity to designated water*, not *use of the
commercial anchorages*. It is not evidence that commercial anchorage occupancy is high. That
question is exactly what the detectability analysis exists to answer, and it is left open
here rather than assumed settled.

## 3. Aggregation

| Rule | Value |
|---|---|
| Temporal unit | one **calendar day**, taken from the date part of `BaseDateTime` as recorded in the source file |
| Deduplication | **distinct MMSI per day.** A vessel contributes at most 1 to a day's occupancy regardless of how many messages it broadcast. |
| Minimum dwell | **none.** One qualifying message makes a vessel present for that day. Transits are already removed by the speed rule; adding a dwell floor would be a second, unvalidated filter. |
| `anchorage_occupancy` | count of distinct qualifying MMSI on that day |
| `entries` | MMSI present on day *d* and absent on day *d−1* |
| `exits` | MMSI present on day *d−1* and absent on day *d* |
| Spell | a maximal run of consecutive days on which one MMSI is present |
| Spell duration | last qualifying timestamp of the final day minus first qualifying timestamp of the first day |
| **Censoring** | a spell touching either edge of a sampled window is **right- or left-censored** and is reported separately. It is never treated as a completed spell. |

Entries, exits and spells are undefined across a gap between sampled windows and are not
computed across one.

## 4. Terminology

The measured quantity is **`anchorage_occupancy`**.

It is **not** `vessel_queue`, `queue`, `queue_length`, `ships_waiting`, `vessels_waiting` or
`waiting_vessels`. AIS transmits position and speed, not intent, so it cannot distinguish a
vessel waiting for a berth from one anchored for weather, crew, documents, or repair.
`assert_not_queue_named` raises on all six names and remains active.

Node classification: **`proxy_observable`**.

## 5. Detectability sample — deterministic window rule

Declared here, before acquisition, so that no window can be chosen for looking quiet or
interesting.

> **Rule.** For each calendar quarter from **2020-Q3 through 2022-Q2** inclusive (8
> quarters), take the 7-day window beginning on the **15th day of the middle month of that
> quarter**.

That yields exactly:

| Quarter | Window |
|---|---|
| 2020-Q3 | 2020-08-15 → 2020-08-21 |
| 2020-Q4 | 2020-11-15 → 2020-11-21 |
| 2021-Q1 | 2021-02-15 → 2021-02-21 |
| 2021-Q2 | 2021-05-15 → 2021-05-21 |
| 2021-Q3 | 2021-08-15 → 2021-08-21 |
| 2021-Q4 | 2021-11-15 → 2021-11-21 |
| 2022-Q1 | 2022-02-15 → 2022-02-21 |
| 2022-Q2 | 2022-05-15 → 2022-05-21 |

56 vessel-days, spanning 2 years, all inside the §1.4 validity era.

Development days already used (**2022-01-01**, **2022-06-15**) fall in none of these windows
and are excluded from baseline statistics regardless.

### 5.1 Baseline may contain genuinely abnormal periods

2021-Q3 and 2021-Q4 fall inside the well-known U.S. port congestion period. They are **kept**.
Dropping them would be event-aware selection, which is exactly what this rule exists to
prevent. The effect is conservative: if those quarters are abnormal, baseline variance is
inflated and detection becomes *harder*, not easier.

## 6. What is not frozen here

Anomaly thresholds. Those are declared separately in
[HAMPTON_ROADS_DETECTABILITY.md](HAMPTON_ROADS_DETECTABILITY.md) after the baseline
distribution is computed but before any continuous search — and are themselves frozen at
that point.
