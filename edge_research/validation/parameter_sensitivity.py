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


def sensitivity_test_combined_condition(
    original_condition: CombinedCondition,
    df: pd.DataFrame,
    forward_engine,
    shift_pct: float = 15.0,
) -> Dict:
    """
    Same robustness question as `sensitivity_test_condition` above --
    "does this condition sit on a plateau, or is it a fragile spike?" --
    generalized to a CombinedCondition (an AND of several atoms), which
    `sensitivity_test_condition` cannot handle directly since it reads a
    single `condition.threshold` to shift.

    APPROACH: perturb ONE atom's numeric threshold at a time (by
    +shift_pct% and -shift_pct%), holding every other atom in the combo
    fixed at its original value, and correlate the resulting combo's
    forward-probability profile against the original combo's profile --
    exactly the same "shift and correlate" test each atomic condition
    gets, just applied once per shiftable atom instead of once for the
    whole condition. The combo's overall `sensitivity_score` is the mean
    correlation across every (atom, direction) pair tested. This checks
    "is the combo robust to each of its own thresholds individually
    moving a bit", which is the natural per-atom analogue of the atomic
    test, not a claim about simultaneous multi-atom perturbation (a much
    larger, combinatorial space this function does not attempt to cover).

    An atom with a non-numeric threshold (column-to-column comparisons
    like `ma_20_sma > close`) has nothing to shift and is simply skipped;
    if NO atom in the combo has a numeric threshold, this returns NaN --
    "not tested", not "confirmed robust".

    Parameters
    ----------
    original_condition : CombinedCondition
    df : pd.DataFrame
    forward_engine : ForwardProfileEngine
    shift_pct : float

    Returns
    -------
    dict
        {
            'original_prob_bull': array,
            'per_atom_results': [
                {'atom_index': int, 'atom': str, 'shift_pct': +/-15,
                 'shifted_threshold': float, 'correlation': float},
                ...
            ],
            'sensitivity_score': float,  # mean correlation across all
                                          # (atom, direction) pairs tested
        }
    """
    evaluator = ConditionEvaluator(df)

    orig_mask = evaluator.evaluate_combined(original_condition)
    orig_prob = np.zeros(forward_engine.max_horizon)
    orig_trigger = np.where(orig_mask)[0]
    orig_trigger = orig_trigger[orig_trigger < len(df) - forward_engine.max_horizon]

    if len(orig_trigger) == 0:
        return {
            'original_prob_bull': np.full(forward_engine.max_horizon, np.nan),
            'per_atom_results': [],
            'sensitivity_score': np.nan,
        }

    for h in range(forward_engine.max_horizon):
        bull_count = np.sum(forward_engine.forward_matrix[orig_trigger, h])
        orig_prob[h] = bull_count / len(orig_trigger)

    per_atom_results = []
    correlations = []

    for atom_idx, atom in enumerate(original_condition.atoms):
        param_info = get_numeric_param_from_condition(atom)
        if param_info is None:
            continue  # non-numeric threshold on this atom -- nothing to shift
        _, param_value = param_info

        for shift_direction in [-1, 1]:
            shift_amt = param_value * (shift_pct / 100.0) * shift_direction
            new_value = param_value + shift_amt

            shifted_atom = AtomicCondition(atom.column, atom.operator, new_value)
            shifted_atoms = list(original_condition.atoms)
            shifted_atoms[atom_idx] = shifted_atom
            shifted_combo = CombinedCondition(shifted_atoms)

            try:
                shifted_mask = evaluator.evaluate_combined(shifted_combo)
                shifted_trigger = np.where(shifted_mask)[0]
                shifted_trigger = shifted_trigger[shifted_trigger < len(df) - forward_engine.max_horizon]

                if len(shifted_trigger) == 0:
                    corr = np.nan
                else:
                    shifted_prob = np.zeros(forward_engine.max_horizon)
                    for h in range(forward_engine.max_horizon):
                        bull_count = np.sum(forward_engine.forward_matrix[shifted_trigger, h])
                        shifted_prob[h] = bull_count / len(shifted_trigger)

                    valid = ~np.isnan(orig_prob) & ~np.isnan(shifted_prob)
                    if np.sum(valid) > 1:
                        corr = float(np.corrcoef(orig_prob[valid], shifted_prob[valid])[0, 1])
                    else:
                        corr = np.nan

                per_atom_results.append({
                    'atom_index': atom_idx,
                    'atom': repr(atom),
                    'shift_pct': shift_pct * shift_direction,
                    'shifted_threshold': new_value,
                    'correlation': corr,
                })

                if not np.isnan(corr):
                    correlations.append(corr)

            except Exception as e:
                logger.warning(f"Error evaluating shifted combo atom {atom_idx}: {e}")

    sensitivity_score = float(np.nanmean(correlations)) if correlations else np.nan

    return {
        'original_prob_bull': orig_prob,
        'per_atom_results': per_atom_results,
        'sensitivity_score': sensitivity_score,
    }


def sensitivity_test_condition_generic(
    condition,
    df: pd.DataFrame,
    forward_engine,
    shift_pct: float = 15.0,
) -> Dict:
    """
    Dispatch to `sensitivity_test_condition` (AtomicCondition) or
    `sensitivity_test_combined_condition` (CombinedCondition) as
    appropriate. Use this from callers that handle both condition types
    generically (e.g. scripts/run_pipeline.py's Phase 7 robustness loop,
    edge_research.walkforward's plateau selection) instead of
    special-casing CombinedCondition into an automatic NaN.
    """
    if isinstance(condition, CombinedCondition):
        return sensitivity_test_combined_condition(condition, df, forward_engine, shift_pct=shift_pct)
    return sensitivity_test_condition(condition, df, forward_engine, shift_pct=shift_pct)


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
