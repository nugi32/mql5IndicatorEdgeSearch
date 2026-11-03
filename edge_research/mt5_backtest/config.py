"""
Per-symbol / per-timeframe settings of the MT5 tester emulation.

One YAML file per timeframe (``config/MT5_TESTER/<SYMBOL>/<TF>.yaml``)
because the spread, and therefore the cost of a trade, differs between
timeframes. If ``<TF>.yaml`` is missing, ``<SYMBOL>/_default.yaml`` is used;
if that is missing too, loading fails on purpose (a silent default spread
would quietly produce wrong results).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Repo root / config / MT5_TESTER, independent of the current working directory.
DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config" / "MT5_TESTER"
VALID_MODELLING = ("open_prices_only",)
VALID_DELAY = ("none", "random", "fixed")


@dataclass
class MT5TesterConfig:
    """Everything the emulator needs. Units are noted per field."""

    # --- Tester settings (what you pick in the MT5 Strategy Tester window) ---
    modelling: str = "open_prices_only"   # only mode implemented
    # MT5 docs: "The Random Delay execution mode is not allowed" with Open prices
    # only. The value is kept so the config mirrors the tester window, but it
    # has no effect in this mode (a warning is logged when it is not "none").
    execution_delay: str = "none"         # none | random | fixed
    forward: str = "none"                 # "none" = whole period is the backtest

    # --- Instrument ---
    point: float = 0.01                   # price value of one point (XAUUSD: 0.01)
    digits: int = 2                       # price digits, used to round fills
    contract_size: float = 100.0          # units per 1.0 lot (XAUUSD: 100 oz)
    lots: float = 0.1
    initial_deposit: float = 10000.0

    # --- Costs ---
    spread_points: float = 30.0           # fixed spread in points; used when no per-bar spread is supplied
    slippage_points: float = 0.0          # extra adverse points per fill (0 = tester triggers without sliding)
    commission_per_lot_per_side: float = 0.0   # deposit currency, charged on entry and on exit
    swap_long_per_lot: float = 0.0        # deposit currency per lot per night (negative = cost)
    swap_short_per_lot: float = 0.0
    swap_rollover_hour: int = 0           # server hour of the rollover
    swap_triple_weekday: int = 2          # booking weekday charged x3 (0=Mon .. 4=Fri); 2 = Wednesday

    # --- EA behaviour being emulated ---
    max_open_positions: int = 1           # 1 = EA ignores signals while a position is open
    # Exit bar = entry bar + holding_bars + exit_bar_offset; the exit is filled at that
    # bar's OPEN (the only tick the EA sees in Open prices only).
    exit_bar_offset: int = 0
    reenter_on_exit_bar: bool = False     # True: EA may open a new trade on the tick that closed the old one
    close_open_at_end: bool = False       # True: close still-open trades at the last bar of the test

    def validate(self) -> "MT5TesterConfig":
        if self.modelling not in VALID_MODELLING:
            raise ValueError(f"modelling must be one of {VALID_MODELLING}, got {self.modelling!r}")
        if self.execution_delay not in VALID_DELAY:
            raise ValueError(f"execution_delay must be one of {VALID_DELAY}, got {self.execution_delay!r}")
        if self.execution_delay != "none":
            logger.warning(
                f"execution_delay={self.execution_delay!r} is ignored: the MT5 tester does not allow "
                f"a delay mode with Open prices only (orders fill on the single bar-open tick)."
            )
        if self.forward != "none":
            raise ValueError("forward must be 'none': the whole period is the backtest (Forward = No)")
        if self.point <= 0 or self.contract_size <= 0 or self.lots <= 0:
            raise ValueError("point, contract_size and lots must be > 0")
        if self.spread_points < 0 or self.slippage_points < 0:
            raise ValueError("spread_points and slippage_points must be >= 0")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")
        if not 0 <= self.swap_rollover_hour <= 23:
            raise ValueError("swap_rollover_hour must be in 0..23")
        if not 0 <= self.swap_triple_weekday <= 4:
            raise ValueError("swap_triple_weekday must be in 0..4 (Mon..Fri)")
        return self

    @property
    def spread_price(self) -> float:
        return self.spread_points * self.point

    @property
    def slippage_price(self) -> float:
        return self.slippage_points * self.point


def config_from_dict(data: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> MT5TesterConfig:
    """Build a validated config; unknown keys are an error (catches typos)."""
    merged = dict(data or {})
    merged.update(overrides or {})
    known = {f.name: f for f in fields(MT5TesterConfig)}
    unknown = sorted(set(merged) - set(known))
    if unknown:
        raise ValueError(f"Unknown MT5 tester setting(s): {unknown}. Valid: {sorted(known)}")
    cfg = MT5TesterConfig()
    for key, value in merged.items():
        current = getattr(cfg, key)
        if isinstance(current, bool):
            setattr(cfg, key, bool(value))
        elif isinstance(current, int):
            setattr(cfg, key, int(value))
        elif isinstance(current, float):
            setattr(cfg, key, float(value))
        else:
            setattr(cfg, key, str(value))
    return cfg.validate()


def find_config_file(config_root: str | Path, symbol: str, timeframe: str) -> Path:
    root = Path(config_root)
    candidates = [root / symbol / f"{timeframe}.yaml", root / symbol / "_default.yaml"]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"No MT5 tester config for {symbol} {timeframe}. Looked for: "
        + ", ".join(str(c) for c in candidates)
        + f". Copy {root / '_template.yaml'} to {candidates[0]} and set the spread for this timeframe."
    )


def load_mt5_config(
    config_root: str | Path,
    symbol: str,
    timeframe: str,
    overrides: Optional[Dict[str, Any]] = None,
    config_file: Optional[str | Path] = None,
) -> MT5TesterConfig:
    """Load the per-timeframe config (or an explicit file) and apply CLI overrides."""
    path = Path(config_file) if config_file else find_config_file(config_root, symbol, timeframe)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    logger.info(f"MT5 tester config: {path}")
    return config_from_dict(data, overrides)
