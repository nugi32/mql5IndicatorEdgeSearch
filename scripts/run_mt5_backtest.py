"""
Re-trade ranked EAs the way the MT5 Strategy Tester ("Open prices only") would,
so the equity curve can be compared with an MT5 report.

Examples:
    # top 5 of a finished run, per-timeframe tester config
    python scripts/run_mt5_backtest.py data/raw_csv/XAUUSD/XAUUSD_M5.csv --symbol XAUUSD --timeframe M5 \
        --run-dir output_walkforward/<run folder> --top-n 5

    # one EA typed by hand, with the broker's real per-bar spread
    python scripts/run_mt5_backtest.py data/raw_csv/XAUUSD/XAUUSD_M5.csv --symbol XAUUSD --timeframe M5 \
        --condition "rsi_14 < 25.0" --direction long --holding-bars 54 --spread-csv XAUUSD_M5_spread.csv
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edge_research.ingestion.economic_calendar import attach_calendar_features  # noqa: E402
from edge_research.ingestion.loader import load_csv_and_validate  # noqa: E402
from edge_research.mt5_backtest.auto import (  # noqa: E402
    backtest_edges_to_folder, find_storage_file, load_columns, needed_columns,
)
from edge_research.mt5_backtest.config import DEFAULT_CONFIG_ROOT, load_mt5_config  # noqa: E402
from edge_research.mt5_backtest.report import load_reference_trades, load_spread_csv  # noqa: E402
from edge_research.utils.run_dir import resolve_output_dir  # noqa: E402

logger = logging.getLogger("mt5_backtest")


def _read_edges(args) -> pd.DataFrame:
    if args.condition:
        if not args.direction or not args.holding_bars:
            raise SystemExit("--condition needs --direction and --holding-bars")
        return pd.DataFrame([{"rank": 1, "condition": args.condition,
                              "direction": args.direction, "holding_bars": args.holding_bars}])
    if not args.run_dir:
        raise SystemExit("give either --run-dir (ranked EAs) or --condition")
    path = Path(args.run_dir) / "ranker_sort_top.csv"
    if not path.is_file():
        raise SystemExit(f"no ranker output in {args.run_dir} (run scripts/run_ranker.py first)")
    logger.info(f"EAs from {path}")
    return pd.read_csv(path).head(args.top_n)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="MT5 Strategy Tester (Open prices only) emulation")
    p.add_argument("csv_path", help="dataExporter.mq5 CSV (OHLC + indicator columns)")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", required=True)
    p.add_argument("--run-dir", help="finished run folder with ranker_sort_top.csv")
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--condition")
    p.add_argument("--direction", choices=["long", "short"])
    p.add_argument("--holding-bars", type=int)
    p.add_argument("--config-root", default=str(DEFAULT_CONFIG_ROOT), help="folder with <SYMBOL>/<TF>.yaml")
    p.add_argument("--config-file", help="use this YAML instead of <config-root>/<SYMBOL>/<TF>.yaml")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="override a setting, e.g. --set spread_points=25 --set lots=0.5")
    p.add_argument("--spread-csv", help="per-bar spread from mql5/spreadExporter.mq5 (overrides fixed spread_points)")
    p.add_argument("--calendar-csv", help="needed only for conditions that use cal_* columns")
    p.add_argument("--start", help="first date of the test, e.g. 2024-01-01")
    p.add_argument("--end", help="last date of the test (inclusive)")
    p.add_argument("--compare-trades", help="trade list exported from MT5 to compare with (single EA only)")
    p.add_argument("--output-dir", help="parent folder for results (default: <run-dir>/mt5_backtest)")
    p.add_argument("--run-name")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    overrides = {}
    for item in args.set:
        key, _, value = item.partition("=")
        overrides[key.strip()] = yaml_value(value)
    cfg = load_mt5_config(args.config_root, args.symbol, args.timeframe, overrides, args.config_file)

    edges = _read_edges(args)
    if args.compare_trades and len(edges) != 1:
        raise SystemExit("--compare-trades works with one EA: use --condition or --top-n 1")

    # Prefer the run's stored table and read only the columns the EAs need (the CSV has
    # ~150 columns; on M1 loading all of it takes several GB).
    storage = find_storage_file(Path(args.run_dir)) if args.run_dir else None
    if storage is not None and not args.calendar_csv:
        df = load_columns(storage, needed_columns(edges))
    else:
        df = load_csv_and_validate(args.csv_path)
        if args.calendar_csv:
            df = attach_calendar_features(df, args.calendar_csv, args.symbol, args.timeframe)
    spread = load_spread_csv(args.spread_csv) if args.spread_csv else None
    spread_source = (f"per-bar from {Path(args.spread_csv).name}" if spread is not None
                     else f"fixed {cfg.spread_points:g} points")
    start = pd.Timestamp(args.start) if args.start else None
    end = pd.Timestamp(args.end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1) if args.end else None

    base = Path(args.output_dir) if args.output_dir else (Path(args.run_dir) / "mt5_backtest" if args.run_dir else Path("mt5_backtest"))
    out_dir = resolve_output_dir(base, args.symbol, args.timeframe, run_name=args.run_name)

    reference = load_reference_trades(args.compare_trades) if args.compare_trades else None
    period = f"{args.start or df.index[0]} to {args.end or df.index[-1]}"
    backtest_edges_to_folder(df, edges, cfg, args.symbol, args.timeframe, out_dir, spread,
                             spread_source, start, end, reference, period)
    print(out_dir / "mt5_backtest_report.md")
    return 0


def yaml_value(text: str):
    import yaml
    return yaml.safe_load(text)


if __name__ == "__main__":
    sys.exit(main())
