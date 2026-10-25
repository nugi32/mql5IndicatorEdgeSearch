"""Tests for the economic-calendar loader / feature builder and the new exporter columns."""

import numpy as np
import pandas as pd
import pytest

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    ConditionGenerator,
    Operator,
    calendar_columns_used,
    custom_indicator_columns_used,
)
from edge_research.ingestion import economic_calendar as cal
from edge_research.ingestion.loader import (
    ingest_pipeline,
    load_csv_and_validate,
    validate_export_schema,
)

CALENDAR_HEADER = (
    "time_server,event_id,country,currency,event_name,importance,sector,event_type,unit,"
    "multiplier,actual,forecast,previous,revised_previous,impact_type,revision"
)


def _calendar_csv(tmp_path, rows):
    path = tmp_path / "economic_calendar.csv"
    path.write_text(CALENDAR_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _row(time, event_id, ccy, importance, actual="", forecast="", impact=0, etype=0):
    return (
        f"{time},{event_id},US,{ccy},Test event {event_id},{importance},0,{etype},0,0,"
        f"{actual},{forecast},,,{impact},0"
    )


def _bars(start, n, freq="30min"):
    return pd.date_range(start, periods=n, freq=freq)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_currencies_for_symbol():
    assert cal.currencies_for_symbol("XAUUSD") == ["USD"]
    assert cal.currencies_for_symbol("EURUSD") == ["EUR", "USD"]
    assert cal.currencies_for_symbol("xauusd.m") == ["USD"]
    with pytest.raises(ValueError):
        cal.currencies_for_symbol("GOLD")


def test_timeframe_seconds():
    assert cal.timeframe_seconds("M30") == 1800
    assert cal.timeframe_seconds("h1") == 3600
    with pytest.raises(ValueError):
        cal.timeframe_seconds("M7")


def test_options_from_config_overrides_defaults():
    opts = cal.calendar_options_from_config({"calendar_max_minutes": 600, "unrelated": 1})
    assert opts["max_minutes"] == 600
    assert opts["importance_high"] == cal.DEFAULT_CALENDAR_OPTIONS["importance_high"]


# ---------------------------------------------------------------------------
# load_calendar_csv
# ---------------------------------------------------------------------------

def test_load_calendar_csv_parses_types_and_sorts(tmp_path):
    path = _calendar_csv(tmp_path, [
        _row("2024-01-05 15:30:00", 2, "usd", 3, actual="216.0", forecast="170.0", impact=1),
        _row("2024-01-05 10:00:00", 1, "EUR", 2),
    ])
    ev = cal.load_calendar_csv(path)
    assert list(ev["time_server"]) == [pd.Timestamp("2024-01-05 10:00"), pd.Timestamp("2024-01-05 15:30")]
    assert ev["currency"].tolist() == ["EUR", "USD"]          # upper-cased
    assert ev["actual"].isna().tolist() == [True, False]       # empty cell -> NaN
    assert ev["importance"].dtype.kind in "if"


def test_load_calendar_csv_requires_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="missing required"):
        cal.load_calendar_csv(path)


# ---------------------------------------------------------------------------
# build_calendar_features
# ---------------------------------------------------------------------------

@pytest.fixture
def events(tmp_path):
    path = _calendar_csv(tmp_path, [
        # coverage anchors (low importance, USD) so the whole day is "covered"
        _row("2024-01-05 00:00:00", 90, "USD", 1),
        _row("2024-01-05 23:59:00", 91, "USD", 1),
        # high-impact USD release at 13:30 with an actual value and a positive-USD impact
        _row("2024-01-05 13:30:00", 1, "USD", 3, actual="216.0", forecast="170.0", impact=1),
        # moderate EUR event: must be ignored for XAUUSD
        _row("2024-01-05 09:00:00", 2, "EUR", 3, actual="1.0", forecast="0.5", impact=1),
        # moderate USD event
        _row("2024-01-05 16:00:00", 3, "USD", 2),
    ])
    return cal.load_calendar_csv(path)


