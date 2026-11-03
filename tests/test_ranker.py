"""Tests for the post-run sort ranker."""

import math

import pandas as pd
import pytest

from edge_research.ranking import ranker as ranker_module
from edge_research.ranking.ranker import (
    RankerConfig, are_similar, collapse_identical, load_gate_results, load_window_results,
    parse_condition, ranker_config_from_dict, rank_timeframe, rank_window, run_ranker, _normalise,
)


def _row(cond, direction="long", hold=10, n=60, pf=1.8, exp=0.25, train=0.27,
         sens=0.9, passed=True, cal=False):
    """
    One row of a walk-forward TEST_PERIOD_RESULTS.csv. The ranker collapses rows with the same
    (direction, holding bars, trades, expectancy), so tests give related rows different ``n``.
    """
    return {"edge_id": 1, "condition": cond, "direction": direction,
            "optimal_holding_bars": hold, "train_expectancy_r": train,
            "train_sensitivity_score": sens, "test_n_trades": n,
            "test_expectancy_r": exp, "test_profit_factor": pf,
            "test_passed": passed, "uses_calendar": cal, "uses_custom_indicators": False}


def _gate_row(cond, direction="long", hold=10, n=60, pf=1.8, exp=0.25, passed=True, cal=False):
    """One row of a normal run's STRATEGY_GATE_RESULTS.csv (the real column set)."""
    return {"edge_id": 1, "condition": cond, "direction": direction, "gate_passed": passed,
            "reasons": "", "optimal_holding_bars": hold, "holding_bars_stable": True,
            "sim_n_trades": n, "sim_expectancy_r": exp, "sim_expectancy_r_ci_low": float("nan"),
            "sim_expectancy_r_ci_high": float("nan"), "sim_profit_factor": pf,
            "sim_win_rate": 0.5, "permutation_p_value": 0.01, "robust_walk_forward": True,
            "uses_calendar": cal, "uses_custom_indicators": False}


def _write(run_dir, label, rows):
    d = run_dir / label
    d.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(d / "TEST_PERIOD_RESULTS.csv", index=False)


def _write_gate(run_dir, rows):
    pd.DataFrame(rows).to_csv(run_dir / "STRATEGY_GATE_RESULTS.csv", index=False)


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


def test_isolated_spike_is_ranked_with_warning_and_plateau_is_deduped():
    rows = [
        _row("rsi_14 < 30.0", n=60, pf=2.0),
        _row("rsi_14 < 28.0", n=61, pf=1.9),
        _row("rsi_14 < 26.0", n=62, pf=1.8),
        _row("atr_14 > 5.0", n=63, pf=3.0),   # great PF but no similar neighbour -> spike
    ]
    res = rank_window(pd.DataFrame(rows), RankerConfig())
    by_cond = {r["condition"]: r for r in res["top"]}
    assert set(by_cond) == {"rsi_14 < 30.0", "atr_14 > 5.0"}      # the spike is listed, not rejected
    assert "no_plateau" in by_cond["atr_14 > 5.0"]["warnings"]
    assert by_cond["atr_14 > 5.0"]["plateau_score"] == 0.0
    assert len(by_cond["rsi_14 < 30.0"]["similar"]) == 2           # near-duplicates collapsed
    assert res["n_ranked"] == 4 and res["n_unique"] == 2


def test_bad_neighbours_lower_plateau():
    good = [_row("rsi_14 < 30.0", n=60), _row("rsi_14 < 28.0", n=61), _row("rsi_14 < 26.0", n=62)]
    mixed = [_row("rsi_14 < 30.0", n=60), _row("rsi_14 < 28.0", n=61, pf=0.8, exp=-0.1, passed=False),
             _row("rsi_14 < 26.0", n=62, pf=0.8, exp=-0.1, passed=False)]
    cfg = RankerConfig()
    p_good = rank_window(pd.DataFrame(good), cfg)["top"][0]["plateau_score"]
    p_mixed = rank_window(pd.DataFrame(mixed), cfg)["top"][0]["plateau_score"]
    assert p_good > p_mixed


def test_low_frequency_and_low_pf_are_warnings_not_rejections():
    rows = [_row("rsi_14 < 30.0", n=5), _row("rsi_14 < 29.0", n=6),
            _row("ema_20 > 1.0", n=60, pf=1.1), _row("ema_20 > 1.05", n=61, pf=1.1)]
    res = rank_window(pd.DataFrame(rows), RankerConfig(sort_dedupe=False))
    assert res["n_ranked"] == 4
    warn = {r["condition"]: r["warnings"] for r in res["top"]}
    assert "low_frequency" in warn["rsi_14 < 30.0"] and "low_pf" in warn["ema_20 > 1.0"]


