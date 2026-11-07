# Prompt: convert research conditions into MQL5 EAs

Attached file (read it first, it is the only source of truth): `dataExporter.mq5`.
The source code of the custom indicators is NOT attached. Use them only as described below.

## Task

I give you one or more conditions from my Python edge-search pipeline.
For EACH condition write one MQL5 Expert Advisor (`.mq5`) that trades exactly what the
pipeline simulated. If I give several conditions, deliver all EAs in ONE `.zip`
(`EA_01_...mq5`, `EA_02_...mq5`, plus a short `README.md`). If you cannot create files, print each
EA in its own code block instead.

Input format for each condition:
`condition | direction (long/short) | hold bars | symbol | timeframe`

## How a condition maps to code

- Every column in a condition (`rsi_7`, `ma_5_ema`, `volregime_atr_ratio`, ...) is a column of the
  CSV written by `dataExporter.mq5`. Find that column in the header and in its `Get*Values()`
  function, then copy the SAME call, parameters and buffer index into the EA.
  Example: `rsi_7` -> `iRSI(_Symbol, _Period, 7, PRICE_CLOSE)`, buffer 0.
- Every value is read at **shift 1** (the last closed bar). `open/high/low/close` mean the bar at
  shift 1. A comparison such as `ma_5_ema < close` compares two shift-1 values.
- Multi-buffer indicators (as in the exporter): stochastic K = 0, D = 1; MACD main = 0,
  signal = 1; Bollinger middle = 0, upper = 1, lower = 2.
- Custom indicators: never recompute or reimplement them (their source is not provided). Load them
  with `iCustom()` and **default inputs**, exactly like the exporter, and read the same buffer at shift 1:
  - `VolRegime_ATR`: `volregime_atr_pctl` = buffer 0, `volregime_atr_ratio` = buffer 5,
    `volregime_regime` = buffer 6.
  - `PriceStructure`: buffers 0..7 = `ps_dist_pdh_atr`, `ps_dist_pdl_atr`, `ps_dist_sess_h_atr`,
    `ps_dist_sess_l_atr`, `ps_dist_round_up_atr`, `ps_dist_round_dn_atr`, `ps_gap_atr`,
    `ps_gap_fill_pct`.
  - Add `#property tester_indicator "VolRegime_ATR.ex5"` / `"PriceStructure.ex5"` for each one used.
  - The compiled indicators are already installed on my side; do not edit or recreate them.
- Skip nothing silently: if a column is not in the exporter header, or is a calendar/news column
  (`cal_*`, `news_*`; the calendar API does not work in the Strategy Tester), stop and tell me.
- Copy buffer indexes exactly as the exporter does. If one looks wrong for the MQL5 indicator
  (for example `iEnvelopes` only has buffers 0 and 1), do not fix it silently: tell me.

## EA behaviour (all EAs)

- Run logic only once per new bar (compare `iTime(_Symbol, _Period, 0)` with the last handled bar time).
- One position per EA: filter by `InpMagic` and `_Symbol`; never open a second one.
- On each new bar, in this order:
  1. If my position exists and `held bars >= InpHoldBars`, close it at market.
     Count bars with `iBarShift(_Symbol, _Period, positionOpenTime)`, not with elapsed time.
  2. If no position exists (also right after step 1 on the same bar), check the signal at
     shift 1 and open at market in the given direction.
- No stop loss, no take profit, fixed lot. Use `CTrade` with `SetTypeFillingBySymbol(true)`.
- Inputs: `InpLots` (0.1), `InpMagic` (unique per EA), `InpHoldBars`, `InpDeviation` (20),
  `InpComment`.
- Release all indicator handles in `OnDeinit`.
- Write ALL comments, strings and log messages in English.

## Rules against guessing

- Use only functions, enums and buffer indexes that appear in the attached file or in the
  standard MQL5 library. Do not invent names.
- Do not claim the code compiles or was tested. State "not compiled" in `README.md`.
- If anything is ambiguous, ask me one short question before writing code.

## Reply format

1. One line per EA: file name, condition, direction, hold bars.
2. In `README.md` / the reply: for each EA a table `condition atom -> MQL5 call -> buffer`.
3. A short list of anything uncertain.