"""Tests for Phase 3: Conditions."""

import numpy as np
import pandas as pd
import pytest

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    ConditionEvaluator,
    Operator,
)


@pytest.fixture
def sample_data():
    """Create sample OHLCV data."""
    n = 200
    df = pd.DataFrame(
        {
            "time": pd.date_range("2023-01-01", periods=n, freq="h"),
            "open": 100 + np.arange(n) * 0.1,
            "high": 101 + np.arange(n) * 0.1,
            "low": 99 + np.arange(n) * 0.1,
            "close": 100.5 + np.arange(n) * 0.1,
            "rsi_14": np.concatenate([np.full(50, 25), np.full(150, 75)]),
            "ma_20_ema": 100 + np.arange(n) * 0.05,
            "ma_50_sma": 100 + np.arange(n) * 0.03,
        }
    )
    df.set_index("time", inplace=True)

    for col in df.columns:
        if df[col].dtype in [np.float64, np.int64]:
            df[col] = df[col].astype(np.float32)

    return df


def test_atomic_condition_lt(sample_data):
    """Test less-than comparison."""
    evaluator = ConditionEvaluator(sample_data)
    cond = AtomicCondition("rsi_14", Operator.LT, 50.0)
    mask = evaluator.evaluate_atomic(cond)

    assert mask.dtype == bool
    assert len(mask) == len(sample_data)
    assert np.all(mask[:50])
    assert not np.any(mask[50:])


def test_atomic_condition_gt(sample_data):
    """Test greater-than comparison."""
    evaluator = ConditionEvaluator(sample_data)
    cond = AtomicCondition("rsi_14", Operator.GT, 50.0)
    mask = evaluator.evaluate_atomic(cond)

    assert not np.any(mask[:50])
    assert np.all(mask[50:])


def test_atomic_condition_column_comparison(sample_data):
    """Test column-to-column comparison."""
    evaluator = ConditionEvaluator(sample_data)
    cond = AtomicCondition("ma_20_ema", Operator.GT, "ma_50_sma")
    mask = evaluator.evaluate_atomic(cond)

    assert np.all(mask)


def test_atomic_condition_crosses_above(sample_data):
    """Test crosses_above operator."""
    evaluator = ConditionEvaluator(sample_data)
    cond = AtomicCondition("rsi_14", Operator.CROSSES_ABOVE, 50.0)
    mask = evaluator.evaluate_atomic(cond)

    assert np.any(mask[48:52])


def test_combined_condition(sample_data):
    """Test AND combination of atoms."""
    evaluator = ConditionEvaluator(sample_data)

    atom1 = AtomicCondition("rsi_14", Operator.LT, 50.0)
    atom2 = AtomicCondition("ma_20_ema", Operator.GT, "ma_50_sma")

    combined = CombinedCondition([atom1, atom2])
    mask = evaluator.evaluate_combined(combined)

    assert np.all(mask[:50])
    assert not np.any(mask[50:])


def test_condition_invalid_column(sample_data):
    """Test error handling for invalid column."""
    evaluator = ConditionEvaluator(sample_data)
    cond = AtomicCondition("nonexistent_col", Operator.LT, 50.0)

    with pytest.raises(KeyError):
        evaluator.evaluate_atomic(cond)


def test_no_lookahead_in_atomic_evaluation(sample_data):
    """Regression test: ensure atomic evaluation doesn't use future data."""
    evaluator = ConditionEvaluator(sample_data)

    cond = AtomicCondition("close", Operator.GT, 100.5)
    mask = evaluator.evaluate_atomic(cond)

    for i in range(1, len(sample_data)):
        if mask[i]:
            assert sample_data["close"].iloc[i] > 100.5