def test_features_schedule_columns(events):
    idx = _bars("2024-01-05 12:00", 8)           # 12:00 .. 15:30 bar opens
    f = cal.build_calendar_features(idx, "M30", events, "XAUUSD")

    # Bar opening 13:00 closes 13:30 == event time: still "next", not yet "known".
    row_1300 = f.loc[pd.Timestamp("2024-01-05 13:00")]
    assert row_1300["cal_min_to_next_high"] == 0.0
    assert row_1300["cal_high_in_bar"] == 0.0
    assert row_1300["cal_high_next_bar"] == 1.0   # the bar we would enter contains the release
    assert row_1300["cal_last_impact_sym"] == 0.0

    # Bar opening 13:30 closes 14:00: the release happened inside it.
    row_1330 = f.loc[pd.Timestamp("2024-01-05 13:30")]
    assert row_1330["cal_high_in_bar"] == 1.0
    assert row_1330["cal_min_since_last_high"] == 30.0
    # Positive USD impact on a USD-quoted symbol = bearish: -1
    assert row_1330["cal_last_impact_sym"] == -1.0

    # 12:00 bar closes 12:30 -> 60 minutes to the 13:30 release; EUR event (09:00) ignored.
    row_1200 = f.loc[pd.Timestamp("2024-01-05 12:00")]
    assert row_1200["cal_min_to_next_high"] == 60.0
    assert row_1200["cal_min_since_last_high"] == cal.DEFAULT_CALENDAR_OPTIONS["max_minutes"]


def test_medplus_tier_includes_moderate_events(events):
    idx = _bars("2024-01-05 15:00", 2)
    f = cal.build_calendar_features(idx, "M30", events, "XAUUSD")
    # bar 15:00 closes 15:30; moderate USD event at 16:00 is 30 min away,
    # but the next HIGH event does not exist any more -> capped.
    assert f.iloc[0]["cal_min_to_next_medplus"] == 30.0
    assert f.iloc[0]["cal_min_to_next_high"] == cal.DEFAULT_CALENDAR_OPTIONS["max_minutes"]


def test_impact_decays_to_zero_after_max_age(events):
    idx = _bars("2024-01-05 13:30", 20)          # up to 23:00
    f = cal.build_calendar_features(idx, "M30", events, "XAUUSD", {"impact_max_age_min": 60})
    assert f.loc[pd.Timestamp("2024-01-05 13:30"), "cal_last_impact_sym"] == -1.0
    assert f.loc[pd.Timestamp("2024-01-05 17:00"), "cal_last_impact_sym"] == 0.0


def test_impact_orientation_for_base_currency(tmp_path):
    path = _calendar_csv(tmp_path, [
        _row("2024-01-05 00:00:00", 90, "EUR", 1),
        _row("2024-01-05 23:59:00", 91, "EUR", 1),
        _row("2024-01-05 10:00:00", 1, "EUR", 3, actual="2.0", forecast="1.0", impact=1),
    ])
    ev = cal.load_calendar_csv(path)
    f = cal.build_calendar_features(_bars("2024-01-05 10:00", 2), "M30", ev, "EURUSD")
    # positive EUR impact on EURUSD (EUR = base) = bullish: +1
    assert f.iloc[0]["cal_last_impact_sym"] == 1.0


def test_bars_outside_calendar_coverage_are_nan(events):
    idx = pd.DatetimeIndex(["2023-06-01 10:00", "2024-01-05 12:00", "2024-03-01 10:00"])
    f = cal.build_calendar_features(idx, "M30", events, "XAUUSD")
    assert f.iloc[0].isna().all()
    assert f.iloc[2].isna().all()
    assert f.iloc[1].notna().all()


def test_holidays_are_excluded(tmp_path):
    path = _calendar_csv(tmp_path, [
        _row("2024-01-05 00:00:00", 90, "USD", 1),
        _row("2024-01-05 23:59:00", 91, "USD", 1),
        _row("2024-01-05 14:00:00", 5, "USD", 3, etype=2),   # holiday
    ])
    ev = cal.load_calendar_csv(path)
    f = cal.build_calendar_features(_bars("2024-01-05 12:00", 1), "M30", ev, "XAUUSD")
    assert f.iloc[0]["cal_min_to_next_high"] == cal.DEFAULT_CALENDAR_OPTIONS["max_minutes"]


def test_surprise_zscore_uses_only_previous_releases(tmp_path):
    # Same event id released 7 times; the 7th has a huge surprise.
    rows = [_row("2024-01-01 00:00:00", 90, "USD", 1), _row("2024-01-31 23:59:00", 91, "USD", 1)]
    for day in range(1, 7):
        rows.append(_row(f"2024-01-{day:02d} 13:30:00", 7, "USD", 3,
                         actual=str(100 + day % 2), forecast="100", impact=1))
    rows.append(_row("2024-01-20 13:30:00", 7, "USD", 3, actual="150", forecast="100", impact=1))
    ev = cal.load_calendar_csv(_calendar_csv(tmp_path, rows))
    idx = pd.DatetimeIndex(["2024-01-03 14:00", "2024-01-20 14:00"])
    f = cal.build_calendar_features(idx, "M30", ev, "XAUUSD")
    # Third release: only 2 prior surprises < min_history (4) -> NaN, not a made-up number.
    assert np.isnan(f.iloc[0]["cal_last_surprise_absz"])
    # Seventh release: |50| over a small prior std -> large z-score.
    assert f.iloc[1]["cal_last_surprise_absz"] > 5


