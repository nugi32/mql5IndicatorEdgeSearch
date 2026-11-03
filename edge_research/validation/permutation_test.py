"""
Phase 7d: Rotation-Based Permutation Significance Test

An additional, non-parametric significance check that complements (does
NOT replace) the analytic z-test + Benjamini-Hochberg correction in
edge_research.forward_profile.significance.

WHY THIS MODULE EXISTS
------------------------
The z-test in Phase 6 assumes each trigger of a condition contributes an
approximately independent Bernoulli sample. Market bars are NOT
independent -- consecutive bars are strongly autocorrelated, and a
condition that stays true for several consecutive bars (e.g. RSI staying
below 20 for 10 bars in a row) produces overlapping, highly correlated
"samples" that the z-test treats as if they were 10 independent coin
flips. This inflates apparent statistical significance and is a likely
contributor to edges that look airtight on paper but do not survive
walk-forward validation or live trading.

METHOD
------
1. Take the real forward-outcome series for a condition's chosen horizon
   (a boolean array: True where the future outcome was "bull").
2. Repeatedly rotate (circularly shift) this ENTIRE series by a random
   offset to build a null distribution. A circular shift preserves the
   outcome series' own autocorrelation and any seasonal/regime structure
   perfectly (it is still the exact same sequence of real market
   outcomes, just re-anchored in time), while destroying any genuine
   relationship between the shifted outcomes and the (fixed) condition
   trigger timing.
3. For each rotation, recompute the effect size the SAME trigger mask
   would have produced against that rotated outcome sequence.
4. The empirical p-value is the fraction of rotations whose |effect size|
   is >= the real, unrotated |effect size|.

This requires no distributional assumptions and is implemented as a
single vectorized `np.roll` per permutation, so it stays fast even on
multi-million-row M1 datasets (a rotation of a 5.5M-element boolean array
takes low single-digit milliseconds; a few hundred permutations per
condition is a sub-second cost).

A condition is "permutation-robust" if this empirical p-value is below
`alpha` (by default matching the pipeline's existing alpha).
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def rotation_permutation_test(
    trigger_mask: np.ndarray,
    outcome_series: np.ndarray,
    n_permutations: int = 500,
    alpha: float = 0.05,
    min_shift_fraction: float = 0.05,
    random_state: Optional[int] = None,
) -> dict:
    """
    Empirical, autocorrelation-aware significance test for one condition.

    Parameters
    ----------
    trigger_mask : np.ndarray
        Boolean mask, True where the condition triggers. Same length as
        outcome_series, same alignment convention as the rest of the
        pipeline (trigger_mask[i] True => known at close of bar i).
    outcome_series : np.ndarray
        Boolean array, True where the forward outcome was "bull" at the
        condition's chosen optimal horizon, aligned so that
        outcome_series[i] is the correct forward outcome for a trigger at
        bar i (i.e. this is a column of ForwardProfileEngine.forward_matrix,
        already shift-aligned with no lookahead -- pass
        `engine.forward_matrix[:, horizon - 1]` directly).
    n_permutations : int
        Number of random rotations used to build the null distribution.
        500 is a reasonable default; raise for more precise p-values near
        the alpha boundary, at roughly linear extra cost.
    alpha : float
        Significance threshold for the empirical p-value.
    min_shift_fraction : float
        Rotation offsets are drawn from
        [min_shift_fraction * n, (1 - min_shift_fraction) * n] to avoid
        near-zero shifts that would leave the rotated series almost
        identical to the real one (which would trivially inflate the
        null's overlap with the real effect and bias the test toward
        "not significant").
    random_state : int, optional
        Seed for reproducibility across pipeline runs.

    Returns
    -------
    dict with keys:
        real_effect_size, null_mean, null_std, p_value, significant, n_trades
    """
    rng = np.random.default_rng(random_state)
    n = len(outcome_series)

    if len(trigger_mask) != n:
        raise ValueError("trigger_mask and outcome_series must be the same length")

    n_trig = int(np.sum(trigger_mask))
    if n_trig == 0:
        return {
            "real_effect_size": np.nan,
            "null_mean": np.nan,
            "null_std": np.nan,
            "p_value": np.nan,
            "significant": False,
            "n_trades": 0,
        }

    baseline_p = float(np.mean(outcome_series))
    real_p = float(np.mean(outcome_series[trigger_mask]))
    real_effect = real_p - baseline_p

    lo = max(1, int(min_shift_fraction * n))
    hi = max(lo + 1, n - lo)
    shifts = rng.integers(lo, hi, size=n_permutations)

    null_effects = np.empty(n_permutations, dtype=np.float64)
    for k, s in enumerate(shifts):
        rotated = np.roll(outcome_series, int(s))
        null_effects[k] = float(np.mean(rotated[trigger_mask])) - baseline_p

    p_value = float(np.mean(np.abs(null_effects) >= np.abs(real_effect)))

    return {
        "real_effect_size": real_effect,
        "null_mean": float(np.mean(null_effects)),
        "null_std": float(np.std(null_effects)),
        "p_value": p_value,
        "significant": p_value < alpha,
        "n_trades": n_trig,
    }
