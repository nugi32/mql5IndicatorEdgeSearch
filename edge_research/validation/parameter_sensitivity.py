"""
Parameter sensitivity analysis: vary thresholds and periods.
"""

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    ConditionEvaluator,
    Operator,
)

logger = logging.getLogger(__name__)


def get_numeric_param_from_condition(condition: AtomicCondition) -> tuple | None:
    """
    Extract numeric threshold or period from condition string.
