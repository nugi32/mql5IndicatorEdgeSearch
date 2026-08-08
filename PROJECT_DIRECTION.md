# edge_research: Project Direction — From Signal Discovery to Strategy Construction

**Status:** Active pivot, effective this document's date.
**Owner:** Nugi
**Scope:** `edge_research` Python pipeline + generated MQL5 EAs (`mql5IndicatorsEdge` project)

---

## 1. Where we came from

The original pipeline answers one narrow question extremely well:

> "If condition X is true at the close of bar `i`, what is the probability
> that `close[i+1+h] > open[i+1]` for some fixed horizon `h`?"

This is a fast, vectorized way to screen a huge space of indicator-based
conditions (now including multi-indicator AND combinations across
different indicator families) and filter them down using frequency
thresholds, a two-sided proportion z-test, and Benjamini-Hochberg FDR
correction across horizons and conditions.

That pipeline works and is not being thrown away. It is Phases 1–7b of
this project and remains the **signal discovery** stage.

## 2. The problem that triggered this pivot

Across several iterations of this project, a consistent pattern emerged:

1. Directional probabilities from Phase 5–6 top out around 52–56% even for
   the statistically "cleanest" conditions (lowest `p_adj`, largest
   `effect_size`).
2. Converting a condition that looks strong in the report into an actual
   MQL5 EA (with a stop loss, take profit, and live tick-by-tick execution)
   consistently produces much worse — often unprofitable — results than the
   Phase 5–6 numbers suggested.

Two root causes were identified:

### 2a. Measurement/execution mismatch

Phase 5–6 measures a **directional probability at a fixed horizon using
the bar's close**. It does not simulate:

- Entry with realistic spread/slippage
- A stop loss or take profit
- The *path* price takes between entry and the horizon (a condition can
  have real directional edge at the horizon while also being highly
  likely to get stopped out on the way there — the old pipeline is
  structurally blind to this, because it only ever looks at two points in
  time: the entry and the horizon)

An EA that trades with SL/TP is answering a completely different
question than "was price higher N bars later?" — so strong Phase 5–6
numbers are not a reliable predictor of live EA performance.

### 2b. Multiple-testing / overfitting risk compounding across runs

FDR correction inside a single pipeline run controls the false-discovery
rate *for that run's set of tests*. It does not — and cannot — account for
the fact that the pipeline has been re-run many times with hand-picked
threshold grids (RSI/CCI/Stochastic/Momentum thresholds, `top_n_atomic_for_combine`,
`max_atoms_per_combo`, correlation cutoffs, etc.), each run effectively
adding more "hidden" comparisons that no automated correction sees. The
practical symptom is exactly what was observed: edges that look
statistically airtight (`p_adj = 0`) but don't survive contact with
walk-forward validation, let alone live trading.

## 3. The decision: stop optimizing signal *discovery*, start optimizing signal *validation and execution realism*

We explicitly reject the idea of scaling up brute-force search further
(more indicators, more combinations, more thresholds tried across more
manual pipeline runs). More search without better validation only makes
overfitting risk worse, not better — see 2b above.

Instead, the project pivots toward **strategy construction**: taking the
(already large) pool of candidate conditions the existing pipeline
produces, and subjecting them to progressively stricter, execution-realistic
validation, so that only a small number of genuinely trustworthy candidates
ever reach MQL5 code generation.

### Guiding principle

> A condition is worth turning into an EA only if it survives being traded,
> not just being measured.

## 4. New pipeline phases

The existing Phases 1–7b are unchanged. Three new phases are inserted
between Phase 7b (Holdout Testing) and Phase 8 (Report Generation):

### Phase 7c — Realistic Trade Simulation (`edge_research/simulation/trade_simulator.py`)

Event-driven, bar-by-bar simulation of what actually happens if a
condition is traded with a concrete, EA-realistic exit scheme: ATR-based
stop loss, ATR-based take profit, optional trailing stop, a maximum
holding period, and spread/slippage cost on both entry and exit.

