"""Pipeline simulation in MT5 'Open prices only' mode (TradeSimConfig.mt5_mode) and its plumbing."""

import sys

import numpy as np
import pandas as pd
import pytest

from edge_research.mt5_backtest.config import config_from_dict
from edge_research.mt5_backtest.engine import run_mt5_backtest
from edge_research.mt5_backtest.pipeline_link import link_mt5_settings, mt5_pipeline_overrides
from edge_research.simulation.trade_simulator import (
    TradeSimConfig, compute_r_multiples_for_horizon, mt5_sim_kwargs, scan_holding_horizons, simulate_condition,
)


def make_df(n=400, seed=1):
    idx = pd.date_range("2024-01-02", periods=n, freq="5min")
    rng = np.random.default_rng(seed)
    close = 2000 + np.cumsum(rng.normal(0, 0.6, n))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 0.2,
                         "low": np.minimum(open_, close) - 0.2, "close": close, "atr_14": 1.5}, index=idx)


def sim_cfg(direction="long", hold=5, **kw):
    return TradeSimConfig(direction=direction, holding_bars=hold, spread_price_units=0.4,
                          slippage_price_units=0.0, mt5_mode=True, **kw)


def random_mask(n, every=7, seed=2):
    rng = np.random.default_rng(seed)
    m = np.zeros(n, bool)
    m[rng.choice(n - 20, size=n // every, replace=False)] = True
    return m


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("hold", [1, 3, 8])
def test_pipeline_sim_matches_standalone_mt5_emulator(direction, hold):
    df, mask = make_df(), random_mask(400)
    sim = simulate_condition(df, mask, sim_cfg(direction, hold))
    emu_cfg = config_from_dict({"spread_points": 40, "point": 0.01, "digits": 8, "lots": 1.0, "contract_size": 1.0})
    emu = run_mt5_backtest(df.astype({"open": "float64"}), mask, direction, hold, emu_cfg)
    assert sim.n_trades == len(emu.trades) > 0
    np.testing.assert_allclose(sim.equity_curve_pips[-1], emu.trades["price_pnl"].sum(), atol=1e-6)
    np.testing.assert_allclose(np.cumsum(emu.trades["price_pnl"]), sim.equity_curve_pips, atol=1e-6)


def test_scan_and_simulate_agree_and_only_one_position_is_open():
    df, mask = make_df(), random_mask(400, every=3)
    cfg = sim_cfg("long", 6)
    scan = scan_holding_horizons(df, mask, cfg, 1, 12)
    for h in (1, 4, 9):
        r = compute_r_multiples_for_horizon(df, mask, cfg, h)
        full = simulate_condition(df, mask, sim_cfg("long", h))
        np.testing.assert_allclose(r, full.r_multiples)
        assert scan.loc[scan.horizon == h, "n_trades"].iloc[0] == len(r)
    legacy = simulate_condition(df, mask, TradeSimConfig(direction="long", holding_bars=6, spread_price_units=0.4))
    assert simulate_condition(df, mask, cfg).n_trades < legacy.n_trades     # overlapping signals are skipped


def test_exit_is_at_open_and_spread_side():
    df = make_df(60)
    mask = np.zeros(60, bool)
    mask[10] = True
    long_pips = simulate_condition(df, mask, sim_cfg("long", 4)).expectancy_pips
    short_pips = simulate_condition(df, mask, sim_cfg("short", 4)).expectancy_pips
    move = df["open"].iloc[15] - df["open"].iloc[11]            # entry bar 11, exit bar 15, both opens
    assert long_pips == pytest.approx(move - 0.4)
    assert short_pips == pytest.approx(-move - 0.4)


def test_exit_bar_offset_and_reentry_flags():
    df = make_df(60)
    mask = np.zeros(60, bool)
    mask[[10, 14]] = True                  # entries on bars 11 and 15; hold 4 -> first trade exits on bar 15
    blocked = simulate_condition(df, mask, sim_cfg("long", 4))
    allowed = simulate_condition(df, mask, sim_cfg("long", 4, reenter_on_exit_bar=True))
    assert blocked.n_trades == 1 and allowed.n_trades == 2
    shifted = simulate_condition(df, mask, sim_cfg("long", 3, exit_bar_offset=1))
    assert shifted.expectancy_pips == pytest.approx(
        simulate_condition(df, mask, sim_cfg("long", 4)).expectancy_pips)


def test_legacy_mode_unchanged_by_default():
    assert TradeSimConfig().mt5_mode is False
    assert mt5_sim_kwargs({}) == {} and mt5_sim_kwargs({"sim_mt5": {}}) == {}
    assert mt5_sim_kwargs({"sim_mt5": {"exit_bar_offset": 1}})["mt5_mode"] is True


def test_link_applies_per_timeframe_settings(tmp_path):
    (tmp_path / "XAUUSD").mkdir()
    (tmp_path / "XAUUSD" / "M5.yaml").write_text("spread_points: 40\npoint: 0.01\n")
    (tmp_path / "XAUUSD" / "H1.yaml").write_text("spread_points: 60\npoint: 0.01\nslippage_points: 5\n")
    base = {"spread_pips": 30.0, "slippage_pips": 1.0, "pip_value": 0.01}
    m5 = link_mt5_settings(base, "XAUUSD", "M5", tmp_path)
    h1 = link_mt5_settings(base, "XAUUSD", "H1", tmp_path)
    assert m5["spread_pips"] == pytest.approx(40) and m5["slippage_pips"] == 0 and "sim_mt5" in m5
    assert h1["spread_pips"] == pytest.approx(60) and h1["slippage_pips"] == pytest.approx(10)  # 2 fills x 5 points
    assert base["spread_pips"] == 30.0                                   # input not mutated
    assert link_mt5_settings(base, "XAUUSD", "M5", tmp_path, enabled=False) is base
    assert link_mt5_settings(base, "XAUUSD", "M30", tmp_path) is base    # no file: legacy fallback
    eur = mt5_pipeline_overrides(config_from_dict({"point": 0.00001, "spread_points": 10}), 0.0001)
    assert eur["spread_pips"] == pytest.approx(1.0)                       # 1 pip


def test_decimate_keeps_extremes():
    from edge_research.mt5_backtest.report import decimate
    v = np.zeros(100_000)
    v[54_321], v[77_777] = 9.0, -9.0
    s = pd.Series(v, index=pd.date_range("2020-01-01", periods=len(v), freq="1min"))
    d = decimate(s, 1000)
    assert len(d["x"]) <= 1000 and d["hi"].max() == 9.0 and d["lo"].min() == -9.0


def _result():
    df = make_df(200)
    cfg = config_from_dict({"spread_points": 40})
    return run_mt5_backtest(df, random_mask(200), "long", 4, cfg)


def test_chart_png_and_svg_fallback(tmp_path, monkeypatch):
    from edge_research.mt5_backtest.report import save_chart
    res = _result()
    png = save_chart(res, "test", tmp_path / "a.png")
    assert png.suffix == ".png" and png.read_bytes()[:4] == b"\x89PNG"
    monkeypatch.setitem(sys.modules, "matplotlib", None)       # simulate matplotlib not installed
    svg = save_chart(res, "test", tmp_path / "b.png")
    assert svg.suffix == ".svg" and svg.read_text().startswith("<svg")


def test_report_folder_has_charts_and_releases_curves(tmp_path):
    from edge_research.mt5_backtest.auto import backtest_edges_to_folder
    df = make_df(300)
    df["rsi_14"] = np.tile([20.0, 60.0, 70.0], 100)
    edges = pd.DataFrame({"rank": [1, 2], "condition": ["rsi_14 < 30.0", "rsi_14 > 65.0"],
                          "direction": ["long", "short"], "holding_bars": [3, 4]})
    rows = backtest_edges_to_folder(df, edges, config_from_dict({"spread_points": 40}), "XAUUSD", "M5", tmp_path)
    assert len(rows) == 2
    assert all(len(r["result"].balance) == 0 and len(r["result"].trades) == 0 for r in rows)   # memory released
    for name in ("overview.png", "curve_01_long_3b.png", "curve_02_short_4b.png",
                 "mt5_backtest_report.md", "trades_01_long_3b.csv", "curve_01_long_3b.csv"):
        assert (tmp_path / name).exists(), name
    md = (tmp_path / "mt5_backtest_report.md").read_text()
    assert "![all EAs](overview.png)" in md and "![curve](curve_01_long_3b.png)" in md


def test_column_subset_loading(tmp_path):
    from edge_research.mt5_backtest.auto import load_columns, needed_columns
    idx = pd.date_range("2024-01-02", periods=50, freq="5min")
    wide = pd.DataFrame(np.random.rand(50, 30).astype("float32"), index=idx,
                        columns=[f"c{i}" for i in range(29)] + ["open"])
    path = tmp_path / "x.parquet"
    wide.to_parquet(path)
    edges = pd.DataFrame({"condition": ["c3 < 0.5 AND c4 > c5", "c99 > 1.0"]})
    cols = needed_columns(edges)
    assert cols == ["c3", "c4", "c5", "c99", "open"]
    sub = load_columns(path, cols)
    assert list(sub.columns) == ["c3", "c4", "c5", "open"] and isinstance(sub.index, pd.DatetimeIndex)


def test_pipeline_core_runs_in_mt5_mode(tmp_path):
    """Tiny synthetic run of Phases 2-9 with the MT5 behaviour linked in (same fixture as the core smoke test)."""
    from pathlib import Path
    from scripts.run_pipeline import run_pipeline_core
    from tests.test_run_pipeline_core_smoke import _synthetic_df
    cfg = {
        "max_horizon": 10, "min_occurrence": 20, "min_freq_per_year": 1.0,
        "alpha": 0.05, "fdr_method": "fdr_bh",
        "wf_train_bars": 2000, "wf_test_bars": 500, "wf_step_bars": 500,
        "spread_pips": 30.0, "slippage_pips": 1.0, "pip_value": 0.01,
        "horizon_scan_min_bars": 1, "horizon_scan_max_bars": 8,
        "permutation_n": 20, "precheck_enabled": False,
        "top_n_atomic_for_combine": 8, "max_atoms_per_combo": 2, "include_ma_conditions": True,
        "rsi_thresholds": [30, 70], "cci_thresholds": [-100, 100], "mom_thresholds": [0],
        "stoch_thresholds": [20, 80], "gate_min_sim_trades": 5,
    }
    root = tmp_path / "cfg"
    (root / "TEST").mkdir(parents=True)
    (root / "TEST" / "M1.yaml").write_text("spread_points: 40\npoint: 0.01\n")
    cfg = link_mt5_settings(cfg, "TEST", "M1", root)
    repo = Path(__file__).resolve().parent.parent
    result = run_pipeline_core(df=_synthetic_df(), known_at_config_path=repo / "config" / "known_at_delay.yaml",
                               pipeline_config=cfg, symbol="TEST", timeframe="M1", output_dir=tmp_path / "out")
    assert len(result["validated_edges"]) > 0
    assert all(e["trade_sim"].config.mt5_mode for e in result["validated_edges"])
    assert all(abs(e["trade_sim"].config.spread_price_units - 0.4) < 1e-9 for e in result["validated_edges"])
