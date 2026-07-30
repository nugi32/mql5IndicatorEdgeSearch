"""Tests for Phase 1: Ingestion."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from edge_research.ingestion.loader import (
    load_csv_and_validate,
    load_from_parquet,
    save_to_parquet,
)


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=100, freq='h'),
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 101,
        'low': np.random.randn(100).cumsum() + 99,
        'close': np.random.randn(100).cumsum() + 100,
        'tick_volume': np.random.randint(100, 1000, 100),
        'rsi_14': np.random.uniform(0, 100, 100),
        'ma_20_ema': np.random.randn(100).cumsum() + 100,
    })
    
    csv_path = tmp_path / "test.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def test_load_csv_validate(sample_csv):
    """Test CSV loading and validation."""
    df = load_csv_and_validate(sample_csv)
    
    assert len(df) == 100
    assert df.index.name == 'time'
    assert df['open'].dtype == np.float32
    assert not df.index.duplicated().any()
    assert df.index.is_monotonic_increasing


def test_save_load_parquet(sample_csv, tmp_path):
    """Test Parquet round-trip."""
    df_orig = load_csv_and_validate(sample_csv)
    
    parquet_path = save_to_parquet(df_orig, tmp_path, 'EURUSD', 'H1')
    
    df_loaded = load_from_parquet(parquet_path)
    
    pd.testing.assert_frame_equal(df_orig, df_loaded)


def test_float32_conversion(sample_csv):
    """Ensure all numeric columns are float32."""
    df = load_csv_and_validate(sample_csv)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        assert df[col].dtype == np.float32, f"Column {col} is not float32"