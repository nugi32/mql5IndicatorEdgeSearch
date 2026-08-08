─   mnt   mql5IndicatorsEdge   multipleCondition ≡  ~3 -10  17ms                                                              bash  27.27%   mql5IndicatorsEdge 3.14.4 09:33:22
╰─ python scripts/run_pipeline.py \
  data/raw_csv/XAUUSD_M1_export_20100101.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config \
  --output-dir output
2026-08-05 09:33:33,038 [INFO] __main__: ================================================================================
2026-08-05 09:33:33,039 [INFO] __main__: EDGE RESEARCH PIPELINE START
2026-08-05 09:33:33,039 [INFO] __main__: ================================================================================
2026-08-05 09:33:33,039 [INFO] __main__: 
[PHASE 1] Ingestion & Storage...
2026-08-05 09:33:33,039 [INFO] edge_research.ingestion.loader: Loading CSV from data/raw_csv/XAUUSD_M1_export_20100101.csv
2026-08-05 09:34:51,264 [WARNING] edge_research.ingestion.loader: Could not parse time with standard formats, using pandas auto-detect
2026-08-05 09:34:52,686 [INFO] edge_research.ingestion.loader: Loaded 5527535 rows, date range: 2009-12-31 18:59:00 to 2025-12-31 23:57:00
2026-08-05 09:34:53,939 [WARNING] edge_research.ingestion.loader: Found NaN values:
envelope_20_01_lower    5527535
dtype: int64
2026-08-05 09:34:53,939 [INFO] edge_research.ingestion.loader: Converted 88 numeric columns to float32
2026-08-05 09:34:53,940 [INFO] edge_research.ingestion.loader: Writing Parquet to output/storage/XAUUSD_M1.parquet (compression=zstd)
2026-08-05 09:35:28,151 [INFO] edge_research.ingestion.loader: Successfully wrote 5527535 rows to output/storage/XAUUSD_M1.parquet
2026-08-05 09:35:28,152 [INFO] __main__: ✓ Ingestion complete: 5527535 bars loaded
2026-08-05 09:35:28,152 [INFO] __main__: 
[PHASE 2] Known-At Tagging...
2026-08-05 09:35:28,152 [INFO] edge_research.known_at.tagging: Loading known-at config from config/known_at_delay.yaml
2026-08-05 09:35:28,157 [INFO] edge_research.known_at.tagging: Loaded 39 known-at rules
2026-08-05 09:35:28,157 [INFO] __main__: ✓ Known-at tagger initialized
2026-08-05 09:35:28,157 [INFO] __main__: 
[PHASE 3] Condition Generation...
2026-08-05 09:35:28,158 [INFO] __main__:   Generated 128 atomic conditions
2026-08-05 09:35:29,205 [INFO] __main__:   128 / 128 atomic conditions passed frequency filter
2026-08-05 09:35:31,868 [INFO] __main__:   Selected top 15 atomic conditions (by 1-bar effect size) for pairwise combination
2026-08-05 09:35:31,868 [WARNING] __main__:   max_atoms_per_combo=5 but only 1 distinct indicator families are present in the top pool (['rsi']). Combos larger than 1 atoms are impossible (each atom must be from a different family) and will simply be skipped. Add more indicator families (e.g. set include_ma_conditions: true) or lower max_atoms_per_combo.
2026-08-05 09:35:31,869 [INFO] __main__:   2-atom combos: 0 generated (from 15 pooled atomic conditions)
2026-08-05 09:35:31,869 [INFO] __main__:   3-atom combos: 0 generated (from 15 pooled atomic conditions)
2026-08-05 09:35:31,870 [INFO] __main__:   4-atom combos: 0 generated (from 15 pooled atomic conditions)
2026-08-05 09:35:31,872 [INFO] __main__:   5-atom combos: 0 generated (from 15 pooled atomic conditions)
2026-08-05 09:35:31,872 [INFO] __main__:   Generated 0 combined conditions total
2026-08-05 09:35:31,872 [INFO] __main__: ✓ Total candidates: 128 (128 atomic + 0 combined)
2026-08-05 09:35:31,873 [INFO] __main__: 
[PHASE 4] Frequency Pre-Filter...
2026-08-05 09:35:32,424 [INFO] __main__: ✓ Frequency filter: 128 / 128 passed
2026-08-05 09:35:32,425 [INFO] __main__: 
[PHASE 5-6] Forward Profile & Significance Testing...
2026-08-05 09:35:32,425 [INFO] edge_research.forward_profile.engine: Precomputing forward matrix (horizon=20)...
2026-08-05 09:35:35,029 [INFO] edge_research.forward_profile.engine: Forward matrix computed: shape (5527535, 20)
2026-08-05 09:35:35,029 [INFO] edge_research.forward_profile.engine: Computing baseline forward profile...
2026-08-05 09:35:35,644 [INFO] edge_research.forward_profile.engine: Baseline profile computed: [0.47873557 0.48854485 0.4919945  0.49415407 0.49548557 0.49649978
 0.49760896 0.49821284 0.49869192 0.4991885  0.4994302  0.49973577
 0.5000636  0.50038487 0.5006579  0.50080353 0.5010888  0.5014063
 0.5015858  0.50176746]
