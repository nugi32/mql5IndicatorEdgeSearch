"""
Phase 1-9 Pipeline Orchestration

End-to-end edge discovery pipeline with CLI interface.
"""

import argparse
import logging
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    ConditionEvaluator,
    ConditionGenerator,
)
from edge_research.conditions.frequency_filter import FrequencyFilter
from edge_research.forward_profile.engine import ForwardProfileEngine
from edge_research.forward_profile.significance import SignificanceAnalyzer
from edge_research.ingestion.loader import ingest_pipeline, load_from_parquet
from edge_research.known_at.tagging import KnownAtTagger
from edge_research.mql5_codegen.generator import MQL5CodeGenerator
from edge_research.reporting.edge_report_schema import EdgeReport
from edge_research.reporting.report_generator import (
    EdgeReportGenerator,
    generate_markdown_report,
)
from edge_research.validation.cost_model import CostModel
from edge_research.validation.parameter_sensitivity import sensitivity_test_condition
from edge_research.validation.regime_stress_test import (
    RegimeClassifier,
    stress_test_condition_by_regime,
)
from edge_research.validation.walk_forward import (
    WalkForwardValidator,
    validate_condition_walk_forward,
)

logger = logging.getLogger(__name__)


def indicator_family(column: str) -> str:
    """
    Extract a coarse indicator family name from a column name, e.g.
    'rsi_14' -> 'rsi', 'cci_20' -> 'cci', 'stoch_14_3_3_k' -> 'stoch'.

    Used as a cheap, always-on guard against combining two conditions on the
    same underlying indicator family (e.g. rsi_14 AND rsi_21), independent of
    whatever the measured statistical correlation happens to be for a given
    dataset/threshold pair.
    """
    return column.split("_")[0]


def is_diverse_combo(atoms, max_corr_combine: float, gen: "ConditionGenerator") -> bool:
    """
    True if every pair of atoms in the combo is from a different indicator
    family AND is not statistically redundant (correlation <= max_corr_combine).
    """
    for a, b in combinations(atoms, 2):
        if indicator_family(a.column) == indicator_family(b.column):
            return False
        if gen.are_redundant(a.column, b.column, max_corr_combine):
            return False
    return True


