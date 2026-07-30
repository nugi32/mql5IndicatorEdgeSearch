Edge Research Project - Complete Implementation
I'll build this systematically, phase by phase.

pyproject.toml
toml
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "edge-research"
version = "0.1.0"
description = "Systematic market-edge discovery pipeline from MQL5-exported indicator data"
requires-python = ">=3.9"
authors = [{name = "Edge Research", email = "dev@edge-research.local"}]
license = {text = "MIT"}

dependencies = [
    "numpy==1.26.4",
    "pandas==2.1.4",
    "pyarrow==14.0.1",
    "pyyaml==6.0.1",
    "scipy==1.11.4",
    "statsmodels==0.14.0",
    "jinja2==3.1.2",
    "pydantic==2.5.2",
    "pydantic-settings==2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest==7.4.3",
    "pytest-cov==4.1.0",
    "black==23.12.1",
    "ruff==0.1.11",
    "mypy==1.7.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true

[tool.black]
line-length = 100
target-version = ["py39"]

[tool.ruff]
line-length = 100
target-version = "py39"
config/known_at_delay.yaml
yaml
# Mapping of indicator columns to their availability delay (in bars)
# Default is 0 (available at close of current bar)
# Future: Ichimoku, Fractals, etc. will have nonzero delays

# Moving averages — available at bar close
ma_.*: 0

# Adaptive MAs
dema_.*: 0
tema_.*: 0
frama_.*: 0
ama_.*: 0
vidya_.*: 0

# Trend/Directional
sar_.*: 0
adx_.*: 0
adxwilder_.*: 0

# Oscillators
rsi_.*: 0
stoch_.*: 0
cci_.*: 0
wpr_.*: 0
mom_.*: 0
macd_.*: 0
osma_.*: 0
demarker_.*: 0
rvi_.*: 0
trix_.*: 0
ac: 0
ao: 0
bears_.*: 0
bulls_.*: 0

# Volatility
atr_.*: 0
bb_.*: 0
stddev_.*: 0
envelope_.*: 0

# Volume-based
obv: 0
ad: 0
mfi_.*: 0
force_.*: 0
chaikin_.*: 0
volumes: 0

# OHLCV
open: 0
high: 0
low: 0
close: 0
tick_volume: 0
real_volume: 0
config/pipeline_config.yaml
yaml
# Pipeline Configuration for edge_research

# Forward-looking horizon parameters
max_horizon: 20                    # Maximum bars to look ahead (1 to 20)
min_horizon: 1                     # Minimum bars (always 1)

# Frequency filtering
min_occurrence: 50                 # Minimum number of times condition triggers
min_freq_per_year: 10              # Minimum occurrences per year (at 1H: ~250 trading days/year)

# Statistical significance
alpha: 0.05                        # Significance level for hypothesis tests
fdr_method: "fdr_bh"               # Benjamini-Hochberg FDR correction

# Walk-forward validation
wf_train_bars: 5000                # Training window size (bars)
wf_test_bars: 1000                 # Test window size (bars)
wf_step_bars: 500                  # Step size between windows

# Regime classification
atr_percentile_low: 25             # ATR < 25th percentile = low vol
atr_percentile_high: 75            # ATR > 75th percentile = high vol

adx_trending_threshold: 25         # ADX > 25 = trending regime
adx_ranging_threshold: 20          # ADX < 20 = ranging regime

# Parameter sensitivity
param_shift_pct: 15                # ±15% parameter shift for sensitivity test

# Cost model (entry and exit)
spread_pips: 2.0                   # Spread in pips
slippage_pips: 1.0                 # Slippage in pips (on entry and exit)
pip_value: 0.0001                  # Pip value (for major forex pairs)

# Holdout set
holdout_pct: 0.15                  # Reserve 15% of data as final untouched test set

# Condition generation
rsi_thresholds: [20, 25, 30, 35, 70, 75, 80]
cci_thresholds: [-100, -50, 50, 100]
mom_thresholds: [-5, 0, 5]
stoch_thresholds: [20, 30, 70, 80]

# Output
output_dir: "./output"
parquet_compression: "zstd"        # zstd or snappy
edge_research/init.py
python
"""
edge_research: Systematic market-edge discovery pipeline.

Phases:
  1. Ingestion: Load MQL5-exported CSV -> Parquet
  2. Known-At: Determine when each indicator is available
  3. Conditions: Build atomic and combined signal conditions
  4. Frequency: Pre-filter conditions by occurrence rate
  5. Forward Profile: Compute probability profiles across horizons
  6. Significance: Statistical testing + FDR correction
  7. Validation: Walk-forward, regime stress, parameter sensitivity, cost
  8. Reporting: Generate edge reports in YAML
  9. MQL5 CodeGen: Render compilable .mq5 EAs
"""

__version__ = "0.1.0"

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)
edge_research/ingestion/loader.py
python
"""
Phase 1: Ingestion & Storage

Load MQL5-exported CSV, validate, convert to float32, parse datetime,
write to Parquet for efficient access by later phases.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


def load_csv_and_validate(
    csv_path: str | Path,
) -> pd.DataFrame:
    """
    Load MQL5-exported CSV file and perform basic validation.

    Parameters
    ----------
    csv_path : str | Path
        Path to the MQL5-exported CSV file.

    Returns
    -------
    pd.DataFrame
        Validated dataframe with datetime index and all numeric columns as float32.

    Raises
    ------
    ValueError
        If duplicate timestamps or non-monotonic ordering detected.

    Notes
    -----
    - Parses 'time' column as datetime (expected format: YYYY.MM.DD HH:MI)
    - Converts all numeric columns to float32
    - Warns if NaN values exceed expected warm-up period
    - Does NOT crash on NaN; logs warning instead
    """
    logger.info(f"Loading CSV from {csv_path}")
    
    # Read CSV with period as decimal separator
    df = pd.read_csv(csv_path, sep=",", decimal=".")
    
    # Rename 'time' column if present (some exports may use different name)
    if "time" not in df.columns:
        raise ValueError("CSV must contain 'time' column")
    
    # Parse datetime: expected format YYYYMMDD HHMM (after CSV export removes dots)
    # Try multiple formats
    for fmt in ["%Y%m%d %H%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"]:
        try:
            df["time"] = pd.to_datetime(df["time"], format=fmt)
            break
        except Exception:
            continue
    else:
        # Fallback: try pandas auto-detect
        logger.warning("Could not parse time with standard formats, using pandas auto-detect")
        df["time"] = pd.to_datetime(df["time"])
    
    # Set index
    df.set_index("time", inplace=True)
    
    # Check for duplicate timestamps
    if df.index.duplicated().any():
        duplicates = df.index[df.index.duplicated(keep=False)].unique()
        raise ValueError(f"Found duplicate timestamps: {duplicates}")
    
    # Check for monotonic increasing
    if not df.index.is_monotonic_increasing:
        raise ValueError("Timestamps are not strictly monotonically increasing")
    
    logger.info(f"Loaded {len(df)} rows, date range: {df.index[0]} to {df.index[-1]}")
    
    # Convert numeric columns to float32
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df[col] = df[col].astype(np.float32)
    
    # Check for NaN
    nan_counts = df.isna().sum()
    if nan_counts.any():
        logger.warning(f"Found NaN values:\n{nan_counts[nan_counts > 0]}")
    
    logger.info(f"Converted {len(numeric_cols)} numeric columns to float32")
    
    return df


def save_to_parquet(
    df: pd.DataFrame,
    output_dir: str | Path,
    symbol: str,
    timeframe: str,
    compression: str = "zstd",
) -> Path:
    """
    Save dataframe to Parquet file.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with datetime index and float32 columns.
    output_dir : str | Path
        Directory to save Parquet file.
    symbol : str
        Symbol (e.g., 'EURUSD').
    timeframe : str
        Timeframe (e.g., 'H1', 'D1').
    compression : str
        Compression codec ('zstd', 'snappy', or None).

    Returns
    -------
    Path
        Path to written Parquet file.

    Notes
    -----
    - Filename format: {SYMBOL}_{TIMEFRAME}.parquet
    - Index (datetime) is preserved in Parquet
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{symbol}_{timeframe}.parquet"
    filepath = output_dir / filename
    
    logger.info(f"Writing Parquet to {filepath} (compression={compression})")
    
    # Convert index to datetime64[ns] if not already
    if df.index.dtype.kind != 'M':
        df.index = pd.to_datetime(df.index)
    
    df.to_parquet(filepath, compression=compression)
    
    logger.info(f"Successfully wrote {len(df)} rows to {filepath}")
    
    return filepath


