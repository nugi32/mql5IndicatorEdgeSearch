"""
Post-run "sort" ranker.

Runs after every pipeline run and writes ``ranker_sort_result.md`` and
``ranker_sort_top.csv`` into the run folder. Nothing is re-simulated; the
ranker only scores what the pipeline already wrote. Two inputs are supported:

  * Walk-forward run: every ``TEST_PERIOD_RESULTS.csv`` under the run folder.
    The markdown has the top combinations for the whole timeframe and for
    every individual window.
  * Normal (single) run: ``STRATEGY_GATE_RESULTS.csv`` in the run folder. One
    flat list. Its trades, profit factor and expectancy come from the Phase 7c
    simulation over the whole dataset, so they are in-sample.

By default nothing is rejected: all combinations are scored and sorted, the top
``sort_top_n`` are listed, and every failed check is shown as a warning.
With ``ranker_drop_below_floor: true`` combinations below the trade floor
(``min_window_trades`` for a single run, ``min_total_trades`` for the timeframe
list of a walk-forward run) are dropped instead.
Scoring rules:

  * Frequency: trade count relative to a floor (per window, or total for the
    timeframe list).
  * Profit factor and expectancy.
  * EA-level plateau: a combination only counts as a plateau when *similar*
    combinations (same direction, same indicator/operator set, nearby
    thresholds and holding bars) also produce good results. An isolated
    combination with no good neighbours is a spike and scores 0 for plateau.
  * Out-of-sample stability (walk-forward input only): a test result close to
    the train result scores extra. A normal run has no train columns, so this
    term is left out of its score.
  * Identical copies (same direction, holding bars, trade count and
    expectancy) are collapsed before ranking, keeping the one with the fewest
    condition atoms. Near-duplicate EAs are then collapsed after scoring: only
    the best-scoring EA of a group of similar EAs is listed.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RESULT_FILENAME = "TEST_PERIOD_RESULTS.csv"
GATE_FILENAME = "STRATEGY_GATE_RESULTS.csv"
SORT_OUTPUT_MD = "ranker_sort_result.md"
SORT_OUTPUT_CSV = "ranker_sort_top.csv"

# STRATEGY_GATE_RESULTS.csv column -> column name the ranker reads. Columns that
# keep their name (condition, direction, optimal_holding_bars, uses_calendar,
# uses_custom_indicators) are not listed.
GATE_COLUMN_MAP = {
    "sim_n_trades": "test_n_trades",
    "sim_profit_factor": "test_profit_factor",
    "sim_expectancy_r": "test_expectancy_r",
    "gate_passed": "test_passed",
}
GATE_REQUIRED_COLUMNS = ("condition", "direction", "optimal_holding_bars", *GATE_COLUMN_MAP)

PF_CAP = 10.0  # profit factors above this (or inf) are clipped before scoring

# Score weights. The timeframe-level score adds window consistency.
WEIGHTS_WINDOW = {"pf": 0.25, "exp": 0.15, "freq": 0.15, "plateau": 0.25, "stab": 0.20}
WEIGHTS_TIMEFRAME = {"pf": 0.20, "exp": 0.10, "freq": 0.10, "plateau": 0.20,
                     "stab": 0.15, "consistency": 0.25}


@dataclass
class RankerConfig:
    """All thresholds. Override via pipeline_config.yaml keys ``ranker_<name>``."""
    min_window_trades: int = 20        # warning/score floor: trades in one window (or in a single run)
    min_total_trades: int = 100        # warning/score floor: trades summed over all windows (timeframe list)
    min_windows: int = 3               # windows a combination must pass in (capped by run size); else a warning
    min_pf: float = 1.3
    min_sensitivity: float = 0.7       # pipeline's own parameter-sensitivity score (walk-forward input only)
    min_plateau_score: float = 0.5     # EA-neighbourhood plateau score
    min_neighbors: int = 1             # fewer similar EAs than this => isolated spike
    threshold_rel_tol: float = 0.30    # thresholds this close (relative) count as similar
    holding_abs_tol: int = 2           # holding bars this close count as similar
    holding_rel_tol: float = 0.25
    sort_top_n: int = 20               # list length per timeframe and per window (or for a single run)
    sort_dedupe: bool = True           # collapse near-duplicate EAs after scoring
    drop_below_floor: bool = False     # True: drop (instead of only warning about) combinations below the trade floor
                                       # (min_window_trades for a single run, min_total_trades for the timeframe list)


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


def load_gate_results(run_dir: Path) -> Optional[pd.DataFrame]:
    """
    Read ``STRATEGY_GATE_RESULTS.csv`` of a normal run and rename its columns to
    the names the ranker reads (see GATE_COLUMN_MAP). Returns None when the file
    is missing or has no rows. A file that lacks a required column raises
    ValueError instead of being ranked with invented values.
    """
    path = Path(run_dir) / GATE_FILENAME
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return None
    if len(df) == 0:
        return None
    missing = [c for c in GATE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing required column(s): {', '.join(missing)}")
    return df.rename(columns=GATE_COLUMN_MAP)


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
        "stab": r.get("stability", 0.0),   # not in the weights when there is no train data
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


def _warning_reasons(r: Dict[str, Any], cfg: RankerConfig, min_trades: int,
                     check_sensitivity: bool = True) -> List[str]:
    """Checks a combination did not meet. They are shown as warnings, nothing is dropped."""
    reasons = []
    if r["n_trades"] < min_trades:
        reasons.append("low_frequency")
    if r["pf"] < cfg.min_pf:
        reasons.append("low_pf")
    if check_sensitivity and not (r["sensitivity"] >= cfg.min_sensitivity):  # NaN fails too
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


def collapse_identical(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Collapse rows that have the same (direction, holding bars, trade count,
    expectancy) into one: the row with the fewest condition atoms (the first one
    on a tie). Such rows are the same trades written differently, e.g.
    ``mom_10 > -5`` and ``mom_10 > 0`` when ``mom_10`` is always above 0.
    The dropped conditions are recorded under the kept row's ``similar``.
    Returns ``(kept_rows, number_of_rows_removed)``.
    """
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r["direction"], r["holding_bars"], r["n_trades"], r["test_exp"])
        groups.setdefault(key, []).append(r)
    kept: List[Dict[str, Any]] = []
    for group in groups.values():
        best = min(group, key=lambda g: len(g["_atoms"]))  # min() keeps the first of equal rows
        dropped = [g["condition"] for g in group if g is not best]
        if dropped:
            best["similar"] = dropped
        kept.append(best)
    return kept, len(rows) - len(kept)


