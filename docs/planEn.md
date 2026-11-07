# Edge Discovery Pipeline — Full Project Specification

## Core Principles
1. **MQL5 is the source of truth.** All indicator values are computed and produced by MQL5, not replicated in Python. Python is purely a consumer of that data.
2. **No lookahead.** Every condition may only use information that is genuinely "known" at that bar (`known_at_bar`), including indicators that have a visual shift or require confirmation.
3. **No fixed lookahead.** Python computes the probability of market direction across ALL horizons (1..max_horizon), then finds on its own which horizon has a statistically significant edge.
4. **Overfitting is prevented through process, not data source.** Multiple-testing correction, walk-forward validation, and a holdout set are mandatory at every exploration stage.
5. **Conditions must be simple and boolean-mappable.** So they translate 1:1 into MQL5 `if()` statements — no black-box ML.

---

## Indicator List — Tier 1 (Initial Scope, Safe to Use)

| Indicator | MQL5 Function | Category | Suggested Parameter Variants |
|---|---|---|---|
| Moving Average | `iMA` | Immediate | period: 5,10,20,50,100,200; mode: SMA,EMA,SMMA,LWMA |
| Double EMA | `iDEMA` | Immediate | period: 10,20,50 |
| Triple EMA | `iTEMA` | Immediate | period: 10,20,50 |
| Fractal Adaptive MA | `iFrAMA` | Immediate | period: 14,20 |
| Adaptive MA (Kaufman) | `iAMA` | Immediate | period: 10; fast:2; slow:30 |
| Variable Index Dynamic Avg | `iVIDyA` | Immediate | period: 9,12 |
| Parabolic SAR | `iSAR` | Sequential-dependent | step:0.02; max:0.2 (+ variant step 0.01/0.03) |
| RSI | `iRSI` | Immediate | period: 7,14,21 |
| Stochastic Oscillator | `iStochastic` | Immediate | %K:5,%D:3,slowing:3 (+ variant 14/3/3) |
| CCI | `iCCI` | Immediate | period: 14,20 |
| Williams %R | `iWPR` | Immediate | period: 14 |
| Momentum | `iMomentum` | Immediate | period: 10,14 |
| MACD | `iMACD` | Immediate | 12/26/9 (standard) |
| MACD Histogram (OsMA) | `iOsMA` | Immediate | 12/26/9 |
| DeMarker | `iDeMarker` | Immediate | period: 14 |
| Relative Vigor Index | `iRVI` | Immediate | period: 10 |
| TriX | `iTriX` | Immediate | period: 14 |
| Accelerator Oscillator | `iAC` | Immediate | (no parameter) |
| Awesome Oscillator | `iAO` | Immediate | (no parameter) |
| Bears Power | `iBearsPower` | Immediate | period: 13 |
| Bulls Power | `iBullsPower` | Immediate | period: 13 |
| ATR | `iATR` | Immediate | period: 14,20 |
| Bollinger Bands | `iBands` | Immediate | period:20, dev:2.0 (+variant dev 1.5/2.5) |
| Standard Deviation | `iStdDev` | Immediate | period: 20 |
| Envelopes | `iEnvelopes` | Immediate | period:20, deviation:0.1% |
| ADX | `iADX` | Immediate | period: 14 |
| ADX Wilder | `iADXWilder` | Immediate | period: 14 |
| On Balance Volume | `iOBV` | Immediate (volume) | (no parameter) |
| Accumulation/Distribution | `iAD` | Immediate (volume) | (no parameter) |
| Money Flow Index | `iMFI` | Immediate (volume) | period: 14 |
| Force Index | `iForce` | Immediate (volume) | period: 13 |
| Chaikin Oscillator | `iChaikin` | Immediate (volume) | fast:3, slow:10 |
| Volumes (tick volume) | `iVolumes` | Immediate (volume) | (no parameter) |

