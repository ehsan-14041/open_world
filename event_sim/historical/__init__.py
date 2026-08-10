"""
Historical replay architecture (scaffolding).

    historical state  →  inject historical event  →  simulate
                      →  trajectory envelope      →  compare with observed history

`events/` and `observations/` ship **empty**. No historical series was invented to make
this look complete: fabricating a 2021 Suez or COVID-era dataset would produce a
validation result that means nothing while looking rigorous. See the READMEs in those
directories for the file contract and the candidate benchmark episodes.
"""

from event_sim.historical.calibration import (
    CalibrationOutcome,
    calibrate_edge,
    calibrate_episode,
    check_identifiability,
    write_calibration_records,
)
from event_sim.historical.evaluation import (
    InsufficientObservationsError,
    directional_accuracy,
    envelope_coverage,
    evaluate_replay,
    milestone_evaluation,
    trajectory_metrics,
)
from event_sim.historical.replay import (
    HindsightLeakageError,
    HistoricalEpisode,
    available_episodes,
    build_replay_slice,
    load_episode,
    load_milestones,
    load_observations,
    observation_metadata,
    replay_episode,
    validate_no_hindsight,
)

__all__ = [
    "CalibrationOutcome",
    "HindsightLeakageError",
    "HistoricalEpisode",
    "InsufficientObservationsError",
    "available_episodes",
    "build_replay_slice",
    "calibrate_edge",
    "calibrate_episode",
    "check_identifiability",
    "directional_accuracy",
    "envelope_coverage",
    "evaluate_replay",
    "milestone_evaluation",
    "load_episode",
    "load_milestones",
    "load_observations",
    "observation_metadata",
    "replay_episode",
    "trajectory_metrics",
    "validate_no_hindsight",
    "write_calibration_records",
]
