"""
Governance: configurable PolicyRules, governance state, validate_delta (with optional modify), approve_meta_proposal.

Class diagram:
  PolicyRule
    - name: str
    - check(delta, world) -> (ok, reason)
    - modify(delta, world) -> Delta | None
    - run(delta, world) -> (ok, reason, modified_delta)
  Governance
    - policy_rules: list[PolicyRule]
    - strictness_level: int
    - validate_delta(delta, world) -> (ok, reasons, modified_delta)
    - approve_meta_proposal(meta_proposal, votes) -> bool
    - snapshot_state() -> dict
"""

from __future__ import annotations

import random
from typing import Any, Callable

from schemas.delta_schema import Delta


# Domain-agnostic: non-negative keys are determined dynamically from scenario/world state
# Variables that typically should not go negative (e.g., population, resources) can be specified
# in scenario governance config, or inferred from variable names containing keywords like "population", "resource", "count"


class PolicyRule:
    """Single rule: check(delta, world) -> (ok, reason); optional modify(delta, world) -> delta."""

    def __init__(
        self,
        name: str,
        check: Callable[[Delta, Any], tuple[bool, str]],
        *,
        modify: Callable[[Delta, Any], Delta] | None = None,
    ) -> None:
        self.name = name
        self.check = check
        self.modify = modify

    def run(self, delta: Delta, world: Any) -> tuple[bool, str, Delta | None]:
        """Run check; if not ok and modify is set, return (True, '', modified_delta). Else (ok, reason, None)."""
        ok, reason = self.check(delta, world)
        if ok:
            return True, "", None
        if self.modify is not None:
            modified = self.modify(delta, world)
            return True, "", modified
        return False, reason, None


def _default_non_negative_check(delta: Delta, world: Any) -> tuple[bool, str]:
    """Default: no negative values for variables that should remain non-negative (domain-agnostic)."""
    world_snapshot = world.snapshot() if hasattr(world, "snapshot") else {}
    global_state = world_snapshot.get("global_state", {}) or world_snapshot.get("variables", {}) or getattr(world, "global_state", {}) or getattr(world, "variables", {})
    
    # Domain-agnostic: infer non-negative keys from variable names
    # Variables containing these keywords are assumed to be non-negative
    non_negative_keywords = {"population", "count", "resource", "cash", "money", "fund", "stock", "inventory", "supply"}
    
    for key, value in (delta.numeric_updates or {}).items():
        # Check if variable name suggests it should be non-negative
        key_lower = key.lower()
        should_be_non_negative = any(keyword in key_lower for keyword in non_negative_keywords)
        
        if should_be_non_negative:
            current = global_state.get(key, 0)
            try:
                new_val = current + value if isinstance(value, (int, float)) else value
                if isinstance(new_val, (int, float)) and new_val < 0:
                    return False, f"{key} would become negative ({new_val})"
            except TypeError:
                return False, f"{key} has invalid update type"
    return True, ""


def _default_entity_refs_check(delta: Delta, world: Any) -> tuple[bool, str]:
    """Default: entity_updates reference existing or new entities."""
    world_snapshot = world.snapshot() if hasattr(world, "snapshot") else {}
    entities = world_snapshot.get("entities", {}) or getattr(world, "entities", {})
    new_ids = set(delta.new_entities or {})
    for eid in (delta.entity_updates or {}):
        if eid not in entities and eid not in new_ids:
            return False, f"entity_updates reference unknown entity: {eid}"
    return True, ""


