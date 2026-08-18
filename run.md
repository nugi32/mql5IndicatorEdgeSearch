╭─   mnt   mql5IndicatorsEdge   tradebility ≡  28ms
                                                 bash  13.91%   mql5IndicatorsEdge 3.14.4 22:00:15
╰─ python scripts/run_pipeline.py \
  data/raw_csv/XAUUSD_M1_export_20100101.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config \
  --output-dir output
2026-08-08 22:00:45,575 [INFO] __main__: ================================================================================
2026-08-08 22:00:45,575 [INFO] __main__: EDGE RESEARCH PIPELINE START
2026-08-08 22:00:45,575 [INFO] __main__: ================================================================================
2026-08-08 22:00:45,575 [INFO] __main__: 
[PHASE 1] Ingestion & Storage...
2026-08-08 22:00:45,575 [INFO] edge_research.ingestion.loader: Loading CSV from data/raw_csv/XAUUSD_M1_export_20100101.csv
2026-08-08 22:02:02,067 [WARNING] edge_research.ingestion.loader: Could not parse time with standard formats, using pandas auto-detect
2026-08-08 22:02:03,506 [INFO] edge_research.ingestion.loader: Loaded 5527535 rows, date range: 2009-12-31 18:59:00 to 2025-12-31 23:57:00
2026-08-08 22:02:04,796 [WARNING] edge_research.ingestion.loader: Found NaN values:
envelope_20_01_lower    5527535
dtype: int64
2026-08-08 22:02:04,796 [INFO] edge_research.ingestion.loader: Converted 88 numeric columns to float32
2026-08-08 22:02:04,796 [INFO] edge_research.ingestion.loader: Writing Parquet to output/storage/XAUUSD_M1.parquet (compression=zstd)
2026-08-08 22:02:38,702 [INFO] edge_research.ingestion.loader: Successfully wrote 5527535 rows to output/storage/XAUUSD_M1.parquet
2026-08-08 22:02:38,702 [INFO] __main__: ✓ Ingestion complete: 5527535 bars loaded
2026-08-08 22:02:38,702 [INFO] __main__: 
[PHASE 2] Known-At Tagging...
2026-08-08 22:02:38,703 [INFO] edge_research.known_at.tagging: Loading known-at config from config/known_at_delay.yaml
2026-08-08 22:02:38,865 [INFO] edge_research.known_at.tagging: Loaded 39 known-at rules
2026-08-08 22:02:38,865 [INFO] __main__: ✓ Known-at tagger initialized
2026-08-08 22:02:38,865 [INFO] __main__: 
[PHASE 3] Condition Generation...
2026-08-08 22:02:38,866 [INFO] __main__:   Generated 128 atomic conditions
2026-08-08 22:02:39,932 [INFO] __main__:   128 / 128 atomic conditions passed frequency filter
2026-08-08 22:02:42,631 [INFO] __main__:   Selected top 15 atomic conditions for combination (stratified across 5 families: ['cci', 'ma', 'mom', 'rsi', 'stoch'], ~3 per family)
2026-08-08 22:02:52,178 [INFO] __main__:   2-atom combos: 82 generated (from 15 pooled atomic conditions)
2026-08-08 22:04:24,762 [INFO] __main__:   3-atom combos: 202 generated (from 15 pooled atomic conditions)
2026-08-08 22:10:46,160 [INFO] __main__:   4-atom combos: 213 generated (from 15 pooled atomic conditions)
2026-08-08 22:25:56,484 [INFO] __main__:   5-atom combos: 63 generated (from 15 pooled atomic conditions)
2026-08-08 22:25:56,485 [INFO] __main__:   Generated 560 combined conditions total
2026-08-08 22:25:56,485 [INFO] __main__: ✓ Total candidates: 688 (128 atomic + 560 combined)
2026-08-08 22:25:56,485 [INFO] __main__: 
[PHASE 4] Frequency Pre-Filter...
2026-08-08 22:26:08,131 [INFO] __main__: ✓ Frequency filter: 560 / 688 passed
2026-08-08 22:26:08,131 [INFO] __main__: 
[PHASE 5-6] Forward Profile & Significance Testing...
2026-08-08 22:26:08,131 [INFO] edge_research.forward_profile.engine: Precomputing forward matrix (horizon=20)...
2026-08-08 22:26:11,195 [INFO] edge_research.forward_profile.engine: Forward matrix computed: shape (5527535, 20)
2026-08-08 22:26:11,196 [INFO] edge_research.forward_profile.engine: Computing baseline forward profile...
2026-08-08 22:26:11,876 [INFO] edge_research.forward_profile.engine: Baseline profile computed: [0.47873557 0.48854485 0.4919945  0.49415407 0.49548557 0.49649978
 0.49760896 0.49821284 0.49869192 0.4991885  0.4994302  0.49973577
 0.5000636  0.50038487 0.5006579  0.50080353 0.5010888  0.5014063
 0.5015858  0.50176746]
