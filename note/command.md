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

```bash

 for XAUUSD
 

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M1.csv \
  --symbol EURUSD --timeframe M1 \
  --config-dir config/EURUSD/M1 --output-dir output

  python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M5.csv \
  --symbol EURUSD --timeframe M5 \
  --config-dir config/EURUSD/M5 --output-dir output

  python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M15.csv \
  --symbol EURUSD --timeframe M15 \
  --config-dir config/EURUSD/M15 --output-dir output

  python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M30.csv \
  --symbol EURUSD --timeframe M30 \
  --config-dir config/EURUSD/M30 --output-dir output

    python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_H1.csv \
  --symbol EURUSD --timeframe H1 \
  --config-dir config/EURUSD/H1 --output-dir output


  python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M1.csv \
  --symbol XAUUSD --timeframe M1 \
  --config-dir config/XAUUSD/M1 --output-dir output

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M5.csv \
  --symbol XAUUSD --timeframe M5 \
  --config-dir config/XAUUSD/M5 --output-dir output

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M15.csv \
  --symbol XAUUSD --timeframe M15 \
  --config-dir config/XAUUSD/M15 --output-dir output

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M30.csv \
  --symbol XAUUSD --timeframe M30 \
  --config-dir config/XAUUSD/M30 --output-dir output

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_H1.csv \
  --symbol XAUUSD --timeframe H1 \
  --config-dir config/XAUUSD/H1 --output-dir output

```
  ## BACKTEST (runs automatically at the end of every run; this re-runs it on an old run folder)
```bash
  python scripts/run_backtest.py output_walkforward/20261025_201031_XAUUSD_M5_p63377 --symbol XAUUSD --timeframe M5
  # settings: config/tester_config.yaml   |   skip the automatic one: add --no-backtest to the pipeline command
```

---

# PAUSE AND RESUME (long runs, shared PC, reboot)

Every run (walk-forward and single) can be paused and continued later, even after a reboot.
A run saves each finished window, and inside a window each finished condition (Phase 7, 7c, 7d).
A pause or crash loses at most the one condition being computed. Phases 3-6 of a window are not
saved: after a resume they are recomputed (they are the fast part), then the saved conditions are skipped.

## Pause a running job
```bash
# 1) in the terminal of the run: press Ctrl+C ONCE
#    -> it finishes the current condition, saves it, and stops by itself (status "paused").
#    Ctrl+C a SECOND time stops at once (the current condition is lost, everything else is kept).

# 2) or from another terminal, without touching the run: create an empty file named PAUSE in its run folder
type nul > output_walkforward\<run folder>\PAUSE          # Windows cmd
New-Item output_walkforward\<run folder>\PAUSE            # Windows PowerShell
touch output_walkforward/<run folder>/PAUSE                # Linux / macOS
```
A pause takes effect at the next saved condition. During Phases 3-6 of a window nothing can be saved
yet, so it waits until Phase 7 starts (Ctrl+C twice if you need the RAM back right now).

## Resume = the SAME command + `--resume`
- No value: continues the newest unfinished run of that script + symbol + timeframe under `--output-dir`.
- Runs that are running right now in another terminal are skipped automatically.
- Several unfinished runs of the same pair and timeframe? Name the one you want: `--resume output_walkforward/<run folder>`.
- Do not change the CSV or the config between pause and resume. A change is detected and the resume is refused
  (start a new run instead).
- After a reboot, a crash, or "STOPPED BY MEMORY GUARD" (exit code 3) the status is not "paused" but the same command works.
- `--sort-top-n`, `--mt5-top-n`, `--no-mt5-backtest` and `--no-ranker` may differ on resume (they only act at the end).
- When the run completes, the ranker and the MT5 backtest run as usual and the `checkpoint/` folder is removed.

```bash
python scripts/list_runs.py output_walkforward          # status per run: running / paused / interrupted / failed / completed
python scripts/list_runs.py output

# preview ranking of the windows finished so far (works on an unfinished walk-forward run)
python scripts/run_ranker.py output_walkforward/<run folder> --symbol XAUUSD --timeframe M5
```

## RESUME walk-forward runs
```bash

 resume walk-forward for XAUUSD

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M1.csv \
  --symbol XAUUSD \
  --timeframe M1 \
  --config-dir config/WALKFORWARD/XAUUSD/M1 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M5.csv \
  --symbol XAUUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/XAUUSD/M5 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M15.csv \
  --symbol XAUUSD \
  --timeframe M15 \
  --config-dir config/WALKFORWARD/XAUUSD/M15 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_M30.csv \
  --symbol XAUUSD \
  --timeframe M30 \
  --config-dir config/WALKFORWARD/XAUUSD/M30 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/XAUUSD/XAUUSD_H1.csv \
  --symbol XAUUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/XAUUSD/H1 \
  --output-dir output_walkforward \
  --resume

```

```bash

 resume walk-forward for EURUSD

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M1.csv \
  --symbol EURUSD \
  --timeframe M1 \
  --config-dir config/WALKFORWARD/EURUSD/M1 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M5.csv \
  --symbol EURUSD \
  --timeframe M5 \
  --config-dir config/WALKFORWARD/EURUSD/M5 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M15.csv \
  --symbol EURUSD \
  --timeframe M15 \
  --config-dir config/WALKFORWARD/EURUSD/M15 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_M30.csv \
  --symbol EURUSD \
  --timeframe M30 \
  --config-dir config/WALKFORWARD/EURUSD/M30 \
  --output-dir output_walkforward \
  --resume

python scripts/run_walkforward_pipeline.py \
  data/raw_csv/EURUSD/EURUSD_H1.csv \
  --symbol EURUSD \
  --timeframe H1 \
  --config-dir config/WALKFORWARD/EURUSD/H1 \
  --output-dir output_walkforward \
  --resume

```

## RESUME single runs
```bash

 resume single run for XAUUSD

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M1.csv \
  --symbol XAUUSD --timeframe M1 \
  --config-dir config/XAUUSD/M1 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M5.csv \
  --symbol XAUUSD --timeframe M5 \
  --config-dir config/XAUUSD/M5 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M15.csv \
  --symbol XAUUSD --timeframe M15 \
  --config-dir config/XAUUSD/M15 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_M30.csv \
  --symbol XAUUSD --timeframe M30 \
  --config-dir config/XAUUSD/M30 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/XAUUSD/XAUUSD_H1.csv \
  --symbol XAUUSD --timeframe H1 \
  --config-dir config/XAUUSD/H1 --output-dir output \
  --resume

```

```bash

 resume single run for EURUSD

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M1.csv \
  --symbol EURUSD --timeframe M1 \
  --config-dir config/EURUSD/M1 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M5.csv \
  --symbol EURUSD --timeframe M5 \
  --config-dir config/EURUSD/M5 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M15.csv \
  --symbol EURUSD --timeframe M15 \
  --config-dir config/EURUSD/M15 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_M30.csv \
  --symbol EURUSD --timeframe M30 \
  --config-dir config/EURUSD/M30 --output-dir output \
  --resume

python scripts/run_pipeline.py data/raw_csv/EURUSD/EURUSD_H1.csv \
  --symbol EURUSD --timeframe H1 \
  --config-dir config/EURUSD/H1 --output-dir output \
  --resume

```
