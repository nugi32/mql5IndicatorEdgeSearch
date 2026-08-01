# edge_research

edge_research is a Python-based research pipeline for discovering and validating trading edges from MQL5-exported indicator data. It turns raw market data and indicator values into candidate conditions, tests those conditions forward in time, and produces structured reports plus MQL5 Expert Advisor stubs.

The project is designed for quantitative research workflows where you want to move from raw CSV exports to statistically tested trade ideas in a repeatable way.

## What this project does

The pipeline follows a multi-stage workflow:

1. Ingest and validate MQL5 CSV data
2. Store the cleaned dataset in Parquet format for efficient reuse
3. Tag known-at values so delayed indicators are handled correctly
4. Generate candidate indicator conditions such as RSI oversold/overbought or moving average relationships
5. Filter conditions by frequency and occurrence thresholds
6. Measure forward-looking probabilities over multiple horizons
7. Apply significance testing and false-discovery-rate correction
8. Validate robustness with walk-forward analysis, regime stress tests, parameter sensitivity, and cost modeling
9. Export YAML reports and generate MQL5 Expert Advisor source files

## Project structure

- [edge_research/ingestion](edge_research/ingestion): CSV loading, validation, and Parquet storage
- [edge_research/known_at](edge_research/known_at): known-at tagging logic for delayed indicators
- [edge_research/conditions](edge_research/conditions): condition generation and evaluation
- [edge_research/forward_profile](edge_research/forward_profile): forward probability profiling and significance analysis
- [edge_research/validation](edge_research/validation): walk-forward, regime stress, sensitivity, and cost tests
- [edge_research/reporting](edge_research/reporting): report schemas and report export
- [edge_research/mql5_codegen](edge_research/mql5_codegen): generation of MQL5 EA source code
- [scripts/run_pipeline.py](scripts/run_pipeline.py): main CLI entry point
- [tests](tests): unit tests covering ingestion, conditions, profiling, and validation

## Requirements

- Python 3.9 or newer
- A working virtual environment is strongly recommended

## Installation

Create and activate a virtual environment, then install the package:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The package dependencies are defined in [pyproject.toml](pyproject.toml).

## Quick start

A sample CSV export is already included in [data/raw_csv/XAUUSD_D1_export_20100101.csv](data/raw_csv/XAUUSD_D1_export_20100101.csv).

Run the full pipeline with:

```bash
python scripts/run_pipeline.py \
  data/raw_csv/XAUUSD_D1_export_20100101.csv \
  --symbol XAUUSD \
  --timeframe D1 \
  --config-dir config \
  --output-dir output

/mnt/projects/mql5IndicatorsEdge/data/raw_csv
```

This will create an output directory containing:

- a Parquet storage folder
- YAML edge reports under a reports folder
- generated MQL5 Expert Advisor files under a generated_ea folder
- a markdown summary file named EDGES_SUMMARY.md

## Configuration

The pipeline uses configuration files from [config](config):

- [config/pipeline_config.yaml](config/pipeline_config.yaml): general thresholds, horizons, significance settings, and validation parameters
- [config/known_at_delay.yaml](config/known_at_delay.yaml): known-at delay settings for indicator tagging

You can edit these files to adjust the behavior of the pipeline without changing code.

## How the pipeline works

### 1. Ingestion

Raw CSV files are loaded, validated, and converted to a standardized dataframe with a datetime index. Numeric data is normalized to float32 and saved to Parquet.

### 2. Known-at tagging

The tagger handles delayed indicators so that the pipeline avoids lookahead bias when evaluating conditions.

### 3. Condition generation

The condition system generates candidate rules from indicator columns such as RSI, CCI, momentum, and stochastic series. These may be simple thresholds or combined conditions.

### 4. Frequency filtering

Before running expensive forward-profile tests, the system filters out conditions that are too rare or occur too infrequently to be meaningful.

### 5. Forward profiling

The forward-profile engine evaluates how often a condition is followed by an upward move across several horizons.

### 6. Significance testing

The significance layer tests whether observed edge probabilities are meaningfully better than baseline expectations and applies multiple-testing correction.

### 7. Robustness validation

The validation modules check whether a condition survives walk-forward testing, regime-specific stress, parameter changes, and transaction costs.

### 8. Reporting

Discovered edges are serialized into structured YAML reports with provenance and metrics.

### 9. MQL5 code generation

The project can emit MQL5 Expert Advisor skeletons that reflect the discovered conditions for further testing in MetaTrader 5.

## Development and testing

Run the test suite with:

```bash
pytest
```

If you want to format or lint the codebase, the project also includes tooling configured in [pyproject.toml](pyproject.toml).

## Notes

- This is a research pipeline, not a turnkey live-trading system.
- The generated MQL5 files are starter templates and should be reviewed before deployment.
- The quality of the discovered edges depends heavily on the source data, configuration, and the assumptions encoded in the validation steps.

## License

This project is distributed under the MIT license.
