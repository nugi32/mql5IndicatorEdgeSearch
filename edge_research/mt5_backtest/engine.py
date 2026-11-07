"""
Trade-by-trade emulation of the MT5 Strategy Tester, "Open prices only".

What the tester does in this mode (MetaTrader 5 help, "Testing Features",
and the MQL5 reference page "Testing Trading Strategies"):

* OnTick() runs once per bar, at the bar open. Every fill therefore happens
  at a bar-open price; the high/low/close of the bar are never traded.
* Bid = the bar's open price. Ask = Bid + spread. The spread is not modelled
  but taken from the broker's history, as a floating value, one value per bar.
* A buy fills at Ask and is closed at Bid; a sell fills at Bid and is closed
  at Ask. Long trades pay the spread of the ENTRY bar, short trades pay the
  spread of the EXIT bar.
* Without stop-loss/take-profit nothing happens between two bar opens.
* Random Delay is not allowed in this mode, so there is no execution delay.
* Forward = No: the whole date range is one backtest.

How the EA is assumed to behave (see MT5TesterConfig): it opens a trade at the
first tick of bar i+1 when the condition was true on bar i, holds it for N bars,
closes it on the first tick of bar i+1+N, keeps one position at a time and
does not open a new trade on the tick that closed the previous one.

This module does not change the research pipeline's own Phase 7c simulation
(which exits at the CLOSE of the exit bar and allows overlapping trades).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from edge_research.mt5_backtest.config import MT5TesterConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    trades: pd.DataFrame            # one row per closed trade
    balance: pd.Series              # realised balance per bar
    equity: pd.Series               # balance + floating profit per bar
    summary: Dict[str, Any]
    n_signals: int = 0              # signals inside the tested range
    n_skipped_busy: int = 0         # signals ignored because a position was open
    n_open_at_end: int = 0          # trades still open when the test ended (not counted)
    n_spread_fallback: int = 0      # bars that used the fixed spread because the per-bar spread was missing


def swap_nights(t_in: pd.Timestamp, t_out: pd.Timestamp, rollover_hour: int, triple_weekday: int) -> int:
    """
    Weighted number of rollovers a position crosses between ``t_in`` (excluded)
    and ``t_out`` (included).

    A rollover happens every day at ``rollover_hour`` server time and is booked
    on the trading day that just ended (an instant at 00:00 belongs to the
    previous calendar day). Saturday and Sunday bookings do not exist, and the
    ``triple_weekday`` booking counts x3, so one trading week sums to 7 nights.
    """
    nights = 0
    day = t_in.normalize()
    last = t_out.normalize()
    while day <= last:
        instant = day + pd.Timedelta(hours=rollover_hour)
        if t_in < instant <= t_out:
            booked = (instant - pd.Timedelta(days=1)) if rollover_hour == 0 else instant
            wd = booked.weekday()
            if wd < 5:
                nights += 3 if wd == triple_weekday else 1
        day += pd.Timedelta(days=1)
    return nights


def _spread_array(df: pd.DataFrame, cfg: MT5TesterConfig, spread_points: Optional[pd.Series]):
    """Per-bar spread in price units, plus how many bars fell back to the fixed value."""
    fixed = cfg.spread_price
    if spread_points is None:
        return np.full(len(df), fixed, dtype=np.float64), 0
    aligned = spread_points.reindex(df.index).to_numpy(dtype=np.float64) * cfg.point
    # The tester uses the last known spread when the history value is <= 0.
    aligned = np.where(aligned > 0, aligned, np.nan)
    aligned = pd.Series(aligned).ffill().to_numpy(dtype=np.float64, copy=True)
    still_bad = ~np.isfinite(aligned)
    aligned[still_bad] = fixed
    return aligned, int(still_bad.sum())


def run_mt5_backtest(
    df: pd.DataFrame,
    mask: np.ndarray,
    direction: str,
    holding_bars: int,
    cfg: MT5TesterConfig,
    spread_points: Optional[pd.Series] = None,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
) -> BacktestResult:
    """
    Emulate one EA over ``df`` (needs an ``open`` column and a sorted
    DatetimeIndex in broker server time).

    Parameters
    ----------
    mask : signal mask, ``mask[i]`` true at the close of bar i.
    direction : "long" or "short".
    holding_bars : bars to hold (the pipeline's ``optimal_holding_bars``).
    spread_points : optional per-bar spread in points indexed by bar time.
    start, end : optional date range of the test (end inclusive).
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
    hold = int(holding_bars) + cfg.exit_bar_offset
    if hold < 1:
        raise ValueError(f"holding_bars + exit_bar_offset must be >= 1, got {hold}")
    if len(mask) != len(df):
        raise ValueError("mask and df must have the same length")

    index = df.index
    n = len(df)
    lo = int(index.searchsorted(pd.Timestamp(start), side="left")) if start is not None else 0
    hi = int(index.searchsorted(pd.Timestamp(end), side="right")) if end is not None else n
    last = hi - 1
    open_ = df["open"].to_numpy(dtype=np.float64)
    spread, n_fallback = _spread_array(df, cfg, spread_points)
    long = direction == "long"
    slip = cfg.slippage_price

    trades: List[Dict[str, Any]] = []
    active_exits: List[int] = []
    n_signals = n_busy = n_open_end = 0

    for s in np.flatnonzero(np.asarray(mask, dtype=bool)):
        e = int(s) + 1                      # entry bar: first tick after the signal bar closed
        if e < lo or e > last:
            continue
        n_signals += 1
        # A position whose exit bar is e is closed on this very tick; the EA then
        # returns without checking for a new entry unless reenter_on_exit_bar.
        active_exits = [x for x in active_exits if x > e or (x == e and not cfg.reenter_on_exit_bar)]
        if len(active_exits) >= cfg.max_open_positions:
            n_busy += 1
            continue
        x = e + hold
        if x > last:
            if cfg.close_open_at_end:
                x = last
            else:
                n_open_end += 1
                active_exits.append(x)
                continue
        if not (np.isfinite(open_[e]) and np.isfinite(open_[x])):
            continue

        if long:
            entry = open_[e] + spread[e] + slip     # buy at Ask
            exit_ = open_[x] - slip                 # close at Bid
        else:
            entry = open_[e] - slip                 # sell at Bid
            exit_ = open_[x] + spread[x] + slip     # close at Ask
        entry, exit_ = round(entry, cfg.digits), round(exit_, cfg.digits)
        price_pnl = (exit_ - entry) if long else (entry - exit_)
        gross = price_pnl * cfg.contract_size * cfg.lots
        commission = -2.0 * cfg.commission_per_lot_per_side * cfg.lots
        nights = swap_nights(index[e], index[x], cfg.swap_rollover_hour, cfg.swap_triple_weekday)
        swap = nights * cfg.lots * (cfg.swap_long_per_lot if long else cfg.swap_short_per_lot)
        trades.append({
            "signal_time": index[e - 1], "entry_time": index[e], "exit_time": index[x],
            "entry_bar": e, "exit_bar": x, "direction": direction,
            "entry_price": entry, "exit_price": exit_,
            "spread_entry": spread[e], "spread_exit": spread[x],
            "price_pnl": price_pnl, "gross_profit": gross,
            "commission": commission, "swap": swap, "nights": nights,
            "profit": gross + commission + swap,
        })
        active_exits.append(x)

    cols = ["signal_time", "entry_time", "exit_time", "entry_bar", "exit_bar", "direction",
            "entry_price", "exit_price", "spread_entry", "spread_exit", "price_pnl",
            "gross_profit", "commission", "swap", "nights", "profit"]
    trades_df = pd.DataFrame(trades, columns=cols)
    balance, equity = _curves(df, trades_df, cfg, spread, lo, last, long)
    summary = _summary(trades_df, balance, equity, cfg)
    return BacktestResult(trades_df, balance, equity, summary, n_signals, n_busy, n_open_end, n_fallback)


def _curves(df, trades, cfg, spread, lo, last, long):
    """Balance steps at the exit bar of each trade; equity adds the open profit marked at each bar open."""
    m = last - lo + 1
    idx = df.index[lo:last + 1]
    if m <= 0:
        empty = pd.Series(dtype=float)
        return empty, empty
    realised = np.zeros(m)
    floating = np.zeros(m)
    open_ = df["open"].to_numpy(dtype=np.float64)
    mult = cfg.contract_size * cfg.lots
    for t in trades.itertuples(index=False):
        e, x = t.entry_bar - lo, t.exit_bar - lo
        realised[x] += t.profit
        seg = slice(t.entry_bar, t.exit_bar)       # bars during which the trade is open (exit tick excluded)
        if long:
            mark = open_[seg] - t.entry_price                       # marked at Bid
        else:
            mark = t.entry_price - (open_[seg] + spread[seg])       # marked at Ask
        floating[e:x] += mark * mult
    balance = cfg.initial_deposit + np.cumsum(realised)
    return pd.Series(balance, index=idx), pd.Series(balance + floating, index=idx)


def _max_drawdown(series: pd.Series):
    if len(series) == 0:
        return 0.0, 0.0
    peak = series.cummax()
    dd = peak - series
    pct = (dd / peak.replace(0, np.nan)).fillna(0.0)
    return float(dd.max()), float(pct.max() * 100.0)


def _max_run(flags: np.ndarray, value: bool) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f == value else 0
        best = max(best, cur)
    return best


def _summary(trades: pd.DataFrame, balance: pd.Series, equity: pd.Series, cfg: MT5TesterConfig) -> Dict[str, Any]:
    n = len(trades)
    profit = trades["profit"].to_numpy(dtype=float)
    wins = profit > 0
    gross_profit = float(profit[wins].sum()) if n else 0.0
    gross_loss = float(profit[~wins & (profit < 0)].sum()) if n else 0.0
    net = float(profit.sum()) if n else 0.0
    bal_dd, bal_dd_pct = _max_drawdown(balance)
    eq_dd, eq_dd_pct = _max_drawdown(equity)
    return {
        "initial_deposit": cfg.initial_deposit,
        "total_net_profit": net,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss < 0 else (np.inf if gross_profit > 0 else 0.0),
        "expected_payoff": (net / n) if n else 0.0,
        "recovery_factor": (net / eq_dd) if eq_dd > 0 else 0.0,
        "total_trades": n,
        "long_trades": int((trades["direction"] == "long").sum()) if n else 0,
        "short_trades": int((trades["direction"] == "short").sum()) if n else 0,
        "profit_trades_pct": (100.0 * wins.sum() / n) if n else 0.0,
        "largest_profit_trade": float(profit.max()) if n else 0.0,
        "largest_loss_trade": float(profit.min()) if n else 0.0,
        "avg_profit_trade": (gross_profit / wins.sum()) if wins.sum() else 0.0,
        "avg_loss_trade": (gross_loss / (profit < 0).sum()) if (profit < 0).sum() else 0.0,
        "max_consecutive_wins": _max_run(wins, True) if n else 0,
        "max_consecutive_losses": _max_run(wins, False) if n else 0,
        "balance_drawdown_max": bal_dd,
        "balance_drawdown_max_pct": bal_dd_pct,
        "equity_drawdown_max": eq_dd,
        "equity_drawdown_max_pct": eq_dd_pct,
        "final_balance": float(balance.iloc[-1]) if len(balance) else cfg.initial_deposit,
    }
