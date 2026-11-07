"""
Fingerprint of everything a saved checkpoint depends on (data, config, symbol).

A checkpoint is only valid for the exact inputs it was made from. Resuming with
a changed CSV or config would silently mix old and new results, so the store
refuses (see CheckpointStore.bind).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

# Bump when the layout of what is pickled into the checkpoint changes.
SCHEMA_VERSION = 1

_SAMPLE_BYTES = 1 << 20  # 1 MiB from the start and from the end of a big file


def file_signature(path: Optional[str | Path]) -> Optional[Dict[str, Any]]:
    """Size plus a hash of the first and last MiB: cheap even for multi-GB CSVs."""
    if not path:
        return None
    p = Path(path)
    size = p.stat().st_size
    digest = hashlib.sha1()
    with p.open("rb") as fh:
        digest.update(fh.read(_SAMPLE_BYTES))
        if size > 2 * _SAMPLE_BYTES:
            fh.seek(size - _SAMPLE_BYTES)
            digest.update(fh.read(_SAMPLE_BYTES))
    return {"size": size, "sample_sha1": digest.hexdigest()}


def build_fingerprint(
    symbol: str,
    timeframe: str,
    pipeline_config: dict,
    files: Dict[str, Optional[str | Path]],
    **extras: Any,
) -> Dict[str, Any]:
    """
    ``pipeline_config`` is the config AFTER the MT5 tester settings were merged
    in, so a change in either file changes the fingerprint. ``files`` maps a
    label to a path (CSV, calendar CSV, known_at yaml, ...).
    """
    config_blob = json.dumps(pipeline_config, sort_keys=True, default=str)
    return {
        "schema": SCHEMA_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "config_sha1": hashlib.sha1(config_blob.encode("utf-8")).hexdigest(),
        "files": {label: file_signature(path) for label, path in files.items()},
        **extras,
    }