Produces per-condition trade statistics: win rate, average win/loss (in
price units), **expectancy in both price units and R-multiples**, profit
factor, and a max-drawdown figure from the resulting equity curve.

This is the primary fix for problem 2a. A condition is not judged on
"was price higher at the horizon" anymore, but on "would a trade with a
real stop and target have made money."

**Known, deliberate limitation:** we only have OHLC bars, not tick data,
so when both the stop and target fall inside the same bar's high-low
range we cannot know which was truly touched first. The simulator
resolves this with a configurable, conservative default
(`intrabar_priority="stop_first"`) and always reports which assumption was
used. This module is a screening tool, not a replacement for a full
"every tick" MetaTrader Strategy Tester run before any live/demo
deployment — that remains a mandatory final step outside this pipeline.

### Phase 7d — Rotation-Based Permutation Test (`edge_research/validation/permutation_test.py`)

An additional, non-parametric significance check that complements (does
not replace) the analytic z-test from Phase 6.

The z-test assumes each triggered sample is close to an independent
Bernoulli draw. Market bars are autocorrelated — a condition that stays
true for several consecutive bars produces overlapping, correlated
"samples," which inflates the z-test's apparent significance. This is a
likely contributor to problem 2b.

The permutation test builds a null distribution by circularly rotating
the real forward-outcome sequence by many random offsets (preserving its
full autocorrelation and seasonal structure while destroying any genuine
relationship with condition timing), and computes an empirical p-value:
the fraction of random rotations whose effect size is at least as extreme
as the one actually observed for the real (unrotated) alignment.

Because it makes no distributional assumptions and directly uses the
data's own autocorrelation structure, this is a stricter and more honest
significance check than the z-test alone, and is implemented as a single
vectorized array rotation so it stays fast even on the ~5.5M-row M1
dataset.

### Phase 7e — Final Strategy Selection Gate (`edge_research/selection/strategy_gate.py`)

Combines every independent piece of evidence into one pass/fail decision.
**All** of the following must hold for a condition to be promoted to MQL5
code generation:

1. Passed Phase 6 significance (`p_adj < alpha`)
2. Robust across walk-forward windows (Phase 7, existing)
3. Passed the Phase 7d rotation permutation test
4. Phase 7c simulated expectancy in R is strictly positive
5. Phase 7c simulation has at least `min_sim_trades` (default 30) trades
   — small samples produce unreliable expectancy estimates
6. Phase 7c simulated profit factor is at least `min_profit_factor`
   (default 1.1 — a deliberately modest margin above breakeven, not a
   high bar, because the goal here is filtering out clearly broken edges,
   not hand-picking a "best" one)

This is intentionally strict. **Reducing the number of surviving edges is
the goal of this pivot, not a side effect to be minimized.** Conditions
that fail the gate are still recorded in the full report for transparency
and future reference, but are clearly marked as not recommended for
EA generation.

Only conditions that pass the gate reach Phase 9 (MQL5 code generation).

## 5. What does NOT change

- Phases 1–7b (ingestion, condition generation including multi-family
  combinations, frequency filtering, forward profiling, FDR-corrected
  significance testing, walk-forward validation, regime stress testing,
  parameter sensitivity, holdout testing) are unchanged.
- The MQL5 EA convention established earlier in this project remains:
  bar-gated processing, signals evaluated on the last completed bar,
  no broker-side SL/TP (virtual position tracking preferred), ATR-based
  safety stops, horizon-based exits where applicable, CSV trade logging,
  unique magic numbers per EA, and — critically — **EAs always remain
  completely separate files, never combined.**
- Indicator timeframes in rule-specific EAs remain hardcoded to the
  timeframe the edge was mined on (established convention from earlier
  debugging of a `Period()` timeframe-mismatch bug).

## 6. Definitions used throughout Phase 7c–7e