def _weights(base: Dict[str, float], has_train: bool) -> Dict[str, float]:
    """Score weights; the stability term is left out when there is no train data."""
    return base if has_train else {k: v for k, v in base.items() if k != "stab"}


# --------------------------------------------------------------------------
# Window and timeframe ranking
# --------------------------------------------------------------------------

def rank_window(df: pd.DataFrame, cfg: RankerConfig, single_run: bool = False) -> Dict[str, Any]:
    """
    Score and sort one table of results. ``single_run=True`` is the table of a
    normal run (STRATEGY_GATE_RESULTS.csv after renaming): it has no train
    columns, so the stability term and the sensitivity warning are not used.
    """
    rows, n_identical = collapse_identical(_normalise(df))
    _plateau(rows, cfg)
    weights = _weights(WEIGHTS_WINDOW, has_train=not single_run)
    ok = []
    for r in rows:
        if not single_run:
            r["stability"] = _stability(r["test_exp"], r["train_exp"])
        reasons = _warning_reasons(r, cfg, cfg.min_window_trades, check_sensitivity=not single_run)
        if not r["test_passed"]:
            reasons.append("gate_failed" if single_run else "test_failed")
        if r["n_trades"] <= 0:
            continue
        if single_run and cfg.drop_below_floor and r["n_trades"] < cfg.min_window_trades:
            continue  # below the trade floor: excluded, not just warned about
        r["warnings"] = reasons
        r["score"] = _score(r, cfg, cfg.min_window_trades, weights)
        ok.append(r)
    ok.sort(key=lambda r: r["score"], reverse=True)
    top = _dedupe(ok, cfg) if cfg.sort_dedupe else ok
    return {"n_total": len(rows), "n_identical": n_identical, "n_ranked": len(ok),
            "n_unique": len(top), "top": top[:cfg.sort_top_n]}


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