def _auto_repair_tradeoff(governance_ref: Any) -> Callable[[Delta, Any], Delta]:
    """Auto-repair function: injects system cost variables, scales delta, adds stochastic noise."""
    
    def modify(delta: Delta, world: Any) -> Delta:
        # Get current strictness_level from governance instance
        strictness_level = governance_ref.strictness_level if hasattr(governance_ref, 'strictness_level') else 1
        """Auto-augment delta by injecting cost variables, scaling based on volatility, adding noise."""
        world_snapshot = world.snapshot() if hasattr(world, "snapshot") else {}
        global_state = world_snapshot.get("global_state", {}) or world_snapshot.get("variables", {}) or getattr(world, "global_state", {}) or getattr(world, "variables", {})
        
        numeric_updates = dict(delta.numeric_updates or {})
        original_numeric = dict(numeric_updates)
        
        # Scale repair intensity based on strictness_level
        repair_magnitude = 1.0 + (strictness_level * 0.2)
        noise_scale = strictness_level * 0.05
        
        # Detect violations
        has_single_variable = len(numeric_updates) == 1
        has_weak_delta = len(numeric_updates) < 2
        has_no_secondary_cost = len([v for v in numeric_updates.values() if isinstance(v, (int, float)) and v < 0]) == 0
        
        # Get available variables from world
        available_vars = list(global_state.keys()) if isinstance(global_state, dict) else []
        
        # Find cost-like variables (pressure, risk, stress, dissatisfaction, etc.)
        cost_vars = [
            v for v in available_vars 
            if isinstance(v, str) and any(
                keyword in v.lower() 
                for keyword in ["pressure", "risk", "stress", "strain", "dissatisfaction", "cost", "budget", "debt"]
            )
        ]
        
        # If no cost vars found, use any variable except the primary one
        if not cost_vars and available_vars:
            primary_vars = list(numeric_updates.keys())
            cost_vars = [v for v in available_vars if v not in primary_vars]
        
        # Auto-repair: inject system cost variables
        if has_single_variable or has_weak_delta:
            primary_var = next(iter(numeric_updates.keys())) if numeric_updates else None
            primary_value = numeric_updates.get(primary_var, 0.0) if primary_var else 0.0
            
            # Inject pressure (negative cost)
            if cost_vars:
                pressure_var = cost_vars[0]
                # Scale pressure based on primary effect magnitude
                pressure_magnitude = abs(primary_value) * 0.3 * repair_magnitude if isinstance(primary_value, (int, float)) else 3.0 * repair_magnitude
                numeric_updates[pressure_var] = numeric_updates.get(pressure_var, 0.0) + pressure_magnitude
            
            # Inject risk if we have another cost variable
            if len(cost_vars) > 1:
                risk_var = cost_vars[1]
                risk_magnitude = abs(primary_value) * 0.2 * repair_magnitude if isinstance(primary_value, (int, float)) else 2.0 * repair_magnitude
                numeric_updates[risk_var] = numeric_updates.get(risk_var, 0.0) + risk_magnitude
        
        # If still no secondary cost, add one
        if has_no_secondary_cost and numeric_updates:
            positive_vars = [k for k, v in numeric_updates.items() if isinstance(v, (int, float)) and v > 0]
            if positive_vars and cost_vars:
                cost_var = cost_vars[0]
                # Add cost proportional to largest positive change
                max_positive = max(abs(v) for k, v in numeric_updates.items() if isinstance(v, (int, float)) and v > 0)
                cost_magnitude = max_positive * 0.25 * repair_magnitude
                numeric_updates[cost_var] = numeric_updates.get(cost_var, 0.0) + cost_magnitude
        
        # Add stochastic noise scaled by strictness
        if noise_scale > 0:
            for var in numeric_updates:
                if isinstance(numeric_updates[var], (int, float)):
                    noise = random.gauss(0, abs(numeric_updates[var]) * noise_scale)
                    numeric_updates[var] = numeric_updates[var] + noise
        
        # Scale delta based on volatility (if we can compute it)
        if len(numeric_updates) >= 2:
            # Scale all values by repair_magnitude to increase intensity
            for var in numeric_updates:
                if isinstance(numeric_updates[var], (int, float)):
                    # Only scale if it's a new injection (not original)
                    if var not in original_numeric:
                        numeric_updates[var] = numeric_updates[var] * repair_magnitude
        
        # Create new delta with repaired numeric_updates
        return Delta(
            numeric_updates=numeric_updates,
            entity_updates=dict(delta.entity_updates or {}),
            new_entities=dict(delta.new_entities or {}),
            relation_updates=list(delta.relation_updates or []),
            meta_proposals=list(delta.meta_proposals or []),
            rationale=delta.rationale + " [auto-repaired: injected tradeoffs]",
            effects_duration=delta.effects_duration,
            mitigation=delta.mitigation,
            delay_turns=delta.delay_turns,
            probability=delta.probability,
        )
    
    return modify


