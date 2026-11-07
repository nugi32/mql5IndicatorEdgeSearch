"""Spread-file loading, trade comparison with an MT5 reference, charts and markdown."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from edge_research.mt5_backtest.config import MT5TesterConfig
from edge_research.mt5_backtest.engine import BacktestResult

logger = logging.getLogger(__name__)

TIME_FORMATS = ("%Y%m%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def parse_times(raw: pd.Series) -> pd.Series:
    """Parse a time column written by the MQL5 tools or by an MT5 export."""
    for fmt in TIME_FORMATS:
        parsed = pd.to_datetime(raw, format=fmt, errors="coerce")
        if parsed.notna().mean() > 0.99:
            return parsed
    return pd.to_datetime(raw, errors="coerce")


def load_spread_csv(path: str | Path) -> pd.Series:
    """Read ``time,spread`` (points) written by mql5/spreadExporter.mq5."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if "time" not in df.columns or "spread" not in df.columns:
        raise ValueError(f"{path}: expected columns 'time' and 'spread', found {list(df.columns)}")
    df["time"] = parse_times(df["time"].astype(str))
    df = df.dropna(subset=["time"]).drop_duplicates("time").set_index("time").sort_index()
    return pd.to_numeric(df["spread"], errors="coerce")


# --------------------------------------------------------------------------
# Comparison with a trade list from MT5
# --------------------------------------------------------------------------

_ALIASES = {
    "entry_time": ("entry_time", "open_time", "time_open", "opentime"),
    "exit_time": ("exit_time", "close_time", "time_close", "closetime"),
    "entry_price": ("entry_price", "open_price", "price_open", "openprice"),
    "exit_price": ("exit_price", "close_price", "price_close", "closeprice"),
}


def load_reference_trades(path: str | Path) -> pd.DataFrame:
    """Trade list from MT5 (CSV with entry/exit time and price; common header names are accepted)."""
    ref = pd.read_csv(path)
    ref.columns = [c.strip().lower().replace(" ", "_") for c in ref.columns]
    out = pd.DataFrame()
    for canonical, names in _ALIASES.items():
        found = next((n for n in names if n in ref.columns), None)
        if found is None:
            raise ValueError(f"{path}: no column for {canonical} (accepted: {names}); found {list(ref.columns)}")
        out[canonical] = ref[found]
    out["entry_time"] = parse_times(out["entry_time"].astype(str))
    out["exit_time"] = parse_times(out["exit_time"].astype(str))
    for c in ("entry_price", "exit_price"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["entry_time"])


def compare_trades(emulated: pd.DataFrame, reference: pd.DataFrame, tol: float = 1e-6) -> Dict[str, Any]:
    """
    Match trades on entry time and report where the emulator and MT5 differ.
    Use the first differences to find which setting (spread, exit bar, one
    position at a time, ...) explains them.
    """
    merged = emulated.merge(reference, on="entry_time", how="outer", suffixes=("", "_mt5"), indicator=True)
    both = merged[merged["_merge"] == "both"].copy()
    both["entry_price_diff"] = both["entry_price"] - both["entry_price_mt5"]
    both["exit_price_diff"] = both["exit_price"] - both["exit_price_mt5"]
    both["exit_time_match"] = both["exit_time"] == both["exit_time_mt5"]
    return {
        "n_emulated": int(len(emulated)),
        "n_mt5": int(len(reference)),
        "n_matched": int(len(both)),
        "only_emulated": merged[merged["_merge"] == "left_only"]["entry_time"].tolist(),
        "only_mt5": merged[merged["_merge"] == "right_only"]["entry_time"].tolist(),
        "exit_time_mismatches": int((~both["exit_time_match"]).sum()),
        "entry_price_mean_abs_diff": float(both["entry_price_diff"].abs().mean()) if len(both) else float("nan"),
        "exit_price_mean_abs_diff": float(both["exit_price_diff"].abs().mean()) if len(both) else float("nan"),
        "entry_price_exact": int((both["entry_price_diff"].abs() <= tol).sum()),
        "exit_price_exact": int((both["exit_price_diff"].abs() <= tol).sum()),
        "detail": both[["entry_time", "entry_price", "entry_price_mt5", "entry_price_diff",
                        "exit_time", "exit_time_mt5", "exit_price", "exit_price_mt5", "exit_price_diff"]],
    }


