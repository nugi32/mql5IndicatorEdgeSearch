//+------------------------------------------------------------------+
//|                                                  DataExporter.mq5 |
//|                                                                  |
//| Expert Advisor for MT5 Strategy Tester that exports historical   |
//| OHLCV data and comprehensive technical indicators to a single    |
//| CSV file for research/analysis in Python. Runs bar-by-bar during |
//| backtest and exports data incrementally.                         |
//+------------------------------------------------------------------+
#property copyright "DataExporter"
#property link      "https://www.mql5.com"
#property version   "1.00"
#property strict
#property description "One-time utility to export indicator data to CSV during backtest"

#include <Trade\Trade.mqh>

//--- Global variables
string g_symbol;
ENUM_TIMEFRAMES g_timeframe;
int g_bars_total;
datetime g_export_time;
int g_columns_exported = 0;
int g_columns_failed = 0;
datetime g_script_start_time;
bool g_csv_initialized = false;
bool g_export_complete = false;

//--- CSV file handle
int g_file_handle = INVALID_HANDLE;

//--- Array to store all bar times and OHLCV
struct BarData {
    datetime time;
    double open;
    double high;
    double low;
    double close;
    long tick_volume;
    long real_volume;
};

BarData g_bars[];

//--- Indicator handles (persistent across OnTick calls)
struct IndicatorHandles {
    // Moving Averages
    int ma_5_sma, ma_5_ema, ma_5_smma, ma_5_lwma;
    int ma_10_sma, ma_10_ema, ma_10_smma, ma_10_lwma;
    int ma_20_sma, ma_20_ema, ma_20_smma, ma_20_lwma;
    int ma_50_sma, ma_50_ema, ma_50_smma, ma_50_lwma;
    int ma_100_sma, ma_100_ema, ma_100_smma, ma_100_lwma;
    int ma_200_sma, ma_200_ema, ma_200_smma, ma_200_lwma;

    // Adaptive MA
    int dema_10, dema_20, dema_50;
    int tema_10, tema_20, tema_50;
    int frama_14, frama_20;
    int ama_10;
    int vidya_9, vidya_12;

    // Trend/Directional
    int sar_002, sar_001, sar_003;
    int adx_14, adxwilder_14;

    // Oscillators
    int rsi_7, rsi_14, rsi_21;
    int stoch_5_3_3, stoch_14_3_3;
    int cci_14, cci_20;
    int wpr_14;
    int mom_10, mom_14;
    int macd_12_26_9;
    int osma_12_26_9;
    int demarker_14;
    int rvi_10;
    int trix_14;
    int ac, ao;
    int bears_13, bulls_13;

    // Volatility
    int atr_14, atr_20;
    int bb_20_2, bb_20_15, bb_20_25;
    int stddev_20;
    int envelope_20_01;

    // Volume-Based
    int obv, ad, mfi_14, force_13, chaikin_3_10;
};

