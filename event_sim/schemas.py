"""
Event Simulator schemas (Phase B).

Plain dataclasses with from_dict/to_dict, matching the repository's existing
dict-over-the-wire convention (schemas/scenario_schema.py, schemas/provenance.py).
Everything here is JSON-round-trippable so world modules live in version-controlled
files and slices can be persisted with a run.

The central design rule: a causal edge cannot exist without an epistemic status.
`CausalEdgeEvidence.status` has no default that reads as "established fact", and
`event_sim.evidence.validate_module` rejects a strong status with no evidence record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# --------------------------------------------------------------------------------------
# Epistemic ladder
# --------------------------------------------------------------------------------------

EvidenceStatus = Literal[
    "observed",                 # directly measured in this world
    "empirical",                # fitted from data we hold
    "literature_backed",        # published study attached
    "historically_calibrated",  # tuned against a replayed historical episode
    "expert_assumption",        # domain judgement, stated as such
    "user_assumption",          # supplied by the user for this run
    "ai_hypothesis",            # proposed by a model; never silently a fact
]

#: Ordered strongest → weakest. Used for coverage reporting and status floors.
EVIDENCE_STATUS_ORDER: tuple[EvidenceStatus, ...] = (
    "observed",
    "empirical",
    "literature_backed",
    "historically_calibrated",
    "expert_assumption",
    "user_assumption",
    "ai_hypothesis",
)

#: Statuses that require at least one Evidence record to be claimed.
EVIDENCE_BACKED_STATUSES: frozenset[str] = frozenset(
    {"observed", "empirical", "literature_backed", "historically_calibrated"}
)

#: Coarse grouping used by the coverage panel.
EVIDENCE_STATUS_GROUP: dict[str, str] = {
    "observed": "observed_empirical",
    "empirical": "observed_empirical",
    "literature_backed": "literature_backed",
    "historically_calibrated": "literature_backed",
    "expert_assumption": "assumption",
    "user_assumption": "assumption",
    "ai_hypothesis": "ai_hypothesis",
}

EffectSetting = Literal["low", "central", "high"]

Confidence = Literal["low", "medium", "high"]

# --------------------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------------------
#
# The Yantian replay established that the binding constraint on validating this model is
# not the simulation engine but whether the real world can be *seen* at all. Every node
# must therefore declare which of three regimes it lives in, so a world builder — and a
# reader — knows which parts of a world are measured, which are inferred through a stand-in,
# and which are pure model.

ObservabilityClass = Literal[
    "observable",        # a real series for THIS variable exists and is obtainable
    "proxy_observable",  # the variable itself is not published; a stand-in is, with cost
    "latent",            # no adequate public counterpart exists; the model carries it alone
]

OBSERVABILITY_ORDER: tuple[ObservabilityClass, ...] = ("observable", "proxy_observable", "latent")

OBSERVABILITY_LABELS: dict[str, str] = {
    "observable": "Directly observable",
    "proxy_observable": "Observable only through a proxy",
    "latent": "Latent — no public counterpart",
}


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


# --------------------------------------------------------------------------------------
# Evidence primitives
# --------------------------------------------------------------------------------------


@dataclass
class Evidence:
    """One provenance record supporting a causal claim or a parameter value."""

    type: str  # empirical_study | dataset | historical_episode | expert_panel | model_output | ...
    reference: str = ""
    year: int | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "reference": self.reference, "year": self.year, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Evidence:
        return cls(
            type=str(d.get("type") or "unspecified"),
            reference=str(d.get("reference") or ""),
            year=int(d["year"]) if isinstance(d.get("year"), (int, float)) else None,
            note=str(d.get("note") or ""),
        )


@dataclass
class EffectRange:
    """
    Uncertain effect magnitude. The three points are the sweep settings for this edge —
    the evidence range and the parameter axis are deliberately the same object, so a world
    cannot be run at a coefficient that the evidence record does not span.
    """

    low: float
    central: float
    high: float

    def value_for(self, setting: str) -> float:
        """Coefficient for a named effect setting ('low' | 'central' | 'high')."""
        if setting == "low":
            return float(self.low)
        if setting == "high":
            return float(self.high)
        return float(self.central)

    def span(self) -> float:
        """Width of the plausible range (|high - low|)."""
        return abs(float(self.high) - float(self.low))

    def to_dict(self) -> dict[str, float]:
        return {"low": float(self.low), "central": float(self.central), "high": float(self.high)}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | float | int) -> EffectRange:
        if isinstance(d, (int, float)):
            v = float(d)
            return cls(low=v, central=v, high=v)
        central = float(d.get("central", 0.0))
        return cls(
            low=float(d.get("low", central)),
            central=central,
            high=float(d.get("high", central)),
        )


@dataclass
class Lag:
    """Delay window for a causal edge, in module time units (weeks for the first slice)."""

    min: int = 0
    max: int = 0
    unit: str = "weeks"

    def effective(self, setting: str = "central") -> int:
        """
        Lag actually used by the engine. 'low' = fastest transmission (min),
        'high' = slowest (max), 'central' = midpoint, rounded down.
        """
        lo, hi = int(self.min), int(self.max)
        if hi < lo:
            lo, hi = hi, lo
        if setting == "low":
            return max(0, lo)
        if setting == "high":
            return max(0, hi)
        return max(0, (lo + hi) // 2)

    def to_dict(self) -> dict[str, Any]:
        return {"min": int(self.min), "max": int(self.max), "unit": self.unit}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | int | None) -> Lag:
        if d is None:
            return cls()
        if isinstance(d, int):
            return cls(min=d, max=d)
        return cls(
            min=int(d.get("min", 0)),
            max=int(d.get("max", d.get("min", 0))),
            unit=str(d.get("unit") or "weeks"),
        )


# --------------------------------------------------------------------------------------
# World model primitives
# --------------------------------------------------------------------------------------


@dataclass
class CausalEdgeEvidence:
    """
    One causal edge with full provenance. This is the unit the evidence-coverage panel
    counts and the unit the causal trace attributes contributions to.
    """

    source: str
    target: str
    polarity: Literal["positive", "negative"]
    effect: EffectRange
    status: EvidenceStatus
    lag: Lag = field(default_factory=Lag)
    evidence: list[Evidence] = field(default_factory=list)
    geography: list[str] = field(default_factory=lambda: ["global"])
    confidence: Confidence = "low"
    mechanism: str = ""
    #: 'linear' is the engine's original propagation. 'conservation' marks an edge that is
    #: realised by a stock's conservation rule instead of a linear coefficient — it is kept
    #: in the graph so it is still counted by evidence coverage and appears in the trace.
    mechanism_type: str = "linear"
    calibration: dict[str, Any] = field(default_factory=dict)
    axis: str | None = None  # assumption axis this edge's effect setting is bound to

    @property
    def id(self) -> str:
        return f"{self.source}->{self.target}"

    def coefficient(self, setting: str = "central") -> float:
        """
        Signed coefficient for propagation. Polarity is authoritative: a 'negative' edge
        always transmits with a negative sign regardless of how the range was written.
        """
        magnitude = abs(self.effect.value_for(setting))
        return -magnitude if self.polarity == "negative" else magnitude

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "polarity": self.polarity,
            "effect": self.effect.to_dict(),
            "lag": self.lag.to_dict(),
            "evidence": [e.to_dict() for e in self.evidence],
            "geography": list(self.geography),
            "confidence": self.confidence,
            "status": self.status,
            "mechanism": self.mechanism,
            "mechanism_type": self.mechanism_type,
            "calibration": dict(self.calibration),
            "axis": self.axis,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CausalEdgeEvidence:
        polarity = str(d.get("polarity") or "positive").lower()
        if polarity not in ("positive", "negative"):
            polarity = "positive"
        return cls(
            source=str(d["source"]),
            target=str(d["target"]),
            polarity=polarity,  # type: ignore[arg-type]
            effect=EffectRange.from_dict(d.get("effect", 0.0)),
            status=str(d.get("status") or "ai_hypothesis"),  # type: ignore[arg-type]
            lag=Lag.from_dict(d.get("lag")),
            evidence=[Evidence.from_dict(e) for e in (d.get("evidence") or [])],
            geography=_as_str_list(d.get("geography")) or ["global"],
            confidence=str(d.get("confidence") or "low"),  # type: ignore[arg-type]
            mechanism=str(d.get("mechanism") or ""),
            mechanism_type=str(d.get("mechanism_type") or "linear"),
            calibration=dict(d.get("calibration") or {}),
            axis=(str(d["axis"]) if d.get("axis") else None),
        )


@dataclass
class VariableDefinition:
    """
    One node. `baseline` and `scale` define the deviation space the engine evolves in;
    `response` is the per-turn fraction of the gap to causal pressure that is closed
    (1.0 = instant, 0.1 = very sluggish). There is no implicit decay anywhere.
    """

    id: str
    unit: str = ""
    label: str = ""
    baseline: float = 0.0
    scale: float = 1.0
    minimum: float | None = None
    maximum: float | None = None
    response: float = 0.5
    #: How this variable evolves. 'relaxation' is the engine's original and only behaviour;
    #: 'stock' applies a conservation rule instead (H1). Defaulting to 'relaxation' means
    #: every existing module keeps byte-identical dynamics.
    kind: str = "relaxation"
    #: Configuration for kind='stock'. See event_sim/engine.py::_step_stock.
    stock: dict[str, Any] = field(default_factory=dict)
    observability: str = "derived"  # measured | reported | derived (how the value arises)
    #: Whether the real world can be seen for this node at all. Distinct from
    #: `observability`: a variable can be 'measured' inside a firm and still be `latent`
    #: from the outside, which is exactly the case for service_level.
    observability_class: ObservabilityClass = "latent"
    observability_note: str = ""
    status: EvidenceStatus = "expert_assumption"
    description: str = ""
    axis: str | None = None  # assumption axis that modulates this variable's response

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "unit": self.unit,
            "label": self.label,
            "baseline": self.baseline,
            "scale": self.scale,
            "range": {"min": self.minimum, "max": self.maximum},
            "dynamics": {"response": self.response, "kind": self.kind, "stock": dict(self.stock)},
            "observability": self.observability,
            "observability_class": self.observability_class,
            "observability_note": self.observability_note,
            "status": self.status,
            "description": self.description,
            "axis": self.axis,
        }

    def to_valuespec(self) -> dict[str, Any]:
        """Spec dict consumable by model.valuespec.clamp_state_to_specs (engine reuse)."""
        spec: dict[str, Any] = {"behavior_type": "FLOW", "decay": 0.0, "inertia": 0.0}
        if self.minimum is not None:
            spec["min"] = self.minimum
        if self.maximum is not None:
            spec["max"] = self.maximum
        if self.unit:
            spec["unit"] = self.unit
        return spec

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VariableDefinition:
        rng = d.get("range") or {}
        dyn = d.get("dynamics") or {}
        return cls(
            id=str(d["id"]),
            unit=str(d.get("unit") or ""),
            label=str(d.get("label") or d["id"]),
            baseline=float(d.get("baseline", 0.0)),
            scale=float(d.get("scale", 1.0) or 1.0),
            minimum=(float(rng["min"]) if rng.get("min") is not None else None),
            maximum=(float(rng["max"]) if rng.get("max") is not None else None),
            response=float(dyn.get("response", 0.5)),
            kind=str(dyn.get("kind") or "relaxation"),
            stock=dict(dyn.get("stock") or {}),
            observability=str(d.get("observability") or "derived"),
            observability_class=str(d.get("observability_class") or "latent"),  # type: ignore[arg-type]
            observability_note=str(d.get("observability_note") or ""),
            status=str(d.get("status") or "expert_assumption"),  # type: ignore[arg-type]
            description=str(d.get("description") or ""),
            axis=(str(d["axis"]) if d.get("axis") else None),
        )


@dataclass
class AssumptionAxis:
    """
    A named uncertain dimension of the world. Sweeps enumerate the product of axis
    settings; pivotal-assumption analysis reports how much each axis moves the outcome.
    """

    id: str
    label: str = ""
    settings: list[str] = field(default_factory=lambda: ["low", "central", "high"])
    description: str = ""
    applies_to: list[str] = field(default_factory=list)  # edge ids / variable ids; empty = module default
    #: setting name -> {"effect": "low|central|high", "response_multiplier": float}
    #: Lets an axis be named in domain terms ("slow" / "fast" recovery) while still
    #: resolving to a point inside the edge's evidenced effect range.
    mapping: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: EvidenceStatus = "expert_assumption"

    def effect_setting(self, setting: str) -> str:
        """Effect point ('low'|'central'|'high') this axis setting selects on bound edges."""
        spec = self.mapping.get(setting) or {}
        value = spec.get("effect")
        if value in ("low", "central", "high"):
            return str(value)
        return setting if setting in ("low", "central", "high") else "central"

    def response_multiplier(self, setting: str) -> float:
        """Multiplier applied to bound variables' response rate for this axis setting."""
        spec = self.mapping.get(setting) or {}
        value = spec.get("response_multiplier")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return 1.0

    def default_setting(self) -> str:
        """Middle setting, used as the baseline world's configuration."""
        if not self.settings:
            return "central"
        return self.settings[len(self.settings) // 2]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "settings": list(self.settings),
            "description": self.description,
            "applies_to": list(self.applies_to),
            "mapping": {k: dict(v) for k, v in self.mapping.items()},
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AssumptionAxis:
        return cls(
            id=str(d["id"]),
            label=str(d.get("label") or d["id"]),
            settings=[str(s) for s in (d.get("settings") or ["low", "central", "high"])],
            description=str(d.get("description") or ""),
            applies_to=_as_str_list(d.get("applies_to")),
            mapping={str(k): dict(v) for k, v in (d.get("mapping") or {}).items()},
            status=str(d.get("status") or "expert_assumption"),  # type: ignore[arg-type]
        )


@dataclass
class WorldModule:
    """
    A reusable slice of the world (economy / energy / supply_chain / ...). Modules are
    files under world_models/<domain>/<id>.json. Deliberately small: the design goal is a
    library of composable modules, not a model of everything.
    """

    id: str
    domain: str
    title: str = ""
    time_unit: str = "weeks"
    version: str = "0.1.0"
    geography: list[str] = field(default_factory=lambda: ["global"])
    description: str = ""
    variables: list[VariableDefinition] = field(default_factory=list)
    edges: list[CausalEdgeEvidence] = field(default_factory=list)
    axes: list[AssumptionAxis] = field(default_factory=list)
    interventions: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def variable_ids(self) -> list[str]:
        return [v.id for v in self.variables]

    def variable(self, vid: str) -> VariableDefinition | None:
        for v in self.variables:
            if v.id == vid:
                return v
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "title": self.title,
            "time_unit": self.time_unit,
            "version": self.version,
            "geography": list(self.geography),
            "description": self.description,
            "variables": [v.to_dict() for v in self.variables],
            "edges": [e.to_dict() for e in self.edges],
            "axes": [a.to_dict() for a in self.axes],
            "interventions": [dict(i) for i in self.interventions],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldModule:
        return cls(
            id=str(d["id"]),
            domain=str(d.get("domain") or "unspecified"),
            title=str(d.get("title") or d["id"]),
            time_unit=str(d.get("time_unit") or "weeks"),
            version=str(d.get("version") or "0.1.0"),
            geography=_as_str_list(d.get("geography")) or ["global"],
            description=str(d.get("description") or ""),
            variables=[VariableDefinition.from_dict(v) for v in (d.get("variables") or [])],
            edges=[CausalEdgeEvidence.from_dict(e) for e in (d.get("edges") or [])],
            axes=[AssumptionAxis.from_dict(a) for a in (d.get("axes") or [])],
            interventions=[dict(i) for i in (d.get("interventions") or [])],
            notes=str(d.get("notes") or ""),
        )


# --------------------------------------------------------------------------------------
# Run-time constructs
# --------------------------------------------------------------------------------------


@dataclass
class WorldSlice:
    """
    The part of the world a run actually instantiates, plus what it deliberately left out.
    `excluded_systems` and `missing_evidence` are first-class: a user must be able to see
    what the simulation is not modelling.
    """

    id: str
    question: str = ""
    time_unit: str = "weeks"
    included_systems: list[str] = field(default_factory=list)
    excluded_systems: list[str] = field(default_factory=list)
    variables: list[VariableDefinition] = field(default_factory=list)
    edges: list[CausalEdgeEvidence] = field(default_factory=list)
    axes: list[AssumptionAxis] = field(default_factory=list)
    interventions: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    def variable(self, vid: str) -> VariableDefinition | None:
        for v in self.variables:
            if v.id == vid:
                return v
        return None

    def variable_specs(self) -> dict[str, dict[str, Any]]:
        """Specs for model.valuespec.clamp_state_to_specs (shared engine bounds enforcement)."""
        return {v.id: v.to_valuespec() for v in self.variables}

    def baseline_state(self) -> dict[str, float]:
        return {v.id: float(v.baseline) for v in self.variables}

    def edges_into(self, target: str) -> list[CausalEdgeEvidence]:
        return [e for e in self.edges if e.target == target]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "time_unit": self.time_unit,
            "included_systems": list(self.included_systems),
            "excluded_systems": list(self.excluded_systems),
            "variables": [v.to_dict() for v in self.variables],
            "edges": [e.to_dict() for e in self.edges],
            "axes": [a.to_dict() for a in self.axes],
            "interventions": [dict(i) for i in self.interventions],
            "assumptions": [dict(a) for a in self.assumptions],
            "missing_evidence": [dict(m) for m in self.missing_evidence],
            "coverage": dict(self.coverage),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldSlice:
        return cls(
            id=str(d.get("id") or "slice"),
            question=str(d.get("question") or ""),
            time_unit=str(d.get("time_unit") or "weeks"),
            included_systems=_as_str_list(d.get("included_systems")),
            excluded_systems=_as_str_list(d.get("excluded_systems")),
            variables=[VariableDefinition.from_dict(v) for v in (d.get("variables") or [])],
            edges=[CausalEdgeEvidence.from_dict(e) for e in (d.get("edges") or [])],
            axes=[AssumptionAxis.from_dict(a) for a in (d.get("axes") or [])],
            interventions=[dict(i) for i in (d.get("interventions") or [])],
            assumptions=[dict(a) for a in (d.get("assumptions") or [])],
            missing_evidence=[dict(m) for m in (d.get("missing_evidence") or [])],
            coverage=dict(d.get("coverage") or {}),
        )


@dataclass
class EventDefinition:
    """
    The injected shock. `magnitude` is expressed in the target variable's own unit as a
    displacement from baseline (e.g. -70 for a 70-point drop in port_capacity index).

    shape: 'step'  — full magnitude for the whole duration, then released
           'ramp'  — linear onset to full magnitude over the duration
           'pulse' — full magnitude on the first turn only
    """

    id: str
    label: str = ""
    description: str = ""
    targets: dict[str, float] = field(default_factory=dict)
    start_turn: int = 1
    duration: int = 1
    shape: Literal["step", "ramp", "pulse"] = "step"
    status: EvidenceStatus = "user_assumption"
    evidence: list[Evidence] = field(default_factory=list)

    def active_turns(self) -> range:
        return range(self.start_turn, self.start_turn + max(1, self.duration))

    def magnitude_at(self, turn: int) -> dict[str, float]:
        """Displacement applied to each target at `turn` (empty when inactive)."""
        if turn not in self.active_turns():
            return {}
        dur = max(1, self.duration)
        if self.shape == "pulse":
            factor = 1.0 if turn == self.start_turn else 0.0
        elif self.shape == "ramp":
            factor = min(1.0, (turn - self.start_turn + 1) / float(dur))
        else:
            factor = 1.0
        if factor == 0.0:
            return {}
        return {k: float(v) * factor for k, v in self.targets.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "description": self.description,
            "targets": dict(self.targets),
            "start_turn": self.start_turn,
            "duration": self.duration,
            "shape": self.shape,
            "status": self.status,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    def to_engine_events(self) -> list[dict[str, Any]]:
        """
        Compile to the shared core.event_queue dict shape
        ({trigger_turn, event_type, params, origin, metadata}) so the injected shock is
        readable by both product surfaces and by existing trace tooling.
        """
        out: list[dict[str, Any]] = []
        for turn in self.active_turns():
            mags = self.magnitude_at(turn)
            if not mags:
                continue
            out.append({
                "trigger_turn": turn,
                "event_type": "event_sim_injection",
                "origin": self.id,
                "params": {
                    "effects": [
                        {"op": "displace_variable", "key": k, "value": v} for k, v in sorted(mags.items())
                    ]
                },
                "metadata": {"source": "event_definition", "status": self.status, "shape": self.shape},
            })
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventDefinition:
        shape = str(d.get("shape") or "step")
        if shape not in ("step", "ramp", "pulse"):
            shape = "step"
        return cls(
            id=str(d.get("id") or "event"),
            label=str(d.get("label") or d.get("id") or "event"),
            description=str(d.get("description") or ""),
            targets={str(k): float(v) for k, v in (d.get("targets") or {}).items()},
            start_turn=int(d.get("start_turn", 1)),
            duration=int(d.get("duration", 1)),
            shape=shape,  # type: ignore[arg-type]
            status=str(d.get("status") or "user_assumption"),  # type: ignore[arg-type]
            evidence=[Evidence.from_dict(e) for e in (d.get("evidence") or [])],
        )


@dataclass
class WorldBranch:
    """
    A fork of a world at a specific turn. Branches restore the same checkpoint, so two
    branches provably start from an identical state (tests/test_event_sim_branching.py).
    """

    branch_id: str
    parent_id: str | None
    fork_turn: int
    label: str = ""
    interventions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "parent_id": self.parent_id,
            "fork_turn": self.fork_turn,
            "label": self.label or self.branch_id,
            "interventions": [dict(i) for i in self.interventions],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorldBranch:
        return cls(
            branch_id=str(d["branch_id"]),
            parent_id=(str(d["parent_id"]) if d.get("parent_id") else None),
            fork_turn=int(d.get("fork_turn", 0)),
            label=str(d.get("label") or d["branch_id"]),
            interventions=[dict(i) for i in (d.get("interventions") or [])],
        )


@dataclass
class Trajectory:
    """
    A family of swept worlds that ended in the same qualitative outcome.

    Reported as counts of tested worlds ("18 of 27 tested worlds"), never as a
    probability — the sweep grid is a designed set of assumption combinations, not a
    sample from a calibrated distribution.
    """

    id: str
    label: str
    description: str = ""
    member_configs: list[dict[str, str]] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    critical_assumptions: list[str] = field(default_factory=list)
    failure_points: list[dict[str, Any]] = field(default_factory=list)
    representative: dict[str, Any] = field(default_factory=dict)

    @property
    def world_count(self) -> int:
        return len(self.member_configs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "world_count": self.world_count,
            "member_configs": [dict(c) for c in self.member_configs],
            "conditions": list(self.conditions),
            "critical_assumptions": list(self.critical_assumptions),
            "failure_points": [dict(f) for f in self.failure_points],
            "representative": dict(self.representative),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Trajectory:
        return cls(
            id=str(d["id"]),
            label=str(d.get("label") or d["id"]),
            description=str(d.get("description") or ""),
            member_configs=[dict(c) for c in (d.get("member_configs") or [])],
            conditions=_as_str_list(d.get("conditions")),
            critical_assumptions=_as_str_list(d.get("critical_assumptions")),
            failure_points=[dict(f) for f in (d.get("failure_points") or [])],
            representative=dict(d.get("representative") or {}),
        )


@dataclass
class ObservedMilestone:
    """
    A dated fact about *when* something happened, rather than a measured level.

    Added because the Yantian replay's most important finding was a timing error
    (-9 weeks), and a level-based envelope cannot test timing. Milestones let a replay be
    falsified by well-dated facts even when no dense numeric series exists — which, after
    two evidence hunts, is the normal situation rather than the exception.

    kind:
      'recovery_to_baseline'  first turn at/after the shock within `tolerance` of baseline
      'peak'                  turn of maximum departure from baseline
      'threshold_cross_up'    first turn the value reaches >= `threshold`
      'threshold_cross_down'  first turn the value falls to <= `threshold`
    """

    id: str
    variable: str
    kind: str
    observed_turn: int
    date: str = ""
    threshold: float | None = None
    tolerance: float = 0.05  # fraction of baseline, for recovery_to_baseline
    source: str = ""
    status: str = "observed"
    note: str = ""
    available_at: str = ""

    def is_scoreable(self) -> bool:
        return self.status == "observed" and self.observed_turn >= 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "variable": self.variable, "kind": self.kind,
            "observed_turn": self.observed_turn, "date": self.date,
            "threshold": self.threshold, "tolerance": self.tolerance,
            "source": self.source, "status": self.status, "note": self.note,
            "available_at": self.available_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservedMilestone:
        return cls(
            id=str(d["id"]),
            variable=str(d["variable"]),
            kind=str(d.get("kind") or "recovery_to_baseline"),
            observed_turn=int(d.get("observed_turn", 0)),
            date=str(d.get("date") or ""),
            threshold=(float(d["threshold"]) if d.get("threshold") is not None else None),
            tolerance=float(d.get("tolerance", 0.05)),
            source=str(d.get("source_id") or d.get("source") or ""),
            status=str(d.get("status") or "observed"),
            note=str(d.get("note") or ""),
            available_at=str(d.get("available_at") or ""),
        )


@dataclass
class HistoricalObservation:
    """
    One observed data point for historical replay evaluation. `status` must be 'observed'
    for the point to be scored — event_sim.historical.evaluation refuses to grade a
    simulation against assumed values.
    """

    variable: str
    turn: int
    value: float
    unit: str = ""
    date: str = ""
    source: str = ""
    status: str = "observed"  # 'observed' is scored; 'context' and weaker statuses are not
    note: str = ""
    #: When this value became publicly available. Distinct from `date`, which is the period
    #: the value describes. The gap between the two is where hindsight leakage hides.
    available_at: str = ""
    reporting_period: str = ""
    mapping_id: str = ""
    turn_assignment: str = ""

    def is_scoreable(self) -> bool:
        """Only directly observed measurements may be used to grade a replay."""
        return self.status == "observed" and self.turn >= 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "turn": self.turn,
            "value": self.value,
            "unit": self.unit,
            "date": self.date,
            "source": self.source,
            "status": self.status,
            "note": self.note,
            "available_at": self.available_at,
            "reporting_period": self.reporting_period,
            "mapping_id": self.mapping_id,
            "turn_assignment": self.turn_assignment,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HistoricalObservation:
        return cls(
            variable=str(d["variable"]),
            turn=int(d.get("turn", 0)),
            value=float(d.get("value", 0.0)),
            unit=str(d.get("unit") or ""),
            date=str(d.get("date") or ""),
            source=str(d.get("source_id") or d.get("source") or ""),
            status=str(d.get("status") or "observed"),
            note=str(d.get("note") or ""),
            available_at=str(d.get("available_at") or ""),
            reporting_period=str(d.get("reporting_period") or ""),
            mapping_id=str(d.get("mapping_id") or ""),
            turn_assignment=str(d.get("turn_assignment") or ""),
        )