def _infer_meta_type(meta_proposal: dict[str, Any]) -> str:
    """Infer meta proposal type from structure."""
    if "name" in meta_proposal and "parameters_schema" in meta_proposal:
        return "new_action"
    if "name" in meta_proposal and "scale" in meta_proposal:
        return "new_variable"
    if "from_key" in meta_proposal and "to_key" in meta_proposal:
        return "new_causal_link"
    if "name" in meta_proposal and "trigger_conditions" in meta_proposal:
        return "new_event"
    return "unknown"


def _check_meta_limits(meta_proposal: dict[str, Any], limits: dict[str, Any]) -> bool:
    """Check if meta proposal is within rate limits. Returns True if allowed."""
    prop_type = meta_proposal.get("type") or _infer_meta_type(meta_proposal)
    count = limits.get("new_variables_count", 0) if prop_type == "new_variable" else (
        limits.get("new_actions_count", 0) if prop_type == "new_action" else 0
    )
    max_per_window = limits.get("max_new_variables_per_N_turns", 2) if prop_type == "new_variable" else (
        limits.get("max_new_actions_per_N_turns", 2) if prop_type == "new_action" else 999
    )
    return count < max_per_window


def _tradeoff_check(require_tradeoffs: bool, governance_ref: Any) -> tuple[Callable[[Delta, Any], tuple[bool, str]], Callable[[Delta, Any], Delta] | None]:
    """Every action must affect at least two system variables (primary + cost/consequence). Returns (check, modify)."""

    def check(delta: Delta, world: Any) -> tuple[bool, str]:
        if not require_tradeoffs:
            return True, ""
        nu = delta.numeric_updates or {}
        if len(nu) < 2:
            return False, "delta must affect at least two variables (primary effect and one cost or consequence)"
        return True, ""

    modify_func = _auto_repair_tradeoff(governance_ref) if require_tradeoffs else None
    return check, modify_func


def default_policy_rules(
    *,
    require_tradeoffs: bool = True,
    governance_ref: Any = None,
) -> list[PolicyRule]:
    """Default rules: no_negative_cash (and resources), entity_refs, tradeoff (when require_tradeoffs)."""
    def no_negative_check(delta: Delta, world: Any) -> tuple[bool, str]:
        return _default_non_negative_check(delta, world)

    def entity_refs_check(delta: Delta, world: Any) -> tuple[bool, str]:
        return _default_entity_refs_check(delta, world)

    rules = [
        PolicyRule("no_negative_resources", no_negative_check),
        PolicyRule("entity_refs", entity_refs_check),
    ]
    if require_tradeoffs and governance_ref is not None:
        tradeoff_check, tradeoff_modify = _tradeoff_check(True, governance_ref)
        rules.append(PolicyRule("require_tradeoffs", tradeoff_check, modify=tradeoff_modify))
    return rules


