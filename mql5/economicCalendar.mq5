//+------------------------------------------------------------------+
//|                                             CalendarExporter.mq5 |
//| Exports the MT5 Economic Calendar to a CSV for a Python pipeline.|
//|                                                                  |
//| IMPORTANT: run this as a SCRIPT on a LIVE chart (terminal online)|
//| Calendar functions are NOT available in the Strategy Tester      |
//| (error 4014), so this cannot be built into DataExporter itself.  |
//|                                                                  |
//| All times are broker SERVER time (same clock as the tester and   |
//| DataExporter.csv), so the two files can be joined directly.      |
//+------------------------------------------------------------------+
#property copyright "CalendarExporter"
#property version   "1.00"
#property script_show_inputs
#property description "Exports economic calendar events/values to CSV (server time)"

input datetime InpFrom              = D'2020.01.01 00:00'; // Start date
input datetime InpTo                = 0;                   // End date (0 = now)
input ENUM_CALENDAR_EVENT_IMPORTANCE InpMinImportance = CALENDAR_IMPORTANCE_LOW; // Minimum importance
input string   InpCurrencies        = "";                  // Currencies, comma-separated (empty = all), e.g. USD,EUR
input string   InpFileName          = "economic_calendar.csv"; // Output file name
input bool     InpUseCommonFolder   = true;                // Save in Common\Files (easier to reach from Python)
input int      InpChunkDays         = 60;                  // Days per calendar request

//--- country cache
long   g_cid[];
string g_ccode[];
string g_ccur[];

//+------------------------------------------------------------------+
string Iso(const datetime t)
{
   MqlDateTime d;
   TimeToStruct(t, d);
   return StringFormat("%04d-%02d-%02d %02d:%02d:%02d", d.year, d.mon, d.day, d.hour, d.min, d.sec);
}

//+------------------------------------------------------------------+
string Clean(string s)
{
   StringReplace(s, ",", " ");
   StringReplace(s, "\"", "");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
}

//+------------------------------------------------------------------+
bool GetCountry(const long id, string &code, string &cur)
{
   int n = ArraySize(g_cid);
   for(int i = 0; i < n; i++)
      if(g_cid[i] == id)
      {
         code = g_ccode[i];
         cur  = g_ccur[i];
         return true;
      }

   MqlCalendarCountry c;
   if(!CalendarCountryById(id, c)) return false;

   ArrayResize(g_cid, n + 1);
   ArrayResize(g_ccode, n + 1);
   ArrayResize(g_ccur, n + 1);
   g_cid[n]   = id;
   g_ccode[n] = c.code;
   g_ccur[n]  = c.currency;
   code = c.code;
   cur  = c.currency;
   return true;
}

//+------------------------------------------------------------------+
bool CurrencyAllowed(const string cur, const string &list[], const int n)
{
   if(n == 0) return true;
   for(int i = 0; i < n; i++)
      if(list[i] == cur) return true;
   return false;
}

//+------------------------------------------------------------------+
string Num(const bool has, const double v, const int digits)
{
   if(!has || !MathIsValidNumber(v)) return "";
   return DoubleToString(v, digits);
}

//+------------------------------------------------------------------+
void OnStart()
{
   if(MQLInfoInteger(MQL_TESTER))
   {
      Print("Calendar functions do not work in the Strategy Tester. Run this script on a live chart.");
      return;
   }

   datetime to = (InpTo == 0) ? TimeTradeServer() : InpTo;
   if(InpFrom >= to)
   {
      Print("Invalid date range.");
      return;
   }

   // parse currency filter
   string curs[];
   int nc = 0;
   if(StringLen(InpCurrencies) > 0)
   {
      string parts[];
      int np = StringSplit(InpCurrencies, ',', parts);
      for(int i = 0; i < np; i++)
      {
         StringTrimLeft(parts[i]);
         StringTrimRight(parts[i]);
         StringToUpper(parts[i]);
         if(parts[i] == "") continue;
         ArrayResize(curs, nc + 1);
         curs[nc++] = parts[i];
      }
   }

   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFolder) flags |= FILE_COMMON;
   int h = FileOpen(InpFileName, flags, ',', CP_UTF8);
   if(h == INVALID_HANDLE)
   {
      Print("Cannot open file ", InpFileName, " error ", GetLastError());
      return;
   }

   FileWrite(h, "time_server", "event_id", "country", "currency", "event_name",
                "importance", "sector", "event_type", "unit", "multiplier",
                "actual", "forecast", "previous", "revised_previous",
                "impact_type", "revision");

   long total = 0;
   datetime from = InpFrom;
   long step = (long)MathMax(1, InpChunkDays) * 86400;

   while(from < to && !IsStopped())
   {
      datetime chunkTo = (datetime)MathMin((double)((long)from + step), (double)to);

      MqlCalendarValue vals[];
      ResetLastError();
      int n = CalendarValueHistory(vals, from, chunkTo);
      if(n < 0)
      {
         int err = GetLastError();
         Print("CalendarValueHistory failed, error ", err, " (", Iso(from), " -> ", Iso(chunkTo), ")");
         if(err == 4014) { Print("Not allowed in tester."); break; }
      }
      else
      {
         for(int i = 0; i < n; i++)
         {
            MqlCalendarEvent ev;
            if(!CalendarEventById(vals[i].event_id, ev)) continue;
            if(ev.importance < InpMinImportance) continue;

            string code, cur;
            if(!GetCountry(ev.country_id, code, cur)) { code = ""; cur = ""; }
            if(!CurrencyAllowed(cur, curs, nc)) continue;

            int dg = (int)ev.digits;

            FileWrite(h,
               Iso(vals[i].time),
               (string)vals[i].event_id,
               code,
               cur,
               Clean(ev.name),
               (string)(int)ev.importance,
               (string)(int)ev.sector,
               (string)(int)ev.type,
               (string)(int)ev.unit,
               (string)(int)ev.multiplier,
               Num(vals[i].HasActualValue(),   vals[i].GetActualValue(),   dg),
               Num(vals[i].HasForecastValue(), vals[i].GetForecastValue(), dg),
               Num(vals[i].HasPreviousValue(), vals[i].GetPreviousValue(), dg),
               Num(vals[i].HasRevisedValue(),  vals[i].GetRevisedValue(),  dg),
               (string)(int)vals[i].impact_type,
               (string)vals[i].revision);
            total++;
         }
      }

      Comment("CalendarExporter: ", Iso(chunkTo), "  rows=", total);
      from = (datetime)((long)chunkTo + 1);
   }

   FileClose(h);
   Comment("");
   Print("CalendarExporter done. Rows written: ", total, " -> ",
         InpUseCommonFolder ? "Common\\Files\\" : "MQL5\\Files\\", InpFileName);
}
//+------------------------------------------------------------------+