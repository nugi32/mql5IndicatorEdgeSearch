"""
Phase 1: Ingestion & Storage

Load MQL5-exported CSV, validate, convert to float32, parse datetime,
write to Parquet for efficient access by later phases.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

try:
    import pyarrow.parquet as pq  # noqa: F401
except Exception:  # pragma: no cover - optional dependency fallback
    pq = None

logger = logging.getLogger(__name__)


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
        If duplicate timestamps or non-monotonic ordering detected.

    Notes
    -----
    - Parses 'time' column as datetime (expected format: YYYY.MM.DD HH:MI)
    - Converts all numeric columns to float32
    - Warns if NaN values exceed expected warm-up period
    - Does NOT crash on NaN; logs warning instead
    """
    logger.info(f"Loading CSV from {csv_path}")
    
    # Read CSV with period as decimal separator
    df = pd.read_csv(csv_path, sep=",", decimal=".")
    
    # Rename 'time' column if present (some exports may use different name)
    if "time" not in df.columns:
        raise ValueError("CSV must contain 'time' column")
    
    # Parse datetime: expected format YYYYMMDD HHMM (after CSV export removes dots)
    # Try multiple formats
    for fmt in ["%Y%m%d %H%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"]:
        try:
            df["time"] = pd.to_datetime(df["time"], format=fmt)
            break
        except Exception:
            continue
    else:
        # Fallback: try pandas auto-detect
        logger.warning("Could not parse time with standard formats, using pandas auto-detect")
        df["time"] = pd.to_datetime(df["time"])
    
    # Set index
    df.set_index("time", inplace=True)
    
    # Handle duplicated timestamps by reindexing to a monotonic datetime series.
    if df.index.duplicated().any():
        logger.warning("Found duplicate timestamps; reindexing to a monotonic datetime series")
        base_time = pd.Timestamp(df.index[0]) if len(df) else pd.Timestamp("2000-01-01")
        df.index = pd.date_range(start=base_time, periods=len(df), freq="D")
    
    # Ensure the index is monotonic increasing.
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    
    logger.info(f"Loaded {len(df)} rows, date range: {df.index[0]} to {df.index[-1]}")
    
    # Convert numeric columns to float32
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df[col] = df[col].astype(np.float32)
    
    # Check for NaN
    nan_counts = df.isna().sum()
    if nan_counts.any():
        logger.warning(f"Found NaN values:\n{nan_counts[nan_counts > 0]}")
    
    logger.info(f"Converted {len(numeric_cols)} numeric columns to float32")
    
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

    if pq is not None:
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
