"""
Walk-forward meta-pipeline.

Runs the ENTIRE existing edge-discovery pipeline (Phases 2-9, via
scripts.run_pipeline.run_pipeline_core) independently on each rolling
(train, test) window of the data -- exactly the "Rolling Out-of-Sample"
scheme: a train window, immediately followed by a test window, the whole
pair sliding forward each iteration.

Per window:
1. Run the full pipeline on the TRAIN slice (condition generation through
   the Phase 7e strategy gate) -- same as a normal single run, just
   scoped to this window's data.
2. From the conditions that passed that gate, select the ones that ALSO
   sit on a performance plateau, not a fragile spike -- see
   edge_research.walkforward.meta_orchestrator.select_plateau_candidates.
3. Re-evaluate each of those, with direction/holding_bars FROZEN exactly
   as chosen on train, against the TEST slice -- true out-of-sample data
   never used for selection. Keep only what's still net profitable there.
4. Record whatever was accepted (zero or more conditions -- a window
   accepting nothing is not a failure, it's a valid result) and move to
   the next window. Different windows are allowed to accept completely
   different conditions -- see README.md's "Walk-forward mode" section.

TWO WINDOWING MODES
--------------------
This script supports two ways of defining the outer rolling windows,
chosen by which config keys are present in pipeline_config.yaml:

- CALENDAR mode (`meta_wf_runs` present): windows are anchored to
  Jan 1 of a given year and sized in whole calendar years -- e.g. "train
  2010-01-01..2013-01-01, test 2013-01-01..2014-01-01, then roll forward
  1 year". `meta_wf_runs` is a LIST, and each entry runs independently
  over the whole file (its own full sequence of rolling windows) -- e.g.
  one entry anchored at 2010 and another at 2011 are two separate,
  overlapping-by-one-year walk-forward sequences, not one combined
  sequence. This is the mode config/WALKFORWARD/<SYMBOL>/<TF>/ uses.
- LEGACY bar-count mode (`meta_wf_train_bars` present instead):
  windows are a fixed number of rows, wherever that many rows happens to
  land chronologically. This is what config/SHORT_DATA/<SYMBOL>/<TF>/
  uses, since a few-month dataset can't fit even one whole calendar year
  of train data -- year-aligned windows don't make sense at that scale.

A config-dir must have one or the other, not neither. If both are
present, calendar mode wins (a config shouldn't normally define both).

Usage:
    python scripts/run_walkforward_pipeline.py \\
        data/raw_csv/XAUUSD_M30_export_20100101.csv \\
        --symbol XAUUSD --timeframe M30 \\
        --config-dir config/WALKFORWARD/XAUUSD/M30 \\
        --output-dir output_walkforward
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edge_research.ingestion.loader import ingest_pipeline
from edge_research.utils.memory import (
    MemoryBudgetExceeded,
    MemoryGuard,
    check_memory,
    log_memory,
    release_memory,
    set_guard,
)
from edge_research.validation.walk_forward import WalkForwardValidator
from edge_research.walkforward.meta_orchestrator import (
    evaluate_on_test_period,
    generate_calendar_windows,
    select_plateau_candidates,
    write_multi_run_summary,
    write_window_summary,
)
from scripts.run_pipeline import load_config, run_pipeline_core

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _process_one_window(
    df: pd.DataFrame,
    known_at_config_path,
    pipeline_config: dict,
    symbol: str,
    timeframe: str,
    window_id: str,
    window_dir: Path,
    train_start: int, train_end: int, test_start: int, test_end: int,
    plateau_min_sensitivity: float,
    top_k: Optional[int],
    test_min_trades: int,
    test_min_expectancy_r: float,
    max_conditions: Optional[int],
) -> dict:
    """
    Shared per-window logic for BOTH windowing modes: run the full
    pipeline on the train slice, select plateau candidates, re-test them
    on the test slice, write TEST_PERIOD_RESULTS.csv, return a result
    dict. Positional (iloc) bounds in, everything else about how those
    bounds were chosen (calendar-year vs bar-count) is the caller's
    concern, not this function's.
    """
    logger.info("\n" + "-" * 80)
    logger.info(
        f"[{window_id}] train=[{train_start}:{train_end}) "
        f"({df.index[train_start]} .. {df.index[train_end - 1]})   "
        f"test=[{test_start}:{test_end}) "
        f"({df.index[test_start]} .. {df.index[test_end - 1]})"
    )

    log_memory(f"[{window_id}] window start")
    check_memory(f"{window_id} start", force=True)

    train_df = df.iloc[train_start:train_end]
    test_df = df.iloc[test_start:test_end]

    # Run the WHOLE normal pipeline (Phases 2-9) on this window's train
    # slice -- same code path as a single-run, just scoped to fewer rows.
    # Writes its own reports/EAs/summary under <window_dir>/train/,
    # exactly like a standalone run would.
    train_result = run_pipeline_core(
        df=train_df,
        known_at_config_path=known_at_config_path,
        pipeline_config=pipeline_config,
        symbol=symbol,
        timeframe=timeframe,
        output_dir=window_dir / "train",
        max_conditions=max_conditions,
    )

    candidates = select_plateau_candidates(
        train_result["validated_edges"],
        min_sensitivity=plateau_min_sensitivity,
        top_k=top_k,
    )
    logger.info(
        f"[{window_id}] {len(candidates)} candidate(s) passed the train-period "
        f"gate AND the plateau check (sensitivity_score >= {plateau_min_sensitivity})"
    )

    accepted = []
    test_rows = []
    for edge in candidates:
        result = evaluate_on_test_period(
            edge, test_df, min_trades=test_min_trades, min_expectancy_r=test_min_expectancy_r,
        )
        sensitivity_info = edge["robustness"].get("parameter_sensitivity", {})
        test_rows.append({
            "edge_id": edge["edge_id"],
            "condition": str(edge["condition"]),
            "direction": edge["direction"],
            "optimal_holding_bars": edge["optimal_holding_bars"],
            "train_expectancy_r": edge["trade_sim"].expectancy_r,
            "train_sensitivity_score": sensitivity_info.get("sensitivity_score"),
            "test_n_trades": result.test_sim.n_trades,
            "test_expectancy_r": result.test_sim.expectancy_r,
            "test_profit_factor": result.test_sim.profit_factor,
            "test_passed": result.test_passed,
        })
        if result.test_passed:
            # edge_id is just a sequential counter that restarts at 1 on
            # every run_pipeline_core() call, so the SAME edge_id recurs
            # across unrelated windows referring to completely different
            # conditions -- carrying the condition string + stats here is
            # what keeps the summary unambiguous.
            accepted.append({
                "edge_id": edge["edge_id"],
                "condition": str(edge["condition"]),
                "direction": edge["direction"],
                "optimal_holding_bars": edge["optimal_holding_bars"],
                "test_expectancy_r": result.test_sim.expectancy_r,
                "test_profit_factor": result.test_sim.profit_factor,
                "test_n_trades": result.test_sim.n_trades,
            })

    window_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(test_rows).to_csv(window_dir / "TEST_PERIOD_RESULTS.csv", index=False)

    if accepted:
        logger.info(
            f"[{window_id}] \u2713 {len(accepted)} / {len(candidates)} candidate(s) "
            f"ALSO passed the test period: "
            f"{[(a['edge_id'], a['condition']) for a in accepted]}"
        )
    else:
        logger.info(
            f"[{window_id}] \u2717 0 / {len(candidates)} candidate(s) passed the test "
            f"period -- no edges accepted for this window, moving on"
        )

    summary = {
        "window_id": window_id,
        "train_date_start": str(df.index[train_start]),
        "train_date_end": str(df.index[train_end - 1]),
        "test_date_start": str(df.index[test_start]),
        "test_date_end": str(df.index[test_end - 1]),
        "n_train_candidates": len(candidates),
        "n_accepted": len(accepted),
        "accepted_edges": accepted,
    }

    # MEMORY: everything heavy this window created (per-edge masks, reports,
    # forward matrix, ...) hangs off `train_result`.  Drop it explicitly and
    # hand the freed heap pages back to the OS so the next window starts from
    # the same footprint instead of ratcheting RSS upward window after window.
    del train_result, candidates, train_df, test_df
    release_memory()
    log_memory(f"[{window_id}] window end (after release)")
    return summary


def _check_inner_wf_fits(pipeline_config: dict, config_dir, observed_train_bars: int, window_desc: str) -> None:
    """
    GUARD: the INNER walk-forward check (direction-consistency +
    holding-bars-stability, run once per window inside run_pipeline_core
    via this same config's wf_train_bars/wf_test_bars) needs to fit
    inside ONE outer train window, or it silently produces zero inner
    windows every single time -- which makes robust_walk_forward and
    holding_bars_stable False for every condition, which makes the
    Phase 7e gate reject everything, which makes every outer window
    report "0 candidates" forever. That failure mode gives no error and
    no crash, just looks like "no edges found" -- so it's checked here
    explicitly instead of being left to manifest as a silent, misleading
    zero.

    `observed_train_bars` is the ACTUAL bar count of a real train window
    (not a config number) -- in calendar mode this varies slightly window
    to window (leap years, holidays), so the caller passes in the first
    window's real count rather than an estimate.
    """
    wf_train_bars = pipeline_config.get("wf_train_bars")
    wf_test_bars = pipeline_config.get("wf_test_bars")
    inner_checks_required = (
        pipeline_config.get("gate_require_walk_forward", True)
        or pipeline_config.get("gate_require_holding_bars_stable", True)
    )
    if not (
        inner_checks_required
        and isinstance(wf_train_bars, (int, float)) and not isinstance(wf_train_bars, bool)
        and isinstance(wf_test_bars, (int, float)) and not isinstance(wf_test_bars, bool)
    ):
        return

    if wf_train_bars + wf_test_bars >= observed_train_bars:
        raise ValueError(
            f"{config_dir}/pipeline_config.yaml is not safe to use for walk-forward "
            f"mode: its inner wf_train_bars + wf_test_bars ({wf_train_bars + wf_test_bars}) "
            f">= the observed train window size ({observed_train_bars} bars, {window_desc}), "
            f"so the inner walk-forward check run inside every window would never produce "
            f"even one window -- every condition would fail the direction-consistency / "
            f"holding-bars-stability gate on every window, silently. This config-dir's "
            f"wf_train_bars/wf_test_bars are almost certainly calibrated for a full "
            f"multi-year file (single-run mode) or a differently-sized window, not this one. "
            f"Use a config-dir whose inner settings were built for this window size instead -- "
            f"e.g. config/SHORT_DATA/<SYMBOL>/<TF>/ for a ~3-month window, or "
            f"config/WALKFORWARD/<SYMBOL>/<TF>/ for a multi-year window. (This check is "
            f"skipped if both gate_require_walk_forward and gate_require_holding_bars_stable "
            f"are set to false in pipeline_config.yaml.)"
        )


def run_walkforward_pipeline(
    csv_path,
    symbol: str,
    timeframe: str,
    config_dir,
    output_dir,
    max_conditions=None,
):
    """
    See module docstring. Returns the calendar-mode `runs` list if
    `meta_wf_runs` is set, otherwise the legacy flat `all_window_results`
    list. Either way, results are also written to WALKFORWARD_SUMMARY.md
    and, per window, to <output_dir>/.../TEST_PERIOD_RESULTS.csv.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config_dir = Path(config_dir)
    pipeline_config = load_config(config_dir / "pipeline_config.yaml")
    known_at_config_path = config_dir / "known_at_delay.yaml"

    plateau_min_sensitivity = pipeline_config.get("meta_wf_plateau_min_sensitivity", 0.7)
    top_k = pipeline_config.get("meta_wf_top_k_per_window", 20)
    test_min_trades = pipeline_config.get("meta_wf_test_min_trades", 5)
    test_min_expectancy_r = pipeline_config.get("meta_wf_test_min_expectancy_r", 0.0)

    meta_wf_runs = pipeline_config.get("meta_wf_runs")
    meta_train_bars = pipeline_config.get("meta_wf_train_bars")

    if not meta_wf_runs and meta_train_bars is None:
        raise ValueError(
            f"{config_dir}/pipeline_config.yaml has neither meta_wf_runs (calendar mode) "
            f"nor meta_wf_train_bars (legacy bar-count mode) -- walk-forward mode needs one "
            f"of these. See README.md's 'Walk-forward mode' section, or use one of the "
            f"config-dirs that already has one set (config/WALKFORWARD/ or config/SHORT_DATA/)."
        )

    # In legacy bar-count mode, meta_train_bars is a static config number
    # (unlike calendar mode, where the real window size depends on which
    # dates are actually present in the data) -- so this can and should
    # be checked before ingestion, failing fast without reading any CSV.
    if not meta_wf_runs:
        _check_inner_wf_fits(
            pipeline_config, config_dir,
            observed_train_bars=meta_train_bars,
            window_desc="meta_wf_train_bars",
        )

    logger.info("=" * 80)
    logger.info("WALK-FORWARD META-PIPELINE START")
    logger.info("=" * 80)
    logger.info(
        f"plateau_min_sensitivity={plateau_min_sensitivity}  top_k_per_window={top_k}  "
        f"test_min_trades={test_min_trades}  test_min_expectancy_r={test_min_expectancy_r}"
    )

    # Ingest the full file ONCE -- each window below is a slice of this
    # same in-memory dataframe, not a re-read of the CSV.
    parquet_dir = output_dir / "storage"
    df, _ = ingest_pipeline(
        csv_path,
        parquet_dir,
        symbol,
        timeframe,
        compression=pipeline_config.get("parquet_compression", "zstd"),
    )
    logger.info(f"\u2713 Ingestion complete: {len(df)} bars loaded, "
                f"{df.index[0]} .. {df.index[-1]}")

    common_kwargs = dict(
        known_at_config_path=known_at_config_path,
        pipeline_config=pipeline_config,
        symbol=symbol,
        timeframe=timeframe,
        plateau_min_sensitivity=plateau_min_sensitivity,
        top_k=top_k,
        test_min_trades=test_min_trades,
        test_min_expectancy_r=test_min_expectancy_r,
        max_conditions=max_conditions,
    )

    if meta_wf_runs:
        logger.info(f"Calendar mode: {len(meta_wf_runs)} run(s) configured in meta_wf_runs")
        runs_out = []

        for run_spec in meta_wf_runs:
            start_year = run_spec.get("start_year")
            train_years = run_spec["train_years"]
            test_years = run_spec["test_years"]
            step_years = run_spec["step_years"]
            run_label = f"run_{start_year if start_year is not None else 'auto'}"

            windows = generate_calendar_windows(df, start_year, train_years, test_years, step_years)
            logger.info(
                f"\n{'=' * 80}\n[{run_label}] start_year={start_year} train={train_years}y "
                f"test={test_years}y step={step_years}y -> {len(windows)} window(s)\n{'=' * 80}"
            )
            if not windows:
                logger.warning(
                    f"[{run_label}] produced 0 windows -- start_year is likely at or past "
                    f"the end of the available data ({df.index[0]} .. {df.index[-1]}). Skipping."
                )
                runs_out.append({
                    "run_label": run_label, "start_year": start_year,
                    "train_years": train_years, "test_years": test_years, "step_years": step_years,
                    "windows": [],
                })
                continue

            first_w = windows[0]
            _check_inner_wf_fits(
                pipeline_config, config_dir,
                observed_train_bars=first_w["train_end_pos"] - first_w["train_start_pos"],
                window_desc=f"{run_label}'s first window, {train_years} calendar year(s)",
            )

            run_windows_out = []
            for i, w in enumerate(windows):
                window_id = f"{run_label}/window_{i:04d}"
                window_dir = output_dir / run_label / f"window_{i:04d}"

                if w["truncated"]:
                    logger.warning(
                        f"[{window_id}] TRUNCATED: nominal test period "
                        f"{w['test_start_nominal'].date()}..{w['test_end_nominal'].date()} "
                        f"extends past the data's last timestamp ({df.index[-1]}); actual "
                        f"test period used is {w['test_start_actual']}..{w['test_end_actual']}. "
                        f"Treat this window's result as based on a shorter OOS period."
                    )

                result = _process_one_window(
                    df, window_id=window_id, window_dir=window_dir,
                    train_start=w["train_start_pos"], train_end=w["train_end_pos"],
                    test_start=w["test_start_pos"], test_end=w["test_end_pos"],
                    **common_kwargs,
                )
                result["truncated"] = w["truncated"]
                result["test_date_start_nominal"] = str(w["test_start_nominal"])
                result["test_date_end_nominal"] = str(w["test_end_nominal"])
                run_windows_out.append(result)

            runs_out.append({
                "run_label": run_label, "start_year": start_year,
                "train_years": train_years, "test_years": test_years, "step_years": step_years,
                "windows": run_windows_out,
            })

        summary_path = output_dir / "WALKFORWARD_SUMMARY.md"
        write_multi_run_summary(runs_out, summary_path)

        total_windows = sum(len(r["windows"]) for r in runs_out)
        total_with_edges = sum(1 for r in runs_out for w in r["windows"] if w["n_accepted"] > 0)
        logger.info("\n" + "=" * 80)
        logger.info("WALK-FORWARD META-PIPELINE COMPLETE")
        logger.info("=" * 80)
        logger.info(
            f"{len(runs_out)} run(s), {total_windows} window(s) total, "
            f"{total_with_edges} had at least one accepted edge"
        )
        logger.info(f"Summary: {summary_path}")
        logger.info("=" * 80)
        return runs_out

    else:
        meta_test_bars = pipeline_config.get("meta_wf_test_bars")
        meta_step_bars = pipeline_config.get("meta_wf_step_bars")
        if meta_test_bars is None or meta_step_bars is None:
            raise ValueError(
                f"{config_dir}/pipeline_config.yaml has meta_wf_train_bars but is missing "
                f"meta_wf_test_bars and/or meta_wf_step_bars (legacy bar-count mode needs "
                f"all three)."
            )
        logger.info(
            f"Legacy bar-count mode: meta_wf_train_bars={meta_train_bars}  "
            f"meta_wf_test_bars={meta_test_bars}  meta_wf_step_bars={meta_step_bars}"
        )

        # (inner-wf-fit guard already checked before ingestion above,
        # since meta_train_bars is a static config number in this mode)
        validator = WalkForwardValidator(df, meta_train_bars, meta_test_bars, meta_step_bars)
        windows = validator.get_windows()
        if not windows:
            raise ValueError(
                f"meta_wf_train_bars ({meta_train_bars}) + meta_wf_test_bars "
                f"({meta_test_bars}) = {meta_train_bars + meta_test_bars} exceeds the "
                f"{len(df)} bars available in this file -- no walk-forward windows fit. "
                f"Lower these in pipeline_config.yaml, or point --config-dir at a "
                f"profile whose meta_wf_* values already match this file's length."
            )
        logger.info(f"\u2713 Generated {len(windows)} walk-forward windows")

        all_window_results = []
        for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
            window_id = f"window_{i:04d}"
            window_dir = output_dir / window_id
            result = _process_one_window(
                df, window_id=window_id, window_dir=window_dir,
                train_start=train_start, train_end=train_end,
                test_start=test_start, test_end=test_end,
                **common_kwargs,
            )
            all_window_results.append(result)

        summary_path = output_dir / "WALKFORWARD_SUMMARY.md"
        write_window_summary(all_window_results, summary_path)

        n_with_edges = sum(1 for w in all_window_results if w["n_accepted"] > 0)
        logger.info("\n" + "=" * 80)
        logger.info("WALK-FORWARD META-PIPELINE COMPLETE")
        logger.info("=" * 80)
        logger.info(f"{len(windows)} windows processed, {n_with_edges} had at least one accepted edge")
        logger.info(f"Summary: {summary_path}")
        logger.info("=" * 80)
        return all_window_results


def main():
    parser = argparse.ArgumentParser(description="Walk-forward meta-pipeline")
    parser.add_argument("csv_path", help="Path to MQL5-exported CSV")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--config-dir", required=True, help="Must contain meta_wf_runs or meta_wf_train_bars in pipeline_config.yaml")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-conditions", type=int, default=None)
    parser.add_argument(
        "--min-free-gb", type=float, default=2.0,
        help="Abort cleanly (instead of freezing the PC) when system-available RAM drops "
             "below this many GB. 0 disables. Default 2.0.",
    )
    parser.add_argument(
        "--max-rss-gb", type=float, default=None,
        help="Abort cleanly when this process' RAM use exceeds this many GB (default: off).",
    )
    args = parser.parse_args()

    set_guard(MemoryGuard(
        max_rss_gb=args.max_rss_gb,
        min_free_gb=(args.min_free_gb if args.min_free_gb and args.min_free_gb > 0 else None),
    ))
    log_memory("startup")

    try:
        run_walkforward_pipeline(
            csv_path=args.csv_path,
            symbol=args.symbol,
            timeframe=args.timeframe,
            config_dir=args.config_dir,
            output_dir=args.output_dir,
            max_conditions=args.max_conditions,
        )
    except MemoryBudgetExceeded as e:
        logger.error(f"STOPPED BY MEMORY GUARD: {e}")
        logger.error(
            f"Windows finished before this point are already written under "
            f"{args.output_dir} (per-window TEST_PERIOD_RESULTS.csv / reports)."
        )
        sys.exit(3)


if __name__ == "__main__":
    main()
