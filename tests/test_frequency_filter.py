"""Tests for Phase 4: Frequency Filter."""

import numpy as np
import pandas as pd
import pytest

from edge_research.conditions.frequency_filter import FrequencyFilter


@pytest.fixture
def sample_data_1year():
    """Create one year of hourly data (approx 8760 bars)."""
    n = 8760
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=n, freq='h'),
        'close': np.random.randn(n).cumsum() + 100,
    })
    df.set_index('time', inplace=True)
    return df


def test_frequency_filter_high_occurrence(sample_data_1year):
    """Test condition with high occurrence passes filter."""
    freq_filter = FrequencyFilter(
        sample_data_1year,
        min_occurrence=50,
        min_freq_per_year=10.0,
    )
    
    # Condition occurs 100 times (well above threshold)
    mask = np.zeros(len(sample_data_1year), dtype=bool)
    mask[::87] = True  # ~100 occurrences
    
    assert freq_filter.passes_filter(mask)


def test_frequency_filter_low_occurrence_fails(sample_data_1year):
    """Test condition with low occurrence fails filter."""
    freq_filter = FrequencyFilter(
        sample_data_1year,
        min_occurrence=100,
        min_freq_per_year=20.0,
    )
    
    # Only 10 occurrences (below threshold)
    mask = np.zeros(len(sample_data_1year), dtype=bool)
    mask[::876] = True
    
    assert not freq_filter.passes_filter(mask)


def test_frequency_analysis(sample_data_1year):
    """Test frequency statistics calculation."""
    freq_filter = FrequencyFilter(sample_data_1year)
    
    mask = np.zeros(len(sample_data_1year), dtype=bool)
    mask[::100] = True  # 87-88 occurrences
    
    n_occur, freq_per_year = freq_filter.analyze_condition_frequency(mask)
    
    assert n_occur > 0
    assert freq_per_year > 0
    assert freq_per_year <= 365  # Can't have more than 365 per year on hourly data