def load_config(config_path: str | Path) -> dict:
    """Load pipeline configuration from YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def run_pipeline(
    csv_path: str | Path,
    symbol: str,
    timeframe: str,
    config_dir: str | Path,
    output_dir: str | Path,
    max_conditions: Optional[int] = None,
) -> None:
    """
    Run full edge discovery pipeline.

    Parameters
    ----------
    csv_path : str | Path
        Path to MQL5-exported CSV.
    symbol : str
        Symbol (e.g., 'EURUSD').
    timeframe : str
        Timeframe (e.g., 'H1').
    config_dir : str | Path
        Directory containing YAML configs.
    output_dir : str | Path
        Output directory for results.
    max_conditions : int, optional
        Limit number of candidate atomic conditions (for testing).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load configs
    pipeline_config = load_config(Path(config_dir) / "pipeline_config.yaml")
    known_at_config_path = Path(config_dir) / "known_at_delay.yaml"

    logger.info("=" * 80)
    logger.info("EDGE RESEARCH PIPELINE START")
    logger.info("=" * 80)

    # PHASE 1: Ingestion
    logger.info("\n[PHASE 1] Ingestion & Storage...")
    parquet_dir = output_dir / "storage"
    df, parquet_path = ingest_pipeline(
        csv_path,
        parquet_dir,
        symbol,
        timeframe,
        compression=pipeline_config.get("parquet_compression", "zstd"),
    )
    logger.info(f"✓ Ingestion complete: {len(df)} bars loaded")

    # PHASE 2: Known-At Tagging
    logger.info("\n[PHASE 2] Known-At Tagging...")
    tagger = KnownAtTagger(known_at_config_path)
    logger.info(f"✓ Known-at tagger initialized")

    # PHASE 3: Condition Generation
    logger.info("\n[PHASE 3] Condition Generation...")
    gen = ConditionGenerator(df, pipeline_config)
    evaluator = ConditionEvaluator(df)

    def evaluate_condition(cond):
        """Evaluate either an AtomicCondition or a CombinedCondition."""
        if isinstance(cond, CombinedCondition):
            return evaluator.evaluate_combined(cond)
        return evaluator.evaluate_atomic(cond)

    # --- Generate atomic candidates ---
    atomic_candidates = []
    for i, atom in enumerate(gen.generate_atomic_conditions()):
        if max_conditions and i >= max_conditions:
            break
        atomic_candidates.append(atom)

    # MA conditions add a 5th indicator family ('ma'), needed if you want combos
    # with more than 4 atoms (max_atoms_per_combo > 4), since is_diverse_combo()
    # requires every atom in a combo to come from a distinct indicator family.
    if pipeline_config.get("include_ma_conditions", False):
        ma_candidates = list(gen.generate_ma_conditions())
        if max_conditions:
            remaining = max(0, max_conditions - len(atomic_candidates))
            ma_candidates = ma_candidates[:remaining]
        atomic_candidates.extend(ma_candidates)

    logger.info(f"  Generated {len(atomic_candidates)} atomic conditions")

    # --- Frequency filter setup (also needed before ranking atomics for combination) ---
    freq_filter = FrequencyFilter(
        df,
        min_occurrence=pipeline_config.get("min_occurrence", 50),
        min_freq_per_year=pipeline_config.get("min_freq_per_year", 10.0),
    )

    # Evaluate + frequency-filter atomic conditions once; masks are reused later
    # so we never re-evaluate the same atomic condition twice.
    atomic_evaluated = []  # list of (cond, mask)
    for cond in atomic_candidates:
        mask = evaluator.evaluate_atomic(cond)
        if freq_filter.passes_filter(mask):
            atomic_evaluated.append((cond, mask))

    logger.info(
        f"  {len(atomic_evaluated)} / {len(atomic_candidates)} atomic conditions "
        f"passed frequency filter"
    )

    # --- Rank atomic conditions by a cheap 1-bar-ahead effect size ---
    # Combining ALL atomic conditions pairwise is combinatorially expensive and
    # multiplies the multiple-testing burden, so we only combine the strongest
    # single-indicator signals (top_n_atomic_for_combine of them).
    open_prices = df["open"].values.astype(np.float32)
    close_prices = df["close"].values.astype(np.float32)
    n_bars = len(df)
    next_open = np.roll(open_prices, -1)
    next_close = np.roll(close_prices, -2)
    valid_1bar = np.arange(n_bars) < (n_bars - 2)
    bull_1bar = np.zeros(n_bars, dtype=bool)
    bull_1bar[valid_1bar] = next_close[valid_1bar] > next_open[valid_1bar]
    baseline_1bar = float(np.mean(bull_1bar[valid_1bar])) if np.any(valid_1bar) else 0.5

    ranked = []
    for cond, mask in atomic_evaluated:
        vm = mask & valid_1bar
        n = int(np.sum(vm))
        if n == 0:
            continue
        p = float(np.mean(bull_1bar[vm]))
        ranked.append((abs(p - baseline_1bar), cond, mask))
    ranked.sort(key=lambda x: x[0], reverse=True)

    # Stratified selection: rank WITHIN each indicator family, then take the top-K
    # from each family, rather than a single global top-N ranking. A global ranking
    # tends to be dominated by whichever family happens to have the largest raw
    # effect sizes (e.g. RSI), starving every other family out of the combination
    # pool entirely -- which silently makes multi-family combos (max_atoms_per_combo
    # > 1) impossible. Stratifying guarantees every family gets a fair shot.
    top_n_for_combine = pipeline_config.get("top_n_atomic_for_combine", 15)

    by_family = {}
    for score, cond, mask in ranked:
        fam = indicator_family(cond.column)
        by_family.setdefault(fam, []).append((score, cond, mask))

    n_families_available = len(by_family)
    per_family_k = max(1, top_n_for_combine // max(1, n_families_available))

    top_pool = []
    for fam, items in by_family.items():
        top_pool.extend([(c, m) for _, c, m in items[:per_family_k]])

    # If stratified selection left room (fewer families than slots), fill remaining
    # slots with the next-best conditions globally, regardless of family.
    remaining_slots = top_n_for_combine - len(top_pool)
    if remaining_slots > 0:
        already = {id(c) for c, _ in top_pool}
        for score, cond, mask in ranked:
            if id(cond) in already:
                continue
            top_pool.append((cond, mask))
            remaining_slots -= 1
            if remaining_slots <= 0:
                break

    logger.info(
        f"  Selected top {len(top_pool)} atomic conditions for combination "
        f"(stratified across {n_families_available} families: "
        f"{sorted(by_family.keys())}, ~{per_family_k} per family)"
    )

    # --- Generate combined (AND) conditions from the top pool only ---
    # max_corr_combine: skip pairs whose raw statistical correlation exceeds this.
    # max_atoms_per_combo: how many atoms per combined condition (2 = pairs, 3 = triples, ...).
    # Every combo is additionally required to use a DIFFERENT indicator family per atom
    # (see indicator_family()/is_diverse_combo()), so e.g. rsi_14 AND rsi_21 is never
    # generated regardless of measured correlation -- only genuinely different indicator
    # classes (RSI, CCI, Stochastic, Momentum, ...) get combined together.
    max_corr_combine = pipeline_config.get("max_corr_combine", 0.85)
    max_atoms_per_combo = pipeline_config.get("max_atoms_per_combo", 2)

    top_conds = [c for c, _ in top_pool]

    n_families = len({indicator_family(c.column) for c in top_conds})
    if max_atoms_per_combo > n_families:
        logger.warning(
            f"  max_atoms_per_combo={max_atoms_per_combo} but only {n_families} distinct "
            f"indicator families are present in the top pool "
            f"({sorted({indicator_family(c.column) for c in top_conds})}). "
            f"Combos larger than {n_families} atoms are impossible (each atom must be "
            f"from a different family) and will simply be skipped. Add more indicator "
            f"families (e.g. set include_ma_conditions: true) or lower max_atoms_per_combo."
        )

    combined_candidates = []
    for k in range(2, max_atoms_per_combo + 1):
        n_before = len(combined_candidates)
        for combo in combinations(top_conds, k):
            if is_diverse_combo(combo, max_corr_combine, gen):
                combined_candidates.append(CombinedCondition(list(combo)))
        logger.info(
            f"  {k}-atom combos: {len(combined_candidates) - n_before} generated "
            f"(from {len(top_conds)} pooled atomic conditions)"
        )

    logger.info(f"  Generated {len(combined_candidates)} combined conditions total")

    candidates = [c for c, _ in atomic_evaluated] + combined_candidates
    logger.info(
        f"✓ Total candidates: {len(candidates)} "
        f"({len(atomic_evaluated)} atomic + {len(combined_candidates)} combined)"
    )

    # PHASE 4: Frequency Pre-Filter
    logger.info("\n[PHASE 4] Frequency Pre-Filter...")
    # Reuse already-computed atomic masks; only combined conditions need evaluating here.
    atomic_mask_lookup = {id(c): m for c, m in atomic_evaluated}

    passing_candidates = []
    for cond in candidates:
        mask = atomic_mask_lookup.get(id(cond))
        if mask is None:
            mask = evaluate_condition(cond)
        if freq_filter.passes_filter(mask):
            passing_candidates.append((cond, mask))

    logger.info(f"✓ Frequency filter: {len(passing_candidates)} / {len(candidates)} passed")

    # PHASE 5 & 6: Forward Profile & Significance
    logger.info("\n[PHASE 5-6] Forward Profile & Significance Testing...")

    max_horizon = pipeline_config.get("max_horizon", 20)
    engine = ForwardProfileEngine(df, max_horizon)
    baseline_prob, baseline_size = engine.get_baseline_profile()

    sig_analyzer = SignificanceAnalyzer(
        alpha=pipeline_config.get("alpha", 0.05),
        fdr_method=pipeline_config.get("fdr_method", "fdr_bh"),
    )

    condition_results = []
    for cond, mask in passing_candidates:
        prob_bull, sample_size, _ = engine.get_profile_for_condition(mask)

        condition_results.append({
            'condition': cond,
            'mask': mask,
            'prob_bull': prob_bull,
            'sample_sizes': sample_size,
            'description': str(cond),
        })

    # Test with FDR correction
    condition_results = sig_analyzer.test_batch_conditions(
        condition_results,
        baseline_prob,
        baseline_size,
    )

    # Filter to significant conditions
    sig_conditions = [
        c for c in condition_results
        if not c.get('rejected', True) and c.get('optimal_horizon') is not None
    ]

    logger.info(f"✓ Significance testing: {len(sig_conditions)} conditions passed")

    # PHASE 7: Robustness Validation
    logger.info("\n[PHASE 7] Robustness Validation...")

    cost_model = CostModel(
        spread_pips=pipeline_config.get("spread_pips", 2.0),
        slippage_pips=pipeline_config.get("slippage_pips", 1.0),
        pip_value=pipeline_config.get("pip_value", 0.0001),
    )

    wf_validator = WalkForwardValidator(
        df,
        train_bars=pipeline_config.get("wf_train_bars", 5000),
        test_bars=pipeline_config.get("wf_test_bars", 1000),
        step_bars=pipeline_config.get("wf_step_bars", 500),
    )

    regime_classifier = RegimeClassifier(
        df,
        adx_trending=pipeline_config.get("adx_trending_threshold", 25),
        atr_percentile_low=pipeline_config.get("atr_percentile_low", 25),
        atr_percentile_high=pipeline_config.get("atr_percentile_high", 75),
    )

    validated_edges = []
    for cond_res in sig_conditions:
        edge_id = f"{symbol}_{timeframe}_{len(validated_edges)+1}"

        cond = cond_res['condition']
        mask = cond_res['mask']
        optimal_h = cond_res['optimal_horizon']

        # Walk-forward
        wf_result = validate_condition_walk_forward(
            df, mask, cond_res['prob_bull'], engine, wf_validator
        )

        # Regime stress
        regime_result = stress_test_condition_by_regime(mask, engine, regime_classifier)

        # Parameter sensitivity: sensitivity_test_condition() only supports single
        # AtomicCondition objects (it reads condition.column directly), not
        # CombinedCondition. Skip combined conditions entirely rather than crashing;
        # for atomic conditions, still skip non-numeric thresholds (e.g. MA vs 'close'),
        # which have nothing to shift by +/-15%.
        if isinstance(cond, CombinedCondition):
            logger.debug(
                f"Skipping parameter sensitivity for '{cond}': "
                f"combined conditions are not supported by sensitivity_test_condition"
            )
            param_result = {'sensitivity_score': np.nan}
        elif isinstance(cond.threshold, str):
            logger.debug(
                f"Skipping parameter sensitivity for '{cond}': "
                f"non-numeric threshold (column-to-column comparison)"
            )
            param_result = {'sensitivity_score': np.nan}
        else:
            try:
                param_result = sensitivity_test_condition(
                    cond,
                    df,
                    engine,
                    shift_pct=pipeline_config.get("param_shift_pct", 15),
                )
            except Exception as e:
                logger.warning(f"Parameter sensitivity failed: {e}")
                param_result = {'sensitivity_score': np.nan}

        # Cost model
        cost_result = cost_model.apply_costs_to_forward_profile(
            mask, df, engine, optimal_h
        )

        robustness_info = {
            'walk_forward': wf_result,
            'regime_stress': regime_result,
            'parameter_sensitivity': param_result,
            'cost_model': cost_result,
        }

        sig_df = cond_res['significance_results']
        freq_info = {
            'n_occurrence': int(np.sum(mask)),
            'freq_per_year': len(np.where(mask)[0]) / ((df.index[-1] - df.index[0]).days / 365.25),
            'date_start': str(df.index[0]),
            'date_end': str(df.index[-1]),
        }

        validated_edges.append({
            'edge_id': edge_id,
            'condition': cond,
            'sig_results': sig_df,
            'freq_info': freq_info,
            'baseline_prob': float(baseline_prob[optimal_h - 1]) if optimal_h > 0 else 0.5,
            'robustness': robustness_info,
            'mask': mask,
        })

    logger.info(f"✓ Robustness validation: {len(validated_edges)} edges validated")

    # Holdout test (final validation)
    logger.info("\n[PHASE 7b] Holdout Set Testing...")
    holdout_pct = pipeline_config.get("holdout_pct", 0.15)
    holdout_start = int(len(df) * (1 - holdout_pct))

    for edge in validated_edges:
        holdout_mask = edge['mask'][holdout_start:].copy()
        holdout_mask[len(holdout_mask) - max_horizon:] = False

        holdout_trigger = np.where(holdout_mask)[0]
        holdout_result = {
            'n_samples': len(holdout_trigger),
            'prob_bull': np.nan,
        }

        if len(holdout_trigger) > 0:
            holdout_df_indices = holdout_trigger + holdout_start
            bull_count = np.sum(
                engine.forward_matrix[holdout_df_indices, edge['sig_results'].iloc[0]['horizon'] - 1]
            )
            holdout_result['prob_bull'] = bull_count / len(holdout_trigger)

        edge['holdout'] = holdout_result

    # PHASE 8: Report Generation
    logger.info("\n[PHASE 8] Report Generation...")

    edge_reports = []
    for edge in validated_edges:
        # Generate MQL5 stub
        mql5_stub = f"// Condition: {edge['condition']}\n// Optimal Horizon: {edge['sig_results'].iloc[0]['horizon']}"

        report = EdgeReportGenerator.generate_edge_report(
            edge_id=edge['edge_id'],
            hypothesis=f"Price rally after {str(edge['condition'])}",
            condition_str=str(edge['condition']),
            frequency_info=edge['freq_info'],
            sig_results_df=edge['sig_results'],
            baseline_prob=edge['baseline_prob'],
            optimal_horizon=int(edge['sig_results'].iloc[0]['horizon']),
            robustness_info=edge['robustness'],
            validated_period="walk-forward validated",
            holdout_result=edge['holdout'],
            mql5_code=mql5_stub,
        )

        edge_reports.append(report)

    logger.info(f"✓ Generated {len(edge_reports)} edge reports")

    # Save individual reports
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(exist_ok=True)

    for report in edge_reports:
        report_path = reports_dir / f"{report.edge_id}.yaml"
        report.save_yaml(str(report_path))

    # Save summary Markdown
    md_path = output_dir / "EDGES_SUMMARY.md"
    generate_markdown_report(edge_reports, md_path)
    logger.info(f"✓ Summary Markdown: {md_path}")

    # PHASE 9: MQL5 Code Generation
    logger.info("\n[PHASE 9] MQL5 Code Generation...")

    ea_dir = output_dir / "generated_ea"
    ea_dir.mkdir(exist_ok=True)

    for report in edge_reports:
        try:
            MQL5CodeGenerator.save_ea_file(report, ea_dir)
        except Exception as e:
            logger.warning(f"Failed to generate MQL5 for {report.edge_id}: {e}")

    logger.info(f"✓ Generated {len(edge_reports)} .mq5 EA files")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("EDGE RESEARCH PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total edges discovered: {len(edge_reports)}")
    logger.info(f"Output directory: {output_dir.resolve()}")
    logger.info(f"  - Reports: {reports_dir}")
    logger.info(f"  - EAs: {ea_dir}")
    logger.info(f"  - Summary: {md_path}")
    logger.info("=" * 80)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="edge_research: Systematic market-edge discovery pipeline"
    )
    parser.add_argument(
        "csv_path",
        type=str,
        help="Path to MQL5-exported CSV file",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="EURUSD",
        help="Symbol (default: EURUSD)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="H1",
        help="Timeframe (default: H1)",
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default="./config",
        help="Config directory (default: ./config)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--max-conditions",
        type=int,
        default=None,
        help="Max candidate atomic conditions to test (for testing)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    run_pipeline(
        csv_path=args.csv_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        config_dir=args.config_dir,
        output_dir=args.output_dir,
        max_conditions=args.max_conditions,
    )


if __name__ == "__main__":
    main()