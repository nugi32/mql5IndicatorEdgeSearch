"""
Cost modeling: spread, slippage, transaction costs.
"""

import logging
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CostModel:
    """Apply realistic trading costs to edge analysis."""

    def __init__(
        self,
        spread_pips: float = 2.0,
        slippage_pips: float = 1.0,
        pip_value: float = 0.0001,
        spread_atr_mult: Optional[float] = None,
        atr_column: str = "atr_14",
    ):
        """
        Initialize cost model.

        Parameters
        ----------
        spread_pips : float
            Bid-ask spread in pips. Used as a fixed baseline, or as the
            fallback whenever `spread_atr_mult` is set but a given bar's
            ATR value isn't usable (NaN/<=0).
        slippage_pips : float
            Slippage on entry/exit in pips.
        pip_value : float
            Value per pip (for major forex: 0.0001).
        spread_atr_mult : Optional[float]
            If set, spread for each triggered bar is computed as
            `spread_atr_mult * atr_at_entry / pip_value` instead of the
            fixed `spread_pips`. This makes the Phase 5-6 cost estimate
            scale with realized volatility at entry time rather than
            assuming a constant spread across the whole dataset -- a fixed
            spread under-estimates cost exactly when extreme-indicator
            conditions (RSI/Stoch/CCI thresholds, etc.) are most likely to
            fire during high-volatility bars. Off by default for backward
            compatibility.
        atr_column : str
            Column to read the entry-time ATR from when `spread_atr_mult`
            is set.
        """
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.pip_value = pip_value
        self.spread_atr_mult = spread_atr_mult
        self.atr_column = atr_column

    def apply_costs_to_forward_profile(
        self,
        condition_mask: np.ndarray,
        df: pd.DataFrame,
        forward_engine,
        optimal_horizon: int,
        direction: str = "long",
    ) -> Dict:
        """
        Compute expectancy with costs applied.

        Parameters
        ----------
        condition_mask : np.ndarray
            Condition mask.
        df : pd.DataFrame
            OHLCV data.
        forward_engine :
            ForwardProfileEngine instance.
        optimal_horizon : int
            Exit horizon (bars).
        direction : str
            "long" or "short". BUG FIX: this parameter was missing entirely
            before -- this function always computed gross P&L as if going
            long (exit_price - entry_price), regardless of whether the
            condition's actual edge was bullish or bearish. For a genuinely
            bearish condition (forward bull probability significantly
            BELOW baseline -- the correct trade is to sell), that produced
            the exact mirror-image (negated) of the true P&L, making a real
            short edge look like a catastrophic loss. Since Phase 6b uses
            this function to drop conditions before they ever reach Phase
            7c (where direction is inferred correctly), this could -- and
            did -- silently reject every bearish edge in a run, sometimes
            leaving 0 survivors even when genuine edges existed. Pass
            infer_direction(cond_prob_bull_at_optimal_horizon,
            baseline_prob_at_optimal_horizon) here, the same call Phase 7c
            already makes, rather than assuming "long".

        Returns
        -------
        dict
            {
                'entry_slippage_pips': float,
                'exit_slippage_pips': float,
                'total_cost_pips': float,
                'gross_expectancy_pips': float,
                'net_expectancy_pips': float,
                'expectancy_r': float,  # in risk units
            }

        Notes
        -----
        Entry: next bar's open, apply spread + slippage
        Exit: at optimal_horizon close, apply spread + slippage
        Assumes 1:1 risk/reward (SL = entry - atr, TP = entry + atr)

        COST CONVENTION -- must match trade_simulator.py's _effective_half_cost
        -----------------------------------------------------------------------
        BUG FIX: this function used to charge `spread_pips + slippage_pips`
        in FULL at both entry and exit (i.e. `total_cost = 2 * (spread + slippage)`),
        as if the full bid-ask spread were paid twice per round trip. Real
        spread cost is paid ONCE per round trip (you buy at Ask, sell at
        Bid -- the Ask-Bid gap is realized a single time, not once on
        entry and again on exit). That made this Phase 6b pre-filter's
        cost estimate roughly 2x higher than Phase 7c's `simulate_condition`
        for the exact same `spread_pips`/`slippage_pips` config -- exactly
        backwards from this filter's own stated intent of being *more*
        lenient than Phase 7c, not stricter. Now split evenly between entry
        and exit (half at each), exactly like `_effective_half_cost`, so
        `spread_pips + slippage_pips` is the TOTAL round-trip cost in both
        phases and a condition's cost-adjusted expectancy_r here is directly
        comparable to Phase 7c's.
        """
        if optimal_horizon < 1 or optimal_horizon > forward_engine.max_horizon:
            return {
                'entry_slippage_pips': np.nan,
                'exit_slippage_pips': np.nan,
                'total_cost_pips': np.nan,
                'gross_expectancy_pips': np.nan,
                'net_expectancy_pips': np.nan,
                'expectancy_r': np.nan,
            }
        
        # Total round-trip cost per side: HALF of (spread + slippage) is
        # charged at entry and HALF at exit, summing to exactly
        # spread_pips + slippage_pips total -- matching
        # trade_simulator._effective_half_cost exactly, not double-counting
        # the spread (see BUG FIX note in the docstring above).
        fixed_entry_cost = (self.spread_pips + self.slippage_pips) / 2.0
        fixed_exit_cost = (self.spread_pips + self.slippage_pips) / 2.0

        # Get ATR for risk unit (and for volatility-scaled spread, if enabled)
        if self.atr_column in df.columns:
            atr = df[self.atr_column].values
        elif "atr_14" in df.columns:
            atr = df["atr_14"].values
        else:
            atr = np.full(len(df), 10.0)  # Default
        
        # Simulate P&L for each trigger
        trigger_indices = np.where(condition_mask)[0]
        trigger_indices = trigger_indices[trigger_indices < len(df) - forward_engine.max_horizon]
        
        if len(trigger_indices) == 0:
            return {
                'entry_slippage_pips': fixed_entry_cost,
                'exit_slippage_pips': fixed_exit_cost,
                'total_cost_pips': fixed_entry_cost + fixed_exit_cost,
                'gross_expectancy_pips': 0.0,
                'net_expectancy_pips': 0.0,
                'expectancy_r': 0.0,
            }

        # Vectorized instead of a per-trigger Python loop: extracting
        # df["open"].values / df["close"].values ONCE outside any loop
        # (instead of once per trigger, which was the actual bottleneck --
        # re-materializing the full column array per iteration is
        # O(n_triggers * n_rows) and made this function take hours on
        # multi-million-row M1 data even though it's numerically simple).
        open_arr = df["open"].values
        close_arr = df["close"].values

        entry_idx = trigger_indices + 1
        exit_idx = entry_idx + optimal_horizon
        in_bounds = exit_idx < len(df)
        entry_idx = entry_idx[in_bounds]
        exit_idx = exit_idx[in_bounds]
        src_idx = trigger_indices[in_bounds]  # bar the condition fired on (for ATR lookup)

        if len(entry_idx) == 0:
            return {
                'entry_slippage_pips': fixed_entry_cost,
                'exit_slippage_pips': fixed_exit_cost,
                'total_cost_pips': fixed_entry_cost + fixed_exit_cost,
                'gross_expectancy_pips': 0.0,
                'net_expectancy_pips': 0.0,
                'expectancy_r': 0.0,
            }

        entry_price = open_arr[entry_idx]
        exit_price = close_arr[exit_idx]
        gross_pnl_pips = (exit_price - entry_price) / self.pip_value
        if direction == "short":
            # A short profits when price falls -- mirror the long P&L
            # rather than recomputing entry/exit, since the cost (spread +
            # slippage) is symmetric and unaffected by direction.
            gross_pnl_pips = -gross_pnl_pips

        if self.spread_atr_mult is not None:
            entry_atr_arr = atr[src_idx]
            valid_atr = np.isfinite(entry_atr_arr) & (entry_atr_arr > 0)
            dynamic_spread_pips = np.where(
                valid_atr,
                (self.spread_atr_mult * entry_atr_arr) / self.pip_value,
                self.spread_pips,
            )
            # Same fix as above: dynamic_spread_pips + slippage_pips is
            # already the TOTAL round-trip cost -- no *2.0 here, that was
            # the double-counting bug.
            total_cost_arr = dynamic_spread_pips + self.slippage_pips
        else:
            total_cost_arr = np.full(len(src_idx), fixed_entry_cost + fixed_exit_cost)

        net_pnl_pips = gross_pnl_pips - total_cost_arr

        pnl_array = net_pnl_pips
        cost_array = total_cost_arr

        mean_total_cost = float(np.mean(cost_array))
        gross_expectancy_pips = np.mean(pnl_array) + mean_total_cost
        net_expectancy_pips = np.mean(pnl_array)
        
        # Expectancy in R units (atr-based)
        mean_atr = np.mean(atr[atr > 0])
        atr_pips = mean_atr / self.pip_value
        expectancy_r = net_expectancy_pips / atr_pips if atr_pips > 0 else 0.0
        
        return {
            'entry_slippage_pips': mean_total_cost / 2.0,
            'exit_slippage_pips': mean_total_cost / 2.0,
            'total_cost_pips': mean_total_cost,
            'gross_expectancy_pips': float(gross_expectancy_pips),
            'net_expectancy_pips': float(net_expectancy_pips),
            'expectancy_r': float(expectancy_r),
        }