def test_stability_raises_score():
    stable = [_row("rsi_14 < 30.0", n=60, exp=0.25, train=0.26), _row("rsi_14 < 28.0", n=61, exp=0.25, train=0.26)]
    unstable = [_row("rsi_14 < 30.0", n=60, exp=0.25, train=1.5), _row("rsi_14 < 28.0", n=61, exp=0.25, train=1.5)]
    s1 = rank_window(pd.DataFrame(stable), RankerConfig())["top"][0]["score"]
    s2 = rank_window(pd.DataFrame(unstable), RankerConfig())["top"][0]["score"]
    assert s1 > s2


def test_sort_keeps_everything_and_limits_top_n():
    rows = [_row("rsi_14 < 30.0", n=5, pf=1.1, passed=False),   # fails several checks
            _row("atr_14 > 5.0", n=60, pf=3.0),                 # isolated spike
            _row("macd > 1.0", n=61, pf=1.8), _row("ema_20 > 2.0", n=62, pf=1.7),
            _row("cci_20 > 100.0", n=63, pf=1.6)]
    res = rank_window(pd.DataFrame(rows), RankerConfig(sort_top_n=3))
    assert res["n_ranked"] == 5 and len(res["top"]) == 3
    scores = [r["score"] for r in res["top"]]
    assert scores == sorted(scores, reverse=True)
    allw = {w for r in rank_window(pd.DataFrame(rows), RankerConfig(sort_top_n=10))["top"]
            for w in r["warnings"]}
    assert {"low_frequency", "low_pf", "no_plateau", "test_failed"} <= allw


def test_timeframe_aggregation_counts_windows_and_total_trades(tmp_path):
    for i in range(3):
        _write(tmp_path, f"run_2015/window_{i:04d}", [
            _row("rsi_14 < 30.0", n=40), _row("rsi_14 < 28.0", n=41),
            _row("atr_14 > 5.0", n=42)])
    # extra combination seen in a single window only
    _write(tmp_path, "run_2015/window_0003", [_row("macd > 2.0", n=500), _row("macd > 2.1", n=501)])
    wins = load_window_results(tmp_path)
    assert list(wins)[0] == "run_2015/window_0000"
    res = rank_timeframe(wins, RankerConfig())
    by_cond = {r["condition"]: r for r in res["top"]}
    rsi = [c for c in by_cond if c.startswith("rsi_14")]
    assert len(rsi) == 1                                          # 30.0 / 28.0 are near-duplicates: one is listed
    top = by_cond[rsi[0]]
    assert top["n_trades"] == {"rsi_14 < 30.0": 120, "rsi_14 < 28.0": 123}[rsi[0]]
    assert top["n_windows_passed"] == 3 and len(top["similar"]) == 1
    assert "no_plateau" in by_cond["atr_14 > 5.0"]["warnings"]
    macd = [c for c in by_cond if c.startswith("macd")]
    assert len(macd) == 1 and "few_windows" in by_cond[macd[0]]["warnings"]     # seen in 1 window only


def test_run_ranker_walkforward_writes_sort_files_and_flags(tmp_path):
    for i in range(3):
        _write(tmp_path, f"window_{i:04d}", [
            _row("cal_minutes_to_next_high > 30.0", cal=True, n=50),
            _row("cal_minutes_to_next_high > 28.0", cal=True, n=51)])
    md = run_ranker(tmp_path, "XAUUSD", "H1")
    assert md == tmp_path / "ranker_sort_result.md"
    text = md.read_text(encoding="utf-8")
    assert text.startswith("# Ranker sort result — XAUUSD H1")
    assert "## Result top per timeframe" in text and "## Result window window_0001" in text
    assert "Warnings" in text and "CAL" in text
    csv = pd.read_csv(tmp_path / "ranker_sort_top.csv")
    assert {"rank", "condition", "direction", "holding_bars", "warnings"} <= set(csv.columns)
    assert "windows_passed" in csv.columns and "train_expectancy_r" in csv.columns


def test_no_results_returns_none(tmp_path):
    assert run_ranker(tmp_path, "X", "H1") is None


def test_config_overrides_from_dict():
    cfg = ranker_config_from_dict({"ranker_min_pf": 1.6, "ranker_sort_top_n": 5})
    assert cfg.min_pf == 1.6 and cfg.sort_top_n == 5 and cfg.min_windows == 3


def test_filter_mode_is_gone():
    import inspect
    assert not hasattr(ranker_module, "MODES")
    assert not hasattr(ranker_module, "OUTPUT_MD") and not hasattr(ranker_module, "OUTPUT_CSV")
    assert "mode" not in inspect.signature(run_ranker).parameters
    names = {f for f in RankerConfig.__dataclass_fields__}
    assert not names & {"top_n_timeframe", "top_n_window", "require_test_passed"}


# ---- identical copies ------------------------------------------------------------------

