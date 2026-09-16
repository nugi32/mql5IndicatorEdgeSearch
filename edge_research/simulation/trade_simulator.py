"""
Phase 7c: Realistic Trade Simulation

Event-driven, bar-by-bar simulation of how a discovered condition would
actually perform if traded with a concrete entry/exit scheme: enter at the
next bar's open, hold for a fixed number of bars, exit at that bar's
close. Spread + slippage cost is charged on both entry and exit.

WHY THIS PHASE EXISTS
----------------------
Phases 5-6 measure a condition's edge as a *directional probability* at a
fixed horizon: "if the condition triggers at bar i, what fraction of the
time is close[i+1+h] > open[i+1]?" This is a clean, fast, vectorized way
to screen thousands of candidate conditions, but it does NOT match how an
EA actually trades: real trades pay spread + slippage on entry AND exit,
and the Phase 5-6 estimate does not tell you which holding period h
actually produces the most *consistent* (not just the most profitable)
result for a given condition.

This phase closes that gap: it takes conditions that already passed
Phase 5-6 significance testing, determines -- per condition, from the
simulated cost-adjusted trade distribution itself, not a hardcoded
default -- which holding period produces the most consistent outcome (see
`scan_holding_horizons` below), and then simulates what actually happens
if you trade the condition with exactly that holding period. Only
conditions that remain profitable under this more realistic simulation,
AND whose selected holding period is itself stable across walk-forward
windows (see edge_research.validation.walk_forward), are worth turning
into an MQL5 EA (see edge_research.selection.strategy_gate).

EXIT SCHEME -- fixed holding period, no stop loss / take profit
------------------------------------------------------------------
Earlier revisions of this module simulated a stop-loss/take-profit/
trailing-stop exit scheme. That has been removed entirely: a position is
now opened at the next bar's open and closed unconditionally at the close
of the bar `holding_bars` bars later -- no price level is ever checked
intrabar. This means the "which side of high/low is touched first"
ambiguity that OHLC-only data cannot resolve no longer applies to this
module; there is no longer an `intrabar_priority` setting because there
is no longer an intrabar path dependency to resolve.

`holding_bars` is NOT a free hyperparameter chosen once for the whole
pipeline. It is selected per-condition by `scan_holding_horizons` (see
below) and validated for stability across walk-forward windows before a
condition is allowed through the Phase 7e gate -- see
edge_research.validation.walk_forward.validate_holding_bars_walk_forward.

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

    EXIT SCHEME -- `holding_bars`
    --------------------------------
    The ONLY exit mechanism: a position opened at bar `entry_bar` is closed
    unconditionally at the close of bar `entry_bar + holding_bars` (clipped
    to the last available bar if the dataset ends first). There is no
    stop-loss, take-profit, or trailing stop. `holding_bars` should be set
    per-condition from `scan_holding_horizons`'s selection, not left at a
    hand-picked constant -- see module docstring.

    RISK NORMALIZATION -- `atr_column`
    --------------------------------------
    With no stop-loss there is no longer a natural "1R" distance from a
    stop price. `atr_column` is still used, but purely as a normalization
    unit for reporting: `r_multiple = pips / entry_atr`. This keeps
    expectancy_r comparable across symbols/timeframes and with the rest of
    the pipeline's existing R-based thresholds, without implying any
    actual stop order.
    """

    direction: Literal["long", "short"] = "long"
    atr_column: str = "atr_14"
    holding_bars: int = 20
    spread_price_units: float = 0.3  # fixed baseline, e.g. XAUUSD spread in price units
    slippage_price_units: float = 0.0
    # Optional volatility scaling: when set, overrides spread_price_units
    # with `spread_atr_mult * entry_atr` for each trade individually.
    spread_atr_mult: Optional[float] = None
    # Optional session scaling: list of (start_hour, end_hour, multiplier)
    # applied on top of whichever spread value is used above. Hours are in
    # broker/server time, [0, 24). Ranges may wrap past midnight.
    session_spread_multipliers: Optional[List[Tuple[int, int, float]]] = None
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
            "holding_bars": self.config.holding_bars,
        }


