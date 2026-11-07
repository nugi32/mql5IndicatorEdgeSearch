"""Tests for per-invocation run directories (parallel-run isolation)."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from edge_research.utils.run_dir import (
    RUN_INFO_FILENAME,
    attach_run_log,
    detach_run_log,
    finish_run,
    resolve_output_dir,
    sanitize_name,
    start_run,
)


def test_auto_names_are_unique_under_concurrency(tmp_path):
    # 16 threads share one PID and (usually) one second: only the atomic
    # mkdir + suffix retry keeps them apart.
    with ThreadPoolExecutor(max_workers=16) as ex:
        dirs = list(ex.map(lambda _: resolve_output_dir(tmp_path, "XAUUSD", "H1"), range(16)))
    assert len({str(d) for d in dirs}) == 16
    assert all(d.is_dir() and d.parent == tmp_path for d in dirs)


def test_explicit_run_name_and_collision_refused(tmp_path):
    d = resolve_output_dir(tmp_path, "XAUUSD", "H1", run_name="my run/1")
    assert d.name == sanitize_name("my run/1") and d.parent == tmp_path
    (d / "x.txt").write_text("keep me")
    with pytest.raises(FileExistsError):
        resolve_output_dir(tmp_path, "XAUUSD", "H1", run_name="my run/1")
    assert (d / "x.txt").read_text() == "keep me"


def test_empty_existing_run_name_is_reusable(tmp_path):
    (tmp_path / "a").mkdir()
    assert resolve_output_dir(tmp_path, "X", "H1", run_name="a") == tmp_path / "a"


def test_flat_mode_uses_base_dir(tmp_path):
    out = tmp_path / "out"
    assert resolve_output_dir(out, "X", "H1", flat=True) == out
    assert out.is_dir()


def test_run_info_lifecycle(tmp_path):
    start_run(tmp_path, "run_pipeline", {"symbol": "XAUUSD"})
    info = json.loads((tmp_path / RUN_INFO_FILENAME).read_text())
    assert info["status"] == "running" and info["args"]["symbol"] == "XAUUSD"
    finish_run(tmp_path, "failed", error="boom")
    info = json.loads((tmp_path / RUN_INFO_FILENAME).read_text())
    assert info["status"] == "failed" and info["error"] == "boom"
    assert info["args"]["symbol"] == "XAUUSD" and "finished_at" in info


def test_run_log_receives_messages(tmp_path):
    h = attach_run_log(tmp_path)
    try:
        logging.getLogger("edge_research.test").warning("hello run log")
    finally:
        detach_run_log(h)
    assert "hello run log" in (tmp_path / "run.log").read_text()
    logging.getLogger("edge_research.test").warning("after detach")
    assert "after detach" not in (tmp_path / "run.log").read_text()


def test_list_runs(tmp_path):
    from scripts.list_runs import collect_runs
    a = resolve_output_dir(tmp_path, "XAUUSD", "H1", run_name="a")
    start_run(a, "run_pipeline", {"symbol": "XAUUSD", "timeframe": "H1"})
    finish_run(a, "completed")
    (tmp_path / "junk").mkdir()
    rows = collect_runs(tmp_path)
    assert [r["run"] for r in rows] == ["a"] and rows[0]["status"] == "completed"
