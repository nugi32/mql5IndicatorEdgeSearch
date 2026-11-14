# Project Direction and Research Limitations

## Purpose

Edge Research separates broad signal discovery from stricter strategy validation. The discovery stages identify indicator conditions whose forward directional outcomes differ from a baseline. Later stages test whether those observations survive additional statistical checks, cost assumptions, and trade simulations.

The guiding principle is:

> A directional statistic is a research hypothesis, not a deployable trading strategy.

## Why validation is a separate problem

A condition may show a statistically significant future directional probability and still lose money after costs, trade overlap rules, exit timing, and broker execution are considered. In addition, many conditions, thresholds, horizons, symbols, and repeated experiments create opportunities for overfitting that a correction within one run cannot fully account for.

For that reason, the project does not treat the smallest adjusted p-value or highest in-sample return as sufficient evidence. It combines independent checks and keeps failed candidates visible with reasons.

## Current validation approach

- Apply multiple-testing correction to the forward-probability tests.
- Evaluate direction across rolling inner walk-forward windows.
- Report regime and threshold-sensitivity behavior.
- Reserve a chronological holdout fraction for an additional check.
- Scan and validate candidate holding periods.
- Simulate trades with configurable costs and an execution model.
- Use a rotation-based permutation test as an additional significance check.
- Apply a final gate before generating EA source.
- For an outer walk-forward run, freeze train-selected direction and duration and evaluate them on subsequent test data.

These are filters and diagnostics, not proofs of future profitability. Repeatedly adjusting thresholds, profiles, or selection rules after examining results can consume the apparent independence of the test data.

## Current Phase 7c behavior

Older planning notes described stop-loss/take-profit or trailing-stop simulation. That is not the current Phase 7c implementation. The current simulator uses a selected fixed holding period and exits according to the configured mode:

- Linked MT5-style mode uses bar-open fills, one active position at a time, and tester configuration for execution details.
- `--legacy-sim` uses the older close-based behavior with overlapping trades.

The research simulation is not an every-tick MT5 backtest. The separate `mt5_backtest` component emulates the MT5 **Open prices only** model and has its own costs and settings. Differences between data, spread, commissions, swaps, position constraints, and signal implementation can still change results.

The reported `expectancy_r` uses ATR as a normalization unit when configured; it does not imply that a stop-loss order exists at that distance.

## EA generation and deployment

The code generator emits MQL5 source for candidates that pass the configured strategy gate. Generated files are artifacts for engineering review, not pre-certified trading programs. Confirm indicator handles, buffer indexes, bar shifts, direction, position handling, holding period, costs, and calendar/custom-indicator dependencies. Compile in MetaEditor and run an independent Strategy Tester test before any demo or live use.

## Open limitations

- CSV OHLC bars do not contain the full intrabar path. The default fixed-duration simulator avoids stop/target ordering assumptions, but it does not model tick-level execution.
- Forward outcomes and statistical tests remain exposed to dependence and regime changes. The permutation test is complementary, not a universal correction for every source of dependence or repeated experimentation.
- Costs depend on instrument, broker, time, and account settings. Static or ATR-scaled assumptions may not match realized costs.
- Calendar features depend on coverage, broker/server timestamps, event metadata, and news export settings.
- Custom-indicator values and generated EAs must agree with the exact MT5 indicator binaries, inputs, buffers, and sampling convention.
- An edge can decay or disappear after the research period. No backtest guarantees live performance.

For the implementation sequence and output interpretation, see [How the Pipeline Works](howItWorks.md). For configuration assumptions, see the [Configuration Guide](configuration.md).
