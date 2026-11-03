"""
Walk-forward validation: rolling train/test splits.
"""

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

from edge_research.simulation.trade_simulator import (
    TradeSimConfig,
    compute_r_multiples_for_horizon,
)

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Rolling window train/test validator."""

    def __init__(
        self,
        df: pd.DataFrame,
        train_bars: int = 5000,
        test_bars: int = 1000,
        step_bars: int = 500,
    ):
        """
        Initialize validator.

        Parameters
        ----------
        df : pd.DataFrame
            Full dataframe with datetime index.
        train_bars : int
            Training window size.
        test_bars : int
            Test window size.
        step_bars : int
            Step size between windows.
        """
        self.df = df
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars
        
        self.windows = self._generate_windows()

    def _generate_windows(self) -> List[Tuple[int, int, int, int]]:
        """
        Generate (train_start, train_end, test_start, test_end) indices.

        Returns
        -------
        List[Tuple[int, int, int, int]]
            List of (train_start, train_end, test_start, test_end) index pairs.
        """
        windows = []
        n = len(self.df)
        
        train_start = 0
        while True:
            train_end = train_start + self.train_bars
            test_start = train_end
            test_end = test_start + self.test_bars
            
            if test_end > n:
                break
            
            windows.append((train_start, train_end, test_start, test_end))
            train_start += self.step_bars
        
        logger.info(f"Generated {len(windows)} walk-forward windows")
        return windows

    def get_windows(self) -> List[Tuple[int, int, int, int]]:
        """Return list of windows."""
        return self.windows

    def get_window_data(
        self,
        window_idx: int,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get train and test dataframes for a window.

        Parameters
        ----------
        window_idx : int
            Window index.

        Returns
        -------
        Tuple[pd.DataFrame, pd.DataFrame]
            (train_df, test_df)
        """
        train_start, train_end, test_start, test_end = self.windows[window_idx]
        
        train_df = self.df.iloc[train_start:train_end]
        test_df = self.df.iloc[test_start:test_end]
        
        return train_df, test_df


def validate_condition_walk_forward(
    full_df: pd.DataFrame,
    condition_mask: np.ndarray,
    condition_prob: np.ndarray,
    forward_engine,
    validator: WalkForwardValidator,
    direction: str = "long",
) -> dict:
    """
    Validate a condition's edge across walk-forward windows.

    Parameters
    ----------
    full_df : pd.DataFrame
        Full dataframe.
    condition_mask : np.ndarray
        Condition mask on full data.
    condition_prob : np.ndarray
        Probability profile on full data.
    forward_engine :
        ForwardProfileEngine instance.
    validator : WalkForwardValidator
        Walk-forward validator.
    direction : str
        "long" or "short". BUG FIX: this parameter was missing entirely --
        the consistency check below used to hardcode
        `np.all(window_probs > 0.5)`, i.e. it only ever recognized a
        condition as "direction consistent" if every window's forward bull
        probability was ABOVE 0.5, regardless of whether the condition's
        actual edge was bullish or bearish. For a genuinely bearish/short
        condition (correctly and consistently showing prob_bull BELOW 0.5
        in every single window -- exactly what "consistent" should mean
        for a short), this hardcoded check reported
        edge_direction_consistent=False every time, since prob_bull > 0.5
        was never true for a real short edge. This is the same class of
        long-only assumption bug fixed in CostModel.apply_costs_to_forward_profile
        -- pass infer_direction(...) here too, the same value used there and
        in Phase 7c, so a genuinely consistent short edge isn't rejected by
        the walk-forward gate purely because it never happened to look
        bullish.

    Returns
    -------
    dict
        {
            'edge_direction_consistent': bool,
            'edge_magnitude_std': float,
            'window_results': [{'window': int, 'prob_bull': arr, ...}]
        }
    """
    window_probs = []
    window_results = []
    
    for window_idx, (train_start, train_end, test_start, test_end) in enumerate(validator.get_windows()):
        # Use test set for validation
        test_mask = condition_mask[test_start:test_end].copy()
        test_mask[len(test_mask) - forward_engine.max_horizon:] = False
        
        if np.sum(test_mask) == 0:
            continue
        
        # Recompute forward profile on test set
        test_forward_matrix = forward_engine.forward_matrix[test_start:test_end]
        
        trigger_indices = np.where(test_mask)[0]
        
        test_probs = np.zeros(forward_engine.max_horizon)
        for h in range(forward_engine.max_horizon):
            bull_count = np.sum(test_forward_matrix[trigger_indices, h])
            test_probs[h] = bull_count / len(trigger_indices) if len(trigger_indices) > 0 else 0.5
        
        window_probs.append(test_probs)
        window_results.append({
            'window': window_idx,
            'prob_bull': test_probs,
            'n_samples': np.sum(test_mask),
        })
    
    if not window_probs:
        logger.warning("No valid windows for walk-forward validation")
        return {
            'edge_direction_consistent': False,
            'edge_magnitude_std': np.nan,
            'window_results': [],
        }
    
    window_probs = np.array(window_probs)

    # Check consistency: every window's forward bull probability must sit
    # on the SAME side of 0.5 that this condition's own inferred direction
    # predicts -- above 0.5 for "long", below 0.5 for "short". (Previously
    # hardcoded to "> 0.5" regardless of direction -- see docstring.)
    mean_probs_per_horizon = np.nanmean(window_probs, axis=0)
    if direction == "short":
        direction_consistent = np.all(mean_probs_per_horizon < 0.5)
    else:
        direction_consistent = np.all(mean_probs_per_horizon > 0.5)
    
    # Check magnitude stability: std of prob_bull across windows
    magnitude_std = np.nanstd(window_probs)
    
    return {
        'edge_direction_consistent': direction_consistent,
        'edge_magnitude_std': float(magnitude_std),
        'window_results': window_results,
    }


