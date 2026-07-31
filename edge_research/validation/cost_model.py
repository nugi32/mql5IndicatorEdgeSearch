"""
Cost modeling: spread, slippage, transaction costs.
"""

import logging
from typing import Dict, Tuple

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
    ):
        """
        Initialize cost model.

        Parameters
        ----------
        spread_pips : float
            Bid-ask spread in pips.
        slippage_pips : float
            Slippage on entry/exit in pips.
        pip_value : float
            Value per pip (for major forex: 0.0001).
        """
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.pip_value = pip_value

    def apply_costs_to_forward_profile(
        self,
        condition_mask: np.ndarray,
        df: pd.DataFrame,
        forward_engine,
        optimal_horizon: int,
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
        
        # Costs per side
        entry_cost = self.spread_pips + self.slippage_pips
        exit_cost = self.spread_pips + self.slippage_pips
        total_cost = entry_cost + exit_cost
        
        # Get ATR for risk unit
        if "atr_14" in df.columns:
            atr = df["atr_14"].values
        else:
            atr = np.full(len(df), 10.0)  # Default
        
        # Simulate P&L for each trigger
        trigger_indices = np.where(condition_mask)[0]
        trigger_indices = trigger_indices[trigger_indices < len(df) - forward_engine.max_horizon]
        
        if len(trigger_indices) == 0:
            return {
                'entry_slippage_pips': entry_cost,
                'exit_slippage_pips': exit_cost,
                'total_cost_pips': total_cost,
                'gross_expectancy_pips': 0.0,
                'net_expectancy_pips': 0.0,
                'expectancy_r': 0.0,
            }
        
        pnl_list = []
        
        for idx in trigger_indices:
            # Entry: next bar open
            entry_price = df["open"].values[idx + 1]
            
            # Exit: optimal_horizon bars later, at close
            exit_idx = idx + 1 + optimal_horizon
            if exit_idx >= len(df):
                continue
            
            exit_price = df["close"].values[exit_idx]
            
            # P&L in pips
            gross_pnl_pips = (exit_price - entry_price) / self.pip_value
            
            # Net of costs
            net_pnl_pips = gross_pnl_pips - total_cost
            
            pnl_list.append(net_pnl_pips)
        
        if not pnl_list:
            pnl_list = [0.0]
        
        pnl_array = np.array(pnl_list)
        gross_expectancy_pips = np.mean(pnl_array) + total_cost
        net_expectancy_pips = np.mean(pnl_array)
        
        # Expectancy in R units (atr-based)
        mean_atr = np.mean(atr[atr > 0])
        atr_pips = mean_atr / self.pip_value
        expectancy_r = net_expectancy_pips / atr_pips if atr_pips > 0 else 0.0
        
        return {
            'entry_slippage_pips': entry_cost,
            'exit_slippage_pips': exit_cost,
            'total_cost_pips': total_cost,
            'gross_expectancy_pips': float(gross_expectancy_pips),
            'net_expectancy_pips': float(net_expectancy_pips),
            'expectancy_r': float(expectancy_r),
        }
