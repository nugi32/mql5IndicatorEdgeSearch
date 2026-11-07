"""Tests for the MT5 'Open prices only' emulation."""

import numpy as np
import pandas as pd
import pytest

from edge_research.mt5_backtest.config import (
    MT5TesterConfig, config_from_dict, find_config_file, load_mt5_config,
)
from edge_research.mt5_backtest.engine import run_mt5_backtest, swap_nights
from edge_research.mt5_backtest.report import compare_trades, load_spread_csv
from edge_research.mt5_backtest.signals import build_mask


def make_df(n=12, start="2024-01-02 00:00", freq="5min", opens=None):
    idx = pd.date_range(start, periods=n, freq=freq)
    opens = opens if opens is not None else [2000.0 + i for i in range(n)]
    return pd.DataFrame({"open": opens, "rsi_14": [50.0] * n}, index=idx)


def cfg(**kw):
    base = dict(spread_points=30, point=0.01, contract_size=100, lots=1.0, initial_deposit=10000)
    base.update(kw)
    return config_from_dict(base)


def mask_at(n, *signal_bars):
    m = np.zeros(n, dtype=bool)
    m[list(signal_bars)] = True
    return m


def test_long_fills_at_ask_and_exits_at_bid_on_open():
    df = make_df()
    res = run_mt5_backtest(df, mask_at(12, 1), "long", 3, cfg())
    t = res.trades.iloc[0]
    assert t.entry_bar == 2 and t.exit_bar == 5          # signal bar 1 -> entry at open of bar 2, exit open of bar 5
    assert t.entry_price == pytest.approx(2002.30)       # open + spread (30 points * 0.01)
    assert t.exit_price == pytest.approx(2005.00)        # Bid = open
    assert t.profit == pytest.approx((2005.0 - 2002.3) * 100)


def test_short_pays_spread_on_exit_bar():
    df = make_df()
    res = run_mt5_backtest(df, mask_at(12, 1), "short", 3, cfg())
    t = res.trades.iloc[0]
    assert t.entry_price == pytest.approx(2002.00)       # Bid
    assert t.exit_price == pytest.approx(2005.30)        # Ask = open + spread
    assert t.profit == pytest.approx((2002.0 - 2005.3) * 100)


def test_per_bar_spread_is_used_and_zero_spread_uses_last_known():
    df = make_df()
    spread = pd.Series([20, 20, 50, 0, 0, 80, 0, 0, 0, 0, 0, 0], index=df.index, dtype=float)
    res = run_mt5_backtest(df, mask_at(12, 1), "long", 3, cfg(), spread_points=spread)
    assert res.trades.iloc[0].entry_price == pytest.approx(2002.50)     # bar 2 spread = 50 points
    short = run_mt5_backtest(df, mask_at(12, 1), "short", 3, cfg(), spread_points=spread)
    assert short.trades.iloc[0].exit_price == pytest.approx(2005.80)    # bar 5 spread = 80 points
    res2 = run_mt5_backtest(df, mask_at(12, 1), "short", 4, cfg(), spread_points=spread)
    assert res2.trades.iloc[0].exit_price == pytest.approx(2006.80)     # bar 6 spread 0 -> last known (80)


def test_one_position_at_a_time_and_exit_bar_blocks_reentry():
    df = make_df(20)
    sig = mask_at(20, 1, 2, 3, 4, 5)       # entries would be bars 2..6, hold 3 -> exit of first trade at bar 5
    res = run_mt5_backtest(df, sig, "long", 3, cfg())
    # bar 2 enters; bars 3,4 busy; bar 5 is the exit tick (no re-entry); bar 6 enters
    assert list(res.trades.entry_bar) == [2, 6]
    assert res.n_skipped_busy == 3
    res2 = run_mt5_backtest(df, sig, "long", 3, cfg(reenter_on_exit_bar=True))
    assert list(res2.trades.entry_bar) == [2, 5]


def test_max_open_positions_allows_overlap():
    df = make_df(20)
    res = run_mt5_backtest(df, mask_at(20, 1, 2), "long", 5, cfg(max_open_positions=2))
    assert list(res.trades.entry_bar) == [2, 3]


def test_exit_bar_offset_and_end_of_data():
    df = make_df(8)
    res = run_mt5_backtest(df, mask_at(8, 1), "long", 3, cfg(exit_bar_offset=1))
    assert res.trades.iloc[0].exit_bar == 6
    res = run_mt5_backtest(df, mask_at(8, 5), "long", 3, cfg())
    assert len(res.trades) == 0 and res.n_open_at_end == 1
    res = run_mt5_backtest(df, mask_at(8, 5), "long", 3, cfg(close_open_at_end=True))
    assert len(res.trades) == 1 and res.trades.iloc[0].exit_bar == 7


