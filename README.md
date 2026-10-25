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
pip install tabulate # Also required, but pyproject.toml hasn't been updated yet.
pip install pyarrow 
```

The package dependencies are defined in [pyproject.toml](pyproject.toml).

## Quick start

A sample CSV export is already included in [data/raw_csv/XAUUSD_D1_export_20100101.csv](data/raw_csv/XAUUSD_D1_export_20100101.csv).

Run the full pipeline with:

```bash
python scripts/run_pipeline.py \
  data/raw_csv/XAUUSD_H4_export_20100101.csv \
  --symbol XAUUSD \
  --timeframe H4 \
  --config-dir config/XAUUSD/H4 \
  --output-dir output
```

```bash
python scripts/run_pipeline.py \
  data/raw_csv/EURUSD_H4_export_20100101.csv \
  --symbol EURUSD \
  --timeframe H4 \
  --config-dir config/EURUSD/H4 \
  --output-dir output
```

If your CSV covers a short period (a few months up to ~1 year) instead of
the full multi-year export, point `--config-dir` at the matching profile
under `config/SHORT_DATA/` instead -- everything else about the command
stays the same:

```bash
python scripts/run_pipeline.py \
  data/raw_csv/XAUUSD_M1_1y.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config/SHORT_DATA/XAUUSD/M1 \
  --output-dir output
```

This will create an output directory containing:

- a Parquet storage folder
- YAML edge reports under a reports folder
- generated MQL5 Expert Advisor files under a generated_ea folder
- a markdown summary file named EDGES_SUMMARY.md

## MQL5 data exporters (mql5/)

Two MQL5 programs produce the input files:

| Program | Type | Output | Used by |
|---|---|---|---|
| `mql5/dataExporter.mq5` (v1.01+) | EA, Strategy Tester | `<SYMBOL>_<TF>_export_<date>.csv`: OHLCV, ~100 standard indicator columns, plus the custom-indicator columns below | `csv_path` argument |
| `mql5/economicCalendarDataExporter.mq5` | Script, **live chart** | `economic_calendar.csv` (Common\Files) | `--calendar-csv` (optional) |

`dataExporter.mq5` needs the compiled `VolRegime_ATR.ex5` and `PriceStructure.ex5`
(sources: `mql5/volRegime.mq5`, `mql5/priceStructure.mq5`) to be found by the tester
(`#property tester_indicator`). If iCustom() fails the exporter writes `NaN`, and the
loader logs a warning naming the indicator whose columns are entirely NaN.

Custom-indicator columns added by the exporter:

- `volregime_atr_pctl` (0-100), `volregime_atr_ratio` (ATR / SMA(ATR)), `volregime_regime` (0 low / 1 mid / 2 high vol)
- `ps_dist_pdh_atr`, `ps_dist_pdl_atr`, `ps_dist_sess_h_atr`, `ps_dist_sess_l_atr`,
  `ps_dist_round_up_atr`, `ps_dist_round_dn_atr` -- `(level - price) / ATR`, positive = level above price
- `ps_gap_atr` (signed daily gap in ATR), `ps_gap_fill_pct` (0-100)

They are picked up automatically: the condition generator creates atoms for every one of
these columns that exists in the CSV (thresholds: `volregime_*`, `ps_*` keys in
`pipeline_config.yaml`). Exports made with the older exporter (no custom columns) still load.
The time column is parsed in the exporter's `YYYYMMDD HH:MM` format.

### news_* columns (dataExporter.mq5 v1.02)

v1.02 merges the calendar exporter into `dataExporter.mq5`: attach it to a **live chart** once
(writes `economic_calendar.csv` to Common\\Files), then run it in the Strategy Tester; the tester
export gets `news_min_to_next`, `news_next_importance`, `news_min_since_last`, `news_last_importance`,
`news_last_surprise`, `news_in_window`, `news_count_next_24h`. The live-chart CSV has the same format
as the old stand-alone script, so it also works with `--calendar-csv` below.

The loader repairs two issues in these columns before anything else sees them
(`loader.sanitize_news_columns`):

1. **Look-ahead at the bar close.** The EA counts an event stamped exactly at the bar close as
   already released, so `news_last_surprise` holds a release's result on the very row where the
   decision is taken before the market reacts. NFP/CPI/FOMC often sit exactly on a bar boundary.
   Those rows are rewritten: the event becomes the *next* event, the last-event fields become NaN.
