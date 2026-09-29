"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'anna' is deprecated; use 'match_adjudicator'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from match_adjudicator import *  # noqa: F403
