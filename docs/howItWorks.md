# How the Pipeline Works

This document describes the current implementation. The main entry points are `scripts/run_pipeline.py` for one dataset and `scripts/run_walkforward_pipeline.py` for an outer rolling train/test workflow.

## End-to-end flow

```text
MT5 export CSV
    |
    v
1. Ingestion and Parquet cache
    |
    v
2. Availability rules and candidate generation
    |
    v
3. Frequency filter
    |
    v
4. Forward profiles and significance tests
    |
    +--> 6b. Optional cost-aware pre-filter
    |
    v
5. Robustness and holdout checks
    |
    v
6. Trade simulation and holding-period selection
    |
    v
7. Rotation permutation test and strategy gate
    |
    v
Reports, gate results, generated EA source
    |
    v
Post-run ranker and optional MT5-style backtest
```

The phase numbers below use the names emitted by the pipeline logs. Phase 1 ingests the dataset; the shared core then runs Phases 2-9.

## Phase-by-phase

### Phase 1: ingestion and storage

`edge_research/ingestion/loader.py` parses the exporter CSV in chunks, parses the bar timestamps, converts numeric feature data to `float32`, validates the resulting frame, and writes a Parquet cache under the run's `storage/` directory. The loader also handles optional calendar feature attachment and sanitizes supported news columns.

Treat one CSV as one symbol/timeframe dataset. Timestamps are expected to represent MT5 broker/server time. The pipeline does not infer a timezone conversion.

### Phase 2: availability configuration

`edge_research/known_at/tagging.py` loads `known_at_delay.yaml`, whose patterns map exported column names to delays in bars. Shipped profiles generally set supported columns to zero delay. Add nonzero delays only when the feature's actual availability requires them, and verify how the condition-building path applies the rule before relying on a custom delay.

### Phase 3: condition generation

`edge_research/conditions/condition_library.py` defines atomic comparisons and AND-combinations. Depending on the columns present and the selected YAML profile, the generator creates threshold conditions for oscillator and other supported features, moving-average comparisons, and eligible custom/calendar/news features.

Combined conditions are drawn from a bounded pool of promising atomic conditions. The pipeline avoids combinations with repeated indicator families and filters redundant column pairs by correlation. This limits the combinatorial growth; it does not eliminate the multiple-testing risk of trying many configurations or repeated research runs.

### Phase 4: frequency filtering

`edge_research/conditions/frequency_filter.py` removes masks that fail configured minimum occurrence and per-year frequency thresholds. This happens before the heavier profile and validation steps.

### Phases 5-6: forward profile and significance

For a trigger at the close of bar `i`, the forward-profile engine assumes entry at the next bar's open. For horizon `h`, it marks the outcome bullish when the close at `i + 1 + h` is above that entry open. It compares each condition's bullish proportion with an unconditional baseline at the same horizon.

The significance analyzer runs two-sided proportion tests across horizons and applies the configured multiple-testing correction (`fdr_method`, commonly Benjamini-Hochberg). A significant horizon is a directional screening result, not a simulated trade return.

### Phase 6b: optional cost-aware pre-filter

When `precheck_enabled` is true, a lightweight cost estimate can remove significant conditions before the full robustness stack. It uses the configured direction and cost assumptions. This is a screening stage and is not equivalent to the detailed Phase 7c simulation.

### Phase 7: robustness

Each surviving condition is assessed using:

- Rolling inner walk-forward windows from `wf_train_bars`, `wf_test_bars`, and `wf_step_bars`, checking whether direction remains consistent on test portions.
- Regime stress summaries using configured volatility and trend classifications.
- Parameter sensitivity by shifting eligible numeric thresholds and comparing forward profiles. Conditions without a shiftable numeric threshold may not receive a sensitivity score.
- A scan over configured holding periods. Candidate holding bars are ranked by a consistency statistic based on cost-adjusted returns, rather than simply choosing the largest observed mean return. The selected duration is also checked across walk-forward windows.

