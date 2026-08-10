"""
Protocol-lesson registry.

Methodological debt: mistakes in how this project *tests* things, as opposed to mistakes in
what it models. They are recorded because a protocol flaw that is quietly fixed teaches
nothing and can silently recur, whereas one that is written down constrains the next design.

The governing rule of this registry: **a historical verdict is never retroactively changed.**
A lesson explains a past result; it does not rescore it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LESSON_STATUS = ("open", "resolved", "accepted_limitation")


@dataclass(frozen=True)
class ProtocolLesson:
    """One methodological error, its consequence, and the rule adopted because of it."""

    id: str
    issue: str
    consequence: str
    resolution: str
    rule: str
    affected: tuple[str, ...]
    status: str = "resolved"
    verdict_unchanged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "issue": self.issue, "consequence": self.consequence,
            "resolution": self.resolution, "rule": self.rule,
            "affected": list(self.affected), "status": self.status,
            "verdict_unchanged": self.verdict_unchanged,
        }


PROTOCOL_LESSONS: tuple[ProtocolLesson, ...] = (
    ProtocolLesson(
        id="mixed_causal_scope_aggregate",
        issue=(
            "The H1 in-sample experiment's primary gate aggregated a median across endpoints "
            "of different causal scope: Yantian's shipping_delay peak timing, which H1 "
            "causally controls, and Baltimore's port_capacity reopening milestone, which is "
            "externally imposed and which H1 structurally cannot move."
        ),
        consequence=(
            "A 4-turn improvement on the sensitive endpoint became a 1-turn movement in the "
            "aggregate, because with n=2 the median simply selected the frozen endpoint. The "
            "pre-registered threshold of 2 turns was therefore missed and the verdict was "
            "experimental_no_effect, despite every secondary metric improving substantially."
        ),
        resolution=(
            "Endpoints now carry an explicit causal_scope classification, fixed before "
            "results exist. Primary efficacy gates use h1_sensitive endpoints only; "
            "insensitive endpoints become a safety gate; uncertain endpoints are exploratory."
        ),
        rule=(
            "Aggregation requires shared causal scope AND shared metric semantics. Shared "
            "units are not shared meaning. Historical verdicts are never retroactively "
            "changed — the previous experiment remains experimental_no_effect."
        ),
        affected=("H1_EXPERIMENT_PROTOCOL.md", "H1_EXPERIMENT_RESULTS.md"),
        status="resolved",
        verdict_unchanged=True,
    ),
    ProtocolLesson(
        id="small_n_aggregate_fragility",
        issue=(
            "A median over two scored tests is decided entirely by whichever value is less "
            "extreme, so it cannot express an improvement confined to one of them."
        ),
        consequence=(
            "The aggregate was uninformative precisely where the experiment was most "
            "informative."
        ),
        resolution=(
            "With small n, report individual endpoint metrics rather than hiding them inside "
            "an aggregate."
        ),
        rule="Do not aggregate when n is small enough for the aggregate to be a selection.",
        affected=("H1_EXPERIMENT_RESULTS.md",),
        status="resolved",
        verdict_unchanged=True,
    ),
    ProtocolLesson(
        id="sensitivity_predicted_then_ignored",
        issue=(
            "The H1 protocol correctly predicted in advance that Baltimore's endpoint would "
            "be mechanically insensitive, and then still gated on a statistic that pooled it "
            "in."
        ),
        consequence=(
            "A known structural limitation was allowed to determine the formal verdict."
        ),
        resolution=(
            "A predicted-insensitive endpoint must be assigned to the safety gate at "
            "pre-registration time, not merely noted in prose."
        ),
        rule=(
            "If a protocol predicts an endpoint cannot move, that prediction must change the "
            "gate structure, not just the discussion."
        ),
        affected=("H1_EXPERIMENT_PROTOCOL.md",),
        status="resolved",
        verdict_unchanged=True,
    ),
    ProtocolLesson(
        id="heldout_blocked_by_data_access",
        issue=(
            "Held-out validation of H1 is blocked not by the absence of suitable data but by "
            "access: qualifying datasets are either commercial or, though free and official, "
            "unreachable from the execution environment."
        ),
        consequence=(
            "H1 cannot advance beyond experimental_no_effect, and the known defect cannot "
            "move beyond 'known', for reasons that are procurement rather than science."
        ),
        resolution=(
            "Recorded as an acquisition decision (EVENT3_DATA_DECISION.md) with the exact "
            "required fields, resolution and coverage, rather than as another search."
        ),
        rule=(
            "When a validation standard cannot be met, record what would meet it. Never "
            "weaken the standard until the available data happens to satisfy it."
        ),
        affected=("EVENT3_SEARCH_V2.md", "EVENT3_DATA_DECISION.md"),
        status="open",
        verdict_unchanged=True,
    ),
)

LESSON_BY_ID: dict[str, ProtocolLesson] = {lesson.id: lesson for lesson in PROTOCOL_LESSONS}


def registry_summary() -> list[dict[str, Any]]:
    """The registry, for reports and the API."""
    return [lesson.to_dict() for lesson in PROTOCOL_LESSONS]


def open_lessons() -> list[ProtocolLesson]:
    """Lessons that still constrain what the project can currently claim."""
    return [lesson for lesson in PROTOCOL_LESSONS if lesson.status == "open"]
