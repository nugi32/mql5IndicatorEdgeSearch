"""
Tests for Phase 6b's cost model -- in particular, that its round-trip
spread/slippage cost convention matches trade_simulator.py's (Phase 7c)
exactly. These two modules independently estimate transaction cost for
the same trade, and if their conventions diverge, Phase 6b's pre-filter
(meant to be a lenient early screen) can silently become STRICTER than
Phase 7c's full simulation, rejecting every candidate before it ever
gets a fair evaluation -- see the BUG FIX note in
CostModel.apply_costs_to_forward_profile's docstring.
"""

import numpy as np
import pandas as pd
import pytest

from edge_research.forward_profile.engine import ForwardProfileEngine
from edge_research.simulation.trade_simulator import TradeSimConfig, simulate_condition
from edge_research.validation.cost_model import CostModel, cost_aware_prefilter


@pytest.fixture
def trending_df():
    n = 200
    close = 100.0 + np.arange(n, dtype=np.float64) * 0.05
    return pd.DataFrame({
        "open": close - 0.01,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "atr_14": np.full(n, 1.0),
    }, index=pd.date_range("2024-01-01", periods=n, freq="h"))


def test_total_cost_is_spread_plus_slippage_not_double(trending_df):
    """
    Round-trip cost for one trade must equal spread_pips + slippage_pips
    exactly (in price units), NOT 2 * (spread_pips + slippage_pips).
    """
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[10] = True

    spread_pips, slippage_pips, pip_value = 30.0, 1.0, 0.01
    cost_model = CostModel(
        spread_pips=spread_pips, slippage_pips=slippage_pips, pip_value=pip_value,
    )
    engine = ForwardProfileEngine(trending_df, max_horizon=10)

    result = cost_model.apply_costs_to_forward_profile(
        mask, trending_df, engine, optimal_horizon=5, direction="long",
    )

    expected_total_cost_pips = spread_pips + slippage_pips  # NOT * 2
    assert result["total_cost_pips"] == pytest.approx(expected_total_cost_pips)


def test_cost_model_matches_trade_simulator_for_same_trigger(trending_df):
    """
    Phase 6b's net_expectancy_pips and Phase 7c's expectancy_pips must
    agree (up to floating point) for the same condition, horizon, and
    fixed-cost config -- they are supposed to be two views of the exact
    same round-trip cost convention.
    """
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[[10, 30, 50]] = True

    spread_pips, slippage_pips, pip_value = 30.0, 1.0, 0.01
    horizon = 5

    cost_model = CostModel(spread_pips=spread_pips, slippage_pips=slippage_pips, pip_value=pip_value)
    engine = ForwardProfileEngine(trending_df, max_horizon=10)
    cost_result = cost_model.apply_costs_to_forward_profile(
        mask, trending_df, engine, optimal_horizon=horizon, direction="long",
    )

    sim_config = TradeSimConfig(
        direction="long",
        atr_column="atr_14",
        holding_bars=horizon,
        spread_price_units=spread_pips * pip_value,
        slippage_price_units=slippage_pips * pip_value,
    )
    sim_result = simulate_condition(trending_df, mask, sim_config)

    assert cost_result["net_expectancy_pips"] * pip_value == pytest.approx(
        sim_result.expectancy_pips, abs=1e-9
    )


def test_prefilter_passes_a_condition_that_only_survives_single_cost(trending_df):
    """
    Construct a raw edge whose magnitude clears ONE round-trip cost but
    not TWO -- this is exactly the class of condition the doubling bug
    used to reject incorrectly.
    """
    n = len(trending_df)
    close = trending_df["close"].values.copy()
    # Make the raw 5-bar move worth ~0.35 price units at each trigger,
    # which sits between one round-trip cost (30+1)*0.01=0.31 and two
    # round-trip costs (0.62): should PASS with the fix, would have
    # FAILED before it.
    mask = np.zeros(n, dtype=bool)
    triggers = [10, 40, 70, 100, 130]
    for t in triggers:
        close[t + 1 + 5] = close[t + 1] + 0.35
        mask[t] = True

    df = trending_df.copy()
    df["close"] = close

    cost_model = CostModel(spread_pips=30.0, slippage_pips=1.0, pip_value=0.01)
    engine = ForwardProfileEngine(df, max_horizon=10)
    cost_result = cost_model.apply_costs_to_forward_profile(
        mask, df, engine, optimal_horizon=5, direction="long",
    )
    passed, reason = cost_aware_prefilter(cost_result, min_expectancy_r=0.0)

    assert passed is True, reason