- **R-multiple**: trade P&L divided by the initial stop-loss distance.
  An R of +1.0 means the trade made exactly one stop-loss's worth of
  profit; R of −1.0 means it lost exactly one stop's worth. R-multiples
  are the standard way to compare trades with different stop distances
  on equal footing, and are what `expectancy_r` in the trade simulator
  reports.
- **Expectancy**: the average P&L per trade, in either price units
  (`expectancy_pips`) or R-multiples (`expectancy_r`). This is the number
  that actually determines long-run profitability — **not** win rate.
  A 45% win-rate system with a 2.5R average winner and a 1R average loser
  is profitable; a 65% win-rate system with a 0.5R average winner and a
  2R average loser is not. Every selection decision in Phase 7e is based
  on expectancy and profit factor, never on raw win probability alone.
- **Profit factor**: gross profit divided by gross loss across all
  simulated trades. 1.0 is exact breakeven before considering any
  unmodeled costs; values meaningfully above 1.0 are required to survive
  the gate.

## 7. Non-goals (explicitly out of scope for this pivot)

- We are **not** trying to push win rate above some target percentage.
  Win rate is a diagnostic, not a selection criterion.
- We are **not** expanding the indicator/threshold search space further.
  The existing multi-family combination search (Phases 3–4) is already
  more than sufficient supply of candidates; the bottleneck has always
  been validation quality, not candidate quantity.
- We are **not** attempting to fully replace the MetaTrader Strategy
  Tester. Phase 7c is a fast Python-side pre-filter to avoid wasting
  Strategy Tester time on obviously broken candidates — final validation
  in MT5's "every tick" mode before any demo/live deployment is still
  required and is unchanged from prior practice.

## 8. Suggested next steps / future work (not yet implemented)

These are ideas for further hardening the pipeline, intentionally left
for a later iteration rather than bundled into this pivot:

- **Bootstrap confidence intervals on `expectancy_r`** (in addition to the
  point estimate) so Phase 7e can require the lower bound of a CI to be
  positive, not just the point estimate.
- **Portfolio-level correlation check** across all gate-passing edges
  before generating EAs for all of them — highly correlated edges
  (e.g. two RSI-based long conditions that tend to fire together) provide
  little diversification benefit and concentrate risk if run
  simultaneously.
- **A lightweight paper-trading / forward-monitoring loop**: log live
  signal triggers from a demo-account EA against what the simulator
  predicted, to catch simulator/reality drift early, before committing
  real capital.
- **Cost sensitivity sweep**: rerun Phase 7c across a small grid of
  spread/slippage assumptions to see how fragile an edge's positive
  expectancy is to slightly worse execution conditions than currently
  modeled.

## 9. Implementation note (this revision)

`run_pipeline.py` wires Phase 7c/7d/7e in between Phase 7b (holdout) and
Phase 8 (report generation), and gates Phase 9 (MQL5 code generation) on
`edge['gate_passed']`. One schema detail worth calling out explicitly,
since it is easy to get wrong silently: `validate_condition_walk_forward`
(in `edge_research/validation/walk_forward.py`) returns a dict whose
consistency flag is keyed `edge_direction_consistent`, not `consistent`.
`report_generator.py` already reads it under that name
(`report.robustness.walk_forward.get('edge_direction_consistent', False)`);
Phase 7e's gate wiring in `run_pipeline.py` reads the same key, so the
`robust_walk_forward` gate reflects the walk-forward validator's actual
output instead of silently defaulting to `False` for every edge.

## 10. Config is timeframe- and symbol-specific — do not reuse one YAML across runs blindly

A D1 XAUUSD smoke test (4123 bars, 2010-2025) surfaced two config values
in `pipeline_config.yaml` that were tuned for M1/H1-scale data and a
forex-style quote convention, and silently break on other
timeframes/symbols instead of erroring clearly:

