"""
Per-invocation run directories, so several pipeline processes can run side by
side (one per terminal) without overwriting each other's results.

Layout produced by default (``--output-dir output_walkforward``)::

    output_walkforward/
        20261025_143012_XAUUSD_H1_p4242/     <- one folder per invocation
            RUN_INFO.json                    <- status, args, timings
            run.log                          <- full log of this run only
            storage/ ...                     <- parquet cache
            WALKFORWARD_SUMMARY.md
            run_2015/window_0001/ ...

``--output-dir`` therefore acts as a *parent* folder. ``--flat-output`` keeps
the legacy behaviour (write straight into ``--output-dir``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RUN_INFO_FILENAME = "RUN_INFO.json"
RUN_LOG_FILENAME = "run.log"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_name(name: str) -> str:
    """Make a string safe to use as a single folder name."""
    cleaned = _SAFE_NAME.sub("_", str(name)).strip("._")
    return cleaned or "run"


def auto_run_name(symbol: str, timeframe: str, now: Optional[datetime] = None) -> str:
    """
    Build a unique-looking run name: timestamp + symbol + timeframe + PID.
    The PID makes two terminals started within the same second differ.
    """
    now = now or datetime.now()
    return sanitize_name(
        f"{now:%Y%m%d_%H%M%S}_{symbol}_{timeframe}_p{os.getpid()}"
    )


def resolve_output_dir(
    base_dir: str | Path,
    symbol: str,
    timeframe: str,
    run_name: Optional[str] = None,
    flat: bool = False,
) -> Path:
    """
    Decide (and create) the directory a single invocation writes into.

    Parameters
    ----------
    base_dir : parent folder given by ``--output-dir``.
    run_name : explicit sub-folder name. Refused if it already exists and is
        non-empty, so a re-used name can never silently overwrite results.
    flat : legacy mode, use ``base_dir`` itself (no isolation).

    The folder is created with ``mkdir(exist_ok=False)``, which is atomic on
    the filesystem, so two processes can never claim the same auto-named
    folder: on a clash the loser appends ``_2``, ``_3``, ...
    """
    base_dir = Path(base_dir)
    if flat:
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    base_dir.mkdir(parents=True, exist_ok=True)

    if run_name:
        target = base_dir / sanitize_name(run_name)
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(
                f"Run folder already exists and is not empty: {target}. "
                f"Pick another --run-name, or omit it to get an automatic unique name."
            )
        target.mkdir(parents=True, exist_ok=True)
        return target

    stem = auto_run_name(symbol, timeframe)
    for attempt in range(1, 1000):
        candidate = base_dir / (stem if attempt == 1 else f"{stem}_{attempt}")
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not allocate a unique run folder under {base_dir}")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_run_info(run_dir: Path, **fields: Any) -> Dict[str, Any]:
    """
    Merge ``fields`` into RUN_INFO.json (created if missing) and return the
    merged dict. Written via a temp file + rename so a reader (e.g.
    list_runs.py) never sees a half-written file.
    """
    path = Path(run_dir) / RUN_INFO_FILENAME
    info: Dict[str, Any] = {}
    if path.exists():
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
    info.update(fields)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return info


def start_run(run_dir: Path, script: str, args: Dict[str, Any]) -> None:
    """Record that a run has started."""
    write_run_info(
        run_dir,
        status="running",
        script=script,
        args=args,
        pid=os.getpid(),
        host=socket.gethostname(),
        started_at=_now_iso(),
        command=" ".join(sys.argv),
    )


def finish_run(run_dir: Path, status: str, error: Optional[str] = None) -> None:
    """Record the final state: completed / failed / stopped_by_memory_guard."""
    fields: Dict[str, Any] = {"status": status, "finished_at": _now_iso()}
    if error:
        fields["error"] = error
    write_run_info(run_dir, **fields)


def attach_run_log(run_dir: Path, level: int = logging.INFO) -> logging.Handler:
    """
    Mirror all logging of this process into <run_dir>/run.log. The console
    output is untouched; the file only ever contains this run's messages.
    """
    handler = logging.FileHandler(Path(run_dir) / RUN_LOG_FILENAME, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)
    return handler


def detach_run_log(handler: logging.Handler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()
