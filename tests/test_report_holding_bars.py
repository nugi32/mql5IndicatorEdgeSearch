"""Tests that edge reports surface holding_bars (Phase 7c) distinctly from
optimal_horizon (Phase 5-6), and that the full per-horizon scan table is
auditable in the markdown output."""

import pandas as pd
import pytest

from edge_research.reporting.report_generator import EdgeReportGenerator, generate_markdown_report, generate_summary_table


@pytest.fixture
def sig_results_df():
    return pd.DataFrame([{
        "horizon": 1, "prob_bull": 0.55, "sample_size": 100, "p_value": 0.01,
        "p_adj": 0.02, "significant": True, "ci_lower": 0.51, "ci_upper": 0.59,
        "effect_size": 0.05,
    }])


@pytest.fixture
def sample_report(sig_results_df):
    return EdgeReportGenerator.generate_edge_report(
        edge_id="TEST_EDGE_001",
        hypothesis="Price rally after RSI oversold reversal",
        condition_str="rsi_14 < 30",
        frequency_info={"n_occurrence": 100, "freq_per_year": 50.0, "date_start": "2020-01-01", "date_end": "2021-01-01"},
        sig_results_df=sig_results_df,
        baseline_prob=0.5,
        optimal_horizon=1,  # Phase 5-6 significance horizon
        robustness_info={
            "walk_forward": {"edge_direction_consistent": True, "edge_magnitude_std": 0.01},
            "cost_model": {"net_expectancy_pips": 1.5, "expectancy_r": 0.1},
            "holding_bars": {
                "holding_bars": 5,
                "holding_bars_stable": True,
                "n_windows_evaluated": 4,
                "n_windows_positive": 4,
                "min_stable_windows_required": 2,
                "scan_table": [
                    {"horizon": 1, "n_trades": 100, "mean_r": 0.05, "std_r": 0.5, "score": 1.0},
                    {"horizon": 5, "n_trades": 100, "mean_r": 0.20, "std_r": 0.9, "score": 2.2},
                    {"horizon": 10, "n_trades": 95, "mean_r": 0.15, "std_r": 1.4, "score": 1.05},
                ],
            },
        },
        validated_period="walk-forward validated",
        holdout_result={},
        mql5_code="// stub",
        metadata={
            "direction": "long",
            # holding_bars (Phase 7c) is DELIBERATELY different from
            # optimal_horizon (Phase 5-6, =1 above) in this fixture, to
            # make sure the report never conflates the two.
            "optimal_holding_bars": 5,
            "holding_bars_stable": True,
        },
    )


def test_summary_table_has_distinct_horizon_and_holding_bars_columns(sample_report):
    df = generate_summary_table([sample_report])
    assert "horizon" in df.columns
    assert "holding_bars" in df.columns
    assert "holding_bars_stable" in df.columns
    row = df.iloc[0]
    assert row["horizon"] == 1        # Phase 5-6
    assert row["holding_bars"] == 5   # Phase 7c -- must NOT equal 'horizon' here
    assert row["holding_bars_stable"] == True


def test_markdown_report_shows_holding_period_section_with_scan_table(sample_report):
    md = generate_markdown_report([sample_report])

    assert "Holding Period (Phase 7c" in md
    assert "Selected holding_bars: 5" in md
    assert "Stable across walk-forward: True" in md
    # Full scan table must be present and auditable, not just the winner.
    assert "| horizon | n_trades | mean_r | std_r | score |" in md
    assert "| 1 |" in md and "| 5 |" in md and "| 10 |" in md
    assert "selected" in md  # marker on the winning row


def test_markdown_report_handles_missing_holding_bars_gracefully():
    """Older reports without the holding_bars field must not crash rendering."""
    sig_df = pd.DataFrame([{
        "horizon": 3, "prob_bull": 0.55, "sample_size": 100, "p_value": 0.01,
        "p_adj": 0.02, "significant": True, "ci_lower": 0.51, "ci_upper": 0.59,
        "effect_size": 0.05,
    }])
    report = EdgeReportGenerator.generate_edge_report(
        edge_id="OLD_EDGE",
        hypothesis="x",
        condition_str="x",
        frequency_info={"n_occurrence": 10, "freq_per_year": 5.0, "date_start": "2020-01-01", "date_end": "2021-01-01"},
        sig_results_df=sig_df,
        baseline_prob=0.5,
        optimal_horizon=3,
        robustness_info={},  # no holding_bars key at all
        validated_period="x",
        holdout_result={},
        mql5_code="// stub",
    )
    md = generate_markdown_report([report])
    assert "Selected holding_bars: None" in md
