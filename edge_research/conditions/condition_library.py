"""
Phase 3: Condition Layer

Define atomic and combined conditions, support evaluation against data,
and generate candidate conditions programmatically.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generator, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Operator(str, Enum):
    """Comparison operators for conditions."""
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    EQ = "=="
    NEQ = "!="


@dataclass
class AtomicCondition:
    """
    Single comparison condition.

    Attributes
    ----------
    column : str
        Indicator column name (e.g., 'rsi_14').
    operator : Operator
        Comparison operator.
    threshold : float | str
        Threshold value (float) or another column name (str).
    """
    column: str
    operator: Operator
    threshold: float | str

    def __repr__(self) -> str:
        return f"{self.column} {self.operator.value} {self.threshold}"


@dataclass
class CombinedCondition:
    """
    AND combination of atomic conditions (typically 2-3).

    Attributes
    ----------
    atoms : List[AtomicCondition]
        List of atomic conditions.
    """
    atoms: List[AtomicCondition]

    def __repr__(self) -> str:
        return " AND ".join(repr(a) for a in self.atoms)


class ConditionEvaluator:
    """Evaluates atomic and combined conditions against data."""

    def __init__(self, df: pd.DataFrame):
        """
        Initialize evaluator with data.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with datetime index and indicator columns.
        """
        self.df = df

    def evaluate_atomic(self, condition: AtomicCondition) -> np.ndarray:
        """
        Evaluate an atomic condition over all bars.

        Parameters
        ----------
        condition : AtomicCondition
            The condition to evaluate.

        Returns
        -------
        np.ndarray
            Boolean mask of shape (len(df),), True where condition is met.

        Raises
        ------
        KeyError
            If column not found in dataframe.
        ValueError
            If operator not recognized.

        Notes
        -----
        - Handles lookahead-free evaluation: result[i] depends only on data[i] and earlier.
        - For crosses_above/crosses_below, requires shifts and may produce NaN at boundaries.
        """
        if condition.column not in self.df.columns:
            raise KeyError(f"Column '{condition.column}' not found in dataframe")
        
        col = self.df[condition.column].values
        
        if isinstance(condition.threshold, str):
            # Column-to-column comparison
            if condition.threshold not in self.df.columns:
                raise KeyError(f"Threshold column '{condition.threshold}' not found")
            threshold_vals = self.df[condition.threshold].values
        else:
            # Fixed threshold
            threshold_vals = condition.threshold
        
        # Evaluate based on operator
        if condition.operator == Operator.LT:
            if isinstance(condition.threshold, str):
                mask = col <= threshold_vals
            else:
                mask = col < threshold_vals
        elif condition.operator == Operator.GT:
            if isinstance(condition.threshold, str):
                mask = col >= threshold_vals
            else:
                mask = col > threshold_vals
        elif condition.operator == Operator.LTE:
            mask = col <= threshold_vals
        elif condition.operator == Operator.GTE:
            mask = col >= threshold_vals
        elif condition.operator == Operator.EQ:
            mask = col == threshold_vals
        elif condition.operator == Operator.NEQ:
            mask = col != threshold_vals
        elif condition.operator == Operator.CROSSES_ABOVE:
            # True if col[i] > threshold[i] and col[i-1] <= threshold[i-1]
            if isinstance(condition.threshold, str):
                threshold_prev = np.roll(threshold_vals, 1)
            else:
                threshold_prev = threshold_vals
            
            col_prev = np.roll(col, 1)
            mask = (col > threshold_vals) & (col_prev <= threshold_prev)
            mask[0] = False  # First bar has no previous
        elif condition.operator == Operator.CROSSES_BELOW:
            # True if col[i] < threshold[i] and col[i-1] >= threshold[i-1]
            if isinstance(condition.threshold, str):
                threshold_prev = np.roll(threshold_vals, 1)
            else:
                threshold_prev = threshold_vals
            
            col_prev = np.roll(col, 1)
            mask = (col < threshold_vals) & (col_prev >= threshold_prev)
            mask[0] = False  # First bar has no previous
        else:
            raise ValueError(f"Unknown operator: {condition.operator}")
        
        return mask.astype(bool)

    def evaluate_combined(self, condition: CombinedCondition) -> np.ndarray:
        """
        Evaluate a combined condition (AND of atoms).

        Parameters
        ----------
        condition : CombinedCondition
            Combined condition.

        Returns
        -------
        np.ndarray
            Boolean mask, True where all atoms are True.
        """
        if not condition.atoms:
            raise ValueError("CombinedCondition must have at least one atom")
        
        mask = self.evaluate_atomic(condition.atoms[0])
        
        for atom in condition.atoms[1:]:
            mask = mask & self.evaluate_atomic(atom)
        
        return mask


class ConditionGenerator:
    """Generates candidate conditions programmatically."""

    def __init__(self, df: pd.DataFrame, config: dict):
        """
        Initialize generator.

        Parameters
        ----------
        df : pd.DataFrame
            Data to generate conditions for.
        config : dict
            Configuration dict with threshold keys (e.g., 'rsi_thresholds').
        """
        self.df = df
        self.config = config or {}
        self.evaluator = ConditionEvaluator(df)

    def generate_atomic_conditions(self) -> Generator[AtomicCondition, None, None]:
        """
        Generate all reasonable atomic conditions based on config thresholds.

        Yields
        ------
        AtomicCondition
            Atomic conditions one at a time (lazy generation to control memory).

        Notes
        -----
        Thresholds are taken from config keys like 'rsi_thresholds', 'cci_thresholds', etc.
        """
        # Extract threshold config
        rsi_thresholds = self.config.get("rsi_thresholds", [30, 70])
        cci_thresholds = self.config.get("cci_thresholds", [-100, 100])
        mom_thresholds = self.config.get("mom_thresholds", [0])
        stoch_thresholds = self.config.get("stoch_thresholds", [20, 80])
        
        # RSI conditions
        for col in self.df.columns:
            if col.startswith("rsi_"):
                for thresh in rsi_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
                    yield AtomicCondition(col, Operator.GT, float(thresh))
        
        # CCI conditions
        for col in self.df.columns:
            if col.startswith("cci_"):
                for thresh in cci_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
                    yield AtomicCondition(col, Operator.GT, float(thresh))
        
        # Momentum conditions
        for col in self.df.columns:
            if col.startswith("mom_"):
                for thresh in mom_thresholds:
                    yield AtomicCondition(col, Operator.GT, float(thresh))
        
        # Stochastic conditions
        for col in self.df.columns:
            if col.startswith("stoch_") and "_k" in col:
                for thresh in stoch_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
                    yield AtomicCondition(col, Operator.GT, float(thresh))

    def generate_ma_conditions(self) -> Generator[AtomicCondition, None, None]:
        """Generate MA crossover and level conditions."""
        # MA levels
        for col in self.df.columns:
            if col.startswith("ma_"):
                # MA above/below recent price
                yield AtomicCondition(col, Operator.GT, "close")
                yield AtomicCondition(col, Operator.LT, "close")

    def get_column_correlation(self, col1: str, col2: str) -> float:
        """
        Compute correlation between two columns.

        Parameters
        ----------
        col1, col2 : str
            Column names.

        Returns
        -------
        float
            Pearson correlation coefficient in [-1, 1].
        """
        if col1 not in self.df.columns or col2 not in self.df.columns:
            return 0.0
        
        # Drop NaN for correlation
        valid = self.df[[col1, col2]].dropna()
        if len(valid) < 2:
            return 0.0
        
        return valid[col1].corr(valid[col2])

    def are_redundant(self, col1: str, col2: str, corr_threshold: float = 0.85) -> bool:
        """
        Check if two columns are highly correlated (likely redundant signals).

        Parameters
        ----------
        col1, col2 : str
            Column names.
        corr_threshold : float
            Correlation threshold above which to consider redundant.

        Returns
        -------
        bool
            True if correlation exceeds threshold in absolute value.
        """
        corr = abs(self.get_column_correlation(col1, col2))
        return corr > corr_threshold

    def generate_combined_conditions(
        self,
        max_atoms: int = 2,
        max_corr: float = 0.85,
    ) -> Generator[CombinedCondition, None, None]:
        """
        Generate combined (AND) conditions from atomic ones.

        Parameters
        ----------
        max_atoms : int
            Maximum atoms per combined condition (typically 2-3).
        max_corr : float
            Skip combinations of highly correlated indicator pairs.

        Yields
        ------
        CombinedCondition
            Combined conditions.

        Notes
        -----
        This is a more expensive generator due to pairwise combinations.
        Consider limiting the pool of atomic conditions first.
        """
        atomic_list = list(self.generate_atomic_conditions())
        
        for i, atom1 in enumerate(atomic_list):
            for atom2 in atomic_list[i+1:]:
                # Skip if indicators are correlated
                if self.are_redundant(atom1.column, atom2.column, max_corr):
                    continue
                
                yield CombinedCondition([atom1, atom2])
                
                # Optionally: 3-way combinations (be careful with memory)
                if max_atoms >= 3:
                    for j, atom3 in enumerate(atomic_list):
                        if j <= i or j <= atomic_list.index(atom2):
                            continue
                        if self.are_redundant(atom1.column, atom3.column, max_corr):
                            continue
                        if self.are_redundant(atom2.column, atom3.column, max_corr):
                            continue
                        
                        yield CombinedCondition([atom1, atom2, atom3])