def test_attach_calendar_features_adds_float32_columns(events, tmp_path):
    idx = _bars("2024-01-05 12:00", 6)
    df = pd.DataFrame({"close": np.arange(6, dtype=np.float32)}, index=idx)
    path = _calendar_csv(tmp_path, [
        _row("2024-01-05 00:00:00", 90, "USD", 1),
        _row("2024-01-05 23:59:00", 91, "USD", 1),
        _row("2024-01-05 13:30:00", 1, "USD", 3, actual="1", forecast="0", impact=1),
    ])
    out = cal.attach_calendar_features(df, path, "XAUUSD", "M30")
    cal_cols = [c for c in out.columns if c.startswith("cal_")]
    assert len(cal_cols) == 10
    assert all(out[c].dtype == np.float32 for c in cal_cols)
    with pytest.raises(ValueError, match="already contains"):
        cal.attach_calendar_features(out, path, "XAUUSD", "M30")


# ---------------------------------------------------------------------------
# loader: dataExporter.mq5 format + schema validation + ingest hook
# ---------------------------------------------------------------------------

def _exporter_csv(tmp_path, n=60, with_custom=True, custom_nan=False):
    times = pd.date_range("2024-01-05 00:00", periods=n, freq="30min")
    rng = np.random.default_rng(1)
    data = {
        # dataExporter.mq5: TimeToString(...) with the dots removed -> "20240105 13:30"
        "time": times.strftime("%Y%m%d %H:%M"),
        "open": 2000 + rng.normal(size=n).cumsum(),
        "high": 2001 + rng.normal(size=n).cumsum(),
        "low": 1999 + rng.normal(size=n).cumsum(),
        "close": 2000 + rng.normal(size=n).cumsum(),
        "tick_volume": rng.integers(100, 1000, n),
        "atr_14": np.full(n, 5.0),
    }
    if with_custom:
        nan = np.nan
        data.update({
            "volregime_atr_pctl": np.full(n, nan) if custom_nan else rng.uniform(0, 100, n),
            "volregime_atr_ratio": np.full(n, nan) if custom_nan else rng.uniform(0.5, 1.5, n),
            "volregime_regime": np.full(n, nan) if custom_nan else rng.integers(0, 3, n).astype(float),
            "ps_dist_pdh_atr": rng.normal(size=n),
            "ps_dist_pdl_atr": rng.normal(size=n),
            "ps_dist_sess_h_atr": rng.normal(size=n),
            "ps_dist_sess_l_atr": rng.normal(size=n),
            "ps_dist_round_up_atr": rng.uniform(0, 2, n),
            "ps_dist_round_dn_atr": -rng.uniform(0, 2, n),
            "ps_gap_atr": rng.normal(size=n),
            "ps_gap_fill_pct": rng.uniform(0, 100, n),
        })
    path = tmp_path / "XAUUSD_M30_export_20241021.csv"
    pd.DataFrame(data).to_csv(path, index=False, na_rep="NaN")
    return path


def test_loader_parses_dataexporter_time_format(tmp_path):
    df = load_csv_and_validate(_exporter_csv(tmp_path))
    assert df.index[0] == pd.Timestamp("2024-01-05 00:00")
    assert df.index[1] == pd.Timestamp("2024-01-05 00:30")
    assert "volregime_regime" in df.columns and "ps_gap_fill_pct" in df.columns


def test_schema_validation_reports_groups(tmp_path):
    df = load_csv_and_validate(_exporter_csv(tmp_path))
    rep = validate_export_schema(df)
    assert rep["custom_groups_present"] == ["VolRegime_ATR", "PriceStructure"]
    assert rep["custom_groups_missing"] == ["news"]     # this export has no news_* columns

    old = load_csv_and_validate(_exporter_csv(tmp_path, with_custom=False))
    assert validate_export_schema(old)["custom_groups_missing"] == ["VolRegime_ATR", "PriceStructure", "news"]


def test_schema_validation_flags_all_nan_indicator(tmp_path, caplog):
    df = load_csv_and_validate(_exporter_csv(tmp_path, custom_nan=True))
    with caplog.at_level("WARNING"):
        rep = validate_export_schema(df)
    assert rep["custom_groups_empty"] == ["VolRegime_ATR"]
    assert "iCustom" in caplog.text