def comparison_markdown(name: str, cmp: Dict[str, Any]) -> List[str]:
    lines = [f"### Comparison with MT5 — {name}", "",
             f"- trades: emulator {cmp['n_emulated']}, MT5 {cmp['n_mt5']}, matched on entry time {cmp['n_matched']}",
             f"- only in emulator: {len(cmp['only_emulated'])}, only in MT5: {len(cmp['only_mt5'])}",
             f"- exit time differs on {cmp['exit_time_mismatches']} matched trades",
             f"- entry price exact on {cmp['entry_price_exact']}, mean abs diff {cmp['entry_price_mean_abs_diff']:.4f}",
             f"- exit price exact on {cmp['exit_price_exact']}, mean abs diff {cmp['exit_price_mean_abs_diff']:.4f}"]
    for label, key in (("only in emulator", "only_emulated"), ("only in MT5", "only_mt5")):
        if cmp[key]:
            shown = ", ".join(str(t) for t in cmp[key][:5])
            lines.append(f"- first {label}: {shown}")
    return lines + [""]


# --------------------------------------------------------------------------
# Chart and markdown
# --------------------------------------------------------------------------

MAX_CHART_POINTS = 2500


def decimate(series: pd.Series, max_points: int = MAX_CHART_POINTS) -> Dict[str, np.ndarray]:
    """
    Shrink a long curve (millions of M1 bars) to at most ``max_points`` buckets
    that still show every peak and trough: per bucket the first timestamp, the
    min, the max and the last value.
    """
    v = series.to_numpy(dtype=np.float64)
    idx = series.index
    n = len(v)
    if n == 0:
        empty = np.array([])
        return {"x": idx[:0], "lo": empty, "hi": empty, "last": empty}
    size = int(np.ceil(n / max_points))
    if size <= 1:
        return {"x": idx, "lo": v, "hi": v, "last": v}
    nb = int(np.ceil(n / size))
    padded = np.pad(v, (0, nb * size - n), mode="edge").reshape(nb, size)
    return {"x": idx[::size][:nb], "lo": padded.min(axis=1), "hi": padded.max(axis=1), "last": padded[:, -1]}


def _chart_title(result: BacktestResult, title: str) -> str:
    s = result.summary
    pf = s["profit_factor"]
    return (f"{title}\nnet {s['total_net_profit']:,.0f}  |  trades {s['total_trades']}  |  "
            f"PF {'inf' if np.isinf(pf) else f'{pf:.2f}'}  |  max equity DD {s['equity_drawdown_max_pct']:.1f}%")


