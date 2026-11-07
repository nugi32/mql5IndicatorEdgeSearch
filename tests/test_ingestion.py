"""Tests for Phase 1: Ingestion."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from edge_research.ingestion.loader import (
    load_csv_and_validate,
    load_from_parquet,
    save_to_parquet,
)


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=100, freq='h'),
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 101,
        'low': np.random.randn(100).cumsum() + 99,
        'close': np.random.randn(100).cumsum() + 100,
        'tick_volume': np.random.randint(100, 1000, 100),
        'rsi_14': np.random.uniform(0, 100, 100),
        'ma_20_ema': np.random.randn(100).cumsum() + 100,
    })
    
    csv_path = tmp_path / "test.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def test_load_csv_validate(sample_csv):
    """Test CSV loading and validation."""
    df = load_csv_and_validate(sample_csv)
    
    assert len(df) == 100
    assert df.index.name == 'time'
    assert df['open'].dtype == np.float32
    assert not df.index.duplicated().any()
    assert df.index.is_monotonic_increasing


def test_load_csv_utf16_encoding(tmp_path):
    """
    MT5's own CSV export commonly writes UTF-16, not UTF-8. Loading must
    not crash with UnicodeDecodeError on such a file.
    """
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=50, freq='h'),
        'open': np.random.randn(50).cumsum() + 100,
        'high': np.random.randn(50).cumsum() + 101,
        'low': np.random.randn(50).cumsum() + 99,
        'close': np.random.randn(50).cumsum() + 100,
    })
    csv_path = tmp_path / "utf16.csv"
    df.to_csv(csv_path, index=False, encoding="utf-16")

    loaded = load_csv_and_validate(csv_path)
    assert len(loaded) == 50


def test_load_csv_cp1252_encoding(tmp_path):
    """MT5 ANSI-codepage exports (Windows-1252) must also load without crashing."""
    df = pd.DataFrame({
        'time': pd.date_range('2023-01-01', periods=50, freq='h'),
        'open': np.random.randn(50).cumsum() + 100,
        'high': np.random.randn(50).cumsum() + 101,
        'low': np.random.randn(50).cumsum() + 99,
        'close': np.random.randn(50).cumsum() + 100,
    })
    csv_path = tmp_path / "cp1252.csv"
    df.to_csv(csv_path, index=False, encoding="cp1252")

    loaded = load_csv_and_validate(csv_path)
    assert len(loaded) == 50


def test_save_load_parquet(sample_csv, tmp_path):
    """Test Parquet round-trip."""
    df_orig = load_csv_and_validate(sample_csv)
    
    parquet_path = save_to_parquet(df_orig, tmp_path, 'EURUSD', 'H1')
    
    df_loaded = load_from_parquet(parquet_path)
    
    pd.testing.assert_frame_equal(df_orig, df_loaded)


def test_float32_conversion(sample_csv):
    """Ensure all numeric columns are float32."""
    df = load_csv_and_validate(sample_csv)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        assert df[col].dtype == np.float32, f"Column {col} is not float32"


def test_duplicate_timestamps_are_dropped_not_rewritten(tmp_path):
    """Duplicate timestamps must not prevent ingestion, and must NOT rewrite
    the timestamps of the whole file (the old date_range(freq='D') hack)."""
    csv_path = tmp_path / "duplicate_time.csv"
    pd.DataFrame(
        {
            "time": ["20091231 00:00", "20091231 00:00", "20091231 00:01"],
            "close": [1.0, 2.0, 3.0],
        }
    ).to_csv(csv_path, index=False)

    df = load_csv_and_validate(csv_path)

    assert len(df) == 2  # one duplicate dropped, last row kept
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()
    assert df.index[0] == pd.Timestamp("2009-12-31 00:00")
    assert df.index[1] == pd.Timestamp("2009-12-31 00:01")
    assert df["close"].iloc[0] == 2.0


def test_stray_quote_in_numeric_cell_is_recovered_not_object_column(tmp_path):
    """A stray '"' must neither crash the load nor turn the column into
    millions of Python strings (object dtype)."""
    csv_path = tmp_path / "stray_quote.csv"
    lines = ["time,open,close"]
    for i in range(50):
        lines.append(f"2023.01.01 {i // 60:02d}:{i % 60:02d},{100 + i}.5,{101 + i}.5")
    lines[10] = '2023.01.01 00:09,109.5,"110.5'      # unterminated quote at field start
    lines[20] = '"2023.01.01 00:19,119.5,120.5'      # quote inside the time cell
    csv_path.write_text("\n".join(lines) + "\n")

    df = load_csv_and_validate(csv_path)

    assert len(df) == 50
    assert df["close"].dtype == np.float32
    assert df["open"].dtype == np.float32
    assert df["close"].iloc[9] == np.float32(110.5)   # value recovered, not NaN
    assert df.index.is_monotonic_increasing


def test_chunked_load_matches_single_read(tmp_path, monkeypatch):
    """Chunk boundaries must not change the result."""
    import edge_research.ingestion.loader as loader_module

    n = 1000
    rng = np.random.default_rng(0)
    src = pd.DataFrame({
        "time": pd.date_range("2023-01-01", periods=n, freq="min").strftime("%Y.%m.%d %H:%M"),
        "open": rng.normal(size=n), "close": rng.normal(size=n),
    })
    csv_path = tmp_path / "chunks.csv"
    src.to_csv(csv_path, index=False)

    monkeypatch.setattr(loader_module, "_CHUNK_ROWS", 137)
    df = loader_module.load_csv_and_validate(csv_path)

    assert len(df) == n
    np.testing.assert_allclose(df["open"].to_numpy(), src["open"].to_numpy().astype(np.float32))
    assert df.index[0] == pd.Timestamp("2023-01-01 00:00")
    assert df.index[-1] == pd.Timestamp("2023-01-01 16:39")


def test_load_csv_falls_back_to_python_engine_on_parser_error(sample_csv, monkeypatch):
    """
    A structural parsing failure (e.g. a stray/unescaped quote character
    causing the C tokenizer's 'Buffer overflow caught - possible malformed
    input file' error) is NOT an encoding problem, so it must not be left
    to crash the whole pipeline the way it did before this fallback
    existed -- the loader should retry with the more tolerant Python
    parser engine and succeed.
    """
    import edge_research.ingestion.loader as loader_module

    real_read_csv = pd.read_csv
    call_log = []

    def fake_read_csv(*args, **kwargs):
        call_log.append(kwargs.get("engine", "c"))
        if kwargs.get("engine") != "python":
            raise pd.errors.ParserError(
                "Error tokenizing data. C error: Buffer overflow caught - possible malformed input file."
            )
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(loader_module.pd, "read_csv", fake_read_csv)

    df = loader_module.load_csv_and_validate(sample_csv)

    assert len(df) == 100
    # Must have actually fallen back to the python engine, not just retried
    # the C engine repeatedly across encodings.
    assert "python" in call_log


def test_load_csv_reports_clear_error_when_every_fallback_fails(tmp_path, monkeypatch):
    """If even the Python engine can't parse it under any encoding, the
    final error must clearly point at malformed content, not encoding."""
    import edge_research.ingestion.loader as loader_module

    def always_fails(*args, **kwargs):
        raise pd.errors.ParserError("Error tokenizing data. C error: Buffer overflow caught.")

    monkeypatch.setattr(loader_module.pd, "read_csv", always_fails)

    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("time,open\n2023-01-01,1.0\n")

    with pytest.raises(ValueError, match="malformed content"):
        loader_module.load_csv_and_validate(bad_csv)


def test_load_csv_falls_back_to_quote_none_before_python_engine(sample_csv, monkeypatch):
    """
    A stray, non-terminating quote character (the specific failure the
    user hit: "',' expected after '\"'" from the Python engine, after a
    C-engine buffer overflow) should be recovered by the FAST
    quoting=QUOTE_NONE retry, without ever needing the slow Python engine
    -- confirm that tier is tried, and tried before engine='python'.
    """
    import edge_research.ingestion.loader as loader_module

    real_read_csv = pd.read_csv
    call_log = []

    def fake_read_csv(*args, **kwargs):
        if kwargs.get("quoting") == 3:  # csv.QUOTE_NONE
            call_log.append("quote_none")
            return real_read_csv(*args, **kwargs)
        if kwargs.get("engine") == "python":
            call_log.append("python")
            return real_read_csv(*args, **kwargs)
        call_log.append("default")
        raise pd.errors.ParserError(
            "Error tokenizing data. C error: Buffer overflow caught - possible malformed input file."
        )

    monkeypatch.setattr(loader_module.pd, "read_csv", fake_read_csv)

    df = loader_module.load_csv_and_validate(sample_csv)

    assert len(df) == 100
    assert "quote_none" in call_log
    assert "python" not in call_log  # never needed the slow tier


def test_load_csv_falls_back_to_python_engine_when_quote_none_also_fails(sample_csv, monkeypatch):
    """If quote-disabling doesn't fix it either, the Python engine is still
    tried as the final tier before giving up."""
    import edge_research.ingestion.loader as loader_module

    real_read_csv = pd.read_csv
    call_log = []

    def fake_read_csv(*args, **kwargs):
        if kwargs.get("engine") == "python":
            call_log.append("python")
            return real_read_csv(*args, **kwargs)
        call_log.append("quote_none" if kwargs.get("quoting") == 3 else "default")
        raise pd.errors.ParserError("Error tokenizing data.")

    monkeypatch.setattr(loader_module.pd, "read_csv", fake_read_csv)

    df = loader_module.load_csv_and_validate(sample_csv)

    assert len(df) == 100
    assert call_log[:2] == ["default", "quote_none"]
    assert "python" in call_log