2026-08-05 09:36:15,147 [INFO] edge_research.forward_profile.significance: Testing 128 conditions with FDR correction...
2026-08-05 09:36:16,462 [INFO] edge_research.forward_profile.significance: Testing complete: 117 conditions passed significance
2026-08-05 09:36:16,462 [INFO] __main__: ✓ Significance testing: 117 conditions passed
2026-08-05 09:36:16,462 [INFO] __main__: 
[PHASE 7] Robustness Validation...
2026-08-05 09:36:16,464 [INFO] edge_research.validation.walk_forward: Generated 11044 walk-forward windows
2026-08-05 09:36:16,566 [INFO] edge_research.validation.regime_stress_test: Regime classification: trending=3380124, high_vol=1381563

2026-08-05 13:14:47,738 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_sma > close
2026-08-05 13:17:58,757 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_sma < close
2026-08-05 13:21:16,510 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_ema > close
2026-08-05 13:24:41,158 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_ema < close
2026-08-05 13:28:08,156 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_smma > close
2026-08-05 13:31:28,254 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_smma < close
2026-08-05 13:34:39,934 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_lwma > close
2026-08-05 13:37:49,502 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_5_lwma < close
2026-08-05 13:40:59,978 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_sma > close
2026-08-05 13:44:11,683 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_sma < close
2026-08-05 13:47:29,482 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_ema > close
2026-08-05 13:50:40,113 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_ema < close
2026-08-05 13:53:49,013 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_smma > close
2026-08-05 13:56:59,659 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_smma < close
2026-08-05 14:00:12,298 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_lwma > close
2026-08-05 14:03:23,200 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_10_lwma < close
2026-08-05 14:06:38,955 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_sma > close
2026-08-05 14:09:50,432 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_sma < close
2026-08-05 14:13:00,498 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_ema > close
2026-08-05 14:16:07,973 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_ema < close
2026-08-05 14:19:23,852 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_smma > close
2026-08-05 14:22:32,872 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_smma < close
2026-08-05 14:25:42,569 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_lwma > close
2026-08-05 14:28:49,976 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_20_lwma < close
2026-08-05 14:32:00,344 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_sma > close
2026-08-05 14:35:07,050 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_sma < close
2026-08-05 14:38:21,977 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_ema > close
2026-08-05 14:41:29,196 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_ema < close
2026-08-05 14:44:44,164 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_smma > close
2026-08-05 14:48:00,077 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_smma < close
2026-08-05 14:51:19,007 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_lwma > close
2026-08-05 14:54:22,531 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_50_lwma < close
2026-08-05 14:57:30,788 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_sma > close
2026-08-05 15:00:40,088 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_sma < close
2026-08-05 15:04:08,430 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_ema > close
2026-08-05 15:07:32,595 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_ema < close
2026-08-05 15:11:02,704 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_smma > close
2026-08-05 15:14:25,161 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_smma < close
2026-08-05 15:18:00,211 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_lwma > close
2026-08-05 15:21:26,321 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_100_lwma < close
2026-08-05 15:24:59,727 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_sma > close
2026-08-05 15:28:25,811 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_sma < close
2026-08-05 15:31:57,119 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_ema > close
2026-08-05 15:35:18,005 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_ema < close
2026-08-05 15:38:51,761 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_smma > close
2026-08-05 15:42:14,543 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_smma < close
2026-08-05 15:45:49,080 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_lwma > close
2026-08-05 15:49:10,955 [WARNING] edge_research.validation.parameter_sensitivity: Could not extract numeric parameter from ma_200_lwma < close
2026-08-05 15:52:39,379 [INFO] __main__: ✓ Robustness validation: 117 edges validated
2026-08-05 15:52:39,380 [INFO] __main__: 
[PHASE 7b] Holdout Set Testing...
2026-08-05 15:52:39,788 [INFO] __main__: 
[PHASE 8] Report Generation...
2026-08-05 15:52:40,008 [INFO] __main__: ✓ Generated 117 edge reports
2026-08-05 16:06:56,832 [INFO] edge_research.reporting.report_generator: Markdown report saved to output/EDGES_SUMMARY.md
2026-08-05 16:06:56,832 [INFO] __main__: ✓ Summary Markdown: output/EDGES_SUMMARY.md
2026-08-05 16:06:56,832 [INFO] __main__: 
[PHASE 9] MQL5 Code Generation...
2026-08-05 16:06:56,833 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_1.mq5
2026-08-05 16:06:56,833 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_2.mq5
2026-08-05 16:06:56,833 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_3.mq5
2026-08-05 16:06:56,834 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_4.mq5
2026-08-05 16:06:56,834 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_5.mq5
2026-08-05 16:06:56,834 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_6.mq5
2026-08-05 16:06:56,835 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_7.mq5
2026-08-05 16:06:56,835 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_8.mq5
2026-08-05 16:06:56,835 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_9.mq5
2026-08-05 16:06:56,835 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_10.mq5
2026-08-05 16:06:56,836 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_11.mq5
2026-08-05 16:06:56,836 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_12.mq5
2026-08-05 16:06:56,836 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_13.mq5
2026-08-05 16:06:56,836 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_14.mq5
2026-08-05 16:06:56,837 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_15.mq5
2026-08-05 16:06:56,837 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_16.mq5
2026-08-05 16:06:56,837 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_17.mq5
2026-08-05 16:06:56,838 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_18.mq5
2026-08-05 16:06:56,838 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_19.mq5
2026-08-05 16:06:56,838 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_20.mq5
2026-08-05 16:06:56,839 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_21.mq5
2026-08-05 16:06:56,839 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_22.mq5
2026-08-05 16:06:56,840 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_23.mq5
2026-08-05 16:06:56,840 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_24.mq5
2026-08-05 16:06:56,841 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_25.mq5
2026-08-05 16:06:56,841 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_26.mq5
2026-08-05 16:06:56,841 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_27.mq5
2026-08-05 16:06:56,842 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_28.mq5
2026-08-05 16:06:56,842 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_29.mq5
2026-08-05 16:06:56,842 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_30.mq5
2026-08-05 16:06:56,843 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_31.mq5
2026-08-05 16:06:56,843 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_32.mq5
2026-08-05 16:06:56,844 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_33.mq5
2026-08-05 16:06:56,844 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_34.mq5
2026-08-05 16:06:56,844 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_35.mq5
2026-08-05 16:06:56,845 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_36.mq5
2026-08-05 16:06:56,845 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_37.mq5
2026-08-05 16:06:56,845 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_38.mq5
2026-08-05 16:06:56,845 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_39.mq5
2026-08-05 16:06:56,846 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_40.mq5
2026-08-05 16:06:56,846 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_41.mq5
2026-08-05 16:06:56,846 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_42.mq5
2026-08-05 16:06:56,847 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_43.mq5
2026-08-05 16:06:56,847 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_44.mq5
2026-08-05 16:06:56,847 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_45.mq5
2026-08-05 16:06:56,848 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_46.mq5
2026-08-05 16:06:56,848 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_47.mq5
2026-08-05 16:06:56,848 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_48.mq5
2026-08-05 16:06:56,849 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_49.mq5
2026-08-05 16:06:56,849 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_50.mq5
2026-08-05 16:06:56,849 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_51.mq5
2026-08-05 16:06:56,850 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_52.mq5
2026-08-05 16:06:56,850 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_53.mq5
2026-08-05 16:06:56,850 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_54.mq5
2026-08-05 16:06:56,850 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_55.mq5
2026-08-05 16:06:56,851 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_56.mq5
2026-08-05 16:06:56,851 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_57.mq5
2026-08-05 16:06:56,851 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_58.mq5
2026-08-05 16:06:56,851 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_59.mq5
2026-08-05 16:06:56,852 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_60.mq5
2026-08-05 16:06:56,852 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_61.mq5
2026-08-05 16:06:56,852 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_62.mq5
2026-08-05 16:06:56,852 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_63.mq5
2026-08-05 16:06:56,853 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_64.mq5
2026-08-05 16:06:56,853 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_65.mq5
2026-08-05 16:06:56,853 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_66.mq5
2026-08-05 16:06:56,853 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_67.mq5
2026-08-05 16:06:56,854 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_68.mq5
2026-08-05 16:06:56,854 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_69.mq5
2026-08-05 16:06:56,854 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_70.mq5
2026-08-05 16:06:56,854 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_71.mq5
2026-08-05 16:06:56,855 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_72.mq5
2026-08-05 16:06:56,855 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_73.mq5
2026-08-05 16:06:56,855 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_74.mq5
2026-08-05 16:06:56,856 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_75.mq5
2026-08-05 16:06:56,856 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_76.mq5
2026-08-05 16:06:56,856 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_77.mq5
2026-08-05 16:06:56,856 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_78.mq5
2026-08-05 16:06:56,857 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_79.mq5
2026-08-05 16:06:56,857 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_80.mq5
2026-08-05 16:06:56,857 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_81.mq5
2026-08-05 16:06:56,858 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_82.mq5
2026-08-05 16:06:56,858 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_83.mq5
2026-08-05 16:06:56,858 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_84.mq5
2026-08-05 16:06:56,858 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_85.mq5
2026-08-05 16:06:56,859 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_86.mq5
2026-08-05 16:06:56,859 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_87.mq5
2026-08-05 16:06:56,859 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_88.mq5
2026-08-05 16:06:56,859 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_89.mq5
2026-08-05 16:06:56,860 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_90.mq5
2026-08-05 16:06:56,860 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_91.mq5
2026-08-05 16:06:56,860 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_92.mq5
2026-08-05 16:06:56,860 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_93.mq5
2026-08-05 16:06:56,861 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_94.mq5
2026-08-05 16:06:56,861 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_95.mq5
2026-08-05 16:06:56,861 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_96.mq5
2026-08-05 16:06:56,861 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_97.mq5
2026-08-05 16:06:56,862 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_98.mq5
2026-08-05 16:06:56,862 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_99.mq5
2026-08-05 16:06:56,862 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_100.mq5
2026-08-05 16:06:56,862 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_101.mq5
2026-08-05 16:06:56,863 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_102.mq5
2026-08-05 16:06:56,863 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_103.mq5
2026-08-05 16:06:56,863 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_104.mq5
2026-08-05 16:06:56,863 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_105.mq5
2026-08-05 16:06:56,864 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_106.mq5
2026-08-05 16:06:56,864 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_107.mq5
2026-08-05 16:06:56,864 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_108.mq5
2026-08-05 16:06:56,865 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_109.mq5
2026-08-05 16:06:56,865 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_110.mq5
2026-08-05 16:06:56,865 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_111.mq5
2026-08-05 16:06:56,865 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_112.mq5
2026-08-05 16:06:56,866 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_113.mq5
2026-08-05 16:06:56,866 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_114.mq5
2026-08-05 16:06:56,866 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_115.mq5
2026-08-05 16:06:56,866 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_116.mq5
2026-08-05 16:06:56,867 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_117.mq5
2026-08-05 16:06:56,867 [INFO] __main__: ✓ Generated 117 .mq5 EA files
2026-08-05 16:06:56,867 [INFO] __main__: 
================================================================================
2026-08-05 16:06:56,867 [INFO] __main__: EDGE RESEARCH PIPELINE COMPLETE
2026-08-05 16:06:56,867 [INFO] __main__: ================================================================================
2026-08-05 16:06:56,867 [INFO] __main__: Total edges discovered: 117
2026-08-05 16:06:56,867 [INFO] __main__: Output directory: /mnt/projects/mql5IndicatorsEdge/output
2026-08-05 16:06:56,867 [INFO] __main__:   - Reports: output/reports
2026-08-05 16:06:56,867 [INFO] __main__:   - EAs: output/generated_ea
2026-08-05 16:06:56,867 [INFO] __main__:   - Summary: output/EDGES_SUMMARY.md
2026-08-05 16:06:56,867 [INFO] __main__: ================================================================================
╭─   mnt   mql5IndicatorsEdge   multipleCondition ≡  ?1 ~3 -10  6h 33m 25s 835ms                                               bash  37.46%   mql5IndicatorsEdge 3.14.4 16:06:57
╰─ 
╭─   mnt   mql5IndicatorsEdge   multipleCondition ≡  ?1 ~3 -10  0ms                                                            bash  37.47%   mql5IndicatorsEdge 3.14.4 16:06:57
╰─ 