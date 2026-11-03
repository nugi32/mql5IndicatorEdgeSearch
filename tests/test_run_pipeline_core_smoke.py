"""End-to-end smoke test of run_pipeline_core on tiny synthetic data.

Guards the memory-release refactor (the `del` block after Phase 6, mask
dropping after the gate): every name it deletes must exist, and the
returned structure must stay what the walk-forward orchestrator expects.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_pipeline import run_pipeline_core

REPO = Path(__file__).resolve().parent.parent


def _synthetic_df(n=6000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="min")
    rsi_14 = rng.uniform(0, 100, n)
    # Plant a real edge (rsi_14 < 30 is followed by a drift up) so that
    # candidates survive significance and Phase 7-9 actually execute.
    ret = rng.normal(0, 0.3, n)
    ret[2:] += 0.5 * (rsi_14[:-2] < 30)  # lands AFTER the entry bar (entry = open of bar t+1)
    close = 1800 + ret.cumsum()
    df = pd.DataFrame({
        "open": close + rng.normal(0, 0.05, n),
        "high": close + 0.3, "low": close - 0.3, "close": close,
        "atr_14": np.full(n, 1.0),
        "adx_14": rng.uniform(10, 40, n),
        "rsi_14": rsi_14, "rsi_7": rng.uniform(0, 100, n),
        "cci_20": rng.normal(0, 100, n), "mom_10": rng.normal(0, 3, n),
        "stoch_14_3_3_k": rng.uniform(0, 100, n),
        "ma_20_ema": close + rng.normal(0, 0.2, n),
    }, index=idx).astype(np.float32)
    return df


def test_run_pipeline_core_smoke(tmp_path):
    cfg = {
        "max_horizon": 10, "min_occurrence": 20, "min_freq_per_year": 1.0,
        "alpha": 0.05, "fdr_method": "fdr_bh",
        "wf_train_bars": 2000, "wf_test_bars": 500, "wf_step_bars": 500,
        "spread_pips": 30.0, "slippage_pips": 1.0, "pip_value": 0.01,
        "horizon_scan_min_bars": 1, "horizon_scan_max_bars": 8,
        "permutation_n": 20, "precheck_enabled": False,
        "top_n_atomic_for_combine": 8, "max_atoms_per_combo": 2,
        "include_ma_conditions": True,
        "rsi_thresholds": [30, 70], "cci_thresholds": [-100, 100],
        "mom_thresholds": [0], "stoch_thresholds": [20, 80],
        "gate_min_sim_trades": 5,
    }
    result = run_pipeline_core(
        df=_synthetic_df(),
        known_at_config_path=REPO / "config" / "known_at_delay.yaml",
        pipeline_config=cfg, symbol="TEST", timeframe="M1",
        output_dir=tmp_path,
    )
    assert set(result) >= {"validated_edges", "edge_reports", "gate_passed_ids"}
    assert len(result["validated_edges"]) > 0, "smoke data must reach Phase 7"
    for edge in result["validated_edges"]:
        # masks are kept only for gate-passing edges; everything else the
        # orchestrator / reports need must still be there
        assert (edge["mask"] is not None) == bool(edge["gate_passed"])
        assert "trade_sim" in edge and "robustness" in edge and "condition" in edge