def rank_timeframe(windows: Dict[str, pd.DataFrame], cfg: RankerConfig) -> Dict[str, Any]:
    rows, n_identical = collapse_identical(aggregate_timeframe(windows, cfg))
    _plateau(rows, cfg)
    min_windows = min(cfg.min_windows, len(windows))
    ok = []
    for r in rows:
        r["stability"] = _stability(r["test_exp"], r["train_exp"])
        reasons = _warning_reasons(r, cfg, cfg.min_total_trades)
        if r["n_windows_passed"] < min_windows:
            reasons.append("few_windows")
        if r["test_exp"] <= 0 and "low_pf" not in reasons:
            reasons.append("non_positive_expectancy")
        if r["n_trades"] <= 0:
            continue
        if cfg.drop_below_floor and r["n_trades"] < cfg.min_total_trades:
            continue  # below the trade floor: excluded, not just warned about
        r["warnings"] = reasons
        r["score"] = _score(r, cfg, cfg.min_total_trades, WEIGHTS_TIMEFRAME)
        ok.append(r)
    ok.sort(key=lambda r: r["score"], reverse=True)
    top = _dedupe(ok, cfg) if cfg.sort_dedupe else ok
    return {"n_total": len(rows), "n_identical": n_identical, "n_ranked": len(ok),
            "n_unique": len(top), "top": top[:cfg.sort_top_n],
            "min_windows": min_windows, "n_windows": len(windows)}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _table(top: List[Dict[str, Any]], timeframe_level: bool, single_run: bool = False) -> List[str]:
    head = ["#", "Condition", "Dir", "Hold", "Trades", "PF", "Exp R"]
    if not single_run:
        head += ["Train Exp R", "Stab"]
    head += ["Plateau", "Nbrs"]
    if timeframe_level:
        head += ["Windows ok"]
    head += ["Score", "Flags", "Warnings"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for i, r in enumerate(top, 1):
        cells = [str(i), f"`{r['condition']}`", r["direction"], str(r["holding_bars"]),
                 str(r["n_trades"]), f"{r['pf']:.2f}", f"{r['test_exp']:.3f}"]
        if not single_run:
            cells += [f"{r['train_exp']:.3f}", f"{r['stability']:.2f}"]
        cells += [f"{r['plateau_score']:.2f}", str(r["n_neighbors"])]
        if timeframe_level:
            cells.append(f"{r['n_windows_passed']}/{r['n_windows']}")
        cells += [f"{r['score']:.1f}", _flags(r), ", ".join(r.get("warnings", [])) or "-"]
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


def _counts_line(res: Dict[str, Any], what: str) -> str:
    identical = (f" {res['n_identical']} identical copies were collapsed before ranking."
                 if res["n_identical"] else "")
    return (f"{res['n_total']} {what}, {res['n_ranked']} ranked, "
            f"{res['n_unique']} after removing near-duplicates.{identical}")


def _warning_legend(cfg: RankerConfig, failed_label: str, single_run: bool) -> str:
    names = ["low_frequency", "low_pf"]
    if not single_run:
        names.append("low_sensitivity")
    names += ["no_plateau", failed_label]
    if not single_run:
        names += ["few_windows", "non_positive_expectancy"]
    return (f"The Warnings column lists the checks a combination did not meet ({', '.join(names)}); "
            f"nothing is dropped because of them. Thresholds: PF >= {cfg.min_pf}, "
            f"plateau >= {cfg.min_plateau_score}"
            + ("" if single_run else f", sensitivity >= {cfg.min_sensitivity}") + ".")


def build_markdown(symbol: str, timeframe: str, tf_result: Dict[str, Any],
                   win_results: Dict[str, Dict[str, Any]], cfg: RankerConfig) -> str:
    """Markdown for a walk-forward run: timeframe list plus one list per window."""
    L: List[str] = [f"# Ranker sort result — {symbol} {timeframe}", ""]
    L += [
        "Scores combine profit factor, expectancy, trade count, EA-level plateau, "
        "out-of-sample stability (test close to train) and, for the timeframe list, "
        "how many windows the combination passed in. Near-duplicate EAs are collapsed.",
        "",
        f"**Sort ranker:** nothing is rejected. All combinations are sorted by score and the "
        f"top {cfg.sort_top_n} are listed. " + _warning_legend(cfg, "test_failed", False),
        "",
        "PF/expectancy at timeframe level are trade-weighted means over windows "
        "(approximation). Flags: CAL = uses calendar/news columns (calendar API does not "
        "work in the Strategy Tester), CUSTOM = uses custom indicators.",
        "",
        "## Result top per timeframe", "",
        _counts_line(tf_result, "distinct combinations")
        + f" Windows needed: {tf_result['min_windows']} (of {tf_result['n_windows']}).", "",
    ]
    if tf_result["top"]:
        L += _table(tf_result["top"], True) + [""] + _similar_notes(tf_result["top"]) + [""]
    else:
        L += ["_No combinations._", ""]
    for label, res in win_results.items():
        L += [f"## Result window {label}", "", _counts_line(res, "candidates"), ""]
        if res["top"]:
            L += _table(res["top"], False) + [""] + _similar_notes(res["top"]) + [""]
        else:
            L += ["_No combinations._", ""]
    return "\n".join(L)


def build_markdown_single(symbol: str, timeframe: str, result: Dict[str, Any], cfg: RankerConfig) -> str:
    """Markdown for a normal run: one flat list from STRATEGY_GATE_RESULTS.csv."""
    L: List[str] = [
        f"# Ranker sort result — {symbol} {timeframe}", "",
        f"**Source:** {GATE_FILENAME} (single run). Trades, PF and expectancy are from the "
        "Phase 7c simulation over the whole dataset, so they are **in-sample**, not an "
        "out-of-sample test period. The file has no train columns, so the stability score and "
        "the sensitivity warning are not used.", "",
        f"**Sort ranker:** nothing is rejected. All combinations are sorted by score and the "
        f"top {cfg.sort_top_n} are listed. " + _warning_legend(cfg, "gate_failed", True)
        + " `gate_failed` means gate_passed is False.", "",
        "Flags: CAL = uses calendar/news columns (calendar API does not work in the Strategy "
        "Tester), CUSTOM = uses custom indicators.", "",
        "## Result", "", _counts_line(result, "candidates"), "",
    ]
    if result["top"]:
        L += _table(result["top"], False, single_run=True) + [""] + _similar_notes(result["top"]) + [""]
    else:
        L += ["_No combinations._", ""]
    return "\n".join(L)


CSV_COLUMNS_WALKFORWARD = [
    "rank", "condition", "direction", "holding_bars", "total_trades", "profit_factor",
    "test_expectancy_r", "train_expectancy_r", "stability", "plateau_score", "n_neighbors",
    "windows_passed", "windows_seen", "score", "flags", "n_similar_removed", "warnings",
]
CSV_COLUMNS_SINGLE = [
    "rank", "condition", "direction", "holding_bars", "total_trades", "profit_factor",
    "sim_expectancy_r", "plateau_score", "n_neighbors", "score", "flags",
    "n_similar_removed", "warnings",
]


def _write_csv(path: Path, top: List[Dict[str, Any]], single_run: bool) -> None:
    """Write the top list. The header is always written, so an empty list is still a readable CSV."""
    rows = []
    for i, r in enumerate(top, 1):
        row = {
            "rank": i, "condition": r["condition"], "direction": r["direction"],
            "holding_bars": r["holding_bars"], "total_trades": r["n_trades"],
            "profit_factor": round(r["pf"], 4),
            "plateau_score": round(r["plateau_score"], 4), "n_neighbors": r["n_neighbors"],
            "score": round(r["score"], 2), "flags": _flags(r),
            "n_similar_removed": len(r.get("similar", [])),
            "warnings": ";".join(r.get("warnings", [])),
        }
        if single_run:
            row["sim_expectancy_r"] = round(r["test_exp"], 4)
        else:
            row.update({
                "test_expectancy_r": round(r["test_exp"], 4),
                "train_expectancy_r": round(r["train_exp"], 4),
                "stability": round(r["stability"], 4),
                "windows_passed": r["n_windows_passed"], "windows_seen": r["n_windows"],
            })
        rows.append(row)
    columns = CSV_COLUMNS_SINGLE if single_run else CSV_COLUMNS_WALKFORWARD
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def run_ranker(run_dir: str | Path, symbol: str, timeframe: str,
               cfg: Optional[RankerConfig] = None) -> Optional[Path]:
    """
    Read the results under ``run_dir`` and write ranker_sort_result.md and
    ranker_sort_top.csv there.

    Input: the TEST_PERIOD_RESULTS.csv files of a walk-forward run if there are
    any, otherwise STRATEGY_GATE_RESULTS.csv of a normal run.

    Returns the markdown path, or None when there is nothing to rank.
    """
    run_dir = Path(run_dir)
    cfg = cfg or RankerConfig()
    windows = load_window_results(run_dir)
    if windows:
        single_run = False
        tf_result = rank_timeframe(windows, cfg)
        win_results = {label: rank_window(df, cfg) for label, df in windows.items()}
        markdown = build_markdown(symbol, timeframe, tf_result, win_results, cfg)
        top = tf_result["top"]
    else:
        gate = load_gate_results(run_dir)
        if gate is None:
            logger.warning(f"Ranker: no {RESULT_FILENAME} or {GATE_FILENAME} with rows found "
                           f"under {run_dir}; nothing to rank")
            return None
        single_run = True
        result = rank_window(gate, cfg, single_run=True)
        markdown = build_markdown_single(symbol, timeframe, result, cfg)
        top = result["top"]
    md_path = run_dir / SORT_OUTPUT_MD
    md_path.write_text(markdown, encoding="utf-8")
    _write_csv(run_dir / SORT_OUTPUT_CSV, top, single_run)
    logger.info(f"Ranker result written to {md_path}")
    return md_path
