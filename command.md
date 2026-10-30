```bash

 for XAUUSD
 
python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M1.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config/WALKFORWARD/XAUUSD/M1 \
  --output-dir output_walkforward

  python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M5.csv \
  --symbol XAUUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/XAUUSD/M5 \
  --output-dir output_walkforward

  python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M15.csv \
  --symbol XAUUSD \
  --timeframe M15 \
  --config-dir config/WALKFORWARD/XAUUSD/M15 \
  --output-dir output_walkforward

  python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M30.csv \
  --symbol XAUUSD \
  --timeframe M30 \
  --config-dir config/WALKFORWARD/XAUUSD/M30 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_H1.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/XAUUSD/H1 \
  --output-dir output_walkforward

```
```bash

 for EURUSD
 
python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M1.csv \
  --symbol EURUSD \
  --timeframe M1 \
  --config-dir config/WALKFORWARD/EURUSD/M1 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M5.csv \
  --symbol EURUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/EURUSD/M5 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M15.csv \
  --symbol EURUSD \
  --timeframe M15 \
  --config-dir config/WALKFORWARD/EURUSD/M15 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M30.csv \
  --symbol EURUSD \
  --timeframe M30 \
  --config-dir config/WALKFORWARD/EURUSD/M30 \
  --output-dir output_walkforward

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_H1.csv \
  --symbol EURUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/EURUSD/H1 \
  --output-dir output_walkforward

```
  ## RANKER
```bash
  python scripts/run_ranker.py output_walkforward/20261025_201031_XAUUSD_M5_p63377 --symbol XAUUSD --timeframe M5 --mode sort --sort-top-n 10
```