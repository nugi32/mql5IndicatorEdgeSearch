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


# Column-name prefixes of the columns that do NOT come from standard MT5 indicators.
# - "volregime_" / "ps_": custom indicators VolRegime_ATR / PriceStructure, exported by
#   dataExporter.mq5 v1.01 (an EA needs iCustom() to reproduce them).
# - "cal_": economic-calendar features built in Python from the MT5 calendar export
#   (the MT5 calendar API does not work in the Strategy Tester, so an EA can only
#   reproduce them live).
CALENDAR_PREFIX = "cal_"
# "news_": the same kind of information, but computed inside MQL5 by dataExporter.mq5 v1.02.
CALENDAR_PREFIXES = ("cal_", "news_")
CUSTOM_INDICATOR_PREFIXES = ("volregime_", "ps_")


def condition_columns(condition) -> set:
    """All column names a condition reads (indicator columns AND column-valued thresholds)."""
    atoms = condition.atoms if isinstance(condition, CombinedCondition) else [condition]
    cols = set()
    for atom in atoms:
        cols.add(atom.column)
        if isinstance(atom.threshold, str):
            cols.add(atom.threshold)
    return cols


def calendar_columns_used(condition) -> list:
    """Sorted cal_* / news_* columns used by a condition (empty list if none)."""
    return sorted(c for c in condition_columns(condition) if c.startswith(CALENDAR_PREFIXES))


