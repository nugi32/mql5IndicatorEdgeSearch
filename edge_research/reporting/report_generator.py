"""
Phase 8: Report Generation

Generate edge reports and summary tables.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

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
    ) -> EdgeReport:
        """
        Generate a complete edge report.
