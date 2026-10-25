"""Tests for the post-run ranker."""

import pandas as pd

from edge_research.ranking.ranker import (
    RankerConfig, are_similar, load_window_results, parse_condition,
    ranker_config_from_dict, rank_timeframe, rank_window, run_ranker, _normalise,
)


def _row(cond, direction="long", hold=10, n=60, pf=1.8, exp=0.25, train=0.27,
         sens=0.9, passed=True, cal=False):
    return {"edge_id": 1, "condition": cond, "direction": direction,
            "optimal_holding_bars": hold, "train_expectancy_r": train,
            "train_sensitivity_score": sens, "test_n_trades": n,
            "test_expectancy_r": exp, "test_profit_factor": pf,
            "test_passed": passed, "uses_calendar": cal, "uses_custom_indicators": False}


def _write(run_dir, label, rows):
    d = run_dir / label
    d.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(d / "TEST_PERIOD_RESULTS.csv", index=False)


def test_parse_condition():
    assert parse_condition("rsi_14 < 30.0 AND ema_20 > ema_50") == [
        ("rsi_14", "<", 30.0), ("ema_20", ">", "ema_50")]


def test_similarity_rules():
    cfg = RankerConfig()
    mk = lambda c, **k: _normalise(pd.DataFrame([_row(c, **k)]))[0]
    a = mk("rsi_14 < 30.0")
    assert are_similar(a, mk("rsi_14 < 25.0"), cfg)               # close threshold
    assert not are_similar(a, mk("rsi_14 < 10.0"), cfg)           # far threshold
    assert not are_similar(a, mk("rsi_14 < 25.0", direction="short"), cfg)
    assert not are_similar(a, mk("rsi_14 > 30.0"), cfg)           # other operator
    assert not are_similar(a, mk("rsi_14 < 30.0", hold=40), cfg)  # far holding bars
    assert not are_similar(a, mk("rsi_14 < 30.0 AND atr_14 > 1.0"), cfg)


def test_isolated_spike_is_rejected_and_plateau_kept_with_dedupe():
    rows = [
        _row("rsi_14 < 30.0", pf=2.0),
        _row("rsi_14 < 28.0", pf=1.9),
        _row("rsi_14 < 26.0", pf=1.8),
        _row("atr_14 > 5.0", pf=3.0),         # great PF but no similar neighbour -> spike
    ]
    res = rank_window(pd.DataFrame(rows), RankerConfig())
    conds = [r["condition"] for r in res["top"]]
    assert "atr_14 > 5.0" not in conds
    assert res["rejected"].get("no_plateau") == 1
    assert len(res["top"]) == 1 and conds[0] == "rsi_14 < 30.0"   # duplicates collapsed
    assert len(res["top"][0]["similar"]) == 2


def test_bad_neighbours_lower_plateau():
    good = [_row("rsi_14 < 30.0"), _row("rsi_14 < 28.0"), _row("rsi_14 < 26.0")]
    mixed = [_row("rsi_14 < 30.0"), _row("rsi_14 < 28.0", pf=0.8, exp=-0.1, passed=False),
             _row("rsi_14 < 26.0", pf=0.8, exp=-0.1, passed=False)]
    cfg = RankerConfig(min_plateau_score=0.0)
    p_good = rank_window(pd.DataFrame(good), cfg)["top"][0]["plateau_score"]
    p_mixed = rank_window(pd.DataFrame(mixed), cfg)["top"][0]["plateau_score"]
    assert p_good > p_mixed


def test_frequency_and_pf_filters():
    rows = [_row("rsi_14 < 30.0", n=5), _row("rsi_14 < 29.0", n=5),
            _row("ema_20 > 1.0", pf=1.1), _row("ema_20 > 1.05", pf=1.1)]
    res = rank_window(pd.DataFrame(rows), RankerConfig())
    assert res["n_pass"] == 0
    assert res["rejected"]["low_frequency"] == 2 and res["rejected"]["low_pf"] == 2


def test_stability_raises_score():
    stable = [_row("rsi_14 < 30.0", exp=0.25, train=0.26), _row("rsi_14 < 28.0", exp=0.25, train=0.26)]
    unstable = [_row("rsi_14 < 30.0", exp=0.25, train=1.5), _row("rsi_14 < 28.0", exp=0.25, train=1.5)]
    s1 = rank_window(pd.DataFrame(stable), RankerConfig())["top"][0]["score"]
    s2 = rank_window(pd.DataFrame(unstable), RankerConfig())["top"][0]["score"]
    assert s1 > s2


def test_timeframe_aggregation_needs_windows_and_total_trades(tmp_path):
    for i in range(3):
        _write(tmp_path, f"run_2015/window_{i:04d}", [
            _row("rsi_14 < 30.0", n=40), _row("rsi_14 < 28.0", n=40),
            _row("atr_14 > 5.0", n=40)] if i < 3 else [])
    # extra combination seen in a single window only
    _write(tmp_path, "run_2015/window_0003", [_row("macd > 2.0", n=500), _row("macd > 2.1", n=500)])
    wins = load_window_results(tmp_path)
    assert list(wins)[0] == "run_2015/window_0000"
    res = rank_timeframe(wins, RankerConfig())
    conds = [r["condition"] for r in res["top"]]
    assert conds == ["rsi_14 < 30.0"]            # 28.0 is a duplicate, atr has no plateau, macd too few windows
    top = res["top"][0]
    assert top["n_trades"] == 120 and top["n_windows_passed"] == 3
    assert res["rejected"].get("few_windows", 0) >= 2


def test_run_ranker_writes_files_and_flags(tmp_path):
    for i in range(3):
        _write(tmp_path, f"window_{i:04d}", [
            _row("cal_minutes_to_next_high > 30.0", cal=True, n=50),
            _row("cal_minutes_to_next_high > 28.0", cal=True, n=50)])
    md = run_ranker(tmp_path, "XAUUSD", "H1")
    text = md.read_text()
    assert text.startswith("# Ranker result — XAUUSD H1")
    assert "## Result top per timeframe" in text and "## Result window window_0001" in text
    assert "CAL" in text
    assert (tmp_path / "ranker_top.csv").exists()


def test_no_results_returns_none(tmp_path):
    assert run_ranker(tmp_path, "X", "H1") is None


def test_config_overrides_from_dict():
    cfg = ranker_config_from_dict({"ranker_min_pf": 1.6, "ranker_top_n_window": 5})
    assert cfg.min_pf == 1.6 and cfg.top_n_window == 5 and cfg.min_windows == 3
