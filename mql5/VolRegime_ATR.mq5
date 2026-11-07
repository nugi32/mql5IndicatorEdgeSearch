//+------------------------------------------------------------------+
//|                                              VolRegime_ATR.mq5   |
//|  Volatility Regime: ATR Percentile + Expansion/Contraction       |
//+------------------------------------------------------------------+
#property copyright "VolRegime"
#property version   "1.00"
#property description "Line  : ATR percentile (0-100), colored by regime"
#property description "Strip : green = volatility expansion, orange = contraction"
#property description "Blue (low vol)  -> favors mean-reversion / range trading"
#property description "Red (high vol)  -> favors momentum / breakout trading"

#property indicator_separate_window
#property indicator_buffers 7
#property indicator_plots   2
#property indicator_minimum 0
#property indicator_maximum 100

#property indicator_label1  "ATR Percentile"
#property indicator_type1   DRAW_COLOR_LINE
#property indicator_color1  clrDodgerBlue,clrGray,clrOrangeRed
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

#property indicator_label2  "Expansion/Contraction"
#property indicator_type2   DRAW_COLOR_HISTOGRAM
#property indicator_color2  clrLimeGreen,clrOrange
#property indicator_width2  3

//--- inputs
input group "=== ATR ==="
input int    InpATRPeriod   = 14;     // ATR period
input int    InpLookback    = 200;    // Percentile lookback (bars)
input group "=== Expansion / Contraction ==="
input int    InpMAPeriod    = 20;     // ATR moving-average period (baseline)
input double InpExpThresh   = 0.00;   // Threshold: ATR/MA > 1+threshold = expansion
input group "=== Regime ==="
input double InpLowPct      = 30.0;   // Percentile <= this = LOW vol (mean-reversion)
input double InpHighPct     = 70.0;   // Percentile >= this = HIGH vol (momentum)
input group "=== Display & Alerts ==="
input bool   InpShowPanel   = true;   // Show text panel
input bool   InpAlertChange = false;  // Alert on regime change (bar close)

//--- buffers
double bufPct[];       // 0 data  : ATR percentile
double bufPctClr[];    // 1 color : 0=low, 1=mid, 2=high
double bufStrip[];     // 2 data  : expansion/contraction strip
double bufStripClr[];  // 3 color : 0=expansion, 1=contraction
double bufATR[];       // 4 calc  : raw ATR
double bufRatio[];     // 5 calc  : ATR / SMA(ATR)   (for EA via iCustom)
double bufRegime[];    // 6 calc  : 0=low, 1=mid, 2=high (for EA via iCustom)

int      hATR = INVALID_HANDLE;
string   PFX  = "VRG_";
datetime lastAlertBar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   if(InpATRPeriod < 1 || InpLookback < 10 || InpMAPeriod < 2)
   {
      Print("Invalid input parameters.");
      return INIT_PARAMETERS_INCORRECT;
   }

   SetIndexBuffer(0, bufPct,      INDICATOR_DATA);
   SetIndexBuffer(1, bufPctClr,   INDICATOR_COLOR_INDEX);
   SetIndexBuffer(2, bufStrip,    INDICATOR_DATA);
   SetIndexBuffer(3, bufStripClr, INDICATOR_COLOR_INDEX);
   SetIndexBuffer(4, bufATR,      INDICATOR_CALCULATIONS);
   SetIndexBuffer(5, bufRatio,    INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, bufRegime,   INDICATOR_CALCULATIONS);

   int firstBar = InpATRPeriod + InpLookback + InpMAPeriod;
   PlotIndexSetInteger(0, PLOT_DRAW_BEGIN, firstBar);
   PlotIndexSetInteger(1, PLOT_DRAW_BEGIN, firstBar);
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   PlotIndexSetDouble(1, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   // horizontal levels follow the inputs
   IndicatorSetInteger(INDICATOR_LEVELS, 2);
   IndicatorSetDouble(INDICATOR_LEVELVALUE, 0, InpLowPct);
   IndicatorSetDouble(INDICATOR_LEVELVALUE, 1, InpHighPct);
   IndicatorSetInteger(INDICATOR_LEVELCOLOR, 0, clrDimGray);
   IndicatorSetInteger(INDICATOR_LEVELCOLOR, 1, clrDimGray);
   IndicatorSetInteger(INDICATOR_LEVELSTYLE, 0, STYLE_DOT);
   IndicatorSetInteger(INDICATOR_LEVELSTYLE, 1, STYLE_DOT);

   IndicatorSetString(INDICATOR_SHORTNAME,
      StringFormat("VolRegime(ATR%d, LB%d)", InpATRPeriod, InpLookback));
   IndicatorSetInteger(INDICATOR_DIGITS, 1);

   hATR = iATR(_Symbol, _Period, InpATRPeriod);
   if(hATR == INVALID_HANDLE)
   {
      Print("Failed to create iATR handle");
      return INIT_FAILED;
   }
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PFX);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
}

