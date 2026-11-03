"""
Run the MT5-style backtest as an automatic last step of a pipeline run, and
the shared "backtest these EAs and write the report folder" routine used by
scripts/run_mt5_backtest.py.

Nothing here changes how a run is started: the same commands as before now
also leave a ``mt5_backtest/`` folder inside the run folder. A problem in this
step is logged and never fails the run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from edge_research.ranking.ranker import SORT_OUTPUT_CSV as RANKER_SORT_CSV, parse_condition
from edge_research.utils.memory import release_memory
from edge_research.mt5_backtest.config import DEFAULT_CONFIG_ROOT, MT5TesterConfig, load_mt5_config
from edge_research.mt5_backtest.engine import run_mt5_backtest
from edge_research.mt5_backtest.report import (
    build_markdown, compare_trades, decimate, load_spread_csv, save_chart, save_overview_chart,
)
from edge_research.mt5_backtest.signals import build_mask

logger = logging.getLogger(__name__)

OUTPUT_FOLDER = "mt5_backtest"
EDGE_COLUMNS = ["rank", "condition", "direction", "holding_bars"]


def find_storage_file(run_dir: Path) -> Optional[Path]:
    """The Parquet (or Feather) table the run wrote in <run>/storage (includes cal_* columns)."""
    for pattern in ("*.parquet", "*.feather"):
        found = sorted((Path(run_dir) / "storage").glob(pattern))
        if found:
            return found[0]
    return None


def needed_columns(edges: pd.DataFrame) -> List[str]:
    """``open`` plus every column the EAs' conditions read (a threshold can itself be a column name)."""
    cols = {"open"}
    for cond in edges["condition"]:
        for column, _, threshold in parse_condition(str(cond)):
            cols.add(column)
            if isinstance(threshold, str):
                cols.add(threshold)
    return sorted(cols)


def load_columns(storage: Path, columns: List[str]) -> pd.DataFrame:
    """
    Read only ``columns`` from the stored table. The full table has ~150
    float32 columns (several GB on M1); the backtest needs a handful.
    Columns missing from the file are skipped, so the affected EAs are
    reported as skipped instead of the whole step failing.
    """
    if storage.suffix.lower() == ".feather":
        df = pd.read_feather(storage)
        return df[[c for c in columns if c in df.columns]]
    import pyarrow.parquet as pq
    present = set(pq.ParquetFile(storage).schema_arrow.names)
    return pd.read_parquet(storage, columns=[c for c in columns if c in present])


def edges_from_gate_results(run_dir: Path, top_n: int) -> pd.DataFrame:
    """Top EAs of a single run: STRATEGY_GATE_RESULTS.csv is sorted gate-passed first, then by expectancy."""
    path = Path(run_dir) / "STRATEGY_GATE_RESULTS.csv"
    if not path.is_file():
        return pd.DataFrame(columns=EDGE_COLUMNS)
    gate = pd.read_csv(path)
    if len(gate) == 0:
        return pd.DataFrame(columns=EDGE_COLUMNS)
    top = gate.dropna(subset=["condition", "direction", "optimal_holding_bars"]).head(top_n)
    return pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "condition": top["condition"].astype(str).to_list(),
        "direction": top["direction"].astype(str).to_list(),
        "holding_bars": top["optimal_holding_bars"].astype(int).to_list(),
    })


def edges_from_ranker(run_dir: Path, top_n: int) -> pd.DataFrame:
    """Top EAs of a run from ranker_sort_top.csv (written by the sort ranker after every run)."""
    path = Path(run_dir) / RANKER_SORT_CSV
    if not path.is_file():
        return pd.DataFrame(columns=EDGE_COLUMNS)
    frame = pd.read_csv(path)
    logger.info(f"MT5 backtest: EAs from {path.name}")
    return frame[EDGE_COLUMNS].head(top_n) if len(frame) else pd.DataFrame(columns=EDGE_COLUMNS)