def test_ingest_pipeline_with_calendar(tmp_path):
    csv_path = _exporter_csv(tmp_path)
    cal_path = _calendar_csv(tmp_path, [
        _row("2024-01-05 00:00:00", 90, "USD", 1),
        _row("2024-01-06 00:00:00", 91, "USD", 1),
        _row("2024-01-05 13:30:00", 1, "USD", 3, actual="216", forecast="170", impact=1),
    ])
    df, parquet_path = ingest_pipeline(
        csv_path, tmp_path / "storage", "XAUUSD", "M30", compression="snappy", calendar_csv=cal_path,
    )
    assert "cal_min_to_next_high" in df.columns
    assert parquet_path.exists()

    df_plain, _ = ingest_pipeline(csv_path, tmp_path / "storage2", "XAUUSD", "M30", compression="snappy")
    assert not any(c.startswith("cal_") for c in df_plain.columns)


# ---------------------------------------------------------------------------
# condition generation for the new columns
# ---------------------------------------------------------------------------

def test_condition_generator_creates_atoms_for_new_columns(tmp_path):
    df = load_csv_and_validate(_exporter_csv(tmp_path))
    cal_path = _calendar_csv(tmp_path, [
        _row("2024-01-05 00:00:00", 90, "USD", 1),
        _row("2024-01-06 00:00:00", 91, "USD", 1),
        _row("2024-01-05 13:30:00", 1, "USD", 3, actual="216", forecast="170", impact=1),
    ])
    cal.attach_calendar_features(df, cal_path, "XAUUSD", "M30")

    atoms = list(ConditionGenerator(df, {}).generate_atomic_conditions())
    by_col = {}
    for a in atoms:
        by_col.setdefault(a.column, []).append(a)

    assert {a.threshold for a in by_col["volregime_regime"]} == {0.0, 1.0, 2.0}
    assert all(a.operator == Operator.EQ for a in by_col["volregime_regime"])
    assert "volregime_atr_pctl" in by_col and "volregime_atr_ratio" in by_col
    for col in ("ps_dist_pdh_atr", "ps_dist_round_dn_atr", "ps_gap_atr", "ps_gap_fill_pct"):
        assert col in by_col, col
    assert "cal_min_to_next_high" in by_col
    assert {a.threshold for a in by_col["cal_last_impact_sym"]} == {1.0, -1.0}
    assert all(a.threshold == 1.0 for a in by_col["cal_high_in_bar"])
    # No atom is created for columns that are not in the frame.
    assert not any(a.column == "ps_dist_nonexistent" for a in atoms)


def test_condition_generator_unchanged_without_new_columns():
    n = 30
    df = pd.DataFrame({"close": np.arange(n, dtype=np.float32), "rsi_14": np.linspace(10, 90, n, dtype=np.float32)})
    atoms = list(ConditionGenerator(df, {}).generate_atomic_conditions())
    assert atoms and all(a.column == "rsi_14" for a in atoms)


def test_condition_flag_helpers():
    combo = CombinedCondition([
        AtomicCondition("rsi_7", Operator.LT, 20.0),
        AtomicCondition("cal_min_to_next_high", Operator.LT, 30.0),
        AtomicCondition("volregime_regime", Operator.EQ, 2.0),
    ])
    assert calendar_columns_used(combo) == ["cal_min_to_next_high"]
    assert custom_indicator_columns_used(combo) == ["volregime_regime"]
    plain = AtomicCondition("ma_5_lwma", Operator.GT, "close")
    assert calendar_columns_used(plain) == [] and custom_indicator_columns_used(plain) == []


# ---------------------------------------------------------------------------
# news_* columns written by dataExporter.mq5 v1.02
# ---------------------------------------------------------------------------

NEWS_HEADER = [
    "news_min_to_next", "news_next_importance", "news_min_since_last",
    "news_last_importance", "news_last_surprise", "news_in_window", "news_count_next_24h",
]


def _news_csv(tmp_path, news_rows):
    """Exporter-style CSV: time + OHLC + the 7 news columns (one row per tuple)."""
    n = len(news_rows)
    times = pd.date_range("2024-01-05 10:00", periods=n, freq="30min")
    df = pd.DataFrame(news_rows, columns=NEWS_HEADER)
    df.insert(0, "time", times.strftime("%Y%m%d %H:%M"))
    for col in ("open", "high", "low", "close"):
        df[col] = 2000.0
    path = tmp_path / "XAUUSD_M30_export_news.csv"
    df.to_csv(path, index=False, na_rep="NaN")
    return path


