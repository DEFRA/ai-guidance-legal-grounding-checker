"""DEPRECATED import shim — remove in rename+1. COMPAT_LEGACY_NAME"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Importing 'esther' is deprecated; use 'audit_assembler'. Aliases removed in rename+1.",
    DeprecationWarning,
    stacklevel=2,
)

from audit_assembler import *  # noqa: F403
