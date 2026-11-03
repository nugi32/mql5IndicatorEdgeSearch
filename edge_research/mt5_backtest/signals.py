"""Turn a condition string from the ranker/reports into a boolean signal mask."""

from __future__ import annotations

import numpy as np
import pandas as pd

from edge_research.conditions.condition_library import (
    AtomicCondition,
    CombinedCondition,
    ConditionEvaluator,
    Operator,
)
from edge_research.ranking.ranker import parse_condition


def build_mask(df: pd.DataFrame, condition: str) -> np.ndarray:
    """
    Evaluate e.g. ``"rsi_14 < 25.0 AND mom_10 > -5.0"`` on ``df``.

    ``mask[i]`` is True when the condition is known at the close of bar i; the
    EA acts on it at the open of bar i+1 (the first tick it sees there).
    Raises KeyError when a needed column is missing (for example a ``cal_*``
    column without ``--calendar-csv``).
    """
    atoms = []
    for column, operator, threshold in parse_condition(condition):
        atoms.append(AtomicCondition(column=column, operator=Operator(operator), threshold=threshold))
    return ConditionEvaluator(df).evaluate_combined(CombinedCondition(atoms=atoms))
