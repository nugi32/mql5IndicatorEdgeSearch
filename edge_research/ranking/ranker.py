"""
Post-run ranker for walk-forward output.

Reads every ``TEST_PERIOD_RESULTS.csv`` under one run folder (one symbol +
timeframe) and writes ``ranker_result.md`` (+ ``ranker_top.csv``) with

  1. the top combinations for the whole timeframe, and
  2. the top combinations of every individual window.

Nothing is re-simulated; the ranker only scores what the pipeline already
wrote. Ranking rules:

  * Frequency must be trustworthy: minimum trades per window, and minimum
    total trades / number of windows for the timeframe-level list.
  * Profit factor above a minimum.
  * EA-level plateau: a combination only counts as a plateau when *similar*
    combinations (same direction, same indicator/operator set, nearby
    thresholds and holding bars) also produce good results. An isolated
    combination with no good neighbours is a spike and is rejected.
  * Near-duplicate EAs are removed: only the best-scoring EA of a group of
    similar EAs is listed, the rest are shown as "similar to".
  * Out-of-sample stability: a test result close to the train result
    scores extra.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RESULT_FILENAME = "TEST_PERIOD_RESULTS.csv"
OUTPUT_MD = "ranker_result.md"
OUTPUT_CSV = "ranker_top.csv"
SORT_OUTPUT_MD = "ranker_sort_result.md"
SORT_OUTPUT_CSV = "ranker_sort_top.csv"

PF_CAP = 10.0  # profit factors above this (or inf) are clipped before scoring

# Score weights. The timeframe-level score adds window consistency.
WEIGHTS_WINDOW = {"pf": 0.25, "exp": 0.15, "freq": 0.15, "plateau": 0.25, "stab": 0.20}
WEIGHTS_TIMEFRAME = {"pf": 0.20, "exp": 0.10, "freq": 0.10, "plateau": 0.20,
                     "stab": 0.15, "consistency": 0.25}


@dataclass
class RankerConfig:
    """All thresholds. Override via pipeline_config.yaml keys ``ranker_<name>``."""
    min_window_trades: int = 20        # trades in one window's test period
    min_total_trades: int = 100        # trades summed over all windows (timeframe list)
    min_windows: int = 3               # windows a combination must appear in (capped by run size)
    min_pf: float = 1.3
    min_sensitivity: float = 0.7       # pipeline's own parameter-sensitivity score
    min_plateau_score: float = 0.5     # EA-neighbourhood plateau score
    min_neighbors: int = 1             # fewer similar EAs than this => isolated spike
    threshold_rel_tol: float = 0.30    # thresholds this close (relative) count as similar
    holding_abs_tol: int = 2           # holding bars this close count as similar
    holding_rel_tol: float = 0.25
    top_n_timeframe: int = 20
    top_n_window: int = 10
    require_test_passed: bool = True   # window-level: only rows that passed the pipeline's test gate
    sort_top_n: int = 10               # sort mode: list length per timeframe and per window
    sort_dedupe: bool = True           # sort mode: collapse near-duplicate EAs


def ranker_config_from_dict(pipeline_config: Optional[Dict[str, Any]]) -> RankerConfig:
    """Build a RankerConfig from optional ``ranker_*`` keys of a config dict."""
    cfg = RankerConfig()
    for f in fields(RankerConfig):
        key = f"ranker_{f.name}"
        if pipeline_config and key in pipeline_config and pipeline_config[key] is not None:
            setattr(cfg, f.name, type(getattr(cfg, f.name))(pipeline_config[key]))
    return cfg


# --------------------------------------------------------------------------
# Condition parsing and similarity
# --------------------------------------------------------------------------

_ATOM_RE = re.compile(r"^\s*(\S+)\s+(\S+)\s+(.+?)\s*$")


def parse_condition(text: str) -> List[Tuple[str, str, Any]]:
    """
    Parse ``"rsi_14 < 30.0 AND atr_14 > 1.5"`` into
    ``[("rsi_14", "<", 30.0), ("atr_14", ">", 1.5)]``.
    A threshold that is not numeric (another column name) stays a string.
    """
    atoms = []
    for part in str(text).split(" AND "):
        m = _ATOM_RE.match(part)
        if not m:
            atoms.append((part.strip(), "", ""))
            continue
        col, op, thr = m.groups()
        try:
            thr_val: Any = float(thr)
        except ValueError:
            thr_val = thr
        atoms.append((col, op, thr_val))
    return atoms


def _thresholds_close(a: Any, b: Any, rel_tol: float) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if a == b:
        return True
    return abs(a - b) <= rel_tol * max(abs(a), abs(b))


def are_similar(row_a: Dict[str, Any], row_b: Dict[str, Any], cfg: RankerConfig) -> bool:
    """
    Two EAs are similar when direction and the (column, operator) set match,
    every threshold is within ``threshold_rel_tol`` and holding bars are close.
    Identical rows are not compared to themselves by the callers.
    """
    if row_a["direction"] != row_b["direction"]:
        return False
    atoms_a = row_a["_atoms"]
    atoms_b = row_b["_atoms"]
    if len(atoms_a) != len(atoms_b):
        return False
    map_a = {(c, o): t for c, o, t in atoms_a}
    map_b = {(c, o): t for c, o, t in atoms_b}
    if map_a.keys() != map_b.keys():
        return False
    if not all(_thresholds_close(map_a[k], map_b[k], cfg.threshold_rel_tol) for k in map_a):
        return False
    ha, hb = row_a["holding_bars"], row_b["holding_bars"]
    tol = max(cfg.holding_abs_tol, cfg.holding_rel_tol * max(ha, hb))
    return abs(ha - hb) <= tol


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _natural_key(text: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def load_window_results(run_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    Return ``{window_label: DataFrame}`` for every TEST_PERIOD_RESULTS.csv under
    ``run_dir``. Label is the path relative to the run folder, e.g.
    ``run_2015/window_0001``. Empty CSVs are skipped.
    """
    run_dir = Path(run_dir)
    out: Dict[str, pd.DataFrame] = {}
    for path in run_dir.rglob(RESULT_FILENAME):
        label = path.parent.relative_to(run_dir).as_posix()
        try:
            df = pd.read_csv(path)
        except (OSError, pd.errors.EmptyDataError):
            continue
        if len(df) == 0:
            continue
        out[label] = df
    return dict(sorted(out.items(), key=lambda kv: _natural_key(kv[0])))