def load_from_parquet(parquet_path: str | Path) -> pd.DataFrame:
    """
    Load previously saved Parquet file.

    Parameters
    ----------
    parquet_path : str | Path
        Path to Parquet file.

    Returns
    -------
    pd.DataFrame
        DataFrame with datetime index and numeric columns as float32.

    Notes
    -----
    This is the primary accessor for all downstream phases after Phase 1 completes.
    """
    logger.info(f"Loading Parquet from {parquet_path}")
    df = pd.read_parquet(parquet_path)
    
    # Ensure float32 dtype
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].dtype != np.float32:
            df[col] = df[col].astype(np.float32)
    
    logger.info(f"Loaded {len(df)} rows from {parquet_path}")
    return df


def ingest_pipeline(
    csv_path: str | Path,
    output_dir: str | Path,
    symbol: str,
    timeframe: str,
    compression: str = "zstd",
) -> Tuple[pd.DataFrame, Path]:
    """
    Full Phase 1 ingestion pipeline: CSV -> validate -> Parquet.

    Parameters
    ----------
    csv_path : str | Path
        Input CSV file path.
    output_dir : str | Path
        Output directory for Parquet.
    symbol : str
        Symbol identifier.
    timeframe : str
        Timeframe identifier.
    compression : str
        Parquet compression codec.

    Returns
    -------
    Tuple[pd.DataFrame, Path]
        Loaded dataframe and path to saved Parquet file.
    """
    df = load_csv_and_validate(csv_path)
    filepath = save_to_parquet(df, output_dir, symbol, timeframe, compression)
    return df, filepath
