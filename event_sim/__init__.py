"""
Event Simulator — evidence-grounded event simulation on the Open World Engine.

Separate product surface from the Enterprise Operations Decision Simulator; shares the
engine's state container (core.world_model.WorldModel), checkpoint store
(simulation.checkpoints.CheckpointStore), transition provenance (schemas.provenance) and
bounds enforcement (model.valuespec).

Scientific contract (enforced, not decorative):
  - No module in this package imports an LLM client. State transitions are deterministic.
  - Every causal edge carries an EvidenceStatus; there is no status that defaults to "fact".
  - Outputs are trajectories under named assumptions, never probabilities of future events.

See docs/EVENT_SIMULATOR_ARCHITECTURE.md.
"""

from event_sim.schemas import (
    AssumptionAxis,
    CausalEdgeEvidence,
    EffectRange,
    Evidence,
    EvidenceStatus,
    EventDefinition,
    HistoricalObservation,
    Lag,
    Trajectory,
    VariableDefinition,
    WorldBranch,
    WorldModule,
    WorldSlice,
)

__all__ = [
    "AssumptionAxis",
    "CausalEdgeEvidence",
    "EffectRange",
    "Evidence",
    "EvidenceStatus",
    "EventDefinition",
    "HistoricalObservation",
    "Lag",
    "Trajectory",
    "VariableDefinition",
    "WorldBranch",
    "WorldModule",
    "WorldSlice",
]
