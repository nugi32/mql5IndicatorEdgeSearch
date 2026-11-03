"""
Phase 6: Statistical Testing

Two-sided proportion z-test + Benjamini-Hochberg FDR correction.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from scipy import stats
except ImportError:  # pragma: no cover - optional dependency fallback
    stats = None

try:
    from statsmodels.stats.multitest import multipletests
except ImportError:  # pragma: no cover - optional dependency fallback
    multipletests = None

logger = logging.getLogger(__name__)


def wilson_ci(
    successes: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """
    Compute Wilson score confidence interval for a binomial proportion.

    Parameters
    ----------
    successes : int
        Number of successes (bull outcomes).
    n : int
        Total number of trials.
    confidence : float
        Confidence level (default 0.95 for 95% CI).

    Returns
    -------
    Tuple[float, float]
        (lower, upper) bounds of confidence interval.

    Notes
    -----
    Wilson CI is more accurate than normal approximation, especially for
    small sample sizes and proportions near 0 or 1.
    """
    if n == 0:
        return (np.nan, np.nan)
    
    if stats is None:
        # Fallback using a normal approximation with a conservative default.
        z = 1.96
    else:
        z = stats.norm.ppf((1 + confidence) / 2)
    
    p_hat = successes / n
    denominator = 1 + z**2 / n
    
    center = (p_hat + z**2 / (2 * n)) / denominator
    margin = z * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denominator
    
    lower = center - margin
    upper = center + margin

    if np.isclose(lower, 0.0, atol=1e-15):
        lower = 0.0
    if np.isclose(upper, 1.0, atol=1e-15):
        upper = 1.0

    return (max(0.0, lower), min(1.0, upper))


def proportion_ztest_per_horizon(
    cond_bull_counts: np.ndarray,
    cond_sample_sizes: np.ndarray,
    baseline_prob: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run two-sided proportion z-test for each horizon.

    Parameters
    ----------
    cond_bull_counts : np.ndarray
        Bull outcome counts per horizon, shape (max_horizon,).
    cond_sample_sizes : np.ndarray
        Sample sizes per horizon.
    baseline_prob : np.ndarray
        Null hypothesis (baseline) probability per horizon.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (p_values, test_statistics) per horizon
    """
    max_horizon = len(baseline_prob)
    p_values = np.zeros(max_horizon)
    test_stats = np.zeros(max_horizon)
    
    for h in range(max_horizon):
        bull_count = cond_bull_counts[h]
        n = cond_sample_sizes[h]
        p0 = baseline_prob[h]
        
        if n == 0 or np.isnan(p0):
            p_values[h] = np.nan
            test_stats[h] = np.nan
            continue
        
        # Observed proportion
        p_obs = bull_count / n
        
        # Standard error under null
        se = np.sqrt(p0 * (1 - p0) / n)
        
        if se == 0:
            p_values[h] = 1.0
            test_stats[h] = 0.0
            continue
        
        # Z-test
        z_stat = (p_obs - p0) / se
        if stats is None:
            # scipy not installed -- fall back to the standard library's
            # math.erf (numpy itself has never had a top-level np.erf;
            # calling it always raised AttributeError regardless of numpy
            # version, this fallback path was simply never exercised
            # until scipy was missing).
            p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(z_stat) / math.sqrt(2))))
        else:
            p_val = 2 * (1 - stats.norm.cdf(abs(z_stat)))  # Two-sided
        
        p_values[h] = p_val
        test_stats[h] = z_stat
    
    return p_values, test_stats


