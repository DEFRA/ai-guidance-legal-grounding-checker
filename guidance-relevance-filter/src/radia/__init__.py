"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'radia' is deprecated; use 'guidance_relevance_filter'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from guidance_relevance_filter import *  # noqa: F403
