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

    Parameters
    ----------
    condition : AtomicCondition
        The condition.

    Returns
    -------
    tuple | None
        (param_name, param_value) if extractable, else None.

    Notes
    -----
    Examples:
    - "rsi_14 < 30" -> ("threshold", 30)
    - "ma_20_sma" -> ("period", 20)
    """
    if isinstance(condition.threshold, str):
        return None  # Column-to-column comparison
    
    # Check if threshold is the numeric parameter
    if condition.operator in (Operator.LT, Operator.GT, Operator.LTE, Operator.GTE):
        return ("threshold", float(condition.threshold))
    
    return None


def sensitivity_test_condition(
    original_condition: AtomicCondition,
    df: pd.DataFrame,
    forward_engine,
    shift_pct: float = 15.0,
) -> Dict:
    """
    Test condition robustness under parameter shifts.

    Parameters
    ----------
    original_condition : AtomicCondition
        Original condition to test.
    df : pd.DataFrame
        Data.
    forward_engine :
        ForwardProfileEngine instance.
    shift_pct : float
        Percentage to shift parameter (e.g., 15 = ±15%).

    Returns
    -------
    dict
        {
            'original_prob_bull': array,
            'shifted_conditions': [
                {'shift_pct': -15, 'prob_bull': array, 'corr': float},
                {'shift_pct': +15, 'prob_bull': array, 'corr': float},
            ],
            'sensitivity_score': float,  # mean correlation across shifts
        }
    """
    evaluator = ConditionEvaluator(df)
    
    # Evaluate original condition
    orig_mask = evaluator.evaluate_atomic(original_condition)
    orig_prob = np.zeros(forward_engine.max_horizon)
    orig_trigger = np.where(orig_mask)[0]
    orig_trigger = orig_trigger[orig_trigger < len(df) - forward_engine.max_horizon]
    
    if len(orig_trigger) == 0:
        return {
            'original_prob_bull': np.full(forward_engine.max_horizon, np.nan),
            'shifted_conditions': [],
            'sensitivity_score': np.nan,
        }
    
    for h in range(forward_engine.max_horizon):
        bull_count = np.sum(forward_engine.forward_matrix[orig_trigger, h])
        orig_prob[h] = bull_count / len(orig_trigger)
    
    # Test shifted versions
    param_info = get_numeric_param_from_condition(original_condition)
    
    if param_info is None:
        logger.warning(f"Could not extract numeric parameter from {original_condition}")
        return {
            'original_prob_bull': orig_prob,
            'shifted_conditions': [],
            'sensitivity_score': np.nan,
        }
    
    param_name, param_value = param_info
    
    shifted_results = []
    correlations = []
    
    for shift_direction in [-1, 1]:
        shift_amt = param_value * (shift_pct / 100.0) * shift_direction
        new_value = param_value + shift_amt
        
        # Create shifted condition
        shifted_cond = AtomicCondition(
            original_condition.column,
            original_condition.operator,
            new_value,
        )
        
        try:
            shifted_mask = evaluator.evaluate_atomic(shifted_cond)
            shifted_trigger = np.where(shifted_mask)[0]
            shifted_trigger = shifted_trigger[shifted_trigger < len(df) - forward_engine.max_horizon]
            
            if len(shifted_trigger) == 0:
                shifted_prob = np.full(forward_engine.max_horizon, np.nan)
                corr = np.nan
            else:
                shifted_prob = np.zeros(forward_engine.max_horizon)
                for h in range(forward_engine.max_horizon):
                    bull_count = np.sum(forward_engine.forward_matrix[shifted_trigger, h])
                    shifted_prob[h] = bull_count / len(shifted_trigger)
                
                # Correlation with original
                valid = ~np.isnan(orig_prob) & ~np.isnan(shifted_prob)
                if np.sum(valid) > 1:
                    corr = float(np.corrcoef(orig_prob[valid], shifted_prob[valid])[0, 1])
                else:
                    corr = np.nan
            
            shifted_results.append({
                'shift_pct': shift_pct * shift_direction,
                'shifted_threshold': new_value,
                'prob_bull': shifted_prob,
                'correlation': corr,
            })
            
            if not np.isnan(corr):
                correlations.append(corr)
        
        except Exception as e:
            logger.warning(f"Error evaluating shifted condition: {e}")
    
    sensitivity_score = np.nanmean(correlations) if correlations else np.nan
    
    return {
        'original_threshold': param_value,
        'original_prob_bull': orig_prob,
        'shifted_conditions': shifted_results,
        'sensitivity_score': float(sensitivity_score),
    }