def backtest_edges_to_folder(
    df: pd.DataFrame,
    edges: pd.DataFrame,
    cfg: MT5TesterConfig,
    symbol: str,
    timeframe: str,
    out_dir: Path,
    spread: Optional[pd.Series] = None,
    spread_source: Optional[str] = None,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
    reference: Optional[pd.DataFrame] = None,
    period_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Backtest every EA in ``edges`` and write trades, curves, charts, summary and the markdown report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    overview: List[Dict[str, Any]] = []
    for edge in edges.itertuples(index=False):
        rank, cond, direction, hold = int(edge.rank), str(edge.condition), str(edge.direction), int(edge.holding_bars)
        file_id = f"{rank:02d}_{direction}_{hold}b"
        row: Dict[str, Any] = {"rank": rank, "condition": cond, "direction": direction,
                               "holding_bars": hold, "file_id": file_id}
        try:
            mask = build_mask(df, cond)
        except KeyError as exc:
            logger.warning(f"MT5 backtest: #{rank} skipped, {exc}")
            continue
        result = run_mt5_backtest(df, mask, direction, hold, cfg, spread, start, end)
        del mask
        result.trades.to_csv(out_dir / f"trades_{file_id}.csv", index=False)
        bal, eq = decimate(result.balance), decimate(result.equity)
        pd.DataFrame({"time": bal["x"], "balance": bal["last"],
                      "equity_low": eq["lo"], "equity_high": eq["hi"]}
                     ).to_csv(out_dir / f"curve_{file_id}.csv", index=False)
        chart = save_chart(result, f"#{rank} {cond} ({direction}, hold {hold})", out_dir / f"curve_{file_id}.png")
        if chart is not None:
            row["chart"] = chart.name
        if reference is not None:
            row["comparison"] = compare_trades(result.trades, reference)
        overview.append({"label": f"#{rank} {direction} {hold}b", "x": bal["x"], "y": bal["last"]})
        # Keep only what the report needs. The per-bar curves and the trade list
        # (millions of values on M1) are released before the next EA is processed.
        result.balance = result.balance.iloc[:0]
        result.equity = result.equity.iloc[:0]
        result.trades = result.trades.iloc[:0]
        row["result"] = result
        rows.append(row)
        logger.info(f"MT5 backtest #{rank}: {result.summary['total_trades']} trades, "
                    f"net {result.summary['total_net_profit']:.2f}, "
                    f"{result.n_skipped_busy} signals skipped while a position was open")
        del bal, eq
        release_memory()

    overview_path = save_overview_chart(
        overview, f"{symbol} {timeframe}: balance of the backtested EAs", out_dir / "overview.png")
    period = period_text or f"{df.index[0]} to {df.index[-1]}"
    source = spread_source or f"fixed {cfg.spread_points:g} points"
    (out_dir / "mt5_backtest_report.md").write_text(
        build_markdown(symbol, timeframe, cfg, rows, period, source,
                       overview_path.name if overview_path else None), encoding="utf-8")
    pd.DataFrame([{"rank": r["rank"], "condition": r["condition"], "direction": r["direction"],
                   "holding_bars": r["holding_bars"], **r["result"].summary} for r in rows]
                 ).to_csv(out_dir / "mt5_backtest_summary.csv", index=False)
    return rows


def run_auto_backtest(
    run_dir: str | Path,
    symbol: str,
    timeframe: str,
    source: str,
    top_n: int = 20,
    config_root: Optional[str | Path] = None,
    spread_csv: Optional[str | Path] = None,
) -> Optional[Path]:
    """
    Backtest the top EAs of a finished run into ``<run_dir>/mt5_backtest/``.

    source: "ranker-sort" (top of ranker_sort_top.csv, used after every run) or
    "gate" (top of STRATEGY_GATE_RESULTS.csv). Returns the report path, or None
    when there was nothing to do.
    """
    run_dir = Path(run_dir)
    if source == "ranker-sort":
        edges = edges_from_ranker(run_dir, top_n)
    elif source == "gate":
        edges = edges_from_gate_results(run_dir, top_n)
    else:
        raise ValueError(f"unknown MT5 backtest source {source!r}; use 'ranker-sort' or 'gate'")
    if len(edges) == 0:
        logger.warning("MT5 backtest: no EAs to backtest in this run")
        return None
    storage = find_storage_file(run_dir)
    if storage is None:
        logger.warning(f"MT5 backtest: no stored data in {run_dir / 'storage'}")
        return None
    cfg = load_mt5_config(config_root or DEFAULT_CONFIG_ROOT, symbol, timeframe)
    df = load_columns(storage, needed_columns(edges))
    logger.info(f"MT5 backtest: loaded {len(df.columns)} columns, {len(df):,} bars")
    spread = load_spread_csv(spread_csv) if spread_csv else None
    source_text = f"per-bar from {Path(spread_csv).name}" if spread is not None else None
    out_dir = run_dir / OUTPUT_FOLDER
    backtest_edges_to_folder(df, edges, cfg, symbol, timeframe, out_dir, spread, source_text)
    logger.info(f"MT5 backtest written to {out_dir}")
    return out_dir / "mt5_backtest_report.md"


def try_auto_backtest(*args, **kwargs) -> Optional[Path]:
    """run_auto_backtest that never raises: a failure here must not fail the finished run."""
    try:
        return run_auto_backtest(*args, **kwargs)
    except Exception:
        logger.exception("MT5 backtest step failed (run results are unaffected); "
                         "re-run it with scripts/run_mt5_backtest.py")
        return None