def test_date_range_limits_entries_and_exits():
    df = make_df(12)
    start, end = df.index[3], df.index[7]
    res = run_mt5_backtest(df, mask_at(12, 1, 3), "long", 2, cfg(), start=start, end=end)
    assert list(res.trades.entry_bar) == [4]            # signal 1 would enter before start


def test_commission_slippage_and_curves():
    df = make_df()
    res = run_mt5_backtest(df, mask_at(12, 1), "long", 3,
                           cfg(commission_per_lot_per_side=3.5, slippage_points=10))
    t = res.trades.iloc[0]
    assert t.entry_price == pytest.approx(2002.40) and t.exit_price == pytest.approx(2004.90)
    assert t.commission == pytest.approx(-7.0)
    assert res.balance.iloc[-1] == pytest.approx(10000 + t.profit)
    assert res.balance.iloc[0] == 10000
    # equity dips by the spread right after entry and equals balance once flat
    assert res.equity.iloc[3] == pytest.approx(10000 + (2003.0 - 2002.4) * 100)
    assert res.equity.iloc[-1] == pytest.approx(res.balance.iloc[-1])


def test_swap_nights_triple_wednesday():
    t = lambda s: pd.Timestamp(s)
    assert swap_nights(t("2024-01-02 10:00"), t("2024-01-02 20:00"), 0, 2) == 0
    assert swap_nights(t("2024-01-02 10:00"), t("2024-01-03 10:00"), 0, 2) == 1      # Tue night
    assert swap_nights(t("2024-01-03 10:00"), t("2024-01-04 10:00"), 0, 2) == 3      # Wed night x3
    assert swap_nights(t("2024-01-01 10:00"), t("2024-01-08 10:00"), 0, 2) == 7      # full week
    assert swap_nights(t("2024-01-05 10:00"), t("2024-01-08 10:00"), 0, 2) == 1      # Fri -> Mon: only Friday booking


def test_swap_applied_to_profit():
    df = make_df(400, freq="1h")
    res = run_mt5_backtest(df, mask_at(400, 1), "long", 30, cfg(swap_long_per_lot=-7.0))
    t = res.trades.iloc[0]
    assert t.nights >= 1 and t.swap == pytest.approx(t.nights * -7.0)
    assert t.profit == pytest.approx(t.gross_profit + t.swap)


def test_config_validation_and_per_timeframe_lookup(tmp_path):
    with pytest.raises(ValueError):
        config_from_dict({"spread_pts": 3})
    with pytest.raises(ValueError):
        config_from_dict({"forward": "half"})
    (tmp_path / "XAUUSD").mkdir()
    (tmp_path / "XAUUSD" / "M5.yaml").write_text("spread_points: 25\n")
    (tmp_path / "XAUUSD" / "H1.yaml").write_text("spread_points: 40\n")
    assert load_mt5_config(tmp_path, "XAUUSD", "M5").spread_points == 25
    assert load_mt5_config(tmp_path, "XAUUSD", "H1").spread_points == 40
    assert load_mt5_config(tmp_path, "XAUUSD", "H1", {"spread_points": 55}).spread_points == 55
    with pytest.raises(FileNotFoundError):
        find_config_file(tmp_path, "XAUUSD", "M30")
    (tmp_path / "XAUUSD" / "_default.yaml").write_text("spread_points: 33\n")
    assert load_mt5_config(tmp_path, "XAUUSD", "M30").spread_points == 33


def test_shipped_xauusd_configs_load():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "config" / "MT5_TESTER"
    for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        assert load_mt5_config(root, "XAUUSD", tf).modelling == "open_prices_only"
        gold = load_mt5_config(root, "XAUUSD", tf)
        assert gold.spread_points == 40 and gold.spread_price == pytest.approx(0.40)
        eur = load_mt5_config(root, "EURUSD", tf)
        assert eur.spread_points == 10 and eur.spread_price == pytest.approx(0.0001)   # 1 pip
        assert eur.contract_size == 100000 and eur.digits == 5


def test_build_mask_matches_condition():
    df = make_df()
    df["rsi_14"] = [10, 80, 10, 10, 80, 80, 10, 10, 10, 80, 80, 10]
    df["mom_10"] = [1.0] * 12
    m = build_mask(df, "rsi_14 < 25.0 AND mom_10 > -5.0")
    assert list(np.flatnonzero(m)) == [0, 2, 3, 6, 7, 8, 11]
    with pytest.raises(KeyError):
        build_mask(df, "cal_min_to_next_high < 30.0")


