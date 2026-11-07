"""
Run the sort ranker on an existing run folder (both pipeline scripts already do
this automatically at the end of a run; use this to re-rank old runs or with
different thresholds). Works on a walk-forward run folder (TEST_PERIOD_RESULTS.csv
files) and on a normal run folder (STRATEGY_GATE_RESULTS.csv).

Usage:
    python scripts/run_ranker.py output_walkforward/<run folder> --symbol XAUUSD --timeframe H1 --min-pf 1.5
    python scripts/run_ranker.py <run folder> --sort-top-n 5
"""

import argparse
import logging
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edge_research.ranking.ranker import RankerConfig, run_ranker  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sort-rank the results of one run folder")
    parser.add_argument("run_dir")
    parser.add_argument("--symbol", default="?")
    parser.add_argument("--timeframe", default="?")
    parser.add_argument("--no-dedupe", action="store_true",
                        help="Keep near-duplicate EAs in the list")
    defaults = RankerConfig()
    for f in fields(RankerConfig):
        flag = "--" + f.name.replace("_", "-")
        default = getattr(defaults, f.name)
        if isinstance(default, bool):
            continue
        parser.add_argument(flag, type=type(default), default=default)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = RankerConfig(**{f.name: getattr(args, f.name) for f in fields(RankerConfig)
                          if not isinstance(getattr(defaults, f.name), bool)})
    if args.no_dedupe:
        cfg.sort_dedupe = False
    path = run_ranker(args.run_dir, args.symbol, args.timeframe, cfg)
    if path is None:
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
