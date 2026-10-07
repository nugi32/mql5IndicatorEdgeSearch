"""
Regime stress tests: trending vs ranging, high vol vs low vol.
"""

import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeClassifier:
    """Classify market regimes (trending, ranging, high-vol, low-vol)."""

    def __init__(
        self,
        df: pd.DataFrame,
        adx_trending: float = 25.0,
        atr_percentile_low: float = 25.0,
        atr_percentile_high: float = 75.0,
    ):
        """
        Initialize classifier.

        Parameters
        ----------
        df : pd.DataFrame
            Dataframe with ADX and ATR columns.
        adx_trending : float
            ADX threshold for trending classification.
        atr_percentile_low : float
            Low ATR percentile threshold.
        atr_percentile_high : float
            High ATR percentile threshold.
        """
        self.df = df
        self.adx_trending = adx_trending
        self.atr_percentile_low = atr_percentile_low
        self.atr_percentile_high = atr_percentile_high

        self._classify_regimes()

    def _classify_regimes(self) -> None:
        """Classify each bar into regime."""
        n = len(self.df)

        # Trending vs ranging
        if "adx_14" in self.df.columns:
            adx = self.df["adx_14"].values
            self.is_trending = adx > self.adx_trending
            self.is_ranging = adx <= self.adx_trending
        else:
            logger.warning("ADX not found; all bars classified as ranging")
            self.is_trending = np.zeros(n, dtype=bool)
            self.is_ranging = np.ones(n, dtype=bool)

        # High vol vs low vol
        if "atr_14" in self.df.columns:
            atr = self.df["atr_14"].values
            atr_low = np.nanpercentile(atr, self.atr_percentile_low)
            atr_high = np.nanpercentile(atr, self.atr_percentile_high)

            self.is_high_vol = atr > atr_high
            self.is_low_vol = atr < atr_low
            self.is_normal_vol = ~(self.is_high_vol | self.is_low_vol)
        else:
            logger.warning("ATR not found; all bars classified as normal vol")
            self.is_high_vol = np.zeros(n, dtype=bool)
            self.is_low_vol = np.zeros(n, dtype=bool)
            self.is_normal_vol = np.ones(n, dtype=bool)

        logger.info(
            f"Regime classification: "
            f"trending={np.sum(self.is_trending)}, "
            f"high_vol={np.sum(self.is_high_vol)}"
        )

    def get_regime_mask(self, regime: str) -> np.ndarray:
        """
        Get boolean mask for a specific regime.

        Parameters
        ----------
        regime : str
            One of: 'trending', 'ranging', 'high_vol', 'low_vol', 'normal_vol'

        Returns
        -------
        np.ndarray
            Boolean mask.
        """
        if regime == "trending":
            return self.is_trending
        elif regime == "ranging":
            return self.is_ranging
        elif regime == "high_vol":
            return self.is_high_vol
        elif regime == "low_vol":
            return self.is_low_vol
        elif regime == "normal_vol":
            return self.is_normal_vol
        else:
            raise ValueError(f"Unknown regime: {regime}")


def stress_test_condition_by_regime(
    condition_mask: np.ndarray,
    forward_engine,
    classifier: RegimeClassifier,
) -> Dict:
    """
    Break down condition's performance by regime.

    Parameters
    ----------
    condition_mask : np.ndarray
        Condition mask on full data.
    forward_engine :
        ForwardProfileEngine instance.
    classifier : RegimeClassifier
        Initialized regime classifier.

    Returns
    -------
    dict
        {
            'regime_results': {
                'trending': {'prob_bull': arr, 'n_samples': int},
                'ranging': {...},
                'high_vol': {...},
                'low_vol': {...},
            },
            'most_robust_regime': str,
        }
    """
    regime_results = {}

    for regime in ["trending", "ranging", "high_vol", "low_vol"]:
        regime_mask = classifier.get_regime_mask(regime)
        combined_mask = condition_mask & regime_mask

        # Exclude end-of-data bars
        combined_mask[len(combined_mask) - forward_engine.max_horizon:] = False

        trigger_indices = np.where(combined_mask)[0]

        if len(trigger_indices) == 0:
            regime_results[regime] = {
                'prob_bull': np.full(forward_engine.max_horizon, np.nan),
                'n_samples': 0,
            }
            continue

        probs = np.zeros(forward_engine.max_horizon)
        for h in range(forward_engine.max_horizon):
            bull_count = np.sum(forward_engine.forward_matrix[trigger_indices, h])
            probs[h] = bull_count / len(trigger_indices)

        regime_results[regime] = {
            'prob_bull': probs,
            'n_samples': len(trigger_indices),
        }

    # Determine most robust regime (highest mean prob_bull with sufficient samples)
    best_regime = None
    best_mean_prob = -np.inf

    for regime, res in regime_results.items():
        if res['n_samples'] >= 10:
            mean_prob = np.nanmean(res['prob_bull'])
            if mean_prob > best_mean_prob:
                best_mean_prob = mean_prob
                best_regime = regime

    return {
        'regime_results': regime_results,
        'most_robust_regime': best_regime,
    }
