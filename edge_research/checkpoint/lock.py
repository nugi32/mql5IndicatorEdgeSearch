"""
One process per run folder.

Uses an OS-level file lock that the operating system releases by itself when
the process ends, crashes, or the PC reboots. So there is no stale lock to
clean up, and no PID check (os.kill(pid, 0) would kill the process on Windows).
"""

from __future__ import annotations

import os
from pathlib import Path


class RunLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = None

    def acquire(self) -> bool:
        """Try to take the lock without waiting. False if another process holds it."""
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None