def test_news_event_exactly_at_bar_close_does_not_leak_surprise(tmp_path):
    nan = np.nan
    path = _news_csv(tmp_path, [
        # (to_next, next_imp, since_last, last_imp, surprise, in_window, count24)
        (120.0, 3, 600.0, 3, 5.0, 0, 2),      # normal row
        (30.0, 3, 630.0, 3, 5.0, 1, 2),       # normal row
        (480.0, 3, 0.0, 3, 85.0, 1, 1),       # event exactly at bar close, surprise already filled
        (450.0, 3, 30.0, 3, 85.0, 1, 1),      # next bar: the release is now genuinely in the past
    ])
    df = load_csv_and_validate(path)

    leak = df.iloc[2]
    assert np.isnan(leak["news_last_surprise"])           # outcome not known at decision time
    assert np.isnan(leak["news_min_since_last"]) and np.isnan(leak["news_last_importance"])
    assert leak["news_min_to_next"] == 0.0                # the event is imminent instead
    assert leak["news_next_importance"] == 3.0
    assert leak["news_count_next_24h"] == 2.0             # 1 reported + the event at the close
    assert leak["news_in_window"] == 1.0

    assert df.iloc[3]["news_last_surprise"] == pytest.approx(85.0)   # legitimately known one bar later
    assert df.iloc[0]["news_last_surprise"] == pytest.approx(5.0)    # untouched


def test_news_rows_outside_calendar_range_become_nan(tmp_path):
    nan = np.nan
    path = _news_csv(tmp_path, [
        (9000.0, 3, nan, nan, nan, 0, 0),     # before the first event of the calendar file
        (60.0, 3, 120.0, 3, 1.0, 0, 1),       # covered
        (nan, nan, 30.0, 3, 1.0, 0, 0),       # after the last event
    ])
    df = load_csv_and_validate(path)
    assert df.iloc[0][NEWS_HEADER].isna().all()
    assert df.iloc[2][NEWS_HEADER].isna().all()
    assert df.iloc[1][NEWS_HEADER].notna().all()


def test_news_columns_all_nan_warns_calendar_not_loaded(tmp_path, caplog):
    nan = np.nan
    path = _news_csv(tmp_path, [(nan,) * 7] * 4)
    with caplog.at_level("WARNING"):
        df = load_csv_and_validate(path)
    assert "LIVE chart" in caplog.text
    assert validate_export_schema(df)["custom_groups_empty"] == ["news"]


def test_sanitize_is_noop_without_news_columns(tmp_path):
    from edge_research.ingestion.loader import sanitize_news_columns
    df = load_csv_and_validate(_exporter_csv(tmp_path, with_custom=False))
    assert sanitize_news_columns(df) == {"boundary_rows": 0, "uncovered_rows": 0}


def test_news_atoms_generated_and_flagged(tmp_path):
    path = _news_csv(tmp_path, [
        (120.0, 2, 600.0, 3, 5.0, 0, 2),
        (30.0, 3, 630.0, 2, -2.0, 1, 3),
        (60.0, 3, 90.0, 3, 1.0, 0, 1),
    ])
    df = load_csv_and_validate(path)
    atoms = list(ConditionGenerator(df, {}).generate_atomic_conditions())
    by_col = {}
    for a in atoms:
        by_col.setdefault(a.column, []).append(a)

    assert {"news_min_to_next", "news_min_since_last", "news_in_window",
            "news_count_next_24h", "news_next_importance", "news_last_importance",
            "news_last_surprise"} <= set(by_col)
    assert {a.threshold for a in by_col["news_next_importance"]} == {2.0, 3.0}
    # surprise: sign only, never a magnitude threshold
    assert {(a.operator, a.threshold) for a in by_col["news_last_surprise"]} == {
        (Operator.GT, 0.0), (Operator.LT, 0.0)}

    combo = CombinedCondition([by_col["news_in_window"][0], AtomicCondition("rsi_7", Operator.LT, 20.0)])
    assert calendar_columns_used(combo) == ["news_in_window"]


def test_constant_importance_column_creates_no_atoms(tmp_path):
    path = _news_csv(tmp_path, [(60.0, 3, 90.0, 3, 1.0, 0, 1)] * 4)   # only HIGH events exported
    df = load_csv_and_validate(path)
    cols = {a.column for a in ConditionGenerator(df, {}).generate_atomic_conditions()}
    assert "news_next_importance" not in cols and "news_last_importance" not in cols
