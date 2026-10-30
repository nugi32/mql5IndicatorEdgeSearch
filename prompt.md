# Task: Develop MQL5 Expert Advisors from Python Pipeline Reports

I will provide you with:
1. **Python Pipeline Reports:** The primary source of truth containing discovered market conditions, trading setups, indicator parameters, and strategy rules.
2. **MQL5 Source Code:** Used by my Python pipeline as a data loader. Use it strictly as a reference for understanding indicator calculations, parameters, buffer indexing, candle shifts, and data handling.

## Requirements

1. **Strategy Implementation**
   - Analyze the reports and translate their exact conditions into executable MQL5 trading logic.
   - Preserve all indicator parameters, thresholds, conditions, and combinations.
   - Do not invent, modify, or optimize trading rules.
   - The reports define the strategy; the MQL5 loader only defines how indicators are calculated.

2. **Bar-Based Execution**
   - Implement an `IsNewBar()` mechanism.
   - All EA processing, including indicator evaluation, entry signals, exit signals, and trade decisions, must execute only once per newly opened candle.
   - Follow the same bar-processing approach used by the provided data loader.
   - Ensure candle shifts and historical data references match the Python pipeline logic.
   - Prevent duplicate executions within the same bar.

3. **MQL5 Constraints**
   - Use native MQL5 functionality only.
   - No custom libraries, external dependencies, or third-party frameworks.
   - Every EA must be self-contained and independently compilable in MetaTrader 5.
   - Handle indicator initialization, invalid values, insufficient history, and resource management correctly.

4. **Project Structure**

Organize each EA by trading pair and timeframe:

```text
MQL5_EAs/
├── XAUUSD/
│   ├── M1/XAUUSD_M1.mq5
│   ├── M5/
│   └── H1/
├── EURUSD/
│   └── M15/EURUSD_M15.mq5
└── README.md
```

Only include pairs and timeframes present in the reports.

5. **Validation and Documentation**
   - Write clean, modular, documented MQL5 code.
   - Verify that indicator calculations and trading conditions match the reports and reference loader.
   - Document each EA's indicators, parameters, entry/exit rules, and any implementation assumptions.
   - Do not silently resolve missing or ambiguous strategy information through guesswork.

## Deliverables

- Complete `.mq5` source files for every reported pair and timeframe.
- Organized project folders.
- A `README.md` documenting the implemented strategies.
- One ZIP archive containing the complete project.

**Important:** Deliver actual, independently compilable EAs, not pseudocode or incomplete templates. Prioritize exact strategy fidelity and bar-by-bar execution over convenience or discretionary modifications.