"""
MT5 Strategy Tester emulation ("Open prices only"), kept separate from the
research pipeline: it re-trades finished results the way the tester would,
so the equity curve can be compared with an MT5 report.
"""

from edge_research.mt5_backtest.config import MT5TesterConfig, load_mt5_config  # noqa: F401
from edge_research.mt5_backtest.engine import BacktestResult, run_mt5_backtest  # noqa: F401
from edge_research.mt5_backtest.signals import build_mask  # noqa: F401
