"""
Phase 1: Ingestion & Storage

Load MQL5-exported CSV, validate, convert to float32, parse datetime,
write to Parquet for efficient access by later phases.

Two MQL5 exporters feed this phase:

* ``mql5/dataExporter.mq5`` (Strategy Tester EA, v1.01+) -- OHLCV, the standard
  indicator columns and the custom-indicator columns ``volregime_*``
  (VolRegime_ATR) and ``ps_*`` (PriceStructure). From v1.02 the same EA also
  appends ``news_*`` columns computed inside MQL5 from the calendar CSV it
  exports on a live chart (see ``sanitize_news_columns`` below).
* The calendar CSV itself (written by ``dataExporter.mq5`` v1.02 on a live chart,
  or by the older stand-alone ``economicCalendarDataExporter.mq5``) -- optional;
  when supplied it is turned into ``cal_*`` feature columns (see
  ``edge_research.ingestion.economic_calendar``).
"""

import csv
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from edge_research.ingestion.economic_calendar import attach_calendar_features
from edge_research.utils.memory import check_memory

try:
    import pyarrow.parquet as pq  # noqa: F401
except Exception:  # pragma: no cover - optional dependency fallback
    pq = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Memory model of the loader (why it is written this way)
# ---------------------------------------------------------------------------
# The old loader did `pd.read_csv(whole_file)` (every numeric column parsed to
# float64) and then converted the columns to float32 ONE AT A TIME with
# `df[col] = df[col].astype(np.float32)`.  On a multi-million-row M1 file that
# holds the complete float64 copy of the table in RAM (pandas keeps the
# original consolidated block alive while any column still views into it) PLUS
# the growing float32 copy, so peak RAM was ~2.5x the final table size; a
# further full-size boolean frame was created by `df.isna()` and a further
# full copy by `to_parquet`.  Here the file is parsed in row chunks and every
# chunk is converted to float32 immediately, so peak RAM ~= the final float32
# table + one chunk.

# dataExporter.mq5 writes TimeToString(...) with the dots removed, i.e. "20240105 13:30"
# (the colon is kept), so that format is tried first. The others are kept for older
# exports / hand-made files.
_TIME_FORMATS = ("%Y%m%d %H:%M", "%Y%m%d %H%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M")
_CHUNK_ROWS = 250_000
_PARQUET_ROW_GROUP = 500_000
_TIME_MIN_PARSE_FRACTION = 0.99


