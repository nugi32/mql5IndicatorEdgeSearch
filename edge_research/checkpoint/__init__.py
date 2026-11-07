"""Pause / resume support for long pipeline runs (see edge_research/checkpoint/store.py)."""

from edge_research.checkpoint.control import RunControl, RunPaused
from edge_research.checkpoint.fingerprint import build_fingerprint
from edge_research.checkpoint.lock import RunLock
from edge_research.checkpoint.session import RunSession, open_session
from edge_research.checkpoint.store import (
    CheckpointMismatch,
    CheckpointStore,
    NullCheckpoint,
    as_checkpoint,
)

__all__ = [
    "CheckpointMismatch", "CheckpointStore", "NullCheckpoint", "RunControl", "RunLock",
    "RunPaused", "RunSession", "as_checkpoint", "build_fingerprint", "open_session",
]
