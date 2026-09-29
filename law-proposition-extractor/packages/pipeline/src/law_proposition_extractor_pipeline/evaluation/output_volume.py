"""Deterministic output-volume metrics for lpe-eval-v0.1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_STATUS_FIELDS = (
    "candidate_status",
    "status",
    "classification",
    "category",
    "review_status",
)

_READY_EXACT = frozenset(
    {
        "ready",
        "approved",
        "compliance_relevant",
        "ready_for_review",
    }
)


def _empty_output_volume() -> dict[str, int | float | None]:
    return {
        "candidate_count": None,
        "final_statement_count": None,
        "ready_count": None,
        "usable_with_context_count": None,
        "needs_review_count": None,
        "candidates_per_fragment": None,
        "statements_per_fragment": None,
    }


def _normalize_status_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def extract_status_classification(record: dict[str, Any]) -> str | None:
    """Return the first status-like string on a final-output row."""
    for field in _STATUS_FIELDS:
        value = record.get(field)
        if value is not None and str(value).strip():
            return _normalize_status_token(value)
    return None


def classify_output_bucket(record: dict[str, Any]) -> str | None:
    """Map a final-output row to ready / usable_with_context / needs_review."""
    status = extract_status_classification(record)
    if status is not None:
        if status == "usable_with_context" or "usable_with_context" in status:
            return "usable_with_context"
        if status == "needs_review" or "needs_review" in status:
            return "needs_review"
        if status in _READY_EXACT:
            return "ready"

    if record.get("is_compliance_relevant") is True:
        return "ready"

    return None


def count_status_buckets(final_outputs: list[dict[str, Any]]) -> dict[str, int | None]:
    ready = usable = needs_review = 0
    classified = 0
    for row in final_outputs:
        bucket = classify_output_bucket(row)
        if bucket is None:
            continue
        classified += 1
        if bucket == "ready":
            ready += 1
        elif bucket == "usable_with_context":
            usable += 1
        elif bucket == "needs_review":
            needs_review += 1

    if classified == 0:
        return {
            "ready_count": None,
            "usable_with_context_count": None,
            "needs_review_count": None,
        }

    return {
        "ready_count": ready,
        "usable_with_context_count": usable,
        "needs_review_count": needs_review,
    }


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def compute_output_volume(
    *,
    candidates: list[dict[str, Any]] | None,
    final_outputs: list[dict[str, Any]] | None,
    fragment_count: int | None,
) -> dict[str, int | float | None]:
    """Compute output-volume metrics from candidate and final-output rows."""
    metrics = _empty_output_volume()

    if candidates is not None:
        metrics["candidate_count"] = len(candidates)

    if final_outputs is not None:
        metrics["final_statement_count"] = len(final_outputs)
        metrics.update(count_status_buckets(final_outputs))

    metrics["candidates_per_fragment"] = _ratio(metrics["candidate_count"], fragment_count)
    metrics["statements_per_fragment"] = _ratio(metrics["final_statement_count"], fragment_count)

    return metrics


def output_volume_warnings(
    volume: dict[str, int | float | None],
    *,
    fragment_count: int | None,
) -> list[str]:
    warnings: list[str] = []
    candidate_count = volume.get("candidate_count")
    final_statement_count = volume.get("final_statement_count")
    ready_count = volume.get("ready_count")
    needs_review_count = volume.get("needs_review_count")

    if candidate_count is None and isinstance(fragment_count, int) and fragment_count > 0:
        warnings.append("output_volume.missing_candidates")

    if final_statement_count is None and isinstance(candidate_count, int) and candidate_count > 0:
        warnings.append("output_volume.missing_final_outputs")

    if candidate_count == 0 and isinstance(fragment_count, int) and fragment_count > 0:
        warnings.append("output_volume.zero_candidates")

    if (
        isinstance(candidate_count, int)
        and candidate_count > 0
        and final_statement_count == 0
    ):
        warnings.append("output_volume.zero_final_outputs")

    if (
        isinstance(needs_review_count, int)
        and isinstance(ready_count, int)
        and needs_review_count > ready_count
    ):
        warnings.append("output_volume.review_load_exceeds_ready")

    return warnings


def _load_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_from_payload(payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def _candidate_rows_from_payload(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return _rows_from_payload(payload)
    if isinstance(payload, dict):
        for key in ("candidates", "propositions", "statements", "rows"):
            rows = _rows_from_payload(payload.get(key))
            if rows is not None:
                return rows
    return None


def _final_rows_from_beatrice(payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    return _rows_from_payload(payload.get("candidates"))


def _final_rows_from_effective_law(payload: Any) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    return _rows_from_payload(payload.get("statements"))


def _load_artifact_rows(
    run_dir: Path,
    export_dir: Path,
    *,
    artifact_type: str,
    glob_pattern: str,
) -> list[dict[str, Any]] | None:
    run_artifacts = _load_json_if_exists(run_dir / "run-artifacts.json")
    if isinstance(run_artifacts, list):
        for artifact in run_artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("artifact_type") != artifact_type:
                continue
            storage_uri = artifact.get("storage_uri")
            if not storage_uri:
                continue
            rows = _candidate_rows_from_payload(_load_json_if_exists(export_dir / str(storage_uri)))
            if rows is not None:
                return rows

    artifacts_dir = run_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.glob(glob_pattern)):
            rows = _candidate_rows_from_payload(_load_json_if_exists(path))
            if rows is not None:
                return rows
    return None


def load_candidate_propositions(
    run_dir: Path,
    bundle: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """Load raw extracted proposition rows from run artefacts, export root, or bundle."""
    resolved_run_dir = run_dir.resolve()
    if resolved_run_dir.parent.name == "runs":
        export_root = resolved_run_dir.parent.parent
    else:
        export_root = resolved_run_dir

    rows = _load_artifact_rows(
        resolved_run_dir,
        export_root,
        artifact_type="propositions",
        glob_pattern="*propositions*.json",
    )
    if rows is not None:
        return rows

    root_payload = _load_json_if_exists(export_root / "propositions.json")
    if root_payload is not None:
        return _candidate_rows_from_payload(root_payload)

    if bundle is not None and "propositions" in bundle:
        return _candidate_rows_from_payload(bundle.get("propositions"))

    return None


def load_final_outputs(
    run_dir: Path,
    bundle: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """Load final exported statement rows from Proposition Matcher/effective-law artefacts or bundle."""
    resolved_run_dir = run_dir.resolve()
    if resolved_run_dir.parent.name == "runs":
        export_root = resolved_run_dir.parent.parent
    else:
        export_root = resolved_run_dir

    beatrice_payload = _load_json_if_exists((export_root / "proposition_matcher_law_candidates.json" if (export_root / "proposition_matcher_law_candidates.json").is_file() else export_root / "beatrice_law_candidates.json"))  # COMPAT_LEGACY_NAME)
    if beatrice_payload is not None:
        rows = _final_rows_from_beatrice(beatrice_payload)
        if rows is not None:
            return rows

    rows = _load_artifact_rows(
        resolved_run_dir,
        export_root,
        artifact_type="proposition_matcher_law_candidates",
        glob_pattern="*proposition-matcher-law-candidates*.json",
    )
    if rows is not None:
        return rows

    effective_payload = _load_json_if_exists(export_root / "effective_law_statements.json")
    if effective_payload is not None:
        rows = _final_rows_from_effective_law(effective_payload)
        if rows is not None:
            return rows

    rows = _load_artifact_rows(
        resolved_run_dir,
        export_root,
        artifact_type="effective_law_statements",
        glob_pattern="*effective-law-statements*.json",
    )
    if rows is not None:
        return rows

    if bundle is not None:
        beatrice_bundle = bundle.get("proposition_matcher_law_candidates")
        if beatrice_bundle is not None:
            rows = _final_rows_from_beatrice(beatrice_bundle)
            if rows is not None:
                return rows
        effective_bundle = bundle.get("effective_law_statements")
        if effective_bundle is not None:
            rows = _final_rows_from_effective_law(effective_bundle)
            if rows is not None:
                return rows

    return None
