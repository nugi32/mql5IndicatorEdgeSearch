# Edge Research Report
Generated: 2026-09-05T07:59:24.009241
Total edges: 10

## Summary Table
| edge_id      | hypothesis                                                            |   horizon |   prob_bull |   effect_size |   frequency_per_year | robust_walk_forward   |   p_adjusted |
|:-------------|:----------------------------------------------------------------------|----------:|------------:|--------------:|---------------------:|:----------------------|-------------:|
| EURUSD_H1_1  | Price rally after rsi_7 > 70.0                                        |         1 |    0.463542 |    -0.0371426 |              798.875 | True                  |  0           |
| EURUSD_H1_3  | Price rally after rsi_7 > 80.0                                        |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_7  | Price rally after rsi_7 > 80.0 AND mom_10 > 5.0                       |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_4  | Price rally after rsi_7 > 80.0 AND ma_5_ema < close                   |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_5  | Price rally after rsi_7 > 80.0 AND mom_10 > -5.0                      |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_6  | Price rally after rsi_7 > 80.0 AND mom_10 > 0.0                       |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_9  | Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 0.0  |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_8  | Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > -5.0 |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_10 | Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 5.0  |         1 |    0.460537 |    -0.0401483 |              235.188 | True                  |  5.12631e-06 |
| EURUSD_H1_2  | Price rally after rsi_7 > 75.0                                        |         1 |    0.460244 |    -0.0404409 |              460.625 | True                  |  7.20972e-11 |

## Detailed Edge Reports
### 1. EURUSD_H1_1
**Hypothesis:** Price rally after rsi_7 > 70.0
**Entry Condition:** rsi_7 > 70.0
**Optimal Horizon:** 1 bars
**Frequency:** 798.9 per year
**Baseline Prob (Bull):** 49.95%

**At Optimal Horizon:**
- Prob (Bull): 46.35%
- Effect Size: -0.0371
- P-value (adj): 0.0000e+00
- CI: [45.49%, 47.22%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0473
- Net Expectancy (pips): 0.66
- Expectancy (R): 0.04

### 2. EURUSD_H1_2
**Hypothesis:** Price rally after rsi_7 > 75.0
**Entry Condition:** rsi_7 > 75.0
**Optimal Horizon:** 1 bars
**Frequency:** 460.6 per year
**Baseline Prob (Bull):** 49.95%

**At Optimal Horizon:**
- Prob (Bull): 46.02%
- Effect Size: -0.0404
- P-value (adj): 7.2097e-11
- CI: [44.89%, 47.16%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0512
- Net Expectancy (pips): 0.75
- Expectancy (R): 0.04

### 3. EURUSD_H1_3
**Hypothesis:** Price rally after rsi_7 > 80.0
**Entry Condition:** rsi_7 > 80.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 4. EURUSD_H1_4
**Hypothesis:** Price rally after rsi_7 > 80.0 AND ma_5_ema < close
**Entry Condition:** rsi_7 > 80.0 AND ma_5_ema < close
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 5. EURUSD_H1_5
**Hypothesis:** Price rally after rsi_7 > 80.0 AND mom_10 > -5.0
**Entry Condition:** rsi_7 > 80.0 AND mom_10 > -5.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 6. EURUSD_H1_6
**Hypothesis:** Price rally after rsi_7 > 80.0 AND mom_10 > 0.0
**Entry Condition:** rsi_7 > 80.0 AND mom_10 > 0.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 7. EURUSD_H1_7
**Hypothesis:** Price rally after rsi_7 > 80.0 AND mom_10 > 5.0
**Entry Condition:** rsi_7 > 80.0 AND mom_10 > 5.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 8. EURUSD_H1_8
**Hypothesis:** Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > -5.0
**Entry Condition:** rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > -5.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 9. EURUSD_H1_9
**Hypothesis:** Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 0.0
**Entry Condition:** rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 0.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

### 10. EURUSD_H1_10
**Hypothesis:** Price rally after rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 5.0
**Entry Condition:** rsi_7 > 80.0 AND ma_5_ema < close AND mom_10 > 5.0
**Optimal Horizon:** 1 bars
**Frequency:** 235.2 per year
**Baseline Prob (Bull):** 50.07%

**At Optimal Horizon:**
- Prob (Bull): 46.05%
- Effect Size: -0.0401
- P-value (adj): 5.1263e-06
- CI: [44.47%, 47.65%]

**Robustness:**
- Walk-Forward Consistent: True
- Magnitude Std: 0.0608
- Net Expectancy (pips): 1.36
- Expectancy (R): 0.08

