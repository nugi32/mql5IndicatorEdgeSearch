"""
edge_research.selection

Phase 7e of the pipeline: the final strategy selection gate that combines
every independent piece of evidence into one pass/fail decision for
whether a condition is promoted to MQL5 code generation.

See PROJECT_DIRECTION.md, section 4, for why this phase exists.
"""

from edge_research.selection.strategy_gate import GateThresholds, passes_strategy_gate

__all__ = [
    "GateThresholds",
    "passes_strategy_gate",
]
