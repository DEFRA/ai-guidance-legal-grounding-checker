"""Isolated compatibility layer for legacy personal component codenames.

DEPRECATED: remove in rename+1. Canonical packages must not import from legacy-named
modules; this package may import canonical implementations.
"""

from .component_aliases import (
    ALIAS_REMOVAL_RELEASE,
    COMPONENT_BY_LEGACY,
    COMPONENT_BY_SLUG,
    deprecate,
    resolve_env,
    resolve_producer_component,
    warn_legacy_name,
)

__all__ = [
    "ALIAS_REMOVAL_RELEASE",
    "COMPONENT_BY_LEGACY",
    "COMPONENT_BY_SLUG",
    "deprecate",
    "resolve_env",
    "resolve_producer_component",
    "warn_legacy_name",
]
