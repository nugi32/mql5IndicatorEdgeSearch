"""
Pure, testable logic for the walk-forward meta-pipeline
(scripts/run_walkforward_pipeline.py). No file I/O, no pipeline
orchestration here -- just: given one window's train-period results
(a run_pipeline_core() return value), pick the candidates worth testing
out-of-sample, and evaluate one candidate's FROZEN parameters against a
different (test-period) dataframe slice.

WHY "PLATEAU", NOT JUST "TOP SCORE"
-------------------------------------
Taking the single highest-scoring condition from a train window and
trusting it is exactly how you end up trading noise: with hundreds of
candidate conditions tested, some will score well by chance alone, and a
condition whose score depends on a hair's-breadth threshold value (e.g.
"rsi_14 < 29.4" scoring well but "rsi_14 < 30" or "rsi_14 < 28" scoring
much worse) is far more likely to be exactly that kind of accident than a
condition whose neighborhood of threshold values ALL score similarly
well. The latter -- a broad, flat region of good performance rather than
an isolated spike -- is what "plateau" means here, and it's already
computed by this pipeline's existing parameter-sensitivity test
(edge_research.validation.parameter_sensitivity.sensitivity_test_condition,
run as part of Phase 7's robustness stack): it shifts each condition's
numeric threshold by +/-15% and correlates the resulting forward-probability
profile against the original. A correlation near 1.0 means the
neighborhood behaves like the original (a plateau); a correlation near 0
or negative means small threshold changes produce a very different
profile (a spike). `select_plateau_candidates` reuses that existing
`sensitivity_score` rather than inventing a second, redundant robustness
metric.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from edge_research.conditions.condition_library import (
    CombinedCondition,
    ConditionEvaluator,
)
from edge_research.simulation.trade_simulator import TradeSimResult, simulate_condition

logger = logging.getLogger(__name__)


def _evaluate_condition_generic(evaluator: ConditionEvaluator, condition) -> np.ndarray:
    """Evaluate either an AtomicCondition or a CombinedCondition -- same
    dispatch scripts/run_pipeline.py's Phase 3 uses internally."""
    if isinstance(condition, CombinedCondition):
        return evaluator.evaluate_combined(condition)
    return evaluator.evaluate_atomic(condition)


def select_plateau_candidates(
    validated_edges: List[dict],
    min_sensitivity: float,
    top_k: Optional[int] = None,
) -> List[dict]:
    """
    From one train-window's `run_pipeline_core()` result, select the
    conditions worth testing out-of-sample on the following test window.

    A condition qualifies only if BOTH:
    1. It already passed the full Phase 7e strategy gate on the train
       window (significance, cost, walk-forward direction/holding-bars
       stability, permutation test -- everything `passes_strategy_gate`
       checks).
    2. Its parameter-sensitivity score (see module docstring) is >=
       `min_sensitivity` -- the "plateau, not a spike" requirement. A
       condition with a missing or NaN sensitivity score (couldn't be
       tested -- e.g. no numeric threshold to shift) is EXCLUDED, not
       given the benefit of the doubt, since "untested for fragility" is
       not the same claim as "confirmed not fragile".

    Qualifying conditions are ranked by train-period `expectancy_r`
    (cost-adjusted, from Phase 7c's trade simulation) descending -- "ambil
    yang tertinggi" -- and truncated to `top_k` if given.

    Parameters
    ----------
    validated_edges : list of dict
        `run_pipeline_core()`'s `validated_edges` -- each dict has at
        least 'gate_passed', 'robustness' (with a 'parameter_sensitivity'
        sub-dict containing 'sensitivity_score'), and 'trade_sim' (a
        TradeSimResult).
    min_sensitivity : float
        Minimum parameter-sensitivity correlation score, typically in
        [0, 1] (can be negative for a condition that inverts under a
        small threshold shift). Sourced from pipeline_config.yaml's
        `meta_wf_plateau_min_sensitivity`.
    top_k : int, optional
        Maximum number of candidates to return (highest expectancy_r
        first). None means no cap -- test everything that qualifies.

    Returns
    -------
    list of dict
        The subset of `validated_edges` that qualify, sorted best-first.
    """
    candidates = []
    for edge in validated_edges:
        if not edge.get("gate_passed"):
            continue

        sensitivity_info = edge.get("robustness", {}).get("parameter_sensitivity", {})
        score = sensitivity_info.get("sensitivity_score")
        if score is None or (isinstance(score, float) and np.isnan(score)):
            continue
        if score < min_sensitivity:
            continue

        candidates.append(edge)

    candidates.sort(key=lambda e: e["trade_sim"].expectancy_r, reverse=True)

    if top_k is not None:
        candidates = candidates[:top_k]

    return candidates