edge_research/known_at/tagging.py
python
"""
Phase 2: Known-At Tagging

Determine the availability delay (in bars) for each indicator column.
Supports nonzero delays for future Tier 2 indicators without code changes
(only YAML config updates needed).
"""

import logging
import re
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger(__name__)


class KnownAtTagger:
    """
    Manages known-at delays for indicator columns based on YAML config.

    Attributes
    ----------
    delays : Dict[str, int]
        Mapping from column name pattern (regex) to delay in bars.
    """

    def __init__(self, config_path: str | Path):
        """
        Load known-at config from YAML file.

        Parameters
        ----------
        config_path : str | Path
            Path to known_at_delay.yaml.
        """
        self.config_path = Path(config_path)
        self.delays: Dict[str, int] = {}
        self._patterns: list = []  # Compiled patterns
        
        self._load_config()

    def _load_config(self) -> None:
        """Load and compile YAML config."""
        logger.info(f"Loading known-at config from {self.config_path}")
        
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        
        if config is None:
            config = {}
        
        for pattern_str, delay in config.items():
            if pattern_str.startswith("#"):
                continue
            
            # Store as regex pattern
            self.delays[pattern_str] = int(delay)
            
            # Compile pattern (convert glob-style * to regex)
            regex_pattern = pattern_str.replace(".", r"\.").replace("*", ".*") + "$"
            self._patterns.append((re.compile(regex_pattern), delay))
        
        logger.info(f"Loaded {len(self.delays)} known-at rules")

    def known_at_bar(self, column_name: str, bar_index: int) -> int:
        """
        Determine the bar index at which a column's value is known for decision-making.

        Parameters
        ----------
        column_name : str
            Name of the indicator column (e.g., 'rsi_14', 'ma_20_ema').
        bar_index : int
            Current bar index.

        Returns
        -------
        int
            The bar index at which this column's value is available.

        Notes
        -----
        If the column name matches a pattern in the config, returns
        bar_index - delay. Otherwise, returns bar_index (delay=0).

        For example, if rsi_14 has delay=1, then at bar 10,
        the value known is from bar 9.
        """
        # Try to match against patterns
        for pattern, delay in self._patterns:
            if pattern.match(column_name):
                result = bar_index - delay
                logger.debug(f"{column_name} at bar {bar_index} -> known at bar {result} (delay={delay})")
                return result
        
        # Default: no delay
        logger.debug(f"{column_name} at bar {bar_index} -> known at bar {bar_index} (default delay=0)")
        return bar_index

    def get_delay(self, column_name: str) -> int:
        """
        Get the configured delay for a column name.

        Parameters
        ----------
        column_name : str
            Column name.

        Returns
        -------
        int
            Delay in bars (0 if not configured).
        """
        for pattern, delay in self._patterns:
            if pattern.match(column_name):
                return delay
        return 0
edge_research/conditions/condition_library.py
python
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
edge_research/conditions/frequency_filter.py
python
"""
Phase 4: Frequency Pre-Filter

Filter conditions by occurrence rate and frequency.
Only pass to Phase 5 those conditions meeting minimum thresholds.
"""

import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FrequencyFilter:
    """Filters conditions by occurrence statistics."""

    def __init__(
        self,
        df: pd.DataFrame,
        min_occurrence: int = 50,
        min_freq_per_year: float = 10.0,
    ):
        """
        Initialize frequency filter.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with datetime index.
        min_occurrence : int
            Minimum number of occurrences required.
        min_freq_per_year : float
            Minimum frequency per calendar year.
        """
        self.df = df
        self.min_occurrence = min_occurrence
        self.min_freq_per_year = min_freq_per_year
        
        # Calculate years covered by data
        date_range = df.index[-1] - df.index[0]
        self.years_covered = date_range.days / 365.25

    def analyze_condition_frequency(
        self,
        mask: np.ndarray,
    ) -> Tuple[int, float]:
        """
        Analyze the frequency of a condition.

        Parameters
        ----------
        mask : np.ndarray
            Boolean mask of shape (len(df),), True where condition occurs.

        Returns
        -------
        Tuple[int, float]
            (n_occurrence, freq_per_year)
        """
        n_occurrence = int(np.sum(mask))
        freq_per_year = n_occurrence / self.years_covered if self.years_covered > 0 else 0.0
        
        return n_occurrence, freq_per_year

    def passes_filter(self, mask: np.ndarray) -> bool:
        """
        Check if a condition passes frequency thresholds.

        Parameters
        ----------
        mask : np.ndarray
            Boolean condition mask.

        Returns
        -------
        bool
            True if condition meets both min_occurrence and min_freq_per_year.
        """
        n_occur, freq_per_year = self.analyze_condition_frequency(mask)
        
        passes = (n_occur >= self.min_occurrence) and (freq_per_year >= self.min_freq_per_year)
        
        if not passes:
            logger.debug(
                f"Condition rejected: n_occur={n_occur} (min={self.min_occurrence}), "
                f"freq_per_year={freq_per_year:.2f} (min={self.min_freq_per_year})"
            )
        
        return passes


