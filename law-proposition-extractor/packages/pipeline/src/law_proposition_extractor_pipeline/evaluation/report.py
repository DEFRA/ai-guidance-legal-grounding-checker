"""Deterministic run-health evaluation report (lpe-eval-v0.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .document_breakdown import (
    compute_document_breakdown,
    document_breakdown_warnings,
    load_source_fragments,
)
from .output_volume import (
    compute_output_volume,
    load_candidate_propositions,
    load_final_outputs,
    output_volume_warnings,
)

SCHEMA_VERSION = "lpe-eval-v0.1"
EVALUATION_REPORT_JSON = "evaluation_report.json"
EVALUATION_SUMMARY_MD = "evaluation_summary.md"


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    compact = "-".join(segment for segment in normalized.split("-") if segment)
    return compact or "item"


def _load_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_run_id(run_dir: Path) -> str:
    manifest = _load_json_if_exists(run_dir / "manifest.json")
    if isinstance(manifest, dict) and manifest.get("run_id"):
        return str(manifest["run_id"])
    run_payload = _load_json_if_exists(run_dir / "run.json")
    if isinstance(run_payload, dict) and run_payload.get("id"):
        return str(run_payload["id"])
    return run_dir.name


def resolve_export_dir(run_dir: Path) -> Path:
    """Return the static export root that contains ``runs/<run_id>/``."""
    resolved = run_dir.resolve()
    if resolved.parent.name == "runs":
        return resolved.parent.parent
    return resolved


def resolve_run_dir(export_dir: Path, bundle: dict[str, Any]) -> Path:
    run_id = str(bundle.get("run", {}).get("id", "run-unknown"))
    return Path(export_dir) / "runs" / _slug(run_id)


@dataclass
class EvaluationReport:
    schema_version: str
    run_id: str
    baseline_run_id: str | None
    generated_at: str
    document_breakdown: dict[str, Any] = field(default_factory=dict)
    output_volume: dict[str, Any] = field(default_factory=dict)
    traceability: dict[str, Any] = field(default_factory=dict)
    deduplication: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "baseline_run_id": self.baseline_run_id,
            "generated_at": self.generated_at,
            "document_breakdown": self.document_breakdown,
            "output_volume": self.output_volume,
            "traceability": self.traceability,
            "deduplication": self.deduplication,
            "comparison": self.comparison,
            "warnings": list(self.warnings),
        }


def build_evaluation_report(
    run_dir: Path,
    baseline_run_dir: Path | None = None,
    bundle: dict[str, Any] | None = None,
) -> EvaluationReport:
    """Build a deterministic evaluation report from exported run artefacts."""
    resolved_run_dir = run_dir.resolve()
    run_id = _read_run_id(resolved_run_dir)
    baseline_run_id: str | None = None
    comparison: dict[str, Any] | None = None
    warnings: list[str] = []

    if baseline_run_dir is not None:
        resolved_baseline = baseline_run_dir.resolve()
        baseline_run_id = _read_run_id(resolved_baseline)
        comparison = {
            "baseline_run_id": baseline_run_id,
            "metrics": {},
        }
        warnings.append(
            "Baseline comparison metrics are not implemented in lpe-eval-v0.1."
        )

    if not resolved_run_dir.is_dir():
        warnings.append(f"Run directory does not exist: {resolved_run_dir}")

    source_fragments = load_source_fragments(resolved_run_dir, bundle)
    document_breakdown = compute_document_breakdown(source_fragments)
    warnings.extend(
        document_breakdown_warnings(
            document_breakdown,
            fragments_available=source_fragments is not None,
        )
    )

    candidates = load_candidate_propositions(resolved_run_dir, bundle)
    final_outputs = load_final_outputs(resolved_run_dir, bundle)
    output_volume = compute_output_volume(
        candidates=candidates,
        final_outputs=final_outputs,
        fragment_count=document_breakdown.get("fragment_count"),
    )
    warnings.extend(
        output_volume_warnings(
            output_volume,
            fragment_count=document_breakdown.get("fragment_count"),
        )
    )

    return EvaluationReport(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        generated_at=_utc_now_iso_z(),
        document_breakdown=document_breakdown,
        output_volume=output_volume,
        traceability={},
        deduplication={},
        comparison=comparison,
        warnings=warnings,
    )


def _format_metric_count(value: Any) -> str:
    if value is None:
        return "n/a"
    return str(value)


def _format_locator_coverage(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return str(value)


def _document_breakdown_is_populated(document_breakdown: dict[str, Any]) -> bool:
    return bool(document_breakdown) and document_breakdown.get("fragment_count") is not None


def _output_volume_is_populated(output_volume: dict[str, Any]) -> bool:
    if not output_volume:
        return False
    return (
        output_volume.get("candidate_count") is not None
        or output_volume.get("final_statement_count") is not None
    )


def _format_output_volume_count(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"
    return str(value)


def _format_output_volume_ratio(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value)


def render_evaluation_summary_md(report: EvaluationReport) -> str:
    lines = [
        "# Law Proposition Extractor Evaluation Summary",
        "",
        f"**Schema:** {report.schema_version} — deterministic Eval v0.1",
        "",
        "This report is generated deterministically from exported run artefacts only. "
        "It does not use LLM-as-judge evaluation and does not require a gold set.",
        "",
        f"**Run ID:** `{report.run_id}`",
    ]
    if report.baseline_run_id is not None:
        lines.append(f"**Baseline run ID:** `{report.baseline_run_id}`")
    lines.extend(
        [
            f"**Generated at:** {report.generated_at}",
            "",
            "## Document breakdown",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Fragments | {_format_metric_count(report.document_breakdown.get('fragment_count'))} |",
            f"| Locator coverage | {_format_locator_coverage(report.document_breakdown.get('locator_coverage'))} |",
            f"| Duplicate fragment hashes | {_format_metric_count(report.document_breakdown.get('duplicate_fragment_hashes'))} |",
            f"| Empty/tiny fragments | {_format_metric_count(report.document_breakdown.get('empty_or_tiny_fragments'))} |",
            "",
            "## Output volume",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Candidates | {_format_output_volume_count(report.output_volume.get('candidate_count'))} |",
            f"| Final statements | {_format_output_volume_count(report.output_volume.get('final_statement_count'))} |",
            f"| Ready | {_format_output_volume_count(report.output_volume.get('ready_count'))} |",
            f"| Usable with context | {_format_output_volume_count(report.output_volume.get('usable_with_context_count'))} |",
            f"| Needs review | {_format_output_volume_count(report.output_volume.get('needs_review_count'))} |",
            f"| Candidates / fragment | {_format_output_volume_ratio(report.output_volume.get('candidates_per_fragment'))} |",
            f"| Statements / fragment | {_format_output_volume_ratio(report.output_volume.get('statements_per_fragment'))} |",
            "",
            "## Metric sections",
            "",
            "| Section | Status |",
            "| --- | --- |",
            f"| document_breakdown | {'populated' if _document_breakdown_is_populated(report.document_breakdown) else 'pending (v0.1 stub)'} |",
            f"| output_volume | {'populated' if _output_volume_is_populated(report.output_volume) else 'pending (v0.1 stub)'} |",
            f"| traceability | {'populated' if report.traceability else 'pending (v0.1 stub)'} |",
            f"| deduplication | {'populated' if report.deduplication else 'pending (v0.1 stub)'} |",
            f"| comparison | {'present' if report.comparison is not None else 'none'} |",
            "",
            "## Warnings",
            "",
        ]
    )
    if report.warnings:
        for warning in report.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def write_evaluation_artifacts(
    run_dir: Path,
    report: EvaluationReport,
) -> tuple[Path, Path]:
    """Write ``evaluation/evaluation_report.json`` and ``evaluation/evaluation_summary.md``."""
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    json_path = eval_dir / EVALUATION_REPORT_JSON
    md_path = eval_dir / EVALUATION_SUMMARY_MD
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_evaluation_summary_md(report), encoding="utf-8")
    return json_path, md_path


def write_run_evaluation_after_export(
    export_dir: str | Path,
    bundle: dict[str, Any],
    *,
    baseline_export_dir: str | Path | None = None,
) -> tuple[Path, Path] | None:
    """Build and write evaluation artefacts under ``runs/<run_id>/evaluation/``."""
    root = Path(export_dir)
    run_dir = resolve_run_dir(root, bundle)
    if not run_dir.is_dir():
        return None

    baseline_run_dir: Path | None = None
    if baseline_export_dir is not None:
        baseline_run_dir = resolve_run_dir(Path(baseline_export_dir), bundle)

    report = build_evaluation_report(
        run_dir,
        baseline_run_dir=baseline_run_dir,
        bundle=bundle,
    )
    return write_evaluation_artifacts(run_dir, report)
