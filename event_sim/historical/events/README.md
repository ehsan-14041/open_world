# Historical events

Episode definitions for replay. **This directory is intentionally empty.** No historical
episode was authored from memory: a replay built on invented dates, capacities or
durations would produce a validation result that looks rigorous and means nothing.

## Candidate benchmark episodes

| Episode | Why it is a good test | What must be collected first |
|---|---|---|
| 2021 Suez Canal blockage | Sharp, dated, single-cause, well-documented downstream effects | Blockage window, transit-time series, spot freight index, downstream stock effects |
| Major port strikes (various) | Known duration, known capacity loss, alternative routing observable | Strike dates, throughput series, diverted-volume figures |
| COVID-era logistics disruption | Long-duration, multi-cause — a hard case for a single-module slice | Throughput, congestion, freight and inventory series, plus demand-side context |

## File contract (`<episode_id>.json`)

```jsonc
{
  "id": "suez_2021",
  "title": "Suez Canal blockage, March 2021",
  "modules": ["port_disruption"],
  "time_unit": "weeks",
  "start_date": "2021-03-22",
  "turns": 20,
  "initial_state": { "port_capacity": 100.0 },   // observed pre-event levels
  "event": {
    "id": "canal_blockage",
    "targets": { "port_capacity": -60.0 },
    "start_turn": 1,
    "duration": 1,
    "shape": "step",
    "status": "observed",                         // requires an evidence record
    "evidence": [ { "type": "...", "reference": "...", "year": 2021 } ]
  },
  "sources": [ { "type": "...", "reference": "..." } ]
}
```

Every number here must trace to a real source. `event.status` may only be `observed` with
an attached evidence record; otherwise state it as `expert_assumption` and expect the
evaluation to be read accordingly.
