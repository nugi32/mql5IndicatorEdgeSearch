"""Tests for combo-aware parameter sensitivity -- the "plateau, not a
spike" check the walk-forward meta-pipeline's candidate selection relies
on for multi-atom (AND) conditions, not just single-indicator ones."""

import numpy as np
import pandas as pd
import pytest

from edge_research.conditions.condition_library import AtomicCondition, CombinedCondition, Operator
from edge_research.forward_profile.engine import ForwardProfileEngine
from edge_research.validation.parameter_sensitivity import (
    sensitivity_test_combined_condition,
    sensitivity_test_condition_generic,
)


@pytest.fixture
def df_and_engine():
    n = 500
    rng = np.random.default_rng(0)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame({
        "open": close - 0.05,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "rsi_14": rng.uniform(0, 100, n),
        "cci_20": rng.uniform(-200, 200, n),
    })
    engine = ForwardProfileEngine(df, max_horizon=5)
    return df, engine


def test_combined_sensitivity_returns_score_when_both_atoms_numeric(df_and_engine):
    df, engine = df_and_engine
    combo = CombinedCondition([
        AtomicCondition("rsi_14", Operator.LT, 30.0),
        AtomicCondition("cci_20", Operator.LT, -100.0),
    ])
    result = sensitivity_test_combined_condition(combo, df, engine, shift_pct=15.0)

    assert not np.isnan(result["sensitivity_score"])
    # 2 atoms x 2 directions (+/-15%) = up to 4 perturbations tested
    assert len(result["per_atom_results"]) <= 4
    assert len(result["per_atom_results"]) > 0


def test_combined_sensitivity_skips_non_numeric_atoms(df_and_engine):
    df, engine = df_and_engine
    df = df.copy()
    df["ma_20"] = df["close"].rolling(20).mean().bfill()
    combo = CombinedCondition([
        AtomicCondition("rsi_14", Operator.LT, 30.0),
        AtomicCondition("ma_20", Operator.GT, "close"),  # non-numeric threshold
    ])
    result = sensitivity_test_combined_condition(combo, df, engine, shift_pct=15.0)

    # Only rsi_14 is shiftable -> at most 2 perturbations (its two directions)
    assert len(result["per_atom_results"]) <= 2
    assert all(r["atom_index"] == 0 for r in result["per_atom_results"])


def test_combined_sensitivity_nan_when_no_numeric_atoms(df_and_engine):
    df, engine = df_and_engine
    df = df.copy()
    df["ma_20"] = df["close"].rolling(20).mean().bfill()
    combo = CombinedCondition([
        AtomicCondition("ma_20", Operator.GT, "close"),
    ])
    result = sensitivity_test_combined_condition(combo, df, engine, shift_pct=15.0)

    assert np.isnan(result["sensitivity_score"])
    assert result["per_atom_results"] == []


def test_generic_dispatch_routes_combined_vs_atomic(df_and_engine):
    df, engine = df_and_engine
    atomic = AtomicCondition("rsi_14", Operator.LT, 30.0)
    combo = CombinedCondition([atomic, AtomicCondition("cci_20", Operator.LT, -100.0)])

    atomic_result = sensitivity_test_condition_generic(atomic, df, engine, shift_pct=15.0)
    combo_result = sensitivity_test_condition_generic(combo, df, engine, shift_pct=15.0)

    # Atomic dispatch returns the atomic-shaped result (has 'shifted_conditions')
    assert "shifted_conditions" in atomic_result
    # Combined dispatch returns the combo-shaped result (has 'per_atom_results')
    assert "per_atom_results" in combo_result