def filter_conditions_batch(
    masks: list,
    condition_descriptions: list,
    freq_filter: FrequencyFilter,
) -> Tuple[list, list]:
    """
    Filter a batch of condition masks.

    Parameters
    ----------
    masks : list
        List of boolean masks.
    condition_descriptions : list
        List of condition descriptions (for logging).
    freq_filter : FrequencyFilter
        Initialized frequency filter.

    Returns
    -------
    Tuple[list, list]
        (passing_masks, passing_descriptions)
    """
    passing_masks = []
    passing_descriptions = []
    
    for mask, desc in zip(masks, condition_descriptions):
        if freq_filter.passes_filter(mask):
            passing_masks.append(mask)
            passing_descriptions.append(desc)
    
    logger.info(
        f"Frequency filter: {len(passing_masks)} / {len(masks)} conditions passed "
        f"(min_occurrence={freq_filter.min_occurrence}, "
        f"min_freq_per_year={freq_filter.min_freq_per_year})"
    )
    
    return passing_masks, passing_descriptions
edge_research/forward_profile/engine.py
python
"""
Phase 5: Forward Probability Profiling

Compute forward-direction probability profiles across horizons.
No lookahead: entry at next bar's open, exit at future bar's close.
"""

import gc
import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ForwardProfileEngine:
    """
    Precomputes and caches forward price movement probabilities.

    Attributes
    ----------
    df : pd.DataFrame
        OHLCV dataframe.
    max_horizon : int
        Maximum bars to look ahead.
    forward_matrix : np.ndarray
        Boolean matrix of shape (n_bars, max_horizon).
        forward_matrix[i, h] = True if close[i+1+h] > open[i+1]
    """

    def __init__(self, df: pd.DataFrame, max_horizon: int = 20):
        """
        Initialize engine and precompute forward direction matrix.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV dataframe with index and 'open', 'close' columns.
        max_horizon : int
            Maximum horizon to compute (default 20 bars).

        Notes
        -----
        RAM usage: n_bars × max_horizon bytes (for bool dtype).
        For 100k bars × 20 horizons ≈ 2 MB.
        """
        self.df = df
        self.max_horizon = max_horizon
        self.forward_matrix = None
        
        self._precompute_forward_matrix()

    def _precompute_forward_matrix(self) -> None:
        """
        Precompute forward direction matrix.

        The matrix is computed fully vectorized:
        - Entry at bar i: next bar's open = open[i+1]
        - Exit at bar i+h: close[i+1+h]
        - Signal: close[i+1+h] > open[i+1]
        """
        logger.info(f"Precomputing forward matrix (horizon={self.max_horizon})...")
        
        n_bars = len(self.df)
        open_prices = self.df["open"].values.astype(np.float32)
        close_prices = self.df["close"].values.astype(np.float32)
        
        # Initialize matrix
        self.forward_matrix = np.zeros((n_bars, self.max_horizon), dtype=bool)
        
        # For each horizon h, compute whether close[i+1+h] > open[i+1]
        for h in range(self.max_horizon):
            # Entry index: i+1 (next bar after signal)
            # Exit index: i+1+h (h bars later)
            exit_idx = np.arange(n_bars) + 1 + h
            entry_idx = np.arange(n_bars) + 1
            
            # Only compute for valid indices (not at end of data)
            valid = exit_idx < n_bars
            
            # Vectorized comparison
            self.forward_matrix[valid, h] = (
                close_prices[exit_idx[valid]] > open_prices[entry_idx[valid]]
            )
        
        logger.info(f"Forward matrix computed: shape {self.forward_matrix.shape}")

    def get_profile_for_condition(
        self,
        condition_mask: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute forward profile for a given condition mask.

        Parameters
        ----------
        condition_mask : np.ndarray
            Boolean mask of shape (n_bars,), True where condition triggers.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray, np.ndarray]
            (prob_bull, sample_size, valid_mask)
            - prob_bull: shape (max_horizon,), probability of bull outcome per horizon
            - sample_size: shape (max_horizon,), count of valid samples per horizon
            - valid_mask: shape (n_bars,), which bars had valid condition evaluation

        Notes
        -----
        - Excludes bars too close to end (where future close unavailable)
        - Returns NaN for horizons with zero valid samples
        """
        n_bars = len(self.df)
        
        # Exclude bars at end (can't compute all horizons)
        valid_mask = condition_mask.copy()
        valid_mask[n_bars - self.max_horizon:] = False
        
        trigger_indices = np.where(valid_mask)[0]
        
        if len(trigger_indices) == 0:
            logger.warning("Condition has no valid trigger points")
            return (
                np.full(self.max_horizon, np.nan),
                np.zeros(self.max_horizon, dtype=int),
                valid_mask,
            )
        
        prob_bull = np.zeros(self.max_horizon, dtype=np.float32)
        sample_size = np.zeros(self.max_horizon, dtype=int)
        
        for h in range(self.max_horizon):
            # Count bull outcomes at this horizon
            bull_count = np.sum(self.forward_matrix[trigger_indices, h])
            n_samples = len(trigger_indices)
            
            prob_bull[h] = bull_count / n_samples if n_samples > 0 else np.nan
            sample_size[h] = n_samples
        
        return prob_bull, sample_size, valid_mask

    def get_baseline_profile(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute unconditional forward profile across entire dataset.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (baseline_prob_bull, baseline_sample_size)

        Notes
        -----
        Used as null hypothesis in significance testing.
        """
        logger.info("Computing baseline forward profile...")
        
        n_bars = len(self.df)
        valid_all = np.ones(n_bars, dtype=bool)
        valid_all[n_bars - self.max_horizon:] = False
        
        baseline_prob = np.zeros(self.max_horizon, dtype=np.float32)
        baseline_size = np.zeros(self.max_horizon, dtype=int)
        
        n_valid = np.sum(valid_all)
        
        for h in range(self.max_horizon):
            valid_indices = np.where(valid_all)[0]
            bull_count = np.sum(self.forward_matrix[valid_indices, h])
            baseline_prob[h] = bull_count / n_valid if n_valid > 0 else 0.5
            baseline_size[h] = n_valid
        
        logger.info(f"Baseline profile computed: {baseline_prob}")
        
        return baseline_prob, baseline_size

    def clear_cache(self) -> None:
        """
        Clear forward matrix from memory (for batch processing multiple symbols).
        """
        if self.forward_matrix is not None:
            del self.forward_matrix
            self.forward_matrix = None
            gc.collect()
            logger.debug("Forward matrix cache cleared")
