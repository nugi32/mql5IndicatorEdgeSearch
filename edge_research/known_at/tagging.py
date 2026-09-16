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