2. **Calendar coverage.** Bars before the first / after the last calendar event are set to NaN
   instead of looking like "far from news".

Atoms are generated for `news_*` (surprise: sign only, because its raw units differ per event), and
edges using them are flagged like `cal_*` ones. Remaining caveats: the exported surprise is not
oriented by impact (higher unemployment is bad news), and `news_*_importance` is constant when only
HIGH events were exported (no atoms are created for a constant column). The Python `cal_*` features
(`--calendar-csv`) are the better-normalised alternative: z-scored surprise, symbol-oriented impact.

### Economic calendar features

```bash
python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M30_export_20100101.csv \
  --symbol XAUUSD --timeframe M30 \
  --config-dir config/XAUUSD/M30 --output-dir output \
  --calendar-csv data/economic_calendar.csv
# same flag for scripts/run_walkforward_pipeline.py
```

With `--calendar-csv`, `edge_research/ingestion/economic_calendar.py` joins the calendar to every
bar (both files are in broker server time, no conversion) and adds float32 `cal_*` columns that
are mined like any other indicator column:

| Column | Meaning |
|---|---|
| `cal_min_to_next_high` / `cal_min_since_last_high` | minutes to the next scheduled / since the last released event of importance >= `calendar_importance_high` (capped at `calendar_max_minutes`) |
| `cal_high_in_bar` / `cal_high_next_bar` | 1 if such an event was released inside this bar / is scheduled inside the next bar |
| `cal_*_medplus` | the same four for importance >= `calendar_importance_medplus` |
| `cal_last_impact_sym` | +1 / -1 / 0: MT5 impact flag of the last high-impact release, re-oriented to the symbol (positive USD impact = -1 for XAUUSD), 0 after `calendar_impact_max_age_min` |
| `cal_last_surprise_absz` | abs(actual - forecast) in std units of that event's own past surprises (expanding, previous releases only) |

Only the currencies that matter for the symbol are used (XAUUSD -> USD, EURUSD -> EUR + USD;
override with `calendar_currencies`). Holidays are dropped. Bars outside the calendar file's
time range get NaN (never "no news"), so export the calendar from the start of your price history.
No look-ahead: features use only events strictly before the bar close, plus the public schedule.

**Calendar edges cannot be cross-checked in MT5.** The calendar API does not work in the
Strategy Tester (error 4014). Edges whose condition reads a `cal_*` column are therefore flagged
(`uses_calendar`) in `STRATEGY_GATE_RESULTS.csv`, in the summary table, in the Markdown report,
in the report YAML metadata and in the generated stub comment; the same goes for
`uses_custom_indicators` (an EA must read `volregime_*` / `ps_*` through `iCustom()`).
In walk-forward mode the flags are in each window's `TEST_PERIOD_RESULTS.csv`.

**Known limitation of the PriceStructure export.** `priceStructure.mq5` writes its buffers only
for the last bar (shift 0), while `dataExporter.mq5` reads shift 1 at each new bar. In a tester
export the `ps_*` values therefore most likely reflect the state at that bar's first tick (price
= the bar's open), not its close. That is not look-ahead, but it differs from the other columns
and from what an EA would read live at shift 0 -- verify before trusting `ps_*` edges.

## Configuration

The pipeline uses configuration files from [config](config):

- [config/pipeline_config.yaml](config/pipeline_config.yaml): general thresholds, horizons, significance settings, and validation parameters
- [config/known_at_delay.yaml](config/known_at_delay.yaml): known-at delay settings for indicator tagging

Per-symbol, per-timeframe profiles live under `config/<SYMBOL>/<TIMEFRAME>/`
(e.g. `config/XAUUSD/M30/`), each with its own `pipeline_config.yaml` +
`known_at_delay.yaml`. For a few months up to ~1 year of data instead of
the full multi-year export, use the matching profile under
`config/SHORT_DATA/<SYMBOL>/<TIMEFRAME>/` (e.g.
`config/SHORT_DATA/XAUUSD/M30/`) instead -- walk-forward window sizes and
minimum-occurrence thresholds are the only things that differ from the
long-history profile; everything else (cost model, gate thresholds,
horizon-scan range) is identical. See the comment header in any
`config/SHORT_DATA/.../pipeline_config.yaml` for the exact bar-count
assumption and how to rescale it further if your data length is very
different.

A third tier, `config/WALKFORWARD/<SYMBOL>/<TIMEFRAME>/`, exists
specifically for walk-forward mode (below) on the full multi-year export --
see that section for why it's a separate tier from `config/<SYMBOL>/<TF>/`
rather than an addition to it.

