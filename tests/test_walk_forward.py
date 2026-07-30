"""Tests for walk-forward validation."""

import numpy as np
import pandas as pd
import pytest

from edge_research.validation.walk_forward import WalkForwardValidator


@pytest.fixture
def sample_data_large():
    """Create large dataset for walk-forward testing."""
    n = 10000
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=n, freq='h'),
        'close': 100 + np.cumsum(np.random.randn(n) * 0.5),
    })
    df.set_index('time', inplace=True)
    return df


def test_walk_forward_windows(sample_data_large):
    """Test window generation."""
    validator = WalkForwardValidator(
        sample_data_large,
        train_bars=5000,
        test_bars=1000,
        step_bars=500,
    )
    
    windows = validator.get_windows()
    
    assert len(windows) > 0
    
    for train_start, train_end, test_start, test_end in windows:
        assert train_start < train_end
        assert test_start == train_end
        assert test_end > test_start
        assert train_end - train_start == 5000
        assert test_end - test_start == 1000


def test_window_data_retrieval(sample_data_large):
    """Test retrieving window data."""
    validator = WalkForwardValidator(sample_data_large, 1000, 500, 250)
    
    train_df, test_df = validator.get_window_data(0)
    
    assert len(train_df) == 1000
    assert len(test_df) == 500
    assert train_df.index[-1] < test_df.index[0]