**Total Tier 1: 32 indicators** (including parameter variants, this yields hundreds of feature columns).

## Indicator List — Tier 2 (Deferred, Requires Special Handling)

| Indicator | Reason for Deferral |
|---|---|
| `iIchimoku` | 26-bar visual shift (Senkou), needs explicit realignment |
| `iAlligator` | 3/5/8-bar visual shift |
| `iGator` | Derived from Alligator, inherits the same issue |
| `iFractals` | Needs a 2-bar confirmation delay |
| `iBWMFI` | Needs additional 4-condition qualitative interpretation |

Revisit Tier 2 only after Tier 1 has produced solid, validated edge candidates.

---

## PHASE 0 — MQL5 Data Exporter (Ground Truth Generator)

**Goal:** a single MQL5 script (not a trading EA) that runs in the Strategy Tester, loops through the entire history, computes all Tier 1 indicators, and writes them to CSV.

### Technical Specification
- **Testing model:** "Open prices only" — sufficient to pull per-bar indicator values, and much faster than "Every tick".
- **Indicator handle batching:** split into groups (e.g., Trend/MA group, Oscillator group, Volatility group, Volume group) to avoid exceeding MT5's handle limit. Call `IndicatorRelease()` after each group is finished before moving to the next.
- **Always evaluate on the closed bar** — use index `[1]` relative to the running bar, never `[0]`.
- **Streaming write** — write CSV row by row (append), do not accumulate large arrays in the EA's memory first.
- **Run per symbol + per timeframe** — results are stored permanently, not repeated for every research session.

### CSV Column Schema
```
time, open, high, low, close, tick_volume,
ma_20_sma, ma_50_sma, ma_20_ema, ..., 
rsi_14, rsi_7, ...
stoch_k_5_3_3, stoch_d_5_3_3, ...
atr_14, bb_upper_20_2, bb_lower_20_2, bb_mid_20_2, ...
adx_14, adx_wilder_14, ...
obv, ad, mfi_14, force_13, chaikin_3_10, volume, ...
sar_002_02, ...
```
All immediate/sequential-dependent columns can be written as-is (`known_at_bar = t`). No Tier 2 columns at this phase.

### Sanity Check
After export, verify row count matches the historical bar count (no missing bars), and check there's no excessive NaN beyond the expected indicator warm-up period at the start of the data.

---

## PHASE 1 — Python: Ingestion & Layer 1 Cache (Indicator Value Layer)

