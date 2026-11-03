"""
Summarise a per-bar spread file (mql5/spreadExporter.mq5) and suggest the
``spread_points`` value for config/MT5_TESTER/<SYMBOL>/<TF>.yaml.

Usage:
    python scripts/calibrate_mt5_spread.py XAUUSD_M5_spread.csv
    python scripts/calibrate_mt5_spread.py XAUUSD_M5_spread.csv --update-config config/MT5_TESTER/XAUUSD/M5.yaml
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edge_research.mt5_backtest.report import load_spread_csv  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Spread statistics for the MT5 tester config")
    p.add_argument("spread_csv")
    p.add_argument("--update-config", help="write the suggested value into this YAML file")
    args = p.parse_args(argv)

    s = load_spread_csv(args.spread_csv).dropna()
    s = s[s > 0]
    if s.empty:
        print("no positive spread values found")
        return 1
    stats = {"bars": len(s), "mean": s.mean(), "median": s.median(),
             "p90": s.quantile(0.9), "p99": s.quantile(0.99), "max": s.max()}
    for k, v in stats.items():
        print(f"{k:>7}: {v:,.1f}")
    print("\nBy hour of day (mean points):")
    print(s.groupby(s.index.hour).mean().round(1).to_string())
    suggestion = round(float(s.mean()))
    print(f"\nSuggested spread_points (mean, cost-equivalent over many trades): {suggestion}")
    print("Better still: pass --spread-csv to run_mt5_backtest.py to use the real per-bar spread.")

    if args.update_config:
        path = Path(args.update_config)
        text = path.read_text(encoding="utf-8")
        if re.search(r"^spread_points:", text, re.M):
            text = re.sub(r"^spread_points:.*$", f"spread_points: {suggestion}", text, count=1, flags=re.M)
        else:
            text += f"\nspread_points: {suggestion}\n"
        path.write_text(text, encoding="utf-8")
        print(f"updated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
