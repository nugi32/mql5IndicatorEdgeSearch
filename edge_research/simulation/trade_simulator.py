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
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TradeSimConfig:
    """Configuration for one realistic trade simulation run.

    COST MODEL -- fixed vs. variable (volatility/session aware)
    --------------------------------------------------------------
    The original cost model used a single constant `spread_price_units` for
    every trade, regardless of when it happened. That is optimistic: real
    broker spreads widen during high-volatility bars and during low-liquidity
    sessions (e.g. the Asia session for XAUUSD), which is disproportionately
    likely to be exactly when mean-reversion/extreme-indicator conditions
    (RSI/Stoch/CCI thresholds etc.) trigger. Two independent, optional
    scaling mechanisms are provided on top of the fixed baseline so existing
    configs keep working unchanged unless explicitly opted in:

    - `spread_atr_mult`: if set, spread is computed as
      `spread_atr_mult * entry_atr` instead of the fixed
      `spread_price_units`. This makes cost scale with the market's own
      realized volatility at entry time, which is a reasonable proxy for
      how much a real broker's spread would widen.
    - `session_spread_multipliers`: an optional list of
      `(start_hour, end_hour, multiplier)` triples, evaluated against the
      hour-of-day of the bar's timestamp (assumed to already be in the
      broker/server timezone the data was exported in -- this module does
      not do timezone conversion). Whichever spread value results from the
      rule above (fixed or ATR-scaled) is then multiplied by the matching
      session's multiplier. Hours are in [0, 24) and a range that wraps
      past midnight (e.g. (22, 6, ...)) is supported. If no range matches,
      multiplier 1.0 is used.

    Both mechanisms are OFF by default (`spread_atr_mult=None`,
    `session_spread_multipliers=None`), so a `TradeSimConfig()` with no
    extra arguments behaves exactly as before.
    """

    direction: Literal["long", "short"] = "long"
    atr_column: str = "atr_14"
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0  # take-profit distance, in ATR multiples
    use_trailing_stop: bool = False
    trail_atr_mult: float = 1.5  # trail distance once trade is in profit
    max_holding_bars: int = 20  # forced exit if neither SL nor TP hit
    spread_price_units: float = 0.3  # fixed baseline, e.g. XAUUSD spread in price units
    slippage_price_units: float = 0.0
    # Optional volatility scaling: when set, overrides spread_price_units
    # with `spread_atr_mult * entry_atr` for each trade individually.
    spread_atr_mult: Optional[float] = None
    # Optional session scaling: list of (start_hour, end_hour, multiplier)
    # applied on top of whichever spread value is used above. Hours are in
    # broker/server time, [0, 24). Ranges may wrap past midnight.
    session_spread_multipliers: Optional[List[Tuple[int, int, float]]] = None
    # Which side is assumed touched first when BOTH the stop and target
    # fall inside the same bar's high-low range (true intrabar order is
    # unknowable from OHLC alone):
    #   "stop_first"   -- conservative / worst-case (recommended default)
    #   "target_first" -- optimistic
    intrabar_priority: Literal["stop_first", "target_first"] = "stop_first"
    # Bootstrap confidence interval on expectancy_r (Phase 7c hardening --
    # see PROJECT_DIRECTION.md section 8, "future work"). Off by default
    # (bootstrap_n=0) since it adds compute cost per condition; enable via
    # config to require the CI lower bound (not just the point estimate) be
    # positive in the Phase 7e gate.
    bootstrap_n: int = 0
    bootstrap_ci: float = 0.95
    bootstrap_random_state: Optional[int] = None


def _session_multiplier(hour: int, ranges: List[Tuple[int, int, float]]) -> float:
    """Look up the spread multiplier for a given hour-of-day (broker time)."""
    for start_hour, end_hour, mult in ranges:
        if start_hour <= end_hour:
            if start_hour <= hour < end_hour:
                return mult
        else:
            # Wraps past midnight, e.g. (22, 6, 1.5) covers 22:00-23:59 and 00:00-05:59.
            if hour >= start_hour or hour < end_hour:
                return mult
    return 1.0


