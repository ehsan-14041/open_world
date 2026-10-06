"""
Decision Journal — file-backed persistence for analyzed decisions.

Each decision is stored as a single JSON file under output/decisions/<id>.json.
Users can annotate outcomes later (what actually happened, driver accuracy),
creating a learning loop that makes the product defensible over time.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

_JOURNAL_DIR = Path(__file__).resolve().parent.parent / "output" / "decisions"


def _journal_dir() -> Path:
    _JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    return _JOURNAL_DIR


def _decision_path(decision_id: str) -> Path:
    return _journal_dir() / f"{decision_id}.json"


CHECK_IN_DAYS = 30


def save_decision(
    decision_input: dict[str, Any],
    brief: dict[str, Any],
    snapshot_summary: dict[str, Any] | None = None,
    decision_id: str | None = None,
    ops_profile: dict[str, Any] | None = None,
    decision_template_id: str | None = None,
    outcomes: dict[str, Any] | None = None,
) -> str:
    """
    Persist a decision record. Returns the decision_id.

    Args:
        decision_input: normalized DecisionInput dict (move, actors, …).
        brief: the built decision brief dict.
        snapshot_summary: optional lightweight snapshot (derived vars only).
        decision_id: supply to overwrite an existing record; generated otherwise.
        ops_profile: optional operations profile summary for enterprise context.
        decision_template_id: optional decision template id from ops_decisions.json.
    """
    did = decision_id or str(uuid.uuid4())[:8]
    now = time.time()
    record = {
        "id": did,
        "created_at": now,
        "check_in_due_at": now + CHECK_IN_DAYS * 86400,
        "decision_input": decision_input or {},
        "brief": brief or {},
        "outcomes": outcomes or {},
        "snapshot_summary": snapshot_summary or {},
        "ops_profile": ops_profile or {},
        "decision_template_id": decision_template_id or "",
        "annotation": None,
    }
    path = _decision_path(did)
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logging.warning("decision_journal.save_decision failed: %s", e)
    return did


def get_decision(decision_id: str) -> dict[str, Any] | None:
    """Return the decision record, or None if not found."""
    path = _decision_path(decision_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logging.warning("decision_journal.get_decision(%s) failed: %s", decision_id, e)
        return None


def list_decisions(limit: int = 50) -> list[dict[str, Any]]:
    """
    Return a list of decision summaries (id, created_at, move, outcome, annotation).
    Sorted newest-first.
    """
    dir_ = _journal_dir()
    files = sorted(dir_.glob("*.json"), key=os.path.getmtime, reverse=True)
    summaries: list[dict[str, Any]] = []
    for f in files[:limit]:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            di = rec.get("decision_input") or {}
            brief = rec.get("brief") or {}
            op = rec.get("ops_profile") or {}
            check_in_due = rec.get("check_in_due_at")
            annotated = rec.get("annotation") is not None
            needs_check_in = (
                bool(check_in_due)
                and time.time() >= float(check_in_due)
                and not annotated
            )
            oc = rec.get("outcomes") or {}
            summaries.append({
                "id": rec.get("id"),
                "created_at": rec.get("created_at"),
                "check_in_due_at": check_in_due,
                "needs_check_in": needs_check_in,
                "move": di.get("move") or oc.get("decision_label") or "",
                "horizon_months": di.get("horizon_months"),
                "outcome": brief.get("outcome") or oc.get("one_line_recommendation") or "",
                "confidence": (brief.get("confidence") or {}).get("level") or "",
                "site_name": op.get("site_name") or "",
                "business_unit_type": op.get("business_unit_type") or "",
                "decision_template_id": rec.get("decision_template_id") or "",
                "annotation": rec.get("annotation"),
            })
        except Exception:
            continue
    return summaries


def annotate_outcome(
    decision_id: str,
    what_actually_happened: str,
    driver_accuracy: str | None = None,
) -> bool:
    """
    Add or update a user annotation on an existing decision record.
    Returns True on success, False if record not found.

    Args:
        decision_id: the decision to annotate.
        what_actually_happened: free-text description of actual outcome.
        driver_accuracy: optional user assessment ('accurate', 'partial', 'wrong').
    """
    record = get_decision(decision_id)
    if record is None:
        return False
    record["annotation"] = {
        "annotated_at": time.time(),
        "what_actually_happened": (what_actually_happened or "").strip(),
        "driver_accuracy": (driver_accuracy or "").strip() or None,
    }
    path = _decision_path(decision_id)
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logging.warning("decision_journal.annotate_outcome(%s) failed: %s", decision_id, e)
        return False
