"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'beatrice' is deprecated; use 'proposition_matcher'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from proposition_matcher import *  # noqa: F403
