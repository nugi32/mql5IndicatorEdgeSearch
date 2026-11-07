"""Tests for the holding-bars walk-forward stability check and gate 8."""

import numpy as np
import pandas as pd
import pytest

from edge_research.selection.strategy_gate import GateThresholds, passes_strategy_gate
from edge_research.simulation.trade_simulator import TradeSimConfig, TradeSimResult
from edge_research.validation.walk_forward import (
    WalkForwardValidator,
    validate_holding_bars_walk_forward,
)


@pytest.fixture
def uptrend_df():
    n = 4000
    close = 100.0 + np.arange(n, dtype=np.float64) * 0.1
    return pd.DataFrame({
        "open": close - 0.02,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "atr_14": np.full(n, 1.0),
    }, index=pd.date_range("2024-01-01", periods=n, freq="h"))


def test_holding_bars_stable_true_for_consistent_uptrend(uptrend_df):
    """A holding period that's profitable everywhere should be stable everywhere."""
    mask = np.zeros(len(uptrend_df), dtype=bool)
    mask[::20] = True  # trigger regularly across the whole dataset

    validator = WalkForwardValidator(uptrend_df, train_bars=1000, test_bars=500, step_bars=500)
    assert len(validator.get_windows()) >= 2

    config = TradeSimConfig(direction="long", spread_price_units=0.0, slippage_price_units=0.0)
    result = validate_holding_bars_walk_forward(
        uptrend_df, mask, config, holding_bars=5, validator=validator, min_stable_windows=2,
    )

    assert result["holding_bars_stable"] is True
    assert result["n_windows_positive"] == result["n_windows_evaluated"]


def test_holding_bars_stable_false_when_min_windows_too_strict(uptrend_df):
    """Raising min_stable_windows above what's achievable should flip the flag."""
    mask = np.zeros(len(uptrend_df), dtype=bool)
    mask[::20] = True

    validator = WalkForwardValidator(uptrend_df, train_bars=1000, test_bars=500, step_bars=500)
    n_windows = len(validator.get_windows())

    config = TradeSimConfig(direction="long", spread_price_units=0.0, slippage_price_units=0.0)
    result = validate_holding_bars_walk_forward(
        uptrend_df, mask, config, holding_bars=5, validator=validator,
        min_stable_windows=n_windows + 100,  # impossible to satisfy
    )

    assert result["holding_bars_stable"] is False


def test_holding_bars_stable_false_for_wrong_direction(uptrend_df):
    """A 'short' in a pure uptrend should never be stable."""
    mask = np.zeros(len(uptrend_df), dtype=bool)
    mask[::20] = True

    validator = WalkForwardValidator(uptrend_df, train_bars=1000, test_bars=500, step_bars=500)
    config = TradeSimConfig(direction="short", spread_price_units=0.0, slippage_price_units=0.0)
    result = validate_holding_bars_walk_forward(
        uptrend_df, mask, config, holding_bars=5, validator=validator, min_stable_windows=1,
    )

    assert result["holding_bars_stable"] is False
    assert result["n_windows_positive"] == 0


def _dummy_sim_result(n_trades=50, expectancy_r=0.1, profit_factor=1.5):
    return TradeSimResult(
        n_trades=n_trades, n_wins=30, n_losses=20, n_timeouts=0,
        win_rate=0.6, avg_win_pips=1.0, avg_loss_pips=-0.5,
        expectancy_pips=0.4, expectancy_r=expectancy_r, profit_factor=profit_factor,
        max_drawdown_pips=2.0, equity_curve_pips=np.array([1.0, 2.0]),
        config=TradeSimConfig(),
    )


def test_gate_fails_when_holding_bars_unstable():
    thresholds = GateThresholds()
    passed, reasons = passes_strategy_gate(
        significant=True,
        robust_walk_forward=True,
        permutation_result={"n_trades": 50, "significant": True, "p_value": 0.01},
        sim_result=_dummy_sim_result(),
        thresholds=thresholds,
        holding_bars_stable=False,
    )
    assert passed is False
    assert any("holding period" in r for r in reasons)


def test_gate_passes_when_holding_bars_stable():
    thresholds = GateThresholds()
    passed, reasons = passes_strategy_gate(
        significant=True,
        robust_walk_forward=True,
        permutation_result={"n_trades": 50, "significant": True, "p_value": 0.01},
        sim_result=_dummy_sim_result(),
        thresholds=thresholds,
        holding_bars_stable=True,
    )
    assert passed is True
    assert reasons == []


def test_gate_skips_holding_bars_check_when_disabled():
    thresholds = GateThresholds(require_holding_bars_stable=False)
    passed, reasons = passes_strategy_gate(
        significant=True,
        robust_walk_forward=True,
        permutation_result={"n_trades": 50, "significant": True, "p_value": 0.01},
        sim_result=_dummy_sim_result(),
        thresholds=thresholds,
        holding_bars_stable=False,
    )
    assert passed is True
