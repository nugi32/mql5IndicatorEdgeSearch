"""Tests for Phase 7c: fixed-holding-bar trade simulation and horizon scan."""

import numpy as np
import pandas as pd
import pytest

from edge_research.simulation.trade_simulator import (
    TradeSimConfig,
    compute_r_multiples_for_horizon,
    scan_holding_horizons,
    select_best_holding_bars,
    simulate_condition,
)


@pytest.fixture
def trending_df():
    """
    Deterministic uptrend: close[i] = 100 + i. No noise, so the ideal
    long holding period is unambiguous and R-multiples are exactly
    predictable, which makes the exit-price arithmetic easy to check by
    hand.
    """
    n = 200
    close = 100.0 + np.arange(n, dtype=np.float64)
    df = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "atr_14": np.full(n, 1.0),
    }, index=pd.date_range("2024-01-01", periods=n, freq="h"))
    return df


def test_simulate_condition_fixed_exit_no_sl_tp(trending_df):
    """A single trigger should exit exactly holding_bars later, no earlier."""
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[10] = True  # entry at bar 11 (open)

    config = TradeSimConfig(
        direction="long",
        atr_column="atr_14",
        holding_bars=5,
        spread_price_units=0.0,
        slippage_price_units=0.0,
    )
    result = simulate_condition(trending_df, mask, config)

    assert result.n_trades == 1
    assert result.n_timeouts == 0
    # entry = open[11] = close[11]-0.5 = 110.5; exit = close[16] = 116
    expected_pips = trending_df["close"].iloc[16] - (trending_df["open"].iloc[11])
    assert result.expectancy_pips == pytest.approx(expected_pips)


def test_simulate_condition_no_config_fields_for_sl_tp():
    """The SL/TP/trailing fields must not exist on TradeSimConfig anymore."""
    config = TradeSimConfig()
    for removed_field in ("sl_atr_mult", "tp_atr_mult", "use_trailing_stop", "trail_atr_mult", "intrabar_priority"):
        assert not hasattr(config, removed_field)
    assert hasattr(config, "holding_bars")


def test_simulate_condition_short_direction(trending_df):
    """Short direction should lose money in a pure uptrend, and by the mirrored amount."""
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[10] = True

    long_config = TradeSimConfig(direction="long", holding_bars=5, spread_price_units=0.0, slippage_price_units=0.0)
    short_config = TradeSimConfig(direction="short", holding_bars=5, spread_price_units=0.0, slippage_price_units=0.0)

    long_result = simulate_condition(trending_df, mask, long_config)
    short_result = simulate_condition(trending_df, mask, short_config)

    assert long_result.expectancy_pips > 0
    assert short_result.expectancy_pips < 0
    assert short_result.expectancy_pips == pytest.approx(-long_result.expectancy_pips)


def test_simulate_condition_timeout_near_end_of_data(trending_df):
    """A trigger too close to the end of the data should be marked 'timeout', not dropped."""
    n = len(trending_df)
    mask = np.zeros(n, dtype=bool)
    mask[n - 3] = True  # only 1 bar of room after entry, holding_bars=5 can't fit

    config = TradeSimConfig(direction="long", holding_bars=5)
    result = simulate_condition(trending_df, mask, config)

    assert result.n_trades == 1
    assert result.n_timeouts == 1


def test_compute_r_multiples_for_horizon_matches_simulate_condition(trending_df):
    """The horizon-scan helper and the full simulator must agree on R-multiples."""
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[[10, 20, 30]] = True

    config = TradeSimConfig(direction="long", holding_bars=7, spread_price_units=0.1, slippage_price_units=0.05)

    sim_result = simulate_condition(trending_df, mask, config)
    scan_r = compute_r_multiples_for_horizon(trending_df, mask, config, horizon=7)

    np.testing.assert_allclose(np.sort(sim_result.r_multiples), np.sort(scan_r))


