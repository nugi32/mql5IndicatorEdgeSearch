"""
Economic-calendar ingestion and per-bar feature building.

Input
-----
The CSV written by ``mql5/economicCalendarDataExporter.mq5`` (a script that
must be run on a LIVE chart, because the MT5 calendar API is unavailable in the
Strategy Tester). Header::

    time_server,event_id,country,currency,event_name,importance,sector,
    event_type,unit,multiplier,actual,forecast,previous,revised_previous,
    impact_type,revision

All times are broker SERVER time -- the same clock as the bar timestamps written
by ``mql5/dataExporter.mq5`` -- so no timezone conversion is done here.

Output
------
A handful of float32 ``cal_*`` columns aligned to the bar index, added to the
main dataframe by :func:`attach_calendar_features`. They become ordinary
indicator columns for the rest of the pipeline (condition generation, forward
profiling, validation, ...).

Look-ahead rules (a row stamped T describes the bar that OPENS at T)
---------------------------------------------------------------------
* The decision for a bar is taken at its CLOSE (``T + timeframe``); the simulator
  enters at the next bar's open. Every feature below only uses information that
  exists at that close time.
* "Next event" features use the SCHEDULE (event time >= bar close). A scheduled
  release time is public long before the release, so this is not look-ahead.
* "Last event" / impact / surprise features only use events with
  ``event time < bar close``. An event stamped exactly at the close is treated as
  not yet known (conservative).
* The surprise normalisation (expected std of ``actual - forecast``) is an
  expanding statistic over the PREVIOUS occurrences of the same event id only.
* Bars outside the calendar coverage (before the first / after the last exported
  event) get NaN, never "no news", so a short calendar file cannot fake a quiet
  market for the earlier years of a long price history.
"""

from __future__ import annotations

import csv
import logging
import re
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Bar length in seconds per MT5 timeframe label used by the exporter.
TIMEFRAME_SECONDS: Dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}

# Metals are quoted against a currency but have no calendar of their own: only
# the quote currency's events move them (XAUUSD -> USD).
_METAL_BASES = {"XAU", "XAG", "XPT", "XPD"}

# ENUM_CALENDAR_EVENT_TYPE: 0 = event, 1 = indicator, 2 = holiday.
_EVENT_TYPE_HOLIDAY = 2
# ENUM_CALENDAR_EVENT_IMPACT: 0 = not set, 1 = positive, 2 = negative
# (impact on the event currency).
_IMPACT_POSITIVE = 1
_IMPACT_NEGATIVE = 2

_REQUIRED_COLUMNS = ("time_server", "importance", "currency")
_NUMERIC_COLUMNS = (
    "event_id", "importance", "sector", "event_type", "unit", "multiplier",
    "actual", "forecast", "previous", "revised_previous", "impact_type", "revision",
)
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Defaults for every calendar option; overridable through pipeline_config.yaml
# keys named ``calendar_<option>``.
DEFAULT_CALENDAR_OPTIONS = {
    # Minimum MT5 importance (1 = low, 2 = moderate, 3 = high) for each tier.
    "importance_high": 3,
    "importance_medplus": 2,
    # Cap (minutes) for the "minutes to next / since last event" columns.
    "max_minutes": 1440,
    # The last-impact / last-surprise columns fall back to 0 after this many minutes.
    "impact_max_age_min": 240,
    # None = derive from the symbol (XAUUSD -> ["USD"], EURUSD -> ["EUR", "USD"]).
    "currencies": None,
    # Drop holiday rows (event_type == 2) from every feature.
    "exclude_holidays": True,
    # Previous occurrences needed before a surprise z-score is trusted.
    "surprise_min_history": 4,
}


def calendar_options_from_config(pipeline_config: Optional[dict]) -> dict:
    """Collect ``calendar_*`` keys from a loaded pipeline_config.yaml dict."""
    options = dict(DEFAULT_CALENDAR_OPTIONS)
    for key in DEFAULT_CALENDAR_OPTIONS:
        cfg_key = f"calendar_{key}"
        if pipeline_config and cfg_key in pipeline_config:
            options[key] = pipeline_config[cfg_key]
    return options


def timeframe_seconds(timeframe: str) -> int:
    """Bar length in seconds for an MT5 timeframe label such as 'M30'."""
    try:
        return TIMEFRAME_SECONDS[str(timeframe).upper()]
    except KeyError as exc:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. Known: {sorted(TIMEFRAME_SECONDS)}"
        ) from exc


