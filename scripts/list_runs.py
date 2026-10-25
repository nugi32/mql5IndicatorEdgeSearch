"""
List the runs found under an output folder (one row per run sub-folder).

Usage:
    python scripts/list_runs.py output_walkforward
"""

import argparse
import json
import sys
from pathlib import Path

from edge_research.utils.run_dir import RUN_INFO_FILENAME


def collect_runs(base_dir: Path) -> list:
    rows = []
    for child in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        info_path = child / RUN_INFO_FILENAME
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {"status": "unreadable"}
        args = info.get("args", {})
        rows.append({
            "run": child.name,
            "status": info.get("status", "?"),
            "symbol": args.get("symbol", ""),
            "tf": args.get("timeframe", ""),
            "pid": info.get("pid", ""),
            "started": info.get("started_at", ""),
            "finished": info.get("finished_at", ""),
        })
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List pipeline runs under an output folder")
    parser.add_argument("output_dir")
    args = parser.parse_args(argv)
    base = Path(args.output_dir)
    if not base.is_dir():
        print(f"Not a directory: {base}", file=sys.stderr)
        return 1
    rows = collect_runs(base)
    if not rows:
        print("No runs found (no RUN_INFO.json in any sub-folder).")
        return 0
    cols = ["run", "status", "symbol", "tf", "pid", "started", "finished"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