def save_chart(result: BacktestResult, title: str, path: Path) -> Optional[Path]:
    """
    Balance / equity curve with a drawdown panel, like the MT5 tester graph.
    Writes ``path`` (PNG) and returns it; if matplotlib is missing, writes an
    SVG next to it instead and returns that. Long curves are decimated, so
    M1 data does not mean millions of plotted points.
    """
    if len(result.balance) == 0:
        return None
    bal, eq = decimate(result.balance), decimate(result.equity)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib is not installed: writing an SVG chart instead (pip install matplotlib for PNG)")
        svg = path.with_suffix(".svg")
        svg.write_text(_svg_chart(bal, eq, _chart_title(result, title)), encoding="utf-8")
        return svg
    peak = np.maximum.accumulate(eq["hi"])
    dd_pct = np.where(peak > 0, (peak - eq["lo"]) / peak * 100.0, 0.0)
    fig, (ax, ax_dd) = plt.subplots(2, 1, figsize=(11, 6), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    ax.fill_between(eq["x"], eq["lo"], eq["hi"], color="#c9d1d9", linewidth=0, label="Equity")
    ax.plot(bal["x"], bal["last"], color="#1f77b4", linewidth=1.4, label="Balance")
    ax.set_title(_chart_title(result, title), fontsize=9)
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax_dd.fill_between(eq["x"], -dd_pct, 0, color="#d62728", alpha=0.45, linewidth=0)
    ax_dd.set_ylabel("Drawdown %", fontsize=8)
    ax_dd.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _svg_chart(bal: Dict[str, np.ndarray], eq: Dict[str, np.ndarray], title: str) -> str:
    """Dependency-free line chart (balance + equity low) used when matplotlib is not installed."""
    w, h, pad = 900, 340, 48
    ys = np.concatenate([bal["last"], eq["lo"], eq["hi"]])
    y0, y1 = float(ys.min()), float(ys.max())
    if y1 == y0:
        y1 = y0 + 1.0

    def poly(y: np.ndarray, color: str, width: float) -> str:
        n = len(y)
        xs = np.linspace(pad, w - pad, n) if n > 1 else np.array([pad])
        py = h - pad - (y - y0) / (y1 - y0) * (h - 2 * pad)
        pts = " ".join(f"{x:.1f},{v:.1f}" for x, v in zip(xs, py))
        return f'<polyline fill="none" stroke="{color}" stroke-width="{width}" points="{pts}"/>'

    first, last = str(bal["x"][0])[:10], str(bal["x"][-1])[:10]
    lines = title.split("\n")
    texts = "".join(f'<text x="{pad}" y="{16 + 14 * i}" font-size="12" font-family="sans-serif">{t}</text>'
                    for i, t in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="white"/>{texts}'
            f'{poly(eq["lo"], "#9aa5b1", 1)}{poly(bal["last"], "#1f77b4", 1.6)}'
            f'<text x="4" y="{pad}" font-size="10">{y1:,.0f}</text><text x="4" y="{h - pad}" font-size="10">{y0:,.0f}</text>'
            f'<text x="{pad}" y="{h - 12}" font-size="10">{first}</text>'
            f'<text x="{w - pad - 60}" y="{h - 12}" font-size="10">{last}</text></svg>')


def save_overview_chart(curves: List[Dict[str, Any]], title: str, path: Path) -> Optional[Path]:
    """All EAs' balance curves on one chart. ``curves``: dicts with label, x, y (already decimated)."""
    curves = [c for c in curves if len(c["y"]) > 0]
    if not curves:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for c in curves:
        ax.plot(c["x"], c["y"], linewidth=1.2, label=c["label"])
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _fmt(v: Any) -> str:
    if isinstance(v, (int, np.integer)):
        return str(v)
    if isinstance(v, float):
        return "inf" if np.isinf(v) else f"{v:,.2f}"
    return str(v)


def build_markdown(symbol: str, timeframe: str, cfg: MT5TesterConfig, rows: List[Dict[str, Any]],
                   period: str, spread_source: str, overview: Optional[str] = None) -> str:
    L = [f"# MT5 tester emulation — {symbol} {timeframe}", "",
         f"Mode: **Open prices only**, delay: none (random delay is not allowed in this mode), forward: no. Period: {period}.",
         f"Spread: {spread_source}. Lots {cfg.lots}, contract size {cfg.contract_size:g}, deposit {cfg.initial_deposit:,.0f}, "
         f"max open positions {cfg.max_open_positions}, exit bar offset {cfg.exit_bar_offset}.", "",
         "| # | Condition | Dir | Hold | Trades | Net profit | PF | Win % | Max equity DD | Skipped (busy) | Open at end |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        s = r["result"].summary
        L.append(f"| {r['rank']} | `{r['condition']}` | {r['direction']} | {r['holding_bars']} | {s['total_trades']} | "
                 f"{_fmt(s['total_net_profit'])} | {_fmt(float(s['profit_factor']))} | {s['profit_trades_pct']:.1f} | "
                 f"{_fmt(s['equity_drawdown_max'])} ({s['equity_drawdown_max_pct']:.1f}%) | "
                 f"{r['result'].n_skipped_busy} | {r['result'].n_open_at_end} |")
    L.append("")
    if overview:
        L += [f"![all EAs]({overview})", ""]
    for r in rows:
        s = r["result"].summary
        L += [f"## #{r['rank']} `{r['condition']}` ({r['direction']}, hold {r['holding_bars']})", ""]
        if r.get("error"):
            L += [f"_Skipped: {r['error']}_", ""]
            continue
        if r.get("chart"):
            L += [f"![curve]({r['chart']})", ""]
        L += ["| Metric | Value |", "|---|---|"]
        for k, v in s.items():
            L.append(f"| {k.replace('_', ' ')} | {_fmt(float(v) if isinstance(v, (float, np.floating)) else v)} |")
        L.append("")
        if r.get("comparison"):
            L += comparison_markdown(r["file_id"], r["comparison"])
    return "\n".join(L)