def cost_aware_prefilter(
    cost_result: Dict,
    min_expectancy_r: float = 0.0,
) -> Tuple[bool, str]:
    """
    Cheap, early pass/fail check on whether a condition's cost-adjusted
    expectancy clears a minimum bar -- BEFORE it is sent through the
    expensive Phase 7 robustness stack (walk-forward, regime stress,
    parameter sensitivity, Phase 7c trade simulation, Phase 7d permutation
    test).

    Rationale (see PROJECT_DIRECTION.md section 8, "cost sensitivity"):
    a condition whose cost-adjusted expectancy_r from Phase 5-6's own cost
    model doesn't even clear breakeven (or a small positive margin) by
    itself is structurally unlikely to survive the stricter Phase 7c
    simulation (which adds a stop loss / take profit and intrabar path
    risk on top of the same cost assumptions). Filtering these out here
    saves the time and compute of running them through the rest of the
    pipeline, and keeps the final report focused on candidates that were
    never doomed by cost alone.

    This is a pre-filter, not a replacement for Phase 7e's gate: it uses
    the simpler horizon-based cost model from `apply_costs_to_forward_profile`
    (no SL/TP, no intrabar path), so it is intentionally more lenient than
    the Phase 7c/7e checks -- the goal is only to discard conditions that
    are *already* underwater on the cheap estimate, not to make the final
    call.

    Parameters
    ----------
    cost_result : Dict
        Output of `CostModel.apply_costs_to_forward_profile`.
    min_expectancy_r : float
        Minimum acceptable cost-adjusted expectancy_r to pass. 0.0 means
        "must clear realistic costs, not just be gross-profitable" (the
        default). A small positive margin (e.g. 0.02-0.05) can be used to
        also filter out candidates that only barely clear breakeven and
        are unlikely to survive Phase 7c's stricter simulation.

    Returns
    -------
    (passed, reason) : Tuple[bool, str]
        passed: True if the condition should proceed to Phase 7.
        reason: human-readable explanation when passed is False (empty
                string when passed is True).
    """
    expectancy_r = cost_result.get('expectancy_r', np.nan)

    if not np.isfinite(expectancy_r):
        return False, "cost-adjusted expectancy_r is not finite (no valid triggers/costs)"

    if expectancy_r < min_expectancy_r:
        return False, (
            f"cost-adjusted expectancy_r ({expectancy_r:.4f}) below minimum "
            f"required margin ({min_expectancy_r:.4f}) -- unlikely to survive "
            f"Phase 7c's stricter SL/TP simulation, skipping expensive "
            f"robustness validation for this candidate"
        )

    return True, ""
