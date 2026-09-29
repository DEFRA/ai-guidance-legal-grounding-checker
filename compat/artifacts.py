"""Dual-read helpers for renamed handoff artifacts.

DEPRECATED: remove legacy filename support in rename+1.
"""

from __future__ import annotations

from pathlib import Path

from .component_aliases import LEGACY_ARTIFACT_FILENAMES, find_artifact


def resolve_proposition_matcher_law_candidates(directory: Path) -> Path | None:
    """Prefer canonical filename; fall back to legacy beatrice_law_candidates.json."""
    return find_artifact(directory, "proposition_matcher_law_candidates.json")


def resolve_match_adjudicator_report(directory: Path) -> Path | None:
    return find_artifact(directory, "match_adjudicator_report.json")


def legacy_filename_for(canonical: str) -> str | None:
    for legacy, canon in LEGACY_ARTIFACT_FILENAMES.items():
        if canon == canonical:
            return legacy
    return None
