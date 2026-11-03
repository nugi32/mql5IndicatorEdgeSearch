//+------------------------------------------------------------------+
//| spreadExporter.mq5                                               |
//| Script: writes the broker's historical spread of every bar of    |
//| one symbol/timeframe, for scripts/run_mt5_backtest.py            |
//| (--spread-csv) and scripts/calibrate_mt5_spread.py.              |
//|                                                                  |
//| Run it on a chart of the symbol you test. The MT5 tester does    |
//| not model the spread: it takes it from this same history.        |
//| Output: Common\Files\<SYMBOL>_<TF>_spread.csv                    |
//|   time,spread     time = bar open (server time, YYYYMMDD HH:MM)  |
//|                   spread = points                                |
//+------------------------------------------------------------------+
#property copyright "edge_research"
#property version   "1.00"
#property script_show_inputs

input ENUM_TIMEFRAMES InpTimeframe = PERIOD_CURRENT;          // Timeframe (current chart if PERIOD_CURRENT)
input datetime        InpFrom      = D'2010.01.01 00:00';     // First bar to export
input datetime        InpTo        = 0;                       // Last bar (0 = now)
input string          InpFileName  = "";                      // Empty = <SYMBOL>_<TF>_spread.csv

void OnStart()
{
   ENUM_TIMEFRAMES tf = (InpTimeframe == PERIOD_CURRENT) ? (ENUM_TIMEFRAMES)_Period : InpTimeframe;
   datetime to = (InpTo == 0) ? TimeCurrent() : InpTo;

   MqlRates rates[];
   ArraySetAsSeries(rates, false);          // oldest bar first
   int copied = CopyRates(_Symbol, tf, InpFrom, to, rates);
   if(copied <= 0)
   {
      PrintFormat("CopyRates failed for %s %s, error %d (open the chart and scroll back to load history)",
                  _Symbol, EnumToString(tf), GetLastError());
      return;
   }

   string tf_name = StringSubstr(EnumToString(tf), 7);   // "PERIOD_M5" -> "M5"
   string name = (InpFileName == "") ? StringFormat("%s_%s_spread.csv", _Symbol, tf_name) : InpFileName;
   int handle = FileOpen(name, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("Cannot open %s, error %d", name, GetLastError());
      return;
   }

   FileWriteString(handle, "time,spread\n");
   MqlDateTime dt;
   for(int i = 0; i < copied; i++)
   {
      TimeToStruct(rates[i].time, dt);
      FileWriteString(handle, StringFormat("%04d%02d%02d %02d:%02d,%d\n",
                                           dt.year, dt.mon, dt.day, dt.hour, dt.min, rates[i].spread));
   }
   FileClose(handle);
   PrintFormat("Wrote %d bars to Common\\Files\\%s", copied, name);
}
