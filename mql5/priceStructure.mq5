//+------------------------------------------------------------------+
//|                                              PriceStructure.mq5  |
//|  Price Structure: Prev Day H/L, Prev Session H/L, Round Numbers, |
//|  Daily Gap, plus distance (points & ATR) to every level          |
//+------------------------------------------------------------------+
#property copyright "PriceStructure"
#property version   "1.00"
#property description "Levels: PDH/PDL, previous session High/Low, prev close (gap), round numbers 00/50"
#property description "Panel shows distance to each level in points and ATR multiples"

#property indicator_chart_window
#property indicator_buffers 8
#property indicator_plots   0

//--- inputs
input group "=== ATR (distance normalization) ==="
input ENUM_TIMEFRAMES InpATRTF   = PERIOD_CURRENT; // ATR timeframe
input int    InpATRPeriod        = 14;             // ATR period
input double InpNearATR          = 0.25;           // 'Near' if distance <= x ATR

input group "=== Sessions (SERVER hours, comma-separated) ==="
input string InpSessionStarts    = "0,8,16";       // Session start hours (e.g. Asia,London,NY)
input int    InpMaxSessionLookBack = 6;            // Max sessions to search back (skips weekends)
input ENUM_TIMEFRAMES InpSessionTF = PERIOD_CURRENT; // Timeframe used to find session H/L (tester 'Open prices' needs >= tester TF)

input group "=== Round numbers ==="
input double InpRoundStep        = 0.0;            // Price step (0 = auto). E.g. 0.0050, 0.50, 50
input int    InpRoundLevels      = 3;              // Number of levels above & below price

input group "=== Gap ==="
input double InpMinGapATR        = 0.10;           // Gap is significant if >= x ATR

input group "=== Display ==="
input bool   InpDrawLines        = true;           // Draw level lines on chart
input bool   InpShowPanel        = true;           // Show distance panel
input int    InpPanelX           = 10;             // Panel X position
input int    InpPanelY           = 45;             // Panel Y position
input int    InpLabelShiftBars   = 3;              // Shift line labels to the right (bars)
input color  InpClrPDH           = clrTomato;      // PDH color
input color  InpClrPDL           = clrDodgerBlue;  // PDL color
input color  InpClrSessH         = clrOrange;      // Prev session high color
input color  InpClrSessL         = clrDeepSkyBlue; // Prev session low color
input color  InpClrPDC           = clrGold;        // Prev close (gap) color
input color  InpClrRoundMajor    = clrSlateGray;   // Major round number color (00)
input color  InpClrRoundMinor    = clrDimGray;     // Minor round number color (50)
input color  InpClrNear          = clrYellow;      // Panel text color when a level is near

//--- buffers (for EA via iCustom; filled on the last bar / shift 0)
// Distance convention: (level - price) / ATR  -> positive = level is above price
double bPDH[];        // 0: distance to Prev Day High (ATR)
double bPDL[];        // 1: distance to Prev Day Low (ATR)
double bSessH[];      // 2: distance to Prev Session High (ATR)
double bSessL[];      // 3: distance to Prev Session Low (ATR)
double bRoundUp[];    // 4: distance to nearest round number above (ATR)
double bRoundDn[];    // 5: distance to nearest round number below (ATR, negative)
double bGap[];        // 6: gap size (ATR), + = gap up
double bGapFill[];    // 7: percent of gap already filled (0-100)

int      hATR = INVALID_HANDLE;
string   PFX  = "PST_";
int      g_sess[];
int      g_nSess = 0;

// level cache
bool     g_init = false;
datetime g_lastBar = 0;
double   g_pdh, g_pdl, g_pdc;
double   g_sh, g_sl;
bool     g_sessOK = false;
datetime g_sessStart = 0, g_sessEnd = 0;
datetime g_t0 = 0, g_t1 = 0;
double   g_lastRoundBelow = -1;

