//+------------------------------------------------------------------+
//|                                          XAUUSD_M5_248_EA.mq5     |
//| Auto-generated from mql5IndicatorEdgeSearch-tradebility          |
//| Edge ID:    XAUUSD_M5_248                                        |
//| Hypothesis: Price rally after rsi_21 < 25.0 AND cci_14 < -100.0  |
//|             AND ma_10_ema > close                                |
//| Direction:  LONG only                                            |
//| Mined on:   M5 (hardcoded -- DO NOT infer from Period())         |
//|                                                                    |
//| Phase 5-6 stats (raw signal, no cost):                            |
//|   Optimal horizon: 1 bar | Freq: 287.1/yr | Baseline: 50.04%      |
//|   Prob(Bull): 56.80% | Effect size: 0.0732 | p(adj)=0.0000e+00    |
//|   CI: [55.37%, 58.23%]                                            |
//| Phase 7 robustness (with cost + ATR SL/TP, see NOTE below):       |
//|   Walk-forward consistent: True | Net Expectancy: 1577.88 pips    |
//|   Expectancy (R): 0.13                                            |
//|                                                                    |
//| *** IMPORTANT -- READ BEFORE LIVE USE ***                         |
//| The Phase 7c numbers above were produced by a run of the pipeline |
//| where config/M5/pipeline_config.yaml had pip_value=0.0001 instead |
//| of the correct 0.01 for XAUUSD, making the simulated spread cost  |
//| ~100x too small (0.003 price units instead of the intended 0.3).  |
//| This bug has now been fixed in the pipeline config, but Phase 5-7 |
//| for M5 has NOT yet been re-run with the corrected cost. The       |
//| expectancy_r=0.13 / net expectancy figures above may not survive  |
//! realistic cost -- re-run the pipeline for M5 and regenerate this  |
//| EA (or at least re-check STRATEGY_GATE_RESULTS.csv for this edge) |
//| before risking real capital on it. The entry LOGIC below (the     |
//| indicator condition itself) is unaffected by the cost bug.        |
//+------------------------------------------------------------------+
#property copyright "mql5IndicatorEdgeSearch-tradebility"
#property version   "1.00"
#property strict
#property description "XAUUSD M5 edge #248: rsi_21<25 AND cci_14<-100 AND ma_10_ema>close (long)"

#include <Trade\Trade.mqh>

//--- Hardcoded to the timeframe this edge was mined on. NEVER use
//    Period() here -- a prior bug computed indicators on the chart's
//    current timeframe instead of the mined one, producing ~250x
//    rarer signals than expected when the EA was attached to the
//    wrong chart timeframe.
#define EA_TIMEFRAME PERIOD_M5

//--- Indicator parameters (must match the values the edge was mined with)
input int    RSI_PERIOD        = 21;      // rsi_21
input double RSI_THRESHOLD     = 25.0;    // rsi_21 < 25.0
input int    CCI_PERIOD        = 14;      // cci_14
input double CCI_THRESHOLD     = -100.0;  // cci_14 < -100.0
input int    MA_PERIOD         = 10;      // ma_10_ema
input ENUM_MA_METHOD MA_METHOD = MODE_EMA;
input int    ATR_PERIOD        = 14;      // atr_14 (used for virtual SL/TP)

//--- Trade management (virtual only -- no broker-side SL/TP, per
//    architectural convention: broker SL/TP can be requoted, hunted,
//    or slipped independently of our own risk model, so every exit is
//    managed and executed by this EA itself).
input double LOT_SIZE          = 0.10;    // Position size
input double SL_ATR_MULT       = 3.0;     // Virtual SL = entry -/+ SL_ATR_MULT * ATR   (Phase 7c: sim_sl_atr_mult)
input double TP_ATR_MULT       = 6.0;     // Virtual TP = entry -/+ TP_ATR_MULT * ATR   (Phase 7c: sim_tp_atr_mult)
input int    MAX_HOLDING_BARS  = 60;      // Force-close if neither SL nor TP hit       (Phase 7c: sim_max_holding_bars)
input int    MAGIC_NUMBER      = 524801;  // Unique per EA/edge (248 encoded in it)
input bool   ENABLE_CSV_LOG    = true;

//--- Global state
CTrade   trade;
int      h_rsi = INVALID_HANDLE;
int      h_cci = INVALID_HANDLE;
int      h_ma  = INVALID_HANDLE;
int      h_atr = INVALID_HANDLE;

datetime last_processed_bar_time = 0;   // new-bar gate
string   csv_filename;

