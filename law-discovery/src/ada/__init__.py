"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'ada' is deprecated; use 'law_discovery'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from law_discovery import *  # noqa: F403
