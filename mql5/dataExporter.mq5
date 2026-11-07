//+------------------------------------------------------------------+
//|                                                  DataExporter.mq5 |
//|                                                                  |
//| Expert Advisor for MT5 Strategy Tester that exports historical   |
//| OHLCV data and comprehensive technical indicators to a single    |
//| CSV file for research/analysis in Python. Runs bar-by-bar during |
//| backtest and exports data incrementally.                         |
//|                                                                  |
//| v1.01: added custom indicators VolRegime_ATR and PriceStructure  |
//| v1.02: added economic calendar support (single file, two modes): |
//|   1) LIVE chart  : exports the MT5 economic calendar to a CSV    |
//|                    (calendar functions do NOT work in the tester,|
//|                     error 4014, so this must run on a live chart)|
//|   2) TESTER      : loads that CSV and appends news feature       |
//|                    columns to every exported bar row.            |
//| Calendar times are broker SERVER time = tester time.             |
//+------------------------------------------------------------------+
#property copyright "DataExporter"
#property link      "https://www.mql5.com"
#property version   "1.02"
#property strict
#property description "Exports indicator data (+ economic calendar features) to CSV during backtest"
#property description "Step 1: attach to a LIVE chart once to export the calendar CSV"
#property description "Step 2: run in Strategy Tester to export bars + news features"

//--- Custom indicators used by the Strategy Tester (compiled .ex5 must exist).
//--- If the indicators live in a sub-folder of MQL5\Indicators (or next to this EA),
//--- put the folder in the path here AND in the two names below, e.g. "MyFolder\\VolRegime_ATR".
#property tester_indicator "VolRegime_ATR.ex5"
#property tester_indicator "PriceStructure.ex5"

#define CUSTOM_IND_VOLREGIME    "VolRegime_ATR"
#define CUSTOM_IND_PRICESTRUCT  "PriceStructure"

#include <Trade\Trade.mqh>

//--- Inputs: economic calendar
input group "=== Calendar export (LIVE chart only) ==="
input bool     InpExportCalendar     = true;                 // Export calendar CSV when attached to a live chart
input bool     InpLiveCalendarOnly   = true;                 // On live chart: stop after calendar export (no bar export)
input datetime InpCalFrom            = D'2020.01.01 00:00';  // Calendar export: start date
input datetime InpCalTo              = 0;                    // Calendar export: end date (0 = now)
input ENUM_CALENDAR_EVENT_IMPORTANCE InpCalMinImportance = CALENDAR_IMPORTANCE_LOW; // Calendar export: minimum importance
input string   InpCalCurrencies      = "";                   // Calendar export: currencies, comma-separated (empty = all)
input int      InpCalChunkDays       = 60;                   // Calendar export: days per request
input group "=== Calendar file & news features ==="
input string   InpCalFile            = "economic_calendar.csv"; // Calendar CSV file name
input bool     InpCalUseCommon       = true;                 // Calendar CSV in Common\Files (readable from the tester)
input bool     InpAddNewsColumns     = true;                 // Append news feature columns to the bar CSV
input string   InpNewsCurrencies     = "";                   // News currencies (empty = auto: base + profit currency of symbol)
input ENUM_CALENDAR_EVENT_IMPORTANCE InpNewsMinImportance = CALENDAR_IMPORTANCE_HIGH; // News features: minimum importance
input int      InpNewsWindowMin      = 30;                   // news_in_window = 1 if an event is within +/- N minutes

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

