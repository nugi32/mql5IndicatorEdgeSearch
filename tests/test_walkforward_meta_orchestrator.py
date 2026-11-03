"""Tests for edge_research.walkforward.meta_orchestrator -- the plateau
candidate selection and frozen-parameter test-period re-evaluation that
scripts/run_walkforward_pipeline.py's per-window loop relies on."""

import numpy as np
import pandas as pd
import pytest

from edge_research.conditions.condition_library import AtomicCondition, Operator
from edge_research.simulation.trade_simulator import TradeSimConfig, TradeSimResult, simulate_condition
from edge_research.walkforward.meta_orchestrator import (
    evaluate_on_test_period,
    select_plateau_candidates,
    write_window_summary,
)


def _fake_edge(edge_id, gate_passed, sensitivity_score, expectancy_r, condition=None, trade_sim_config=None):
    return {
        "edge_id": edge_id,
        "condition": condition or AtomicCondition("rsi_14", Operator.LT, 30.0),
        "direction": "long",
        "gate_passed": gate_passed,
        "robustness": {"parameter_sensitivity": {"sensitivity_score": sensitivity_score}},
        "trade_sim": TradeSimResult(
            n_trades=50, n_wins=30, n_losses=20, n_timeouts=0, win_rate=0.6,
            avg_win_pips=1.0, avg_loss_pips=-0.5, expectancy_pips=0.3,
            expectancy_r=expectancy_r, profit_factor=1.5, max_drawdown_pips=2.0,
            equity_curve_pips=np.array([1.0]),
            config=trade_sim_config or TradeSimConfig(direction="long", holding_bars=5),
        ),
        "optimal_holding_bars": 5,
    }


def test_select_plateau_candidates_filters_gate_and_sensitivity():
    edges = [
        _fake_edge("A", gate_passed=True, sensitivity_score=0.9, expectancy_r=0.10),
        _fake_edge("B", gate_passed=True, sensitivity_score=0.3, expectancy_r=0.50),  # fails plateau despite best score
        _fake_edge("C", gate_passed=False, sensitivity_score=0.95, expectancy_r=0.20),  # never passed gate
        _fake_edge("D", gate_passed=True, sensitivity_score=np.nan, expectancy_r=0.15),  # untested -> excluded
        _fake_edge("E", gate_passed=True, sensitivity_score=0.75, expectancy_r=0.05),
    ]
    selected = select_plateau_candidates(edges, min_sensitivity=0.7)
    ids = [e["edge_id"] for e in selected]

    assert ids == ["A", "E"]  # ranked by expectancy_r desc, B/C/D excluded


def test_select_plateau_candidates_respects_top_k():
    edges = [
        _fake_edge("A", True, 0.9, 0.30),
        _fake_edge("B", True, 0.9, 0.20),
        _fake_edge("C", True, 0.9, 0.10),
    ]
    selected = select_plateau_candidates(edges, min_sensitivity=0.5, top_k=2)
    assert [e["edge_id"] for e in selected] == ["A", "B"]


def test_select_plateau_candidates_empty_when_nothing_qualifies():
    edges = [_fake_edge("A", False, 0.9, 0.3), _fake_edge("B", True, 0.1, 0.5)]
    assert select_plateau_candidates(edges, min_sensitivity=0.7) == []