edge_research/forward_profile/significance.py
python
"""
Phase 6: Statistical Testing

Two-sided proportion z-test + Benjamini-Hochberg FDR correction.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

logger = logging.getLogger(__name__)


def wilson_ci(
    successes: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """
    Compute Wilson score confidence interval for a binomial proportion.

    Parameters
    ----------
    successes : int
        Number of successes (bull outcomes).
    n : int
        Total number of trials.
    confidence : float
        Confidence level (default 0.95 for 95% CI).

    Returns
    -------
    Tuple[float, float]
        (lower, upper) bounds of confidence interval.

    Notes
    -----
    Wilson CI is more accurate than normal approximation, especially for
    small sample sizes and proportions near 0 or 1.
    """
    if n == 0:
        return (np.nan, np.nan)
    
    p_hat = successes / n
    z = stats.norm.ppf((1 + confidence) / 2)
    
    denominator = 1 + z**2 / n
    
    center = (p_hat + z**2 / (2 * n)) / denominator
    margin = z * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denominator
    
    lower = center - margin
    upper = center + margin
    
    return (max(0.0, lower), min(1.0, upper))


def proportion_ztest_per_horizon(
    cond_bull_counts: np.ndarray,
    cond_sample_sizes: np.ndarray,
    baseline_prob: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run two-sided proportion z-test for each horizon.

    Parameters
    ----------
    cond_bull_counts : np.ndarray
        Bull outcome counts per horizon, shape (max_horizon,).
    cond_sample_sizes : np.ndarray
        Sample sizes per horizon.
    baseline_prob : np.ndarray
        Null hypothesis (baseline) probability per horizon.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (p_values, test_statistics) per horizon
    """
    max_horizon = len(baseline_prob)
    p_values = np.zeros(max_horizon)
    test_stats = np.zeros(max_horizon)
    
    for h in range(max_horizon):
        bull_count = cond_bull_counts[h]
        n = cond_sample_sizes[h]
        p0 = baseline_prob[h]
        
        if n == 0 or np.isnan(p0):
            p_values[h] = np.nan
            test_stats[h] = np.nan
            continue
        
        # Observed proportion
        p_obs = bull_count / n
        
        # Standard error under null
        se = np.sqrt(p0 * (1 - p0) / n)
        
        if se == 0:
            p_values[h] = 1.0
            test_stats[h] = 0.0
            continue
        
        # Z-test
        z_stat = (p_obs - p0) / se
        p_val = 2 * (1 - stats.norm.cdf(abs(z_stat)))  # Two-sided
        
        p_values[h] = p_val
        test_stats[h] = z_stat
    
    return p_values, test_stats