@dataclass
class TestPeriodResult:
    test_sim: TradeSimResult
    test_passed: bool


def evaluate_on_test_period(
    edge: dict,
    test_df: pd.DataFrame,
    min_trades: int,
    min_expectancy_r: float,
) -> TestPeriodResult:
    """
    Re-evaluate one train-window-selected condition against a DIFFERENT
    (test-period) dataframe slice, with its direction and holding_bars
    FROZEN exactly as chosen during training -- no re-optimization here.
    Only the condition's trigger mask is recomputed, against the test
    period's own rows, since the same indicator-threshold condition will
    naturally fire on different bars in different data.

    This is the actual out-of-sample check the walk-forward meta-pipeline
    exists to run: a condition that looked good AND had a plateau on the
    train window still has to independently clear a bar on data it was
    never selected using.

    Parameters
    ----------
    edge : dict
        One entry from `select_plateau_candidates`'s output -- needs
        'condition' (the AtomicCondition/CombinedCondition object) and
        'trade_sim' (whose `.config` -- direction, atr_column,
        holding_bars, cost settings -- is reused unchanged).
    test_df : pd.DataFrame
        The test-period slice. Must contain the same columns the
        condition and TradeSimConfig.atr_column reference.
    min_trades : int
        Minimum simulated trades required on the test period to accept
        the condition. Sourced from `meta_wf_test_min_trades` -- test
        windows are typically much shorter than train windows, so this
        is usually set well below the train-side `gate_min_sim_trades`.
    min_expectancy_r : float
        Minimum cost-adjusted expectancy_r required on the test period.
        Sourced from `meta_wf_test_min_expectancy_r` (0.0 by default --
        must be net profitable out-of-sample, not just on training data).

    Returns
    -------
    TestPeriodResult
        `test_sim`: the full TradeSimResult on the test period (for
        reporting). `test_passed`: True only if both thresholds above are
        cleared AND expectancy_r is a real number (not NaN, which happens
        when the condition never triggers a valid trade in the test
        window at all).
    """
    evaluator = ConditionEvaluator(test_df)
    test_mask = _evaluate_condition_generic(evaluator, edge["condition"])

    test_sim = simulate_condition(test_df, test_mask, edge["trade_sim"].config)

    test_passed = (
        test_sim.n_trades >= min_trades
        and not np.isnan(test_sim.expectancy_r)
        and test_sim.expectancy_r >= min_expectancy_r
    )

    return TestPeriodResult(test_sim=test_sim, test_passed=test_passed)