//+------------------------------------------------------------------+
void SetLabel(const int sw, const int row, const string text, const color clr)
{
   string name = PFX + "L" + IntegerToString(row);
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, sw, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 6 + row * 15);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   int firstBar = InpATRPeriod + InpLookback + InpMAPeriod;
   if(rates_total <= firstBar + 1) return 0;
   if(BarsCalculated(hATR) < rates_total) return 0;

   //--- fetch ATR
   int toCopy = (prev_calculated == 0) ? rates_total : rates_total - prev_calculated + 1;
   if(CopyBuffer(hATR, 0, 0, toCopy, bufATR) <= 0) return 0;

   //--- starting point
   int start;
   if(prev_calculated == 0)
   {
      for(int i = 0; i < firstBar && i < rates_total; i++)
      {
         bufPct[i] = EMPTY_VALUE;     bufPctClr[i] = 1;
         bufStrip[i] = EMPTY_VALUE;   bufStripClr[i] = 0;
         bufRatio[i] = EMPTY_VALUE;   bufRegime[i] = EMPTY_VALUE;
      }
      start = firstBar;
   }
   else
      start = MathMax(firstBar, prev_calculated - 1);

   //--- calculate
   for(int i = start; i < rates_total; i++)
   {
      double a = bufATR[i];

      // percentile rank: % of ATR values in the window that are below the current ATR
      int less = 0, equal = 0;
      for(int k = i - InpLookback + 1; k < i; k++)
      {
         if(bufATR[k] < a) less++;
         else if(bufATR[k] == a) equal++;
      }
      double pct = 100.0 * (less + 0.5 * equal) / (double)(InpLookback - 1);

      // ATR relative to its own moving average
      double sum = 0.0;
      for(int k = i - InpMAPeriod + 1; k <= i; k++) sum += bufATR[k];
      double ma    = sum / InpMAPeriod;
      double ratio = (ma > 0.0) ? a / ma : 1.0;

      int regime = 1;
      if(pct <= InpLowPct)       regime = 0;
      else if(pct >= InpHighPct) regime = 2;

      bufPct[i]      = pct;
      bufPctClr[i]   = regime;               // 0 blue, 1 gray, 2 red
      bufRatio[i]    = ratio;
      bufRegime[i]   = regime;
      bufStrip[i]    = 6.0;                  // small strip at the bottom of the window
      bufStripClr[i] = (ratio > 1.0 + InpExpThresh) ? 0 : 1;
   }

   //--- alert on regime change (closed bars only)
   if(InpAlertChange && rates_total > firstBar + 3)
   {
      datetime curBar = time[rates_total - 1];
      if(curBar != lastAlertBar)
      {
         if(lastAlertBar != 0 && bufRegime[rates_total - 2] != bufRegime[rates_total - 3])
         {
            string names[3] = {"LOW VOL (mean-reversion)", "MID VOL (neutral)", "HIGH VOL (momentum)"};
            Alert(_Symbol, " ", EnumToString(_Period), ": regime -> ",
                  names[(int)bufRegime[rates_total - 2]]);
         }
         lastAlertBar = curBar;
      }
   }

   //--- panel
   if(InpShowPanel)
   {
      int sw = ChartWindowFind();
      if(sw >= 0)
      {
         int    L      = rates_total - 1;
         double pct    = bufPct[L];
         double ratio  = bufRatio[L];
         bool   expand = (ratio > 1.0 + InpExpThresh);
         int    reg    = (int)bufRegime[L];

         string regName, advice;
         color  clr;

         if(reg == 0 && !expand)
         {
            regName = "LOW VOL + CONTRACTION (squeeze)"; clr = clrDodgerBlue;
            advice  = "Range/mean-reversion OK. Caution: compression often precedes a breakout.";
         }
         else if(reg == 0 && expand)
         {
            regName = "LOW VOL + EXPANSION (transition)"; clr = clrDeepSkyBlue;
            advice  = "Volatility waking up from lows. Fade edge weakening, watch for breakout.";
         }
         else if(reg == 2 && expand)
         {
            regName = "HIGH VOL + EXPANSION (trending)"; clr = clrOrangeRed;
            advice  = "Momentum/breakout regime. Avoid fading / mean-reversion.";
         }
         else if(reg == 2 && !expand)
         {
            regName = "HIGH VOL + CONTRACTION (cooling)"; clr = clrOrange;
            advice  = "Momentum fading. Mean-reversion may start to work, stay cautious.";
         }
         else
         {
            regName = expand ? "MID VOL + EXPANSION" : "MID VOL + CONTRACTION"; clr = clrSilver;
            advice  = "Neutral regime. Neither style has a dominant edge.";
         }

         SetLabel(sw, 0, "Regime : " + regName, clr);
         SetLabel(sw, 1, StringFormat("ATR %.1f pts | Pctl %.0f | ATR/MA ratio %.2f",
                                      bufATR[L] / _Point, pct, ratio), clrSilver);
         SetLabel(sw, 2, advice, clrGray);
      }
   }
   return rates_total;
}
//+------------------------------------------------------------------+