def _normalise(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Turn a results DataFrame into clean row dicts with parsed atoms."""
    rows = []
    for rec in df.to_dict("records"):
        pf = pd.to_numeric(rec.get("test_profit_factor"), errors="coerce")
        pf = PF_CAP if (pf is not None and np.isposinf(pf)) else pf
        pf = 0.0 if pd.isna(pf) else float(min(max(pf, 0.0), PF_CAP))
        def num(key, default=0.0):
            v = pd.to_numeric(rec.get(key), errors="coerce")
            return default if pd.isna(v) else float(v)
        rows.append({
            "condition": str(rec["condition"]),
            "direction": str(rec.get("direction", "")),
            "holding_bars": int(num("optimal_holding_bars")),
            "n_trades": int(num("test_n_trades")),
            "pf": pf,
            "test_exp": num("test_expectancy_r"),
            "train_exp": num("train_expectancy_r"),
            "sensitivity": num("train_sensitivity_score", float("nan")),
            "test_passed": bool(rec.get("test_passed", False)),
            "uses_calendar": bool(rec.get("uses_calendar", False)),
            "uses_custom": bool(rec.get("uses_custom_indicators", False)),
            "_atoms": parse_condition(rec["condition"]),
        })
    return rows


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def _stability(test_exp: float, train_exp: float) -> float:
    """1.0 when test and train expectancy are equal, falling to 0 when they differ by the full magnitude."""
    denom = max(abs(test_exp), abs(train_exp), 1e-9)
    return max(0.0, 1.0 - abs(test_exp - train_exp) / denom)


def _plateau(rows: List[Dict[str, Any]], cfg: RankerConfig) -> None:
    """
    Fill ``n_neighbors``, ``plateau_score`` and ``_neighbors`` for each row,
    using all rows of the pool (including ones that failed the test, so a bad
    neighbour lowers the score).
    """
    def good(r):
        return r["pf"] >= cfg.min_pf and r["test_exp"] > 0
    for i, r in enumerate(rows):
        nbrs = [j for j, o in enumerate(rows) if j != i and are_similar(r, o, cfg)]
        r["_neighbors"] = nbrs
        r["n_neighbors"] = len(nbrs)
        if len(nbrs) < cfg.min_neighbors:
            r["plateau_score"] = 0.0
            continue
        group = [r] + [rows[j] for j in nbrs]
        share = sum(good(g) for g in group) / len(group)
        pfs = np.array([g["pf"] for g in group])
        cv = float(pfs.std() / pfs.mean()) if pfs.mean() > 0 else 1.0
        r["plateau_score"] = share * (1.0 - min(1.0, cv))


def _score(r: Dict[str, Any], cfg: RankerConfig, trade_floor: int, weights: Dict[str, float]) -> float:
    parts = {
        "pf": min(max((r["pf"] - 1.0) / 2.0, 0.0), 1.0),            # PF 3.0 => full marks
        "exp": min(max(r["test_exp"] / 0.5, 0.0), 1.0),             # 0.5R => full marks
        "freq": min(max(math.log(max(r["n_trades"], 1) / max(trade_floor, 1)) / math.log(10), 0.0), 1.0),
        "plateau": r["plateau_score"],
        "stab": r["stability"],
        "consistency": r.get("consistency", 0.0),
    }
    return 100.0 * sum(weights[k] * parts[k] for k in weights) / sum(weights.values())


def _flags(r: Dict[str, Any]) -> str:
    out = []
    if r["uses_calendar"]:
        out.append("CAL")
    if r["uses_custom"]:
        out.append("CUSTOM")
    return ",".join(out)


def _reject_reasons(r: Dict[str, Any], cfg: RankerConfig, min_trades: int) -> List[str]:
    reasons = []
    if r["n_trades"] < min_trades:
        reasons.append("low_frequency")
    if r["pf"] < cfg.min_pf:
        reasons.append("low_pf")
    if not (r["sensitivity"] >= cfg.min_sensitivity):  # NaN fails too
        reasons.append("low_sensitivity")
    if r["plateau_score"] < cfg.min_plateau_score:
        reasons.append("no_plateau")
    return reasons


def _dedupe(rows_sorted: List[Dict[str, Any]], cfg: RankerConfig) -> List[Dict[str, Any]]:
    """
    Greedy near-duplicate removal on score-sorted rows: keep a row only if it
    is not similar to an already kept (better) one; the dropped ones are
    recorded under the kept row's ``similar``.
    """
    kept: List[Dict[str, Any]] = []
    for r in rows_sorted:
        for k in kept:
            if are_similar(r, k, cfg):
                k.setdefault("similar", []).append(r["condition"])
                break
        else:
            kept.append(r)
    return kept


# --------------------------------------------------------------------------
# Window and timeframe ranking
# --------------------------------------------------------------------------

def rank_window(df: pd.DataFrame, cfg: RankerConfig, sort_mode: bool = False) -> Dict[str, Any]:
    rows = _normalise(df)
    _plateau(rows, cfg)
    ok, rejected = [], {}
    for r in rows:
        r["stability"] = _stability(r["test_exp"], r["train_exp"])
        reasons = _reject_reasons(r, cfg, cfg.min_window_trades)
        if not r["test_passed"] and (sort_mode or cfg.require_test_passed):
            reasons.append("test_failed")
        if sort_mode:
            # Sort mode: nothing is rejected; failed checks become warnings.
            if r["n_trades"] <= 0:
                continue
            r["warnings"] = reasons
        elif reasons:
            for x in reasons:
                rejected[x] = rejected.get(x, 0) + 1
            continue
        r["score"] = _score(r, cfg, cfg.min_window_trades, WEIGHTS_WINDOW)
        ok.append(r)
    ok.sort(key=lambda r: r["score"], reverse=True)
    top = _dedupe(ok, cfg) if (not sort_mode or cfg.sort_dedupe) else ok
    limit = cfg.sort_top_n if sort_mode else cfg.top_n_window
    return {"n_total": len(rows), "n_pass": len(ok), "n_unique": len(top),
            "rejected": rejected, "top": top[:limit]}


def _weighted(values: pd.Series, weights: pd.Series) -> float:
    w = weights.to_numpy(dtype=float)
    v = values.to_numpy(dtype=float)
    mask = ~np.isnan(v)
    if not mask.any():
        return float("nan")
    if w[mask].sum() <= 0:
        return float(v[mask].mean())
    return float(np.average(v[mask], weights=w[mask]))


def aggregate_timeframe(windows: Dict[str, pd.DataFrame], cfg: RankerConfig) -> List[Dict[str, Any]]:
    """
    Collapse all windows into one row per (condition, direction). PF and
    expectancies are trade-weighted means across windows (an approximation:
    exact pooled PF would need the individual trades).
    """
    frames = []
    for label, df in windows.items():
        d = df.copy()
        d["_window"] = label
        frames.append(d)
    all_rows = pd.concat(frames, ignore_index=True)
    # Older result files may lack the flag/pass columns.
    for col, default in (("uses_calendar", False), ("uses_custom_indicators", False),
                         ("test_passed", False), ("direction", "")):
        if col not in all_rows.columns:
            all_rows[col] = default
        all_rows[col] = all_rows[col].fillna(default)
    for col in ("test_profit_factor", "test_expectancy_r", "train_expectancy_r",
                "test_n_trades", "train_sensitivity_score", "optimal_holding_bars"):
        all_rows[col] = pd.to_numeric(all_rows[col], errors="coerce")
    all_rows["test_profit_factor"] = all_rows["test_profit_factor"].replace(np.inf, PF_CAP).clip(0, PF_CAP)
    all_rows["test_n_trades"] = all_rows["test_n_trades"].fillna(0)
    n_windows_total = len(windows)

    out = []
    for (cond, direction), g in all_rows.groupby(["condition", "direction"], sort=False):
        w = g["test_n_trades"]
        pf_ok = g["test_profit_factor"] >= cfg.min_pf
        passed = g["test_passed"].astype(bool) & pf_ok & (g["test_n_trades"] >= cfg.min_window_trades)
        rows = _normalise(g.assign(
            test_profit_factor=_weighted(g["test_profit_factor"], w),
            test_expectancy_r=_weighted(g["test_expectancy_r"], w),
            train_expectancy_r=_weighted(g["train_expectancy_r"], w),
            test_n_trades=int(w.sum()),
            train_sensitivity_score=g["train_sensitivity_score"].mean(),
            optimal_holding_bars=int(g["optimal_holding_bars"].mode().iloc[0]),
        ).iloc[:1])
        r = rows[0]
        r["n_windows"] = int(g["_window"].nunique())
        r["n_windows_passed"] = int(passed.sum())
        r["consistency"] = r["n_windows_passed"] / max(n_windows_total, 1)
        r["uses_calendar"] = bool(g["uses_calendar"].astype(bool).any())
        r["uses_custom"] = bool(g["uses_custom_indicators"].astype(bool).any())
        out.append(r)
    return out


def rank_timeframe(windows: Dict[str, pd.DataFrame], cfg: RankerConfig,
                   sort_mode: bool = False) -> Dict[str, Any]:
    rows = aggregate_timeframe(windows, cfg)
    _plateau(rows, cfg)
    min_windows = min(cfg.min_windows, len(windows))
    ok, rejected = [], {}
    for r in rows:
        r["stability"] = _stability(r["test_exp"], r["train_exp"])
        reasons = _reject_reasons(r, cfg, cfg.min_total_trades)
        if r["n_windows_passed"] < min_windows:
            reasons.append("few_windows")
        if r["test_exp"] <= 0 and "low_pf" not in reasons:
            reasons.append("non_positive_expectancy")
        if sort_mode:
            if r["n_trades"] <= 0:
                continue
            r["warnings"] = reasons
        elif reasons:
            for x in reasons:
                rejected[x] = rejected.get(x, 0) + 1
            continue
        r["score"] = _score(r, cfg, cfg.min_total_trades, WEIGHTS_TIMEFRAME)
        ok.append(r)
    ok.sort(key=lambda r: r["score"], reverse=True)
    top = _dedupe(ok, cfg) if (not sort_mode or cfg.sort_dedupe) else ok
    limit = cfg.sort_top_n if sort_mode else cfg.top_n_timeframe
    return {"n_total": len(rows), "n_pass": len(ok), "n_unique": len(top),
            "rejected": rejected, "top": top[:limit],
            "min_windows": min_windows, "n_windows": len(windows)}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _fmt_rejected(rej: Dict[str, int]) -> str:
    if not rej:
        return "none"
    return ", ".join(f"{k}={v}" for k, v in sorted(rej.items(), key=lambda kv: -kv[1]))


def _table(top: List[Dict[str, Any]], timeframe_level: bool, sort_mode: bool = False) -> List[str]:
    head = ["#", "Condition", "Dir", "Hold", "Trades", "PF", "Exp R", "Train Exp R", "Stab", "Plateau", "Nbrs"]
    if timeframe_level:
        head += ["Windows ok"]
    head += ["Score", "Flags"]
    if sort_mode:
        head += ["Warnings"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for i, r in enumerate(top, 1):
        cells = [str(i), f"`{r['condition']}`", r["direction"], str(r["holding_bars"]),
                 str(r["n_trades"]), f"{r['pf']:.2f}", f"{r['test_exp']:.3f}",
                 f"{r['train_exp']:.3f}", f"{r['stability']:.2f}",
                 f"{r['plateau_score']:.2f}", str(r["n_neighbors"])]
        if timeframe_level:
            cells.append(f"{r['n_windows_passed']}/{r['n_windows']}")
        cells += [f"{r['score']:.1f}", _flags(r)]
        if sort_mode:
            cells.append(", ".join(r.get("warnings", [])) or "-")
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _similar_notes(top: List[Dict[str, Any]]) -> List[str]:
    notes = []
    for i, r in enumerate(top, 1):
        sim = r.get("similar")
        if sim:
            shown = "; ".join(f"`{s}`" for s in sim[:3])
            more = f" (+{len(sim) - 3} more)" if len(sim) > 3 else ""
            notes.append(f"- #{i} also stands for {len(sim)} similar EA(s): {shown}{more}")
    return notes


def build_markdown(symbol: str, timeframe: str, tf_result: Dict[str, Any],
                   win_results: Dict[str, Dict[str, Any]], cfg: RankerConfig,
                   sort_mode: bool = False) -> str:
    title = "Ranker sort result" if sort_mode else "Ranker result"
    L: List[str] = [f"# {title} — {symbol} {timeframe}", ""]
    L += [
        "Scores combine profit factor, expectancy, trade count, EA-level plateau, "
        "out-of-sample stability (test close to train) and, for the timeframe list, "
        "how many windows the combination passed in. Near-duplicate EAs are collapsed.",
        "",
    ]
    if sort_mode:
        L += [
            f"**Sort mode:** nothing is rejected. All combinations are sorted by score and the "
            f"top {cfg.sort_top_n} are listed. The Warnings column shows which of the strict "
            f"filters (filter mode) a combination would fail: low_frequency, low_pf, "
            f"low_sensitivity, no_plateau, test_failed, few_windows, non_positive_expectancy.",
            "",
        ]
    else:
        L += [
            f"Thresholds: PF >= {cfg.min_pf}, sensitivity >= {cfg.min_sensitivity}, "
            f"plateau >= {cfg.min_plateau_score}, window trades >= {cfg.min_window_trades}, "
            f"total trades >= {cfg.min_total_trades}, windows >= {tf_result['min_windows']} "
            f"(of {tf_result['n_windows']}).",
            "",
        ]
    L += [
        "PF/expectancy at timeframe level are trade-weighted means over windows "
        "(approximation). Flags: CAL = uses calendar/news columns (calendar API does not "
        "work in the Strategy Tester), CUSTOM = uses custom indicators.",
        "",
        "## Result top per timeframe", "",
        f"{tf_result['n_total']} distinct combinations, {tf_result['n_pass']} "
        f"{'ranked' if sort_mode else 'passed all filters'}, "
        f"{tf_result['n_unique']} after removing near-duplicates."
        + ("" if sort_mode else f" Rejected by: {_fmt_rejected(tf_result['rejected'])}."), "",
    ]
    empty = "_No combinations._" if sort_mode else "_No combination passed all filters._"
    if tf_result["top"]:
        L += _table(tf_result["top"], True, sort_mode) + [""] + _similar_notes(tf_result["top"]) + [""]
    else:
        L += [empty, ""]
    for label, res in win_results.items():
        L += [f"## Result window {label}", "",
              f"{res['n_total']} candidates, {res['n_pass']} "
              f"{'ranked' if sort_mode else 'passed'}, "
              f"{res['n_unique']} after removing near-duplicates."
              + ("" if sort_mode else f" Rejected by: {_fmt_rejected(res['rejected'])}."), ""]
        if res["top"]:
            L += _table(res["top"], False, sort_mode) + [""] + _similar_notes(res["top"]) + [""]
        else:
            L += [empty, ""]
    return "\n".join(L)


def _write_csv(path: Path, top: List[Dict[str, Any]], sort_mode: bool) -> None:
    rows = []
    for i, r in enumerate(top, 1):
        row = {
            "rank": i, "condition": r["condition"], "direction": r["direction"],
            "holding_bars": r["holding_bars"], "total_trades": r["n_trades"],
            "profit_factor": round(r["pf"], 4), "test_expectancy_r": round(r["test_exp"], 4),
            "train_expectancy_r": round(r["train_exp"], 4), "stability": round(r["stability"], 4),
            "plateau_score": round(r["plateau_score"], 4), "n_neighbors": r["n_neighbors"],
            "windows_passed": r["n_windows_passed"], "windows_seen": r["n_windows"],
            "score": round(r["score"], 2), "flags": _flags(r),
            "n_similar_removed": len(r.get("similar", [])),
        }
        if sort_mode:
            row["warnings"] = ";".join(r.get("warnings", []))
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


MODES = ("filter", "sort", "both")


def run_ranker(run_dir: str | Path, symbol: str, timeframe: str,
               cfg: Optional[RankerConfig] = None, mode: str = "filter") -> Optional[Path]:
    """
    Read results under ``run_dir`` and write the ranker output there.

    mode="filter": strict filters -> ranker_result.md / ranker_top.csv (original ranker)
    mode="sort":   no rejection, sort by score, top N -> ranker_sort_result.md / ranker_sort_top.csv
    mode="both":   both of the above

    Returns the first markdown path written, or None when no window results exist.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    run_dir = Path(run_dir)
    cfg = cfg or RankerConfig()
    windows = load_window_results(run_dir)
    if not windows:
        logger.warning(f"Ranker: no {RESULT_FILENAME} found under {run_dir}; nothing to rank")
        return None

    first: Optional[Path] = None
    for sort_mode in ([False, True] if mode == "both" else [mode == "sort"]):
        tf_result = rank_timeframe(windows, cfg, sort_mode)
        win_results = {label: rank_window(df, cfg, sort_mode) for label, df in windows.items()}
        md_name, csv_name = (SORT_OUTPUT_MD, SORT_OUTPUT_CSV) if sort_mode else (OUTPUT_MD, OUTPUT_CSV)
        md_path = run_dir / md_name
        md_path.write_text(
            build_markdown(symbol, timeframe, tf_result, win_results, cfg, sort_mode), encoding="utf-8")
        _write_csv(run_dir / csv_name, tf_result["top"], sort_mode)
        logger.info(f"Ranker ({'sort' if sort_mode else 'filter'}) result written to {md_path}")
        first = first or md_path
    return first
