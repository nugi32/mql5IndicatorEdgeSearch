"""
Phase 1: Ingestion & Storage

Load MQL5-exported CSV, validate, convert to float32, parse datetime,
write to Parquet for efficient access by later phases.
"""

import csv
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

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

_TIME_FORMATS = ("%Y%m%d %H%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M")
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
    - Parses 'time' column as datetime (expected format: YYYY.MM.DD HH:MI)
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
) -> Tuple[pd.DataFrame, Path]:
    """
    Full Phase 1 ingestion pipeline: CSV -> validate -> Parquet.

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

    Returns
    -------
    Tuple[pd.DataFrame, Path]
        Loaded dataframe and path to saved Parquet file.
    """
    df = load_csv_and_validate(csv_path)
    filepath = save_to_parquet(df, output_dir, symbol, timeframe, compression)
    return df, filepath
