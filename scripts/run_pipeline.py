"""
Phase 1-9 Pipeline Orchestration

End-to-end edge discovery pipeline with CLI interface.
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from edge_research.conditions.condition_library import (
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