Older config layouts that are no longer the primary ones (a pre-symbol-split
`config/<TIMEFRAME>/` layout, and an unused single-file-per-timeframe
layout) have been archived under `config/_legacy/` rather than deleted --
see `config/_legacy/README.md` if you're looking for something that used
to be at one of those paths.

You can edit these files to adjust the behavior of the pipeline without changing code.

## Walk-forward mode

A single run of `scripts/run_pipeline.py` discovers conditions from, and
validates them against, one fixed block of history. `scripts/run_walkforward_pipeline.py`
instead runs the *entire* pipeline repeatedly on a rolling window of the
data -- the "Rolling Out-of-Sample" scheme:

```
train ----> test
      train ----> test
            train ----> test
                  train ----> test
```

Per window:

1. Run the whole normal pipeline (condition generation through the Phase 7e
   strategy gate) on the TRAIN slice only.
2. From what passed that gate, keep only the conditions that ALSO sit on a
   performance **plateau** -- their `parameter_sensitivity` score (already
   computed by Phase 7; a +/-15% threshold shift shouldn't wreck the
   result) has to clear `meta_wf_plateau_min_sensitivity`. A condition that
   only works at one hyper-specific threshold value is treated as noise,
   not an edge, however good its train-period number looks.
3. Re-evaluate each surviving candidate's direction and holding period
   -- frozen exactly as chosen on train, no re-optimizing -- against the
   TEST slice, data it was never selected using. Keep only what's still
   net profitable there.
4. Whatever's accepted (which can be zero conditions -- that's a valid
   result, not a failure) is recorded, and the window slides forward.

Different windows are allowed to accept completely different conditions,
or none at all. That's intentional: the whole point of this mode is
testing whether an edge is time-local rather than assuming one
combination of indicators should keep working forever.

### Two windowing modes

How the outer train/test windows are actually placed depends on which
keys are in the config-dir's `pipeline_config.yaml`:

| Config tier | Windowing | Outer window | Use for |
|---|---|---|---|
| `config/SHORT_DATA/<SYMBOL>/<TF>/` | bar-count (`meta_wf_train_bars`/`meta_wf_test_bars`/`meta_wf_step_bars`) | ~3 months | A CSV that only covers a few months to ~1 year -- too short to even fit one calendar year |
| `config/WALKFORWARD/<SYMBOL>/<TF>/` | **calendar-year** (`meta_wf_runs`) | 3 years train / 1 year test, rolled forward 1 year at a time | The full multi-year export |

**Calendar mode (`meta_wf_runs`)** anchors every window to January 1st
instead of wherever a fixed bar count happens to land. A fixed bar count
starts and ends at a different real date depending on how many rows exist
in each stretch of data (weekends, holidays, session gaps all shift it) --
so "train on roughly 3 years" could silently mean 2010-04-17..2013-06-02
in one run and something else entirely in another, and a period you
already know produces a good result (e.g. from a manual, separately-run
test) can end up split across two windows or diluted by unrelated data
just because the bar-count boundary happened to fall in the middle of it.
Calendar mode fixes both: `config/WALKFORWARD/.../pipeline_config.yaml`'s
`meta_wf_runs` is a LIST, each entry an independent walk-forward sequence:

```yaml
meta_wf_runs:
  - start_year: 2010
    train_years: 3
    test_years: 1
    step_years: 1
  - start_year: 2011
    train_years: 3
    test_years: 1
    step_years: 1
```

The first entry trains on exactly 2010-01-01..2013-01-01, tests on
2013-01-01..2014-01-01, then rolls the train start forward by
`step_years` (here, 1 year) and repeats for as long as the data covers.
The second entry is a **separate, independent** sequence anchored a year
later (2011-01-01..2014-01-01 train, ...) -- not a continuation of the
first. Add or remove entries to run more or fewer of these; each one
reruns the whole pipeline on every one of its own windows, so more
entries means more total runtime. `step_years` doesn't have to equal
`test_years` -- a smaller step gives overlapping test periods across
consecutive windows in that entry's sequence, a larger step skips ahead.

If your data doesn't end exactly on a year boundary (normal -- weekends,
holidays, export cutoffs), the final window in a sequence is still
produced rather than silently dropped, but marked `truncated` in
`WALKFORWARD_SUMMARY.md` with both the calendar-exact ("nominal") and the
actual date range the data could provide -- check that flag before
trusting a truncated window's test-period result the same as a full one.

