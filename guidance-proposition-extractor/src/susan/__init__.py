"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'susan' is deprecated; use 'guidance_proposition_extractor'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from guidance_proposition_extractor import *  # noqa: F403
