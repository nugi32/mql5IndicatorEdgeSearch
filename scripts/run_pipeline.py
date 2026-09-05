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
from edge_research.selection.strategy_gate import GateThresholds, passes_strategy_gate
from edge_research.simulation.trade_simulator import (
    TradeSimConfig,
    infer_direction,
    simulate_condition,
)
from edge_research.validation.cost_model import CostModel, cost_aware_prefilter
from edge_research.validation.parameter_sensitivity import sensitivity_test_condition
from edge_research.validation.permutation_test import rotation_permutation_test
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

    # Determine each condition's trade direction (long/short) NOW, right
    # after significance testing -- not later in Phase 7c as before. BUG
    # FIX: Phase 6b's cost-aware pre-filter (and the Phase 7 loop's cost
    # model call) used to call apply_costs_to_forward_profile() without a
    # direction at all, which silently assumed every condition was a LONG
    # trade. Any condition whose true edge was bearish (forward bull
    # probability significantly BELOW baseline, i.e. correct trade is
    # SHORT) had its P&L computed backwards -- mirrored/negated -- making
    # a real short edge look catastrophically unprofitable. Since Phase 6b
    # drops conditions before they ever reach Phase 7c (where direction
    # used to be inferred), this could reject every bearish edge in a run
    # for a reason that had nothing to do with cost realism. This is
    # exactly what happened on an EURUSD H4 run: 0/335 passed Phase 6b
    # with an expectancy_r distribution that didn't move at all when the
    # cost config was corrected from XAUUSD to EURUSD values -- the
    # dominant effect was the sign bug, not the cost magnitude.
    for cond_res in sig_conditions:
        sig_df = cond_res['significance_results']
        cond_prob_bull_at_h = float(sig_df.iloc[0]['prob_bull'])
        baseline_prob_at_h = float(baseline_prob[cond_res['optimal_horizon'] - 1])
        cond_res['direction'] = infer_direction(cond_prob_bull_at_h, baseline_prob_at_h)

    # Cost model is needed for both the Phase 6b pre-filter below and the
    # Phase 7 robustness loop's per-edge cost estimate, so it's built once
    # here. spread_atr_mult (optional) makes the cost estimate scale with
    # each trigger's own entry-time volatility instead of a single fixed
    # spread across the whole dataset -- see cost_model.py docstring and
    # PROJECT_DIRECTION.md section 8 ("cost sensitivity").
    cost_model = CostModel(
        spread_pips=pipeline_config.get("spread_pips", 2.0),
        slippage_pips=pipeline_config.get("slippage_pips", 1.0),
        pip_value=pipeline_config.get("pip_value", 0.0001),
        spread_atr_mult=pipeline_config.get("spread_atr_mult", None),
        atr_column=pipeline_config.get("sim_atr_column", "atr_14"),
    )

    # PHASE 6b: Cost-Aware Pre-Filter
    # See PROJECT_DIRECTION.md section 8 ("cost sensitivity sweep" /
    # cost-aware filtering). Cheaply estimates each significant condition's
    # cost-adjusted expectancy_r using the same horizon-based cost model as
    # Phase 5-6 (no SL/TP, no intrabar path -- see cost_aware_prefilter's
    # docstring), and drops candidates that don't even clear this lenient
    # bar BEFORE they pay for the much more expensive Phase 7 robustness
    # stack (walk-forward, regime stress, parameter sensitivity, Phase 7c
    # trade simulation, Phase 7d permutation test). Disabled by default
    # (min_precheck_expectancy_r absent -> filter still runs but with a
    # 0.0 margin, i.e. "must not already be underwater on the cheap
    # estimate"); set precheck_enabled: false in pipeline_config.yaml to
    # skip this phase entirely and let every significant condition through
    # to Phase 7 as before.
    logger.info("\n[PHASE 6b] Cost-Aware Pre-Filter...")
    precheck_enabled = pipeline_config.get("precheck_enabled", True)
    min_precheck_expectancy_r = pipeline_config.get("min_precheck_expectancy_r", 0.0)

    if precheck_enabled:
        prefiltered_conditions = []
        n_dropped = 0
        all_expectancy_r = []
        for cond_res in sig_conditions:
            cost_result = cost_model.apply_costs_to_forward_profile(
                cond_res['mask'], df, engine, cond_res['optimal_horizon'],
                direction=cond_res['direction'],
            )
            cond_res['precheck_cost_result'] = cost_result
            if np.isfinite(cost_result.get('expectancy_r', np.nan)):
                all_expectancy_r.append(cost_result['expectancy_r'])
            passed, reason = cost_aware_prefilter(cost_result, min_precheck_expectancy_r)
            if passed:
                prefiltered_conditions.append(cond_res)
            else:
                n_dropped += 1
                logger.debug(f"Phase 6b dropped '{cond_res['description']}': {reason}")

        logger.info(
            f"✓ Cost-aware pre-filter: {len(prefiltered_conditions)} / {len(sig_conditions)} "
            f"conditions passed (min_expectancy_r={min_precheck_expectancy_r}), "
            f"{n_dropped} dropped before entering the expensive Phase 7 robustness stack"
        )
        if all_expectancy_r:
            arr = np.array(all_expectancy_r)
            logger.info(
                f"  Cost-adjusted expectancy_r distribution across all {len(arr)} "
                f"significant conditions: min={arr.min():.4f}, "
                f"median={np.median(arr):.4f}, mean={arr.mean():.4f}, max={arr.max():.4f}"
            )
        if len(prefiltered_conditions) == 0 and len(sig_conditions) > 0:
            logger.warning(
                "⚠ Phase 6b dropped EVERY significant condition. This can be a genuine "
                "result (this timeframe's raw edges don't clear realistic transaction "
                "costs at all -- see the expectancy_r distribution above: if the max is "
                "also <= 0, that's the case here), or a config/cost mismatch (e.g. "
                "spread_pips/pip_value/spread_atr_mult not set correctly for this "
                "symbol -- see PROJECT_DIRECTION.md section 10). Check the distribution "
                "logged above before concluding the timeframe itself is unviable. To "
                "inspect Phase 5-6 candidates without the cost filter, rerun with "
                "precheck_enabled: false in pipeline_config.yaml."
            )
        sig_conditions = prefiltered_conditions
    else:
        logger.info("✓ Cost-aware pre-filter disabled (precheck_enabled: false)")

    # PHASE 7: Robustness Validation
    logger.info("\n[PHASE 7] Robustness Validation...")

    wf_train_bars = pipeline_config.get("wf_train_bars", 5000)
    wf_test_bars = pipeline_config.get("wf_test_bars", 1000)
    wf_step_bars = pipeline_config.get("wf_step_bars", 500)

    # Fail fast with a clear message rather than a cryptic TypeError deep
    # inside WalkForwardValidator._generate_windows() if one of these was
    # left as a non-numeric placeholder in pipeline_config.yaml (e.g. a
    # formula comment like "~0.35 * N" that was never filled in with an
    # actual number for this timeframe's bar count).
    for _name, _val in (
        ("wf_train_bars", wf_train_bars),
        ("wf_test_bars", wf_test_bars),
        ("wf_step_bars", wf_step_bars),
    ):
        if not isinstance(_val, (int, float)) or isinstance(_val, bool):
            raise ValueError(
                f"pipeline_config.yaml: '{_name}' must be a number, got "
                f"{_val!r} ({type(_val).__name__}). This is often a leftover "
                f"formula placeholder (e.g. '~0.35 * N') that needs to be "
                f"replaced with an actual integer bar count for this "
                f"timeframe's dataset size (len(df)={len(df)})."
            )
    wf_train_bars = int(wf_train_bars)
    wf_test_bars = int(wf_test_bars)
    wf_step_bars = int(wf_step_bars)

    wf_validator = WalkForwardValidator(
        df,
        train_bars=wf_train_bars,
        test_bars=wf_test_bars,
        step_bars=wf_step_bars,
    )

    # WalkForwardValidator silently produces zero windows if
    # wf_train_bars + wf_test_bars doesn't fit inside len(df) -- which
    # then makes every single condition's 'edge_direction_consistent'
    # default to False (see validate_condition_walk_forward's empty-window
    # branch), which in turn makes the Phase 7e gate's robust_walk_forward
    # check fail for EVERY edge, with no other evidence considered. This
    # is a data-size/config mismatch, not a signal quality problem, and it
    # is easy to miss under the per-condition "No valid windows" spam
    # logged deeper in validate_condition_walk_forward. Fail loudly once,
    # here, with the actual numbers, instead.
    if len(wf_validator.get_windows()) == 0:
        logger.warning(
            f"⚠ Walk-forward validation will produce ZERO windows for this run: "
            f"wf_train_bars ({wf_train_bars}) + wf_test_bars ({wf_test_bars}) = "
            f"{wf_train_bars + wf_test_bars} bars needed per window, but the "
            f"dataset only has {len(df)} bars. Every condition's walk-forward "
            f"result will default to 'not robust', which will make the Phase 7e "
            f"strategy gate reject ALL candidates regardless of their trade "
            f"simulation or permutation test results. Lower wf_train_bars/"
            f"wf_test_bars/wf_step_bars in pipeline_config.yaml to fit this "
            f"timeframe's bar count (e.g. for {len(df)} bars, something like "
            f"wf_train_bars={max(100, len(df) // 3)}, "
            f"wf_test_bars={max(50, len(df) // 15)}, "
            f"wf_step_bars={max(25, len(df) // 30)} would produce multiple "
            f"windows), or set gate_require_walk_forward: false to proceed "
            f"without this check (not recommended for anything beyond a "
            f"smoke test)."
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
            df, mask, cond_res['prob_bull'], engine, wf_validator,
            direction=cond_res['direction'],
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

        # Cost model -- reuse the Phase 6b pre-filter's result when
        # available (same inputs, avoids recomputing) instead of a second
        # full pass over every trigger.
        cost_result = cond_res.get('precheck_cost_result')
        if cost_result is None:
            cost_result = cost_model.apply_costs_to_forward_profile(
                mask, df, engine, optimal_h, direction=cond_res['direction']
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
            'direction': cond_res['direction'],
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

    # PHASE 7c: Realistic Trade Simulation
    # See PROJECT_DIRECTION.md, section 4. Simulates every condition that
    # survived Phase 5-7b with a concrete, EA-realistic ATR-based SL/TP
    # scheme and spread/slippage cost, instead of relying only on the
    # fixed-horizon directional probability from Phase 5-6.
    logger.info("\n[PHASE 7c] Realistic Trade Simulation...")
    sim_sl_atr_mult = pipeline_config.get("sim_sl_atr_mult", 1.5)
    sim_tp_atr_mult = pipeline_config.get("sim_tp_atr_mult", 3.0)
    sim_use_trailing = pipeline_config.get("sim_use_trailing_stop", False)
    sim_trail_atr_mult = pipeline_config.get("sim_trail_atr_mult", 1.5)
    sim_max_holding_bars = pipeline_config.get("sim_max_holding_bars", max_horizon)
    sim_atr_column = pipeline_config.get("sim_atr_column", "atr_14")
    # Variable/volatility-and-session-aware cost model (opt-in, see
    # TradeSimConfig docstring). None/empty -> behaves exactly as before.
    sim_spread_atr_mult = pipeline_config.get("spread_atr_mult", None)
    sim_session_multipliers_cfg = pipeline_config.get("session_spread_multipliers", None)
    sim_session_multipliers = (
        [tuple(row) for row in sim_session_multipliers_cfg]
        if sim_session_multipliers_cfg
        else None
    )
    # Bootstrap CI on expectancy_r (off by default -- adds compute cost).
    sim_bootstrap_n = pipeline_config.get("sim_bootstrap_n", 0)
    sim_bootstrap_ci = pipeline_config.get("sim_bootstrap_ci", 0.95)
    sim_bootstrap_seed = pipeline_config.get("sim_bootstrap_random_state", None)

    for edge in validated_edges:
        optimal_h = int(edge['sig_results'].iloc[0]['horizon'])
        # Reuse the direction already determined right after Phase 5-6
        # (before Phase 6b) rather than recomputing it here -- same inputs,
        # same infer_direction() call, kept as a single source of truth so
        # Phase 6b's filtering decision and Phase 7c's simulation direction
        # can never silently diverge.
        direction = edge['direction']

        sim_config = TradeSimConfig(
            direction=direction,
            atr_column=sim_atr_column,
            sl_atr_mult=sim_sl_atr_mult,
            tp_atr_mult=sim_tp_atr_mult,
            use_trailing_stop=sim_use_trailing,
            trail_atr_mult=sim_trail_atr_mult,
            max_holding_bars=sim_max_holding_bars,
            spread_price_units=pipeline_config.get("spread_pips", 2.0)
            * pipeline_config.get("pip_value", 0.0001),
            slippage_price_units=pipeline_config.get("slippage_pips", 1.0)
            * pipeline_config.get("pip_value", 0.0001),
            spread_atr_mult=sim_spread_atr_mult,
            session_spread_multipliers=sim_session_multipliers,
            bootstrap_n=sim_bootstrap_n,
            bootstrap_ci=sim_bootstrap_ci,
            bootstrap_random_state=sim_bootstrap_seed,
        )

        try:
            sim_result = simulate_condition(df, edge['mask'], sim_config)
        except KeyError as e:
            logger.warning(f"Trade simulation skipped for {edge['edge_id']}: {e}")
            sim_result = simulate_condition(
                df, np.zeros_like(edge['mask']), sim_config
            )  # yields an empty/NaN result via the n_trades==0 path

        edge['trade_sim'] = sim_result
        edge['direction'] = direction

    n_sim_positive = sum(
        1 for e in validated_edges
        if e['trade_sim'].n_trades > 0 and e['trade_sim'].expectancy_r > 0
    )
    logger.info(
        f"✓ Trade simulation complete: {n_sim_positive} / {len(validated_edges)} "
        f"edges have positive simulated expectancy_r"
    )

    # PHASE 7d: Rotation-Based Permutation Test
    # See PROJECT_DIRECTION.md, section 4. A stricter, autocorrelation-aware
    # significance check that complements (not replaces) Phase 6's z-test.
    logger.info("\n[PHASE 7d] Rotation-Based Permutation Test...")
    perm_n = pipeline_config.get("permutation_n", 500)
    perm_alpha = pipeline_config.get("alpha", 0.05)
    perm_seed = pipeline_config.get("permutation_random_state", None)

    for edge in validated_edges:
        optimal_h = int(edge['sig_results'].iloc[0]['horizon'])
        outcome_series = engine.forward_matrix[:, optimal_h - 1]
        perm_result = rotation_permutation_test(
            trigger_mask=edge['mask'],
            outcome_series=outcome_series,
            n_permutations=perm_n,
            alpha=perm_alpha,
            random_state=perm_seed,
        )
        edge['permutation'] = perm_result

    n_perm_sig = sum(1 for e in validated_edges if e['permutation'].get('significant'))
    logger.info(
        f"✓ Permutation testing complete: {n_perm_sig} / {len(validated_edges)} "
        f"edges pass the rotation permutation test"
    )

    # PHASE 7e: Final Strategy Selection Gate
    # See PROJECT_DIRECTION.md, section 4. Combines Phase 6 significance,
    # Phase 7 walk-forward robustness, Phase 7d permutation significance,
    # and Phase 7c simulated expectancy/profit factor into a single
    # pass/fail decision. Only gate-passing edges reach Phase 9 (MQL5
    # code generation).
    #
    # NOTE ON SCHEMA: validate_condition_walk_forward() (Phase 7, existing
    # code in edge_research/validation/walk_forward.py) returns its
    # consistency flag under the key 'edge_direction_consistent', not
    # 'consistent'. report_generator.py already reads it under that name
    # (see EdgeReportGenerator / generate_markdown_report), so we read the
    # same key here rather than guessing at a different one -- reading the
    # wrong key would silently default every edge's robust_walk_forward to
    # False and make the gate impossible to pass.
    logger.info("\n[PHASE 7e] Final Strategy Selection Gate...")
    gate_thresholds = GateThresholds(
        alpha=pipeline_config.get("alpha", 0.05),
        min_sim_trades=pipeline_config.get("gate_min_sim_trades", 30),
        min_profit_factor=pipeline_config.get("gate_min_profit_factor", 1.1),
        require_walk_forward=pipeline_config.get("gate_require_walk_forward", True),
        require_permutation=pipeline_config.get("gate_require_permutation", True),
        require_positive_ci_lower=pipeline_config.get("gate_require_positive_ci_lower", False),
    )

    gate_rows = []
    for edge in validated_edges:
        significant = bool(edge['sig_results'].iloc[0]['significant'])
        wf_info = edge['robustness'].get('walk_forward')
        robust_wf = bool(wf_info.get('edge_direction_consistent', False)) \
            if isinstance(wf_info, dict) else False

        passed, reasons = passes_strategy_gate(
            significant=significant,
            robust_walk_forward=robust_wf,
            permutation_result=edge['permutation'],
            sim_result=edge['trade_sim'],
            thresholds=gate_thresholds,
        )
        edge['gate_passed'] = passed
        edge['gate_reasons'] = reasons

        gate_rows.append({
            "edge_id": edge['edge_id'],
            "condition": str(edge['condition']),
            "direction": edge['direction'],
            "gate_passed": passed,
            "reasons": "; ".join(reasons) if reasons else "",
            "sim_n_trades": edge['trade_sim'].n_trades,
            "sim_expectancy_r": edge['trade_sim'].expectancy_r,
            "sim_expectancy_r_ci_low": edge['trade_sim'].expectancy_r_ci_low,
            "sim_expectancy_r_ci_high": edge['trade_sim'].expectancy_r_ci_high,
            "sim_profit_factor": edge['trade_sim'].profit_factor,
            "sim_win_rate": edge['trade_sim'].win_rate,
            "permutation_p_value": edge['permutation'].get('p_value'),
            "robust_walk_forward": robust_wf,
        })

    n_gate_passed = sum(1 for e in validated_edges if e['gate_passed'])
    logger.info(
        f"✓ Strategy gate: {n_gate_passed} / {len(validated_edges)} edges "
        f"passed ALL criteria and are recommended for EA generation"
    )

    gate_summary_columns = [
        "edge_id", "condition", "direction", "gate_passed", "reasons",
        "sim_n_trades", "sim_expectancy_r", "sim_expectancy_r_ci_low",
        "sim_expectancy_r_ci_high", "sim_profit_factor", "sim_win_rate",
        "permutation_p_value", "robust_walk_forward",
    ]
    gate_summary_df = pd.DataFrame(gate_rows, columns=gate_summary_columns)
    if len(gate_summary_df) > 0:
        gate_summary_df = gate_summary_df.sort_values(
            by=["gate_passed", "sim_expectancy_r"], ascending=[False, False]
        )
    gate_summary_path = output_dir / "STRATEGY_GATE_RESULTS.csv"
    gate_summary_df.to_csv(gate_summary_path, index=False)
    logger.info(f"✓ Gate results written to {gate_summary_path}")

    # PHASE 8: Report Generation
    logger.info("\n[PHASE 8] Report Generation...")

    edge_reports = []
    for edge in validated_edges:
        gate_note = (
            "RECOMMENDED FOR EA GENERATION"
            if edge['gate_passed']
            else f"NOT RECOMMENDED ({'; '.join(edge['gate_reasons'])})"
        )
        sim = edge['trade_sim']
        mql5_stub = (
            f"// Condition: {edge['condition']}\n"
            f"// Optimal Horizon: {edge['sig_results'].iloc[0]['horizon']}\n"
            f"// Direction: {edge['direction']}\n"
            f"// Strategy gate: {gate_note}\n"
            f"// Simulated (Phase 7c): n_trades={sim.n_trades}, "
            f"expectancy_r={sim.expectancy_r:.4f}, "
            f"profit_factor={sim.profit_factor:.2f}\n"
            f"// Permutation test (Phase 7d): p_value={edge['permutation'].get('p_value')}"
        )

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

    logger.info(f"✓ Generated {len(edge_reports)} edge reports (all candidates, gate status included)")

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
    # Only edges that passed the Phase 7e strategy gate are turned into EAs.
    # See PROJECT_DIRECTION.md, section 4 -- reducing the number of
    # surviving edges is the intended outcome of this pipeline, not a bug.
    logger.info("\n[PHASE 9] MQL5 Code Generation (gate-passing edges only)...")

    ea_dir = output_dir / "generated_ea"
    ea_dir.mkdir(exist_ok=True)

    gate_passed_ids = {e['edge_id'] for e in validated_edges if e['gate_passed']}
    n_generated = 0
    for report in edge_reports:
        if report.edge_id not in gate_passed_ids:
            continue
        try:
            MQL5CodeGenerator.save_ea_file(report, ea_dir)
            n_generated += 1
        except Exception as e:
            logger.warning(f"Failed to generate MQL5 for {report.edge_id}: {e}")

    logger.info(
        f"✓ Generated {n_generated} .mq5 EA files "
        f"({len(edge_reports) - n_generated} candidates did not pass the strategy gate "
        f"and were skipped; see {gate_summary_path.name} for reasons)"
    )

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