IndicatorHandles g_handles;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit() {
    g_symbol = Symbol();
    g_timeframe = Period();
    g_export_time = TimeCurrent();
    g_script_start_time = TimeCurrent();

    // Determine total bars available
    g_bars_total = Bars(g_symbol, g_timeframe);
    if (g_bars_total <= 0) {
        Print("ERROR: No bars available for ", g_symbol, " on timeframe ", g_timeframe);
        return INIT_FAILED;
    }

    Print("===== DataExporter START (Tester Mode) =====");
    Print("Symbol: ", g_symbol, " | Timeframe: ", TimeframeToString(g_timeframe));
    Print("Total bars in history: ", g_bars_total);

    // Load base OHLCV data
    if (!LoadBarData()) {
        Print("ERROR: Failed to load bar data");
        return INIT_FAILED;
    }

    // Generate filename
    string filename = GenerateFilename();

    // Initialize CSV file
    if (!InitializeCSV(filename)) {
        Print("ERROR: Failed to initialize CSV file");
        return INIT_FAILED;
    }

    // Create all indicator handles
    CreateIndicatorHandles();

    g_csv_initialized = true;

    Print("Initialization complete. Starting data export on each bar...");

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick() {
    if (!g_csv_initialized || g_export_complete) {
        return;
    }

    int current_bar_index = 0; // Current bar (most recent in tester)
    int total_bars = Bars(g_symbol, g_timeframe);

    // Calculate progress
    int bars_processed = total_bars - current_bar_index;
    int progress_percent = (bars_processed * 100) / total_bars;

    Comment("DataExporter Progress: ", progress_percent, "% | Bars: ", bars_processed, "/", total_bars);

    // Write current bar to CSV
    WriteBarToCSV(current_bar_index);

    // Check if we've reached the end of history (first bar)
    if (current_bar_index >= total_bars - 1) {
        g_export_complete = true;
        OnDeinit(REASON_PROGRAM);
    }
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
    if (g_file_handle != INVALID_HANDLE) {
        FileClose(g_file_handle);
    }

    // Release all indicator handles
    ReleaseAllHandles();

    if (g_export_complete) {
        datetime script_end_time = TimeCurrent();
        int elapsed_seconds = (int)(script_end_time - g_script_start_time);

        Print("===== DataExporter COMPLETE =====");
        Print("Total bars exported: ", Bars(g_symbol, g_timeframe));
        Print("Columns exported: ", g_columns_exported);
        Print("Columns failed: ", g_columns_failed);
        Print("Time elapsed: ", elapsed_seconds, " seconds");
        Print("File location: MQL5\\Files\\DataExport_", g_symbol, "_", TimeframeToString(g_timeframe), ".csv");
    }
}

//+------------------------------------------------------------------+
//| Load base OHLCV data                                             |
//+------------------------------------------------------------------+
bool LoadBarData() {
    ArrayResize(g_bars, g_bars_total);

    for (int i = 0; i < g_bars_total; i++) {
        g_bars[i].time = iTime(g_symbol, g_timeframe, i);
        g_bars[i].open = iOpen(g_symbol, g_timeframe, i);
        g_bars[i].high = iHigh(g_symbol, g_timeframe, i);
        g_bars[i].low = iLow(g_symbol, g_timeframe, i);
        g_bars[i].close = iClose(g_symbol, g_timeframe, i);
        g_bars[i].tick_volume = iVolume(g_symbol, g_timeframe, i);
        g_bars[i].real_volume = iRealVolume(g_symbol, g_timeframe, i);
    }

    return true;
}

//+------------------------------------------------------------------+
//| Generate output filename                                         |
//+------------------------------------------------------------------+
string GenerateFilename() {
    string timestamp = TimeToString(g_export_time, TIME_DATE);
    StringReplace(timestamp, ".", "");
    return g_symbol + "_" + TimeframeToString(g_timeframe) + "_export_" + timestamp + ".csv";
}

//+------------------------------------------------------------------+
//| Convert timeframe enum to string                                 |
//+------------------------------------------------------------------+
string TimeframeToString(ENUM_TIMEFRAMES tf) {
    switch (tf) {
        case PERIOD_M1:  return "M1";
        case PERIOD_M5:  return "M5";
        case PERIOD_M15: return "M15";
        case PERIOD_M30: return "M30";
        case PERIOD_H1:  return "H1";
        case PERIOD_H4:  return "H4";
        case PERIOD_D1:  return "D1";
        case PERIOD_W1:  return "W1";
        case PERIOD_MN1: return "MN1";
        default: return "UNKNOWN";
    }
}

//+------------------------------------------------------------------+
//| Initialize CSV file with header row                              |
//| NOTE: MQL5 does not support range-based for loops or brace-init  |
//| lists ({5,10,20}) like C++11. Replaced with static arrays and    |
//| standard indexed for loops.                                      |
//+------------------------------------------------------------------+
bool InitializeCSV(string filename) {
    g_file_handle = FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_ANSI);
    if (g_file_handle == INVALID_HANDLE) {
        Print("ERROR: Cannot create file ", filename);
        return false;
    }

    // Write header row
    string header = "time,open,high,low,close,tick_volume,real_volume";

    // Moving Averages: 6 periods x 4 modes = 24 columns
    int ma_periods[6] = {5, 10, 20, 50, 100, 200};
    for (int i = 0; i < ArraySize(ma_periods); i++) {
        int period = ma_periods[i];
        header += ",ma_" + (string)period + "_sma,ma_" + (string)period + "_ema";
        header += ",ma_" + (string)period + "_smma,ma_" + (string)period + "_lwma";
    }

    // Adaptive MA
    int dema_periods[3] = {10, 20, 50};
    for (int i = 0; i < ArraySize(dema_periods); i++) {
        header += ",dema_" + (string)dema_periods[i];
    }
    int tema_periods[3] = {10, 20, 50};
    for (int i = 0; i < ArraySize(tema_periods); i++) {
        header += ",tema_" + (string)tema_periods[i];
    }
    int frama_periods[2] = {14, 20};
    for (int i = 0; i < ArraySize(frama_periods); i++) {
        header += ",frama_" + (string)frama_periods[i];
    }
    header += ",ama_10_2_30";
    int vidya_periods[2] = {9, 12};
    for (int i = 0; i < ArraySize(vidya_periods); i++) {
        header += ",vidya_" + (string)vidya_periods[i];
    }

    // Trend/Directional
    header += ",sar_002_02,sar_001_02,sar_003_02";
    header += ",adx_14,adxwilder_14";

    // Oscillators
    int rsi_periods[3] = {7, 14, 21};
    for (int i = 0; i < ArraySize(rsi_periods); i++) {
        header += ",rsi_" + (string)rsi_periods[i];
    }
    header += ",stoch_5_3_3_k,stoch_5_3_3_d,stoch_14_3_3_k,stoch_14_3_3_d";
    int cci_periods[2] = {14, 20};
    for (int i = 0; i < ArraySize(cci_periods); i++) {
        header += ",cci_" + (string)cci_periods[i];
    }
    header += ",wpr_14,mom_10,mom_14,macd_12_26_9_main,macd_12_26_9_signal";
    header += ",osma_12_26_9,demarker_14,rvi_10,trix_14,ac,ao";
    header += ",bears_13,bulls_13";

    // Volatility
    int atr_periods[2] = {14, 20};
    for (int i = 0; i < ArraySize(atr_periods); i++) {
        header += ",atr_" + (string)atr_periods[i];
    }
    header += ",bb_20_2_upper,bb_20_2_middle,bb_20_2_lower";
    header += ",bb_20_15_upper,bb_20_15_middle,bb_20_15_lower";
    header += ",bb_20_25_upper,bb_20_25_middle,bb_20_25_lower";
    header += ",stddev_20,envelope_20_01_upper,envelope_20_01_lower";

    // Volume-Based
    header += ",obv,ad,mfi_14,force_13,chaikin_3_10,volumes";

    FileWrite(g_file_handle, header);

    // Count columns for reporting
    g_columns_exported = CountColumns(header);

    Print("CSV header written with ", g_columns_exported, " indicator columns");

    return true;
}