def test_collapse_identical_keeps_fewest_atoms():
    rows = _normalise(pd.DataFrame([
        _row("mom_10 > -5.0 AND rsi_14 < 30.0", n=80, exp=0.2),
        _row("rsi_14 < 30.0", n=80, exp=0.2),                  # same trades, fewest atoms -> kept
        _row("mom_10 > 0.0 AND rsi_14 < 30.0", n=80, exp=0.2),
        _row("rsi_14 < 30.0", n=81, exp=0.2),                  # other trade count -> own row
        _row("rsi_14 < 30.0", direction="short", n=80, exp=0.2),
        _row("rsi_14 < 30.0", hold=11, n=80, exp=0.2),
        _row("rsi_14 < 30.0", n=80, exp=0.21),
    ]))
    kept, removed = collapse_identical(rows)
    assert removed == 2 and len(kept) == 5
    first = kept[0]
    assert first["condition"] == "rsi_14 < 30.0" and len(first["similar"]) == 2


def test_collapse_identical_tie_keeps_first():
    rows = _normalise(pd.DataFrame([_row("a_1 > 1.0"), _row("b_2 > 2.0")]))
    kept, removed = collapse_identical(rows)
    assert removed == 1 and kept[0]["condition"] == "a_1 > 1.0"


def test_identical_copies_are_collapsed_even_without_near_duplicate_removal():
    rows = [_row("mom_10 > -5.0", n=90, exp=0.3), _row("mom_10 > 0.0", n=90, exp=0.3),
            _row("rsi_14 < 30.0", n=70, exp=0.2)]
    res = rank_window(pd.DataFrame(rows), RankerConfig(sort_dedupe=False))
    assert res["n_identical"] == 1 and res["n_total"] == 2
    assert [r["condition"] for r in res["top"]][0] in ("mom_10 > -5.0", "rsi_14 < 30.0")
    assert "mom_10 > 0.0" not in [r["condition"] for r in res["top"]]


# ---- normal run (STRATEGY_GATE_RESULTS.csv) ----------------------------------------------

def test_gate_columns_are_mapped(tmp_path):
    _write_gate(tmp_path, [_gate_row("rsi_14 < 30.0", n=77, pf=2.1, exp=0.33, passed=False, hold=12)])
    df = load_gate_results(tmp_path)
    assert df.loc[0, "test_n_trades"] == 77 and df.loc[0, "test_profit_factor"] == 2.1
    assert df.loc[0, "test_expectancy_r"] == 0.33 and not df.loc[0, "test_passed"]
    assert df.loc[0, "optimal_holding_bars"] == 12
    assert "train_expectancy_r" not in df.columns and "train_sensitivity_score" not in df.columns
    r = _normalise(df)[0]
    assert (r["n_trades"], r["pf"], r["test_exp"], r["holding_bars"]) == (77, 2.1, 0.33, 12)


def test_gate_input_missing_column_is_an_error(tmp_path):
    rows = pd.DataFrame([_gate_row("rsi_14 < 30.0")]).drop(columns=["sim_profit_factor"])
    rows.to_csv(tmp_path / "STRATEGY_GATE_RESULTS.csv", index=False)
    with pytest.raises(ValueError, match="sim_profit_factor"):
        load_gate_results(tmp_path)


def test_gate_input_empty_or_missing_returns_none(tmp_path):
    assert load_gate_results(tmp_path) is None
    pd.DataFrame(columns=list(_gate_row("x").keys())).to_csv(tmp_path / "STRATEGY_GATE_RESULTS.csv", index=False)
    assert load_gate_results(tmp_path) is None
    assert run_ranker(tmp_path, "X", "H1") is None


def test_single_run_has_no_stability_and_no_sensitivity_warning():
    df = pd.DataFrame([_gate_row("rsi_14 < 30.0"), _gate_row("rsi_14 < 28.0", n=61)]).rename(
        columns=ranker_module.GATE_COLUMN_MAP)
    res = rank_window(df, RankerConfig(), single_run=True)
    top = res["top"][0]
    assert "low_sensitivity" not in top["warnings"]
    assert "stability" not in top                                   # the term is not computed
    # Score uses the renormalised weights without "stab": PF 1.8, 0.25R, 60 trades, full plateau.
    w = {k: v for k, v in ranker_module.WEIGHTS_WINDOW.items() if k != "stab"}
    parts = {"pf": 0.4, "exp": 0.5, "freq": min(max(math.log10(top["n_trades"] / 20), 0), 1),
             "plateau": top["plateau_score"]}
    expected = 100 * sum(w[k] * parts[k] for k in w) / sum(w.values())
    assert top["score"] == pytest.approx(expected)


