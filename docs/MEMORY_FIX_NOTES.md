# Memory and Long-Run Notes

This page records implementation behavior relevant to large CSV files and long walk-forward runs. It is not a benchmark or a guarantee of a particular peak-memory footprint; actual usage depends on data size, columns, configuration, and installed libraries.

## Ingestion

The CSV loader reads data in chunks, converts numeric columns to `float32` during ingestion, and writes the Parquet cache in row groups. This avoids holding multiple full-size numeric copies during parsing. Corrupted timestamp or numeric fields can still be dropped or represented as missing values, so inspect warnings and row counts.

## Candidate masks and computation

Condition masks and forward matrices can be large on high-frequency datasets. The pipeline releases rejected candidate masks before its more expensive validation loops. Holding-period scans and combination-correlation work have optimizations intended to limit repeated allocations and calculations.

## Walk-forward memory safeguards

`scripts/run_walkforward_pipeline.py` exposes:

- `--min-free-gb`: stop cleanly when system-available memory falls below the requested threshold; defaults to 2 GB, and `0` disables this guard.
- `--max-rss-gb`: stop cleanly when the process exceeds a specified resident-memory limit; disabled by default.

Memory logs are useful for distinguishing a stable per-window footprint from growth across windows. A guard stop should be resumable with the original command and inputs.

```bash
python scripts/run_walkforward_pipeline.py path/to/export.csv \
  --symbol XAUUSD --timeframe M1 \
  --config-dir config/WALKFORWARD/XAUUSD/M1 \
  --output-dir output_walkforward \
  --min-free-gb 3 --max-rss-gb 40
```

See the [Operations Guide](operations.md) for pause/resume behavior and the [Configuration Guide](configuration.md) for window settings.