**Bar-count mode (`meta_wf_train_bars`/`meta_wf_test_bars`/`meta_wf_step_bars`)**
is what `config/SHORT_DATA/` still uses, unchanged -- calendar-year windows
don't make sense on a dataset that doesn't even span a full year.

Usage (identical either way -- the config-dir determines the mode):

```bash
python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M5.csv \
  --symbol XAUUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/XAUUSD/M5 \
  --output-dir output_walkforward

  python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M1.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config/WALKFORWARD/XAUUSD/M1 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_H1.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/XAUUSD/H1 \
  --output-dir output_walkforward


python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD_H1_export_20100101.csv \
  --symbol EURUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/EURUSD/H1 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD_M5_export_20100101.csv \
  --symbol EURUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/EURUSD/M5 \
  --output-dir output_walkforward
```

**`config/<SYMBOL>/<TF>/` (the plain long-history profile) deliberately has
NO `meta_wf_*` block and must not be used for walk-forward mode.** Its
`wf_train_bars`/`wf_test_bars` (the *inner* walk-forward check that runs
once per window, inside Phase 7 -- see below) are calibrated assuming the
entire multi-year file is the training set. Point walk-forward mode at
that profile and the inner check would need more bars than a single outer
window even contains, so it would silently produce zero inner windows on
every single outer window, fail every condition's `robust_walk_forward`
check with no other evidence considered, and report "0 candidates" for
the entire run -- with no crash, nothing that looks like an error.
`scripts/run_walkforward_pipeline.py` checks for exactly this (comparing
`wf_train_bars + wf_test_bars` against the OBSERVED bar count of an
actual train window -- in calendar mode that's measured from the real
data for each run, since it isn't a fixed config number there) and
refuses to start rather than run silently to a meaningless result -- if
you see that error, use `config/WALKFORWARD/` or `config/SHORT_DATA/`
instead of `config/<SYMBOL>/<TF>/`.

This inner-vs-outer distinction matters generally: `wf_train_bars` /
`wf_test_bars` / `wf_step_bars` control the walk-forward check run ONCE
INSIDE a single pipeline pass (direction consistency, holding-bars
stability -- see Phase 7 below); `meta_wf_runs` (or, in bar-count mode,
`meta_wf_train_bars` / `meta_wf_test_bars` / `meta_wf_step_bars`) control
the OUTER rolling windows this script runs the whole pipeline on, once
per window. Both exist, both matter, and they are deliberately
namespaced apart (`meta_wf_*` vs `wf_*`) so changing one never silently
changes the other. **If you build a profile for a different window
length (e.g. `train_years: 5`), the same rule applies: recalibrate that
profile's own `wf_train_bars`/`wf_test_bars`/`wf_step_bars`/
`min_occurrence` for ITS window size, the same way `config/SHORT_DATA/`
and `config/WALKFORWARD/` were each built -- don't just change
`meta_wf_runs` on `config/<SYMBOL>/<TF>/` and expect it to work.**

Output layout (calendar mode -- bar-count mode is the same minus the
`run_*` grouping level, windows sit directly under `output_walkforward/`):

```
output_walkforward/
  storage/                              # Parquet from the one-time ingestion
  WALKFORWARD_SUMMARY.md                # every run, every window: dates, candidates, accepted conditions + test-period stats
  run_2010/
    window_0000/
      train/                            # a completely normal single-run output for the train slice
        reports/  generated_ea/  STRATEGY_GATE_RESULTS.csv  EDGES_SUMMARY.md
      TEST_PERIOD_RESULTS.csv           # every plateau candidate's test-period stats + pass/fail
    window_0001/
      ...
  run_2011/
    window_0000/
      ...
```

`window_NNNN/train/generated_ea/` holds an EA for every condition that
passed the TRAIN-period gate -- that's every plateau candidate, not only
the ones that also passed the test period. Check `TEST_PERIOD_RESULTS.csv`
(`test_passed` column) or `WALKFORWARD_SUMMARY.md` before trusting one of
those EAs -- match it up by the **condition string**, not by `edge_id`
alone: `edge_id` is just a sequential counter that restarts at 1 in every
window, so e.g. `XAUUSD_M30_3` in one window and `XAUUSD_M30_3` in another
are almost certainly two unrelated conditions that happened to land at
the same position in each window's own list.

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
