"""Inspect persisted run directories for operator status and next steps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .cli_run_summary import build_cli_completion_summary
from .extraction_progress import extraction_timing_metrics_from_bundle, format_extraction_timing_summary
from .file_input import load_case_file
from .run_persistence import (
    RUN_BUNDLE_FILENAME,
    load_persisted_run_config,
    resolve_run_directory,
    run_bundle_path,
)
from .run_quality import build_run_quality_summary
from .source_bundle_intake import resolve_case_output_paths


def format_path_mtime_iso(path: Path) -> str:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return mtime.isoformat().replace("+00:00", "Z")


def _read_case_data(run_dir: Path) -> dict[str, Any] | None:
    _, case_json = resolve_case_output_paths(run_dir)
    if not case_json.is_file():
        return None
    try:
        payload = load_case_file(str(case_json))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_bundle_if_present(run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    bundle_file = run_bundle_path(run_dir)
    if not bundle_file.is_file():
        return None, None
    try:
        payload = json.loads(bundle_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"run_bundle.json exists but is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "run_bundle.json must contain a JSON object."
    return payload, None


def _appears_in_progress(run_dir: Path, *, bundle: dict[str, Any] | None) -> tuple[bool, str | None]:
    tmp_candidates = (
        run_dir / f"{RUN_BUNDLE_FILENAME}.tmp",
        run_dir / "case.json.tmp",
    )
    for tmp in tmp_candidates:
        if tmp.is_file():
            return True, f"temporary write in progress ({tmp.name})"

    if bundle is None:
        return False, None

    timing = extraction_timing_metrics_from_bundle(bundle)
    started = timing.get("extraction_started_at")
    completed = timing.get("extraction_completed_at")
    jobs_total = timing.get("extraction_jobs_total")
    jobs_completed = timing.get("extraction_jobs_completed")
    if started and not completed:
        return True, "extraction started but extraction_completed_at is missing"
    if (
        isinstance(jobs_total, int)
        and isinstance(jobs_completed, int)
        and jobs_total > 0
        and jobs_completed < jobs_total
        and not completed
    ):
        return (
            True,
            f"extraction jobs incomplete ({jobs_completed}/{jobs_total})",
        )
    return False, None


def _checkpoint_lines(bundle: dict[str, Any] | None) -> list[str]:
    if bundle is None:
        return []
    timing = extraction_timing_metrics_from_bundle(bundle)
    if not timing:
        return []
    summary = format_extraction_timing_summary(timing)
    return [line for line in summary.splitlines() if line.strip()]


def _command_target(run_dir: Path, case_data: dict[str, Any] | None) -> str:
    _, case_json = resolve_case_output_paths(run_dir)
    if case_json.is_file():
        return str(case_json)
    return str(run_dir)


def suggest_next_command(
    *,
    run_dir: Path,
    has_run_bundle: bool,
    appears_in_progress: bool,
    case_data: dict[str, Any] | None,
    bundle: dict[str, Any] | None,
    summary: dict[str, Any],
) -> str:
    target = _command_target(run_dir, case_data)
    run_dir_ref = str(run_dir)

    if appears_in_progress:
        return f"law-proposition-extractor-run-case run-status {run_dir_ref}"

    if not has_run_bundle:
        return f"law-proposition-extractor-run-case run-case {target} [--use-llm --extraction-mode heuristic|local|frontier]"

    mode = str(
        summary.get("extraction_mode_effective")
        or summary.get("extraction_mode")
        or "heuristic"
    )
    cached_failed = int(summary.get("cached_llm_results_failed") or 0)
    skip_hist = summary.get("skip_reasons_by_type")
    failed_chunk_cached = (
        int(skip_hist.get("failed_chunk_cached") or 0) if isinstance(skip_hist, dict) else 0
    )
    live_failed = int(summary.get("live_llm_calls_failed") or summary.get("failed_llm_calls") or 0)
    proposition_count = int(summary.get("propositions") or 0)

    if cached_failed > 0 or failed_chunk_cached > 0:
        persisted = load_persisted_run_config(case_data or {})
        fallback = persisted.extraction_fallback if persisted else "fail_closed"
        use_llm_flag = " --use-llm" if persisted and persisted.use_llm else ""
        return (
            f"law-proposition-extractor-run-case run-case {target}{use_llm_flag} "
            f"--extraction-mode {mode} --extraction-fallback {fallback} "
            f"--retry-failed-extraction-cache"
        )

    if proposition_count > 0 and live_failed == 0 and cached_failed == 0:
        return f"law-proposition-extractor-run-case export-run {run_dir_ref}"

    if live_failed > 0 or proposition_count == 0:
        return (
            f"law-proposition-extractor-run-case run-and-export-case {target} "
            f"--extraction-mode {mode} --output-dir dist/static-report"
        )

    return f"law-proposition-extractor-run-case export-run {run_dir_ref}"


@dataclass(frozen=True)
class RunStatusReport:
    run_dir: Path
    has_run_bundle: bool
    run_bundle_mtime: str | None
    proposition_count: int
    extraction_mode: str
    extraction_mode_requested: str
    live_success: int | None
    live_failed: int | None
    cached_success: int | None
    cached_failed: int | None
    appears_in_progress: bool
    in_progress_reason: str | None
    checkpoint_lines: list[str]
    suggested_next_command: str
    completed_at: str | None
    bundle_error: str | None


def build_run_status_report(run_path: str | Path) -> RunStatusReport:
    run_dir = resolve_run_directory(run_path)
    bundle_file = run_bundle_path(run_dir)
    has_run_bundle = bundle_file.is_file()
    run_bundle_mtime = format_path_mtime_iso(bundle_file) if has_run_bundle else None

    case_data = _read_case_data(run_dir)
    persisted = load_persisted_run_config(case_data or {}) if case_data else None
    bundle, bundle_error = _load_bundle_if_present(run_dir)

    appears_in_progress, in_progress_reason = _appears_in_progress(run_dir, bundle=bundle)
    checkpoint_lines = _checkpoint_lines(bundle)

    summary: dict[str, Any] = {}
    if bundle is not None:
        quality = build_run_quality_summary(bundle)
        summary = build_cli_completion_summary(bundle, quality_summary=quality, output_dir=None)

    proposition_count = int(summary.get("propositions") or 0)
    if proposition_count == 0 and persisted is not None:
        proposition_count = persisted.proposition_count
    if proposition_count == 0 and bundle is not None:
        props = bundle.get("propositions")
        proposition_count = len(props) if isinstance(props, list) else 0

    extraction_mode = str(
        summary.get("extraction_mode_effective")
        or summary.get("extraction_mode")
        or (persisted.extraction_mode_effective if persisted else "")
        or "unknown"
    )
    extraction_mode_requested = str(
        summary.get("extraction_mode_requested")
        or (persisted.extraction_mode_requested if persisted else "")
        or extraction_mode
    )

    live_success: int | None = None
    live_failed: int | None = None
    cached_success: int | None = None
    cached_failed: int | None = None
    if summary:
        live_success = int(summary.get("live_llm_calls_successful") or 0)
        live_failed = int(summary.get("live_llm_calls_failed") or 0)
        cached_success = int(summary.get("cached_llm_results_successful") or 0)
        cached_failed = int(summary.get("cached_llm_results_failed") or 0)

    completed_at = persisted.completed_at if persisted and persisted.completed_at else None

    suggested = suggest_next_command(
        run_dir=run_dir,
        has_run_bundle=has_run_bundle and bundle is not None,
        appears_in_progress=appears_in_progress,
        case_data=case_data,
        bundle=bundle,
        summary=summary,
    )

    return RunStatusReport(
        run_dir=run_dir,
        has_run_bundle=has_run_bundle,
        run_bundle_mtime=run_bundle_mtime,
        proposition_count=proposition_count,
        extraction_mode=extraction_mode,
        extraction_mode_requested=extraction_mode_requested,
        live_success=live_success,
        live_failed=live_failed,
        cached_success=cached_success,
        cached_failed=cached_failed,
        appears_in_progress=appears_in_progress,
        in_progress_reason=in_progress_reason,
        checkpoint_lines=checkpoint_lines,
        suggested_next_command=suggested,
        completed_at=completed_at,
        bundle_error=bundle_error,
    )


def format_run_status_lines(report: RunStatusReport) -> list[str]:
    lines = [
        f"Run directory: {report.run_dir}",
        f"run_bundle.json: {'yes' if report.has_run_bundle else 'no'}",
    ]
    if report.run_bundle_mtime:
        lines.append(f"run_bundle.json mtime: {report.run_bundle_mtime}")
    lines.append(f"Propositions: {report.proposition_count}")
    lines.append(f"Extraction mode: {report.extraction_mode}")
    if report.extraction_mode_requested != report.extraction_mode:
        lines.append(f"Extraction mode requested: {report.extraction_mode_requested}")
    if report.completed_at:
        lines.append(f"Run completed at: {report.completed_at}")

    if report.live_success is not None:
        lines.append(
            "Live LLM calls: "
            f"{report.live_success} ok / {report.live_failed or 0} failed"
        )
    if report.cached_success is not None:
        lines.append(
            "Cached LLM results: "
            f"{report.cached_success} ok / {report.cached_failed or 0} failed"
        )

    if report.appears_in_progress:
        reason = f" ({report.in_progress_reason})" if report.in_progress_reason else ""
        lines.append(f"In progress: yes{reason}")
    else:
        lines.append("In progress: no")

    if report.bundle_error:
        lines.append(f"Bundle error: {report.bundle_error}")

    if report.checkpoint_lines:
        lines.append("Latest extraction progress:")
        lines.extend(f"  {line}" if not line.startswith("  ") else line for line in report.checkpoint_lines)

    lines.append(f"Suggested next command: {report.suggested_next_command}")
    return lines