def currencies_for_symbol(symbol: str) -> List[str]:
    """
    Calendar currencies that matter for a symbol.

    XAUUSD -> ['USD'], EURUSD -> ['EUR', 'USD']. A broker suffix after the six
    letter symbol (e.g. 'XAUUSD.m') is ignored.
    """
    match = re.match(r"^([A-Za-z]{3})([A-Za-z]{3})", str(symbol).strip())
    if not match:
        raise ValueError(
            f"Cannot derive calendar currencies from symbol '{symbol}'. Set "
            f"calendar_currencies in pipeline_config.yaml explicitly."
        )
    base, quote = match.group(1).upper(), match.group(2).upper()
    return [quote] if base in _METAL_BASES else [base, quote]


def _currency_sign(symbol: str, currency: str) -> int:
    """+1 if the currency is the symbol's base, -1 if it is the quote, else 0."""
    match = re.match(r"^([A-Za-z]{3})([A-Za-z]{3})", str(symbol).strip())
    if not match:
        return 0
    base, quote = match.group(1).upper(), match.group(2).upper()
    if currency == base:
        return 1
    if currency == quote:
        return -1
    return 0


def _to_epoch_seconds(values) -> np.ndarray:
    """datetime-like -> int64 epoch seconds (independent of pandas' datetime unit)."""
    arr = np.asarray(pd.DatetimeIndex(values).to_numpy())
    return arr.astype("datetime64[s]").astype(np.int64)


