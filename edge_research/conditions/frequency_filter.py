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
