# Configuration Guide

Configuration is YAML-based. Select a profile that matches the symbol and data length before running the pipeline; do not assume one profile is suitable for every instrument or timeframe.

## Configuration files

Each pipeline `--config-dir` is expected to contain both:

- `pipeline_config.yaml`: thresholds, statistical options, validation windows, simulation costs, and optional walk-forward settings.
- `known_at_delay.yaml`: column-pattern availability delays.

The repository includes these profile families:

| Path | Intended use |
|---|---|
| `config/<SYMBOL>/<TIMEFRAME>/` | Single-dataset run profile for the matching symbol/timeframe |
| `config/SHORT_DATA/<SYMBOL>/<TIMEFRAME>/` | Shorter history, with inner windows and minimum counts sized for less data |
| `config/WALKFORWARD/<SYMBOL>/<TIMEFRAME>/` | Outer rolling walk-forward run; defines either calendar or bar-count windows |
| `config/MT5_TESTER/<SYMBOL>/<TIMEFRAME>.yaml` | Execution assumptions for MT5-style simulation and backtests; loaded separately |
| `config/_legacy/` | Archived layouts; not recommended for new runs |

Some profiles exist only for particular symbols or timeframes. Check the directory before copying a command. The repository-root `config/pipeline_config.yaml` has instrument-specific assumptions; prefer an explicit symbol/timeframe profile.

## Important profile-selection rules

1. Use a matching symbol and timeframe folder.
2. For `SHORT_DATA`, verify that the CSV length is within the profile's stated intended range in the YAML comments.
3. For an outer walk-forward run, use a profile containing `meta_wf_runs` or `meta_wf_train_bars`. The script requires one of these.
4. Check `wf_train_bars`, `wf_test_bars`, and `wf_step_bars` against the data actually loaded. If no inner windows fit, the robustness gate may reject all conditions.
5. Recheck all cost values when changing instruments. Currency-pair pip conventions do not automatically apply to metals or other CFDs.

## Key `pipeline_config.yaml` settings

| Group | Common keys | Effect |
|---|---|---|
| Forward scan | `min_horizon`, `max_horizon` | Horizons used to compute forward direction outcomes |
| Candidate frequency | `min_occurrence`, `min_freq_per_year` | Minimum condition trigger counts/rates |
| Statistical tests | `alpha`, `fdr_method` | Significance threshold and multiple-testing correction |
| Candidate generation | `rsi_thresholds`, `cci_thresholds`, `mom_thresholds`, `stoch_thresholds`, `include_ma_conditions` | Atomic condition families and thresholds |
| Combination search | `top_n_atomic_for_combine`, `max_corr_combine`, `max_atoms_per_combo` | Pool size, redundancy cutoff, and combination size |
| Inner walk-forward | `wf_train_bars`, `wf_test_bars`, `wf_step_bars` | Rolling validation window sizes, expressed in bars |
| Regime checks | `atr_percentile_low`, `atr_percentile_high`, `adx_trending_threshold`, `adx_ranging_threshold` | Regime classifications |
| Sensitivity | `param_shift_pct` | Numeric threshold perturbation percentage |
| Holdout | `holdout_pct` | Chronological fraction reserved for holdout reporting |
| Directional cost model | `spread_pips`, `slippage_pips`, `pip_value`, optional `spread_atr_mult`, `session_spread_multipliers` | Cost assumptions for prefilter/simulation |
| Holding-period scan | `horizon_scan_min_bars`, `horizon_scan_max_bars`, `horizon_min_stable_windows` | Candidate trade durations and their stability requirement |
| Permutation test | `permutation_n`, optional `permutation_random_state` | Number of rotations and optional reproducibility seed |
| Gate | `gate_min_sim_trades`, `gate_min_profit_factor`, `gate_require_walk_forward`, `gate_require_permutation`, `gate_require_positive_ci_lower` | Promotion criteria |
| Bootstrap | `sim_bootstrap_n`, `sim_bootstrap_ci`, optional `sim_bootstrap_random_state` | Optional confidence interval for expectancy |
| Calendar features | `calendar_*` | Importance thresholds, currencies, coverage, and feature parameters |
| Ranker | `ranker_*` | Ranking thresholds, list size, duplicate handling, and optional floor filtering |

The full source of truth for available keys and their profile-specific values is each YAML file. Comments in shipped profiles may include instrument-specific calibration guidance.

## Cost units

For the basic research cost model, `spread_pips * pip_value` and `slippage_pips * pip_value` are converted into price units. Confirm that these products match the symbol's quoting convention and intended cost interpretation. An incorrect `pip_value` can materially distort expectancy without causing an error.

Optional `spread_atr_mult` replaces the fixed spread estimate with a value scaled by entry ATR. Optional `session_spread_multipliers` further scales costs by the timestamp hour in broker/server time. These assumptions should be based on relevant broker data, not treated as universal defaults.

The MT5 tester emulation uses its own `config/MT5_TESTER/<SYMBOL>/<TIMEFRAME>.yaml` settings, including `point`, `digits`, `contract_size`, `spread_points`, commission, swaps, and position limits. The checked-in tester profiles currently cover XAUUSD and EURUSD. A per-bar spread export can override the fixed spread for the backtest.

## Walk-forward profile keys

The outer runner selects its mode from `pipeline_config.yaml`:

- `meta_wf_runs`: calendar-year run specifications.
- `meta_wf_train_bars`, `meta_wf_test_bars`, `meta_wf_step_bars`: fixed-row windows for shorter histories.

Additional `meta_wf_*` settings control candidate plateau filtering and test-period acceptance. In calendar mode the full inner pipeline configuration must also be sized for each training slice, not for the entire CSV.

## Recommended review before a run

- Confirm the selected profile's symbol/timeframe and intended data size.
- Confirm the CSV timestamps, bar count, and indicator columns.
- Verify that spread and slippage convert to realistic price units for the symbol.
- Confirm that inner and outer windows fit and produce the intended number of tests.
- Save the exact config and data used for every result. Resume fingerprints prevent resuming with changed inputs, but they do not prove that the assumptions are correct.
