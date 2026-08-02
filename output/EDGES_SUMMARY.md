# Edge Research Report
Generated: 2026-08-02T01:31:10.843954
Total edges: 17

## Summary Table
| edge_id      | hypothesis                                                |   horizon |   prob_bull |   effect_size |   frequency_per_year | robust_walk_forward   |   p_adjusted |
|:-------------|:----------------------------------------------------------|----------:|------------:|--------------:|---------------------:|:----------------------|-------------:|
| XAUUSD_D1_4  | Price rally after rsi_7 > 75.0                            |         1 |    0.538117 |    0.0187405  |              28.5674 | False                 |     1        |
| XAUUSD_D1_7  | Price rally after cci_14 < -100.0                         |         1 |    0.524781 |    0.00540531 |              42.8823 | False                 |     1        |
| XAUUSD_D1_3  | Price rally after rsi_7 < 35.0                            |         1 |    0.515896 |   -0.00348008 |              43.2574 | False                 |     1        |
| XAUUSD_D1_2  | Price rally after rsi_7 < 30.0                            |         1 |    0.509761 |   -0.00961465 |              28.8174 | False                 |     1        |
| XAUUSD_D1_10 | Price rally after stoch_5_3_3_k < 30.0 AND rsi_7 < 35.0   |         1 |    0.506422 |   -0.012954   |              34.0683 | False                 |     1        |
| XAUUSD_D1_6  | Price rally after rsi_14 < 35.0                           |         1 |    0.497126 |   -0.0222496  |              21.7537 | False                 |     1        |
| XAUUSD_D1_13 | Price rally after rsi_7 < 35.0 AND stoch_5_3_3_k < 20.0   |         1 |    0.494764 |   -0.0246117  |              23.8791 | False                 |     1        |
| XAUUSD_D1_17 | Price rally after rsi_14 < 35.0 AND stoch_14_3_3_k < 30.0 |         1 |    0.494118 |   -0.0252584  |              21.2536 | False                 |     1        |
| XAUUSD_D1_8  | Price rally after rsi_7 < 30.0 AND stoch_5_3_3_k < 30.0   |         1 |    0.489899 |   -0.0294771  |              24.7542 | False                 |     0.885361 |
| XAUUSD_D1_9  | Price rally after rsi_7 < 30.0 AND stoch_5_3_3_k < 20.0   |         1 |    0.489796 |   -0.0295801  |              18.3781 | False                 |     1        |
| XAUUSD_D1_1  | Price rally after rsi_7 < 25.0                            |         1 |    0.485185 |   -0.0341909  |              16.8779 | False                 |     0.899142 |
| XAUUSD_D1_5  | Price rally after rsi_14 < 30.0                           |         1 |    0.48     |   -0.0393761  |              10.9394 | False                 |     0.922788 |
| XAUUSD_D1_14 | Price rally after rsi_14 < 30.0 AND stoch_14_3_3_k < 30.0 |         1 |    0.48     |   -0.0393761  |              10.9394 | False                 |     0.922788 |
| XAUUSD_D1_12 | Price rally after stoch_5_3_3_k < 30.0 AND rsi_14 < 35.0  |         1 |    0.465909 |   -0.0534669  |              16.5028 | False                 |     0.529319 |
| XAUUSD_D1_11 | Price rally after stoch_5_3_3_k < 30.0 AND rsi_7 < 25.0   |         1 |    0.46473  |   -0.0546457  |              15.0651 | False                 |     0.563058 |
| XAUUSD_D1_15 | Price rally after stoch_5_3_3_k < 20.0 AND rsi_7 < 25.0   |         1 |    0.459596 |   -0.0597801  |              12.3771 | False                 |     0.459351 |
| XAUUSD_D1_16 | Price rally after stoch_5_3_3_k < 20.0 AND rsi_14 < 35.0  |         1 |    0.457895 |   -0.0614813  |              11.877  | False                 |     0.563136 |

## Detailed Edge Reports
### 1. XAUUSD_D1_1
**Hypothesis:** Price rally after rsi_7 < 25.0
**Entry Condition:** rsi_7 < 25.0
**Optimal Horizon:** 1 bars
**Frequency:** 16.9 per year
**Baseline Prob (Bull):** 55.03%