- **`wf_train_bars` / `wf_test_bars` / `wf_step_bars`**: `WalkForwardValidator`
  needs `wf_train_bars + wf_test_bars` bars to fit inside the dataset to
  produce even one window. The historical defaults (5000/1000/500) assume
  M1/H1-scale bar counts; on D1 (~4000 bars total) they produce **zero**
  windows, which makes every condition's `edge_direction_consistent`
  default to `False`, which makes the Phase 7e gate reject 100% of
  candidates regardless of trade simulation or permutation test results.
  `run_pipeline.py` now detects and warns loudly about this specific
  situation (zero windows) right when the validator is constructed,
  instead of only surfacing it as 117x repeated per-condition log spam
  with no explanation of the downstream gate impact. Scale these three
  values to the dataset's actual bar count per run/timeframe.
- **`spread_pips` / `pip_value`**: written for 5-digit forex quoting
  (`pip_value: 0.0001`). For XAUUSD, a realistic spread is closer to 0.3
  price units (as established earlier in this project); at the forex
  defaults, Phase 7c's simulated trading cost comes out to ~0.0002 --
  effectively zero -- which makes simulated expectancy look better than
  it would with realistic costs. Use symbol-appropriate values (e.g.
  `pip_value: 0.01`, `spread_pips` sized so `spread_pips * pip_value`
  matches the real spread) rather than the forex defaults for XAUUSD or
  any non-forex instrument.

Practical takeaway: keep a separate `pipeline_config.yaml` (or a
documented per-symbol/per-timeframe override block) per
symbol+timeframe combination rather than one shared file, since several
of these parameters are expressed in raw bar counts / raw price units
rather than something that self-scales across instruments.

## 11. Per-timeframe config profiles (`config/<TIMEFRAME>/`)

`run_pipeline.py` always reads `<config-dir>/pipeline_config.yaml` and
`<config-dir>/known_at_delay.yaml` by fixed filename, so the practical way
to support multiple timeframes is one self-contained config directory per
timeframe, selected via `--config-dir`:

```
config/M1/pipeline_config.yaml    config/M1/known_at_delay.yaml
config/M5/pipeline_config.yaml    config/M5/known_at_delay.yaml
config/M15/pipeline_config.yaml   config/M15/known_at_delay.yaml
config/M30/pipeline_config.yaml   config/M30/known_at_delay.yaml
config/H1/pipeline_config.yaml    config/H1/known_at_delay.yaml
config/H4/pipeline_config.yaml    config/H4/known_at_delay.yaml
config/D1/pipeline_config.yaml    config/D1/known_at_delay.yaml
```

```bash
python scripts/run_pipeline.py data/raw_csv/XAUUSD_M15_export.csv \
  --symbol XAUUSD --timeframe M15 --config-dir config/M15 --output-dir output
```

`known_at_delay.yaml` is identical across all profiles (it maps indicator
*column names* to availability delay in bars, which doesn't depend on
timeframe), so it's just copied unchanged into every profile directory.

`wf_train_bars` / `wf_test_bars` / `wf_step_bars` in each profile are
sized off an **assumed** typical exported bar count for that timeframe
(documented in a comment at the top of each file), scaled using the same
ratio validated on the real D1 XAUUSD smoke test in section 10
(train ~= 0.35N, test ~= 0.07N, step ~= 0.035N, where N is total bars).
This is a starting point, not a measurement of the user's actual file --
each profile's header comment says explicitly to check the real
`"Ingestion complete: N bars loaded"` line from Phase 1 and rescale if the
assumption is far off. The Phase 7 zero-window guard added in section 10
will still catch a bad guess and explain exactly what to change, so this
can't fail silently even if the assumption is wrong.

`min_occurrence` / `min_freq_per_year` are also scaled up for
faster/lower timeframes (more raw bars available -> a fixed absolute
occurrence count is a weaker filter), and `spread_pips` / `pip_value` in
every profile default to forex-major conventions -- override them
per-symbol as described in section 10 (e.g. XAUUSD) regardless of which
timeframe profile you're using, since spread is a symbol property, not a
timeframe property.

---

*This document should be updated whenever the gate criteria in Phase 7e
change, so the reasoning behind current thresholds stays discoverable.*
