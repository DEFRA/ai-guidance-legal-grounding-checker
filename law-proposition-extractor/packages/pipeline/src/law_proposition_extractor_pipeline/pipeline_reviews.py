"""Append-only pipeline review decisions (governance metadata)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import PipelineReviewDecision, RunArtifact

from .intake import content_hash

_PIPELINE_DECISION_VALUES = frozenset(
    {"approved", "rejected", "needs_review", "overridden", "deferred"}
)


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    compact = "-".join(segment for segment in normalized.split("-") if segment)
    return compact or "item"


def _normalize_field(field: str | None) -> str | None:
    if field is None:
        return None
    s = str(field).strip()
    return s if s else None


def _field_matches(stored: Any, requested: str | None) -> bool:
    return _normalize_field(stored if isinstance(stored, str) else None) == _normalize_field(
        requested
    )


def normalise_pipeline_review_decisions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("pipeline_review_decisions")
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


def categorisation_artifact_id(row: dict[str, Any]) -> str:
    return ":".join(
        [
            str(row.get("source_record_id", "")),
            str(row.get("source_inventory_row_id") or ""),
            str(row.get("source_target_link_id") or ""),
        ]
    )


def resolve_current_pipeline_review_decision(
    decisions: list[dict[str, Any]],
    *,
    artifact_type: str,
    artifact_id: str,
    applies_to_field: str | None = None,
) -> dict[str, Any] | None:
    """Return the effective decision for an artifact (append-only + supersedes chain)."""
    superseded_ids: set[str] = set()
    for d in decisions:
        if not isinstance(d, dict):
            continue
        sid = d.get("supersedes_decision_id")
        if sid is not None and str(sid).strip():
            superseded_ids.add(str(sid).strip())

    matches = [
        d
        for d in decisions
        if isinstance(d, dict)
        and str(d.get("artifact_type", "")) == artifact_type
        and str(d.get("artifact_id", "")) == artifact_id
        and _field_matches(d.get("applies_to_field"), applies_to_field)
        and str(d.get("id", "")).strip() not in superseded_ids
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda d: (str(d.get("reviewed_at", "")), str(d.get("id", ""))),
    )


def attach_pipeline_review_decisions_artifact(bundle: dict[str, Any]) -> None:
    """Register a run artifact when governance decisions exist. Idempotent."""
    decisions = normalise_pipeline_review_decisions(bundle)
    if not decisions:
        return
    run_artifacts = bundle.get("run_artifacts")
    if not isinstance(run_artifacts, list):
        run_artifacts = []
        bundle["run_artifacts"] = run_artifacts
    if any(
        isinstance(a, dict) and str(a.get("artifact_type")) == "pipeline_review_decisions"
        for a in run_artifacts
    ):
        return

    run = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
    run_id = str(run.get("id", "run-unknown"))
    payload = json.dumps(decisions, sort_keys=True, default=str)
    run_artifacts.append(
        RunArtifact(
            id=f"artifact-{run_id}-pipeline-review-decisions",
            run_id=run_id,
            artifact_type="pipeline_review_decisions",
            provenance="pipeline.governance",
            content_hash=content_hash(payload),
            metadata={},
        ).model_dump(mode="json")
    )


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_pipeline_review_decision(
    export_dir: str | Path,
    *,
    run_id: str | None,
    artifact_type: str,
    artifact_id: str,
    decision: str,
    reviewer: str | None = None,
    reason: str = "",
    replacement_value: Any | None = None,
    evidence: list[str] | None = None,
    applies_to_field: str | None = None,
    supersedes_decision_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    reviewed_at: str | None = None,
    decision_id: str | None = None,
) -> dict[str, Any]:
    """Append one decision to pipeline_review_decisions.json and sync run artifact hashes."""
    root = Path(export_dir)
    if not root.is_dir():
        raise ValueError(f"Export directory does not exist: {root}")

    run_payload = _read_json(root / "run.json", {})
    resolved_run_id = run_id or (str(run_payload.get("id", "")) if isinstance(run_payload, dict) else "")
    if not resolved_run_id:
        raise ValueError("run_id is required when run.json is missing or has no id")

    dnorm = str(decision).strip().lower()
    if dnorm not in _PIPELINE_DECISION_VALUES:
        raise ValueError(f"Invalid decision {decision!r}")

    path = root / "pipeline_review_decisions.json"
    existing = _read_json(path, [])
    if not isinstance(existing, list):
        existing = []
    decisions: list[dict[str, Any]] = [d for d in existing if isinstance(d, dict)]

    if supersedes_decision_id:
        sid = str(supersedes_decision_id).strip()
        if sid and not any(str(d.get("id")) == sid for d in decisions):
            raise ValueError(f"supersedes_decision_id {sid!r} not found in existing decisions")

    rid = decision_id or f"prd-{uuid.uuid4().hex[:12]}"
    if any(str(d.get("id")) == rid for d in decisions):
        raise ValueError(f"decision id {rid!r} already exists (append-only)")

    row = PipelineReviewDecision(
        id=rid,
        run_id=resolved_run_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        decision=dnorm,  # type: ignore[assignment]
        reviewer=reviewer,
        reviewed_at=reviewed_at or _utc_now_iso_z(),
        reason=reason,
        replacement_value=replacement_value,
        evidence=list(evidence or []),
        applies_to_field=applies_to_field,
        supersedes_decision_id=supersedes_decision_id,
        metadata=dict(metadata or {}),
    ).model_dump(mode="json")
    decisions.append(row)
    _write_json(path, decisions)

    _sync_run_artifact_for_pipeline_reviews(root, run_id=resolved_run_id, decisions=decisions)
    return row


def _sync_run_artifact_for_pipeline_reviews(
    root: Path,
    *,
    run_id: str,
    decisions: list[dict[str, Any]],
) -> None:
    payload = json.dumps(decisions, sort_keys=True, default=str)
    h = content_hash(payload)
    artifact_id = f"artifact-{run_id}-pipeline-review-decisions"
    run_slug = _slug(run_id)
    nested_run_dir = root / "runs" / run_slug

    run_artifacts_path = root / "run_artifacts.json"
    run_artifacts = _read_json(run_artifacts_path, [])
    if not isinstance(run_artifacts, list):
        run_artifacts = []

    idx: int | None = None
    for i, item in enumerate(run_artifacts):
        if isinstance(item, dict) and str(item.get("artifact_type")) == "pipeline_review_decisions":
            idx = i
            break

    entry: dict[str, Any] = {
        "id": artifact_id,
        "run_id": run_id,
        "artifact_type": "pipeline_review_decisions",
        "provenance": "pipeline.governance",
        "content_hash": h,
    }
    if nested_run_dir.is_dir():
        nested_artifact_path = nested_run_dir / "artifacts" / f"{_slug(artifact_id)}.json"
        entry["storage_uri"] = str(nested_artifact_path.relative_to(root))
        _write_json(nested_artifact_path, decisions)

    if idx is None:
        run_artifacts.append(entry)
    else:
        prev = run_artifacts[idx] if isinstance(run_artifacts[idx], dict) else {}
        run_artifacts[idx] = {**prev, **entry}

    _write_json(run_artifacts_path, run_artifacts)

    nested_run_artifacts = nested_run_dir / "run-artifacts.json"
    if nested_run_artifacts.parent.is_dir():
        _write_json(nested_run_artifacts, run_artifacts)

    run_manifest_path = nested_run_dir / "manifest.json"
    man = _read_json(run_manifest_path, {})
    if isinstance(man, dict) and man.get("run_id") == run_id:
        arts = man.get("artifacts")
        if isinstance(arts, list):
            found = False
            for a in arts:
                if isinstance(a, dict) and str(a.get("artifact_type")) == "pipeline_review_decisions":
                    a["id"] = artifact_id
                    if "storage_uri" in entry:
                        a["storage_uri"] = entry["storage_uri"]
                    found = True
                    break
            if not found and "storage_uri" in entry:
                arts.append(
                    {
                        "id": artifact_id,
                        "artifact_type": "pipeline_review_decisions",
                        "storage_uri": entry["storage_uri"],
                    }
                )
            man["artifacts"] = arts
        man["has_pipeline_review_decisions"] = len(decisions) > 0
        man["pipeline_review_decision_count"] = len(decisions)
        _write_json(run_manifest_path, man)

    root_man = _read_json(root / "manifest.json", {})
    if isinstance(root_man, dict):
        root_man["has_pipeline_review_decisions"] = len(decisions) > 0
        root_man["pipeline_review_decision_count"] = len(decisions)
        _write_json(root / "manifest.json", root_man)