//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, bPDH,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(1, bPDL,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(2, bSessH,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(3, bSessL,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(4, bRoundUp, INDICATOR_CALCULATIONS);
   SetIndexBuffer(5, bRoundDn, INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, bGap,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(7, bGapFill, INDICATOR_CALCULATIONS);

   // parse session hours
   string parts[];
   int n = StringSplit(InpSessionStarts, ',', parts);
   ArrayResize(g_sess, 0);
   g_nSess = 0;
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      if(parts[i] == "") continue;
      int h = (int)StringToInteger(parts[i]);
      if(h < 0 || h > 23) continue;
      ArrayResize(g_sess, g_nSess + 1);
      g_sess[g_nSess++] = h;
   }
   if(g_nSess == 0)
   {
      ArrayResize(g_sess, 1);
      g_sess[0] = 0;
      g_nSess = 1;
   }
   ArraySort(g_sess);

   hATR = iATR(_Symbol, InpATRTF, InpATRPeriod);
   if(hATR == INVALID_HANDLE)
   {
      Print("Failed to create iATR handle");
      return INIT_FAILED;
   }
   IndicatorSetString(INDICATOR_SHORTNAME, "PriceStructure");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PFX);
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Round number step                                                |
//+------------------------------------------------------------------+
double GetRoundStep(const double price)
{
   if(InpRoundStep > 0.0) return InpRoundStep;
   if(_Digits == 5 || _Digits == 4) return 0.0050;   // 50 pips -> xx00 / xx50
   if(_Digits == 3) return 0.50;                     // JPY pairs
   if(price <= 0.0) return 1.0;
   double mag = MathPow(10.0, MathFloor(MathLog10(price)));
   return mag / 20.0;                                // XAU 2350 -> 50, BTC 65000 -> 500
}