//--- News events loaded from the calendar CSV (sorted by time)
datetime g_news_t[];
int      g_news_imp[];
double   g_news_sur[];     // actual - forecast (EMPTY_VALUE if not available)
int      g_news_n = 0;

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

    // Custom indicators (VolRegime_ATR / PriceStructure)
    int volregime;
    int pricestruct;
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

    // ---- LIVE chart: export the economic calendar (not possible in the tester)
    bool in_tester = (bool)MQLInfoInteger(MQL_TESTER);
    if (!in_tester && InpExportCalendar) {
        ExportCalendar();
        if (InpLiveCalendarOnly) {
            Print("Calendar export finished. Live-calendar-only mode: EA will stop now.");
            Print("Next step: run this EA in the Strategy Tester to export bars + news features.");
            ExpertRemove();
            return INIT_SUCCEEDED;
        }
    }

    // Determine total bars available
    g_bars_total = Bars(g_symbol, g_timeframe);
    if (g_bars_total <= 0) {
        if (in_tester) {
            // In the tester there may be no bars BEFORE the start date; bars arrive as the test runs.
            Print("WARNING: no bars before the test start date yet - continuing (bars arrive during the test).");
            g_bars_total = 0;
        } else {
            Print("ERROR: No bars available for ", g_symbol, " on timeframe ", g_timeframe);
            return INIT_FAILED;
        }
    }

    Print("===== DataExporter START (Tester Mode) =====");
    Print("Symbol: ", g_symbol, " | Timeframe: ", TimeframeToString(g_timeframe));
    Print("Total bars in history: ", g_bars_total);

    // Load base OHLCV data
    if (!LoadBarData()) {
        Print("ERROR: Failed to load bar data");
        return INIT_FAILED;
    }

    // Load economic calendar CSV (for news feature columns)
    if (InpAddNewsColumns) {
        if (!LoadNewsCalendar())
            Print("WARNING: news calendar not loaded. News columns will be NaN. ",
                  "Run this EA once on a live chart to create ", InpCalFile);
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

void WriteBarToCSVLive() {
    if (g_file_handle == INVALID_HANDLE) return;

    datetime t = iTime(g_symbol, g_timeframe, 1);
    double o = iOpen(g_symbol, g_timeframe, 1);
    double h = iHigh(g_symbol, g_timeframe, 1);
    double l = iLow(g_symbol, g_timeframe, 1);
    double c = iClose(g_symbol, g_timeframe, 1);
    long tv = iVolume(g_symbol, g_timeframe, 1);
    long rv = iRealVolume(g_symbol, g_timeframe, 1);

    string time_str = TimeToString(t, TIME_DATE | TIME_MINUTES);
    StringReplace(time_str, ".", "");

    string row = time_str + ",";
    row += DoubleToString(o, 6) + ",";
    row += DoubleToString(h, 6) + ",";
    row += DoubleToString(l, 6) + ",";
    row += DoubleToString(c, 6) + ",";
    row += (string)tv + ",";
    row += (string)rv;

    row += GetMAValues(1);
    row += GetAdaptiveMAValues(1);
    row += GetTrendValues(1);
    row += GetOscillatorValues(1);
    row += GetVolatilityValues(1);
    row += GetVolumeBased(1);
    row += GetVolRegimeValues(1);
    row += GetPriceStructureValues(1);
    row += GetNewsValues(t);

    FileWrite(g_file_handle, row);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
datetime g_last_bar_time = 0;

void OnTick() {
    if (!g_csv_initialized || g_export_complete) return;

    datetime current_bar_time = iTime(g_symbol, g_timeframe, 0);

    if (current_bar_time == g_last_bar_time) return;
    g_last_bar_time = current_bar_time;

    int total_bars = Bars(g_symbol, g_timeframe);
    int progress_percent = 0; // hitung sesuai kebutuhan

    Comment("DataExporter Progress: bars=", total_bars);

    WriteBarToCSVLive();

    static int last_total_bars = 0;
    if (total_bars == last_total_bars) {
        g_export_complete = true;
        OnDeinit(REASON_PROGRAM);
    }
    last_total_bars = total_bars;
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

    // Custom: VolRegime_ATR (regime: 0=low vol, 1=mid, 2=high vol)
    header += ",volregime_atr_pctl,volregime_atr_ratio,volregime_regime";

    // Custom: PriceStructure (distances = (level - price) / ATR, + = level above price)
    header += ",ps_dist_pdh_atr,ps_dist_pdl_atr,ps_dist_sess_h_atr,ps_dist_sess_l_atr";
    header += ",ps_dist_round_up_atr,ps_dist_round_dn_atr,ps_gap_atr,ps_gap_fill_pct";

    // Economic calendar / news features (computed at bar close time = bar open + period)
    if (InpAddNewsColumns) {
        header += ",news_min_to_next,news_next_importance";
        header += ",news_min_since_last,news_last_importance,news_last_surprise";
        header += ",news_in_window,news_count_next_24h";
    }

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

    // Custom indicators (default inputs of each indicator are used)
    g_handles.volregime = iCustom(g_symbol, g_timeframe, CUSTOM_IND_VOLREGIME);
    if (g_handles.volregime == INVALID_HANDLE)
        Print("WARNING: failed to load custom indicator ", CUSTOM_IND_VOLREGIME,
              " (error ", GetLastError(), "). Its columns will be NaN.");

    g_handles.pricestruct = iCustom(g_symbol, g_timeframe, CUSTOM_IND_PRICESTRUCT);
    if (g_handles.pricestruct == INVALID_HANDLE)
        Print("WARNING: failed to load custom indicator ", CUSTOM_IND_PRICESTRUCT,
              " (error ", GetLastError(), "). Its columns will be NaN.");

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

    // Add custom indicators
    row += GetVolRegimeValues(bar_index);
    row += GetPriceStructureValues(bar_index);

    // Add news features
    row += GetNewsValues(g_bars[bar_index].time);

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

    // Volumes (read the series directly: g_bars is only a snapshot taken at init and can be
    // empty / out of range in the tester, which stops the EA with 'array out of range')
    result += "," + (string)iVolume(g_symbol, g_timeframe, bar_index);

    return result;
}

//+------------------------------------------------------------------+
//| Get VolRegime_ATR values for bar                                 |
//| Indicator buffers: 0 = ATR percentile, 5 = ATR/MA ratio,         |
//| 6 = regime (0 low vol / 1 mid / 2 high vol)                      |
//+------------------------------------------------------------------+
string GetVolRegimeValues(int bar_index) {
    string result = "";
    double value;

    if (GetCustomValue(g_handles.volregime, bar_index, value, 0)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // ATR percentile
    if (GetCustomValue(g_handles.volregime, bar_index, value, 5)) result += "," + DoubleToString(value, 6); else result += ",NaN"; // ATR / MA ratio
    if (GetCustomValue(g_handles.volregime, bar_index, value, 6)) result += "," + DoubleToString(value, 0); else result += ",NaN"; // Regime

    return result;
}

//+------------------------------------------------------------------+
//| Get PriceStructure values for bar                                |
//| Indicator buffers 0..7 (distance = (level - price) / ATR):       |
//| PDH, PDL, PrevSession H, PrevSession L, RoundUp, RoundDown,      |
//| Gap (ATR), Gap fill %                                            |
//+------------------------------------------------------------------+
string GetPriceStructureValues(int bar_index) {
    string result = "";
    double value;

    for (int b = 0; b < 8; b++) {
        if (GetCustomValue(g_handles.pricestruct, bar_index, value, b)) result += "," + DoubleToString(value, 6); else result += ",NaN";
    }

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
//| Get custom indicator value (also treats EMPTY_VALUE as missing)  |
//+------------------------------------------------------------------+
bool GetCustomValue(int handle, int bar_index, double &value, int buffer = 0) {
    if (handle == INVALID_HANDLE) return false;

    double buffer_array[1];
    int copied = CopyBuffer(handle, buffer, bar_index, 1, buffer_array);

    if (copied <= 0) return false;

    value = buffer_array[0];
    if (IsNaN(value) || value == EMPTY_VALUE || MathAbs(value) >= 1.0e300) return false;
    return true;
}

//+------------------------------------------------------------------+
//| Check if value is NaN                                            |
//+------------------------------------------------------------------+
bool IsNaN(double value) {
    return (value != value);
}

//+==================================================================+
//|                    ECONOMIC CALENDAR SECTION                     |
//+==================================================================+

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
string CalIso(const datetime t) {
    MqlDateTime d;
    TimeToStruct(t, d);
    return StringFormat("%04d-%02d-%02d %02d:%02d:%02d", d.year, d.mon, d.day, d.hour, d.min, d.sec);
}

string CalClean(string s) {
    StringReplace(s, ",", " ");
    StringReplace(s, "\"", "");
    StringReplace(s, "\r", " ");
    StringReplace(s, "\n", " ");
    return s;
}

string CalNum(const bool has, const double v, const int digits) {
    if (!has || !MathIsValidNumber(v)) return "";
    return DoubleToString(v, digits);
}

// split "USD, eur" -> {"USD","EUR"}; returns count
int CalParseList(const string src, string &out[]) {
    ArrayResize(out, 0);
    int n = 0;
    if (StringLen(src) == 0) return 0;
    string parts[];
    int np = StringSplit(src, ',', parts);
    for (int i = 0; i < np; i++) {
        StringTrimLeft(parts[i]);
        StringTrimRight(parts[i]);
        StringToUpper(parts[i]);
        if (parts[i] == "") continue;
        ArrayResize(out, n + 1);
        out[n++] = parts[i];
    }
    return n;
}

bool CalInList(const string cur, const string &list[], const int n) {
    if (n == 0) return true;
    for (int i = 0; i < n; i++)
        if (list[i] == cur) return true;
    return false;
}

//--- country cache (used by the live export)
long   g_cal_cid[];
string g_cal_ccode[];
string g_cal_ccur[];

bool CalGetCountry(const long id, string &code, string &cur) {
    int n = ArraySize(g_cal_cid);
    for (int i = 0; i < n; i++) {
        if (g_cal_cid[i] == id) {
            code = g_cal_ccode[i];
            cur  = g_cal_ccur[i];
            return true;
        }
    }

    MqlCalendarCountry c;
    if (!CalendarCountryById(id, c)) return false;

    ArrayResize(g_cal_cid, n + 1);
    ArrayResize(g_cal_ccode, n + 1);
    ArrayResize(g_cal_ccur, n + 1);
    g_cal_cid[n]   = id;
    g_cal_ccode[n] = c.code;
    g_cal_ccur[n]  = c.currency;
    code = c.code;
    cur  = c.currency;
    return true;
}

//+------------------------------------------------------------------+
//| LIVE ONLY: export the MT5 economic calendar to CSV               |
//+------------------------------------------------------------------+
bool ExportCalendar() {
    if (MQLInfoInteger(MQL_TESTER)) {
        Print("Calendar functions do not work in the Strategy Tester. Run on a live chart.");
        return false;
    }

    datetime to = (InpCalTo == 0) ? TimeTradeServer() : InpCalTo;
    if (InpCalFrom >= to) {
        Print("Calendar export: invalid date range.");
        return false;
    }

    string curs[];
    int nc = CalParseList(InpCalCurrencies, curs);

    int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
    if (InpCalUseCommon) flags |= FILE_COMMON;
    int h = FileOpen(InpCalFile, flags, ',', CP_UTF8);
    if (h == INVALID_HANDLE) {
        Print("Calendar export: cannot open file ", InpCalFile, " error ", GetLastError());
        return false;
    }

    FileWrite(h, "time_server", "event_id", "country", "currency", "event_name",
                 "importance", "sector", "event_type", "unit", "multiplier",
                 "actual", "forecast", "previous", "revised_previous",
                 "impact_type", "revision");

    long total = 0;
    datetime from = InpCalFrom;
    long step = (long)MathMax(1, InpCalChunkDays) * 86400;

    while (from < to && !IsStopped()) {
        datetime chunk_to = (datetime)MathMin((double)((long)from + step), (double)to);

        MqlCalendarValue vals[];
        ResetLastError();
        int n = CalendarValueHistory(vals, from, chunk_to);
        if (n < 0) {
            int err = GetLastError();
            Print("CalendarValueHistory failed, error ", err, " (", CalIso(from), " -> ", CalIso(chunk_to), ")");
            if (err == 4014) { Print("Not allowed in tester."); break; }
        } else {
            for (int i = 0; i < n; i++) {
                MqlCalendarEvent ev;
                if (!CalendarEventById(vals[i].event_id, ev)) continue;
                if (ev.importance < InpCalMinImportance) continue;

                string code, cur;
                if (!CalGetCountry(ev.country_id, code, cur)) { code = ""; cur = ""; }
                if (!CalInList(cur, curs, nc)) continue;

                int dg = (int)ev.digits;

                FileWrite(h,
                    CalIso(vals[i].time),
                    (string)vals[i].event_id,
                    code,
                    cur,
                    CalClean(ev.name),
                    (string)(int)ev.importance,
                    (string)(int)ev.sector,
                    (string)(int)ev.type,
                    (string)(int)ev.unit,
                    (string)(int)ev.multiplier,
                    CalNum(vals[i].HasActualValue(),   vals[i].GetActualValue(),   dg),
                    CalNum(vals[i].HasForecastValue(), vals[i].GetForecastValue(), dg),
                    CalNum(vals[i].HasPreviousValue(), vals[i].GetPreviousValue(), dg),
                    CalNum(vals[i].HasRevisedValue(),  vals[i].GetRevisedValue(),  dg),
                    (string)(int)vals[i].impact_type,
                    (string)vals[i].revision);
                total++;
            }
        }

        Comment("DataExporter - calendar export: ", CalIso(chunk_to), "  rows=", total);
        from = (datetime)((long)chunk_to + 1);
    }

    FileClose(h);
    Comment("");
    Print("Calendar export done. Rows written: ", total, " -> ",
          InpCalUseCommon ? "Common\\Files\\" : "MQL5\\Files\\", InpCalFile);
    return true;
}

//+------------------------------------------------------------------+
//| Load the calendar CSV into memory (sorted by time), keeping only |
//| events that match the news currencies and minimum importance     |
//+------------------------------------------------------------------+
bool LoadNewsCalendar() {
    g_news_n = 0;
    ArrayResize(g_news_t, 0);
    ArrayResize(g_news_imp, 0);
    ArrayResize(g_news_sur, 0);

    // currencies used for news features
    string curs[];
    int nc = CalParseList(InpNewsCurrencies, curs);
    if (nc == 0) {
        string base = SymbolInfoString(g_symbol, SYMBOL_CURRENCY_BASE);
        string prof = SymbolInfoString(g_symbol, SYMBOL_CURRENCY_PROFIT);
        StringToUpper(base);
        StringToUpper(prof);
        if (base != "") { ArrayResize(curs, nc + 1); curs[nc++] = base; }
        if (prof != "" && prof != base) { ArrayResize(curs, nc + 1); curs[nc++] = prof; }
    }

    int flags = FILE_READ | FILE_TXT | FILE_ANSI;
    if (InpCalUseCommon) flags |= FILE_COMMON;
    int fh = FileOpen(InpCalFile, flags, 0, CP_UTF8);
    if (fh == INVALID_HANDLE) {
        Print("News calendar: cannot open ", InpCalFile, " (error ", GetLastError(), ")");
        return false;
    }

    datetime tmp_t[];
    int      tmp_i[];
    double   tmp_s[];
    int cnt = 0;

    FileReadString(fh); // header line

    while (!FileIsEnding(fh)) {
        string line = FileReadString(fh);
        if (StringLen(line) < 10) continue;

        string f[];
        int nf = StringSplit(line, ',', f);
        if (nf < 15) continue;

        int imp = (int)StringToInteger(f[5]);
        if (imp < (int)InpNewsMinImportance) continue;

        string cur = f[3];
        StringToUpper(cur);
        if (!CalInList(cur, curs, nc)) continue;

        string ts = f[0];
        StringReplace(ts, "-", ".");
        datetime t = StringToTime(ts);
        if (t <= 0) continue;

        double sur = EMPTY_VALUE;
        if (f[10] != "" && f[11] != "") sur = StringToDouble(f[10]) - StringToDouble(f[11]);

        ArrayResize(tmp_t, cnt + 1);
        ArrayResize(tmp_i, cnt + 1);
        ArrayResize(tmp_s, cnt + 1);
        tmp_t[cnt] = t;
        tmp_i[cnt] = imp;
        tmp_s[cnt] = sur;
        cnt++;
    }
    FileClose(fh);

    if (cnt == 0) {
        Print("News calendar: no matching events in ", InpCalFile, " (check currencies / importance / date range).");
        return false;
    }
    if (cnt >= 1048576) {
        Print("News calendar: too many events (", cnt, "). Raise the minimum importance or narrow currencies.");
        return false;
    }

    // sort by time (key = time << 20 | original index)
    long keys[];
    ArrayResize(keys, cnt);
    for (int i = 0; i < cnt; i++) keys[i] = (((long)tmp_t[i]) << 20) | (long)i;
    ArraySort(keys);

    ArrayResize(g_news_t, cnt);
    ArrayResize(g_news_imp, cnt);
    ArrayResize(g_news_sur, cnt);
    for (int k = 0; k < cnt; k++) {
        int idx = (int)(keys[k] & 0xFFFFF);
        g_news_t[k]   = tmp_t[idx];
        g_news_imp[k] = tmp_i[idx];
        g_news_sur[k] = tmp_s[idx];
    }
    g_news_n = cnt;

    string cur_list = "";
    for (int c = 0; c < nc; c++) cur_list += (c > 0 ? "," : "") + curs[c];
    Print("News calendar loaded: ", g_news_n, " events | currencies: ", cur_list,
          " | min importance: ", (int)InpNewsMinImportance);
    return true;
}

//+------------------------------------------------------------------+
//| First index whose event time is strictly greater than x          |
//+------------------------------------------------------------------+
int NewsUpperBound(const datetime x) {
    int lo = 0, hi = g_news_n;
    while (lo < hi) {
        int mid = (lo + hi) / 2;
        if (g_news_t[mid] <= x) lo = mid + 1;
        else hi = mid;
    }
    return lo;
}

//+------------------------------------------------------------------+
//| News feature columns for the bar that opened at bar_time.        |
//| Reference time = bar close (open + period): only information     |
//| known at that moment is used (no lookahead).                     |
//| Columns: min_to_next, next_importance, min_since_last,           |
//|          last_importance, last_surprise (actual-forecast),       |
//|          in_window (+/- InpNewsWindowMin), count_next_24h        |
//+------------------------------------------------------------------+
string GetNewsValues(const datetime bar_time) {
    if (!InpAddNewsColumns) return "";
    if (g_news_n == 0) return ",NaN,NaN,NaN,NaN,NaN,NaN,NaN";

    datetime ref = bar_time + (datetime)PeriodSeconds(g_timeframe);
    int ub = NewsUpperBound(ref);

    string r = "";
    double min_next = -1.0, min_last = -1.0;

    // next event
    if (ub < g_news_n) {
        min_next = (double)((long)g_news_t[ub] - (long)ref) / 60.0;
        r += "," + DoubleToString(min_next, 1) + "," + IntegerToString(g_news_imp[ub]);
    } else {
        r += ",NaN,NaN";
    }

    // last event
    if (ub > 0) {
        int j = ub - 1;
        min_last = (double)((long)ref - (long)g_news_t[j]) / 60.0;
        r += "," + DoubleToString(min_last, 1) + "," + IntegerToString(g_news_imp[j]);
        if (g_news_sur[j] != EMPTY_VALUE) r += "," + DoubleToString(g_news_sur[j], 6);
        else r += ",NaN";
    } else {
        r += ",NaN,NaN,NaN";
    }

    // window flag
    bool in_window = (min_next >= 0.0 && min_next <= InpNewsWindowMin) ||
                     (min_last >= 0.0 && min_last <= InpNewsWindowMin);
    r += "," + (in_window ? "1" : "0");

    // events in the next 24h
    int ub24 = NewsUpperBound(ref + (datetime)86400);
    r += "," + IntegerToString(ub24 - ub);

    return r;
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

    // Custom indicators
    if (g_handles.volregime != INVALID_HANDLE) IndicatorRelease(g_handles.volregime);
    if (g_handles.pricestruct != INVALID_HANDLE) IndicatorRelease(g_handles.pricestruct);

    Print("All indicator handles released");
}