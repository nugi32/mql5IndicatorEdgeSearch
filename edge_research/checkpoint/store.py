"""
Crash-safe checkpoint store.

Results are saved per *item* (a finished window, a validated condition, ...)
in an append-only log, one log per stage. Each record carries its length and a
CRC, and is flushed to disk before the run goes on. So:

    * a kill, power loss or reboot loses at most the item being computed;
    * a record torn by the crash is detected and ignored on the next start;
    * nothing is ever rewritten, so there is no half-updated file.

Items are looked up by a *key* (e.g. the condition text), never by position.
If a resumed run produces different candidates than before, unknown keys are
just recomputed; a cached value is only ever reused for the same key.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from edge_research.checkpoint.control import RunControl

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("<II")  # payload length, CRC32 of the payload
FINGERPRINT_FILENAME = "fingerprint.json"


class CheckpointMismatch(RuntimeError):
    """The saved checkpoint was made from different data/config than this run uses."""


class RecordLog:
    """Append-only file of pickled (key, value) records."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._items: Dict[str, Any] = {}
        self._fh = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        pos = 0
        while pos + _HEADER.size <= len(data):
            length, crc = _HEADER.unpack_from(data, pos)
            start = pos + _HEADER.size
            end = start + length
            if end > len(data) or zlib.crc32(data[start:end]) != crc:
                break
            try:
                key, value = pickle.loads(data[start:end])
            except Exception:
                break
            self._items[key] = value
            pos = end
        if pos < len(data):
            # Torn tail from a crash: cut it off so new records start on a clean boundary.
            logger.warning(f"{self.path.name}: ignoring {len(data) - pos} damaged trailing bytes")
            with open(self.path, "r+b") as fh:
                fh.truncate(pos)

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: str, default: Any = None) -> Any:
        return self._items.get(key, default)

    def append(self, key: str, value: Any) -> None:
        payload = pickle.dumps((key, value), protocol=pickle.HIGHEST_PROTOCOL)
        if self._fh is None:
            self._fh = open(self.path, "ab")
        self._fh.write(_HEADER.pack(len(payload), zlib.crc32(payload)) + payload)
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._items[key] = value

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class CheckpointStore:
    """Checkpoints of one run folder. ``scope()`` gives a nested store (one per window)."""

    def __init__(self, root: Path, control: Optional[RunControl] = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.control = control or RunControl()
        self._logs: Dict[str, RecordLog] = {}
        self._children: Dict[str, "CheckpointStore"] = {}

    # -- items ---------------------------------------------------------------

    def _log(self, stage: str) -> RecordLog:
        if stage not in self._logs:
            self._logs[stage] = RecordLog(self.root / f"{stage}.ckpt")
        return self._logs[stage]

    def recall(self, stage: str, key: str, default: Any = None) -> Any:
        """Saved value for ``key`` in ``stage``, or ``default``."""
        return self._log(stage).get(key, default)

    def remember(self, stage: str, key: str, value: Any) -> None:
        """Save a value. A checkpoint problem must never fail the run itself."""
        try:
            self._log(stage).append(key, value)
        except Exception:
            logger.warning(f"Could not save checkpoint {stage}/{key[:60]}; "
                           f"the run continues without it", exc_info=True)

    def memo(self, stage: str, key: str, compute: Callable[[], Any]) -> Any:
        """
        Return the saved value for ``key``; otherwise compute it, save it, and
        honour a pending pause request (the item is already safe on disk).
        """
        log = self._log(stage)
        if key in log:
            return log.get(key)
        value = compute()
        self.remember(stage, key, value)
        self.control.raise_if_paused()
        return value

    def raise_if_paused(self) -> None:
        self.control.raise_if_paused()

    # -- nesting -------------------------------------------------------------

    def scope(self, name: str) -> "CheckpointStore":
        if name not in self._children:
            self._children[name] = CheckpointStore(self.root / name, self.control)
        return self._children[name]

    def drop_scope(self, name: str) -> None:
        """Delete a finished scope (its items are no longer needed)."""
        child = self._children.pop(name, None)
        if child is not None:
            child.close()
        shutil.rmtree(self.root / name, ignore_errors=True)

    # -- validity ------------------------------------------------------------

    def bind(self, fingerprint: Dict[str, Any]) -> None:
        """
        Tie this store to the inputs of the run. First call saves the
        fingerprint; later calls (a resume) must match it exactly.
        """
        path = self.root / FINGERPRINT_FILENAME
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            current = json.loads(json.dumps(fingerprint, default=str))
            changed = sorted(k for k in set(saved) | set(current) if saved.get(k) != current.get(k))
            if changed:
                raise CheckpointMismatch(
                    f"Cannot resume: {', '.join(changed)} changed since this run started "
                    f"(data file, config, symbol or timeframe). Start a new run instead, or "
                    f"restore the original inputs."
                )
            return
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(fingerprint, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)

    def close(self) -> None:
        for log in self._logs.values():
            log.close()
        for child in self._children.values():
            child.close()

    def clear(self) -> None:
        """Delete the whole checkpoint (used when a run completed)."""
        self.close()
        shutil.rmtree(self.root, ignore_errors=True)


class NullCheckpoint:
    """Same interface, saves nothing: the default, so existing callers behave as before."""

    def recall(self, stage: str, key: str, default: Any = None) -> Any:
        return default

    def remember(self, stage: str, key: str, value: Any) -> None:
        pass

    def memo(self, stage: str, key: str, compute: Callable[[], Any]) -> Any:
        return compute()

    def raise_if_paused(self) -> None:
        pass

    def scope(self, name: str) -> "NullCheckpoint":
        return self

    def drop_scope(self, name: str) -> None:
        pass

    def bind(self, fingerprint: Dict[str, Any]) -> None:
        pass


def as_checkpoint(checkpoint: Optional[CheckpointStore]) -> "CheckpointStore | NullCheckpoint":
    return checkpoint if checkpoint is not None else NullCheckpoint()