**RAM optimization at this point:**
- Load the CSV once, convert all numeric columns to `float32` (instead of pandas' default `float64`) — saves ~50% RAM.
- The `time` column is stored as `int64` (unix timestamp) or `datetime64[ns]` set as the index, not as a string.
- Store the result as **Parquet** with compression (`snappy` or `zstd`), partitioned per symbol+timeframe — not CSV for reuse, since parquet is far faster to read and smaller on disk.
- **This is computed/converted once.** All subsequent phases only read from this parquet, never re-parsing the CSV.

```
storage/
  EURUSD_H1.parquet
  EURUSD_M15.parquet
  GBPUSD_H1.parquet
```

---

## PHASE 2 — Known-At Tagging (Delay Layer)

For the entirety of Tier 1, almost all have `known_at_bar = t` (usable immediately). The `sar_*` columns still get `known_at_bar = t` because, despite being sequential-dependent, their value is still purely derived from data up to bar `t`.

Store this mapping as a small config file (dict/YAML), not hardcoded in the logic — so that if Tier 2 is added later, only this mapping needs updating, not the core code:

```yaml
known_at_delay:
  default: 0
  # example for future Tier 2:
  # fractal_up: 2
  # fractal_down: 2
```

---

## PHASE 3 — Condition Layer (Generate Condition Candidates)

1. **Atomic conditions**: simple comparisons per indicator, e.g. `rsi_14 < 30`, `close < bb_lower_20_2`, `ma_20_ema > ma_50_ema` (crossover state).
2. **Combined conditions**: AND across 2-3 atomic conditions from different indicators (avoid combining highly correlated indicators, e.g. RSI_7 AND RSI_14, since that isn't genuine signal diversification).
3. **RAM optimization:** conditions are stored as a **boolean mask** (`numpy bool_` array, 1 byte per element) or **bit-packed** (`numpy.packbits`, 1 bit per element) if the number of condition candidates is very large. They are not stored as permanent columns in the parquet — computed on-the-fly from Layer 1 when needed, since recomputation is cheap (elementwise comparison).
4. Conditions are processed batch by batch (e.g., per indicator group), not by generating all thousands of combinations at once in a single in-memory list.

---

## PHASE 4 — Frequency Pre-Filter (Cheap, Before Heavy Processing)

For each candidate condition, compute:
- `n_occurrence` = total occurrences of the condition being True.
- `freq_per_year` = occurrence divided by the data's year range.

Filter:
```python
MIN_OCCURRENCE = 200        # adjust to data length
MIN_FREQ_PER_YEAR = 30      # minimum ~30x/year to be actionable
```

Conditions that don't pass are discarded here — **before** entering the far more computationally expensive forward probability profiling. This is the single largest point of RAM and time savings in the entire pipeline.

---

## PHASE 5 — Forward Probability Profiling (Core Research)

### RAM Control Concept
The largest structure in the entire pipeline is the **forward return matrix**: `n_bars × max_horizon`. This is computed **once** for the entire dataset (not per condition), then reused by all conditions.

```python
MAX_HORIZON = 100   # hard ceiling, adjust to available RAM

# forward_direction[i, h] = True if close[i+h] > close[i]
# dtype bool -> 1 byte, for 500,000 bars x 100 horizons = 50 MB only
```

RAM estimate: `n_bars × max_horizon × 1 byte` (bool dtype). For 10 years of H1 data (~87,600 bars) with `max_horizon=100`: ±8.7 MB. Very manageable. If you want multiple timeframes/symbols at once, process **one file at a time**, flush results to disk, then move to the next file — don't load all symbols into RAM simultaneously.

### Correct Entry Point (Anti-Lookahead)
Entry is considered to occur at the **next bar's open** after the condition is confirmed (bar `t+1` open), not at the close of the signal bar (bar `t`). Forward return is computed from this entry point, not from `close[t]`.

### Computation per Condition
For each condition that passed Phase 4:
```python
idx_true = np.where(condition_mask)[0]
idx_true = idx_true[idx_true < n - MAX_HORIZON]  # discard those too close to data end

for h in range(1, MAX_HORIZON + 1):
    entry_price = open_[idx_true + 1]          # next bar's open
    future_price = close[idx_true + 1 + h]
    is_bull = future_price > entry_price
    prob = is_bull.mean()
    n = len(idx_true)
    ci_low, ci_high = wilson_ci(is_bull.sum(), n)
```
Output is stored as one summary row per (condition, horizon) — not the raw arrays permanently. Once the probability is computed, intermediate arrays can be immediately discarded (`del`, garbage collected) before moving to the next condition.

---

## PHASE 6 — Statistical Testing & Multiple-Testing Correction

1. **Baseline**: compute the unconditional `P(bull)` at the same horizons (from the entire dataset, without any condition) as a comparison point.
2. **Proportion z-test** for each horizon vs. baseline.
3. **Benjamini-Hochberg (FDR) correction** — because a single condition is tested across many horizons at once (up to 100 tests), and many conditions are tested at once (potentially hundreds of candidates). Correction must be applied at **both levels**, not just one.
4. Keep only the horizons that pass `p_adj < alpha` as significant candidates.

---

## PHASE 7 — Robustness & Validation

| Test | Purpose |
|---|---|
| **Walk-forward** (rolling train/test window) | Verify the edge is stable over time, not just within one window |
| **Regime breakdown** (trending/ranging/high-vol/low-vol) | Verify the edge doesn't only work in one type of market condition |
| **Parameter sensitivity** (shift threshold/period ±10-20%) | If the edge drops drastically, that's a sign of overfitting to a specific number |
| **Cost model** (realistic spread + slippage) | Verify expectancy stays positive net of costs |
| **Final holdout** (data untouched throughout Phases 3-7) | Final confirmation, used only once |

---

## PHASE 8 — Edge Report (Final Output, Structured Format)

YAML/JSON format per candidate edge that passes all phases:

```yaml
edge_id: rsi14_below30_bb_lower_v1
hypothesis: "RSI(14)<30 AND Close<BB_lower(20,2) tends toward a bullish reversal"
entry_condition:
  - indicator: rsi_14
    operator: "<"
    value: 30
  - indicator: bb_lower_20_2
    operator: "close_below"
frequency:
  n_occurrence: 2150
  freq_per_year: 65.3
optimal_horizon: 4
statistics:
  horizon_4:
    prob_bull: 0.596
    ci_95: [0.575, 0.617]
    baseline_prob: 0.503
    p_adj: 0.0008
robustness:
  walk_forward_stability: "consistent 4/5 windows"
  regime_breakdown:
    trending: {prob_bull: 0.61, n: 1100}
    ranging: {prob_bull: 0.58, n: 1050}
  parameter_sensitivity: "stable across period 12-16"
  cost_adjusted_expectancy_R: 0.28
validated_period: "2015-01 to 2023-12"
holdout_result:
  prob_bull: 0.583
  n: 210
mql5_mapping:
  entry: "rsi[1] < 30 && close[1] < bb_lower[1]"
  exit_type: fixed_bar
  exit_bars: 4
  magic_number: null   # filled in manually when generating the EA
```

---

## PHASE 9 — MQL5 Code Generation

1. Parser reads `edge_report.yaml` → fills in the `.mq5` template following the existing pattern (virtual SL/TP, independent magic number, CSV logging).
2. Default exit logic: fixed bar count from `optimal_horizon`, optionally combined with virtual TP/SL derived from the return distribution at that horizon.
3. **Mandatory sanity check**: run the generated EA in the Strategy Tester over the same period, and compare trade count and rough win rate against the numbers in the edge report. A large mismatch indicates a conversion bug.

---

## Final Folder Structure

```
edge_research/
├── mql5_exporter/
│   └── DataExporter.mq5          # Phase 0
├── data/
│   ├── raw_csv/                  # exporter output
│   └── storage/                  # Phase 1: parquet, float32
├── config/
│   └── known_at_delay.yaml       # Phase 2
├── conditions/
│   ├── condition_library.py      # Phase 3
│   └── frequency_filter.py       # Phase 4
├── forward_profile/
│   ├── engine.py                 # Phase 5
│   └── significance.py           # Phase 6
├── validation/
│   ├── walk_forward.py
│   ├── regime_stress_test.py
│   ├── parameter_sensitivity.py
│   └── cost_model.py             # Phase 7
├── reporting/
│   ├── edge_report_schema.py
│   └── report_generator.py       # Phase 8
└── mql5_codegen/
    ├── templates/
    └── generator.py              # Phase 9
```

---

## RAM Budget Summary

| Layer | Structure | Size (estimate, 10 years H1 data) |
|---|---|---|
| Layer 1 — Indicator cache | parquet, float32, all columns | Tens-to-hundreds of MB on disk, read partially as needed |
| Layer 2 — Condition mask | bool array per condition, on-the-fly | ~87 KB per condition (87,600 bars × 1 byte) |
| Layer 3 — Forward return matrix | bool, computed once, reused | ~8.7 MB (`n_bars × max_horizon`) |

The most important RAM control points: **`MAX_HORIZON`** (hard ceiling on Layer 3) and **batch processing per symbol/timeframe** (never loading everything into memory at once).