def test_single_run_failed_gate_is_a_warning(tmp_path):
    df = pd.DataFrame([_gate_row("rsi_14 < 30.0", passed=False)]).rename(columns=ranker_module.GATE_COLUMN_MAP)
    top = rank_window(df, RankerConfig(), single_run=True)["top"][0]
    assert "gate_failed" in top["warnings"] and "test_failed" not in top["warnings"]


def test_run_ranker_on_normal_run_writes_flat_list(tmp_path):
    rows = [_gate_row("rsi_14 < 30.0", n=300, pf=2.2, exp=0.4),
            _gate_row("mom_10 > -5.0", n=250, pf=1.9, exp=0.3),        # identical pair
            _gate_row("mom_10 > 0.0", n=250, pf=1.9, exp=0.3),
            _gate_row("cal_x > 1.0", n=200, pf=1.5, exp=0.1, cal=True, passed=False),
            _gate_row("atr_14 > 5.0", n=0, pf=float("nan"), exp=float("nan"))]   # no trades: skipped
    _write_gate(tmp_path, rows)
    md = run_ranker(tmp_path, "XAUUSD", "M5", RankerConfig(sort_top_n=10))
    text = md.read_text(encoding="utf-8")
    assert text.startswith("# Ranker sort result — XAUUSD M5") and "in-sample" in text
    assert "## Result\n" in text and "Result window" not in text and "Train Exp R" not in text
    assert "CAL" in text and "gate_failed" in text
    csv = pd.read_csv(tmp_path / "ranker_sort_top.csv")
    assert list(csv.columns)[:5] == ["rank", "condition", "direction", "holding_bars", "total_trades"]
    assert "windows_passed" not in csv.columns and "train_expectancy_r" not in csv.columns
    assert len(csv) == 3 and csv["rank"].tolist() == [1, 2, 3]
    assert "mom_10 > 0.0" not in csv["condition"].tolist()              # identical copy collapsed
    assert "atr_14 > 5.0" not in csv["condition"].tolist()


def test_walkforward_files_take_precedence_over_a_gate_file(tmp_path):
    _write_gate(tmp_path, [_gate_row("rsi_14 < 30.0")])
    _write(tmp_path, "window_0000", [_row("rsi_14 < 30.0"), _row("rsi_14 < 28.0")])
    run_ranker(tmp_path, "X", "H1")
    assert "windows_passed" in pd.read_csv(tmp_path / "ranker_sort_top.csv").columns


def test_empty_ranking_still_writes_a_readable_csv(tmp_path):
    _write_gate(tmp_path, [_gate_row("rsi_14 < 30.0", n=0, pf=float("nan"), exp=float("nan"))])
    run_ranker(tmp_path, "X", "H1")
    csv = pd.read_csv(tmp_path / "ranker_sort_top.csv")
    assert len(csv) == 0 and "condition" in csv.columns


def test_drop_below_floor_single_run():
    rows = [_gate_row("rsi_14 < 30.0", n=1500), _gate_row("atr_14 > 5.0", n=999, direction="short")]
    df = pd.DataFrame(rows).rename(columns=ranker_module.GATE_COLUMN_MAP)
    cfg = RankerConfig(min_window_trades=1000)
    kept = {r["condition"] for r in rank_window(df, cfg, single_run=True)["top"]}
    assert kept == {"rsi_14 < 30.0", "atr_14 > 5.0"}                # default: warned about, not dropped
    cfg = RankerConfig(min_window_trades=1000, drop_below_floor=True)
    kept = {r["condition"] for r in rank_window(df, cfg, single_run=True)["top"]}
    assert kept == {"rsi_14 < 30.0"}                                 # 1000 trades or more is kept, 999 is dropped
    exact = pd.DataFrame([_gate_row("rsi_14 < 30.0", n=1000)]).rename(columns=ranker_module.GATE_COLUMN_MAP)
    assert len(rank_window(exact, cfg, single_run=True)["top"]) == 1


def test_drop_below_floor_timeframe_only_uses_total_trades(tmp_path):
    for i in range(3):
        _write(tmp_path, f"run_2015/window_{i:04d}", [
            _row("rsi_14 < 30.0", n=400),            # 1200 trades in total
            _row("atr_14 > 5.0", n=100, direction="short")])   # 300 trades in total
    wins = load_window_results(tmp_path)
    cfg = RankerConfig(min_total_trades=1000, drop_below_floor=True)
    kept = {r["condition"] for r in rank_timeframe(wins, cfg)["top"]}
    assert kept == {"rsi_14 < 30.0"}
    # the per-window floor is untouched in walk-forward lists (still warnings only)
    assert len(rank_window(wins["run_2015/window_0000"], cfg)["top"]) == 2


def test_drop_below_floor_config_key():
    assert ranker_config_from_dict({"ranker_drop_below_floor": True, "ranker_min_total_trades": 1000}).drop_below_floor is True
    assert ranker_config_from_dict({}).drop_below_floor is False
