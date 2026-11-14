# Operations Guide

This guide covers the command-line workflows, run management, output interpretation, and local validation.

## Run a single dataset

```bash
python scripts/run_pipeline.py path/to/export.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/XAUUSD/H1 \
  --output-dir output
```

The command reads `pipeline_config.yaml` and `known_at_delay.yaml` from the selected directory. Each invocation normally gets its own unique run folder under `--output-dir`.

Useful single-run options:

| Option | Purpose |
|---|---|
| `--run-name NAME` | Choose the run subdirectory name |
| `--resume [RUN_FOLDER]` | Resume the newest unfinished matching run, or name a specific run |
| `--calendar-csv PATH` | Add calendar-derived `cal_*` features |
| `--max-conditions N` | Limit atomic candidates for a bounded test/smoke run |
| `--legacy-sim` | Use the legacy Phase 7c simulation behavior instead of the linked MT5-style mode |
| `--no-mt5-backtest` | Skip the automatic post-run MT5-style backtest |
| `--mt5-top-n N` | Set how many ranked candidates the automatic backtest processes |
| `--mt5-spread-csv PATH` | Use per-bar spread values from the spread exporter |
| `--mt5-config-root PATH` | Select a different root for MT5 tester YAML settings |
| `--flat-output` | Use legacy direct output layout; avoid when running concurrently |
| `--log-level LEVEL` | Set `DEBUG`, `INFO`, `WARNING`, or `ERROR` logging |

## Run outer walk-forward validation

```bash
python scripts/run_walkforward_pipeline.py path/to/export.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/XAUUSD/H1 \
  --output-dir output_walkforward
```

The profile must define calendar windows (`meta_wf_runs`) or bar-count windows (`meta_wf_train_bars`). Options include `--resume`, `--run-name`, `--calendar-csv`, `--max-conditions`, `--legacy-sim`, `--no-ranker`, `--no-mt5-backtest`, `--sort-top-n`, `--mt5-top-n`, `--mt5-config-root`, and `--mt5-spread-csv`.

Walk-forward runs also support memory safeguards:

```bash
python scripts/run_walkforward_pipeline.py path/to/export.csv \
  --symbol XAUUSD --timeframe M1 \
  --config-dir config/WALKFORWARD/XAUUSD/M1 \
  --output-dir output_walkforward \
  --min-free-gb 3 \
  --max-rss-gb 40
```

`--min-free-gb` defaults to 2 GB; set it to `0` to disable that system-available-memory threshold. `--max-rss-gb` is disabled unless set. A guard stop preserves progress for a later resume.

## Pause and resume

- Press `Ctrl+C` once to request a safe pause at a checkpoint boundary.
- Alternatively, create an empty `PAUSE` file in the active run directory.
- Run the same command with `--resume` to continue. Supply the original CSV and configuration.
- If multiple incomplete runs exist, specify the run directory: `--resume output_walkforward/<run-name>`.

The checkpoint includes a fingerprint of relevant inputs. A changed CSV, config, or other fingerprinted input is rejected rather than silently mixed into saved results. A checkpoint is temporary run state and is removed after successful completion.

## Inspect and re-rank runs

List runs beneath an output parent:

```bash
python scripts/list_runs.py output_walkforward
```

Re-rank a completed or partially completed run:

```bash
python scripts/run_ranker.py output_walkforward/<run-name> \
  --symbol XAUUSD --timeframe H1 --sort-top-n 10
```

The ranker reads existing results; it does not re-run the research pipeline. It writes `ranker_sort_result.md` and `ranker_sort_top.csv`. A single-run ranking is based on whole-dataset gate/simulation results and is therefore in-sample. Walk-forward rankings use recorded test-period results. Ranking scores and warning thresholds are not additional statistical proof.

## Run or inspect an MT5-style backtest

The pipeline normally attempts a post-run backtest of the ranked candidates. Skip it with `--no-mt5-backtest`, or re-run later:

```bash
python scripts/run_mt5_backtest.py path/to/export.csv \
  --symbol XAUUSD --timeframe H1 \
  --run-dir output/<run-name> --top-n 20
```

The standalone script also supports a single condition, tester config overrides (`--set KEY=VALUE`), spread CSV input, date limits, calendar CSV input, and optional trade-list comparison. See `python scripts/run_mt5_backtest.py --help` for the current complete option list.

## Output files

Typical single-run folder:

```text
<run>/
├── RUN_INFO.json
├── run.log
├── storage/                         # cached Parquet input
├── STRATEGY_GATE_RESULTS.csv        # every candidate's gate decision/reasons
├── EDGES_SUMMARY.md                 # readable candidate summary
├── reports/                         # one YAML report per candidate
├── generated_ea/                    # source for gate-passing candidates
├── ranker_sort_result.md
├── ranker_sort_top.csv
└── mt5_backtest/                    # when the automatic backtest succeeds
```

A walk-forward folder additionally contains `WALKFORWARD_SUMMARY.md`, per-window training outputs, and `TEST_PERIOD_RESULTS.csv` files. Exact contents can differ by mode and by whether ranking/backtesting was skipped.

Start with `STRATEGY_GATE_RESULTS.csv` for a single run. For outer walk-forward results, inspect `WALKFORWARD_SUMMARY.md` and the relevant test-period CSV. Do not select EAs based only on the train output or the ranker score.

## Tests and development checks

Install the development extra, then run:

```bash
pytest
```

Targeted tests can be run with `pytest tests/test_<area>.py`. The project configures pytest, Black, Ruff, and mypy in `pyproject.toml`; the presence of configuration does not imply every tool is a required CI gate.
