"""Thin CLI entry helper for deprecated personal-codename console scripts.

DEPRECATED: remove in rename+1.
"""

from __future__ import annotations

import runpy
import sys
from typing import Callable

from .component_aliases import deprecate


def run_deprecated_cli(legacy: str, canonical_main: Callable[[], None] | None = None, *, module: str | None = None) -> None:
    """Warn and dispatch to the canonical CLI main or module."""
    deprecate(legacy)
    if canonical_main is not None:
        canonical_main()
        return
    if module is not None:
        sys.argv[0] = module
        runpy.run_module(module, run_name="__main__")
        return
    raise RuntimeError("canonical_main or module required")