def _effective_half_cost(
    config: "TradeSimConfig",
    entry_atr: float,
    timestamp,
) -> float:
    """
    Compute the per-side (entry or exit) cost in price units for one trade,
    applying volatility scaling (if configured) then session scaling
    (if configured) on top of the fixed baseline.
    """
    if config.spread_atr_mult is not None:
        spread = config.spread_atr_mult * entry_atr
    else:
        spread = config.spread_price_units

    if config.session_spread_multipliers:
        hour = getattr(timestamp, "hour", None)
        if hour is not None:
            spread = spread * _session_multiplier(hour, config.session_spread_multipliers)

    return (spread + config.slippage_price_units) / 2.0


def bootstrap_expectancy_r_ci(
    r_multiples: np.ndarray,
    n_boot: int = 1000,
    ci: float = 0.95,
    random_state: Optional[int] = None,
) -> Tuple[float, float]:
    """
    Bootstrap confidence interval on mean R-multiple (expectancy_r).

    Resamples the observed trade R-multiples with replacement `n_boot`
    times and returns the (lower, upper) percentile bounds for the given
    confidence level. This is the "future work" item from
    PROJECT_DIRECTION.md section 8: Phase 7e can require the LOWER bound
    of this interval to be positive, which is a stricter and more honest
    check than the point estimate alone -- a condition with few trades or
    high trade-to-trade variance can have a positive mean expectancy_r
    purely by chance.

    Parameters
    ----------
    r_multiples : np.ndarray
        Per-trade R-multiples (one value per simulated trade).
    n_boot : int
        Number of bootstrap resamples. 0 disables (returns (nan, nan)).
    ci : float
        Confidence level, e.g. 0.95 for a 95% CI.
    random_state : Optional[int]
        Seed for reproducibility.

    Returns
    -------
    (lower, upper) : Tuple[float, float]
        Bootstrap percentile CI bounds on the mean R-multiple. (nan, nan)
        if there are fewer than 2 trades or n_boot <= 0.
    """
    if n_boot <= 0 or r_multiples is None or len(r_multiples) < 2:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(random_state)
    n = len(r_multiples)
    alpha = (1.0 - ci) / 2.0

    boot_means = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        sample = rng.choice(r_multiples, size=n, replace=True)
        boot_means[i] = np.mean(sample)

    lower = float(np.percentile(boot_means, 100 * alpha))
    upper = float(np.percentile(boot_means, 100 * (1 - alpha)))
    return (lower, upper)


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
    r_multiples: np.ndarray = field(default_factory=lambda: np.array([]))
    expectancy_r_ci_low: float = float("nan")
    expectancy_r_ci_high: float = float("nan")

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
            "expectancy_r_ci_low": self.expectancy_r_ci_low,
            "expectancy_r_ci_high": self.expectancy_r_ci_high,
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

    for i in trigger_idx:
        entry_bar = i + 1
        if entry_bar >= n:
            continue

        entry_atr = atr[i]
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            continue

        # Per-trade cost: fixed baseline by default, optionally scaled by
        # this trade's own entry-time ATR and/or the entry bar's
        # session-of-day (see TradeSimConfig docstring / _effective_half_cost).
        entry_timestamp = df.index[entry_bar] if entry_bar < len(df.index) else None
        half_cost = _effective_half_cost(config, entry_atr, entry_timestamp)

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
            r_multiples=np.array([]),
            expectancy_r_ci_low=np.nan,
            expectancy_r_ci_high=np.nan,
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

    ci_low, ci_high = bootstrap_expectancy_r_ci(
        r_arr,
        n_boot=config.bootstrap_n,
        ci=config.bootstrap_ci,
        random_state=config.bootstrap_random_state,
    )

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
        r_multiples=r_arr,
        expectancy_r_ci_low=ci_low,
        expectancy_r_ci_high=ci_high,
    )
