"""
Phase 7c: Realistic Trade Simulation

Event-driven, bar-by-bar simulation of how a discovered condition would
actually perform if traded with a concrete entry/exit/risk-management
scheme (stop loss, take profit, optional trailing stop, spread cost,
max holding period).

WHY THIS PHASE EXISTS
----------------------
Phases 5-6 measure a condition's edge as a *directional probability* at a
fixed horizon: "if the condition triggers at bar i, what fraction of the
time is close[i+1+h] > open[i+1]?" This is a clean, fast, vectorized way
to screen thousands of candidate conditions, but it does NOT match how an
EA actually trades:

  - The EA enters with a stop loss and take profit. A condition can have a
    genuine directional edge at the close of bar i+1+h while ALSO being
    highly likely to hit a stop loss on the way there. The probability
    profile from Phase 5 is blind to this "path" between entry and the
    horizon -- it only looks at the two endpoints.
  - Real trades pay spread + slippage on entry AND exit.
  - Horizon-based exit ("exit at bar i+1+h regardless of price") is rarely
    how a live EA behaves; EAs typically exit on SL/TP/trailing stop.

This phase closes that gap: it takes conditions that already passed
Phase 5-6 significance testing and simulates what actually happens if you
trade them with a concrete, EA-realistic exit scheme. Only conditions that
remain profitable under this more realistic simulation are worth turning
into an MQL5 EA (see edge_research.selection.strategy_gate).

LIMITATION -- INTRABAR PATH ASSUMPTION
----------------------------------------
We only have OHLC bars, not tick data, so we cannot know the true order in
which high/low were touched within a bar. This module uses a conservative,
configurable assumption (see `intrabar_priority`) and records it in every
result so it is never silently forgotten. This is a known, deliberate
simplification -- for final validation before going live, replay the EA in
the MT5 Strategy Tester in "every tick" mode, which this module does not
replace.

See PROJECT_DIRECTION.md, section 4, for the full rationale.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TradeSimConfig:
    """Configuration for one realistic trade simulation run."""

    direction: Literal["long", "short"] = "long"
    atr_column: str = "atr_14"
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0  # take-profit distance, in ATR multiples
    use_trailing_stop: bool = False
    trail_atr_mult: float = 1.5  # trail distance once trade is in profit
    max_holding_bars: int = 20  # forced exit if neither SL nor TP hit
    spread_price_units: float = 0.3  # e.g. XAUUSD spread in price units
    slippage_price_units: float = 0.0
    # Which side is assumed touched first when BOTH the stop and target
    # fall inside the same bar's high-low range (true intrabar order is
    # unknowable from OHLC alone):
    #   "stop_first"   -- conservative / worst-case (recommended default)
    #   "target_first" -- optimistic
    intrabar_priority: Literal["stop_first", "target_first"] = "stop_first"


@dataclass
class TradeSimResult:
    """Aggregated results of simulating a condition over the full dataset."""

    n_trades: int
    n_wins: int
    n_losses: int
    n_timeouts: int
    win_rate: float
    avg_win_pips: float
    avg_loss_pips: float
    expectancy_pips: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_pips: float
    equity_curve_pips: np.ndarray
    config: TradeSimConfig

    def summary_dict(self) -> dict:
        """Flat dict suitable for embedding in an edge report / YAML output."""
        return {
            "n_trades": self.n_trades,
            "n_wins": self.n_wins,
            "n_losses": self.n_losses,
            "n_timeouts": self.n_timeouts,
            "win_rate": self.win_rate,
            "avg_win_pips": self.avg_win_pips,
            "avg_loss_pips": self.avg_loss_pips,
            "expectancy_pips": self.expectancy_pips,
            "expectancy_r": self.expectancy_r,
            "profit_factor": self.profit_factor,
            "max_drawdown_pips": self.max_drawdown_pips,
            "direction": self.config.direction,
            "sl_atr_mult": self.config.sl_atr_mult,
            "tp_atr_mult": self.config.tp_atr_mult,
            "intrabar_priority": self.config.intrabar_priority,
        }


def infer_direction(cond_prob_bull: float, baseline_prob: float) -> Literal["long", "short"]:
    """
    Infer whether a condition should be traded long or short based on
    whether it pushes the forward bull probability above or below the
    unconditional baseline at the same horizon.
    """
    return "long" if cond_prob_bull >= baseline_prob else "short"


def simulate_condition(
    df: pd.DataFrame,
    mask: np.ndarray,
    config: TradeSimConfig,
) -> TradeSimResult:
    """
    Bar-by-bar simulation of every trigger of `mask` under `config`.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'open', 'high', 'low', 'close', and config.atr_column.
    mask : np.ndarray
        Boolean trigger mask, same convention as the rest of the pipeline
        (mask[i] True => condition known at close of bar i; entry happens
        at open of bar i+1, matching Phase 5's no-lookahead convention).
    config : TradeSimConfig

    Returns
    -------
    TradeSimResult
    """
    if config.atr_column not in df.columns:
        raise KeyError(
            f"ATR column '{config.atr_column}' not found in dataframe; "
            f"required for stop-loss/take-profit sizing."
        )

    open_ = df["open"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    atr = df[config.atr_column].values.astype(np.float64)

    n = len(df)
    trigger_idx = np.where(mask)[0]

    pips_results = []
    r_results = []
    outcomes = []  # 'win' | 'loss' | 'timeout'

    long = config.direction == "long"
    half_cost = (config.spread_price_units + config.slippage_price_units) / 2.0

    for i in trigger_idx:
        entry_bar = i + 1
        if entry_bar >= n:
            continue

        entry_atr = atr[i]
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            continue

        raw_entry = open_[entry_bar]
        entry_price = raw_entry + half_cost if long else raw_entry - half_cost

        sl_dist = config.sl_atr_mult * entry_atr
        tp_dist = config.tp_atr_mult * entry_atr
        if sl_dist <= 0:
            continue

        if long:
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

        trail_price = sl_price
        exit_price = None
        outcome = "timeout"

        last_bar = min(entry_bar + config.max_holding_bars, n - 1)
        for b in range(entry_bar, last_bar + 1):
            bar_high, bar_low = high[b], low[b]

            hit_sl = (bar_low <= trail_price) if long else (bar_high >= trail_price)
            hit_tp = (bar_high >= tp_price) if long else (bar_low <= tp_price)

            if hit_sl and hit_tp:
                # Both levels fall within this bar's range -- true intrabar
                # order is unknown from OHLC alone; resolve per config.
                if config.intrabar_priority == "stop_first":
                    exit_price, outcome = trail_price, "loss"
                else:
                    exit_price, outcome = tp_price, "win"
                break
            elif hit_sl:
                # A trailing stop that has moved into profit still counts
                # as a "win" even though it exits via the stop-loss branch.
                is_win = (trail_price > entry_price) if long else (trail_price < entry_price)
                exit_price, outcome = trail_price, ("win" if is_win else "loss")
                break
            elif hit_tp:
                exit_price, outcome = tp_price, "win"
                break

            if config.use_trailing_stop:
                if long:
                    candidate = close[b] - config.trail_atr_mult * entry_atr
                    trail_price = max(trail_price, candidate)
                else:
                    candidate = close[b] + config.trail_atr_mult * entry_atr
                    trail_price = min(trail_price, candidate)

        if exit_price is None:
            # Forced exit at close of the last allowed bar (max_holding_bars reached).
            exit_price = close[last_bar]
            outcome = "timeout"

        exit_price = exit_price - half_cost if long else exit_price + half_cost

        pips = (exit_price - entry_price) if long else (entry_price - exit_price)
        r_multiple = pips / sl_dist

        pips_results.append(pips)
        r_results.append(r_multiple)
        outcomes.append(outcome)

    pips_arr = np.array(pips_results, dtype=np.float64)
    r_arr = np.array(r_results, dtype=np.float64)
    outcomes_arr = np.array(outcomes)

    n_trades = len(pips_arr)
    if n_trades == 0:
        logger.debug("simulate_condition: no valid trades produced (check ATR/data coverage)")
        return TradeSimResult(
            n_trades=0,
            n_wins=0,
            n_losses=0,
            n_timeouts=0,
            win_rate=np.nan,
            avg_win_pips=np.nan,
            avg_loss_pips=np.nan,
            expectancy_pips=np.nan,
            expectancy_r=np.nan,
            profit_factor=np.nan,
            max_drawdown_pips=np.nan,
            equity_curve_pips=np.array([]),
            config=config,
        )

    wins = pips_arr > 0
    losses = ~wins
    n_wins = int(np.sum(wins))
    n_losses = int(np.sum(losses))
    n_timeouts = int(np.sum(outcomes_arr == "timeout"))

    avg_win = float(np.mean(pips_arr[wins])) if n_wins > 0 else 0.0
    avg_loss = float(np.mean(pips_arr[losses])) if n_losses > 0 else 0.0

    gross_win = float(np.sum(pips_arr[wins])) if n_wins > 0 else 0.0
    gross_loss = float(-np.sum(pips_arr[losses])) if n_losses > 0 else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else np.inf

    equity_curve = np.cumsum(pips_arr)
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = running_max - equity_curve
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

    return TradeSimResult(
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        n_timeouts=n_timeouts,
        win_rate=n_wins / n_trades,
        avg_win_pips=avg_win,
        avg_loss_pips=avg_loss,
        expectancy_pips=float(np.mean(pips_arr)),
        expectancy_r=float(np.mean(r_arr)),
        profit_factor=profit_factor,
        max_drawdown_pips=max_dd,
        equity_curve_pips=equity_curve,
        config=config,
    )
