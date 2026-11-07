"""
Memory watchdog + release helpers.

WHY THIS EXISTS
---------------
The pipeline holds one boolean mask (1 byte * window_bars) per candidate
condition, plus a (bars x max_horizon) forward matrix, plus the full
multi-million-row dataframe.  On M1 data that adds up to many GB, and when
the OS starts swapping the whole PC freezes long before Python raises
MemoryError.  This module gives the pipeline a cooperative "circuit breaker":
it raises `MemoryBudgetExceeded` (a MemoryError subclass) while the machine
is still responsive, so the run stops cleanly with a clear message and the
per-window results already written to disk are preserved.

Nothing here changes any numerical result.
"""

import ctypes
import gc
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_GB = 1024.0 ** 3


class MemoryBudgetExceeded(MemoryError):
    """Raised by MemoryGuard.check() when a configured limit is crossed."""


def rss_gb() -> Optional[float]:
    """Resident set size of this process in GB (None if unavailable)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024 / _GB
    except OSError:
        pass
    try:
        import psutil  # optional
        return psutil.Process(os.getpid()).memory_info().rss / _GB
    except Exception:
        return None


def available_gb() -> Optional[float]:
    """System-wide memory that can be allocated without swapping, in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024 / _GB
    except OSError:
        pass
    try:
        import psutil  # optional
        return psutil.virtual_memory().available / _GB
    except Exception:
        return None


def release_memory() -> None:
    """
    gc.collect() + ask glibc to hand freed heap pages back to the OS.

    Freed numpy arrays of ~1 MB (one condition mask on M1 data) are served
    from the malloc heap, not mmap, so without malloc_trim the process RSS
    only ratchets upward across walk-forward windows even though Python
    has released the objects.
    """
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass  # non-glibc platform: nothing to do


def log_memory(tag: str) -> None:
    r, a = rss_gb(), available_gb()
    parts = []
    if r is not None:
        parts.append(f"rss={r:.2f}GB")
    if a is not None:
        parts.append(f"system_available={a:.2f}GB")
    if parts:
        logger.info(f"[MEM] {tag}: " + " ".join(parts))


class MemoryGuard:
    """
    Parameters
    ----------
    max_rss_gb : float, optional
        Abort when this process' RSS exceeds this many GB.
    min_free_gb : float, optional
        Abort when system-wide available memory drops below this many GB.
    min_interval_s : float
        check() is throttled so calling it inside hot loops is cheap.
    """

    def __init__(self, max_rss_gb: Optional[float] = None,
                 min_free_gb: Optional[float] = 2.0,
                 min_interval_s: float = 1.0):
        self.max_rss_gb = max_rss_gb
        self.min_free_gb = min_free_gb
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def check(self, tag: str = "", force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last) < self.min_interval_s:
            return
        self._last = now

        if self.max_rss_gb is not None:
            r = rss_gb()
            if r is not None and r > self.max_rss_gb:
                release_memory()
                r = rss_gb()
                if r is not None and r > self.max_rss_gb:
                    raise MemoryBudgetExceeded(
                        f"Process RSS {r:.2f}GB exceeds --max-rss-gb={self.max_rss_gb} "
                        f"(at: {tag}). Stopping cleanly before the PC starts swapping."
                    )
        if self.min_free_gb is not None:
            a = available_gb()
            if a is not None and a < self.min_free_gb:
                release_memory()
                a = available_gb()
                if a is not None and a < self.min_free_gb:
                    raise MemoryBudgetExceeded(
                        f"System available memory {a:.2f}GB is below --min-free-gb="
                        f"{self.min_free_gb} (process rss={rss_gb()}GB, at: {tag}). "
                        f"Stopping cleanly before the PC starts swapping."
                    )


_guard: Optional[MemoryGuard] = None


def set_guard(guard: Optional[MemoryGuard]) -> None:
    global _guard
    _guard = guard


def check_memory(tag: str = "", force: bool = False) -> None:
    """No-op unless a guard was installed with set_guard()."""
    if _guard is not None:
        _guard.check(tag, force=force)