2026-08-08 22:27:13,351 [INFO] edge_research.forward_profile.significance: Testing 560 conditions with FDR correction...
2026-08-08 22:27:18,801 [INFO] edge_research.forward_profile.significance: Testing complete: 549 conditions passed significance
2026-08-08 22:27:18,801 [INFO] __main__: ✓ Significance testing: 549 conditions passed
2026-08-08 22:27:18,801 [INFO] __main__: 
[PHASE 7] Robustness Validation...
2026-08-08 22:27:18,801 [INFO] edge_research.validation.walk_forward: Generated 146 walk-forward windows
2026-08-08 22:27:18,905 [INFO] edge_research.validation.regime_stress_test: Regime classification: trending=3380124, high_vol=1381563
2026-08-09 06:34:13,704 [INFO] __main__: ✓ Robustness validation: 549 edges validated
2026-08-09 06:34:13,704 [INFO] __main__: 
[PHASE 7b] Holdout Set Testing...
2026-08-09 06:34:14,366 [INFO] __main__: 
[PHASE 7c] Realistic Trade Simulation...
2026-08-09 07:16:22,429 [INFO] __main__: ✓ Trade simulation complete: 461 / 549 edges have positive simulated expectancy_r
2026-08-09 07:16:22,429 [INFO] __main__: 
[PHASE 7d] Rotation-Based Permutation Test...
2026-08-09 08:30:18,378 [INFO] __main__: ✓ Permutation testing complete: 535 / 549 edges pass the rotation permutation test
2026-08-09 08:30:18,378 [INFO] __main__: 
[PHASE 7e] Final Strategy Selection Gate...
2026-08-09 08:30:18,417 [INFO] __main__: ✓ Strategy gate: 312 / 549 edges passed ALL criteria and are recommended for EA generation
2026-08-09 08:30:18,463 [INFO] __main__: ✓ Gate results written to output/STRATEGY_GATE_RESULTS.csv
2026-08-09 08:30:18,463 [INFO] __main__: 
[PHASE 8] Report Generation...
2026-08-09 08:30:19,422 [INFO] __main__: ✓ Generated 549 edge reports (all candidates, gate status included)
2026-08-09 08:31:11,891 [INFO] edge_research.reporting.report_generator: Markdown report saved to output/EDGES_SUMMARY.md
2026-08-09 08:31:11,891 [INFO] __main__: ✓ Summary Markdown: output/EDGES_SUMMARY.md
2026-08-09 08:31:11,891 [INFO] __main__: 
[PHASE 9] MQL5 Code Generation (gate-passing edges only)...
2026-08-09 08:31:11,899 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_1.mq5
2026-08-09 08:31:11,899 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_3.mq5
2026-08-09 08:31:11,900 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_5.mq5
2026-08-09 08:31:11,900 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_15.mq5
2026-08-09 08:31:11,900 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_16.mq5
2026-08-09 08:31:11,901 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_18.mq5
2026-08-09 08:31:11,901 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_20.mq5
2026-08-09 08:31:11,901 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_27.mq5
2026-08-09 08:31:11,901 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_28.mq5
2026-08-09 08:31:11,902 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_30.mq5
2026-08-09 08:31:11,902 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_32.mq5
2026-08-09 08:31:11,902 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_118.mq5
2026-08-09 08:31:11,903 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_119.mq5
2026-08-09 08:31:11,903 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_120.mq5
2026-08-09 08:31:11,903 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_121.mq5
2026-08-09 08:31:11,903 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_122.mq5
2026-08-09 08:31:11,904 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_123.mq5
2026-08-09 08:31:11,904 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_124.mq5
2026-08-09 08:31:11,904 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_125.mq5
2026-08-09 08:31:11,905 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_126.mq5
2026-08-09 08:31:11,905 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_127.mq5
2026-08-09 08:31:11,905 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_128.mq5
2026-08-09 08:31:11,905 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_129.mq5
2026-08-09 08:31:11,906 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_130.mq5
2026-08-09 08:31:11,906 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_131.mq5
2026-08-09 08:31:11,906 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_132.mq5
2026-08-09 08:31:11,906 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_133.mq5
2026-08-09 08:31:11,907 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_134.mq5
2026-08-09 08:31:11,907 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_135.mq5
2026-08-09 08:31:11,907 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_136.mq5
2026-08-09 08:31:11,908 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_137.mq5
2026-08-09 08:31:11,908 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_138.mq5
2026-08-09 08:31:11,908 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_139.mq5
2026-08-09 08:31:11,908 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_140.mq5
2026-08-09 08:31:11,909 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_141.mq5
2026-08-09 08:31:11,909 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_142.mq5
2026-08-09 08:31:11,909 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_143.mq5
2026-08-09 08:31:11,910 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_144.mq5
2026-08-09 08:31:11,910 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_145.mq5
2026-08-09 08:31:11,910 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_146.mq5
2026-08-09 08:31:11,910 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_194.mq5
2026-08-09 08:31:11,911 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_195.mq5
2026-08-09 08:31:11,911 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_196.mq5
2026-08-09 08:31:11,911 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_197.mq5
2026-08-09 08:31:11,911 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_198.mq5
2026-08-09 08:31:11,912 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_199.mq5
2026-08-09 08:31:11,912 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_200.mq5
2026-08-09 08:31:11,912 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_201.mq5
2026-08-09 08:31:11,913 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_202.mq5
2026-08-09 08:31:11,913 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_203.mq5
2026-08-09 08:31:11,913 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_204.mq5
2026-08-09 08:31:11,913 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_205.mq5
2026-08-09 08:31:11,914 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_206.mq5
2026-08-09 08:31:11,914 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_207.mq5
2026-08-09 08:31:11,914 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_208.mq5
2026-08-09 08:31:11,914 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_209.mq5
2026-08-09 08:31:11,915 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_210.mq5
2026-08-09 08:31:11,915 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_211.mq5
2026-08-09 08:31:11,915 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_212.mq5
2026-08-09 08:31:11,915 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_213.mq5
2026-08-09 08:31:11,916 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_214.mq5
2026-08-09 08:31:11,916 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_215.mq5
2026-08-09 08:31:11,916 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_216.mq5
2026-08-09 08:31:11,917 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_217.mq5
2026-08-09 08:31:11,917 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_218.mq5
2026-08-09 08:31:11,917 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_219.mq5
2026-08-09 08:31:11,917 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_220.mq5
2026-08-09 08:31:11,918 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_221.mq5
2026-08-09 08:31:11,918 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_222.mq5
2026-08-09 08:31:11,918 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_223.mq5
2026-08-09 08:31:11,919 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_224.mq5
2026-08-09 08:31:11,919 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_225.mq5
2026-08-09 08:31:11,919 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_226.mq5
2026-08-09 08:31:11,920 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_227.mq5
2026-08-09 08:31:11,920 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_228.mq5
2026-08-09 08:31:11,920 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_229.mq5
2026-08-09 08:31:11,920 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_230.mq5
2026-08-09 08:31:11,921 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_231.mq5
2026-08-09 08:31:11,921 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_232.mq5
2026-08-09 08:31:11,921 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_233.mq5
2026-08-09 08:31:11,922 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_234.mq5
2026-08-09 08:31:11,922 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_235.mq5
2026-08-09 08:31:11,922 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_236.mq5
2026-08-09 08:31:11,922 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_237.mq5
2026-08-09 08:31:11,923 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_238.mq5
2026-08-09 08:31:11,923 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_239.mq5
2026-08-09 08:31:11,923 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_240.mq5
2026-08-09 08:31:11,923 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_241.mq5
2026-08-09 08:31:11,924 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_242.mq5
2026-08-09 08:31:11,924 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_243.mq5
2026-08-09 08:31:11,924 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_244.mq5
2026-08-09 08:31:11,925 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_245.mq5
2026-08-09 08:31:11,925 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_246.mq5
2026-08-09 08:31:11,925 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_247.mq5
2026-08-09 08:31:11,926 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_248.mq5
2026-08-09 08:31:11,926 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_249.mq5
2026-08-09 08:31:11,926 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_250.mq5
2026-08-09 08:31:11,926 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_251.mq5
2026-08-09 08:31:11,927 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_252.mq5
2026-08-09 08:31:11,927 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_253.mq5
2026-08-09 08:31:11,927 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_254.mq5
2026-08-09 08:31:11,928 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_255.mq5
2026-08-09 08:31:11,928 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_256.mq5
2026-08-09 08:31:11,928 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_257.mq5
2026-08-09 08:31:11,928 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_258.mq5
2026-08-09 08:31:11,929 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_259.mq5
2026-08-09 08:31:11,929 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_260.mq5
2026-08-09 08:31:11,929 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_261.mq5
2026-08-09 08:31:11,930 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_262.mq5
2026-08-09 08:31:11,930 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_263.mq5
2026-08-09 08:31:11,930 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_264.mq5
2026-08-09 08:31:11,930 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_265.mq5
2026-08-09 08:31:11,931 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_266.mq5
2026-08-09 08:31:11,931 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_267.mq5
2026-08-09 08:31:11,931 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_268.mq5
2026-08-09 08:31:11,932 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_269.mq5
2026-08-09 08:31:11,932 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_270.mq5
2026-08-09 08:31:11,932 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_271.mq5
2026-08-09 08:31:11,932 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_272.mq5
2026-08-09 08:31:11,933 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_273.mq5
2026-08-09 08:31:11,933 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_274.mq5
2026-08-09 08:31:11,933 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_275.mq5
2026-08-09 08:31:11,934 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_276.mq5
2026-08-09 08:31:11,934 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_277.mq5
2026-08-09 08:31:11,934 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_278.mq5
2026-08-09 08:31:11,935 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_279.mq5
2026-08-09 08:31:11,935 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_280.mq5
2026-08-09 08:31:11,935 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_281.mq5
2026-08-09 08:31:11,935 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_282.mq5
2026-08-09 08:31:11,936 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_283.mq5
2026-08-09 08:31:11,936 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_284.mq5
2026-08-09 08:31:11,936 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_285.mq5
2026-08-09 08:31:11,936 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_286.mq5
2026-08-09 08:31:11,937 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_287.mq5
2026-08-09 08:31:11,937 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_288.mq5
2026-08-09 08:31:11,937 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_289.mq5
2026-08-09 08:31:11,938 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_290.mq5
2026-08-09 08:31:11,938 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_291.mq5
2026-08-09 08:31:11,938 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_358.mq5
2026-08-09 08:31:11,939 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_359.mq5
2026-08-09 08:31:11,939 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_360.mq5
2026-08-09 08:31:11,939 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_361.mq5
2026-08-09 08:31:11,939 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_362.mq5
2026-08-09 08:31:11,940 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_363.mq5
2026-08-09 08:31:11,940 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_364.mq5
2026-08-09 08:31:11,940 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_365.mq5
2026-08-09 08:31:11,941 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_366.mq5
2026-08-09 08:31:11,941 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_367.mq5
2026-08-09 08:31:11,941 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_368.mq5
2026-08-09 08:31:11,941 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_369.mq5
2026-08-09 08:31:11,942 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_370.mq5
2026-08-09 08:31:11,942 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_371.mq5
2026-08-09 08:31:11,942 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_372.mq5
2026-08-09 08:31:11,943 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_373.mq5
2026-08-09 08:31:11,943 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_374.mq5
2026-08-09 08:31:11,943 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_375.mq5
2026-08-09 08:31:11,943 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_376.mq5
2026-08-09 08:31:11,944 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_377.mq5
2026-08-09 08:31:11,944 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_378.mq5
2026-08-09 08:31:11,944 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_379.mq5
2026-08-09 08:31:11,945 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_380.mq5
2026-08-09 08:31:11,945 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_381.mq5
2026-08-09 08:31:11,945 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_382.mq5
2026-08-09 08:31:11,945 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_383.mq5
2026-08-09 08:31:11,946 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_384.mq5
2026-08-09 08:31:11,946 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_385.mq5
2026-08-09 08:31:11,946 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_386.mq5
2026-08-09 08:31:11,946 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_387.mq5
2026-08-09 08:31:11,947 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_388.mq5
2026-08-09 08:31:11,947 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_389.mq5
2026-08-09 08:31:11,947 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_390.mq5
2026-08-09 08:31:11,948 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_391.mq5
2026-08-09 08:31:11,948 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_392.mq5
2026-08-09 08:31:11,948 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_393.mq5
2026-08-09 08:31:11,948 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_394.mq5
2026-08-09 08:31:11,949 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_395.mq5
2026-08-09 08:31:11,949 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_396.mq5
2026-08-09 08:31:11,949 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_397.mq5
2026-08-09 08:31:11,950 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_398.mq5
2026-08-09 08:31:11,950 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_399.mq5
2026-08-09 08:31:11,950 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_400.mq5
2026-08-09 08:31:11,950 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_401.mq5
2026-08-09 08:31:11,951 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_402.mq5
2026-08-09 08:31:11,951 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_403.mq5
2026-08-09 08:31:11,951 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_404.mq5
2026-08-09 08:31:11,952 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_405.mq5
2026-08-09 08:31:11,952 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_406.mq5
2026-08-09 08:31:11,952 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_407.mq5
2026-08-09 08:31:11,952 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_408.mq5
2026-08-09 08:31:11,953 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_409.mq5
2026-08-09 08:31:11,953 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_410.mq5
2026-08-09 08:31:11,953 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_411.mq5
2026-08-09 08:31:11,953 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_412.mq5
2026-08-09 08:31:11,954 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_413.mq5
2026-08-09 08:31:11,954 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_414.mq5
2026-08-09 08:31:11,954 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_415.mq5
2026-08-09 08:31:11,954 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_416.mq5
2026-08-09 08:31:11,955 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_417.mq5
2026-08-09 08:31:11,955 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_418.mq5
2026-08-09 08:31:11,955 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_419.mq5
2026-08-09 08:31:11,955 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_420.mq5
2026-08-09 08:31:11,956 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_421.mq5
2026-08-09 08:31:11,956 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_422.mq5
2026-08-09 08:31:11,956 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_423.mq5
2026-08-09 08:31:11,956 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_424.mq5
2026-08-09 08:31:11,957 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_425.mq5
2026-08-09 08:31:11,957 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_426.mq5
2026-08-09 08:31:11,957 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_427.mq5
2026-08-09 08:31:11,957 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_428.mq5
2026-08-09 08:31:11,958 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_429.mq5
2026-08-09 08:31:11,958 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_430.mq5
2026-08-09 08:31:11,958 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_431.mq5
2026-08-09 08:31:11,958 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_432.mq5
2026-08-09 08:31:11,959 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_433.mq5
2026-08-09 08:31:11,959 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_434.mq5
2026-08-09 08:31:11,959 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_435.mq5
2026-08-09 08:31:11,959 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_436.mq5
2026-08-09 08:31:11,960 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_437.mq5
2026-08-09 08:31:11,960 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_438.mq5
2026-08-09 08:31:11,960 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_439.mq5
2026-08-09 08:31:11,960 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_440.mq5
2026-08-09 08:31:11,961 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_441.mq5
2026-08-09 08:31:11,961 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_442.mq5
2026-08-09 08:31:11,961 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_443.mq5
2026-08-09 08:31:11,961 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_444.mq5
2026-08-09 08:31:11,962 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_445.mq5
2026-08-09 08:31:11,962 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_446.mq5
2026-08-09 08:31:11,962 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_447.mq5
2026-08-09 08:31:11,962 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_448.mq5
2026-08-09 08:31:11,963 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_449.mq5
2026-08-09 08:31:11,963 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_450.mq5
2026-08-09 08:31:11,963 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_451.mq5
2026-08-09 08:31:11,963 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_452.mq5
2026-08-09 08:31:11,964 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_453.mq5
2026-08-09 08:31:11,964 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_454.mq5
2026-08-09 08:31:11,964 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_455.mq5
2026-08-09 08:31:11,964 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_456.mq5
2026-08-09 08:31:11,965 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_457.mq5
2026-08-09 08:31:11,965 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_458.mq5
2026-08-09 08:31:11,965 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_459.mq5
2026-08-09 08:31:11,965 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_460.mq5
2026-08-09 08:31:11,966 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_461.mq5
2026-08-09 08:31:11,966 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_462.mq5
2026-08-09 08:31:11,966 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_463.mq5
2026-08-09 08:31:11,966 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_464.mq5
2026-08-09 08:31:11,967 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_465.mq5
2026-08-09 08:31:11,967 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_466.mq5
2026-08-09 08:31:11,967 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_467.mq5
2026-08-09 08:31:11,967 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_468.mq5
2026-08-09 08:31:11,968 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_469.mq5
2026-08-09 08:31:11,968 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_470.mq5
2026-08-09 08:31:11,968 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_471.mq5
2026-08-09 08:31:11,968 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_472.mq5
2026-08-09 08:31:11,969 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_473.mq5
2026-08-09 08:31:11,969 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_474.mq5
2026-08-09 08:31:11,969 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_475.mq5
2026-08-09 08:31:11,969 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_476.mq5
2026-08-09 08:31:11,970 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_477.mq5
2026-08-09 08:31:11,970 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_478.mq5
2026-08-09 08:31:11,970 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_479.mq5
2026-08-09 08:31:11,970 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_480.mq5
2026-08-09 08:31:11,971 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_481.mq5
2026-08-09 08:31:11,971 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_482.mq5
2026-08-09 08:31:11,971 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_483.mq5
2026-08-09 08:31:11,971 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_484.mq5
2026-08-09 08:31:11,972 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_485.mq5
2026-08-09 08:31:11,972 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_486.mq5
2026-08-09 08:31:11,972 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_505.mq5
2026-08-09 08:31:11,972 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_506.mq5
2026-08-09 08:31:11,973 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_507.mq5
2026-08-09 08:31:11,973 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_508.mq5
2026-08-09 08:31:11,973 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_509.mq5
2026-08-09 08:31:11,973 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_510.mq5
2026-08-09 08:31:11,974 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_511.mq5
2026-08-09 08:31:11,974 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_512.mq5
2026-08-09 08:31:11,974 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_513.mq5
2026-08-09 08:31:11,974 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_514.mq5
2026-08-09 08:31:11,975 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_515.mq5
2026-08-09 08:31:11,975 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_516.mq5
2026-08-09 08:31:11,975 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_517.mq5
2026-08-09 08:31:11,975 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_518.mq5
2026-08-09 08:31:11,976 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_519.mq5
2026-08-09 08:31:11,976 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_520.mq5
2026-08-09 08:31:11,976 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_521.mq5
2026-08-09 08:31:11,976 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_522.mq5
2026-08-09 08:31:11,977 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_523.mq5
2026-08-09 08:31:11,977 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_524.mq5
2026-08-09 08:31:11,977 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_525.mq5
2026-08-09 08:31:11,977 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_526.mq5
2026-08-09 08:31:11,978 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_527.mq5
2026-08-09 08:31:11,978 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_528.mq5
2026-08-09 08:31:11,978 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_529.mq5
2026-08-09 08:31:11,978 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_530.mq5
2026-08-09 08:31:11,979 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_531.mq5
2026-08-09 08:31:11,979 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_532.mq5
2026-08-09 08:31:11,979 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_533.mq5
2026-08-09 08:31:11,979 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_534.mq5
2026-08-09 08:31:11,980 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_535.mq5
2026-08-09 08:31:11,980 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_536.mq5
2026-08-09 08:31:11,980 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_537.mq5
2026-08-09 08:31:11,980 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_538.mq5
2026-08-09 08:31:11,981 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_539.mq5
2026-08-09 08:31:11,981 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_540.mq5
2026-08-09 08:31:11,981 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_541.mq5
2026-08-09 08:31:11,981 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_542.mq5
2026-08-09 08:31:11,982 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_543.mq5
2026-08-09 08:31:11,982 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_544.mq5
2026-08-09 08:31:11,982 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_545.mq5
2026-08-09 08:31:11,982 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_546.mq5
2026-08-09 08:31:11,983 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_547.mq5
2026-08-09 08:31:11,983 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_548.mq5
2026-08-09 08:31:11,983 [INFO] edge_research.mql5_codegen.generator: Generated MQL5 EA: output/generated_ea/XAUUSD_M1_549.mq5
2026-08-09 08:31:11,983 [INFO] __main__: ✓ Generated 312 .mq5 EA files (237 candidates did not pass the strategy gate and were skipped; see STRATEGY_GATE_RESULTS.csv for reasons)
2026-08-09 08:31:11,983 [INFO] __main__: 
================================================================================
2026-08-09 08:31:11,983 [INFO] __main__: EDGE RESEARCH PIPELINE COMPLETE
2026-08-09 08:31:11,983 [INFO] __main__: ================================================================================
2026-08-09 08:31:11,983 [INFO] __main__: Total edges discovered: 549
2026-08-09 08:31:11,984 [INFO] __main__: Output directory: /mnt/projects/mql5IndicatorsEdge/output
2026-08-09 08:31:11,984 [INFO] __main__:   - Reports: output/reports
2026-08-09 08:31:11,984 [INFO] __main__:   - EAs: output/generated_ea
2026-08-09 08:31:11,984 [INFO] __main__:   - Summary: output/EDGES_SUMMARY.md
2026-08-09 08:31:11,984 [INFO] __main__: ================================================================================
╭─   mnt   mql5IndicatorsEdge   tradebility ≡  ~1  10h 30m 34s 689ms
                                                  bash  9.36%   mql5IndicatorsEdge 3.14.4 08:31:12
╰─ code .
╭─   mnt   mql5IndicatorsEdge   tradebility ≡  ~1  359ms
                                                  bash  9.61%   mql5IndicatorsEdge 3.14.4 10:15:16
╰─ 
