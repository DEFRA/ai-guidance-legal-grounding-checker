"""Deterministic document-breakdown metrics for lpe-eval-v0.1."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

EMPTY_OR_TINY_THRESHOLD = 20

_LOCATOR_FIELDS = (
    "canonical_locator",
    "locator",
    "source_locator",
    "section_id",
    "sectionId",
)

_TEXT_FIELDS = (
    "fragment_text",
    "source_text",
    "text",
    "content",
    "body",
)


def extract_locator(fragment: dict[str, Any]) -> str | None:
    """Return the first non-empty locator-like value on a fragment row."""
    for field in _LOCATOR_FIELDS:
        value = fragment.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    metadata = fragment.get("metadata")
    if isinstance(metadata, dict):
        for field in _LOCATOR_FIELDS:
            value = metadata.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def extract_source_text(fragment: dict[str, Any]) -> str:
    """Return the first source-text-like value on a fragment row."""
    for field in _TEXT_FIELDS:
        value = fragment.get(field)
        if value is not None and str(value).strip():
            return str(value)
    metadata = fragment.get("metadata")
    if isinstance(metadata, dict):
        for field in _TEXT_FIELDS:
            value = metadata.get(field)
            if value is not None and str(value).strip():
                return str(value)
    return ""


def normalize_text_for_hash(text: str) -> str:
    """Conservatively normalize source text: strip and collapse whitespace."""
    return re.sub(r"\s+", " ", str(text or "").strip())


def _text_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def _empty_document_breakdown() -> dict[str, int | float | None]:
    return {
        "fragment_count": None,
        "fragments_with_locator": None,
        "fragments_without_locator": None,
        "locator_coverage": None,
        "duplicate_fragment_hashes": None,
        "empty_or_tiny_fragments": None,
        "source_text_hash_mismatch_count": None,
    }


def compute_document_breakdown(
    fragments: list[dict[str, Any]] | None,
) -> dict[str, int | float | None]:
    """Compute document-breakdown metrics from source fragment rows."""
    if fragments is None:
        return _empty_document_breakdown()

    fragment_count = len(fragments)
    fragments_with_locator = sum(1 for row in fragments if extract_locator(row) is not None)
    fragments_without_locator = fragment_count - fragments_with_locator
    locator_coverage: float | None
    if fragment_count == 0:
        locator_coverage = None
    else:
        locator_coverage = fragments_with_locator / fragment_count

    hash_counts: Counter[str] = Counter()
    empty_or_tiny_fragments = 0
    for row in fragments:
        normalized = normalize_text_for_hash(extract_source_text(row))
        if not normalized or len(normalized) < EMPTY_OR_TINY_THRESHOLD:
            empty_or_tiny_fragments += 1
            continue
        hash_counts[_text_hash(normalized)] += 1

    duplicate_fragment_hashes = sum(count - 1 for count in hash_counts.values() if count > 1)

    return {
        "fragment_count": fragment_count,
        "fragments_with_locator": fragments_with_locator,
        "fragments_without_locator": fragments_without_locator,
        "locator_coverage": locator_coverage,
        "duplicate_fragment_hashes": duplicate_fragment_hashes,
        "empty_or_tiny_fragments": empty_or_tiny_fragments,
        "source_text_hash_mismatch_count": None,
    }


def document_breakdown_warnings(
    breakdown: dict[str, int | float | None],
    *,
    fragments_available: bool,
) -> list[str]:
    warnings: list[str] = []
    if not fragments_available:
        warnings.append("document_breakdown.missing_source_fragments")
        return warnings

    locator_coverage = breakdown.get("locator_coverage")
    if isinstance(locator_coverage, (int, float)) and locator_coverage < 0.95:
        warnings.append("document_breakdown.low_locator_coverage")

    duplicate = breakdown.get("duplicate_fragment_hashes")
    if isinstance(duplicate, int) and duplicate > 0:
        warnings.append("document_breakdown.duplicate_fragments")

    empty_or_tiny = breakdown.get("empty_or_tiny_fragments")
    if isinstance(empty_or_tiny, int) and empty_or_tiny > 0:
        warnings.append("document_breakdown.empty_or_tiny_fragments")

    return warnings


def _load_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_from_payload(payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def _load_from_run_artifacts(run_dir: Path, export_dir: Path) -> list[dict[str, Any]] | None:
    run_artifacts = _load_json_if_exists(run_dir / "run-artifacts.json")
    if isinstance(run_artifacts, list):
        for artifact in run_artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("artifact_type") != "source_fragments":
                continue
            storage_uri = artifact.get("storage_uri")
            if not storage_uri:
                continue
            rows = _rows_from_payload(_load_json_if_exists(export_dir / str(storage_uri)))
            if rows is not None:
                return rows

    artifacts_dir = run_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.glob("*source-fragments*.json")):
            rows = _rows_from_payload(_load_json_if_exists(path))
            if rows is not None:
                return rows
    return None


def load_source_fragments(
    run_dir: Path,
    bundle: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """Load source fragment rows from run artefacts, export root, or bundle."""
    resolved_run_dir = run_dir.resolve()
    if resolved_run_dir.parent.name == "runs":
        export_root = resolved_run_dir.parent.parent
    else:
        export_root = resolved_run_dir

    rows = _load_from_run_artifacts(resolved_run_dir, export_root)
    if rows is not None:
        return rows

    root_payload = _load_json_if_exists(export_root / "source_fragments.json")
    if root_payload is not None:
        return _rows_from_payload(root_payload)

    if bundle is not None and "source_fragments" in bundle:
        return _rows_from_payload(bundle.get("source_fragments"))

    return None