def test_spread_csv_and_compare(tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("time,spread\n20240102 00:00,20\n20240102 00:05,25\n")
    s = load_spread_csv(f)
    assert s.loc[pd.Timestamp("2024-01-02 00:05")] == 25
    df = make_df()
    res = run_mt5_backtest(df, mask_at(12, 1, 6), "long", 2, cfg())
    ref = res.trades[["entry_time", "exit_time", "entry_price", "exit_price"]].copy()
    ref.loc[1, "exit_price"] += 0.5
    cmp = compare_trades(res.trades, ref)
    assert cmp["n_matched"] == 2 and cmp["exit_price_exact"] == 1 and cmp["exit_time_mismatches"] == 0


def _fake_run(tmp_path, with_gate=True, with_ranker=False):
    """A finished-run folder: storage parquet + gate/ranker csv, enough for the automatic step."""
    n = 300
    idx = pd.date_range("2024-01-02", periods=n, freq="5min")
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"open": 2000 + np.cumsum(rng.normal(0, 0.5, n)),
                       "rsi_14": rng.uniform(10, 90, n)}, index=idx).astype("float32")
    (tmp_path / "storage").mkdir()
    df.to_parquet(tmp_path / "storage" / "XAUUSD_M5.parquet")
    if with_gate:
        pd.DataFrame({"condition": ["rsi_14 < 30.0", "cal_x < 1.0"], "direction": ["long", "long"],
                      "optimal_holding_bars": [4, 4], "gate_passed": [True, False]}
                     ).to_csv(tmp_path / "STRATEGY_GATE_RESULTS.csv", index=False)
    if with_ranker:
        pd.DataFrame({"rank": [1], "condition": ["rsi_14 < 30.0"], "direction": ["short"],
                      "holding_bars": [4]}).to_csv(tmp_path / "ranker_sort_top.csv", index=False)
    return tmp_path


def test_auto_backtest_single_run_writes_folder_and_skips_unavailable_columns(tmp_path):
    from edge_research.mt5_backtest.auto import run_auto_backtest
    run = _fake_run(tmp_path)
    cfg_root = tmp_path / "cfg"
    (cfg_root / "XAUUSD").mkdir(parents=True)
    (cfg_root / "XAUUSD" / "M5.yaml").write_text("spread_points: 40\n")
    report = run_auto_backtest(run, "XAUUSD", "M5", "gate", 5, cfg_root)
    assert report == run / "mt5_backtest" / "mt5_backtest_report.md" and report.exists()
    assert (run / "mt5_backtest" / "trades_01_long_4b.csv").exists()
    assert "cal_x" not in report.read_text()          # EA #2 needs a column that is not stored: skipped


def test_auto_backtest_walkforward_uses_ranker_file(tmp_path):
    from edge_research.mt5_backtest.auto import run_auto_backtest
    run = _fake_run(tmp_path, with_gate=False, with_ranker=True)
    report = run_auto_backtest(run, "XAUUSD", "M5", "ranker-sort", 5)     # shipped per-timeframe config
    assert report is not None and (run / "mt5_backtest" / "trades_01_short_4b.csv").exists()


def test_auto_backtest_ranker_filter_source_is_gone(tmp_path):
    import pytest
    from edge_research.mt5_backtest import auto
    from edge_research.mt5_backtest.auto import run_auto_backtest, try_auto_backtest
    run = _fake_run(tmp_path, with_gate=False, with_ranker=True)
    with pytest.raises(ValueError, match="ranker-filter"):
        run_auto_backtest(run, "XAUUSD", "M5", "ranker-filter", 5)
    assert try_auto_backtest(run, "XAUUSD", "M5", "ranker-filter", 5) is None     # never raises
    (run / "ranker_top.csv").write_text("rank,condition,direction,holding_bars\n1,rsi_14 < 30.0,long,4\n")
    (run / "ranker_sort_top.csv").unlink()
    assert len(auto.edges_from_ranker(run, 10)) == 0          # the old ranker_top.csv is not read any more


def test_auto_backtest_top_n_limits_ranker_rows(tmp_path):
    from edge_research.mt5_backtest.auto import edges_from_ranker
    pd.DataFrame({"rank": [1, 2, 3], "condition": ["a_1 > 1.0", "b_1 > 1.0", "c_1 > 1.0"],
                  "direction": ["long"] * 3, "holding_bars": [4, 5, 6],
                  "warnings": ["", "", ""]}).to_csv(tmp_path / "ranker_sort_top.csv", index=False)
    assert edges_from_ranker(tmp_path, 2)["condition"].tolist() == ["a_1 > 1.0", "b_1 > 1.0"]
    pd.DataFrame(columns=["rank", "condition", "direction", "holding_bars"]).to_csv(
        tmp_path / "ranker_sort_top.csv", index=False)
    assert len(edges_from_ranker(tmp_path, 10)) == 0           # header-only file: nothing to backtest


def test_auto_backtest_never_raises_and_handles_empty(tmp_path):
    from edge_research.mt5_backtest.auto import run_auto_backtest, try_auto_backtest
    assert run_auto_backtest(tmp_path, "XAUUSD", "M5", "gate") is None            # nothing to backtest
    run = _fake_run(tmp_path / "r") if (tmp_path / "r").mkdir() is None else None
    assert try_auto_backtest(run, "XAUUSD", "M99", "gate") is None                # no config for M99: logged, not raised
