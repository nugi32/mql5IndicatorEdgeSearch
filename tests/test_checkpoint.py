"""Pause / resume: checkpoint store, pause control, run lock, sessions, and a
full pause-then-resume run of run_pipeline_core compared with an uninterrupted one."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from edge_research.checkpoint import (
    CheckpointMismatch,
    CheckpointStore,
    NullCheckpoint,
    RunControl,
    RunLock,
    RunPaused,
    open_session,
)
from edge_research.checkpoint.store import RecordLog
from edge_research.utils.run_dir import read_run_info
from scripts import run_pipeline
from scripts.run_pipeline import run_pipeline_core
from scripts.run_walkforward_pipeline import _checkpointed_window

REPO = Path(__file__).resolve().parent.parent


# --- record log ---------------------------------------------------------------

def test_record_log_roundtrip_and_torn_tail(tmp_path):
    path = tmp_path / "a.ckpt"
    log = RecordLog(path)
    log.append("k1", {"x": 1})
    log.append("k2", np.arange(3))
    log.close()
    good_size = path.stat().st_size
    with open(path, "ab") as fh:           # simulate a write cut short by a crash
        fh.write(b"\x10\x00\x00\x00\xde\xad\xbe\xefpartial")
    again = RecordLog(path)
    assert again.get("k1") == {"x": 1} and list(again.get("k2")) == [0, 1, 2]
    assert len(again) == 2
    assert path.stat().st_size == good_size  # damaged tail was cut off
    again.append("k3", "new")                # and appending works afterwards
    again.close()
    assert RecordLog(path).get("k3") == "new"


def test_record_log_stops_at_corrupt_record(tmp_path):
    path = tmp_path / "a.ckpt"
    log = RecordLog(path)
    log.append("k1", 1)
    log.append("k2", 2)
    log.close()
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0xFF                          # flip a bit in the last record
    path.write_bytes(bytes(raw))
    log2 = RecordLog(path)
    assert "k1" in log2 and "k2" not in log2


# --- store --------------------------------------------------------------------

def test_memo_computes_once_across_restarts(tmp_path):
    calls = []
    store = CheckpointStore(tmp_path)
    assert store.memo("s", "a", lambda: calls.append(1) or 42) == 42
    store.close()
    restarted = CheckpointStore(tmp_path)    # a new process after a reboot
    assert restarted.memo("s", "a", lambda: calls.append(1) or 99) == 42
    assert calls == [1]


def test_memo_saves_item_then_pauses(tmp_path):
    control = RunControl(tmp_path)
    store = CheckpointStore(tmp_path / "ck", control)
    control.request_pause()
    with pytest.raises(RunPaused):
        store.memo("s", "a", lambda: "value")
    assert store.recall("s", "a") == "value"  # the item was saved before pausing


def test_pause_file(tmp_path):
    control = RunControl(tmp_path)
    assert not control.pause_requested
    (tmp_path / "PAUSE").write_text("")
    with pytest.raises(RunPaused):
        control.raise_if_paused()
    control.clear_pause_file()
    control.raise_if_paused()


def test_run_paused_is_not_swallowed_by_except_exception():
    assert not issubclass(RunPaused, Exception)


def test_scope_and_drop(tmp_path):
    store = CheckpointStore(tmp_path)
    child = store.scope("run_2010/window_0000")
    child.remember("phase7", "k", 1)
    assert (tmp_path / "run_2010" / "window_0000" / "phase7.ckpt").exists()
    store.drop_scope("run_2010/window_0000")
    assert not (tmp_path / "run_2010" / "window_0000").exists()


def test_bind_refuses_changed_inputs(tmp_path):
    fp = {"schema": 1, "symbol": "XAUUSD", "config_sha1": "aaa", "files": {"csv": {"size": 5}}}
    CheckpointStore(tmp_path).bind(fp)
    CheckpointStore(tmp_path).bind(dict(fp))                       # same inputs: fine
    with pytest.raises(CheckpointMismatch, match="config_sha1"):
        CheckpointStore(tmp_path).bind({**fp, "config_sha1": "bbb"})


def test_null_checkpoint_just_computes():
    null = NullCheckpoint()
    assert null.memo("s", "k", lambda: 7) == 7
    assert null.scope("x") is null
    null.raise_if_paused()


# --- walk-forward window helper -----------------------------------------------

def test_checkpointed_window_skips_finished_and_pauses_after_saving(tmp_path):
    control = RunControl(tmp_path)
    store = CheckpointStore(tmp_path / "ck", control)
    calls = []

    def compute(window_store):
        calls.append(1)
        window_store.remember("phase7", "k", 1)   # per-condition state of the window
        return {"window_id": "w0", "n_accepted": 2}

    control.request_pause()
    with pytest.raises(RunPaused):
        _checkpointed_window(store, "w0", compute)
    assert not (tmp_path / "ck" / "w0").exists()  # finished window's scratch state is gone
    assert _checkpointed_window(store, "w0", compute) == {"window_id": "w0", "n_accepted": 2}
    assert calls == [1]


# --- lock and sessions --------------------------------------------------------

def test_run_lock_is_exclusive(tmp_path):
    first, second = RunLock(tmp_path / "x.lock"), RunLock(tmp_path / "x.lock")
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def _open(tmp_path, **kw):
    args = {"symbol": "XAUUSD", "timeframe": "M5"}
    return open_session(tmp_path, "XAUUSD", "M5", "run_pipeline", args, **kw)


def test_session_pause_then_resume_finds_the_run(tmp_path):
    first = _open(tmp_path)
    first.finish("paused")
    other = open_session(tmp_path, "EURUSD", "M5", "run_pipeline",
                         {"symbol": "EURUSD", "timeframe": "M5"})
    other.finish("paused")                      # a different pair must not be picked up
    second = _open(tmp_path, resume="")
    assert second.resumed and second.run_dir == first.run_dir
    info = read_run_info(second.run_dir)
    assert info["status"] == "running" and info["resume_count"] == 1
    second.finish("completed")
    assert not (second.run_dir / "checkpoint").exists()  # completed run drops its checkpoint


def test_session_resume_refuses_completed_and_running_elsewhere(tmp_path):
    done = _open(tmp_path)
    done.finish("completed")
    with pytest.raises(SystemExit, match="no unfinished"):
        _open(tmp_path, resume="")
    with pytest.raises(SystemExit, match="already completed"):
        _open(tmp_path, resume=done.run_dir.name)
    live = _open(tmp_path)                       # still holds its lock: "running" elsewhere
    with pytest.raises(SystemExit):
        _open(tmp_path, resume=live.run_dir.name)
    live.finish("paused")


def test_session_resume_picks_up_crashed_run(tmp_path):
    crashed = _open(tmp_path)
    crashed.lock.release()                       # process died: status stays "running"
    assert read_run_info(crashed.run_dir)["status"] == "running"
    again = _open(tmp_path, resume="")
    assert again.run_dir == crashed.run_dir
    again.finish("paused")


def test_session_resume_removes_stale_pause_file(tmp_path):
    first = _open(tmp_path)
    (first.run_dir / "PAUSE").write_text("")
    first.finish("paused")
    second = _open(tmp_path, resume="")
    assert not (second.run_dir / "PAUSE").exists()
    second.control.raise_if_paused()
    second.finish("paused")


# --- pause + resume of the real pipeline core ---------------------------------

def _synthetic_df(n=6000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="min")
    rsi_14 = rng.uniform(0, 100, n)
    ret = rng.normal(0, 0.3, n)
    ret[2:] += 0.5 * (rsi_14[:-2] < 30)
    close = 1800 + ret.cumsum()
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.05, n),
        "high": close + 0.3, "low": close - 0.3, "close": close,
        "atr_14": np.full(n, 1.0), "adx_14": rng.uniform(10, 40, n),
        "rsi_14": rsi_14, "rsi_7": rng.uniform(0, 100, n),
        "cci_20": rng.normal(0, 100, n), "mom_10": rng.normal(0, 3, n),
        "stoch_14_3_3_k": rng.uniform(0, 100, n),
        "ma_20_ema": close + rng.normal(0, 0.2, n),
    }, index=idx).astype(np.float32)


CONFIG = {
    "max_horizon": 10, "min_occurrence": 20, "min_freq_per_year": 1.0,
    "alpha": 0.05, "fdr_method": "fdr_bh",
    "wf_train_bars": 2000, "wf_test_bars": 500, "wf_step_bars": 500,
    "spread_pips": 30.0, "slippage_pips": 1.0, "pip_value": 0.01,
    "horizon_scan_min_bars": 1, "horizon_scan_max_bars": 8,
    "permutation_n": 20, "permutation_random_state": 7, "precheck_enabled": False,
    "top_n_atomic_for_combine": 8, "max_atoms_per_combo": 2,
    "include_ma_conditions": True,
    "rsi_thresholds": [30, 70], "cci_thresholds": [-100, 100],
    "mom_thresholds": [0], "stoch_thresholds": [20, 80],
    "gate_min_sim_trades": 5,
}


def _run(out_dir, checkpoint=None):
    return run_pipeline_core(
        df=_synthetic_df(), known_at_config_path=REPO / "config" / "known_at_delay.yaml",
        pipeline_config=dict(CONFIG), symbol="TEST", timeframe="M1",
        output_dir=out_dir, checkpoint=checkpoint,
    )


def test_pause_and_resume_gives_the_same_result_without_recomputing(tmp_path, monkeypatch):
    real = run_pipeline.validate_condition_walk_forward
    counter = {"n": 0}

    def counting(*a, **kw):
        counter["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(run_pipeline, "validate_condition_walk_forward", counting)

    baseline = _run(tmp_path / "baseline")
    total = counter["n"]
    assert total >= 4, "smoke data must give several conditions to interrupt between"

    # First session: pause right after the 2nd condition of Phase 7 is saved.
    counter["n"] = 0
    control = RunControl()
    store = CheckpointStore(tmp_path / "ck", control)
    original_remember = store.remember

    def remember_then_request_pause(stage, key, value):
        original_remember(stage, key, value)
        if stage == "phase7" and len(store._log("phase7")) == 2:
            control.request_pause()

    store.remember = remember_then_request_pause
    with pytest.raises(RunPaused):
        _run(tmp_path / "paused", checkpoint=store)
    assert counter["n"] == 2
    store.close()

    # Second session ("after a reboot"): new objects, same checkpoint folder.
    counter["n"] = 0
    resumed = _run(tmp_path / "paused", checkpoint=CheckpointStore(tmp_path / "ck", RunControl()))
    assert counter["n"] == total - 2               # the 2 saved conditions were not redone

    def summary(result):
        return sorted(
            (str(e["condition"]), e["direction"], e["optimal_holding_bars"],
             e["trade_sim"].n_trades, round(float(e["trade_sim"].expectancy_r), 9),
             e["permutation"].get("p_value"), bool(e["gate_passed"]))
            for e in result["validated_edges"]
        )

    assert summary(resumed) == summary(baseline)
    assert (pd.read_csv(tmp_path / "paused" / "STRATEGY_GATE_RESULTS.csv")
            .equals(pd.read_csv(tmp_path / "baseline" / "STRATEGY_GATE_RESULTS.csv")))


# --- pause + resume of a whole walk-forward run (legacy bar-count windows) -----

def _write_wf_inputs(tmp_path):
    import yaml
    df = _synthetic_df(n=6000).reset_index().rename(columns={"index": "time"})
    df["tick_volume"] = 100
    csv_path = tmp_path / "XAUUSD_M5.csv"
    df.to_csv(csv_path, index=False)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "known_at_delay.yaml").write_text(
        (REPO / "config" / "known_at_delay.yaml").read_text())
    cfg = {**CONFIG, "meta_wf_train_bars": 3000, "meta_wf_test_bars": 1000,
           "meta_wf_step_bars": 1000, "meta_wf_test_min_trades": 1}
    (config_dir / "pipeline_config.yaml").write_text(yaml.safe_dump(cfg))
    return csv_path, config_dir


def test_walkforward_pause_and_resume_matches_uninterrupted_run(tmp_path):
    from scripts.run_walkforward_pipeline import run_walkforward_pipeline
    csv_path, config_dir = _write_wf_inputs(tmp_path)

    def run(out, checkpoint=None):
        return run_walkforward_pipeline(
            csv_path=csv_path, symbol="XAUUSD", timeframe="M5", config_dir=config_dir,
            output_dir=out, checkpoint=checkpoint)

    baseline = run(tmp_path / "baseline")
    assert len(baseline) >= 3

    control = RunControl()
    store = CheckpointStore(tmp_path / "ck", control)
    original_remember = store.remember

    def remember_then_pause(stage, key, value):
        original_remember(stage, key, value)
        if stage == "windows":
            control.request_pause()           # pause as soon as the first window is saved

    store.remember = remember_then_pause
    with pytest.raises(RunPaused):
        run(tmp_path / "paused", checkpoint=store)
    store.close()
    assert len(RecordLog(tmp_path / "ck" / "windows.ckpt")) == 1

    resumed = run(tmp_path / "paused", checkpoint=CheckpointStore(tmp_path / "ck", RunControl()))
    assert resumed == baseline                # same summaries for every window, in order
    assert (tmp_path / "paused" / "WALKFORWARD_SUMMARY.md").read_text() \
        == (tmp_path / "baseline" / "WALKFORWARD_SUMMARY.md").read_text()


def test_cli_pause_then_resume_flag(tmp_path, monkeypatch):
    """The real main(): a paused run ends with status 'paused', and the same command
    plus --resume finishes it (ranker included) and removes the checkpoint."""
    import sys
    from edge_research.checkpoint import store as store_module
    from scripts import run_walkforward_pipeline as wf_script

    csv_path, config_dir = _write_wf_inputs(tmp_path)
    out = tmp_path / "out"
    argv = ["run_walkforward_pipeline.py", str(csv_path), "--symbol", "XAUUSD",
            "--timeframe", "M5", "--config-dir", str(config_dir), "--output-dir", str(out),
            "--no-mt5-backtest"]

    original = store_module.CheckpointStore.remember

    def remember_then_pause(self, stage, key, value):
        original(self, stage, key, value)
        if stage == "windows":
            self.control.request_pause()

    monkeypatch.setattr(store_module.CheckpointStore, "remember", remember_then_pause)
    monkeypatch.setattr(sys, "argv", argv)
    wf_script.main()                                   # pauses itself, exit code 0
    run_dir = next(p for p in out.iterdir() if p.is_dir())
    assert read_run_info(run_dir)["status"] == "paused"
    assert (run_dir / "checkpoint").is_dir()

    monkeypatch.setattr(store_module.CheckpointStore, "remember", original)
    monkeypatch.setattr(sys, "argv", argv + ["--resume"])
    wf_script.main()
    info = read_run_info(run_dir)
    assert info["status"] == "completed" and info["resume_count"] == 1
    assert not (run_dir / "checkpoint").exists()
    assert (run_dir / "WALKFORWARD_SUMMARY.md").exists()
    assert len([p for p in out.iterdir() if p.is_dir()]) == 1   # resumed in place, no new folder


def test_cli_single_run_pause_inside_phase7_then_resume(tmp_path, monkeypatch):
    """Same for scripts/run_pipeline.py, paused between two conditions of Phase 7."""
    import sys
    import yaml
    from edge_research.checkpoint import store as store_module

    csv_path, config_dir = _write_wf_inputs(tmp_path)
    (config_dir / "pipeline_config.yaml").write_text(yaml.safe_dump(CONFIG))
    out = tmp_path / "out"
    argv = ["run_pipeline.py", str(csv_path), "--symbol", "XAUUSD", "--timeframe", "M5",
            "--config-dir", str(config_dir), "--output-dir", str(out), "--no-mt5-backtest"]

    original = store_module.CheckpointStore.remember

    def remember_then_pause(self, stage, key, value):
        original(self, stage, key, value)
        if stage == "phase7":
            self.control.request_pause()

    monkeypatch.setattr(store_module.CheckpointStore, "remember", remember_then_pause)
    monkeypatch.setattr(sys, "argv", argv)
    run_pipeline.main()
    run_dir = next(p for p in out.iterdir() if p.is_dir())
    assert read_run_info(run_dir)["status"] == "paused"
    assert len(RecordLog(run_dir / "checkpoint" / "phase7.ckpt")) == 1
    assert not (run_dir / "STRATEGY_GATE_RESULTS.csv").exists()

    monkeypatch.setattr(store_module.CheckpointStore, "remember", original)
    monkeypatch.setattr(sys, "argv", argv + ["--resume"])
    run_pipeline.main()
    assert read_run_info(run_dir)["status"] == "completed"
    assert (run_dir / "STRATEGY_GATE_RESULTS.csv").exists()
    assert (run_dir / "ranker_sort_top.csv").exists()