//+------------------------------------------------------------------+
//| Previous session High/Low (searches back if empty, e.g. weekend) |
//+------------------------------------------------------------------+
bool GetPrevSession(double &hi, double &lo, datetime &st, datetime &en)
{
   datetime now  = TimeCurrent();
   long     base = (long)now - ((long)now % 86400);

   datetime B[];
   int n = 0;
   for(int d = -8; d <= 0; d++)
      for(int j = 0; j < g_nSess; j++)
      {
         datetime t = (datetime)(base + (long)d * 86400 + (long)g_sess[j] * 3600);
         if(t <= now)
         {
            ArrayResize(B, n + 1);
            B[n++] = t;
         }
      }
   if(n < 2) return false;

   for(int k = 1; k <= InpMaxSessionLookBack; k++)
   {
      int idx = n - 1 - k;
      if(idx < 0) break;
      st = B[idx];
      en = B[idx + 1];

      double h[], l[];
      int ch = CopyHigh(_Symbol, InpSessionTF, st, en - 1, h);
      int cl = CopyLow (_Symbol, InpSessionTF, st, en - 1, l);
      if(ch > 0 && cl > 0)
      {
         hi = h[ArrayMaximum(h)];
         lo = l[ArrayMinimum(l)];
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Draw a level line + label                                        |
//+------------------------------------------------------------------+
void DrawLevel(const string key, const double price, const color clr,
               const ENUM_LINE_STYLE style, const int width, const string txt)
{
   if(!InpDrawLines) return;
   string ln = PFX + "L_" + key;
   string tx = PFX + "T_" + key;

   if(ObjectFind(0, ln) < 0)
   {
      ObjectCreate(0, ln, OBJ_TREND, 0, g_t1, price, g_t0, price);
      ObjectSetInteger(0, ln, OBJPROP_RAY_RIGHT, true);
      ObjectSetInteger(0, ln, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, ln, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, ln, OBJPROP_BACK, true);
   }
   else
   {
      ObjectMove(0, ln, 0, g_t1, price);
      ObjectMove(0, ln, 1, g_t0, price);
   }
   ObjectSetInteger(0, ln, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, ln, OBJPROP_STYLE, style);
   ObjectSetInteger(0, ln, OBJPROP_WIDTH, width);

   datetime tl = g_t0 + (datetime)(PeriodSeconds() * InpLabelShiftBars);
   if(ObjectFind(0, tx) < 0)
   {
      ObjectCreate(0, tx, OBJ_TEXT, 0, tl, price);
      ObjectSetInteger(0, tx, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, tx, OBJPROP_FONTSIZE, 8);
      ObjectSetString(0, tx, OBJPROP_FONT, "Arial");
      ObjectSetInteger(0, tx, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, tx, OBJPROP_HIDDEN, true);
   }
   else
      ObjectMove(0, tx, 0, tl, price);
   ObjectSetString(0, tx, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, tx, OBJPROP_COLOR, clr);
}

//+------------------------------------------------------------------+
//| Draw round numbers around price                                  |
//+------------------------------------------------------------------+
void DrawRoundNumbers(const double price)
{
   double step  = GetRoundStep(price);
   double below = MathFloor(price / step + 1e-9) * step;
   if(below == g_lastRoundBelow && g_init) return;   // price still in the same band
   g_lastRoundBelow = below;

   ObjectsDeleteAll(0, PFX + "RN_");
   if(!InpDrawLines) return;

   for(int i = -(InpRoundLevels - 1); i <= InpRoundLevels; i++)
   {
      double lvl = below + i * step;
      double q   = lvl / (2.0 * step);
      bool   major = (MathAbs(q - MathRound(q)) < 1e-6);   // multiple of 2 steps = '00'
      string name  = PFX + "RN_" + IntegerToString(i + 100);

      ObjectCreate(0, name, OBJ_HLINE, 0, 0, lvl);
      ObjectSetInteger(0, name, OBJPROP_COLOR, major ? InpClrRoundMajor : InpClrRoundMinor);
      ObjectSetInteger(0, name, OBJPROP_STYLE, major ? STYLE_DASH : STYLE_DOT);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetString(0, name, OBJPROP_TEXT,
                      (major ? "RN 00 " : "RN 50 ") + DoubleToString(lvl, _Digits));
   }
}

//+------------------------------------------------------------------+
//| Panel                                                            |
//+------------------------------------------------------------------+
void Row(const int r, const string text, const color clr)
{
   string name = PFX + "P" + IntegerToString(r);
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, InpPanelX);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, InpPanelY + r * 15);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
}

string DistText(const string label, const double level, const double price, const double atr)
{
   double d = level - price;
   return StringFormat("%-11s %s  %+8.1f pts  %+6.2f ATR",
                       label, DoubleToString(level, _Digits), d / _Point, d / atr);
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
   if(rates_total < 35) return 0;

   if(prev_calculated == 0)
   {
      ArrayInitialize(bPDH, EMPTY_VALUE);     ArrayInitialize(bPDL, EMPTY_VALUE);
      ArrayInitialize(bSessH, EMPTY_VALUE);   ArrayInitialize(bSessL, EMPTY_VALUE);
      ArrayInitialize(bRoundUp, EMPTY_VALUE); ArrayInitialize(bRoundDn, EMPTY_VALUE);
      ArrayInitialize(bGap, EMPTY_VALUE);     ArrayInitialize(bGapFill, EMPTY_VALUE);
   }

   int    L     = rates_total - 1;
   double price = close[L];

   //--- ATR (last closed bar)
   double a[1];
   if(BarsCalculated(hATR) <= 0 || CopyBuffer(hATR, 0, 1, 1, a) <= 0) return prev_calculated;
   double atr = a[0];
   if(atr <= 0.0) atr = _Point;

   g_t0 = time[L];
   g_t1 = time[MathMax(0, L - 30)];

   //--- refresh levels on a new bar
   bool newBar = (time[L] != g_lastBar);
   if(newBar || !g_init)
   {
      g_pdh = iHigh (_Symbol, PERIOD_D1, 1);
      g_pdl = iLow  (_Symbol, PERIOD_D1, 1);
      g_pdc = iClose(_Symbol, PERIOD_D1, 1);
      g_sessOK = GetPrevSession(g_sh, g_sl, g_sessStart, g_sessEnd);
      g_lastBar = time[L];

      if(g_pdh > 0)
      {
         DrawLevel("PDH", g_pdh, InpClrPDH, STYLE_SOLID, 1, "PDH " + DoubleToString(g_pdh, _Digits));
         DrawLevel("PDL", g_pdl, InpClrPDL, STYLE_SOLID, 1, "PDL " + DoubleToString(g_pdl, _Digits));
         DrawLevel("PDC", g_pdc, InpClrPDC, STYLE_DOT,   1, "PDC " + DoubleToString(g_pdc, _Digits));
      }
      if(g_sessOK)
      {
         DrawLevel("SH", g_sh, InpClrSessH, STYLE_DASH, 1, "Sess H " + DoubleToString(g_sh, _Digits));
         DrawLevel("SL", g_sl, InpClrSessL, STYLE_DASH, 1, "Sess L " + DoubleToString(g_sl, _Digits));
      }
   }

   //--- round numbers (redrawn only when price moves to another band)
   DrawRoundNumbers(price);
   g_init = true;

   double step  = GetRoundStep(price);
   double below = MathFloor(price / step + 1e-9) * step;
   double above = below + step;

   //--- daily gap: today's open vs yesterday's close
   double dOpen = iOpen(_Symbol, PERIOD_D1, 0);
   double dHigh = iHigh(_Symbol, PERIOD_D1, 0);
   double dLow  = iLow (_Symbol, PERIOD_D1, 0);
   double gap   = (g_pdc > 0.0) ? dOpen - g_pdc : 0.0;
   bool   gapSig = (MathAbs(gap) >= InpMinGapATR * atr);
   double fillPct = 0.0;
   if(gapSig)
   {
      if(gap > 0.0) fillPct = 100.0 * (dOpen - dLow)  / gap;
      else          fillPct = 100.0 * (dHigh - dOpen) / (-gap);
      fillPct = MathMax(0.0, MathMin(100.0, fillPct));
   }

   //--- fill buffers (last bar)
   bPDH[L]     = (g_pdh > 0.0) ? (g_pdh - price) / atr : EMPTY_VALUE;
   bPDL[L]     = (g_pdl > 0.0) ? (g_pdl - price) / atr : EMPTY_VALUE;
   bSessH[L]   = g_sessOK ? (g_sh - price) / atr : EMPTY_VALUE;
   bSessL[L]   = g_sessOK ? (g_sl - price) / atr : EMPTY_VALUE;
   bRoundUp[L] = (above - price) / atr;
   bRoundDn[L] = (below - price) / atr;
   bGap[L]     = gap / atr;
   bGapFill[L] = fillPct;

   //--- panel
   if(InpShowPanel)
   {
      double nearDist = InpNearATR * atr;
      Row(0, StringFormat("PRICE STRUCTURE | ATR %.1f pts | + = level above price", atr / _Point), clrSilver);

      color c;
      c = (MathAbs(g_pdh - price) <= nearDist) ? InpClrNear : InpClrPDH;
      Row(1, DistText("PDH", g_pdh, price, atr) + ((MathAbs(g_pdh - price) <= nearDist) ? "  <NEAR>" : ""), c);
      c = (MathAbs(g_pdl - price) <= nearDist) ? InpClrNear : InpClrPDL;
      Row(2, DistText("PDL", g_pdl, price, atr) + ((MathAbs(g_pdl - price) <= nearDist) ? "  <NEAR>" : ""), c);

      if(g_sessOK)
      {
         c = (MathAbs(g_sh - price) <= nearDist) ? InpClrNear : InpClrSessH;
         Row(3, DistText("PrevSess H", g_sh, price, atr) + ((MathAbs(g_sh - price) <= nearDist) ? "  <NEAR>" : ""), c);
         c = (MathAbs(g_sl - price) <= nearDist) ? InpClrNear : InpClrSessL;
         Row(4, DistText("PrevSess L", g_sl, price, atr) + ((MathAbs(g_sl - price) <= nearDist) ? "  <NEAR>" : ""), c);
      }
      else
      {
         Row(3, "PrevSess H  session data not available yet", clrGray);
         Row(4, "PrevSess L  session data not available yet", clrGray);
      }

      c = (MathAbs(above - price) <= nearDist) ? InpClrNear : clrSilver;
      Row(5, DistText("Round Up", above, price, atr) + ((MathAbs(above - price) <= nearDist) ? "  <NEAR>" : ""), c);
      c = (MathAbs(below - price) <= nearDist) ? InpClrNear : clrSilver;
      Row(6, DistText("Round Down", below, price, atr) + ((MathAbs(below - price) <= nearDist) ? "  <NEAR>" : ""), c);

      if(gapSig)
      {
         string st = (fillPct >= 100.0) ? "FILLED" : StringFormat("%.0f%% filled", fillPct);
         Row(7, StringFormat("Gap %s %.1f pts (%.2f ATR) | %s",
                             gap > 0 ? "UP" : "DOWN", MathAbs(gap) / _Point, MathAbs(gap) / atr, st),
             (fillPct >= 100.0) ? clrGray : InpClrPDC);
      }
      else
         Row(7, "Gap: no significant gap", clrGray);
   }

   ChartRedraw();
   return rates_total;
}
//+------------------------------------------------------------------+