//--- Virtual trade state (survives ticks; rebuilt on restart from the
//    live position + comment, since we never rely on broker SL/TP)
double   v_sl_price   = 0.0;
double   v_tp_price   = 0.0;
datetime v_entry_time = 0;
int      v_entry_bar_shift_base = 0;    // bars-held is computed from this

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MAGIC_NUMBER);
   trade.SetTypeFillingBySymbol(_Symbol);

   h_rsi = iRSI(_Symbol, EA_TIMEFRAME, RSI_PERIOD, PRICE_CLOSE);
   h_cci = iCCI(_Symbol, EA_TIMEFRAME, CCI_PERIOD, PRICE_TYPICAL);
   h_ma  = iMA(_Symbol, EA_TIMEFRAME, MA_PERIOD, 0, MA_METHOD, PRICE_CLOSE);
   h_atr = iATR(_Symbol, EA_TIMEFRAME, ATR_PERIOD);

   if(h_rsi == INVALID_HANDLE || h_cci == INVALID_HANDLE ||
      h_ma  == INVALID_HANDLE || h_atr == INVALID_HANDLE)
   {
      Print("XAUUSD_M5_248_EA: failed to create one or more indicator handles");
      return(INIT_FAILED);
   }

   csv_filename = "XAUUSD_M5_248_" + _Symbol + ".csv";
   if(ENABLE_CSV_LOG)
   {
      int h = FileOpen(csv_filename, FILE_WRITE | FILE_CSV | FILE_ANSI);
      if(h != INVALID_HANDLE)
      {
         FileWrite(h, "entry_time", "entry_price", "sl_price", "tp_price",
                       "exit_time", "exit_price", "exit_reason",
                       "pnl_price_units", "bars_held");
         FileClose(h);
      }
   }

   // Restart-safe recovery: if there's already a live position with our
   // magic number (EA was restarted mid-trade), rebuild the virtual
   // SL/TP from the position's own stored comment instead of assuming
   // there is no open trade.
   RecoverOpenPositionIfAny();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(h_rsi != INVALID_HANDLE) IndicatorRelease(h_rsi);
   if(h_cci != INVALID_HANDLE) IndicatorRelease(h_cci);
   if(h_ma  != INVALID_HANDLE) IndicatorRelease(h_ma);
   if(h_atr != INVALID_HANDLE) IndicatorRelease(h_atr);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Manage any open virtual position on every tick (SL/TP must be
   // checked intrabar, not just on new bars, or we'd give back edge
   // waiting for the next bar close).
   if(HasOpenPosition())
   {
      ManageOpenPosition();
      return; // one position at a time for this edge
   }

   // --- New-bar gate ---
   // Only evaluate the entry condition once per completed M5 bar (index
   // 1 = last fully closed bar), never intrabar on a forming bar 0 --
   // this matches exactly how the Python pipeline evaluated the
   // condition (one row per completed bar) and avoids re-firing the
   // same signal on every tick within the same bar.
   datetime current_bar_time = iTime(_Symbol, EA_TIMEFRAME, 1);
   if(current_bar_time == last_processed_bar_time)
      return;
   if(current_bar_time == 0)
      return; // not enough bars yet
   last_processed_bar_time = current_bar_time;

   if(!CheckEntryCondition())
      return;

   OpenLongPosition();
}

//+------------------------------------------------------------------+
//| Entry condition: rsi_21 < 25.0 AND cci_14 < -100.0                |
//|                   AND ma_10_ema > close                            |
//| Evaluated on the last COMPLETED bar (shift 1), matching the        |
//| known-at convention the edge was mined under.                      |
//+------------------------------------------------------------------+
bool CheckEntryCondition()
{
   double rsi_buf[1], cci_buf[1], ma_buf[1];

   if(CopyBuffer(h_rsi, 0, 1, 1, rsi_buf) <= 0) return false;
   if(CopyBuffer(h_cci, 0, 1, 1, cci_buf) <= 0) return false;
   if(CopyBuffer(h_ma,  0, 1, 1, ma_buf)  <= 0) return false;

   double close_1 = iClose(_Symbol, EA_TIMEFRAME, 1);

   bool cond_rsi = rsi_buf[0] < RSI_THRESHOLD;
   bool cond_cci = cci_buf[0] < CCI_THRESHOLD;
   bool cond_ma  = ma_buf[0]  > close_1;

   return (cond_rsi && cond_cci && cond_ma);
}

//+------------------------------------------------------------------+
//| Open the long position with virtual (EA-managed) SL/TP.           |
//| No broker-side SL/TP is ever sent -- see architectural note above.|
//+------------------------------------------------------------------+
void OpenLongPosition()
{
   double atr_buf[1];
   if(CopyBuffer(h_atr, 0, 1, 1, atr_buf) <= 0 || atr_buf[0] <= 0)
   {
      Print("XAUUSD_M5_248_EA: ATR unavailable, skipping entry");
      return;
   }
   double atr_value = atr_buf[0];

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl  = ask - SL_ATR_MULT * atr_value;
   double tp  = ask + TP_ATR_MULT * atr_value;

   string comment = StringFormat("edge248|sl=%.5f|tp=%.5f", sl, tp);

   if(!trade.Buy(LOT_SIZE, _Symbol, 0.0, 0.0, 0.0, comment))
   {
      Print("XAUUSD_M5_248_EA: Buy failed, error=", GetLastError());
      return;
   }

   v_sl_price   = sl;
   v_tp_price   = tp;
   v_entry_time = TimeCurrent();

   Print(StringFormat(
      "XAUUSD_M5_248_EA: opened LONG @ %.5f  virtual SL=%.5f  virtual TP=%.5f  ATR=%.5f",
      ask, sl, tp, atr_value));
}

