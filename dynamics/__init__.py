"""
Deterministic propagation with edge_model adapters, delay/decay.
"""

from dynamics.propagation import (
    propagate_variable_changes,
    propagate_with_edge_models,
)

__all__ = ["propagate_variable_changes", "propagate_with_edge_models"]
