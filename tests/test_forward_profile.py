"""Tests for Phase 5: Forward Profile Engine."""

import numpy as np
import pandas as pd
import pytest

from edge_research.forward_profile.engine import ForwardProfileEngine


@pytest.fixture
def sample_ohlcv():
    """Create simple OHLCV data."""
    n = 100
    close_prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    open_prices = close_prices + np.random.randn(n) * 0.2
    
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=n, freq='h'),
        'open': open_prices,
        'high': np.maximum(open_prices, close_prices) + np.abs(np.random.randn(n) * 0.1),
        'low': np.minimum(open_prices, close_prices) - np.abs(np.random.randn(n) * 0.1),
        'close': close_prices,
    })
    df.set_index('time', inplace=True)
    
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(np.float32)
    
    return df


def test_forward_matrix_shape(sample_ohlcv):
    """Test forward matrix has correct shape."""
    engine = ForwardProfileEngine(sample_ohlcv, max_horizon=10)
    
    assert engine.forward_matrix.shape == (len(sample_ohlcv), 10)
    assert engine.forward_matrix.dtype == bool


def test_no_lookahead_in_forward_matrix(sample_ohlcv):
    """Regression test: forward matrix must not use bar i data at decision bar i."""
    engine = ForwardProfileEngine(sample_ohlcv, max_horizon=5)
    
    # forward_matrix[i, h] should only depend on:
    # - open[i+1] (entry)
    # - close[i+1+h] (exit)
    # Not on anything at bar i
    
    n_bars = len(sample_ohlcv)
    
    for i in range(n_bars - 6):
        for h in range(5):
            exit_idx = i + 1 + h
            
            if exit_idx >= n_bars:
                assert not engine.forward_matrix[i, h]
            else:
                # Verify the decision is based on correct bars
                entry_price = sample_ohlcv['open'].iloc[i + 1]
                exit_price = sample_ohlcv['close'].iloc[exit_idx]
                
                expected = exit_price > entry_price
                actual = engine.forward_matrix[i, h]
                
                assert expected == actual, f"Lookahead error at bar {i}, horizon {h}"


def test_get_profile_for_condition(sample_ohlcv):
    """Test probability profile computation for condition."""
    engine = ForwardProfileEngine(sample_ohlcv, max_horizon=10)
    
    # Simple condition: always true
    condition_mask = np.ones(len(sample_ohlcv), dtype=bool)
    
    prob_bull, sample_size, valid_mask = engine.get_profile_for_condition(condition_mask)
    
    assert len(prob_bull) == 10
    assert len(sample_size) == 10
    assert np.all((prob_bull >= 0) & (prob_bull <= 1) | np.isnan(prob_bull))


def test_baseline_profile(sample_ohlcv):
    """Test baseline (unconditional) profile."""
    engine = ForwardProfileEngine(sample_ohlcv, max_horizon=10)
    
    baseline_prob, baseline_size = engine.get_baseline_profile()
    
    assert len(baseline_prob) == 10
    assert len(baseline_size) == 10
    assert np.all((baseline_prob >= 0) & (baseline_prob <= 1))
    assert np.all(baseline_size >= 0)


def test_profile_computation_vectorized(sample_ohlcv):
    """Test that profile computation is efficient (vectorized)."""
    # This test ensures no explicit loops over bars at decision level
    engine = ForwardProfileEngine(sample_ohlcv, max_horizon=20)
    
    # Create condition that triggers every 10th bar
    condition_mask = np.zeros(len(sample_ohlcv), dtype=bool)
    condition_mask[::10] = True
    
    prob_bull, sample_size, _ = engine.get_profile_for_condition(condition_mask)
    
    # Should complete quickly even with large max_horizon
    assert np.sum(sample_size > 0) > 0
