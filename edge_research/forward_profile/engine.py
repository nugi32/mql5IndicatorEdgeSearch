"""
Phase 5: Forward Probability Profiling

Compute forward-direction probability profiles across horizons.
No lookahead: entry at next bar's open, exit at future bar's close.
"""

import gc
import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ForwardProfileEngine:
    """
    Precomputes and caches forward price movement probabilities.

    Attributes
    ----------
    df : pd.DataFrame
        OHLCV dataframe.
    max_horizon : int
        Maximum bars to look ahead.
    forward_matrix : np.ndarray
        Boolean matrix of shape (n_bars, max_horizon).
        forward_matrix[i, h] = True if close[i+1+h] > open[i+1]
    """

    def __init__(self, df: pd.DataFrame, max_horizon: int = 20):
        """
        Initialize engine and precompute forward direction matrix.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV dataframe with index and 'open', 'close' columns.
        max_horizon : int
            Maximum horizon to compute (default 20 bars).

        Notes
        -----
        RAM usage: n_bars × max_horizon bytes (for bool dtype).
        For 100k bars × 20 horizons ≈ 2 MB.
        """
        self.df = df
        self.max_horizon = max_horizon
        self.forward_matrix = None
        
        self._precompute_forward_matrix()

    def _precompute_forward_matrix(self) -> None:
        """
        Precompute forward direction matrix.

        The matrix is computed fully vectorized:
        - Entry at bar i: next bar's open = open[i+1]
        - Exit at bar i+h: close[i+1+h]
        - Signal: close[i+1+h] > open[i+1]
        """
        logger.info(f"Precomputing forward matrix (horizon={self.max_horizon})...")
        
        n_bars = len(self.df)
        open_prices = self.df["open"].values.astype(np.float32)
        close_prices = self.df["close"].values.astype(np.float32)
        
        # Initialize matrix
        self.forward_matrix = np.zeros((n_bars, self.max_horizon), dtype=bool)
        
        # For each horizon h, compute whether close[i+1+h] > open[i+1]
        for h in range(self.max_horizon):
            # Entry index: i+1 (next bar after signal)
            # Exit index: i+1+h (h bars later)
            exit_idx = np.arange(n_bars) + 1 + h
            entry_idx = np.arange(n_bars) + 1
            
            # Only compute for valid indices (not at end of data)
            valid = exit_idx < n_bars
            
            # Vectorized comparison
            self.forward_matrix[valid, h] = (
                close_prices[exit_idx[valid]] > open_prices[entry_idx[valid]]
            )
        
        logger.info(f"Forward matrix computed: shape {self.forward_matrix.shape}")

    def get_profile_for_condition(
        self,
        condition_mask: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute forward profile for a given condition mask.

        Parameters
        ----------
        condition_mask : np.ndarray
            Boolean mask of shape (n_bars,), True where condition triggers.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray, np.ndarray]
            (prob_bull, sample_size, valid_mask)
            - prob_bull: shape (max_horizon,), probability of bull outcome per horizon
            - sample_size: shape (max_horizon,), count of valid samples per horizon
            - valid_mask: shape (n_bars,), which bars had valid condition evaluation

        Notes
        -----
        - Excludes bars too close to end (where future close unavailable)
        - Returns NaN for horizons with zero valid samples
        """
        n_bars = len(self.df)
        
        # Exclude bars at end (can't compute all horizons)
        valid_mask = condition_mask.copy()
        valid_mask[n_bars - self.max_horizon:] = False
        
        trigger_indices = np.where(valid_mask)[0]
        
        if len(trigger_indices) == 0:
            logger.warning("Condition has no valid trigger points")
            return (
                np.full(self.max_horizon, np.nan),
                np.zeros(self.max_horizon, dtype=int),
                valid_mask,
            )
        
        prob_bull = np.zeros(self.max_horizon, dtype=np.float32)
        sample_size = np.zeros(self.max_horizon, dtype=int)
        
        for h in range(self.max_horizon):
            # Count bull outcomes at this horizon
            bull_count = np.sum(self.forward_matrix[trigger_indices, h])
            n_samples = len(trigger_indices)
            
            prob_bull[h] = bull_count / n_samples if n_samples > 0 else np.nan
            sample_size[h] = n_samples
        
        return prob_bull, sample_size, valid_mask

    def get_baseline_profile(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute unconditional forward profile across entire dataset.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (baseline_prob_bull, baseline_sample_size)

        Notes
        -----
        Used as null hypothesis in significance testing.
        """
        logger.info("Computing baseline forward profile...")
        
        n_bars = len(self.df)
        valid_all = np.ones(n_bars, dtype=bool)
        valid_all[n_bars - self.max_horizon:] = False
        
        baseline_prob = np.zeros(self.max_horizon, dtype=np.float32)
        baseline_size = np.zeros(self.max_horizon, dtype=int)
        
        n_valid = np.sum(valid_all)
        
        for h in range(self.max_horizon):
            valid_indices = np.where(valid_all)[0]
            bull_count = np.sum(self.forward_matrix[valid_indices, h])
            baseline_prob[h] = bull_count / n_valid if n_valid > 0 else 0.5
            baseline_size[h] = n_valid
        
        logger.info(f"Baseline profile computed: {baseline_prob}")
        
        return baseline_prob, baseline_size

    def clear_cache(self) -> None:
        """
        Clear forward matrix from memory (for batch processing multiple symbols).
        """
        if self.forward_matrix is not None:
            del self.forward_matrix
            self.forward_matrix = None
            gc.collect()
            logger.debug("Forward matrix cache cleared")