def validate_holding_bars_walk_forward(
    full_df: pd.DataFrame,
    condition_mask: np.ndarray,
    sim_config: TradeSimConfig,
    holding_bars: int,
    validator: WalkForwardValidator,
    min_stable_windows: int,
) -> dict:
    """
    Check whether an already-selected holding period (from
    edge_research.simulation.trade_simulator.scan_holding_horizons /
    select_best_holding_bars, chosen on the FULL dataset) still produces a
    positive cost-adjusted R-multiple out-of-sample, window by window.

    This is deliberately NOT "re-run the horizon scan independently on
    each window and see if it agrees" -- with a wide horizon-candidate
    range and many windows, that would just multiply the number of
    in-sample selections being made (more multiple-testing, not less).
    Instead, this fixes `holding_bars` at the value already chosen on the
    full sample and asks the narrower, more defensible question: does
    THIS SPECIFIC horizon still show a positive mean R-multiple on data it
    wasn't selected from? A horizon that only "worked" because the
    full-sample scan overfit to noise will tend to fail this check in
    most windows, the same way a genuinely direction-inconsistent edge
    fails `validate_condition_walk_forward` above.

    Parameters
    ----------
    full_df : pd.DataFrame
        Full dataframe (must contain 'open', 'close', sim_config.atr_column).
    condition_mask : np.ndarray
        Condition mask on full data.
    sim_config : TradeSimConfig
        Direction and cost fields are used; `holding_bars` on this object
        is ignored in favor of the `holding_bars` argument (so callers can
        pass the same base config used elsewhere without mutating it).
    holding_bars : int
        The horizon already selected on the full sample, to be checked.
    validator : WalkForwardValidator
        Same walk-forward windows used for direction-consistency checking.
    min_stable_windows : int
        Minimum number of windows (with at least one valid trade) in which
        this holding period must show a positive mean R-multiple for
        `holding_bars_stable` to be True. Sourced from pipeline_config.yaml
        (`horizon_min_stable_windows`) so it can be tuned per dataset size
        rather than hardcoded.

    Returns
    -------
    dict
        {
            'holding_bars': int,
            'holding_bars_stable': bool,
            'n_windows_evaluated': int,   # windows with >=1 valid trade
            'n_windows_positive': int,    # of those, how many had mean_r > 0
            'min_stable_windows_required': int,
            'window_results': [{'window': int, 'n_trades': int, 'mean_r': float}],
        }
    """
    window_results = []
    n_windows_positive = 0
    n_windows_evaluated = 0

    for window_idx, (train_start, train_end, test_start, test_end) in enumerate(validator.get_windows()):
        test_mask_full = np.zeros_like(condition_mask)
        test_mask_full[test_start:test_end] = condition_mask[test_start:test_end]

        if np.sum(test_mask_full) == 0:
            continue

        r = compute_r_multiples_for_horizon(full_df, test_mask_full, sim_config, holding_bars)
        n_h = len(r)
        if n_h == 0:
            continue

        mean_r = float(np.mean(r))
        n_windows_evaluated += 1
        is_positive = mean_r > 0
        if is_positive:
            n_windows_positive += 1

        window_results.append({
            'window': window_idx,
            'n_trades': n_h,
            'mean_r': mean_r,
        })

    holding_bars_stable = n_windows_positive >= min_stable_windows

    if n_windows_evaluated == 0:
        logger.warning(
            f"No valid walk-forward windows to evaluate holding_bars={holding_bars} "
            f"stability -- defaulting holding_bars_stable=False"
        )
        holding_bars_stable = False

    return {
        'holding_bars': holding_bars,
        'holding_bars_stable': holding_bars_stable,
        'n_windows_evaluated': n_windows_evaluated,
        'n_windows_positive': n_windows_positive,
        'min_stable_windows_required': min_stable_windows,
        'window_results': window_results,
    }
