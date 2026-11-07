"""
Pause requests for long runs.

A run can be paused three ways, all handled the same way: the run keeps going
until the next *item boundary* (a finished window, or a finished condition
inside a window), saves that item, and then stops cleanly by raising
``RunPaused``. Nothing is lost and the run can be resumed later with
``--resume``.

    * Ctrl+C once (or SIGTERM / SIGBREAK): graceful pause.
    * Ctrl+C a second time: stop immediately (the current item is lost).
    * Create an empty file named PAUSE in the run folder: graceful pause
      without touching the terminal.
"""

from __future__ import annotations

import contextlib
import logging
import signal
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

PAUSE_FILENAME = "PAUSE"


class RunPaused(BaseException):
    """
    Raised at a safe boundary after a pause was requested.

    Derives from BaseException (like KeyboardInterrupt) on purpose, so that no
    ``except Exception`` block deep inside the pipeline can swallow it.
    """


class RunControl:
    """Tracks whether the user asked this run to pause."""

    def __init__(self, run_dir: Optional[Path] = None):
        self._pause_file = Path(run_dir) / PAUSE_FILENAME if run_dir else None
        self._requested = False
        self._signals_seen = 0

    @property
    def pause_requested(self) -> bool:
        if self._requested:
            return True
        return bool(self._pause_file and self._pause_file.exists())

    def request_pause(self) -> None:
        self._requested = True

    def raise_if_paused(self) -> None:
        if self.pause_requested:
            raise RunPaused("pause requested")

    def clear_pause_file(self) -> None:
        """Remove a leftover PAUSE file so a resumed run does not pause at once."""
        if self._pause_file and self._pause_file.exists():
            try:
                self._pause_file.unlink()
                logger.info(f"Removed leftover {PAUSE_FILENAME} file")
            except OSError:
                logger.warning(f"Could not remove {self._pause_file}; delete it by hand")

    def _on_signal(self, signum, frame) -> None:
        self._signals_seen += 1
        if self._signals_seen == 1:
            self._requested = True
            logger.warning(
                "Pause requested: the run stops after the current item is saved. "
                "Press Ctrl+C again to stop immediately (the current item is lost)."
            )
        else:
            raise KeyboardInterrupt

    @contextlib.contextmanager
    def handle_signals(self) -> Iterator["RunControl"]:
        """Turn Ctrl+C / SIGTERM / SIGBREAK into a graceful pause while active."""
        previous = {}
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK exists on Windows only
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                previous[sig] = signal.signal(sig, self._on_signal)
            except ValueError:  # not the main thread: leave default handling
                logger.debug(f"Cannot install handler for {name} outside the main thread")
        try:
            yield self
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