def infer_direction(cond_prob_bull: float, baseline_prob: float) -> Literal["long", "short"]:
    """
    Infer whether a condition should be traded long or short based on
    whether it pushes the forward bull probability above or below the
    unconditional baseline at the same horizon.
    """
    return "long" if cond_prob_bull >= baseline_prob else "short"


def compute_r_multiples_for_horizon(
    df: pd.DataFrame,
    mask: np.ndarray,
    config: TradeSimConfig,
    horizon: int,
) -> np.ndarray:
    """
    Cost-adjusted per-trigger R-multiples for a single fixed holding period,
    without building a full TradeSimResult. Used by both
    `scan_holding_horizons` (to compare many candidate horizons) and by
    edge_research.validation.walk_forward.validate_holding_bars_walk_forward
    (to check whether one already-selected horizon holds up out-of-sample).

    Entry: open of bar i+1 (i = trigger bar), cost-adjusted by
    `_effective_half_cost` using that trade's own entry-time ATR/timestamp
    -- exactly the convention `simulate_condition` uses. Exit: close of bar
    i+1+horizon, cost-adjusted the same way. No path-dependent check of any
    kind -- this is deliberately just the two endpoints, cost-adjusted.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'open', 'close', and config.atr_column.
    mask : np.ndarray
        Boolean trigger mask (mask[i] True => condition known at close of
        bar i, entry at open of bar i+1).
    config : TradeSimConfig
        Only `direction`, `atr_column`, and the cost fields are used;
        `holding_bars` on the config object is ignored in favor of the
        `horizon` argument.
    horizon : int
        Number of bars to hold, >= 1.

    Returns
    -------
    np.ndarray
        R-multiples, one per valid trigger (triggers too close to the end
        of the data to reach `horizon` bars are silently excluded).
    """
    if config.atr_column not in df.columns:
        raise KeyError(
            f"ATR column '{config.atr_column}' not found in dataframe; "
            f"required for R-multiple normalization."
        )
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    open_ = df["open"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    atr = df[config.atr_column].values.astype(np.float64)
    index = df.index

    n = len(df)
    trigger_idx = np.where(mask)[0]
    long = config.direction == "long"

    r_results = []
    for i in trigger_idx:
        entry_bar = i + 1
        exit_bar = entry_bar + horizon
        if exit_bar >= n:
            continue

        entry_atr = atr[i]
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            continue

        entry_timestamp = index[entry_bar]
        half_cost = _effective_half_cost(config, entry_atr, entry_timestamp)

        raw_entry = open_[entry_bar]
        entry_price = raw_entry + half_cost if long else raw_entry - half_cost

        raw_exit = close[exit_bar]
        exit_price = raw_exit - half_cost if long else raw_exit + half_cost

        pips = (exit_price - entry_price) if long else (entry_price - exit_price)
        r_results.append(pips / entry_atr)

    return np.array(r_results, dtype=np.float64)


def scan_holding_horizons(
    df: pd.DataFrame,
    mask: np.ndarray,
    config: TradeSimConfig,
    horizon_min: int,
    horizon_max: int,
) -> pd.DataFrame:
    """
    Score every candidate holding period in [horizon_min, horizon_max] for
    "consistency", not raw profit, and return the full per-horizon table so
    the choice is auditable rather than a hardcoded/dummy number.

    SCORE -- per-horizon t-statistic on R-multiple
    ---------------------------------------------------
    `score(h) = mean(R_h) / (std(R_h) / sqrt(n_h))`

    This is deliberately NOT "pick the horizon with the highest mean
    R-multiple". A horizon with a large but highly dispersed mean is
    penalized relative to a horizon with a smaller but tightly clustered
    mean -- the t-statistic formulation rewards both a positive edge AND
    low trade-to-trade variance (what "consistent" means here), and also
    penalizes horizons with too few valid samples to trust the estimate.

    This function only screens on the full (in-sample) dataset. Whatever
    horizon is selected from this table must still be checked for
    stability across walk-forward windows before being trusted -- see
    edge_research.validation.walk_forward.validate_holding_bars_walk_forward.
    Selecting a horizon here and reporting its in-sample performance as if
    it were already validated would repeat the exact class of mistake
    already fixed elsewhere in this pipeline (selection on the same data
    used to report performance).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'open', 'close', and config.atr_column.
    mask : np.ndarray
        Boolean trigger mask.
    config : TradeSimConfig
        Only `direction`, `atr_column`, and cost fields are used.
    horizon_min, horizon_max : int
        Inclusive range of candidate holding periods to scan, in bars.

    Returns
    -------
    pd.DataFrame
        Columns: horizon, n_trades, mean_r, std_r, score. `score` is NaN
        for horizons with fewer than 2 valid trades (std is undefined) --
        such horizons are never selected by `select_best_holding_bars`.
    """
    rows = []
    for h in range(horizon_min, horizon_max + 1):
        r = compute_r_multiples_for_horizon(df, mask, config, h)
        n_h = len(r)
        if n_h >= 2:
            mean_r = float(np.mean(r))
            std_r = float(np.std(r, ddof=1))
            score = (mean_r / (std_r / np.sqrt(n_h))) if std_r > 0 else np.nan
        else:
            mean_r = float(np.mean(r)) if n_h == 1 else np.nan
            std_r = np.nan
            score = np.nan
        rows.append({
            "horizon": h,
            "n_trades": n_h,
            "mean_r": mean_r,
            "std_r": std_r,
            "score": score,
        })
    return pd.DataFrame(rows)


def select_best_holding_bars(scan_table: pd.DataFrame) -> Optional[int]:
    """
    Pick the horizon with the highest score from `scan_holding_horizons`'s
    output table. Horizons with NaN score (fewer than 2 valid trades, or
    zero-variance/degenerate distributions) are never selected.

    Returns
    -------
    Optional[int]
        The selected horizon (bars), or None if every horizon in the
        table had an undefined score (e.g. the condition has too few
        triggers to evaluate at all).
    """
    valid = scan_table.dropna(subset=["score"])
    if len(valid) == 0:
        return None
    best_row = valid.loc[valid["score"].idxmax()]
    return int(best_row["horizon"])


def simulate_condition(
    df: pd.DataFrame,
    mask: np.ndarray,
    config: TradeSimConfig,
) -> TradeSimResult:
    """
    Bar-by-bar simulation of every trigger of `mask` under `config`.

    Entry at open of bar i+1 (no-lookahead, matching Phase 5's
    convention). Exit unconditionally at close of bar
    i+1+config.holding_bars (clipped to the last available bar if the
    dataset ends first -- such trades are marked outcome='timeout' since
    they didn't get the full intended holding period). There is no
    stop-loss, take-profit, or trailing stop of any kind.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'open', 'high', 'low', 'close', and config.atr_column.
        ('high'/'low' are not used by the exit logic itself but are kept
        as a required-column check for interface stability with callers
        that also use this dataframe for other phases.)
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
            f"required for R-multiple normalization."
        )

    open_ = df["open"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    atr = df[config.atr_column].values.astype(np.float64)

    n = len(df)
    trigger_idx = np.where(mask)[0]

    pips_results = []
    r_results = []
    outcomes = []  # 'closed' | 'timeout' (data ran out before holding_bars elapsed)

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

        intended_exit_bar = entry_bar + config.holding_bars
        exit_bar = min(intended_exit_bar, n - 1)
        outcome = "closed" if exit_bar == intended_exit_bar else "timeout"

        raw_exit = close[exit_bar]
        exit_price = raw_exit - half_cost if long else raw_exit + half_cost

        pips = (exit_price - entry_price) if long else (entry_price - exit_price)
        r_multiple = pips / entry_atr

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