def custom_indicator_columns_used(condition) -> list:
    """Sorted volregime_* / ps_* columns used by a condition (empty list if none)."""
    return sorted(
        c for c in condition_columns(condition) if c.startswith(CUSTOM_INDICATOR_PREFIXES)
    )


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
            mask = col < threshold_vals
        elif condition.operator == Operator.GT:
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
            col_prev = np.roll(col, 1)
            if isinstance(condition.threshold, str):
                threshold_prev = np.roll(threshold_vals, 1)
                mask = (col > threshold_vals) & (col_prev <= threshold_prev)
            else:
                mask = (col > threshold_vals) & (col_prev <= threshold_vals)
            mask[0] = False
        elif condition.operator == Operator.CROSSES_BELOW:
            col_prev = np.roll(col, 1)
            if isinstance(condition.threshold, str):
                threshold_prev = np.roll(threshold_vals, 1)
                mask = (col < threshold_vals) & (col_prev >= threshold_prev)
            else:
                mask = (col < threshold_vals) & (col_prev >= threshold_vals)
            mask[0] = False
        else:
            raise ValueError(f"Unknown operator: {condition.operator}")

        if isinstance(condition.threshold, str) and len(mask) > 0:
            mask[0] = True
        
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

        # --- VolRegime_ATR custom indicator (dataExporter.mq5 v1.01) ---
        yield from self._volregime_conditions()

        # --- PriceStructure custom indicator (dataExporter.mq5 v1.01) ---
        yield from self._price_structure_conditions()

        # --- Economic calendar features (present only when a calendar CSV was ingested) ---
        yield from self._calendar_conditions()

        # --- news_* columns written by dataExporter.mq5 v1.02 ---
        yield from self._news_conditions()

    def _volregime_conditions(self) -> Generator[AtomicCondition, None, None]:
        """
        Volatility-regime atoms.

        volregime_atr_pctl : ATR percentile rank (0..100) -> '<' / '>' thresholds
        volregime_atr_ratio: ATR / SMA(ATR), ~1.0          -> '<' / '>' thresholds
        volregime_regime   : 0 low / 1 mid / 2 high vol    -> '==' each listed value
        """
        pctl_thresholds = self.config.get("volregime_pctl_thresholds", [20, 30, 70, 80])
        ratio_thresholds = self.config.get("volregime_ratio_thresholds", [0.8, 1.0, 1.2])
        regime_values = self.config.get("volregime_regime_values", [0, 1, 2])

        if "volregime_atr_pctl" in self.df.columns:
            for thresh in pctl_thresholds:
                yield AtomicCondition("volregime_atr_pctl", Operator.LT, float(thresh))
                yield AtomicCondition("volregime_atr_pctl", Operator.GT, float(thresh))
        if "volregime_atr_ratio" in self.df.columns:
            for thresh in ratio_thresholds:
                yield AtomicCondition("volregime_atr_ratio", Operator.LT, float(thresh))
                yield AtomicCondition("volregime_atr_ratio", Operator.GT, float(thresh))
        if "volregime_regime" in self.df.columns:
            for value in regime_values:
                yield AtomicCondition("volregime_regime", Operator.EQ, float(value))

    def _price_structure_conditions(self) -> Generator[AtomicCondition, None, None]:
        """
        Price-structure atoms. Every ps_dist_* column is (level - price) / ATR, so a
        positive value means the level is ABOVE price. ps_gap_atr is the signed daily
        gap in ATR; ps_gap_fill_pct is the percentage of that gap already filled.
        """
        dist_thresholds = self.config.get("ps_dist_thresholds", [-2, -1, -0.5, 0.5, 1, 2])
        gap_thresholds = self.config.get("ps_gap_thresholds", [-1, -0.5, 0.5, 1])
        gap_fill_thresholds = self.config.get("ps_gap_fill_thresholds", [25, 50, 75])

        for col in self.df.columns:
            if col.startswith("ps_dist_"):
                for thresh in dist_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
                    yield AtomicCondition(col, Operator.GT, float(thresh))
        if "ps_gap_atr" in self.df.columns:
            for thresh in gap_thresholds:
                yield AtomicCondition("ps_gap_atr", Operator.LT, float(thresh))
                yield AtomicCondition("ps_gap_atr", Operator.GT, float(thresh))
        if "ps_gap_fill_pct" in self.df.columns:
            for thresh in gap_fill_thresholds:
                yield AtomicCondition("ps_gap_fill_pct", Operator.GT, float(thresh))

    def _news_conditions(self) -> Generator[AtomicCondition, None, None]:
        """
        Atoms for the news_* columns exported by dataExporter.mq5 v1.02 (after
        ``sanitize_news_columns`` has removed the bar-boundary look-ahead).

        news_min_to_next / news_min_since_last: '<' minute thresholds
        news_in_window: '== 1'
        news_count_next_24h: '>' count thresholds
        news_next_importance / news_last_importance: '==' each importance level that occurs
            (skipped when the column is constant, e.g. the export only kept HIGH events)
        news_last_surprise: only its SIGN ('> 0' beat / '< 0' miss vs forecast). Its magnitude is
            in the raw unit of each event (thousands of jobs vs percent), so a numeric
            threshold would mix incomparable numbers.
        """
        minute_thresholds = self.config.get("calendar_minutes_thresholds", [15, 30, 60, 120, 240])
        count_thresholds = self.config.get("news_count_thresholds", [0, 1, 2])

        cols = self.df.columns
        for col in ("news_min_to_next", "news_min_since_last"):
            if col in cols:
                for thresh in minute_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
        if "news_in_window" in cols:
            yield AtomicCondition("news_in_window", Operator.EQ, 1.0)
        if "news_count_next_24h" in cols:
            for thresh in count_thresholds:
                yield AtomicCondition("news_count_next_24h", Operator.GT, float(thresh))
        for col in ("news_next_importance", "news_last_importance"):
            if col in cols:
                values = self.df[col].to_numpy()
                values = values[~np.isnan(values)]
                if len(values) and values.min() != values.max():
                    for level in np.unique(values):
                        yield AtomicCondition(col, Operator.EQ, float(level))
        if "news_last_surprise" in cols:
            yield AtomicCondition("news_last_surprise", Operator.GT, 0.0)
            yield AtomicCondition("news_last_surprise", Operator.LT, 0.0)

    def _calendar_conditions(self) -> Generator[AtomicCondition, None, None]:
        """
        Economic-calendar atoms (columns built by
        edge_research.ingestion.economic_calendar).

        cal_min_to_next_* / cal_min_since_last_*: '<' minute thresholds
            ("news within N minutes" / "N minutes after news")
        cal_*_in_bar / cal_*_next_bar: '== 1' (news released in this bar / due in the next)
        cal_last_impact_sym: '== 1' / '== -1' (last high-impact release bullish / bearish
            for the symbol)
        cal_last_surprise_absz: '>' thresholds (size of the last surprise in std units)
        """
        minute_thresholds = self.config.get("calendar_minutes_thresholds", [15, 30, 60, 120, 240])
        surprise_thresholds = self.config.get("calendar_surprise_thresholds", [0.5, 1.0, 2.0])

        for col in self.df.columns:
            if not col.startswith(CALENDAR_PREFIX):
                continue
            if col.startswith("cal_min_"):
                for thresh in minute_thresholds:
                    yield AtomicCondition(col, Operator.LT, float(thresh))
            elif col.endswith("_in_bar") or col.endswith("_next_bar"):
                yield AtomicCondition(col, Operator.EQ, 1.0)
            elif col == "cal_last_impact_sym":
                yield AtomicCondition(col, Operator.EQ, 1.0)
                yield AtomicCondition(col, Operator.EQ, -1.0)
            elif col == "cal_last_surprise_absz":
                for thresh in surprise_thresholds:
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
        if col1 == col2:
            return 1.0
        
        if col1 not in self.df.columns or col2 not in self.df.columns:
            return 0.0

        # Memoized: is_diverse_combo() asks about the same few dozen column
        # pairs once per COMBINATION (thousands of times), and each uncached
        # call copies two full columns and runs dropna()+corr() over the
        # whole window (~1M rows on M1).
        key = (col1, col2) if col1 <= col2 else (col2, col1)
        cache = self.__dict__.setdefault("_corr_cache", {})
        if key in cache:
            return cache[key]
        
        # Drop NaN for correlation
        valid = self.df[[col1, col2]].dropna()
        if len(valid) < 2:
            result = 0.0
        else:
            result = valid[col1].corr(valid[col2])
        cache[key] = result
        return result

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
