"""
Make the research pipeline itself behave like the MT5 Strategy Tester.

The per-timeframe settings in config/MT5_TESTER/<SYMBOL>/<TF>.yaml are copied
into the pipeline config before any phase runs:

* ``spread_pips`` / ``slippage_pips`` are replaced by the tester's spread and
  slippage, so every cost estimate (Phase 5-6, the Phase 6b pre-filter, the
  Phase 7c simulation) uses the same numbers;
* ``sim_mt5`` switches the Phase 7c trade simulation to Open-prices-only
  rules (see TradeSimConfig.mt5_mode): fills at bar opens, spread paid by the
  side that closes at Ask, one position at a time.

Without a config file for the symbol/timeframe, or with ``enabled=False``
(``--legacy-sim``), the pipeline config is returned unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from edge_research.mt5_backtest.config import DEFAULT_CONFIG_ROOT, MT5TesterConfig, load_mt5_config

logger = logging.getLogger(__name__)


def mt5_pipeline_overrides(cfg: MT5TesterConfig, pip_value: float) -> dict:
    """Pipeline-config keys that express ``cfg`` in the pipeline's own units (pips of ``pip_value``)."""
    if cfg.max_open_positions != 1:
        logger.warning(
            f"max_open_positions={cfg.max_open_positions}: the pipeline simulation always keeps one "
            f"position at a time; only the post-run backtest honours more than one."
        )
    return {
        "spread_pips": cfg.spread_price / pip_value,
        # TradeSimConfig.slippage_price_units is the round-trip total (half per fill).
        "slippage_pips": 2.0 * cfg.slippage_price / pip_value,
        "sim_mt5": {
            "exit_bar_offset": cfg.exit_bar_offset,
            "reenter_on_exit_bar": cfg.reenter_on_exit_bar,
            "spread_points": cfg.spread_points,
        },
    }


def link_mt5_settings(
    pipeline_config: dict,
    symbol: str,
    timeframe: str,
    config_root: Optional[str | Path] = None,
    enabled: bool = True,
) -> dict:
    """Return a copy of ``pipeline_config`` with the MT5 tester behaviour applied (or the original if off/unavailable)."""
    if not enabled:
        logger.info("Phase 7c simulation: legacy model (--legacy-sim)")
        return pipeline_config
    try:
        cfg = load_mt5_config(config_root or DEFAULT_CONFIG_ROOT, symbol, timeframe)
    except FileNotFoundError as exc:
        logger.warning(f"{exc} Falling back to the legacy simulation for this run.")
        return pipeline_config
    pip_value = float(pipeline_config.get("pip_value", 0.0001))
    merged = dict(pipeline_config)
    merged.update(mt5_pipeline_overrides(cfg, pip_value))
    logger.info(
        f"Phase 7c simulation: MT5 Open-prices-only behaviour, {symbol} {timeframe}, "
        f"spread {cfg.spread_points:g} points, exit bar offset {cfg.exit_bar_offset}, "
        f"one position at a time"
    )
    return merged