class Governance:
    """Validates deltas via configurable policy rules; optional delta modification; approves meta-proposals."""

    def __init__(
        self,
        *,
        auto_approve_max_agents: int = 1,
        policy_rules: list[PolicyRule] | None = None,
        strictness_level: int = 1,
        require_tradeoffs: bool = True,
    ) -> None:
        self.auto_approve_max_agents = auto_approve_max_agents
        self.require_tradeoffs = require_tradeoffs
        self.strictness_level = strictness_level
        self._disabled_rules = set()
        # Create policy rules with reference to self so modify functions can access current strictness_level
        self.policy_rules = list(
            policy_rules or default_policy_rules(require_tradeoffs=require_tradeoffs, governance_ref=self)
        )

    def add_policy_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule at runtime."""
        self.policy_rules.append(rule)

    def disable_rule(self, name: str) -> None:
        """Disable a rule by name; it will be skipped in validate_delta."""
        self._disabled_rules.add(name)

    def enable_rule(self, name: str) -> None:
        """Re-enable a rule by name."""
        self._disabled_rules.discard(name)

    def set_strictness_level(self, level: int) -> None:
        """Set strictness level at runtime."""
        self.strictness_level = int(level)

    def update_policy_rules(self, rules: list[PolicyRule]) -> None:
        """Replace policy rules with a new list."""
        self.policy_rules = list(rules)

    def validate_delta(self, delta: Delta, world: Any) -> tuple[bool, list[str], Delta | None]:
        """
        Run all policy rules. Returns (ok, warnings, modified_delta).
        ALWAYS returns success (True) with warnings indicating repairs made.
        Never blocks execution completely - auto-repairs violations.
        """
        warnings: list[str] = []
        current = delta
        repairs_made = False
        
        for rule in self.policy_rules:
            if rule.name in self._disabled_rules:
                continue
            if not self.require_tradeoffs and rule.name == "require_tradeoffs":
                continue

            # Scale rule application based on strictness_level
            # Higher strictness = more intense repairs, but never skip completely
            ok, reason, modified = rule.run(current, world)
            
            if not ok:
                # Rule failed - if it has modify function, it will auto-repair
                # Otherwise, scale the check based on strictness
                if rule.modify is not None:
                    # Auto-repair will happen in rule.run()
                    warnings.append(f"{rule.name}: {reason} [auto-repaired]")
                    repairs_made = True
                else:
                    # For rules without modify, scale strictness
                    # At strictness 0, warnings only; at higher strictness, more warnings
                    if self.strictness_level > 0:
                        warnings.append(f"{rule.name}: {reason} [scaled by strictness {self.strictness_level}]")
            elif modified is not None:
                # Rule modified the delta
                current = modified
                repairs_made = True
                warnings.append(f"{rule.name}: delta was auto-repaired")
        
        # ALWAYS return success - never reject completely
        # Warnings indicate what repairs were made
        return True, warnings, current if current is not delta else None

    def approve_meta_proposal(
        self,
        meta_proposal: dict[str, Any],
        agent_votes: list[bool],
        *,
        meta_limits: dict[str, Any] | None = None,
        auto_approve_meta_types: list[str] | None = None,
    ) -> bool:
        """
        Majority approve, or auto-approve if <= auto_approve_max_agents.
        Handles: governance_change, new_action, new_variable, new_causal_link, new_event.
        meta_limits: {new_variables_count, new_actions_count, turn, turns_window} for rate limiting.
        auto_approve_meta_types: if proposal type in list, auto-approve when agents <= N.
        """
        if meta_limits and not _check_meta_limits(meta_proposal, meta_limits):
            return False
        if not agent_votes:
            return self.auto_approve_max_agents >= 1
        if len(agent_votes) <= self.auto_approve_max_agents:
            prop_type = meta_proposal.get("type") or _infer_meta_type(meta_proposal)
            if auto_approve_meta_types and prop_type in auto_approve_meta_types:
                return True
            return True
        if meta_proposal.get("type") == "governance_change":
            return sum(agent_votes) > len(agent_votes) / 2
        return sum(agent_votes) > len(agent_votes) / 2

    def apply_governance_change(self, change: dict[str, Any]) -> None:
        """Apply a proposed governance change (e.g. strictness_level, add/remove rule)."""
        if "strictness_level" in change:
            self.strictness_level = int(change["strictness_level"])
        if "policy_rules" in change and isinstance(change["policy_rules"], list):
            pass  # Could replace or extend policy_rules by name

    def intervene_for_stability(self, world_snapshot: Any, ssi: float) -> None:
        """
        Called when System Stability Index (SSI) is below threshold.
        Applies stricter governance: increase strictness_level and optionally
        tighter hard_clips for the next delta validation.
        """
        self.set_strictness_level(min(5, self.strictness_level + 1))

    def snapshot_state(self) -> dict[str, Any]:
        """Return governance state for snapshot."""
        return {
            "strictness_level": self.strictness_level,
            "rule_names": [r.name for r in self.policy_rules],
            "disabled_rules": list(self._disabled_rules),
        }
