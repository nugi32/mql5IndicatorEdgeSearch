"""The vectorized R-multiple scan must reproduce the old per-trigger Python
loop exactly (same float64 operations, same order)."""

import numpy as np
import pandas as pd
import pytest

from edge_research.simulation.trade_simulator import (
    TradeSimConfig,
    _effective_half_cost,
    compute_r_multiples_for_horizon,
    scan_holding_horizons,
)


def _reference_loop(df, mask, config, horizon):
    """Verbatim copy of the previous implementation."""
    open_ = df["open"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    atr = df[config.atr_column].values.astype(np.float64)
    index = df.index
    n = len(df)
    long = config.direction == "long"
    out = []
    for i in np.where(mask)[0]:
        entry_bar = i + 1
        exit_bar = entry_bar + horizon
        if exit_bar >= n:
            continue
        entry_atr = atr[i]
        if not np.isfinite(entry_atr) or entry_atr <= 0:
            continue
        half_cost = _effective_half_cost(config, entry_atr, index[entry_bar])
        raw_entry = open_[entry_bar]
        entry_price = raw_entry + half_cost if long else raw_entry - half_cost
        raw_exit = close[exit_bar]
        exit_price = raw_exit - half_cost if long else raw_exit + half_cost
        pips = (exit_price - entry_price) if long else (entry_price - exit_price)
        out.append(pips / entry_atr)
    return np.array(out, dtype=np.float64)


@pytest.fixture
def market():
    rng = np.random.default_rng(7)
    n = 3000
    idx = pd.date_range("2023-01-02", periods=n, freq="min")
    close = 2000 + rng.normal(0, 0.4, n).cumsum()
    df = pd.DataFrame({
        "open": close + rng.normal(0, 0.1, n),
        "close": close,
        "atr_14": np.abs(rng.normal(1.2, 0.3, n)).astype(np.float32),
    }, index=idx)
    df.loc[df.index[[5, 40, 41]], "atr_14"] = [np.nan, 0.0, -1.0]  # invalid ATR rows
    mask = rng.random(n) < 0.15
    mask[[5, 40, 41, n - 1, n - 2, n - 3]] = True   # bad ATR + triggers at the very end
    return df, mask


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("variant", ["fixed", "atr_mult", "session", "both"])
def test_matches_reference_loop(market, direction, variant):
    df, mask = market
    kw = dict(direction=direction, atr_column="atr_14",
              spread_price_units=0.3, slippage_price_units=0.05)
    if variant in ("atr_mult", "both"):
        kw["spread_atr_mult"] = 0.03
    if variant in ("session", "both"):
        kw["session_spread_multipliers"] = [(0, 7, 1.5), (22, 3, 1.7), (7, 16, 1.0), (13, 16, 0.9)]
    cfg = TradeSimConfig(**kw)

    for h in (1, 2, 17, 250, 2990, 5000):
        got = compute_r_multiples_for_horizon(df, mask, cfg, h)
        ref = _reference_loop(df, mask, cfg, h)
        assert got.shape == ref.shape, (h, got.shape, ref.shape)
        np.testing.assert_array_equal(got, ref)


def test_scan_table_matches_per_horizon_reference(market):
    df, mask = market
    cfg = TradeSimConfig(direction="long", atr_column="atr_14", spread_price_units=0.3)
    table = scan_holding_horizons(df, mask, cfg, 1, 40)
    for _, row in table.iterrows():
        ref = _reference_loop(df, mask, cfg, int(row["horizon"]))
        assert int(row["n_trades"]) == len(ref)
        if len(ref) >= 2:
            assert row["mean_r"] == float(np.mean(ref))
            assert row["std_r"] == float(np.std(ref, ddof=1))
