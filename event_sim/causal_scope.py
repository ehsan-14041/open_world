"""
Causal scope of a hypothesis, and endpoint classification.

The H1 in-sample experiment failed its formal gate because the primary aggregate pooled an
endpoint H1 causally controls (`shipping_delay` peak timing) with one it does not
(`port_capacity` reopening date, externally imposed). The improvement on the first was
diluted by the structural immobility of the second.

The fix is not to re-score that experiment — its verdict stands — but to make causal scope
an explicit, checkable property of every endpoint *before* results exist:

    h1_sensitive     inside the hypothesis's causal scope   -> primary efficacy gate
    h1_insensitive   outside it                             -> safety gate only
    uncertain_scope  genuinely unclear                      -> exploratory, never decisive

Sensitivity is derived from the actual topology where possible, not asserted, so an endpoint
cannot be quietly reclassified to suit a result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from event_sim.schemas import WorldSlice

SCOPE_CLASSES = ("h1_sensitive", "h1_insensitive", "uncertain_scope")

#: Roles an endpoint can play in a held-out verdict.
SCOPE_ROLES: dict[str, str] = {
    "h1_sensitive": "primary efficacy gate",
    "h1_insensitive": "safety gate only — must NOT move materially",
    "uncertain_scope": "exploratory — reported, never decisive",
}


class ScopeError(ValueError):
    """Raised on an invalid or post-hoc endpoint classification."""


@dataclass(frozen=True)
class CausalScope:
    """
    A hypothesis's declared causal reach.

    `direct` is what the mechanism itself is; `downstream` is what it can move through the
    graph; `outside` is what it structurally cannot move and must not be allowed to dilute
    the primary gate.
    """

    hypothesis: str
    direct: tuple[str, ...]
    downstream: tuple[str, ...]
    outside: tuple[str, ...]
    note: str = ""

    def classify_variable(self, variable: str) -> str:
        if variable in self.direct or variable in self.downstream:
            return "h1_sensitive"
        if variable in self.outside:
            return "h1_insensitive"
        return "uncertain_scope"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "direct": list(self.direct),
            "downstream": list(self.downstream),
            "outside": list(self.outside),
            "note": self.note,
        }


#: H1's causal scope, declared before Event #3 was searched for.
H1_SCOPE = CausalScope(
    hypothesis="H1",
    direct=("vessel_queue",),
    downstream=("shipping_delay",),
    outside=("port_capacity",),
    note=(
        "port_capacity is OUTSIDE scope: in every replay it is either injected as the event "
        "or relaxes back on the baseline's own dynamics, which H1 does not touch. The queue "
        "sits downstream of it. Variables further downstream than shipping_delay "
        "(inventory_availability, service_level, ...) are left UNCERTAIN rather than claimed: "
        "H1 can reach them through the graph, but no replay so far has an observation for "
        "them, so their sensitivity is untested."
    ),
)


def derive_downstream(slice_: WorldSlice, roots: Iterable[str]) -> set[str]:
    """
    Variables reachable from `roots` through the slice's edges.

    Used to CHECK a declared scope against the actual topology, so a scope claim cannot
    drift away from the model it describes.
    """
    reachable: set[str] = set()
    frontier = list(roots)
    edges_from: dict[str, list[str]] = {}
    for edge in slice_.edges:
        edges_from.setdefault(edge.source, []).append(edge.target)
    while frontier:
        current = frontier.pop()
        for target in edges_from.get(current, []):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    return reachable


def verify_scope(scope: CausalScope, slice_: WorldSlice) -> list[str]:
    """
    Check a declared scope against the topology. Returns problems; empty means consistent.

    Catches two mistakes: claiming something is downstream when no path exists, and
    declaring something outside scope when the graph says the mechanism can reach it.
    """
    problems: list[str] = []
    reachable = derive_downstream(slice_, scope.direct)
    for variable in scope.downstream:
        if variable not in reachable:
            problems.append(
                f"{scope.hypothesis}: '{variable}' is declared downstream of "
                f"{list(scope.direct)} but no causal path reaches it"
            )
    for variable in scope.outside:
        if variable in reachable:
            problems.append(
                f"{scope.hypothesis}: '{variable}' is declared OUTSIDE scope but is reachable "
                f"from {list(scope.direct)} — an out-of-scope claim must be structural"
            )
    return problems


@dataclass
class Endpoint:
    """
    One evaluation endpoint, classified before any result exists.

    `frozen_at` records when the classification was fixed. `classify_endpoints` refuses to
    produce a classification that disagrees with the declared scope, so an endpoint cannot
    be moved between gates after the fact.
    """

    id: str
    variable: str
    metric: str
    scope_class: str
    role: str = ""
    observed: bool = True
    note: str = ""
    frozen_at: str = ""

    def is_primary(self) -> bool:
        return self.scope_class == "h1_sensitive"

    def is_safety(self) -> bool:
        return self.scope_class == "h1_insensitive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "variable": self.variable, "metric": self.metric,
            "scope_class": self.scope_class, "role": self.role or SCOPE_ROLES[self.scope_class],
            "observed": self.observed, "note": self.note, "frozen_at": self.frozen_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Endpoint:
        scope_class = str(d.get("scope_class") or "uncertain_scope")
        if scope_class not in SCOPE_CLASSES:
            raise ScopeError(f"endpoint {d.get('id')!r}: unknown scope class {scope_class!r}")
        return cls(
            id=str(d["id"]), variable=str(d["variable"]), metric=str(d.get("metric") or ""),
            scope_class=scope_class, role=str(d.get("role") or ""),
            observed=bool(d.get("observed", True)), note=str(d.get("note") or ""),
            frozen_at=str(d.get("frozen_at") or ""),
        )


def classify_endpoints(endpoints: Sequence[Endpoint], scope: CausalScope) -> list[str]:
    """
    Verify each endpoint's stored classification against the declared scope.

    Returns disagreements. A disagreement is an error, not something to silently correct:
    it means either the scope or the classification was changed after the fact.
    """
    problems: list[str] = []
    for endpoint in endpoints:
        expected = scope.classify_variable(endpoint.variable)
        if endpoint.scope_class != expected:
            problems.append(
                f"endpoint {endpoint.id!r} on '{endpoint.variable}' is classified "
                f"{endpoint.scope_class!r} but {scope.hypothesis}'s declared scope implies "
                f"{expected!r}"
            )
        if not endpoint.frozen_at:
            problems.append(f"endpoint {endpoint.id!r} records no freeze timestamp")
    return problems


def split_by_role(endpoints: Sequence[Endpoint]) -> dict[str, list[Endpoint]]:
    """Group endpoints into the three gates."""
    out: dict[str, list[Endpoint]] = {k: [] for k in SCOPE_CLASSES}
    for endpoint in endpoints:
        out[endpoint.scope_class].append(endpoint)
    return out


def assert_aggregatable(endpoints: Sequence[Endpoint]) -> None:
    """
    Refuse to aggregate endpoints that are not comparable.

    Aggregation requires the same causal scope AND the same metric semantics. Two numbers
    both measured "in turns" are not therefore poolable — that is exactly the mistake the
    previous experiment's primary gate made.
    """
    if not endpoints:
        return
    scopes = {e.scope_class for e in endpoints}
    if len(scopes) > 1:
        raise ScopeError(
            f"cannot aggregate endpoints across causal scopes {sorted(scopes)}: a metric "
            f"H1 cannot move would dilute one it can"
        )
    metrics = {e.metric for e in endpoints}
    if len(metrics) > 1:
        raise ScopeError(
            f"cannot aggregate across different metric semantics {sorted(metrics)}: shared "
            f"units are not shared meaning"
        )