If the inner train-plus-test window does not fit the dataset, the validator can produce no windows. The pipeline warns that this can cause robustness gates to reject every candidate; adjust the profile rather than interpreting this as evidence about market behavior.

### Phase 7b: holdout check

The configured final fraction of the data (`holdout_pct`) is evaluated separately as a final holdout result. A holdout summary is evidence for review, not an independent guarantee of future performance. Avoid repeatedly tuning a strategy against the same holdout and then continuing to call it untouched.

### Phase 7c: trade simulation

The pipeline simulates the selected direction and holding duration with configured spread and slippage assumptions. The normal CLI path links MT5 tester settings from `config/MT5_TESTER/` unless `--legacy-sim` is requested.

In the MT5-style mode, fills use bar opens, the configured position limit applies (one position by default), and positions exit at a later bar open according to the linked tester settings. The legacy mode instead preserves the earlier close-of-bar, overlapping-trade behavior. Neither mode models every tick. The simulator reports trade counts, win rate, expectancy, profit factor, and R-normalized results; here, R is normalized using the configured ATR column and is not a stop-loss risk unit.

### Phase 7d: rotation permutation test

`edge_research/validation/permutation_test.py` compares the observed directional effect with effects from circularly rotated forward-outcome data. It complements the analytic significance test by preserving the outcome sequence's structure while disrupting its alignment with the condition triggers. The configured permutation count and optional random seed determine resolution and reproducibility.

### Phase 7e: strategy gate

`edge_research/selection/strategy_gate.py` records pass/fail and reasons for each candidate. The default gate can require significant evidence, walk-forward direction consistency, permutation significance, enough simulated trades, positive R expectancy, a minimum profit factor, and stable selected holding bars. Bootstrap confidence-bound gating is optional and requires bootstrap simulation to be enabled.

Candidates that fail remain visible in reports. Only gate-passing candidates are passed to Phase 9 code generation.

### Phases 8-9: reports and EA source

Phase 8 writes a YAML report per candidate, `EDGES_SUMMARY.md`, and `STRATEGY_GATE_RESULTS.csv`. Phase 9 writes `.mq5` source for gate-passing candidates to `generated_ea/`.

The generated source is a starting point, not a substitute for checking each condition-to-MQL5 mapping. Review and compile it in MetaEditor, then test in MT5 with the intended symbol, timeframe, dates, spread, and account settings.

## Outer walk-forward workflow

The outer walk-forward runner repeatedly executes the full discovery pipeline on each training slice. It selects gate-passing train candidates whose sensitivity score clears the configured plateau threshold, freezes their direction and holding bars, and evaluates them on the following test slice without re-optimizing those choices.

Two window definitions are supported:

- Calendar windows when `meta_wf_runs` is present. Each configured run specification defines its own calendar-year train/test sequence.
- Fixed bar-count windows when `meta_wf_train_bars` is present. This supports shorter datasets where calendar-year windows are unsuitable.

The two modes are selected by the configuration keys, not only by the directory name. A window that accepts no candidates is a valid result.

## Main implementation areas

| Module | Responsibility |
|---|---|
| `edge_research/ingestion/` | CSV parsing, Parquet storage, economic-calendar features |
| `edge_research/known_at/` | Availability-delay configuration |
| `edge_research/conditions/` | Candidate conditions, masks, and frequency checks |
| `edge_research/forward_profile/` | Forward outcomes and statistical significance |
| `edge_research/validation/` | Inner walk-forward, regimes, sensitivity, costs, permutation test |
| `edge_research/simulation/` | Holding-period scan and trade simulation |
| `edge_research/selection/` | Final strategy gate |
| `edge_research/walkforward/` | Outer train/test selection and evaluation |
| `edge_research/reporting/` | Candidate reports and Markdown summary |
| `edge_research/mql5_codegen/` | MQL5 source generation |
| `edge_research/ranking/` | Post-run ranking |
| `edge_research/mt5_backtest/` | Separate MT5 open-prices-only emulation |
| `edge_research/checkpoint/` | Run locks, fingerprints, and resumable state |
