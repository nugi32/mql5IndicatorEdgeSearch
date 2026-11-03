"""Guards for the shipped walk-forward configs and the top-20 defaults."""
from pathlib import Path

import yaml

from edge_research.ranking.ranker import RankerConfig

ROOT = Path(__file__).resolve().parents[1]


def test_walkforward_configs_have_single_non_duplicate_run():
    # Same train/test/step with different start_year only repeats windows,
    # which inflates the ranker's summed trades and passing windows.
    files = sorted((ROOT / "config" / "WALKFORWARD").rglob("pipeline_config.yaml"))
    assert files
    for f in files:
        runs = yaml.safe_load(f.read_text(encoding="utf-8"))["meta_wf_runs"]
        shapes = [(r["train_years"], r["test_years"], r["step_years"]) for r in runs]
        assert len(runs) == 1, f"{f}: expected one meta_wf_runs entry, got {len(runs)}"
        assert len(set(shapes)) == len(shapes), f"{f}: duplicate window shape"


def test_walkforward_configs_use_total_trade_floor_of_1000():
    for f in sorted((ROOT / "config" / "WALKFORWARD").rglob("pipeline_config.yaml")):
        cfg = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert cfg["ranker_min_total_trades"] == 1000, f
        assert cfg["ranker_drop_below_floor"] is True, f


def test_top_n_defaults_are_20():
    assert RankerConfig().sort_top_n == 20
