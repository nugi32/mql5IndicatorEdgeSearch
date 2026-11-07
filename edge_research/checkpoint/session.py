"""
Start a new run, or pick up a paused one, for both pipeline scripts.

A run folder is resumable when its RUN_INFO.json says it did not complete
(paused, interrupted, failed, stopped by the memory guard, or "running" but the
process is gone, e.g. after a reboot) and nobody holds its lock.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from edge_research.checkpoint.control import RunControl
from edge_research.checkpoint.lock import RunLock
from edge_research.checkpoint.store import CheckpointStore
from edge_research.utils.run_dir import (
    RUN_INFO_FILENAME,
    finish_run,
    read_run_info,
    resolve_output_dir,
    start_run,
    write_run_info,
)

logger = logging.getLogger(__name__)

CHECKPOINT_DIRNAME = "checkpoint"
LOCK_FILENAME = "RUN.lock"
# "running" is included: a crashed or rebooted run never got to write a final status.
RESUMABLE_STATUSES = {"paused", "interrupted", "failed", "stopped_by_memory_guard", "running"}


@dataclass
class RunSession:
    run_dir: Path
    store: CheckpointStore
    control: RunControl
    lock: RunLock
    resumed: bool

    def finish(self, status: str, error: Optional[str] = None) -> None:
        """Write the final status, drop the checkpoint of a completed run, release the lock."""
        finish_run(self.run_dir, status, error=error)
        if status == "completed":
            self.store.clear()
        else:
            self.store.close()
        self.lock.release()

    def resume_hint(self) -> str:
        return f"Resume later with the same command plus: --resume \"{self.run_dir}\""


def _matching_run(info: Dict[str, Any], script: str, symbol: str, timeframe: str) -> bool:
    args = info.get("args", {})
    return (info.get("script") == script and args.get("symbol") == symbol
            and args.get("timeframe") == timeframe)


def _find_resumable(base_dir: Path, script: str, symbol: str,
                    timeframe: str) -> Tuple[Path, RunLock]:
    """Newest unfinished run of this script/symbol/timeframe that is not running right now."""
    candidates = []
    for child in base_dir.iterdir() if base_dir.is_dir() else []:
        info = read_run_info(child)
        if (info and info.get("status") in RESUMABLE_STATUSES
                and _matching_run(info, script, symbol, timeframe)):
            candidates.append((info.get("started_at", ""), child))
    for _, child in sorted(candidates, reverse=True):
        lock = RunLock(child / LOCK_FILENAME)
        if lock.acquire():
            return child, lock
        logger.info(f"Skipping {child.name}: another process is running it")
    raise SystemExit(
        f"--resume: no unfinished {script} run for {symbol} {timeframe} under {base_dir}. "
        f"List runs with: python scripts/list_runs.py {base_dir}"
    )


def _explicit_run(value: str, base_dir: Path, script: str, symbol: str,
                  timeframe: str) -> Tuple[Path, RunLock]:
    path = Path(value)
    if not path.is_dir():
        path = base_dir / value
    info = read_run_info(path) if path.is_dir() else None
    if info is None:
        raise SystemExit(f"--resume: {value} is not a run folder (no {RUN_INFO_FILENAME}).")
    if info.get("status") == "completed":
        raise SystemExit(f"--resume: {path.name} already completed; nothing to resume.")
    if not _matching_run(info, script, symbol, timeframe):
        raise SystemExit(f"--resume: {path.name} was started by a different script, "
                         f"symbol or timeframe than this command.")
    lock = RunLock(path / LOCK_FILENAME)
    if not lock.acquire():
        raise SystemExit(f"--resume: {path.name} is running in another process right now.")
    return path, lock


def open_session(
    output_dir: str | Path,
    symbol: str,
    timeframe: str,
    script: str,
    args: Dict[str, Any],
    resume: Optional[str] = None,
    run_name: Optional[str] = None,
    flat: bool = False,
) -> RunSession:
    """
    ``resume`` is None for a new run, ``""`` to resume the newest unfinished
    run of this script/symbol/timeframe, or a run folder name/path.
    """
    base_dir = Path(output_dir)
    if resume is None:
        run_dir = resolve_output_dir(base_dir, symbol, timeframe, run_name=run_name, flat=flat)
        lock = RunLock(run_dir / LOCK_FILENAME)
        if not lock.acquire():  # cannot happen for a fresh folder, but never run unlocked
            raise SystemExit(f"{run_dir} is locked by another process.")
        start_run(run_dir, script, args)
        resumed = False
    else:
        if flat:
            run_dir, lock = _explicit_run(str(base_dir), base_dir, script, symbol, timeframe)
        elif resume:
            run_dir, lock = _explicit_run(resume, base_dir, script, symbol, timeframe)
        else:
            run_dir, lock = _find_resumable(base_dir, script, symbol, timeframe)
        previous = read_run_info(run_dir) or {}
        write_run_info(
            run_dir, status="running", pid=os.getpid(), finished_at="", error="",
            resumed_at=datetime.now().isoformat(timespec="seconds"),
            resume_count=int(previous.get("resume_count", 0)) + 1,
        )
        resumed = True
        logger.info(f"Resuming run {run_dir.name} (resume #{previous.get('resume_count', 0) + 1})")

    control = RunControl(run_dir)
    if resumed:
        control.clear_pause_file()
    store = CheckpointStore(run_dir / CHECKPOINT_DIRNAME, control)
    return RunSession(run_dir=run_dir, store=store, control=control, lock=lock, resumed=resumed)