//+------------------------------------------------------------------+
//| Check whether we currently hold a position opened by this EA.     |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == MAGIC_NUMBER &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Manage the currently open position: check virtual SL/TP and the   |
//| max-holding-bars timeout, and close via market order when hit --  |
//| never relies on the broker's own SL/TP execution.                 |
//+------------------------------------------------------------------+
void ManageOpenPosition()
{
   ulong ticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t <= 0) continue;
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == MAGIC_NUMBER &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         ticket = t;
         break;
      }
   }
   if(ticket == 0) return;

   double entry_price = PositionGetDouble(POSITION_PRICE_OPEN);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   string reason = "";

   if(bid <= v_sl_price)
      reason = "SL";
   else if(bid >= v_tp_price)
      reason = "TP";
   else
   {
      // Max holding bars timeout, counted in completed EA_TIMEFRAME bars
      int bars_held = iBarShift(_Symbol, EA_TIMEFRAME, v_entry_time, false);
      if(bars_held >= MAX_HOLDING_BARS)
         reason = "TIMEOUT";
   }

   if(reason == "")
      return;

   double exit_price = bid;
   if(trade.PositionClose(ticket))
   {
      int bars_held = iBarShift(_Symbol, EA_TIMEFRAME, v_entry_time, false);
      LogTrade(v_entry_time, entry_price, v_sl_price, v_tp_price,
                TimeCurrent(), exit_price, reason,
                exit_price - entry_price, bars_held);
      Print(StringFormat("XAUUSD_M5_248_EA: closed (%s) @ %.5f  pnl=%.5f",
                          reason, exit_price, exit_price - entry_price));
      v_sl_price = 0.0;
      v_tp_price = 0.0;
      v_entry_time = 0;
   }
   else
   {
      Print("XAUUSD_M5_248_EA: PositionClose failed, error=", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Restart-safe recovery: if the terminal restarted while a position |
//| opened by this EA was still live, rebuild the virtual SL/TP from  |
//| the order comment we stamped it with at entry, instead of losing  |
//| track of the trade's risk levels.                                 |
//+------------------------------------------------------------------+
void RecoverOpenPositionIfAny()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MAGIC_NUMBER) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

      string comment = PositionGetString(POSITION_COMMENT);
      double sl = 0.0, tp = 0.0;
      if(ParseVirtualLevelsFromComment(comment, sl, tp))
      {
         v_sl_price   = sl;
         v_tp_price   = tp;
         v_entry_time = (datetime)PositionGetInteger(POSITION_TIME);
         Print(StringFormat(
            "XAUUSD_M5_248_EA: recovered open position, virtual SL=%.5f TP=%.5f",
            v_sl_price, v_tp_price));
      }
      else
      {
         // Comment missing/unparseable (e.g. manually opened trade with
         // our magic number by coincidence) -- fall back to a fresh
         // ATR-based estimate from current conditions so the position
         // is never left with sl=tp=0 (which would never trigger).
         double atr_buf[1];
         double entry_price = PositionGetDouble(POSITION_PRICE_OPEN);
         if(CopyBuffer(h_atr, 0, 0, 1, atr_buf) > 0 && atr_buf[0] > 0)
         {
            v_sl_price = entry_price - SL_ATR_MULT * atr_buf[0];
            v_tp_price = entry_price + TP_ATR_MULT * atr_buf[0];
         }
         v_entry_time = (datetime)PositionGetInteger(POSITION_TIME);
         Print("XAUUSD_M5_248_EA: recovered position with fallback SL/TP (comment unparseable)");
      }
      return;
   }
}

bool ParseVirtualLevelsFromComment(const string comment, double &sl, double &tp)
{
   int sl_pos = StringFind(comment, "sl=");
   int tp_pos = StringFind(comment, "tp=");
   if(sl_pos < 0 || tp_pos < 0) return false;

   string sl_str = StringSubstr(comment, sl_pos + 3, tp_pos - (sl_pos + 3) - 1);
   string tp_str = StringSubstr(comment, tp_pos + 3);

   sl = StringToDouble(sl_str);
   tp = StringToDouble(tp_str);
   return (sl > 0 && tp > 0);
}

//+------------------------------------------------------------------+
//| CSV trade logging                                                  |
//+------------------------------------------------------------------+
void LogTrade(datetime entry_time, double entry_price, double sl_price, double tp_price,
              datetime exit_time, double exit_price, string reason,
              double pnl_price_units, int bars_held)
{
   if(!ENABLE_CSV_LOG) return;

   int h = FileOpen(csv_filename, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI);
   if(h == INVALID_HANDLE) return;

   FileSeek(h, 0, SEEK_END);
   FileWrite(h,
      TimeToString(entry_time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(entry_price, _Digits),
      DoubleToString(sl_price, _Digits),
      DoubleToString(tp_price, _Digits),
      TimeToString(exit_time, TIME_DATE | TIME_MINUTES | TIME_SECONDS),
      DoubleToString(exit_price, _Digits),
      reason,
      DoubleToString(pnl_price_units, _Digits),
      IntegerToString(bars_held));
   FileClose(h);
}