def write_window_summary(all_window_results: List[dict], path) -> None:
    """
    Write a single markdown file summarizing every window: date ranges,
    how many train-period candidates qualified (gate + plateau), how many
    also survived the test period, and the CONDITION (not just an id) for
    every accepted edge.

    Deliberately window-by-window rather than a single aggregate "best
    edges" list -- different windows are EXPECTED to accept different
    (even entirely non-overlapping) sets of conditions; presenting one
    combined ranking would misrepresent that as one static strategy
    rather than what it actually is, a record of what worked in each
    period.

    NOTE ON edge_id: scripts/run_pipeline.py assigns edge_id as a plain
    sequential counter ("XAUUSD_M30_1", "XAUUSD_M30_2", ...) that restarts
    at 1 every time run_pipeline_core() is called -- i.e. on every window.
    The SAME edge_id therefore recurs across unrelated windows referring
    to completely different conditions. This function shows each accepted
    edge's full condition string (and its test-period stats) precisely so
    a reader never has to infer identity from that recycled id alone.
    """
    lines = ["# Walk-Forward Meta-Pipeline Summary\n\n"]

    n_windows = len(all_window_results)
    n_with_edges = sum(1 for w in all_window_results if w["n_accepted"] > 0)
    lines.append(f"- Windows processed: {n_windows}\n")
    lines.append(f"- Windows with at least one accepted edge: {n_with_edges}\n\n")

    lines.append("| window | train period | test period | train candidates | accepted |\n")
    lines.append("|---|---|---|---:|---:|\n")
    for w in all_window_results:
        lines.append(
            f"| {w['window_id']} "
            f"| {w['train_date_start']} .. {w['train_date_end']} "
            f"| {w['test_date_start']} .. {w['test_date_end']} "
            f"| {w['n_train_candidates']} "
            f"| {w['n_accepted']} |\n"
        )

    lines.append("\n## Accepted edges by window\n\n")
    lines.append(
        "Note: `edge_id` restarts from 1 on every window (see this "
        "function's docstring) -- the same id in two different windows is "
        "NOT the same condition. The condition string is what identifies "
        "an edge; treat the id as a within-window label only.\n\n"
    )
    for w in all_window_results:
        lines.append(f"### {w['window_id']}\n\n")
        accepted = w.get("accepted_edges", [])
        if accepted:
            lines.append("| edge_id | condition | direction | holding_bars | test expectancy_r | test PF | test n_trades |\n")
            lines.append("|---|---|---|---:|---:|---:|---:|\n")
            for a in accepted:
                lines.append(
                    f"| {a['edge_id']} | `{a['condition']}` | {a['direction']} "
                    f"| {a['optimal_holding_bars']} | {a['test_expectancy_r']:.4f} "
                    f"| {a['test_profit_factor']:.2f} | {a['test_n_trades']} |\n"
                )
        else:
            lines.append("- (none)\n")
        lines.append("\n")

    with open(path, "w") as f:
        f.writelines(lines)


