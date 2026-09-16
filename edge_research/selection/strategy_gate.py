"""
Phase 7e: Final Strategy Selection Gate

Combines every independent piece of evidence gathered about a condition
into a single pass/fail decision for "is this actually worth turning into
an MQL5 EA." This is intentionally strict -- the goal of this pipeline's
strategy-construction pivot is fewer, more trustworthy edges, not more
edges with impressive-looking p-values.

GATES (all enabled gates must pass)
------------------------------------
1. significant             - Phase 6 FDR-corrected z-test, p_adj < alpha
2. robust_walk_forward      - consistent across walk-forward windows
                               (Phase 7, existing)
3. permutation_significant  - Phase 7d rotation-based permutation test,
                               robust to autocorrelation, p < alpha
4. sim_min_trades           - enough simulated trades (Phase 7c) to trust
                               the expectancy estimate (default >= 30)
5. sim_expectancy_positive  - Phase 7c realistic trade simulation
                               (spread/slippage/SL/TP) yields expectancy_r > 0
6. sim_profit_factor        - gross win / gross loss >= min_profit_factor
                               (default 1.1 -- a deliberately modest margin
                               above breakeven; the goal is filtering out
                               clearly broken edges, not hand-picking a
                               "best" one)
7. sim_expectancy_ci_lower  - OPTIONAL (off by default). If TradeSimConfig's
                               bootstrap_n > 0, requires the LOWER bound of
                               the bootstrap confidence interval on
                               expectancy_r to be positive, not just the
                               point estimate. This is stricter than gate 5:
                               a condition with few trades or high
                               trade-to-trade variance can show a positive
                               mean expectancy_r purely by chance even
                               though the interval around it comfortably
                               includes zero or negative values. See
                               PROJECT_DIRECTION.md section 8.
8. holding_bars_stable      - the per-condition holding period selected by
                               scan_holding_horizons/select_best_holding_bars
                               (Phase 7c) still shows a positive cost-adjusted
                               R-multiple on enough held-out walk-forward
                               windows -- see
                               validate_holding_bars_walk_forward. Without
                               this gate, a holding period chosen purely
                               from full-sample noise could reach Phase 9
                               looking "consistent" when it was actually
                               overfit, the same failure mode gate 2 guards
                               against for direction.

Only conditions passing every enabled gate should proceed to MQL5 code
generation (Phase 9). Conditions that fail are still worth recording for
transparency -- see PROJECT_DIRECTION.md, section 4.
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class GateThresholds:
    """Tunable thresholds for the final selection gate. See module docstring."""

    alpha: float = 0.05
    min_sim_trades: int = 30
    min_profit_factor: float = 1.1
    require_walk_forward: bool = True
    require_permutation: bool = True
    # If True, additionally requires the LOWER bound of the bootstrap CI on
    # expectancy_r (sim_result.expectancy_r_ci_low) to be > 0. Only takes
    # effect when the trade simulation was run with bootstrap_n > 0 in
    # TradeSimConfig -- if the CI wasn't computed (NaN), this gate is
    # skipped rather than silently failing every edge, and a warning is
    # surfaced via the reasons list so the gap is visible.
    require_positive_ci_lower: bool = False
    # See gate 8 in the module docstring. Defaults to True since an
    # unvalidated holding period is exactly the kind of full-sample-only
    # selection this pipeline's other gates exist to catch.
    require_holding_bars_stable: bool = True


def passes_strategy_gate(
    significant: bool,
    robust_walk_forward: bool,
    permutation_result: dict,
    sim_result,  # edge_research.simulation.trade_simulator.TradeSimResult
    thresholds: GateThresholds,
    holding_bars_stable: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Evaluate all gates for one condition.

    Parameters
    ----------
    significant : bool
        Result of Phase 6 FDR-corrected significance testing for this
        condition's optimal horizon.
    robust_walk_forward : bool
        Result of Phase 7 walk-forward validation.
    permutation_result : dict
        Output of edge_research.validation.permutation_test.rotation_permutation_test.
    sim_result : TradeSimResult
        Output of edge_research.simulation.trade_simulator.simulate_condition.
    thresholds : GateThresholds
    holding_bars_stable : bool
        Result of
        edge_research.validation.walk_forward.validate_holding_bars_walk_forward
        -- whether this condition's selected holding period holds up
        out-of-sample. See gate 8 in the module docstring.

    Returns
    -------
    (passed, reasons)
        passed: True only if every enabled gate passes.
        reasons: human-readable list of every gate that failed
                 (empty list if passed).
    """
    reasons: List[str] = []

    if thresholds.require_holding_bars_stable and not holding_bars_stable:
        reasons.append("selected holding period not stable across walk-forward windows")

    if not significant:
        reasons.append("failed Phase 6 significance (p_adj >= alpha)")

    if thresholds.require_walk_forward and not robust_walk_forward:
        reasons.append("not robust across walk-forward windows")

    if thresholds.require_permutation:
        if permutation_result.get("n_trades", 0) == 0:
            reasons.append("permutation test had zero trigger samples")
        elif not permutation_result.get("significant", False):
            p = permutation_result.get("p_value", float("nan"))
            reasons.append(
                f"failed rotation permutation test (p={p:.4f} >= {thresholds.alpha})"
            )

    if sim_result.n_trades < thresholds.min_sim_trades:
        reasons.append(
            f"too few simulated trades ({sim_result.n_trades} < {thresholds.min_sim_trades})"
        )
    else:
        if not (sim_result.expectancy_r > 0):
            reasons.append(
                f"non-positive simulated expectancy (R={sim_result.expectancy_r:.4f})"
            )
        if not (sim_result.profit_factor >= thresholds.min_profit_factor):
            reasons.append(
                f"profit factor below threshold "
                f"({sim_result.profit_factor:.2f} < {thresholds.min_profit_factor})"
            )

        if thresholds.require_positive_ci_lower:
            ci_low = getattr(sim_result, "expectancy_r_ci_low", float("nan"))
            if math.isnan(ci_low):
                reasons.append(
                    "require_positive_ci_lower is enabled but no bootstrap CI "
                    "was computed (set bootstrap_n > 0 in TradeSimConfig)"
                )
            elif not (ci_low > 0):
                reasons.append(
                    f"bootstrap CI lower bound on expectancy_r is not positive "
                    f"(CI low={ci_low:.4f})"
                )

    return (len(reasons) == 0, reasons)