@pytest.fixture
def test_df():
    n = 100
    close = 100.0 + np.arange(n, dtype=np.float64) * 0.05
    return pd.DataFrame({
        "open": close - 0.01,
        "high": close + 0.05,
        "low": close - 0.05,
        "close": close,
        "atr_14": np.full(n, 1.0),
        "rsi_14": np.tile(np.linspace(10, 90, 10), n // 10),
    }, index=pd.date_range("2024-06-01", periods=n, freq="h"))


def test_evaluate_on_test_period_passes_for_profitable_condition(test_df):
    edge = _fake_edge(
        "A", True, 0.9, expectancy_r=0.1,
        condition=AtomicCondition("rsi_14", Operator.LT, 30.0),
        trade_sim_config=TradeSimConfig(direction="long", atr_column="atr_14", holding_bars=3,
                                         spread_price_units=0.0, slippage_price_units=0.0),
    )
    result = evaluate_on_test_period(edge, test_df, min_trades=1, min_expectancy_r=0.0)

    assert result.test_sim.n_trades > 0
    assert isinstance(result.test_passed, bool)
    # Uptrending test_df + long direction -> should be net positive and pass
    assert result.test_passed is True


def test_evaluate_on_test_period_fails_when_too_few_trades(test_df):
    edge = _fake_edge(
        "A", True, 0.9, expectancy_r=0.1,
        condition=AtomicCondition("rsi_14", Operator.LT, 30.0),
        trade_sim_config=TradeSimConfig(direction="long", atr_column="atr_14", holding_bars=3),
    )
    result = evaluate_on_test_period(edge, test_df, min_trades=10_000, min_expectancy_r=0.0)
    assert result.test_passed is False


def test_evaluate_on_test_period_fails_when_condition_never_triggers(test_df):
    edge = _fake_edge(
        "A", True, 0.9, expectancy_r=0.1,
        condition=AtomicCondition("rsi_14", Operator.LT, -999.0),  # never true
        trade_sim_config=TradeSimConfig(direction="long", atr_column="atr_14", holding_bars=3),
    )
    result = evaluate_on_test_period(edge, test_df, min_trades=1, min_expectancy_r=0.0)
    assert result.test_sim.n_trades == 0
    assert result.test_passed is False


def test_write_window_summary_creates_readable_markdown(tmp_path):
    windows = [
        {
            "window_id": "window_0000",
            "train_date_start": "2024-01-01", "train_date_end": "2024-03-01",
            "test_date_start": "2024-03-01", "test_date_end": "2024-04-01",
            "n_train_candidates": 5, "n_accepted": 2,
            "accepted_edges": [
                {"edge_id": "A", "condition": "rsi_14 < 30", "direction": "long",
                 "optimal_holding_bars": 5, "test_expectancy_r": 0.12,
                 "test_profit_factor": 1.4, "test_n_trades": 20},
                {"edge_id": "B", "condition": "cci_20 < -100", "direction": "long",
                 "optimal_holding_bars": 3, "test_expectancy_r": 0.08,
                 "test_profit_factor": 1.2, "test_n_trades": 15},
            ],
        },
        {
            "window_id": "window_0001",
            "train_date_start": "2024-02-01", "train_date_end": "2024-04-01",
            "test_date_start": "2024-04-01", "test_date_end": "2024-05-01",
            "n_train_candidates": 3, "n_accepted": 0,
            "accepted_edges": [],
        },
    ]
    path = tmp_path / "WALKFORWARD_SUMMARY.md"
    write_window_summary(windows, path)

    content = path.read_text()
    assert "window_0000" in content
    assert "window_0001" in content
    assert "(none)" in content
    assert "rsi_14 < 30" in content
    assert "cci_20 < -100" in content
    # Same bare edge_id "A" must never be the only identifying info --
    # the condition string has to be right next to it, since the id alone
    # is ambiguous across windows (see write_window_summary's docstring).
    assert "restarts from 1 on every window" in content


def test_run_walkforward_pipeline_rejects_incompatible_inner_wf_settings(tmp_path):
    """
    If a config-dir's inner wf_train_bars + wf_test_bars can't fit inside
    one meta_wf_train_bars-sized window, that config is unsafe for
    walk-forward mode (every window's inner walk-forward check would
    silently produce zero windows, failing every condition's gate with no
    error). This must be rejected loudly, before any CSV is even read.
    """
    import pytest as _pytest
    from scripts.run_walkforward_pipeline import run_walkforward_pipeline

    config_dir = tmp_path / "bad_config"
    config_dir.mkdir()
    (config_dir / "known_at_delay.yaml").write_text("rules: []\n")
    (config_dir / "pipeline_config.yaml").write_text(
        "wf_train_bars: 44000\n"
        "wf_test_bars: 8800\n"
        "wf_step_bars: 4400\n"
        "meta_wf_train_bars: 24192\n"  # smaller than wf_train_bars + wf_test_bars -- inconsistent
        "meta_wf_test_bars: 6048\n"
        "meta_wf_step_bars: 6048\n"
    )

    with _pytest.raises(ValueError, match="not safe to use for walk-forward"):
        run_walkforward_pipeline(
            csv_path=str(tmp_path / "nonexistent.csv"),  # never reached -- guard fires first
            symbol="XAUUSD",
            timeframe="M30",
            config_dir=str(config_dir),
            output_dir=str(tmp_path / "out"),
        )


def test_run_walkforward_pipeline_accepts_compatible_inner_wf_settings_before_ingestion(tmp_path):
    """The same guard must NOT fire when the config is actually consistent
    -- confirmed by letting it proceed to (and fail at) CSV ingestion
    instead of raising the config-guard error."""
    import pytest as _pytest
    from scripts.run_walkforward_pipeline import run_walkforward_pipeline

    config_dir = tmp_path / "good_config"
    config_dir.mkdir()
    (config_dir / "known_at_delay.yaml").write_text("rules: []\n")
    (config_dir / "pipeline_config.yaml").write_text(
        "wf_train_bars: 1050\n"
        "wf_test_bars: 210\n"
        "wf_step_bars: 105\n"
        "meta_wf_train_bars: 3024\n"
        "meta_wf_test_bars: 1008\n"
        "meta_wf_step_bars: 1008\n"
    )

    # Should get past the consistency guard and fail later trying to read
    # a CSV that doesn't exist -- proving the guard did NOT block it.
    with _pytest.raises(Exception) as excinfo:
        run_walkforward_pipeline(
            csv_path=str(tmp_path / "nonexistent.csv"),
            symbol="XAUUSD",
            timeframe="M30",
            config_dir=str(config_dir),
            output_dir=str(tmp_path / "out"),
        )
    assert "not safe to use for walk-forward" not in str(excinfo.value)


def test_run_walkforward_pipeline_guard_skipped_when_inner_checks_disabled(tmp_path):
    """If BOTH gate_require_walk_forward and gate_require_holding_bars_stable
    are disabled, the inner wf_train_bars/wf_test_bars result is never
    consulted by the gate, so the size-mismatch guard must not block a
    config that would otherwise trip it."""
    import pytest as _pytest
    from scripts.run_walkforward_pipeline import run_walkforward_pipeline

    config_dir = tmp_path / "disabled_gates_config"
    config_dir.mkdir()
    (config_dir / "known_at_delay.yaml").write_text("rules: []\n")
    (config_dir / "pipeline_config.yaml").write_text(
        "wf_train_bars: 44000\n"
        "wf_test_bars: 8800\n"
        "wf_step_bars: 4400\n"
        "meta_wf_train_bars: 24192\n"  # would normally trip the guard
        "meta_wf_test_bars: 6048\n"
        "meta_wf_step_bars: 6048\n"
        "gate_require_walk_forward: false\n"
        "gate_require_holding_bars_stable: false\n"
    )

    with _pytest.raises(Exception) as excinfo:
        run_walkforward_pipeline(
            csv_path=str(tmp_path / "nonexistent.csv"),
            symbol="XAUUSD",
            timeframe="M30",
            config_dir=str(config_dir),
            output_dir=str(tmp_path / "out"),
        )
    assert "not safe to use for walk-forward" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Calendar-based windowing (generate_calendar_windows / write_multi_run_summary)
# ---------------------------------------------------------------------------

from edge_research.walkforward.meta_orchestrator import (
    generate_calendar_windows,
    write_multi_run_summary,
)


def _make_daily_df(start, end):
    idx = pd.date_range(start, end, freq="D")
    n = len(idx)
    close = 100.0 + np.arange(n, dtype=np.float64) * 0.01
    return pd.DataFrame({
        "open": close, "high": close + 0.1, "low": close - 0.1, "close": close,
    }, index=idx)


def test_calendar_windows_align_to_jan_1():
    """Core ask: boundaries must land exactly on Jan 1, not wherever N bars happens to fall."""
    df = _make_daily_df("2010-01-01", "2020-12-31")
    windows = generate_calendar_windows(df, start_year=2010, train_years=3, test_years=1, step_years=1)

    assert len(windows) > 0
    w0 = windows[0]
    assert w0["train_start_nominal"] == pd.Timestamp("2010-01-01")
    assert w0["train_end_nominal"] == pd.Timestamp("2013-01-01")
    assert w0["test_start_nominal"] == pd.Timestamp("2013-01-01")
    assert w0["test_end_nominal"] == pd.Timestamp("2014-01-01")
    # With daily data starting exactly on Jan 1, actual should match nominal.
    assert w0["train_start_actual"] == pd.Timestamp("2010-01-01")


def test_calendar_windows_roll_forward_by_step_years():
    df = _make_daily_df("2010-01-01", "2020-12-31")
    windows = generate_calendar_windows(df, start_year=2010, train_years=3, test_years=1, step_years=1)

    assert windows[1]["train_start_nominal"] == pd.Timestamp("2011-01-01")
    assert windows[2]["train_start_nominal"] == pd.Timestamp("2012-01-01")


def test_calendar_windows_two_different_start_years_are_independent():
    """The exact scenario requested: a start_year=2010 sequence and a
    start_year=2011 sequence over the SAME data, as two separate sequences."""
    df = _make_daily_df("2010-01-01", "2020-12-31")
    windows_2010 = generate_calendar_windows(df, start_year=2010, train_years=3, test_years=1, step_years=1)
    windows_2011 = generate_calendar_windows(df, start_year=2011, train_years=3, test_years=1, step_years=1)

    assert windows_2010[0]["train_start_nominal"] == pd.Timestamp("2010-01-01")
    assert windows_2011[0]["train_start_nominal"] == pd.Timestamp("2011-01-01")
    # Same train/test lengths, just offset by a year -- not the same windows.
    assert windows_2010[0] != windows_2011[0]


def test_calendar_windows_defaults_start_year_to_data_first_year():
    df = _make_daily_df("2015-03-15", "2020-12-31")
    windows = generate_calendar_windows(df, start_year=None, train_years=2, test_years=1, step_years=1)
    assert windows[0]["train_start_nominal"] == pd.Timestamp("2015-01-01")


def test_calendar_windows_flags_truncated_tail_window():
    """Data ending mid-year must still produce a final window, marked truncated,
    rather than being silently dropped or silently treated as complete."""
    df = _make_daily_df("2010-01-01", "2016-06-15")  # ends mid-2016, not on a year boundary
    windows = generate_calendar_windows(df, start_year=2010, train_years=3, test_years=1, step_years=1)

    last = windows[-1]
    assert last["truncated"] is True
    assert last["test_end_actual"] <= pd.Timestamp("2016-06-15")
    # Every earlier window must be a full, non-truncated window.
    assert all(not w["truncated"] for w in windows[:-1])


def test_calendar_windows_empty_when_start_year_past_data_end():
    df = _make_daily_df("2010-01-01", "2012-12-31")
    windows = generate_calendar_windows(df, start_year=2020, train_years=3, test_years=1, step_years=1)
    assert windows == []


def test_calendar_windows_clips_start_before_data_start():
    """A start_year earlier than the data itself shouldn't crash, and
    shouldn't produce a window with an empty train period either -- the
    loop must advance past every train_start whose window would be
    entirely before the data starts, and only emit the first window that
    actually contains real train data (whose train_start_actual is then
    the data's own first bar, not the fictional nominal start_year)."""
    df = _make_daily_df("2015-01-01", "2020-12-31")
    windows = generate_calendar_windows(df, start_year=2005, train_years=3, test_years=1, step_years=1)
    assert len(windows) > 0
    assert windows[0]["train_start_actual"] == pd.Timestamp("2015-01-01")
    # The nominal start_year asked for (2005) is NOT what's reported --
    # it's whichever later iteration first produced real train content.
    assert windows[0]["train_start_nominal"].year >= 2005


def test_calendar_windows_positions_are_contiguous_train_to_test():
    df = _make_daily_df("2010-01-01", "2020-12-31")
    windows = generate_calendar_windows(df, start_year=2010, train_years=2, test_years=1, step_years=1)
    for w in windows:
        assert w["test_start_pos"] == w["train_end_pos"]
        assert w["train_start_pos"] < w["train_end_pos"] <= w["test_start_pos"] < w["test_end_pos"]


def test_write_multi_run_summary_groups_by_run(tmp_path):
    runs = [
        {
            "run_label": "run_2010", "start_year": 2010, "train_years": 3, "test_years": 1, "step_years": 1,
            "windows": [
                {"window_id": "run_2010/window_0000", "train_date_start": "2010-01-01", "train_date_end": "2012-12-31",
                 "test_date_start": "2013-01-01", "test_date_end": "2013-12-31", "truncated": False,
                 "n_train_candidates": 5, "n_accepted": 1,
                 "accepted_edges": [{"edge_id": "A", "condition": "rsi_14 < 30", "direction": "long",
                                      "optimal_holding_bars": 5, "test_expectancy_r": 0.1,
                                      "test_profit_factor": 1.3, "test_n_trades": 20}]},
            ],
        },
        {
            "run_label": "run_2011", "start_year": 2011, "train_years": 3, "test_years": 1, "step_years": 1,
            "windows": [
                {"window_id": "run_2011/window_0000", "train_date_start": "2011-01-01", "train_date_end": "2013-12-31",
                 "test_date_start": "2014-01-01", "test_date_end": "2014-12-31", "truncated": False,
                 "n_train_candidates": 0, "n_accepted": 0, "accepted_edges": []},
            ],
        },
    ]
    path = tmp_path / "WALKFORWARD_SUMMARY.md"
    write_multi_run_summary(runs, path)

    content = path.read_text()
    assert "run_2010" in content
    assert "run_2011" in content
    assert "start_year=2010" in content
    assert "start_year=2011" in content
    assert "rsi_14 < 30" in content