def load_calendar_csv(csv_path: str | Path) -> pd.DataFrame:
    """
    Load the calendar CSV written by economicCalendarDataExporter.mq5.

    Returns a dataframe sorted by ``time_server`` with a parsed datetime column
    and numeric columns coerced to float (empty cells -> NaN).
    """
    csv_path = Path(csv_path)
    logger.info(f"Loading economic calendar from {csv_path}")

    raw = None
    last_error: Optional[Exception] = None
    # The exporter writes UTF-8, but MT5 builds differ, so be tolerant.
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        for kwargs in (
            {"quoting": csv.QUOTE_NONE},
            {"quoting": csv.QUOTE_NONE, "on_bad_lines": "skip"},
            {"engine": "python", "on_bad_lines": "skip"},
        ):
            try:
                raw = pd.read_csv(csv_path, sep=",", encoding=encoding, dtype=str,
                                  keep_default_na=False, **kwargs)
            except (UnicodeError, UnicodeDecodeError) as exc:
                last_error = exc
                break  # wrong encoding: other parser tiers will not help
            except pd.errors.ParserError as exc:
                last_error = exc
                continue
            break
        if raw is not None:
            break

    if raw is None:
        raise ValueError(f"Could not parse calendar file {csv_path}: {last_error}")

    raw.columns = [str(c).replace('"', "").strip() for c in raw.columns]
    missing = [c for c in _REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(
            f"Calendar CSV {csv_path} is missing required column(s) {missing}. "
            f"Expected the output of mql5/economicCalendarDataExporter.mq5."
        )

    for col in ("currency", "country", "event_name"):
        if col in raw.columns:
            cleaned_text = raw[col].astype(str).str.replace('"', "", regex=False).str.strip()
            raw[col] = cleaned_text.str.upper() if col == "currency" else cleaned_text

    time_text = raw["time_server"].astype(str).str.replace('"', "", regex=False).str.strip()
    raw["time_server"] = pd.to_datetime(time_text, format=_TIME_FORMAT, errors="coerce")
    n_bad = int(raw["time_server"].isna().sum())
    if n_bad:
        logger.warning(f"Dropped {n_bad} calendar row(s) with an unparseable time_server")
    raw = raw[raw["time_server"].notna()].copy()

    for col in _NUMERIC_COLUMNS:
        if col in raw.columns:
            cleaned = raw[col].astype(str).str.replace('"', "", regex=False).str.strip()
            raw[col] = pd.to_numeric(cleaned.replace("", np.nan), errors="coerce")
        else:
            raw[col] = np.nan

    raw = raw.drop_duplicates().sort_values("time_server", kind="stable").reset_index(drop=True)
    logger.info(
        f"Loaded {len(raw)} calendar rows, {raw['time_server'].iloc[0]} .. "
        f"{raw['time_server'].iloc[-1]}" if len(raw) else "Calendar file contains no usable rows"
    )
    return raw


def _surprise_zscore(events: pd.DataFrame, min_history: int) -> np.ndarray:
    """
    |actual - forecast| divided by the expanding std of the PREVIOUS surprises of
    the same event id. NaN when there is not enough history or std is zero.
    """
    surprise = (events["actual"] - events["forecast"]).to_numpy(dtype=float)
    frame = pd.DataFrame({"event_id": events["event_id"].to_numpy(), "surprise": surprise})
    prior_std = (
        frame.groupby("event_id", sort=False)["surprise"]
        .transform(lambda s: s.shift(1).expanding(min_periods=min_history).std())
        .to_numpy(dtype=float)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        absz = np.abs(surprise) / prior_std
    absz[~np.isfinite(absz)] = np.nan
    return absz


def _tier_features(
    ev_times: np.ndarray,
    bar_open: np.ndarray,
    bar_close: np.ndarray,
    bar_seconds: int,
    max_minutes: float,
) -> Dict[str, np.ndarray]:
    """Schedule-based features for one importance tier (ev_times sorted, unique)."""
    n = len(bar_close)
    if len(ev_times) == 0:
        return {
            "to_next": np.full(n, max_minutes), "since_last": np.full(n, max_minutes),
            "in_bar": np.zeros(n), "next_bar": np.zeros(n),
        }

    # First event at/after the bar close = next scheduled event; the one before it
    # is the last event strictly before the close.
    idx_next = np.searchsorted(ev_times, bar_close, side="left")
    has_next = idx_next < len(ev_times)
    has_prev = idx_next > 0

    next_time = np.where(has_next, ev_times[np.minimum(idx_next, len(ev_times) - 1)], 0)
    prev_time = np.where(has_prev, ev_times[np.maximum(idx_next - 1, 0)], 0)

    to_next = np.where(has_next, (next_time - bar_close) / 60.0, max_minutes)
    since_last = np.where(has_prev, (bar_close - prev_time) / 60.0, max_minutes)

    return {
        "to_next": np.minimum(to_next, max_minutes),
        "since_last": np.minimum(since_last, max_minutes),
        # An event was released while this bar was forming: [open, close).
        "in_bar": (has_prev & (prev_time >= bar_open)).astype(float),
        # The bar we would enter next contains a scheduled event: [close, close + tf).
        "next_bar": (has_next & (next_time < bar_close + bar_seconds)).astype(float),
    }


def build_calendar_features(
    index: pd.DatetimeIndex,
    timeframe: str,
    events: pd.DataFrame,
    symbol: str,
    options: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Build the ``cal_*`` feature columns for every bar.

    Parameters
    ----------
    index : pd.DatetimeIndex
        Bar OPEN times (broker server time), as written by dataExporter.mq5.
    timeframe : str
        Bar timeframe label ('M1' .. 'W1'); the bar closes at ``open + timeframe``.
    events : pd.DataFrame
        Output of :func:`load_calendar_csv`.
    symbol : str
        Used to pick the relevant currencies and to orient the impact sign.
    options : dict, optional
        Overrides for DEFAULT_CALENDAR_OPTIONS.

    Returns
    -------
    pd.DataFrame
        float32 columns indexed like ``index``:

        cal_min_to_next_high / cal_min_since_last_high
            Minutes (capped at ``max_minutes``) to the next scheduled / since the
            last released event of importance >= ``importance_high``.
        cal_high_in_bar
            1 if such an event was released while the bar was forming.
        cal_high_next_bar
            1 if such an event is scheduled inside the bar we would enter next.
        cal_min_to_next_medplus / cal_min_since_last_medplus /
        cal_medplus_in_bar / cal_medplus_next_bar
            Same four, for importance >= ``importance_medplus``.
        cal_last_impact_sym
            +1 / -1 / 0: the MT5 impact flag (positive / negative for the event
            currency) of the most recent high-importance event with a published
            actual value, re-oriented to the SYMBOL (a positive USD impact is -1
            for XAUUSD or EURUSD), 0 after ``impact_max_age_min`` minutes.
        cal_last_surprise_absz
            |actual - forecast| in units of the expanding std of that event's own
            past surprises, for the most recent high-importance event; 0 after
            ``impact_max_age_min`` minutes, NaN if there is no usable history.

        Every column is NaN for bars outside the calendar coverage.
    """
    opts = dict(DEFAULT_CALENDAR_OPTIONS)
    if options:
        opts.update(options)

    bar_seconds = timeframe_seconds(timeframe)
    max_minutes = float(opts["max_minutes"])
    max_age_sec = float(opts["impact_max_age_min"]) * 60.0

    currencies = opts["currencies"] or currencies_for_symbol(symbol)
    currencies = [str(c).upper() for c in currencies]

    ev = events
    if opts["exclude_holidays"]:
        ev = ev[ev["event_type"] != _EVENT_TYPE_HOLIDAY]
    ev = ev[ev["currency"].isin(currencies)]
    ev = ev[ev["importance"].notna()]
    if len(ev) == 0:
        logger.warning(
            f"No calendar events left for currencies {currencies} -- every cal_* "
            f"column will be NaN. Check the Currencies input of the exporter."
        )

    bar_open = _to_epoch_seconds(index)
    bar_close = bar_open + bar_seconds
    n_bars = len(bar_open)

    # Coverage is judged on the filtered feed so a currency with no rows is visible.
    if len(ev):
        all_times = _to_epoch_seconds(ev["time_server"])
        cov_start, cov_end = all_times.min(), all_times.max()
        covered = (bar_close >= cov_start) & (bar_close <= cov_end)
    else:
        covered = np.zeros(n_bars, dtype=bool)

    out: Dict[str, np.ndarray] = {}

    for tier_name, min_importance in (
        ("high", opts["importance_high"]),
        ("medplus", opts["importance_medplus"]),
    ):
        tier = ev[ev["importance"] >= min_importance]
        times = np.unique(_to_epoch_seconds(tier["time_server"])) if len(tier) else np.array([], dtype=np.int64)
        feats = _tier_features(times, bar_open, bar_close, bar_seconds, max_minutes)
        out[f"cal_min_to_next_{tier_name}"] = feats["to_next"]
        out[f"cal_min_since_last_{tier_name}"] = feats["since_last"]
        out[f"cal_{tier_name}_in_bar"] = feats["in_bar"]
        out[f"cal_{tier_name}_next_bar"] = feats["next_bar"]

    # --- last released high-importance event: impact direction + surprise size ---
    impact_val = np.zeros(n_bars)
    surprise_val = np.zeros(n_bars)

    released = ev[
        (ev["importance"] >= opts["importance_high"])
        & ev["actual"].notna()
        & ev["impact_type"].isin([_IMPACT_POSITIVE, _IMPACT_NEGATIVE])
    ].copy()

    if len(released):
        released["_t"] = _to_epoch_seconds(released["time_server"])
        flag = np.where(released["impact_type"].to_numpy() == _IMPACT_POSITIVE, 1.0, -1.0)
        ccy_sign = released["currency"].map(lambda c: _currency_sign(symbol, c)).to_numpy(dtype=float)
        released["_impact"] = flag * ccy_sign

        has_fc = released["forecast"].notna().to_numpy()
        absz = np.full(len(released), np.nan)
        if has_fc.any():
            absz_all = _surprise_zscore(
                released.sort_values(["event_id", "_t"], kind="stable"),
                int(opts["surprise_min_history"]),
            )
            # _surprise_zscore returns values in the sorted order; map them back.
            order = released.sort_values(["event_id", "_t"], kind="stable").index
            absz = pd.Series(absz_all, index=order).reindex(released.index).to_numpy()
        released["_absz"] = absz

        # Several events usually share one release timestamp (e.g. NFP + wages):
        # direction = sign of the summed impact, surprise = the largest one.
        grouped = released.groupby("_t", sort=True).agg(
            impact=("_impact", "sum"), absz=("_absz", "max")
        )
        g_times = grouped.index.to_numpy(dtype=np.int64)
        g_impact = np.sign(grouped["impact"].to_numpy(dtype=float))
        g_absz = grouped["absz"].to_numpy(dtype=float)

        idx_last = np.searchsorted(g_times, bar_close, side="left") - 1
        has_last = idx_last >= 0
        safe = np.maximum(idx_last, 0)
        age = np.where(has_last, bar_close - g_times[safe], np.inf)
        fresh = has_last & (age <= max_age_sec)

        impact_val = np.where(fresh, g_impact[safe], 0.0)
        surprise_val = np.where(fresh, g_absz[safe], 0.0)

    out["cal_last_impact_sym"] = impact_val
    out["cal_last_surprise_absz"] = surprise_val

    features = {}
    for name, values in out.items():
        arr = np.asarray(values, dtype=np.float32).copy()
        arr[~covered] = np.nan
        features[name] = arr

    frac = float(covered.mean()) if n_bars else 0.0
    logger.info(
        f"Calendar features built for currencies {currencies}: {frac:.1%} of bars are inside "
        f"the calendar coverage ({len(features)} columns)"
    )
    if frac < 0.999 and n_bars:
        logger.warning(
            f"Only {frac:.1%} of the bars fall inside the calendar file's time range; the other "
            f"bars get NaN in every cal_* column and can never trigger a calendar condition. "
            f"Re-run the calendar exporter with an earlier 'Start date' to cover the whole history."
        )

    return pd.DataFrame(features, index=index)


def attach_calendar_features(
    df: pd.DataFrame,
    calendar_csv: str | Path,
    symbol: str,
    timeframe: str,
    options: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Load the calendar CSV, build the cal_* columns and add them to ``df`` in place.

    Columns are inserted one by one (no full-frame copy) because the price table
    can be several GB on M1.
    """
    events = load_calendar_csv(calendar_csv)
    if len(events) == 0:
        raise ValueError(f"Calendar file {calendar_csv} has no usable rows")

    features = build_calendar_features(df.index, timeframe, events, symbol, options)

    existing = [c for c in features.columns if c in df.columns]
    if existing:
        raise ValueError(
            f"Price CSV already contains calendar column(s) {existing}; refusing to overwrite."
        )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        for col in features.columns:
            df[col] = features[col].to_numpy(dtype=np.float32)

    logger.info(f"Attached {len(features.columns)} calendar feature columns to the price table")
    return df
