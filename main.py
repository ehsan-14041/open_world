#!/usr/bin/env python3
"""
Open World Engine – CLI entry.
Load demo scenario, build SimulationLoop, run N steps. Option --dry-run disables LLM.
Usage: python main.py [--steps N] [--dry-run] [--snapshot path]
"""

import argparse
import json
import os
import sys

# Ensure project root (open_world_engine) is on path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.settings import SCENARIO_PATH, DRY_RUN, SNAPSHOT_PATH
from schemas.scenario_schema import normalize_scenario, validate_scenario
from simulation.loop import SimulationLoop, load_scenario
from core.narrative_builder import (
    build_narrative,
    build_structured_summary,
    prepare_final_output_with_role_names,
)
from core.phase_detector import detect_phases, build_phase_summary_facts
from core.registry_validator import validate_registry_health
from core.narrative_firewall import replace_placeholders
from core.llm_client import call_llm
from core.scenario_analysis_output import build_scenario_analysis_output
from summarization.facts import build_narrative_facts


def main() -> int:
    parser = argparse.ArgumentParser(description="Open World Engine – multi-agent social simulation")
    parser.add_argument("--steps", type=int, default=5, help="Number of simulation steps (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Disable LLM; use rule-based behavior only")
    parser.add_argument("--snapshot", type=str, default=None, help="Path to save final world snapshot JSON")
    parser.add_argument("--scenario", type=str, default=None, help="Path to scenario JSON (default: config/scenarios/demo_scenario.json)")
    parser.add_argument("--scenario-text", type=str, default=None, help="Free-form scenario text; parsed to JSON (LLM) then run (scenario-to-simulation pipeline)")
    parser.add_argument("--use-llm-for-agents", action="store_true", help="With --scenario-text: generate agent definitions (personality, initial_variables) via LLM")
    parser.add_argument("--narrative", action="store_true", help="Print final narrative built from provenance and world state")
    parser.add_argument("--summary", action="store_true", help="Print only the structured one-paragraph world summary")
    args = parser.parse_args()

    scenario_path = args.scenario or SCENARIO_PATH
    snapshot_path = args.snapshot or SNAPSHOT_PATH
    dry_run = args.dry_run or DRY_RUN

    # LLM Integration: optional scenario-from-text path (scenario-to-simulation pipeline)
    scenario_data = None
    if args.scenario_text:
        from scenario_parser import parse_scenario_text
        from core.agent_generator import generate_agents_from_scenario
        try:
            scenario_data = parse_scenario_text(args.scenario_text.strip(), use_llm=not dry_run)
            errors = validate_scenario(scenario_data)
            if errors:
                print("Scenario validation failed:", "; ".join(errors), file=sys.stderr)
                return 1
            scenario_data = normalize_scenario(scenario_data)
            if args.use_llm_for_agents and not dry_run:
                def llm_wrapper(prompt: str, system: str | None = None, *, as_json: bool = False):
                    return call_llm(prompt, system=system, as_json=as_json)
                scenario_data["initial_agents"] = generate_agents_from_scenario(scenario_data, llm_wrapper)
                scenario_data = normalize_scenario(scenario_data)
        except ValueError as e:
            print("Scenario parse failed:", e, file=sys.stderr)
            return 1

    if args.summary:
        loop = SimulationLoop(
            scenario_path=None if scenario_data else scenario_path,
            scenario_data=scenario_data,
            dry_run=dry_run,
            snapshot_path=snapshot_path,
        )
        result = loop.run(
            steps=args.steps,
            snapshot_out_path=snapshot_path,
            return_provenance=True,
            silent=True,
        )
        if isinstance(result, dict):
            scenario = normalize_scenario(scenario_data or load_scenario(scenario_path))
            initial_state = scenario.get("initial_state") or {}
            agents = [
                {"name": a.name, "role": getattr(a, "role", a.name), "objectives": getattr(a, "objectives", {})}
                for a in loop.agents
            ]
            trace = result.get("provenance", [])
            final_state = result.get("final", result)
            turn_records = [p.get("turn_record") for p in trace if p.get("turn_record")]
            phases = detect_phases(turn_records)
            phase_summary_facts = build_phase_summary_facts(turn_records, phases)
            registry_status = validate_registry_health(scenario)
            paragraph = build_structured_summary(
                trace,
                initial_state,
                final_state,
                agents,
                use_llm=not dry_run,
                llm_callback=lambda prompt, system: call_llm(prompt, system=system),
                scenario=scenario,
            )
            print(paragraph)
            if phase_summary_facts:
                print("\n=== Phase summary facts ===")
                for item in phase_summary_facts[:5]:
                    f = item.get("fact", "") if isinstance(item, dict) else str(item)
                    tr = item.get("turn_record", {}) if isinstance(item, dict) else {}
                    resolved = replace_placeholders(f, tr, tr.get("turn", 0)) if tr else f
                    print(" -", resolved)
        return 0

    loop = SimulationLoop(
        scenario_path=None if scenario_data else scenario_path,
        scenario_data=scenario_data,
        dry_run=dry_run,
        snapshot_path=snapshot_path,
    )
    print("Running Open World Engine")
    print(f"  steps={args.steps} dry_run={dry_run} scenario={scenario_path or '(from text)'}")
    result = loop.run(
        steps=args.steps,
        snapshot_out_path=snapshot_path,
        return_turns=args.narrative,
        return_provenance=args.narrative,
    )
    if args.narrative and isinstance(result, dict):
        final = result.get("final", result)
        trace = result.get("provenance", [])
        agents = [
            {"name": a.name, "role": getattr(a, "role", a.name), "objectives": getattr(a, "objectives", {})}
            for a in loop.agents
        ]
        scenario = normalize_scenario(scenario_data or load_scenario(scenario_path)) if scenario_data or scenario_path else {}
        turn_records = [p.get("turn_record") for p in trace if p.get("turn_record")]
        phases = detect_phases(turn_records)
        phase_summary_facts = build_phase_summary_facts(turn_records, phases)
        registry_status = validate_registry_health(scenario)
        final_display = prepare_final_output_with_role_names(final, agents, trace, scenario)
        final_display["registry_status"] = registry_status
        final_display["phase_summary_facts"] = [x.get("fact", x) if isinstance(x, dict) else x for x in phase_summary_facts]
        final_display["action_definitions"] = getattr(loop, "_action_definitions", {})
        print("")
        print("=== Final world state ===")
        print(json.dumps(final_display, indent=2))
        print("")
        print("=== Simulation narrative ===")
        narrative = build_narrative(
            trace,
            final,
            use_llm=not dry_run,
            llm_callback=lambda prompt, system: call_llm(prompt, system=system),
            agents=agents,
            scenario=scenario,
        )
        print(narrative)
        state_specs = scenario.get("variable_specs") or scenario.get("state_spec") or {}
        narrative_facts = build_narrative_facts(trace, final, agents=agents, scenario=scenario, state_specs=state_specs)
        action_definitions = getattr(loop, "_action_definitions", {})
        analysis = build_scenario_analysis_output(
            result,
            scenario=scenario,
            agents=agents,
            action_definitions=action_definitions,
            facts=narrative_facts,
            allow_numbers=False,
        )
        print("")
        print("=== Logic Core (JSON) ===")
        print(json.dumps(analysis["logic_core"], indent=2))
        print("")
        print("=== Executive Summary ===")
        for key in ("paragraph_1_what_happened", "paragraph_2_why_causal", "paragraph_3_critical_risk_next_turn"):
            title = key.replace("_", " ").title()
            print(f"--- {title} ---")
            print(analysis["executive_summary"].get(key, ""))
            print("")
    else:
        final = result.get("final", result) if isinstance(result, dict) else result
        if loop.agents and isinstance(final, dict) and final.get("agents_state"):
            agents = [
                {"name": a.name, "role": getattr(a, "role", a.name), "objectives": getattr(a, "objectives", {})}
                for a in loop.agents
            ]
            trace = result.get("provenance", []) if isinstance(result, dict) else []
            scenario = normalize_scenario(scenario_data or load_scenario(scenario_path)) if scenario_data or scenario_path else {}
            final = prepare_final_output_with_role_names(final, agents, trace, scenario)
        print("")
        print("=== Final world state ===")
        print(json.dumps(final, indent=2))
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