def test_scan_holding_horizons_score_formula_matches_manual_tstat(trending_df):
    """scan_holding_horizons' score column must equal mean/(std/sqrt(n)) exactly."""
    mask = np.zeros(len(trending_df), dtype=bool)
    mask[[5, 15, 25, 35, 45]] = True

    config = TradeSimConfig(direction="long", spread_price_units=0.1, slippage_price_units=0.0)
    table = scan_holding_horizons(trending_df, mask, config, horizon_min=3, horizon_max=3)
    row = table.iloc[0]

    r = compute_r_multiples_for_horizon(trending_df, mask, config, horizon=3)
    expected_score = np.mean(r) / (np.std(r, ddof=1) / np.sqrt(len(r)))

    assert row["n_trades"] == len(r)
    assert row["score"] == pytest.approx(expected_score)


def test_scan_holding_horizons_prefers_consistency_over_raw_mean():
    """
    A horizon with a smaller but tightly-clustered mean R should outscore
    a horizon with a larger but wildly dispersed mean R -- this is the
    entire point of the t-stat score (see scan_holding_horizons docstring).

    Built with well-separated, non-overlapping triggers so each trigger's
    horizon-h return is independently controllable by construction, rather
    than emerging from an entangled cumulative price path.
    """
    horizon_a, horizon_b = 2, 5
    spacing = 20  # >> horizon_b, so windows never overlap
    n_triggers = 10
    n = n_triggers * spacing + horizon_b + 5

    close = np.full(n, 100.0)
    trigger_bars = [i * spacing for i in range(n_triggers)]

    rng = np.random.default_rng(1)
    for k, t in enumerate(trigger_bars):
        entry_bar = t + 1
        # Horizon A: nearly identical small consistent gain every time (tiny
        # noise so std is small-but-nonzero, giving a large but finite
        # score, rather than an undefined std=0 score).
        close[entry_bar + horizon_a] = close[entry_bar] + 1.0 + 0.001 * (k % 3)
        # Horizon B: mean gain is larger on average, but wildly dispersed
        # (half the time a big win, half the time a big loss) -> high mean,
        # very high std, much lower t-stat despite the bigger raw mean.
        shock = 20.0 if k % 2 == 0 else -10.0
        close[entry_bar + horizon_b] = close[entry_bar] + shock
        # Keep intermediate bars flat so horizons between A and B don't
        # accidentally inherit horizon B's shock.
        for b in range(entry_bar, entry_bar + horizon_b + 1):
            if b not in (entry_bar, entry_bar + horizon_a, entry_bar + horizon_b):
                close[b] = close[entry_bar]

    df = pd.DataFrame({
        "open": close,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "atr_14": np.full(n, 1.0),
    }, index=pd.date_range("2024-01-01", periods=n, freq="h"))

    mask = np.zeros(n, dtype=bool)
    mask[trigger_bars] = True

    config = TradeSimConfig(direction="long", spread_price_units=0.0, slippage_price_units=0.0)
    table = scan_holding_horizons(df, mask, config, horizon_min=1, horizon_max=horizon_b)

    row_a = table[table["horizon"] == horizon_a].iloc[0]
    row_b = table[table["horizon"] == horizon_b].iloc[0]
    best_h = select_best_holding_bars(table)

    assert row_b["mean_r"] > row_a["mean_r"]  # horizon B has the bigger raw mean...
    assert row_a["score"] > row_b["score"]    # ...but horizon A is the consistent one
    assert best_h == horizon_a                # and consistency, not raw mean, wins selection


def test_select_best_holding_bars_returns_none_when_all_nan():
    table = pd.DataFrame({
        "horizon": [1, 2, 3],
        "n_trades": [0, 1, 0],
        "mean_r": [np.nan, 0.5, np.nan],
        "std_r": [np.nan, np.nan, np.nan],
        "score": [np.nan, np.nan, np.nan],
    })
    assert select_best_holding_bars(table) is None


def test_simulate_condition_zero_trades_returns_nan_result(trending_df):
    mask = np.zeros(len(trending_df), dtype=bool)
    config = TradeSimConfig(direction="long", holding_bars=5)
    result = simulate_condition(trending_df, mask, config)
    assert result.n_trades == 0
    assert np.isnan(result.expectancy_r)
