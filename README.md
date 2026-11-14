# Edge Research

Edge Research is a Python research pipeline for screening indicator-based market conditions from MetaTrader 5 (MT5) exports. It measures forward outcomes, applies statistical and robustness checks, simulates trades with configurable execution costs, and writes reports plus candidate MQL5 Expert Advisor (EA) source files.

It is a research and validation tool, not an automated live-trading system. Generated EAs require code review, compilation, and independent testing in the MT5 Strategy Tester before any demo or live use.

## Documentation

- [How the pipeline works](docs/howItWorks.md): stages, data flow, metrics, and decision logic.
- [Configuration guide](docs/configuration.md): selecting profiles and configuring thresholds and costs.
- [Operations guide](docs/operations.md): commands, pause/resume, outputs, ranking, backtests, and tests.
- [MQL5 data and exporters](docs/mql5-data.md): input schema, exporters, custom indicators, and calendar data.
- [Project direction and limitations](docs/PROJECT_DIRECTION.md): design rationale and research caveats.
- [Command cookbook](note/command.md): copyable command templates.
- [EA review checklist](note/convert.md): checks required before using generated EA source.

## Requirements and installation

- Python 3.9 or newer.
- An MQL5-exported CSV for the symbol and timeframe being researched.
- For the end-to-end run commands, install the project and development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Dependencies and optional analysis packages are declared in [pyproject.toml](pyproject.toml).

## Quick start

First export bars and indicators from MT5 as described in [MQL5 data and exporters](docs/mql5-data.md). Replace the example CSV path below with the path to your own export. Choose a configuration profile that matches both the symbol and the dataset length.

Single-dataset run:

```bash
python scripts/run_pipeline.py path/to/XAUUSD_H1.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/XAUUSD/H1 \
  --output-dir output
```

Rolling out-of-sample run:

```bash
python scripts/run_walkforward_pipeline.py path/to/XAUUSD_H1.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/XAUUSD/H1 \
  --output-dir output_walkforward
```

Both commands create a unique run directory beneath the selected output directory. Review `STRATEGY_GATE_RESULTS.csv` for a single run, or `WALKFORWARD_SUMMARY.md` and each window's `TEST_PERIOD_RESULTS.csv` for a walk-forward run. See the [operations guide](docs/operations.md) for all outputs and options.

## Repository map

| Path | Purpose |
|---|---|
| [edge_research/](edge_research/) | Python ingestion, candidate generation, validation, simulation, reporting, and code generation |
| [scripts/](scripts/) | Command-line entry points |
| [mql5/](mql5/) | MT5 exporters, helper indicators, and related MQL5 source |
| [config/](config/) | Symbol/timeframe research profiles and MT5 tester settings |
| [tests/](tests/) | Automated test suite |
| [data/raw_csv/](data/raw_csv/) | Intended location for locally supplied exports; input data may not be included in a checkout |

## Development

Run the test suite with:

```bash
pytest
```

The project uses pytest configuration in [pyproject.toml](pyproject.toml). The numerical results are only as reliable as the input data, configuration, and execution assumptions; successful tests do not establish that a strategy is profitable or safe to deploy.