//+------------------------------------------------------------------+
//| Count columns in header                                          |
//+------------------------------------------------------------------+
int CountColumns(string header) {
    int count = 1; // Start with 1 for "time"
    for (int i = 0; i < StringLen(header); i++) {
        if (StringGetCharacter(header, i) == ',') {
            count++;
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Create all indicator handles                                     |
//+------------------------------------------------------------------+
void CreateIndicatorHandles() {
    // Moving Averages
    g_handles.ma_5_sma = iMA(g_symbol, g_timeframe, 5, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_5_ema = iMA(g_symbol, g_timeframe, 5, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_5_smma = iMA(g_symbol, g_timeframe, 5, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_5_lwma = iMA(g_symbol, g_timeframe, 5, 0, MODE_LWMA, PRICE_CLOSE);

    g_handles.ma_10_sma = iMA(g_symbol, g_timeframe, 10, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_10_ema = iMA(g_symbol, g_timeframe, 10, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_10_smma = iMA(g_symbol, g_timeframe, 10, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_10_lwma = iMA(g_symbol, g_timeframe, 10, 0, MODE_LWMA, PRICE_CLOSE);

    g_handles.ma_20_sma = iMA(g_symbol, g_timeframe, 20, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_20_ema = iMA(g_symbol, g_timeframe, 20, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_20_smma = iMA(g_symbol, g_timeframe, 20, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_20_lwma = iMA(g_symbol, g_timeframe, 20, 0, MODE_LWMA, PRICE_CLOSE);

    g_handles.ma_50_sma = iMA(g_symbol, g_timeframe, 50, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_50_ema = iMA(g_symbol, g_timeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_50_smma = iMA(g_symbol, g_timeframe, 50, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_50_lwma = iMA(g_symbol, g_timeframe, 50, 0, MODE_LWMA, PRICE_CLOSE);

    g_handles.ma_100_sma = iMA(g_symbol, g_timeframe, 100, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_100_ema = iMA(g_symbol, g_timeframe, 100, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_100_smma = iMA(g_symbol, g_timeframe, 100, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_100_lwma = iMA(g_symbol, g_timeframe, 100, 0, MODE_LWMA, PRICE_CLOSE);

    g_handles.ma_200_sma = iMA(g_symbol, g_timeframe, 200, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.ma_200_ema = iMA(g_symbol, g_timeframe, 200, 0, MODE_EMA, PRICE_CLOSE);
    g_handles.ma_200_smma = iMA(g_symbol, g_timeframe, 200, 0, MODE_SMMA, PRICE_CLOSE);
    g_handles.ma_200_lwma = iMA(g_symbol, g_timeframe, 200, 0, MODE_LWMA, PRICE_CLOSE);

    // Adaptive MA
    g_handles.dema_10 = iDEMA(g_symbol, g_timeframe, 10, 0, PRICE_CLOSE);
    g_handles.dema_20 = iDEMA(g_symbol, g_timeframe, 20, 0, PRICE_CLOSE);
    g_handles.dema_50 = iDEMA(g_symbol, g_timeframe, 50, 0, PRICE_CLOSE);

    g_handles.tema_10 = iTEMA(g_symbol, g_timeframe, 10, 0, PRICE_CLOSE);
    g_handles.tema_20 = iTEMA(g_symbol, g_timeframe, 20, 0, PRICE_CLOSE);
    g_handles.tema_50 = iTEMA(g_symbol, g_timeframe, 50, 0, PRICE_CLOSE);

    g_handles.frama_14 = iFrAMA(g_symbol, g_timeframe, 14, 0, PRICE_CLOSE);
    g_handles.frama_20 = iFrAMA(g_symbol, g_timeframe, 20, 0, PRICE_CLOSE);

    g_handles.ama_10 = iAMA(g_symbol, g_timeframe, 10, 2, 30, 0, PRICE_CLOSE);

    // iVIDyA signature: (symbol, period, cmo_period, ema_period, shift, applied_price)
    // Original call was missing one int parameter (wrong parameters count).
    g_handles.vidya_9 = iVIDyA(g_symbol, g_timeframe, 9, 12, 0, PRICE_CLOSE);
    g_handles.vidya_12 = iVIDyA(g_symbol, g_timeframe, 12, 12, 0, PRICE_CLOSE);

    // Trend/Directional
    g_handles.sar_002 = iSAR(g_symbol, g_timeframe, 0.02, 0.2);
    g_handles.sar_001 = iSAR(g_symbol, g_timeframe, 0.01, 0.2);
    g_handles.sar_003 = iSAR(g_symbol, g_timeframe, 0.03, 0.2);

    g_handles.adx_14 = iADX(g_symbol, g_timeframe, 14);
    g_handles.adxwilder_14 = iADXWilder(g_symbol, g_timeframe, 14);

    // Oscillators
    g_handles.rsi_7 = iRSI(g_symbol, g_timeframe, 7, PRICE_CLOSE);
    g_handles.rsi_14 = iRSI(g_symbol, g_timeframe, 14, PRICE_CLOSE);
    g_handles.rsi_21 = iRSI(g_symbol, g_timeframe, 21, PRICE_CLOSE);

    // iStochastic signature: (symbol, period, Kperiod, Dperiod, slowing, ma_method, price_field)
    // Original call was missing the ENUM_STO_PRICE price_field argument.
    g_handles.stoch_5_3_3 = iStochastic(g_symbol, g_timeframe, 5, 3, 3, MODE_SMA, STO_LOWHIGH);
    g_handles.stoch_14_3_3 = iStochastic(g_symbol, g_timeframe, 14, 3, 3, MODE_SMA, STO_LOWHIGH);

    g_handles.cci_14 = iCCI(g_symbol, g_timeframe, 14, PRICE_TYPICAL);
    g_handles.cci_20 = iCCI(g_symbol, g_timeframe, 20, PRICE_TYPICAL);

    g_handles.wpr_14 = iWPR(g_symbol, g_timeframe, 14);

    g_handles.mom_10 = iMomentum(g_symbol, g_timeframe, 10, PRICE_CLOSE);
    g_handles.mom_14 = iMomentum(g_symbol, g_timeframe, 14, PRICE_CLOSE);

    g_handles.macd_12_26_9 = iMACD(g_symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE);
    g_handles.osma_12_26_9 = iOsMA(g_symbol, g_timeframe, 12, 26, 9, PRICE_CLOSE);

    g_handles.demarker_14 = iDeMarker(g_symbol, g_timeframe, 14);
    g_handles.rvi_10 = iRVI(g_symbol, g_timeframe, 10);

    // iTriX signature: (symbol, period, ma_period, applied_price)
    // Original call was missing the applied_price argument.
    g_handles.trix_14 = iTriX(g_symbol, g_timeframe, 14, PRICE_CLOSE);

    g_handles.ac = iAC(g_symbol, g_timeframe);
    g_handles.ao = iAO(g_symbol, g_timeframe);

    g_handles.bears_13 = iBearsPower(g_symbol, g_timeframe, 13);
    g_handles.bulls_13 = iBullsPower(g_symbol, g_timeframe, 13);

    // Volatility
    g_handles.atr_14 = iATR(g_symbol, g_timeframe, 14);
    g_handles.atr_20 = iATR(g_symbol, g_timeframe, 20);

    g_handles.bb_20_2 = iBands(g_symbol, g_timeframe, 20, 0, 2.0, PRICE_CLOSE);
    g_handles.bb_20_15 = iBands(g_symbol, g_timeframe, 20, 0, 1.5, PRICE_CLOSE);
    g_handles.bb_20_25 = iBands(g_symbol, g_timeframe, 20, 0, 2.5, PRICE_CLOSE);

    g_handles.stddev_20 = iStdDev(g_symbol, g_timeframe, 20, 0, MODE_SMA, PRICE_CLOSE);
    g_handles.envelope_20_01 = iEnvelopes(g_symbol, g_timeframe, 20, 0, MODE_SMA, PRICE_CLOSE, 0.1);

    // Volume-Based
    // iOBV signature: (symbol, period, ENUM_APPLIED_VOLUME) - NOT applied price.
    g_handles.obv = iOBV(g_symbol, g_timeframe, VOLUME_TICK);
    g_handles.ad = iAD(g_symbol, g_timeframe, VOLUME_TICK);
    g_handles.mfi_14 = iMFI(g_symbol, g_timeframe, 14, VOLUME_TICK);

    // iForce signature: (symbol, period, ma_period, ma_method, ENUM_APPLIED_VOLUME) - last arg must be volume, not price.
    g_handles.force_13 = iForce(g_symbol, g_timeframe, 13, MODE_SMA, VOLUME_TICK);

    // iChaikin signature: (symbol, period, fast_period, slow_period, ma_method, applied_volume)
    // Original call was missing the ma_method argument.
    g_handles.chaikin_3_10 = iChaikin(g_symbol, g_timeframe, 3, 10, MODE_EMA, VOLUME_TICK);

    Print("All indicator handles created successfully");
}

//+------------------------------------------------------------------+
//| Write current bar to CSV                                         |
//+------------------------------------------------------------------+
void WriteBarToCSV(int bar_index) {
    if (g_file_handle == INVALID_HANDLE) return;

    // Format time
    string time_str = TimeToString(g_bars[bar_index].time, TIME_DATE | TIME_MINUTES);
    StringReplace(time_str, ".", "");

    // Build row with base OHLCV
    string row = time_str + ",";
    row += DoubleToString(g_bars[bar_index].open, 6) + ",";
    row += DoubleToString(g_bars[bar_index].high, 6) + ",";
    row += DoubleToString(g_bars[bar_index].low, 6) + ",";
    row += DoubleToString(g_bars[bar_index].close, 6) + ",";
    row += (string)g_bars[bar_index].tick_volume + ",";
    row += (string)g_bars[bar_index].real_volume;

    // Add Moving Averages
    row += GetMAValues(bar_index);

    // Add Adaptive MA
    row += GetAdaptiveMAValues(bar_index);

    // Add Trend/Directional
    row += GetTrendValues(bar_index);

    // Add Oscillators
    row += GetOscillatorValues(bar_index);

    // Add Volatility
    row += GetVolatilityValues(bar_index);

    // Add Volume-Based
    row += GetVolumeBased(bar_index);

    FileWrite(g_file_handle, row);
}

//+------------------------------------------------------------------+
//| Get Moving Average values for bar                                |
//+------------------------------------------------------------------+
string GetMAValues(int bar_index) {
    string result = "";

    double value;

    // MA 5
    if (GetIndicatorValue(g_handles.ma_5_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_5_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_5_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_5_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MA 10
    if (GetIndicatorValue(g_handles.ma_10_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_10_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_10_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_10_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MA 20
    if (GetIndicatorValue(g_handles.ma_20_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_20_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_20_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_20_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MA 50
    if (GetIndicatorValue(g_handles.ma_50_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_50_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_50_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_50_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MA 100
    if (GetIndicatorValue(g_handles.ma_100_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_100_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_100_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_100_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MA 200
    if (GetIndicatorValue(g_handles.ma_200_sma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_200_ema, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_200_smma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.ma_200_lwma, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    return result;
}

//+------------------------------------------------------------------+
//| Get Adaptive MA values for bar                                   |
//+------------------------------------------------------------------+
string GetAdaptiveMAValues(int bar_index) {
    string result = "";
    double value;

    // DEMA
    if (GetIndicatorValue(g_handles.dema_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.dema_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.dema_50, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // TEMA
    if (GetIndicatorValue(g_handles.tema_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.tema_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.tema_50, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // FrAMA
    if (GetIndicatorValue(g_handles.frama_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.frama_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // AMA
    if (GetIndicatorValue(g_handles.ama_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // VIDyA
    if (GetIndicatorValue(g_handles.vidya_9, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.vidya_12, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    return result;
}

//+------------------------------------------------------------------+
//| Get Trend/Directional values for bar                             |
//+------------------------------------------------------------------+
string GetTrendValues(int bar_index) {
    string result = "";
    double value;

    // SAR
    if (GetIndicatorValue(g_handles.sar_002, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.sar_001, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.sar_003, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // ADX
    if (GetIndicatorValue(g_handles.adx_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.adxwilder_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    return result;
}

//+------------------------------------------------------------------+
//| Get Oscillator values for bar                                    |
//+------------------------------------------------------------------+
string GetOscillatorValues(int bar_index) {
    string result = "";
    double value;

    // RSI
    if (GetIndicatorValue(g_handles.rsi_7, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.rsi_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.rsi_21, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Stochastic 5,3,3
    if (GetIndicatorValue(g_handles.stoch_5_3_3, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.stoch_5_3_3, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Stochastic 14,3,3
    if (GetIndicatorValue(g_handles.stoch_14_3_3, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.stoch_14_3_3, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // CCI
    if (GetIndicatorValue(g_handles.cci_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.cci_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // WPR
    if (GetIndicatorValue(g_handles.wpr_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Momentum
    if (GetIndicatorValue(g_handles.mom_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.mom_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MACD
    if (GetIndicatorValue(g_handles.macd_12_26_9, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.macd_12_26_9, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // OsMA
    if (GetIndicatorValue(g_handles.osma_12_26_9, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // DeMarker
    if (GetIndicatorValue(g_handles.demarker_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // RVI
    if (GetIndicatorValue(g_handles.rvi_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // TriX
    if (GetIndicatorValue(g_handles.trix_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // AC
    if (GetIndicatorValue(g_handles.ac, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // AO
    if (GetIndicatorValue(g_handles.ao, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Bears & Bulls
    if (GetIndicatorValue(g_handles.bears_13, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.bulls_13, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    return result;
}

//+------------------------------------------------------------------+
//| Get Volatility values for bar                                    |
//+------------------------------------------------------------------+
string GetVolatilityValues(int bar_index) {
    string result = "";
    double value;

    // ATR
    if (GetIndicatorValue(g_handles.atr_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.atr_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Bollinger Bands 20,2
    if (GetIndicatorValue(g_handles.bb_20_2, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // Upper
    if (GetIndicatorValue(g_handles.bb_20_2, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // Middle
    if (GetIndicatorValue(g_handles.bb_20_2, bar_index, value, 2)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // Lower

    // Bollinger Bands 20,1.5
    if (GetIndicatorValue(g_handles.bb_20_15, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.bb_20_15, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.bb_20_15, bar_index, value, 2)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Bollinger Bands 20,2.5
    if (GetIndicatorValue(g_handles.bb_20_25, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.bb_20_25, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    if (GetIndicatorValue(g_handles.bb_20_25, bar_index, value, 2)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // StdDev
    if (GetIndicatorValue(g_handles.stddev_20, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Envelopes
    if (GetIndicatorValue(g_handles.envelope_20_01, bar_index, value, 1)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // Upper
    if (GetIndicatorValue(g_handles.envelope_20_01, bar_index, value, 2)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // Lower

    return result;
}

//+------------------------------------------------------------------+
//| Get Volume-Based values for bar                                  |
//+------------------------------------------------------------------+
string GetVolumeBased(int bar_index) {
    string result = "";
    double value;

    // OBV
    if (GetIndicatorValue(g_handles.obv, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // A/D
    if (GetIndicatorValue(g_handles.ad, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // MFI
    if (GetIndicatorValue(g_handles.mfi_14, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Force
    if (GetIndicatorValue(g_handles.force_13, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Chaikin
    if (GetIndicatorValue(g_handles.chaikin_3_10, bar_index, value)) result += "," + DoubleToString(value, 6); else result += ",NaN";

    // Volumes
    result += "," + (string)g_bars[bar_index].tick_volume;

    return result;
}

//+------------------------------------------------------------------+
//| Get indicator value for a given bar                              |
//+------------------------------------------------------------------+
bool GetIndicatorValue(int handle, int bar_index, double &value, int buffer = 0) {
    if (handle == INVALID_HANDLE) return false;

    double buffer_array[1];
    int copied = CopyBuffer(handle, buffer, bar_index, 1, buffer_array);

    if (copied <= 0) return false;

    value = buffer_array[0];
    return !IsNaN(value);
}

//+------------------------------------------------------------------+
//| Check if value is NaN                                            |
//+------------------------------------------------------------------+
bool IsNaN(double value) {
    return (value != value);
}

//+------------------------------------------------------------------+
//| Release all indicator handles                                    |
//+------------------------------------------------------------------+
void ReleaseAllHandles() {
    // Moving Averages
    if (g_handles.ma_5_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_5_sma);
    if (g_handles.ma_5_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_5_ema);
    if (g_handles.ma_5_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_5_smma);
    if (g_handles.ma_5_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_5_lwma);

    if (g_handles.ma_10_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_10_sma);
    if (g_handles.ma_10_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_10_ema);
    if (g_handles.ma_10_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_10_smma);
    if (g_handles.ma_10_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_10_lwma);

    if (g_handles.ma_20_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_20_sma);
    if (g_handles.ma_20_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_20_ema);
    if (g_handles.ma_20_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_20_smma);
    if (g_handles.ma_20_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_20_lwma);

    if (g_handles.ma_50_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_50_sma);
    if (g_handles.ma_50_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_50_ema);
    if (g_handles.ma_50_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_50_smma);
    if (g_handles.ma_50_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_50_lwma);

    if (g_handles.ma_100_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_100_sma);
    if (g_handles.ma_100_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_100_ema);
    if (g_handles.ma_100_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_100_smma);
    if (g_handles.ma_100_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_100_lwma);

    if (g_handles.ma_200_sma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_200_sma);
    if (g_handles.ma_200_ema != INVALID_HANDLE) IndicatorRelease(g_handles.ma_200_ema);
    if (g_handles.ma_200_smma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_200_smma);
    if (g_handles.ma_200_lwma != INVALID_HANDLE) IndicatorRelease(g_handles.ma_200_lwma);

    // Adaptive MA
    if (g_handles.dema_10 != INVALID_HANDLE) IndicatorRelease(g_handles.dema_10);
    if (g_handles.dema_20 != INVALID_HANDLE) IndicatorRelease(g_handles.dema_20);
    if (g_handles.dema_50 != INVALID_HANDLE) IndicatorRelease(g_handles.dema_50);

    if (g_handles.tema_10 != INVALID_HANDLE) IndicatorRelease(g_handles.tema_10);
    if (g_handles.tema_20 != INVALID_HANDLE) IndicatorRelease(g_handles.tema_20);
    if (g_handles.tema_50 != INVALID_HANDLE) IndicatorRelease(g_handles.tema_50);

    if (g_handles.frama_14 != INVALID_HANDLE) IndicatorRelease(g_handles.frama_14);
    if (g_handles.frama_20 != INVALID_HANDLE) IndicatorRelease(g_handles.frama_20);

    if (g_handles.ama_10 != INVALID_HANDLE) IndicatorRelease(g_handles.ama_10);

    if (g_handles.vidya_9 != INVALID_HANDLE) IndicatorRelease(g_handles.vidya_9);
    if (g_handles.vidya_12 != INVALID_HANDLE) IndicatorRelease(g_handles.vidya_12);

    // Trend/Directional
    if (g_handles.sar_002 != INVALID_HANDLE) IndicatorRelease(g_handles.sar_002);
    if (g_handles.sar_001 != INVALID_HANDLE) IndicatorRelease(g_handles.sar_001);
    if (g_handles.sar_003 != INVALID_HANDLE) IndicatorRelease(g_handles.sar_003);

    if (g_handles.adx_14 != INVALID_HANDLE) IndicatorRelease(g_handles.adx_14);
    if (g_handles.adxwilder_14 != INVALID_HANDLE) IndicatorRelease(g_handles.adxwilder_14);

    // Oscillators
    if (g_handles.rsi_7 != INVALID_HANDLE) IndicatorRelease(g_handles.rsi_7);
    if (g_handles.rsi_14 != INVALID_HANDLE) IndicatorRelease(g_handles.rsi_14);
    if (g_handles.rsi_21 != INVALID_HANDLE) IndicatorRelease(g_handles.rsi_21);

    if (g_handles.stoch_5_3_3 != INVALID_HANDLE) IndicatorRelease(g_handles.stoch_5_3_3);
    if (g_handles.stoch_14_3_3 != INVALID_HANDLE) IndicatorRelease(g_handles.stoch_14_3_3);

    if (g_handles.cci_14 != INVALID_HANDLE) IndicatorRelease(g_handles.cci_14);
    if (g_handles.cci_20 != INVALID_HANDLE) IndicatorRelease(g_handles.cci_20);

    if (g_handles.wpr_14 != INVALID_HANDLE) IndicatorRelease(g_handles.wpr_14);

    if (g_handles.mom_10 != INVALID_HANDLE) IndicatorRelease(g_handles.mom_10);
    if (g_handles.mom_14 != INVALID_HANDLE) IndicatorRelease(g_handles.mom_14);

    if (g_handles.macd_12_26_9 != INVALID_HANDLE) IndicatorRelease(g_handles.macd_12_26_9);
    if (g_handles.osma_12_26_9 != INVALID_HANDLE) IndicatorRelease(g_handles.osma_12_26_9);

    if (g_handles.demarker_14 != INVALID_HANDLE) IndicatorRelease(g_handles.demarker_14);
    if (g_handles.rvi_10 != INVALID_HANDLE) IndicatorRelease(g_handles.rvi_10);
    if (g_handles.trix_14 != INVALID_HANDLE) IndicatorRelease(g_handles.trix_14);

    if (g_handles.ac != INVALID_HANDLE) IndicatorRelease(g_handles.ac);
    if (g_handles.ao != INVALID_HANDLE) IndicatorRelease(g_handles.ao);

    if (g_handles.bears_13 != INVALID_HANDLE) IndicatorRelease(g_handles.bears_13);
    if (g_handles.bulls_13 != INVALID_HANDLE) IndicatorRelease(g_handles.bulls_13);

    // Volatility
    if (g_handles.atr_14 != INVALID_HANDLE) IndicatorRelease(g_handles.atr_14);
    if (g_handles.atr_20 != INVALID_HANDLE) IndicatorRelease(g_handles.atr_20);

    if (g_handles.bb_20_2 != INVALID_HANDLE) IndicatorRelease(g_handles.bb_20_2);
    if (g_handles.bb_20_15 != INVALID_HANDLE) IndicatorRelease(g_handles.bb_20_15);
    if (g_handles.bb_20_25 != INVALID_HANDLE) IndicatorRelease(g_handles.bb_20_25);

    if (g_handles.stddev_20 != INVALID_HANDLE) IndicatorRelease(g_handles.stddev_20);
    if (g_handles.envelope_20_01 != INVALID_HANDLE) IndicatorRelease(g_handles.envelope_20_01);

    // Volume-Based
    if (g_handles.obv != INVALID_HANDLE) IndicatorRelease(g_handles.obv);
    if (g_handles.ad != INVALID_HANDLE) IndicatorRelease(g_handles.ad);
    if (g_handles.mfi_14 != INVALID_HANDLE) IndicatorRelease(g_handles.mfi_14);
    if (g_handles.force_13 != INVALID_HANDLE) IndicatorRelease(g_handles.force_13);
    if (g_handles.chaikin_3_10 != INVALID_HANDLE) IndicatorRelease(g_handles.chaikin_3_10);

    Print("All indicator handles released");
}