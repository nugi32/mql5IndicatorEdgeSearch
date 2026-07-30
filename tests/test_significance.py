"""Tests for Phase 6: Significance Testing."""

import numpy as np
import pandas as pd
import pytest

from edge_research.forward_profile.significance import (
    SignificanceAnalyzer,
    apply_bh_correction,
    proportion_ztest_per_horizon,
    wilson_ci,
)


def test_wilson_ci():
    """Test Wilson confidence interval computation."""
    # 50 successes out of 100
    lower, upper = wilson_ci(50, 100, confidence=0.95)
    
    assert 0 <= lower <= upper <= 1
    assert lower < 0.5 < upper
    
    # Wider interval for smaller sample
    lower2, upper2 = wilson_ci(5, 10, confidence=0.95)
    assert (upper2 - lower2) > (upper - lower)


def test_wilson_ci_edge_cases():
    """Test Wilson CI edge cases."""
    # All successes
    lower, upper = wilson_ci(100, 100)
    assert lower > 0.9
    assert upper == 1.0
    
    # No successes
    lower, upper = wilson_ci(0, 100)
    assert lower == 0.0
    assert upper < 0.1
    
    # Empty sample
    lower, upper = wilson_ci(0, 0)
    assert np.isnan(lower) and np.isnan(upper)


def test_proportion_ztest_per_horizon():
    """Test z-test across horizons."""
    # Condition: 60% bull vs baseline 50%
    cond_bull_counts = np.array([60, 65, 70], dtype=int)
    cond_sample_sizes = np.array([100, 100, 100], dtype=int)
    baseline_prob = np.array([0.5, 0.5, 0.5])
    
    p_values, z_stats = proportion_ztest_per_horizon(
        cond_bull_counts,
        cond_sample_sizes,
        baseline_prob,
    )
    
    assert len(p_values) == 3
    assert len(z_stats) == 3
    assert np.all(p_values > 0)
    assert np.all(p_values < 1)


def test_bh_correction():
    """Test Benjamini-Hochberg FDR correction."""
    # Create some p-values (mix of significant and non-significant)
    p_values = np.array([0.001, 0.005, 0.01, 0.1, 0.5, np.nan])
    
    reject, p_adj = apply_bh_correction(p_values, alpha=0.05)
    
    assert len(reject) == len(p_values)
    assert len(p_adj) == len(p_values)
    # At least one should be significant
    assert np.any(reject[~np.isnan(p_values)])
    # NaN should remain NaN
    assert np.isnan(p_adj[-1])


def test_significance_analyzer():
    """Test full significance analyzer."""
    analyzer = SignificanceAnalyzer(alpha=0.05)
    
    cond_prob_bull = np.array([0.55, 0.60, 0.65])
    cond_sample_sizes = np.array([100, 100, 100])
    baseline_prob = np.array([0.5, 0.5, 0.5])
    baseline_sample_sizes = np.array([1000, 1000, 1000])
    
    results_df = analyzer.test_condition_horizons(
        cond_prob_bull,
        cond_sample_sizes,
        baseline_prob,
        baseline_sample_sizes,
    )
    
    assert len(results_df) == 3
    assert 'p_value' in results_df.columns
    assert 'p_adj' in results_df.columns
    assert 'significant' in results_df.columns
    assert 'ci_lower' in results_df.columns
    assert 'ci_upper' in results_df.columns


def test_optimal_horizon_selection():
    """Test selection of optimal horizon."""
    analyzer = SignificanceAnalyzer(alpha=0.05)
    
    # Create results with one significant horizon
    results_df = pd.DataFrame({
        'horizon': [1, 2, 3],
        'prob_bull': [0.52, 0.65, 0.60],
        'sample_size': [100, 100, 100],
        'p_value': [0.3, 0.001, 0.01],
        'p_adj': [0.3, 0.001, 0.01],
        'significant': [False, True, True],
        'ci_lower': [0.45, 0.58, 0.53],
        'ci_upper': [0.59, 0.72, 0.67],
        'effect_size': [0.02, 0.15, 0.10],
    })
    
    optimal_h = analyzer.select_optimal_horizon(results_df)
    
    # Should select horizon 2 (highest effect_size among significant)
    assert optimal_h == 2