"""
Phase 8: Report Generation

Generate edge reports and summary tables.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

from edge_research.reporting.edge_report_schema import (
    AtomicConditionReport,
    EdgeReport,
    FrequencyReport,
    RobustnessReport,
    SignificanceReport,
)

logger = logging.getLogger(__name__)


class EdgeReportGenerator:
    """Generate edge reports from pipeline results."""

    @staticmethod
    def generate_edge_report(
        edge_id: str,
        hypothesis: str,
        condition_str: str,
        frequency_info: Dict,
        sig_results_df: pd.DataFrame,
        baseline_prob: float,
        optimal_horizon: int,
        robustness_info: Dict,
        validated_period: str,
        holdout_result: Dict,
        mql5_code: str,
        metadata: Dict = None,
    ) -> EdgeReport:
        """
        Generate a complete edge report.

        Parameters
        ----------
        edge_id : str
            Unique edge identifier.
        hypothesis : str
            Human-readable hypothesis.
        condition_str : str
            Condition description.
        frequency_info : Dict
            From FrequencyFilter.analyze_condition_frequency().
        sig_results_df : pd.DataFrame
            From SignificanceAnalyzer.test_condition_horizons().
        baseline_prob : float
            Baseline bull probability at optimal horizon.
        optimal_horizon : int
            Selected horizon.
        robustness_info : Dict
            Robustness validation results.
        validated_period : str
            Description of validation period.
        holdout_result : Dict
            Results on final holdout set.
        mql5_code : str
            Generated MQL5 code snippet.
        metadata : Dict, optional
            Free-form extras consumed downstream by MQL5CodeGenerator --
            in particular 'direction' ('long'/'short') and
            'optimal_holding_bars' (the selected fixed-bar exit horizon),
            which together determine the generated EA's entry side and
            EXIT_BARS. Defaults to {} if omitted.

        Returns
        -------
        EdgeReport
            Complete report object.
        """
        # Significance results
        sig_list = []
        for _, row in sig_results_df.iterrows():
            sig_list.append(
                SignificanceReport(
                    horizon=int(row['horizon']),
                    prob_bull=float(row['prob_bull']),
                    sample_size=int(row['sample_size']),
                    p_value=float(row['p_value']) if pd.notna(row['p_value']) else None,
                    p_adjusted=float(row['p_adj']) if pd.notna(row['p_adj']) else None,
                    significant=bool(row['significant']) if pd.notna(row['significant']) else False,
                    ci_lower=float(row['ci_lower']),
                    ci_upper=float(row['ci_upper']),
                    effect_size=float(row['effect_size']),
                )
            )
        
        # Frequency info
        freq_report = FrequencyReport(
            n_occurrence=int(frequency_info.get('n_occurrence', 0)),
            freq_per_year=float(frequency_info.get('freq_per_year', 0)),
            date_range_start=str(frequency_info.get('date_start', 'unknown')),
            date_range_end=str(frequency_info.get('date_end', 'unknown')),
        )
        
        # Robustness info
        robustness = RobustnessReport(
            walk_forward=robustness_info.get('walk_forward', {}),
            regime_stress=robustness_info.get('regime_stress', {}),
            parameter_sensitivity=robustness_info.get('parameter_sensitivity', {}),
            cost_model=robustness_info.get('cost_model', {}),
            holding_bars=robustness_info.get('holding_bars', {}),
        )
        
        report = EdgeReport(
            edge_id=edge_id,
            hypothesis=hypothesis,
            entry_condition=condition_str,
            frequency=freq_report,
            optimal_horizon=int(optimal_horizon),
            significance_results=sig_list,
            baseline_prob=float(baseline_prob),
            robustness=robustness,
            validated_period=validated_period,
            holdout_result=holdout_result,
            mql5_mapping=mql5_code,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )
        
        return report


def generate_summary_table(
    edge_reports: List[EdgeReport],
) -> pd.DataFrame:
    """
    Generate summary table across all edges.

    Parameters
    ----------
    edge_reports : List[EdgeReport]
        List of edge reports.

    Returns
    -------
    pd.DataFrame
        Summary table with columns:
        [edge_id, hypothesis, horizon, holding_bars, holding_bars_stable,
         prob_bull, effect_size, frequency_per_year, robust_walk_forward,
         p_adjusted]

        NOTE: 'horizon' is the Phase 5-6 significance-testing horizon
        (report.optimal_horizon) -- it answers "at what forward horizon is
        this condition's directional probability statistically
        significant?". It is NOT the EA's actual exit rule. 'holding_bars'
        is the Phase 7c value (report.metadata['optimal_holding_bars']) --
        the number of bars the generated EA actually holds the position
        for (EXIT_BARS). These are two different questions about two
        different phases and can legitimately have different answers for
        the same condition -- see generate_markdown_report's per-edge
        "Holding Period" section for the full per-horizon evidence table
        behind each holding_bars value.
    """
    rows = []
    
    for report in edge_reports:
        sig_at_horizon = [
            s for s in report.significance_results
            if s.horizon == report.optimal_horizon
        ]
        
        if sig_at_horizon:
            sig = sig_at_horizon[0]
            prob_bull = sig.prob_bull
            effect_size = sig.effect_size
            p_adj = sig.p_adjusted
        else:
            prob_bull = np.nan
            effect_size = np.nan
            p_adj = np.nan
        
        robust_wf = report.robustness.walk_forward.get(
            'edge_direction_consistent', False
        )
        metadata = report.metadata or {}
        
        rows.append({
            'edge_id': report.edge_id,
            'hypothesis': report.hypothesis,
            'horizon': report.optimal_horizon,
            'holding_bars': metadata.get('optimal_holding_bars'),
            'holding_bars_stable': metadata.get('holding_bars_stable'),
            'prob_bull': prob_bull,
            'effect_size': effect_size,
            'frequency_per_year': report.frequency.freq_per_year,
            'robust_walk_forward': robust_wf,
            'p_adjusted': p_adj,
        })
    
    df_summary = pd.DataFrame(rows)
    
    # Sort by effect size descending
    df_summary = df_summary.sort_values('effect_size', ascending=False, na_position='last')
    
    return df_summary


def generate_markdown_report(
    edge_reports: List[EdgeReport],
    output_path: str | Path = None,
) -> str:
    """
    Generate human-readable Markdown report.

    Parameters
    ----------
    edge_reports : List[EdgeReport]
        List of edge reports.
    output_path : str | Path, optional
        Path to save Markdown file.

    Returns
    -------
    str
        Markdown content.
    """
    lines = [
        "# Edge Research Report\n",
        f"Generated: {datetime.utcnow().isoformat()}\n",
        f"Total edges: {len(edge_reports)}\n",
        "\n",
    ]
    
    if len(edge_reports) == 0:
        lines.append("No edges found passing validation criteria.\n")
    else:
        # Summary table
        summary_df = generate_summary_table(edge_reports)
        lines.append("## Summary Table\n")
        lines.append(summary_df.to_markdown(index=False))
        lines.append("\n\n")
        
        # Individual reports
        lines.append("## Detailed Edge Reports\n")
        
        for i, report in enumerate(edge_reports, 1):
            metadata = report.metadata or {}
            lines.append(f"### {i}. {report.edge_id}\n")
            lines.append(f"**Hypothesis:** {report.hypothesis}\n")
            lines.append(f"**Entry Condition:** {report.entry_condition}\n")
            lines.append(f"**Optimal Horizon:** {report.optimal_horizon} bars\n")
            lines.append(f"**Frequency:** {report.frequency.freq_per_year:.1f} per year\n")
            lines.append(f"**Baseline Prob (Bull):** {report.baseline_prob:.2%}\n")
            
            # Significance at optimal horizon
            sig_at_h = [
                s for s in report.significance_results
                if s.horizon == report.optimal_horizon
            ]
            if sig_at_h:
                sig = sig_at_h[0]
                lines.append(f"\n**At Optimal Horizon:**\n")
                lines.append(f"- Prob (Bull): {sig.prob_bull:.2%}\n")
                lines.append(f"- Effect Size: {sig.effect_size:.4f}\n")
                lines.append(f"- P-value (adj): {sig.p_adjusted:.4e}\n")
                lines.append(f"- CI: [{sig.ci_lower:.2%}, {sig.ci_upper:.2%}]\n")
            
            # Robustness
            lines.append(f"\n**Robustness:**\n")
            wf_result = report.robustness.walk_forward
            lines.append(f"- Walk-Forward Consistent: {wf_result.get('edge_direction_consistent', False)}\n")
            lines.append(f"- Magnitude Std: {wf_result.get('edge_magnitude_std', np.nan):.4f}\n")
            
            cost = report.robustness.cost_model
            lines.append(f"- Net Expectancy (pips): {cost.get('net_expectancy_pips', np.nan):.2f}\n")
            lines.append(f"- Expectancy (R): {cost.get('expectancy_r', np.nan):.2f}\n")

            # Holding period (Phase 7c) -- the EA's actual exit rule
            # (EXIT_BARS), selected per-condition by scanning every
            # candidate horizon and scoring it for consistency
            # (mean_r / (std_r / sqrt(n)), NOT raw mean profit -- see
            # edge_research/simulation/trade_simulator.py). This is a
            # DIFFERENT number from "Optimal Horizon" above (that one
            # answers a Phase 5-6 significance-testing question, this one
            # answers "how long does the EA actually hold the trade").
            # The full table is printed so this number is auditable from
            # the report alone rather than something to take on faith.
            hb_info = metadata.get('optimal_holding_bars')
            hb_stable = metadata.get('holding_bars_stable')
            hb_detail = report.robustness.holding_bars or {}
            lines.append(f"\n**Holding Period (Phase 7c -- EA's EXIT_BARS):**\n")
            lines.append(f"- Selected holding_bars: {hb_info}\n")
            lines.append(f"- Stable across walk-forward: {hb_stable}\n")
            if hb_detail.get('n_windows_evaluated') is not None:
                lines.append(
                    f"- Walk-forward check: positive mean R in "
                    f"{hb_detail.get('n_windows_positive')}/"
                    f"{hb_detail.get('n_windows_evaluated')} windows "
                    f"(required >= {hb_detail.get('min_stable_windows_required')})\n"
                )
            scan_table = hb_detail.get('scan_table')
            if scan_table:
                lines.append("\n| horizon | n_trades | mean_r | std_r | score |\n")
                lines.append("|---:|---:|---:|---:|---:|\n")
                for row in scan_table:
                    mean_r = row.get('mean_r')
                    std_r = row.get('std_r')
                    score = row.get('score')
                    mean_r_s = f"{mean_r:.4f}" if mean_r == mean_r else "nan"  # nan != nan
                    std_r_s = f"{std_r:.4f}" if std_r == std_r else "nan"
                    score_s = f"{score:.3f}" if score == score else "nan"
                    marker = " **<-- selected**" if row.get('horizon') == hb_info else ""
                    lines.append(
                        f"| {row.get('horizon')} | {row.get('n_trades')} | "
                        f"{mean_r_s} | {std_r_s} | {score_s}{marker} |\n"
                    )
            
            lines.append("\n")
    
    content = "".join(lines)
    
    if output_path:
        Path(output_path).write_text(content)
        logger.info(f"Markdown report saved to {output_path}")
    
    return content
