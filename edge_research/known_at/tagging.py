"""
Phase 2: Known-At Tagging

Determine the availability delay (in bars) for each indicator column.
Supports nonzero delays for future Tier 2 indicators without code changes
(only YAML config updates needed).
"""

import logging
import re
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger(__name__)


class KnownAtTagger:
    """
    Manages known-at delays for indicator columns based on YAML config.
