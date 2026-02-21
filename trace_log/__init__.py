"""
Action trace: separate from causal_links; full traceability.
"""

from trace_log.action_trace import (
    append_action_trace_entry,
    ActionTraceEntry,
)

__all__ = ["append_action_trace_entry", "ActionTraceEntry"]