def generate_calendar_windows(
    df: pd.DataFrame,
    start_year: Optional[int],
    train_years: int,
    test_years: int,
    step_years: int,
) -> List[Dict]:
    """
    Generate rolling (train, test) windows aligned to calendar year
    boundaries (always Jan 1), instead of a fixed bar count.

    WHY THIS EXISTS -- bar-count windows don't align to real dates
    ------------------------------------------------------------------
    A window defined by `meta_wf_train_bars` (a fixed number of rows)
    starts and ends wherever that many rows happens to land -- which
    depends on how many bars actually exist in each stretch of the data
    (weekends, holidays, session gaps all shift it), not on any date a
    human asked for. Two consequences that motivated this function:
    1. "Train on 2010-01-01..2013-01-01" cannot be expressed with a bar
       count at all -- the same train_bars value lands on a different
       real date range depending on how much data came before it.
    2. A genuinely good edge in some memorable calendar period (e.g. one
       you already checked by hand) can silently fail to appear in
       walk-forward mode's results, not because the edge isn't there, but
       because the bar-count window boundaries happened to fall in the
       middle of that period instead of around it -- splitting or diluting
       exactly the stretch of data that mattered.

    Windows here are always anchored to January 1 of `start_year` (or the
    data's own first year if `start_year` is None), train for
    `train_years` calendar years, test for the next `test_years` calendar
    years immediately after (no gap), then roll the START forward by
    `step_years` and repeat.

    HANDLING DATA THAT DOESN'T END ON A CLEAN YEAR BOUNDARY
    ------------------------------------------------------------
    Real market data essentially never ends exactly at a year boundary
    (weekends, the last trading session of the year, export cutoffs).
    Rather than discard an otherwise-almost-complete final window over a
    few missing hours/days, each window records BOTH the nominal
    (calendar-exact) boundary asked for AND the actual boundary the data
    provides (the nearest available bar) -- `truncated=True` flags any
    window whose test period had to be cut short because the data simply
    doesn't extend that far. This is the same "mark it, don't hide it"
    philosophy trade_simulator.py uses for a trade that hits the end of
    the dataset before its intended holding period elapses (outcome
    'timeout'). Always check `truncated` before trusting a window's
    test-period result at face value.

    Parameters
    ----------
    df : pd.DataFrame
        Must have a DatetimeIndex, sorted ascending (as ingest_pipeline
        produces).
    start_year : Optional[int]
        Calendar year the first window's train period starts on Jan 1.
        None -> use the data's own first year.
    train_years, test_years, step_years : int
        Whole calendar years. step_years is how far the train START moves
        forward each iteration -- e.g. step_years == test_years gives
        non-overlapping test periods; a smaller step_years gives
        overlapping test periods across consecutive windows.

    Returns
    -------
    List[Dict]
        One dict per window, in order:
        {
            'train_start_pos', 'train_end_pos',   # positional (iloc) bounds, train
            'test_start_pos', 'test_end_pos',      # positional (iloc) bounds, test
            'train_start_nominal', 'train_end_nominal',   # pd.Timestamp asked for
            'test_start_nominal', 'test_end_nominal',
            'train_start_actual', 'train_end_actual',     # pd.Timestamp actually used
            'test_start_actual', 'test_end_actual',
            'truncated': bool,   # test_end_nominal exceeds the data's last timestamp
        }
        Empty list if `start_year` (or the data's first year) leaves no
        room for even one full train+test period.
    """
    if len(df) == 0:
        return []

    data_start = df.index[0]
    data_end = df.index[-1]

    if start_year is None:
        start_year = data_start.year

    windows: List[Dict] = []
    train_start_nominal = pd.Timestamp(year=start_year, month=1, day=1)

    while train_start_nominal < data_end:
        train_end_nominal = train_start_nominal + pd.DateOffset(years=train_years)
        test_start_nominal = train_end_nominal
        test_end_nominal = test_start_nominal + pd.DateOffset(years=test_years)

        train_start_pos = int(df.index.searchsorted(train_start_nominal))
        train_end_pos = int(df.index.searchsorted(train_end_nominal))
        test_start_pos = train_end_pos  # contiguous, no gap between train and test
        test_end_pos = int(df.index.searchsorted(test_end_nominal))
        test_end_pos = min(test_end_pos, len(df))

        if train_end_pos <= train_start_pos or test_end_pos <= test_start_pos:
            if train_start_nominal < data_start:
                # This train_start is still entirely before the data even
                # begins (e.g. start_year is earlier than the file's own
                # history) -- there may well be usable data at a LATER
                # train_start, so advance and keep looking rather than
                # giving up immediately.
                train_start_nominal = train_start_nominal + pd.DateOffset(years=step_years)
                continue
            # Otherwise we've genuinely run past the end of the usable
            # data -- stop, don't emit an empty window.
            break

        truncated = test_end_nominal > data_end

        windows.append({
            "train_start_pos": train_start_pos, "train_end_pos": train_end_pos,
            "test_start_pos": test_start_pos, "test_end_pos": test_end_pos,
            "train_start_nominal": train_start_nominal, "train_end_nominal": train_end_nominal,
            "test_start_nominal": test_start_nominal, "test_end_nominal": test_end_nominal,
            "train_start_actual": df.index[train_start_pos],
            "train_end_actual": df.index[train_end_pos - 1],
            "test_start_actual": df.index[test_start_pos],
            "test_end_actual": df.index[test_end_pos - 1],
            "truncated": truncated,
        })

        if truncated:
            # The data ran out partway through this window's nominal test
            # period -- there is nothing left to start a further window
            # from, so this is the last one for this run.
            break

        train_start_nominal = train_start_nominal + pd.DateOffset(years=step_years)

    return windows