def _file_contains_quote(csv_path: str | Path, block_size: int = 64 * 1024 * 1024) -> bool:
    """
    Cheap byte-level scan (GB/s) for any '"' in the file.

    This data is purely numeric OHLC + indicators, so a '"' is never
    legitimate.  Knowing this up front lets the loader skip the default C
    parser attempt that, on a file with an unterminated quote, spends tens of
    minutes and ~16 GB swallowing the rest of the file into ONE field before
    failing with 'Buffer overflow caught'.
    """
    with open(csv_path, "rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                return False
            if b'"' in block:
                return True


def _clean_name(name) -> str:
    return str(name).replace('"', "").strip()


def _column_to_float32(series: pd.Series) -> np.ndarray:
    """Chunk column -> float32; text columns (stray quote characters etc.)
    are cleaned of '"' and coerced, so a corrupted cell becomes NaN (or its
    real number, when the quote was the only problem) instead of turning the
    whole column into millions of Python strings."""
    if series.dtype.kind in "fiub":
        return np.asarray(series, dtype=np.float32)
    cleaned = series.astype(str).str.replace('"', "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").to_numpy(dtype=np.float32, na_value=np.nan)


def _parse_time_chunk(raw: pd.Series, fmt_hint):
    """Returns (parsed datetime Series with NaT for unparseable rows, format used)."""
    text = raw.astype(str).str.replace('"', "", regex=False).str.strip()
    candidates = ([fmt_hint] if fmt_hint else []) + [f for f in _TIME_FORMATS if f != fmt_hint]
    for fmt in candidates:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if len(parsed) == 0 or parsed.notna().mean() >= _TIME_MIN_PARSE_FRACTION:
            return parsed, fmt
    logger.warning("Could not parse time with standard formats, using pandas auto-detect")
    parsed = pd.to_datetime(text, errors="coerce")
    if len(parsed) and parsed.notna().mean() < _TIME_MIN_PARSE_FRACTION:
        raise ValueError(
            "Could not parse the 'time' column: fewer than 99% of the values match any of "
            f"{list(_TIME_FORMATS)} or pandas auto-detection. Example value: {text.iloc[0]!r}"
        )
    return parsed, None


def _read_csv_as_float32_frame(csv_path, encoding: str, read_kwargs: dict) -> pd.DataFrame:
    """
    One parse attempt (one encoding + one parser configuration), chunked.
    Raises UnicodeError / pd.errors.ParserError exactly like pd.read_csv would,
    so the caller's fallback tiers keep working.
    """
    reader = pd.read_csv(
        csv_path, sep=",", decimal=".", encoding=encoding,
        chunksize=_CHUNK_ROWS, **read_kwargs,
    )
    chunks = [reader] if isinstance(reader, pd.DataFrame) else reader

    names = None
    col_parts: dict = {}
    time_parts = []
    fmt = None
    n_bad_time = 0

    try:
        for chunk in chunks:
            check_memory("CSV load")
            chunk.columns = [_clean_name(c) for c in chunk.columns]
            if "time" not in chunk.columns:
                raise ValueError("CSV must contain 'time' column")
            if names is None:
                names = [c for c in chunk.columns if c != "time"]
                col_parts = {c: [] for c in names}

            parsed, fmt = _parse_time_chunk(chunk["time"], fmt)
            keep = parsed.notna().to_numpy()
            n_bad_time += int((~keep).sum())
            all_kept = bool(keep.all())

            time_parts.append(pd.DatetimeIndex(parsed if all_kept else parsed[keep]))
            for c in names:
                arr = _column_to_float32(chunk[c])
                col_parts[c].append(arr if all_kept else arr[keep])
            del chunk
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()

    if not time_parts:
        raise ValueError(f"{csv_path} contains no data rows")

    if n_bad_time:
        logger.warning(
            f"Dropped {n_bad_time} row(s) whose 'time' value could not be parsed "
            f"(almost always the corrupted row(s) that carried the stray quote character)."
        )

    index = time_parts[0] if len(time_parts) == 1 else time_parts[0].append(time_parts[1:])
    index.name = "time"
    del time_parts

    data = {}
    for c in names:
        parts = col_parts.pop(c)
        data[c] = parts[0] if len(parts) == 1 else np.concatenate(parts)
        del parts
    # copy=False: keep one float32 array per column instead of consolidating
    # (= copying) everything into a single second block.
    return pd.DataFrame(data, index=index, copy=False)


# ---------------------------------------------------------------------------
# Export schema (mql5/dataExporter.mq5 v1.01)
# ---------------------------------------------------------------------------
# Column names written by the custom indicators. A value of NaN means the
# indicator had no value for that bar (EMPTY_VALUE / failed iCustom handle).
CORE_COLUMNS = ("open", "high", "low", "close")

VOLREGIME_COLUMNS = (
    "volregime_atr_pctl",    # ATR percentile rank, 0..100
    "volregime_atr_ratio",   # ATR / SMA(ATR), ~1.0
    "volregime_regime",      # 0 = low vol, 1 = mid, 2 = high vol
)

PRICE_STRUCTURE_COLUMNS = (
    "ps_dist_pdh_atr",        # (previous day high - price) / ATR
    "ps_dist_pdl_atr",        # (previous day low - price) / ATR
    "ps_dist_sess_h_atr",     # (previous session high - price) / ATR
    "ps_dist_sess_l_atr",     # (previous session low - price) / ATR
    "ps_dist_round_up_atr",   # (nearest round number above - price) / ATR
    "ps_dist_round_dn_atr",   # (nearest round number below - price) / ATR (<= 0)
    "ps_gap_atr",             # daily gap / ATR, + = gap up
    "ps_gap_fill_pct",        # % of the daily gap already filled, 0..100
)

# dataExporter.mq5 v1.02 news columns (computed in MQL5 at bar close = bar open + period).
NEWS_COLUMNS = (
    "news_min_to_next",        # minutes from bar close to the next event
    "news_next_importance",    # MT5 importance (1..3) of that event
    "news_min_since_last",     # minutes since the last event
    "news_last_importance",
    "news_last_surprise",      # actual - forecast of the last event (raw units, mixed across events)
    "news_in_window",          # 1 if an event is within +/- InpNewsWindowMin minutes
    "news_count_next_24h",     # number of events in the next 24 hours
)

_CUSTOM_GROUPS = (
    ("VolRegime_ATR", VOLREGIME_COLUMNS),
    ("PriceStructure", PRICE_STRUCTURE_COLUMNS),
)


def validate_export_schema(df: pd.DataFrame) -> dict:
    """
    Sanity-check a loaded dataExporter.mq5 table and log what is wrong with it.

    Never raises: old exports without the custom-indicator groups still load, and a
    table without OHLC columns is only warned about (the loader itself is also used
    on partial files; the later pipeline phases fail with a clear KeyError if they
    really need the missing column).

    Returns
    -------
    dict
        {'custom_groups_present': [...], 'custom_groups_empty': [...],
         'custom_groups_missing': [...]}
    """
    missing_core = [c for c in CORE_COLUMNS if c not in df.columns]
    if missing_core:
        logger.warning(
            f"CSV is missing OHLC column(s) {missing_core}; the pipeline phases need "
            f"open/high/low/close. Columns found: {list(df.columns)[:12]}..."
        )

    report = {"custom_groups_present": [], "custom_groups_empty": [], "custom_groups_missing": []}

    for group_name, columns in _CUSTOM_GROUPS:
        present = [c for c in columns if c in df.columns]
        if not present:
            report["custom_groups_missing"].append(group_name)
            logger.info(
                f"No {group_name} columns in this CSV (export made before dataExporter.mq5 v1.01?). "
                f"Conditions on {columns[0].split('_')[0]}_* will not be generated."
            )
            continue

        absent = [c for c in columns if c not in df.columns]
        if absent:
            logger.warning(f"{group_name}: columns missing from the CSV: {absent}")

        all_nan = [c for c in present if bool(np.isnan(df[c].to_numpy()).all())]
        if len(all_nan) == len(present):
            report["custom_groups_empty"].append(group_name)
            logger.warning(
                f"{group_name}: every value is NaN. The exporter writes NaN when iCustom() fails, "
                f"so the indicator most likely was not found by the Strategy Tester. Check that "
                f"the compiled .ex5 exists and that the #property tester_indicator path in "
                f"dataExporter.mq5 matches its location, then re-export."
            )
            continue

        report["custom_groups_present"].append(group_name)
        for c in all_nan:
            logger.warning(f"{group_name}: column '{c}' is entirely NaN")

    # News columns (dataExporter.mq5 v1.02).
    news_present = [c for c in NEWS_COLUMNS if c in df.columns]
    if not news_present:
        report["custom_groups_missing"].append("news")
        logger.info("No news_* columns in this CSV (export made before dataExporter.mq5 v1.02, or "
                    "InpAddNewsColumns = false). Use --calendar-csv to add calendar features instead.")
    elif all(bool(np.isnan(df[c].to_numpy()).all()) for c in news_present):
        report["custom_groups_empty"].append("news")
        logger.warning(
            "news_*: every value is NaN. The EA writes NaN when it could not load the calendar CSV in "
            "the tester. Run dataExporter.mq5 once on a LIVE chart to create economic_calendar.csv "
            "(Common\\Files), then re-run the tester export."
        )
    else:
        report["custom_groups_present"].append("news")

    # Value-range checks (cheap; only on columns that exist).
    if "volregime_regime" in df.columns:
        reg = df["volregime_regime"].to_numpy()
        bad = int(np.sum(~np.isnan(reg) & ~np.isin(reg, (0.0, 1.0, 2.0))))
        if bad:
            logger.warning(f"volregime_regime has {bad} value(s) outside {{0, 1, 2}}")
    if "volregime_atr_pctl" in df.columns:
        pct = df["volregime_atr_pctl"].to_numpy()
        bad = int(np.sum(~np.isnan(pct) & ((pct < 0.0) | (pct > 100.0))))
        if bad:
            logger.warning(f"volregime_atr_pctl has {bad} value(s) outside [0, 100]")
    if "ps_gap_fill_pct" in df.columns:
        fill = df["ps_gap_fill_pct"].to_numpy()
        bad = int(np.sum(~np.isnan(fill) & ((fill < 0.0) | (fill > 100.0))))
        if bad:
            logger.warning(f"ps_gap_fill_pct has {bad} value(s) outside [0, 100]")

    return report


def sanitize_news_columns(df: pd.DataFrame) -> dict:
    """
    Repair two problems in the ``news_*`` columns written by dataExporter.mq5 v1.02
    (in place). Does nothing if the columns are absent.

    1. LOOK-AHEAD at the bar boundary. MQL5 treats an event stamped exactly at the bar
       close as ALREADY RELEASED (``time <= ref``), so ``news_last_surprise`` carries the
       actual-vs-forecast result of a release at 13:30:00 on the row whose decision is taken
       at 13:30:00 -- before the market has reacted. Scheduled events (NFP, CPI, FOMC) very
       often sit exactly on a bar boundary, so this would hand the miner the outcome on the
       most volatile bars. Rows with ``news_min_since_last == 0`` are therefore rewritten:
       the event becomes the NEXT event (to_next = 0, next_importance = its importance,
       count_next_24h + 1) and the last-event fields (since_last, last_importance,
       last_surprise) become NaN. The in-window flag stays 1.
    2. COVERAGE. The exporter has no notion of the calendar file's time range: bars before
       the first event look like "far from news" (large to_next, count 0) instead of unknown.
       Rows with no previous event (before the file starts) or no next event (after it ends)
       get NaN in every news_* column, so they can never satisfy a news condition.

    Returns
    -------
    dict
        {'boundary_rows': int, 'uncovered_rows': int}
    """
    stats = {"boundary_rows": 0, "uncovered_rows": 0}
    if not all(c in df.columns for c in NEWS_COLUMNS):
        return stats

    cols = {c: df[c].to_numpy(dtype=np.float32, copy=True) for c in NEWS_COLUMNS}

    # (2) coverage first, so the boundary fix below only touches covered rows.
    uncovered = np.isnan(cols["news_min_since_last"]) | np.isnan(cols["news_min_to_next"])
    # A fully NaN block (calendar not loaded) is handled by validate_export_schema.
    if uncovered.any() and not uncovered.all():
        for c in NEWS_COLUMNS:
            cols[c][uncovered] = np.nan
        stats["uncovered_rows"] = int(uncovered.sum())

    # (1) boundary look-ahead
    boundary = cols["news_min_since_last"] == 0.0
    if boundary.any():
        event_importance = cols["news_last_importance"][boundary].copy()
        cols["news_min_to_next"][boundary] = 0.0
        cols["news_next_importance"][boundary] = event_importance
        cols["news_count_next_24h"][boundary] += 1.0
        cols["news_min_since_last"][boundary] = np.nan
        cols["news_last_importance"][boundary] = np.nan
        cols["news_last_surprise"][boundary] = np.nan
        stats["boundary_rows"] = int(boundary.sum())

    if stats["boundary_rows"] or stats["uncovered_rows"]:
        for c in NEWS_COLUMNS:
            df[c] = cols[c]
        logger.info(
            f"news_* columns sanitized: {stats['boundary_rows']} row(s) with an event exactly at the "
            f"bar close moved from 'last' to 'next' (look-ahead fix), {stats['uncovered_rows']} row(s) "
            f"outside the calendar's time range set to NaN"
        )
    return stats


def load_csv_and_validate(
    csv_path: str | Path,
) -> pd.DataFrame:
    """
    Load MQL5-exported CSV file and perform basic validation.

    Parameters
    ----------
    csv_path : str | Path
        Path to the MQL5-exported CSV file.

    Returns
    -------
    pd.DataFrame
        Validated dataframe with datetime index and all numeric columns as float32.

    Raises
    ------
    ValueError
        If the file cannot be parsed under any encoding / parser tier.

    Notes
    -----
    - Parses 'time' column as datetime (dataExporter.mq5 format 'YYYYMMDD HH:MM'; the older
      'YYYYMMDD HHMM', 'YYYY.MM.DD HH:MM' and 'YYYY-MM-DD HH:MM' are also accepted)
    - Streams the file in row chunks, converting to float32 as it goes
    - Duplicate timestamps are dropped (last row kept); a non-monotonic index is sorted
    - Warns if NaN values are present; does NOT crash on NaN
    """
    logger.info(f"Loading CSV from {csv_path}")

    has_quote = _file_contains_quote(csv_path)
    if has_quote:
        logger.warning(
            f"'{csv_path}' contains at least one '\"' character. The data is purely numeric, "
            f"so it is corrupted export data -- skipping the default C parser (which would "
            f"spend a long time and a lot of RAM on an unterminated quote) and parsing with "
            f"quoting disabled; stray quote characters are stripped from each cell."
        )

    # Parser tiers, cheapest first.  MT5's own export is often UTF-16 or
    # cp1252, so every tier is tried under each encoding.
    default_tier = ("default", {})
    quote_none_tier = ("quote_none", {"quoting": csv.QUOTE_NONE})
    skip_tier = ("quote_none_skip_bad_lines", {"quoting": csv.QUOTE_NONE, "on_bad_lines": "skip"})
    python_tier = ("python", {"engine": "python"})
    tiers = (
        [quote_none_tier, skip_tier, python_tier]
        if has_quote
        else [default_tier, quote_none_tier, skip_tier, python_tier]
    )

    df = None
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"):
        for label, kwargs in tiers:
            try:
                df = _read_csv_as_float32_frame(csv_path, encoding, kwargs)
            except (UnicodeDecodeError, UnicodeError) as e:
                last_error = e
                break  # wrong encoding: no point trying other parser tiers
            except pd.errors.ParserError as e:
                last_error = e
                logger.warning(
                    f"Parser tier '{label}' failed on '{csv_path}' with encoding "
                    f"'{encoding}': {e}. Trying the next, more tolerant tier."
                )
                continue

            if encoding != "utf-8":
                logger.warning(
                    f"CSV was not valid UTF-8; loaded successfully as '{encoding}' instead. "
                    f"If any text columns look garbled, re-export the CSV as UTF-8."
                )
            if label == "quote_none":
                logger.warning(
                    f"Loaded '{csv_path}' with quote-character handling disabled. Any '\"' "
                    f"inside a numeric cell was stripped; cells that still are not numbers "
                    f"become NaN (see the 'Found NaN values' line below)."
                )
            elif label == "quote_none_skip_bad_lines":
                logger.warning(
                    f"Loaded '{csv_path}' with quoting disabled AND malformed lines skipped "
                    f"(rows with the wrong number of fields were dropped) -- check the "
                    f"export for truncated/corrupted rows."
                )
            elif label == "python":
                logger.warning(
                    f"Loaded '{csv_path}' with the slow Python parser engine after the C "
                    f"tiers failed -- the export likely has structural corruption."
                )
            break
        if df is not None:
            break

    if df is None:
        raise ValueError(
            f"Could not parse {csv_path} with any of utf-8/utf-8-sig/utf-16/cp1252/latin-1, "
            f"using the default C parser, quote-disabled C parser, or Python parser engine. "
            f"Last error: {last_error}. This usually means the CSV has malformed content (an "
            f"unescaped quote character, a row with the wrong number of fields, or similar) "
            f"rather than a wrong encoding -- open the file in a text editor and check for "
            f"stray \" characters or truncated rows, particularly near where the export might "
            f"have been interrupted."
        )

    # Ensure the index is monotonic increasing (stable so equal stamps keep file order).
    if not df.index.is_monotonic_increasing:
        df = df.sort_index(kind="stable")

    # Duplicate timestamps: keep the LAST row of each.  (The previous behaviour --
    # replacing the whole index with date_range(freq="D") -- destroyed every
    # timestamp in the file, and for millions of rows runs off the end of the
    # supported date range, which breaks the calendar walk-forward windows.)
    dup_mask = df.index.duplicated(keep="last")
    if dup_mask.any():
        logger.warning(
            f"Found {int(dup_mask.sum())} duplicate timestamp(s); keeping the last row "
            f"for each timestamp and dropping the others"
        )
        df = df[~dup_mask]

    logger.info(f"Loaded {len(df)} rows, date range: {df.index[0]} to {df.index[-1]}")

    # Check for NaN column by column (df.isna() would allocate a full-size bool frame).
    nan_counts = pd.Series(
        {c: int(np.isnan(df[c].to_numpy()).sum()) for c in df.columns}, dtype="int64"
    )
    if nan_counts.any():
        logger.warning(f"Found NaN values:\n{nan_counts[nan_counts > 0]}")

    logger.info(f"Converted {len(df.columns)} numeric columns to float32")

    validate_export_schema(df)
    sanitize_news_columns(df)

    return df


def save_to_parquet(
    df: pd.DataFrame,
    output_dir: str | Path,
    symbol: str,
    timeframe: str,
    compression: str = "zstd",
) -> Path:
    """
    Save dataframe to Parquet file.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with datetime index and float32 columns.
    output_dir : str | Path
        Directory to save Parquet file.
    symbol : str
        Symbol (e.g., 'EURUSD').
    timeframe : str
        Timeframe (e.g., 'H1', 'D1').
    compression : str
        Compression codec ('zstd', 'snappy', or None).

    Returns
    -------
    Path
        Path to written Parquet file.

    Notes
    -----
    - Filename format: {SYMBOL}_{TIMEFRAME}.parquet
    - Index (datetime) is preserved in Parquet
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{symbol}_{timeframe}.parquet"
    filepath = output_dir / filename
    
    logger.info(f"Writing Parquet to {filepath} (compression={compression})")
    
    # Convert index to datetime64[ns] if not already
    if df.index.dtype.kind != 'M':
        df.index = pd.to_datetime(df.index)

    if pq is not None and len(df) > _PARQUET_ROW_GROUP:
        # Write row group by row group: df.to_parquet() first converts the WHOLE
        # frame to an Arrow table (a second full copy of the data in RAM).
        import pyarrow as pa

        writer = None
        try:
            for start in range(0, len(df), _PARQUET_ROW_GROUP):
                table = pa.Table.from_pandas(
                    df.iloc[start:start + _PARQUET_ROW_GROUP], preserve_index=True
                )
                if writer is None:
                    writer = pq.ParquetWriter(
                        filepath, table.schema, compression=compression or "none"
                    )
                writer.write_table(table)
                del table
        finally:
            if writer is not None:
                writer.close()
    elif pq is not None:
        df.to_parquet(filepath, compression=compression)
    else:
        filepath = filepath.with_suffix('.feather')
        df.to_feather(filepath)
    
    logger.info(f"Successfully wrote {len(df)} rows to {filepath}")
    
    return filepath


def load_from_parquet(parquet_path: str | Path) -> pd.DataFrame:
    """
    Load previously saved Parquet file.

    Parameters
    ----------
    parquet_path : str | Path
        Path to Parquet file.

    Returns
    -------
    pd.DataFrame
        DataFrame with datetime index and numeric columns as float32.

    Notes
    -----
    This is the primary accessor for all downstream phases after Phase 1 completes.
    """
    logger.info(f"Loading stored data from {parquet_path}")
    if parquet_path.suffix.lower() == ".feather":
        df = pd.read_feather(parquet_path)
    else:
        df = pd.read_parquet(parquet_path)
    
    # Ensure float32 dtype
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].dtype != np.float32:
            df[col] = df[col].astype(np.float32)
    
    logger.info(f"Loaded {len(df)} rows from {parquet_path}")
    return df


def ingest_pipeline(
    csv_path: str | Path,
    output_dir: str | Path,
    symbol: str,
    timeframe: str,
    compression: str = "zstd",
    calendar_csv: Optional[str | Path] = None,
    calendar_options: Optional[dict] = None,
) -> Tuple[pd.DataFrame, Path]:
    """
    Full Phase 1 ingestion pipeline: CSV -> validate -> (+ calendar) -> Parquet.

    Parameters
    ----------
    csv_path : str | Path
        Input CSV file path.
    output_dir : str | Path
        Output directory for Parquet.
    symbol : str
        Symbol identifier.
    timeframe : str
        Timeframe identifier.
    compression : str
        Parquet compression codec.
    calendar_csv : str | Path, optional
        CSV written by economicCalendarDataExporter.mq5. When given, the cal_*
        feature columns are added to the table (and therefore to the Parquet file).
        When omitted the pipeline behaves exactly as before.
    calendar_options : dict, optional
        Overrides for the calendar feature builder; see
        ``edge_research.ingestion.economic_calendar.DEFAULT_CALENDAR_OPTIONS``
        (pipeline_config.yaml keys ``calendar_*``).

    Returns
    -------
    Tuple[pd.DataFrame, Path]
        Loaded dataframe and path to saved Parquet file.
    """
    df = load_csv_and_validate(csv_path)
    if calendar_csv is not None:
        df = attach_calendar_features(df, calendar_csv, symbol, timeframe, calendar_options)
    filepath = save_to_parquet(df, output_dir, symbol, timeframe, compression)
    return df, filepath
