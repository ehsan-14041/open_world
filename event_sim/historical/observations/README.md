# Historical observations

Observed series used to grade a replay. **This directory is intentionally empty.**

`event_sim/historical/evaluation.py` will only score points whose `status` is `observed`,
and raises `InsufficientObservationsError` when there are none — so an empty directory
produces an honest failure rather than a fake perfect score.

## File contract (`<episode_id>.json`)

```jsonc
{
  "episode": "suez_2021",
  "observations": [
    {
      "variable": "shipping_delay",   // must match a variable id in the replayed slice
      "turn": 3,                       // turns since the episode start_date, in the episode's time unit
      "value": 11.4,
      "unit": "days",
      "date": "2021-04-12",
      "source": "<real, checkable reference>",
      "status": "observed",
      "note": ""
    }
  ]
}
```

## Rules

- `status` must be `observed` for a point to be scored. Estimates and reconstructions are
  loadable but are counted in `skipped_non_observed`, not in the coverage figure.
- `source` must be checkable. An unsourced number is not an observation.
- Unit mismatches are the caller's responsibility: convert to the variable's declared unit
  before storing, and record the conversion in `note`.
