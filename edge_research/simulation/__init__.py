"""
edge_research.simulation

Phase 7c of the pipeline: event-driven, bar-by-bar trade simulation that
turns a discovered condition into a concrete, EA-realistic set of trade
outcomes (entry, stop loss, take profit, optional trailing stop, spread
and slippage cost), instead of relying on the fixed-horizon directional
probability produced by Phases 5-6 alone.

See PROJECT_DIRECTION.md, section 4, for why this phase exists.
"""

from edge_research.simulation.trade_simulator import (
    TradeSimConfig,
    TradeSimResult,
    infer_direction,
    simulate_condition,
)

__all__ = [
    "TradeSimConfig",
    "TradeSimResult",
    "infer_direction",
    "simulate_condition",
]