def apply_bh_correction(
    p_values: np.ndarray,
    alpha: float = 0.05,
    method: str = "fdr_bh",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Apply Benjamini-Hochberg FDR correction.

    Parameters
    ----------
    p_values : np.ndarray
        Raw p-values.
    alpha : float
        Significance level.
    method : str
        Multiple testing correction method ('fdr_bh', 'fdr_by', 'bonferroni', etc).

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (reject_flags, adjusted_p_values)
    """
    # Filter NaN values for statsmodels
    valid_mask = ~np.isnan(p_values)
    
    if not np.any(valid_mask):
        return np.zeros_like(p_values, dtype=bool), p_values.copy()
    
    p_valid = p_values[valid_mask]
    reject, p_adj_valid, _, _ = multipletests(p_valid, alpha=alpha, method=method)
    
    # Reconstruct full arrays
    p_adj = np.full_like(p_values, np.nan)
    reject_full = np.zeros_like(p_values, dtype=bool)
    
    p_adj[valid_mask] = p_adj_valid
    reject_full[valid_mask] = reject
    
    return reject_full, p_adj


class SignificanceAnalyzer:
    """Orchestrates statistical testing for conditions."""

    def __init__(self, alpha: float = 0.05, fdr_method: str = "fdr_bh"):
        """
        Initialize analyzer.

        Parameters
        ----------
        alpha : float
            Significance level.
        fdr_method : str
            FDR correction method.
        """
        self.alpha = alpha
        self.fdr_method = fdr_method

    def test_condition_horizons(
        self,
        cond_prob_bull: np.ndarray,
        cond_sample_sizes: np.ndarray,
        baseline_prob: np.ndarray,
        baseline_sample_sizes: np.ndarray,
    ) -> pd.DataFrame:
        """
        Test a condition's significance across all horizons with FDR correction.

        Parameters
        ----------
        cond_prob_bull : np.ndarray
            Condition's bull probability per horizon.
        cond_sample_sizes : np.ndarray
            Condition's sample sizes.
        baseline_prob : np.ndarray
            Baseline bull probability.
        baseline_sample_sizes : np.ndarray
            Baseline sample sizes.

        Returns
        -------
        pd.DataFrame
            Results table with columns:
            [horizon, prob_bull, sample_size, p_value, p_adj, significant,
             ci_lower, ci_upper, effect_size]
        """
        max_horizon = len(baseline_prob)
        
        # Convert probabilities to counts for z-test
        cond_bull_counts = (cond_prob_bull * cond_sample_sizes).astype(int)
        
        # Run z-tests
        p_values, z_stats = proportion_ztest_per_horizon(
            cond_bull_counts,
            cond_sample_sizes,
            baseline_prob,
        )
        
        # Apply FDR correction across horizons
        reject, p_adj = apply_bh_correction(p_values, self.alpha, self.fdr_method)
        
        # Compute confidence intervals and effect sizes
        ci_lowers = np.zeros(max_horizon)
        ci_uppers = np.zeros(max_horizon)
        effect_sizes = np.zeros(max_horizon)
        
        for h in range(max_horizon):
            lower, upper = wilson_ci(cond_bull_counts[h], cond_sample_sizes[h])
            ci_lowers[h] = lower
            ci_uppers[h] = upper
            
            # Effect size: difference in proportions
            effect_sizes[h] = (cond_prob_bull[h] - baseline_prob[h])
        
        results_df = pd.DataFrame({
            "horizon": np.arange(1, max_horizon + 1),
            "prob_bull": cond_prob_bull,
            "sample_size": cond_sample_sizes,
            "p_value": p_values,
            "p_adj": p_adj,
            "significant": reject,
            "ci_lower": ci_lowers,
            "ci_upper": ci_uppers,
            "effect_size": effect_sizes,
        })
        
        return results_df

    def select_optimal_horizon(self, results_df: pd.DataFrame) -> Optional[int]:
        """
        Select the optimal horizon from significance test results.

        Parameters
        ----------
        results_df : pd.DataFrame
            Results from test_condition_horizons().

        Returns
        -------
        Optional[int]
            Horizon (1-indexed) with strongest edge, or None if no significant horizon.

        Notes
        -----
        Selection rule:
        1. Filter to significant horizons (p_adj < alpha)
        2. Among significant, pick horizon with maximum effect_size
        3. Tiebreaker: tightest confidence interval (smallest upper - lower)
        """
        sig_df = results_df[results_df["significant"]].copy()
        
        if len(sig_df) == 0:
            return None
        
        # Sort by effect size (descending), then by CI width (ascending)
        sig_df["ci_width"] = sig_df["ci_upper"] - sig_df["ci_lower"]
        sig_df = sig_df.sort_values(
            by=["effect_size", "ci_width"],
            ascending=[False, True],
        )
        
        return int(sig_df.iloc[0]["horizon"])

    def test_batch_conditions(
        self,
        condition_results: List[Dict],
        baseline_prob: np.ndarray,
        baseline_sample_sizes: np.ndarray,
    ) -> List[Dict]:
        """
        Test multiple conditions (FDR-corrected across conditions + horizons).

        Parameters
        ----------
        condition_results : List[Dict]
            List of dicts with keys 'prob_bull', 'sample_sizes'.
        baseline_prob : np.ndarray
            Baseline probabilities.
        baseline_sample_sizes : np.ndarray
            Baseline sample sizes.

        Returns
        -------
        List[Dict]
            Updated condition_results with 'significance_results', 'optimal_horizon', 'rejected' keys.

        Notes
        -----
        Applies two levels of FDR correction:
        1. Within each condition: across horizons
        2. Across all conditions: all p-values pooled
        """
        logger.info(f"Testing {len(condition_results)} conditions with FDR correction...")
        
        # First pass: per-condition testing
        all_p_values = []
        condition_p_dfs = []
        
        for cond_res in condition_results:
            p_df = self.test_condition_horizons(
                cond_res["prob_bull"],
                cond_res["sample_sizes"],
                baseline_prob,
                baseline_sample_sizes,
            )
            condition_p_dfs.append(p_df)
            all_p_values.extend(p_df["p_value"].dropna().values)
        
        # Second pass: global FDR correction across all tests
        if all_p_values:
            all_p_array = np.array(all_p_values)
            _, p_adj_global = apply_bh_correction(all_p_array, self.alpha, self.fdr_method)
            
            # Map back to conditions
            p_idx = 0
            for i, cond_res in enumerate(condition_results):
                p_df = condition_p_dfs[i]
                p_df_valid = p_df[~p_df["p_value"].isna()]
                n_p = len(p_df_valid)
                
                p_df.loc[p_df["p_value"].notna(), "p_adj"] = p_adj_global[p_idx : p_idx + n_p]
                p_df["significant"] = p_df["p_adj"] < self.alpha
                
                p_idx += n_p
                
                # Select optimal horizon
                optimal_h = self.select_optimal_horizon(p_df)
                
                cond_res["significance_results"] = p_df
                cond_res["optimal_horizon"] = optimal_h
                cond_res["rejected"] = optimal_h is None
        
        logger.info(
            f"Testing complete: "
            f"{sum(1 for c in condition_results if not c.get('rejected', True))} "
            f"conditions passed significance"
        )
        
        return condition_results
edge_research/validation/walk_forward.py
python
"""
Walk-forward validation: rolling train/test splits.
"""

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """Rolling window train/test validator."""

    def __init__(
        self,
        df: pd.DataFrame,
        train_bars: int = 5000,
        test_bars: int = 1000,
        step_bars: int = 500,
    ):
        """
        Initialize validator.

        Parameters
        ----------
        df : pd.DataFrame
            Full dataframe with datetime index.
        train_bars : int
            Training window size.
        test_bars : int
            Test window size.
        step_bars : int
            Step size between windows.
        """
        self.df = df
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars
        
        self.windows = self._generate_windows()

    def _generate_windows(self) -> List[Tuple[int, int, int, int]]:
        """
        Generate (train_start, train_end, test_start, test_end) indices.

        Returns
        -------
        List[Tuple[int, int, int, int]]
            List of (train_start, train_end, test_start, test_end) index pairs.
        """
        windows = []
        n = len(self.df)
        
        train_start = 0
        while True:
            train_end = train_start + self.train_bars
            test_start = train_end
            test_end = test_start + self.test_bars
            
            if test_end > n:
                break
            
            windows.append((train_start, train_end, test_start, test_end))
            train_start += self.step_bars
        
        logger.info(f"Generated {len(windows)} walk-forward windows")
        return windows

    def get_windows(self) -> List[Tuple[int, int, int, int]]:
        """Return list of windows."""
        return self.windows

    def get_window_data(
        self,
        window_idx: int,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get train and test dataframes for a window.

        Parameters
        ----------
        window_idx : int
            Window index.

        Returns
        -------
        Tuple[pd.DataFrame, pd.DataFrame]
            (train_df, test_df)
        """
        train_start, train_end, test_start, test_end = self.windows[window_idx]
        
        train_df = self.df.iloc[train_start:train_end]
        test_df = self.df.iloc[test_start:test_end]
        
        return train_df, test_df


def validate_condition_walk_forward(
    full_df: pd.DataFrame,
    condition_mask: np.ndarray,
    condition_prob: np.ndarray,
    forward_engine,
    validator: WalkForwardValidator,
) -> dict:
    """
    Validate a condition's edge across walk-forward windows.

    Parameters
    ----------
    full_df : pd.DataFrame
        Full dataframe.
    condition_mask : np.ndarray
        Condition mask on full data.
    condition_prob : np.ndarray
        Probability profile on full data.
    forward_engine :
        ForwardProfileEngine instance.
    validator : WalkForwardValidator
        Walk-forward validator.

    Returns
    -------
    dict
        {
            'edge_direction_consistent': bool,
            'edge_magnitude_std': float,
            'window_results': [{'window': int, 'prob_bull': arr, ...}]
        }
    """
    window_probs = []
    window_results = []
    
    for window_idx, (train_start, train_end, test_start, test_end) in enumerate(validator.get_windows()):
        # Use test set for validation
        test_mask = condition_mask[test_start:test_end].copy()
        test_mask[len(test_mask) - forward_engine.max_horizon:] = False
        
        if np.sum(test_mask) == 0:
            continue
        
        # Recompute forward profile on test set
        test_forward_matrix = forward_engine.forward_matrix[test_start:test_end]
        
        trigger_indices = np.where(test_mask)[0]
        
        test_probs = np.zeros(forward_engine.max_horizon)
        for h in range(forward_engine.max_horizon):
            bull_count = np.sum(test_forward_matrix[trigger_indices, h])
            test_probs[h] = bull_count / len(trigger_indices) if len(trigger_indices) > 0 else 0.5
        
        window_probs.append(test_probs)
        window_results.append({
            'window': window_idx,
            'prob_bull': test_probs,
            'n_samples': np.sum(test_mask),
        })
    
    if not window_probs:
        logger.warning("No valid windows for walk-forward validation")
        return {
            'edge_direction_consistent': False,
            'edge_magnitude_std': np.nan,
            'window_results': [],
        }
    
    window_probs = np.array(window_probs)
    
    # Check consistency: all window prob_bull > 0.5?
    direction_consistent = np.all(np.nanmean(window_probs, axis=0) > 0.5)
    
    # Check magnitude stability: std of prob_bull across windows
    magnitude_std = np.nanstd(window_probs)
    
    return {
        'edge_direction_consistent': direction_consistent,
        'edge_magnitude_std': float(magnitude_std),
        'window_results': window_results,
    }
edge_research/validation/regime_stress_test.py
python
"""  
Regime stress tests: trending vs ranging, high vol vs low vol.  
"""  

import logging  

import numpy as np  
import pandas as pd  

logger = logging.getLogger(__name__)  


class RegimeClassifier:  
    """Classify market regimes (trending, ranging, high-vol, low-vol)."""  

    def __init__(  
        self,  
        df: pd.DataFrame,  
        adx_trending: float = 25.0,  
        atr_percentile_low: float = 25.0,  
        atr_percentile_high: float = 75.0,  
    ):  
        """  
        Initialize classifier.  

        Parameters  
        ----------  
        df : pd.DataFrame  
            Dataframe with ADX and ATR columns.  
        adx_trending : float  
            ADX threshold for trending classification.  
        atr_percentile_low : float  
            Low ATR percentile threshold.  
        atr_percentile_high : float  
            High ATR percentile threshold.  
        """  
        self.df = df  
        self.adx_trending = adx_trending  
        self.atr_percentile_low = atr_percentile_low  
        self.atr_percentile_high = atr_percentile_high  
        
        self._classify_regimes()  

    def _classify_regimes(self) -> None:  
        """Classify each bar into regime."""  
        n = len(self.df)  
        
        # Trending vs ranging  
        if "adx_14" in self.df.columns:  
            adx = self.df["adx_14"].values  
            self.is_trending = adx > self.adx_trending  
            self.is_ranging = adx <= self.adx_trending  
        else:  
            logger.warning("ADX not found; all bars classified as ranging")  
            self.is_trending = np.zeros(n, dtype=bool)  
            self.is_ranging = np.ones(n, dtype=bool)  
        
        # High vol vs low vol  
        if "atr_14" in self.df.columns:  
            atr = self.df["atr_14"].values  
            atr_low = np.nanpercentile(atr, self.atr_percentile_low)  
            atr_high = np.nanpercentile(atr, self.atr_percentile_high)  
            
            self.is_high_vol = atr > atr_high  
            self.is_low_vol = atr < atr_low  
            self.is_normal_vol = ~(self.is_high_vol | self.is_low_vol)  
        else:  
            logger.warning("ATR not found; all bars classified as normal vol")  
            self.is_high_vol = np.zeros(n, dtype=bool)  
            self.is_low_vol = np.zeros(n, dtype=bool)  
            self.is_normal_vol = np.ones(n, dtype=bool)  
        
        logger.info(  
            f"Regime classification: "  
            f"trending={np.sum(self.is_trending)}, "  
            f"high_vol={np.sum(self.is_high_vol)}"  
        )  

    def get_regime_mask(self, regime: str) -> np.ndarray:  
        """  
        Get boolean mask for a specific regime.  

        Parameters  
        ----------  
        regime : str  
            One of: 'trending', 'ranging', 'high_vol', 'low_vol', 'normal_vol'  

        Returns  
        -------  
        np.ndarray  
            Boolean mask.  
        """  
        if regime == "trending":  
            return self.is_trending  
        elif regime == "ranging":  
            return self.is_ranging  
        elif regime == "high_vol":  
            return self.is_high_vol  
        elif regime == "low_vol":  
            return self.is_low_vol  
        elif regime == "normal_vol":  
            return self.is