**At Optimal Horizon:**
- Prob (Bull): 48.52%
- Effect Size: -0.0342
- P-value (adj): 8.9914e-01
- CI: [42.26%, 54.09%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 305759.66
- Expectancy (R): 1.28

### 2. XAUUSD_D1_2
**Hypothesis:** Price rally after rsi_7 < 30.0
**Entry Condition:** rsi_7 < 30.0
**Optimal Horizon:** 1 bars
**Frequency:** 28.8 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 50.98%
- Effect Size: -0.0096
- P-value (adj): 1.0000e+00
- CI: [46.42%, 55.51%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 239763.89
- Expectancy (R): 1.00

### 3. XAUUSD_D1_3
**Hypothesis:** Price rally after rsi_7 < 35.0
**Entry Condition:** rsi_7 < 35.0
**Optimal Horizon:** 1 bars
**Frequency:** 43.3 per year
**Baseline Prob (Bull):** 55.40%

**At Optimal Horizon:**
- Prob (Bull): 51.59%
- Effect Size: -0.0035
- P-value (adj): 1.0000e+00
- CI: [47.87%, 55.29%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 185435.50
- Expectancy (R): 0.77

### 4. XAUUSD_D1_4
**Hypothesis:** Price rally after rsi_7 > 75.0
**Entry Condition:** rsi_7 > 75.0
**Optimal Horizon:** 1 bars
**Frequency:** 28.6 per year
**Baseline Prob (Bull):** 55.28%

**At Optimal Horizon:**
- Prob (Bull): 53.81%
- Effect Size: 0.0187
- P-value (adj): 1.0000e+00
- CI: [48.95%, 58.17%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 283388.19
- Expectancy (R): 1.18

### 5. XAUUSD_D1_5
**Hypothesis:** Price rally after rsi_14 < 30.0
**Entry Condition:** rsi_14 < 30.0
**Optimal Horizon:** 1 bars
**Frequency:** 10.9 per year
**Baseline Prob (Bull):** 55.40%

**At Optimal Horizon:**
- Prob (Bull): 48.00%
- Effect Size: -0.0394
- P-value (adj): 9.2279e-01
- CI: [40.17%, 54.80%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 269614.03
- Expectancy (R): 1.13

### 6. XAUUSD_D1_6
**Hypothesis:** Price rally after rsi_14 < 35.0
**Entry Condition:** rsi_14 < 35.0
**Optimal Horizon:** 1 bars
**Frequency:** 21.8 per year
**Baseline Prob (Bull):** 55.30%

**At Optimal Horizon:**
- Prob (Bull): 49.71%
- Effect Size: -0.0222
- P-value (adj): 1.0000e+00
- CI: [44.21%, 54.66%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 211034.83
- Expectancy (R): 0.88

### 7. XAUUSD_D1_7
**Hypothesis:** Price rally after cci_14 < -100.0
**Entry Condition:** cci_14 < -100.0
**Optimal Horizon:** 1 bars
**Frequency:** 42.9 per year
**Baseline Prob (Bull):** 55.40%

**At Optimal Horizon:**
- Prob (Bull): 52.48%
- Effect Size: 0.0054
- P-value (adj): 1.0000e+00
- CI: [48.74%, 56.19%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 165989.50
- Expectancy (R): 0.69

### 8. XAUUSD_D1_8
**Hypothesis:** Price rally after rsi_7 < 30.0 AND stoch_5_3_3_k < 30.0
**Entry Condition:** rsi_7 < 30.0 AND stoch_5_3_3_k < 30.0
**Optimal Horizon:** 1 bars
**Frequency:** 24.8 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 48.99%
- Effect Size: -0.0295
- P-value (adj): 8.8536e-01
- CI: [43.85%, 53.65%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 237504.14
- Expectancy (R): 0.99

### 9. XAUUSD_D1_9
**Hypothesis:** Price rally after rsi_7 < 30.0 AND stoch_5_3_3_k < 20.0
**Entry Condition:** rsi_7 < 30.0 AND stoch_5_3_3_k < 20.0
**Optimal Horizon:** 1 bars
**Frequency:** 18.4 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 48.98%
- Effect Size: -0.0296
- P-value (adj): 1.0000e+00
- CI: [43.32%, 54.67%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 248371.92
- Expectancy (R): 1.04

### 10. XAUUSD_D1_10
**Hypothesis:** Price rally after stoch_5_3_3_k < 30.0 AND rsi_7 < 35.0
**Entry Condition:** stoch_5_3_3_k < 30.0 AND rsi_7 < 35.0
**Optimal Horizon:** 1 bars
**Frequency:** 34.1 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 50.64%
- Effect Size: -0.0130
- P-value (adj): 1.0000e+00
- CI: [46.45%, 54.82%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 214108.72
- Expectancy (R): 0.89

### 11. XAUUSD_D1_11
**Hypothesis:** Price rally after stoch_5_3_3_k < 30.0 AND rsi_7 < 25.0
**Entry Condition:** stoch_5_3_3_k < 30.0 AND rsi_7 < 25.0
**Optimal Horizon:** 1 bars
**Frequency:** 15.1 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 46.47%
- Effect Size: -0.0546
- P-value (adj): 5.6306e-01
- CI: [40.28%, 52.78%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 306704.88
- Expectancy (R): 1.28

### 12. XAUUSD_D1_12
**Hypothesis:** Price rally after stoch_5_3_3_k < 30.0 AND rsi_14 < 35.0
**Entry Condition:** stoch_5_3_3_k < 30.0 AND rsi_14 < 35.0
**Optimal Horizon:** 1 bars
**Frequency:** 16.5 per year
**Baseline Prob (Bull):** 55.28%

**At Optimal Horizon:**
- Prob (Bull): 46.59%
- Effect Size: -0.0535
- P-value (adj): 5.2932e-01
- CI: [40.67%, 52.61%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 262120.55
- Expectancy (R): 1.10

### 13. XAUUSD_D1_13
**Hypothesis:** Price rally after rsi_7 < 35.0 AND stoch_5_3_3_k < 20.0
**Entry Condition:** rsi_7 < 35.0 AND stoch_5_3_3_k < 20.0
**Optimal Horizon:** 1 bars
**Frequency:** 23.9 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 49.48%
- Effect Size: -0.0246
- P-value (adj): 1.0000e+00
- CI: [44.23%, 54.21%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 216678.88
- Expectancy (R): 0.91

### 14. XAUUSD_D1_14
**Hypothesis:** Price rally after rsi_14 < 30.0 AND stoch_14_3_3_k < 30.0
**Entry Condition:** rsi_14 < 30.0 AND stoch_14_3_3_k < 30.0
**Optimal Horizon:** 1 bars
**Frequency:** 10.9 per year
**Baseline Prob (Bull):** 55.40%

**At Optimal Horizon:**
- Prob (Bull): 48.00%
- Effect Size: -0.0394
- P-value (adj): 9.2279e-01
- CI: [40.17%, 54.80%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 269614.03
- Expectancy (R): 1.13

### 15. XAUUSD_D1_15
**Hypothesis:** Price rally after stoch_5_3_3_k < 20.0 AND rsi_7 < 25.0
**Entry Condition:** stoch_5_3_3_k < 20.0 AND rsi_7 < 25.0
**Optimal Horizon:** 1 bars
**Frequency:** 12.4 per year
**Baseline Prob (Bull):** 55.03%

**At Optimal Horizon:**
- Prob (Bull): 45.96%
- Effect Size: -0.0598
- P-value (adj): 4.5935e-01
- CI: [38.67%, 52.41%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 308571.84
- Expectancy (R): 1.29

### 16. XAUUSD_D1_16
**Hypothesis:** Price rally after stoch_5_3_3_k < 20.0 AND rsi_14 < 35.0
**Entry Condition:** stoch_5_3_3_k < 20.0 AND rsi_14 < 35.0
**Optimal Horizon:** 1 bars
**Frequency:** 11.9 per year
**Baseline Prob (Bull):** 55.33%

**At Optimal Horizon:**
- Prob (Bull): 45.79%
- Effect Size: -0.0615
- P-value (adj): 5.6314e-01
- CI: [38.86%, 52.89%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 277100.88
- Expectancy (R): 1.16

### 17. XAUUSD_D1_17
**Hypothesis:** Price rally after rsi_14 < 35.0 AND stoch_14_3_3_k < 30.0
**Entry Condition:** rsi_14 < 35.0 AND stoch_14_3_3_k < 30.0
**Optimal Horizon:** 1 bars
**Frequency:** 21.3 per year
**Baseline Prob (Bull):** 55.40%

**At Optimal Horizon:**
- Prob (Bull): 49.41%
- Effect Size: -0.0253
- P-value (adj): 1.0000e+00
- CI: [44.13%, 54.70%]

**Robustness:**
- Walk-Forward Consistent: False
- Magnitude Std: nan
- Net Expectancy (pips): 231270.83
- Expectancy (R): 0.97