def apply_bh_correction(
    p_values: np.ndarray,
    alpha: float = 0.05,
    method: str = "fdr_bh",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Apply Benjamini-Hochberg FDR correction.

    Parameters
    ----------
    p_values : np.ndarray
        Raw p-values.
    alpha : float
        Significance level.
    method : str
        Multiple testing correction method ('fdr_bh', 'fdr_by', 'bonferroni', etc).

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (reject_flags, adjusted_p_values)
    """
    # Filter NaN values for statsmodels
    valid_mask = ~np.isnan(p_values)
    
    if not np.any(valid_mask):
        return np.zeros_like(p_values, dtype=bool), p_values.copy()
    
    p_valid = p_values[valid_mask]
    if multipletests is None:
        # statsmodels not installed -- fall back to a manual BH
        # implementation. BUG FIX: this previously computed
        # `p_sorted[m-1-i] * (m-i)/(m-i)`, which is always `* 1`
        # (numerator and denominator are identical) -- i.e. it silently
        # returned the RAW p-values unadjusted for multiple testing
        # whenever statsmodels was missing, letting more false positives
        # through as "significant" than the FDR correction is supposed to
        # allow. Correct BH: for the k-th smallest p-value out of m (rank
        # j = k+1, 1-indexed), adjusted p-value = p_(j) * m / j, then
        # enforce monotonicity via the cumulative-min pass below
        # (unchanged, that part was already correct).
        order = np.argsort(p_valid)
        p_sorted = p_valid[order]
        m = len(p_sorted)
        p_adj_sorted = np.empty_like(p_sorted)
        for i in range(m):
            rank = m - i  # 1-indexed rank of p_sorted[m-1-i]
            p_adj_sorted[m - 1 - i] = min(1.0, p_sorted[m - 1 - i] * m / rank)
        p_adj_sorted = np.minimum.accumulate(p_adj_sorted[::-1])[::-1]
        p_adj_valid = np.empty_like(p_valid)
        p_adj_valid[order] = p_adj_sorted
        reject = p_adj_valid <= alpha
    else:
        reject, p_adj_valid, _, _ = multipletests(p_valid, alpha=alpha, method=method)
    
    # Reconstruct full arrays
    p_adj = np.full_like(p_values, np.nan)
    reject_full = np.zeros_like(p_values, dtype=bool)
    
    p_adj[valid_mask] = p_adj_valid
    reject_full[valid_mask] = reject
    
    return reject_full, p_adj


class SignificanceAnalyzer:
    """Orchestrates statistical testing for conditions."""

    def __init__(self, alpha: float = 0.05, fdr_method: str = "fdr_bh"):
        """
        Initialize analyzer.

        Parameters
        ----------
        alpha : float
            Significance level.
        fdr_method : str
            FDR correction method.
        """
        self.alpha = alpha
        self.fdr_method = fdr_method

    def test_condition_horizons(
        self,
        cond_prob_bull: np.ndarray,
        cond_sample_sizes: np.ndarray,
        baseline_prob: np.ndarray,
        baseline_sample_sizes: np.ndarray,
    ) -> pd.DataFrame:
        """
        Test a condition's significance across all horizons with FDR correction.

        Parameters
        ----------
        cond_prob_bull : np.ndarray
            Condition's bull probability per horizon.
        cond_sample_sizes : np.ndarray
            Condition's sample sizes.
        baseline_prob : np.ndarray
            Baseline bull probability.
        baseline_sample_sizes : np.ndarray
            Baseline sample sizes.

        Returns
        -------
        pd.DataFrame
            Results table with columns:
            [horizon, prob_bull, sample_size, p_value, p_adj, significant,
             ci_lower, ci_upper, effect_size]
        """
        max_horizon = len(baseline_prob)
        
        # Convert probabilities to counts for z-test
        cond_bull_counts = (cond_prob_bull * cond_sample_sizes).astype(int)
        
        # Run z-tests
        p_values, z_stats = proportion_ztest_per_horizon(
            cond_bull_counts,
            cond_sample_sizes,
            baseline_prob,
        )
        
        # Apply FDR correction across horizons
        reject, p_adj = apply_bh_correction(p_values, self.alpha, self.fdr_method)
        
        # Compute confidence intervals and effect sizes
        ci_lowers = np.zeros(max_horizon)
        ci_uppers = np.zeros(max_horizon)
        effect_sizes = np.zeros(max_horizon)
        
        for h in range(max_horizon):
            lower, upper = wilson_ci(cond_bull_counts[h], cond_sample_sizes[h])
            ci_lowers[h] = lower
            ci_uppers[h] = upper
            
            # Effect size: difference in proportions
            effect_sizes[h] = (cond_prob_bull[h] - baseline_prob[h])
        
        results_df = pd.DataFrame({
            "horizon": np.arange(1, max_horizon + 1),
            "prob_bull": cond_prob_bull,
            "sample_size": cond_sample_sizes,
            "p_value": p_values,
            "p_adj": p_adj,
            "significant": reject,
            "ci_lower": ci_lowers,
            "ci_upper": ci_uppers,
            "effect_size": effect_sizes,
        })
        
        return results_df

    def select_optimal_horizon(self, results_df: pd.DataFrame) -> Optional[int]:
        """
        Select the optimal horizon from significance test results.

        Parameters
        ----------
        results_df : pd.DataFrame
            Results from test_condition_horizons().

        Returns
        -------
        Optional[int]
            Horizon (1-indexed) with strongest edge, or None if no significant horizon.

        Notes
        -----
        Selection rule:
        1. Filter to significant horizons (p_adj < alpha)
        2. Among significant, pick horizon with maximum effect_size
        3. Tiebreaker: tightest confidence interval (smallest upper - lower)
        """
        sig_df = results_df[results_df["significant"]].copy()
        
        if len(sig_df) == 0:
            return None
        
        # Sort by effect size (descending), then by CI width (ascending)
        sig_df["ci_width"] = sig_df["ci_upper"] - sig_df["ci_lower"]
        sig_df = sig_df.sort_values(
            by=["effect_size", "ci_width"],
            ascending=[False, True],
        )
        
        return int(sig_df.iloc[0]["horizon"])

    def test_batch_conditions(
        self,
        condition_results: List[Dict],
        baseline_prob: np.ndarray,
        baseline_sample_sizes: np.ndarray,
    ) -> List[Dict]:
        """
        Test multiple conditions (FDR-corrected across conditions + horizons).

        Parameters
        ----------
        condition_results : List[Dict]
            List of dicts with keys 'prob_bull', 'sample_sizes'.
        baseline_prob : np.ndarray
            Baseline probabilities.
        baseline_sample_sizes : np.ndarray
            Baseline sample sizes.

        Returns
        -------
        List[Dict]
            Updated condition_results with 'significance_results', 'optimal_horizon', 'rejected' keys.

        Notes
        -----
        Applies two levels of FDR correction:
        1. Within each condition: across horizons
        2. Across all conditions: all p-values pooled
        """
        logger.info(f"Testing {len(condition_results)} conditions with FDR correction...")
        
        # First pass: per-condition testing
        all_p_values = []
        condition_p_dfs = []
        
        for cond_res in condition_results:
            p_df = self.test_condition_horizons(
                cond_res["prob_bull"],
                cond_res["sample_sizes"],
                baseline_prob,
                baseline_sample_sizes,
            )
            condition_p_dfs.append(p_df)
            all_p_values.extend(p_df["p_value"].dropna().values)
        
        # Second pass: global FDR correction across all tests
        if all_p_values:
            all_p_array = np.array(all_p_values)
            _, p_adj_global = apply_bh_correction(all_p_array, self.alpha, self.fdr_method)
            
            # Map back to conditions
            p_idx = 0
            for i, cond_res in enumerate(condition_results):
                p_df = condition_p_dfs[i]
                p_df_valid = p_df[~p_df["p_value"].isna()]
                n_p = len(p_df_valid)
                
                p_df.loc[p_df["p_value"].notna(), "p_adj"] = p_adj_global[p_idx : p_idx + n_p]
                p_df["significant"] = p_df["p_adj"] < self.alpha
                
                p_idx += n_p
                
                # Select optimal horizon
                optimal_h = self.select_optimal_horizon(p_df)
                
                cond_res["significance_results"] = p_df
                cond_res["optimal_horizon"] = optimal_h
                cond_res["rejected"] = optimal_h is None
        
        logger.info(
            f"Testing complete: "
            f"{sum(1 for c in condition_results if not c.get('rejected', True))} "
            f"conditions passed significance"
        )
        
        return condition_results