def write_multi_run_summary(runs: List[Dict], path) -> None:
    """
    Same purpose as `write_window_summary`, for calendar-based mode where
    multiple independent `meta_wf_runs` entries (different start_year
    anchors) were each rolled forward over the same data. Grouped by run
    first, since windows from different runs are independent walk-forward
    sequences, not one combined sequence -- presenting them flattened
    together would make windows from different runs that happen to cover
    overlapping calendar periods look like they belong to the same
    sequence.

    Parameters
    ----------
    runs : List[Dict]
        [{'run_label': str, 'start_year', 'train_years', 'test_years',
          'step_years', 'windows': [ ... same per-window dicts
          write_window_summary uses, each also carrying 'truncated',
          'train_date_start'/'train_date_end'/'test_date_start'/
          'test_date_end' as the ACTUAL (not nominal) dates used ... ]}]
    path : path to write the .md file to
    """
    lines = ["# Walk-Forward Meta-Pipeline Summary (calendar mode)\n\n"]

    total_windows = sum(len(r["windows"]) for r in runs)
    total_with_edges = sum(
        1 for r in runs for w in r["windows"] if w["n_accepted"] > 0
    )
    lines.append(f"- Runs: {len(runs)}\n")
    lines.append(f"- Total windows across all runs: {total_windows}\n")
    lines.append(f"- Windows with at least one accepted edge: {total_with_edges}\n\n")
    lines.append(
        "Note: `edge_id` restarts from 1 on every window (see "
        "`write_window_summary`'s docstring) -- the same id in two "
        "different windows, even within the same run, is NOT the same "
        "condition. The condition string is what identifies an edge.\n\n"
    )

    for r in runs:
        lines.append(
            f"## Run: start_year={r['start_year']} "
            f"(train={r['train_years']}y, test={r['test_years']}y, step={r['step_years']}y)\n\n"
        )

        lines.append("| window | train period (actual) | test period (actual) | truncated | train candidates | accepted |\n")
        lines.append("|---|---|---|---|---:|---:|\n")
        for w in r["windows"]:
            lines.append(
                f"| {w['window_id']} "
                f"| {w['train_date_start']} .. {w['train_date_end']} "
                f"| {w['test_date_start']} .. {w['test_date_end']} "
                f"| {'YES -- see note below' if w['truncated'] else 'no'} "
                f"| {w['n_train_candidates']} "
                f"| {w['n_accepted']} |\n"
            )

        lines.append("\n### Accepted edges\n\n")
        for w in r["windows"]:
            lines.append(f"#### {w['window_id']}\n\n")
            if w["truncated"]:
                lines.append(
                    "**Truncated window** -- the nominal test period "
                    f"({w['test_date_start_nominal']} .. {w['test_date_end_nominal']}) "
                    "extends past the end of the available data; the "
                    f"actual test period used was only "
                    f"{w['test_date_start']} .. {w['test_date_end']}. Treat "
                    "this window's results as based on a shorter, possibly "
                    "much shorter, OOS period than the other windows.\n\n"
                )
            accepted = w.get("accepted_edges", [])
            if accepted:
                lines.append("| edge_id | condition | direction | holding_bars | test expectancy_r | test PF | test n_trades |\n")
                lines.append("|---|---|---|---:|---:|---:|---:|\n")
                for a in accepted:
                    lines.append(
                        f"| {a['edge_id']} | `{a['condition']}` | {a['direction']} "
                        f"| {a['optimal_holding_bars']} | {a['test_expectancy_r']:.4f} "
                        f"| {a['test_profit_factor']:.2f} | {a['test_n_trades']} |\n"
                    )
            else:
                lines.append("- (none)\n")
            lines.append("\n")

    with open(path, "w") as f:
        f.writelines(lines)
