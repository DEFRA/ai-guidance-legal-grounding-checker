"""Batch runner for extraction prompt-lab fixtures with aggregate summary."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .extraction_prompt_eval import (
    PromptEvalResult,
    _evaluation_config,
    evaluate_and_write_prompt_lab_run,
    evaluate_prompt_lab_extraction,
)
from .extraction_workbench import (
    FragmentWorkbenchResult,
    load_prompt_lab_fixture,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)

PROMPT_LAB_SUMMARY_JSON = "prompt_lab_summary.json"
PROMPT_LAB_SUMMARY_MD = "PROMPT_LAB_SUMMARY.md"

FragmentExtractionMode = Literal["local", "frontier", "dry"]
BatchRowStatus = Literal["pass", "warn", "fail", "error", "skipped"]

_TIER_RE = re.compile(r"^slurry-(good|bad|ugly)-", re.IGNORECASE)
_MATCHED_RE = re.compile(r"^(\d+)/(\d+)$")

_FAILURE_THEMES: tuple[tuple[str, str], ...] = (
    ("missing_expected_legal_effect", "missing expected legal effect"),
    ("wrong_boilerplate_classification", "wrong boilerplate classification"),
    ("unexpected_checkable_proposition", "unexpected checkable proposition"),
    ("missing_evidence_quote", "missing evidence quote"),
    ("weak_subject_or_action", "weak subject/action"),
    ("missing_conditions_or_exceptions", "missing conditions/exceptions"),
    ("over_compressed_proposition", "over-compressed proposition"),
    ("table_evidence_salvage", "table evidence salvage"),
    ("extraction_or_runtime_error", "extraction/runtime error"),
    ("fixture_or_eval_policy_warning", "fixture/eval policy warning"),
)


@dataclass
class PromptLabBatchRow:
    fixture_file: str
    case_id: str
    tier: str
    label: str
    evaluation_mode: str
    status: BatchRowStatus
    expected_proposition_count: int = 0
    actual_proposition_count: int = 0
    matched_expected: str = "0/0"
    expected_checkable_count: int | None = None
    actual_checkable_count: int = 0
    extra_actual_count: int = 0
    missing_legal_effects: list[str] = field(default_factory=list)
    unexpected_legal_effects: list[str] = field(default_factory=list)
    boilerplate_failures: int = 0
    over_compression_warnings: int = 0
    evidence_failures: int = 0
    runtime_extraction_errors: list[str] = field(default_factory=list)
    run_directory: str | None = None
    warnings: list[str] = field(default_factory=list)
    failure_themes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_file": self.fixture_file,
            "case_id": self.case_id,
            "tier": self.tier,
            "label": self.label,
            "evaluation_mode": self.evaluation_mode,
            "status": self.status,
            "expected_proposition_count": self.expected_proposition_count,
            "actual_proposition_count": self.actual_proposition_count,
            "matched_expected": self.matched_expected,
            "expected_checkable_count": self.expected_checkable_count,
            "actual_checkable_count": self.actual_checkable_count,
            "extra_actual_count": self.extra_actual_count,
            "missing_legal_effects": list(self.missing_legal_effects),
            "unexpected_legal_effects": list(self.unexpected_legal_effects),
            "boilerplate_failures": self.boilerplate_failures,
            "over_compression_warnings": self.over_compression_warnings,
            "evidence_failures": self.evidence_failures,
            "runtime_extraction_errors": list(self.runtime_extraction_errors),
            "run_directory": self.run_directory,
            "warnings": list(self.warnings),
            "failure_themes": list(self.failure_themes),
        }


@dataclass
class PromptLabBatchResult:
    output_root: str
    mode: str
    generated_at: str
    fixture_count: int
    rows: list[PromptLabBatchRow]
    failure_themes: dict[str, list[str]]
    verdict: str
    verdict_detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_root": self.output_root,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "fixture_count": len(self.rows),
            "verdict": self.verdict,
            "verdict_detail": self.verdict_detail,
            "failure_themes": self.failure_themes,
            "rows": [row.to_dict() for row in self.rows],
        }


def infer_fixture_tier(fixture_path: Path, fixture_data: dict[str, Any] | None = None) -> str:
    stem = fixture_path.stem.lower()
    match = _TIER_RE.match(stem)
    if match:
        return match.group(1).lower()
    label = str((fixture_data or {}).get("label") or "").upper()
    for tier in ("GOOD", "BAD", "UGLY"):
        if label.startswith(tier):
            return tier.lower()
    return "unknown"


def discover_prompt_lab_fixtures(
    fixture_dir: Path | None = None,
    *,
    fixture_paths: list[Path] | None = None,
    fixture_glob: str | None = None,
    limit: int | None = None,
) -> list[Path]:
    """Discover prompt-lab fixture JSON files, skipping helpers and eval_runs."""
    discovered: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        discovered.append(resolved)

    if fixture_paths:
        for raw in fixture_paths:
            path = Path(raw).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"fixture not found: {path}")
            if fixture_glob and not fnmatch.fnmatch(path.name, fixture_glob):
                continue
            _add(path)

    if fixture_dir is not None:
        root = Path(fixture_dir).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"fixture directory not found: {root}")
        for path in sorted(root.rglob("*.json")):
            rel = path.relative_to(root)
            if any(part == "eval_runs" for part in rel.parts):
                continue
            if path.name.startswith("_"):
                continue
            if fixture_glob and not fnmatch.fnmatch(path.name, fixture_glob):
                continue
            _add(path)

    if not discovered and fixture_dir is None and not fixture_paths:
        raise ValueError("provide fixture_dir or fixture_paths")

    discovered.sort(key=lambda p: p.name)
    if limit is not None and limit >= 0:
        discovered = discovered[: int(limit)]
    return discovered


def _fixture_has_dry_output(fixture_data: dict[str, Any]) -> bool:
    dry = fixture_data.get("dry")
    if not isinstance(dry, dict):
        return False
    raw = dry.get("raw_model_output")
    return isinstance(raw, str) and bool(raw.strip())


def _count_evidence_failures(eval_result: PromptEvalResult) -> int:
    return sum(1 for m in eval_result.expected_matches if not m.evidence_ok)


def _unexpected_legal_effects(eval_result: PromptEvalResult) -> list[str]:
    expected = set(eval_result.checks.get("legal_effect_coverage", {}).get("expected") or [])
    actual = set(eval_result.checks.get("legal_effect_coverage", {}).get("actual") or [])
    return sorted(actual - expected)


def _parse_matched_expected(matched: str) -> tuple[int, int] | None:
    m = _MATCHED_RE.match(str(matched).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _row_is_extras_only_failure(row: PromptLabBatchRow) -> bool:
    """Fail because exhaustive count/extras despite matching every expected gold row."""
    if row.status != "fail":
        return False
    counts = _parse_matched_expected(row.matched_expected)
    if counts is None or counts[0] != counts[1]:
        return False
    if row.extra_actual_count <= 0:
        return False
    if row.evidence_failures > 0:
        return False
    return True


def _row_suggests_prompt_change(row: PromptLabBatchRow) -> bool:
    """True when unmatched expected rows look like omission or weak extraction, not policy/classifier alone."""
    counts = _parse_matched_expected(row.matched_expected)
    if counts is None or counts[0] >= counts[1]:
        return False
    if row.evidence_failures > 0:
        return True
    themes = set(row.failure_themes)
    if "weak_subject_or_action" in themes or "missing_conditions_or_exceptions" in themes:
        return True
    if "over_compressed_proposition" in themes:
        return True
    # Unmatched gold rows but full fragment extracted (classifier / legal_effect taxonomy).
    if (
        counts[0] == 0
        and row.actual_proposition_count >= row.expected_proposition_count
        and row.evidence_failures == 0
    ):
        return False
    return counts[0] < counts[1]


def _classify_failure_themes(
    *,
    row: PromptLabBatchRow,
    eval_result: PromptEvalResult | None,
) -> list[str]:
    themes: list[str] = []
    if row.runtime_extraction_errors:
        themes.append("extraction_or_runtime_error")
    if eval_result is None:
        return themes

    if eval_result.missing_effects:
        themes.append("missing_expected_legal_effect")

    all_expected_matched = (
        eval_result.matched_expected_count == eval_result.expected_count
        and eval_result.expected_count > 0
    )
    if row.unexpected_legal_effects and not all_expected_matched:
        themes.append("missing_expected_legal_effect")
    elif row.unexpected_legal_effects and all_expected_matched:
        themes.append("fixture_or_eval_policy_warning")

    boilerplate = eval_result.checks.get("boilerplate_classification") or {}
    if boilerplate.get("findings"):
        themes.append("wrong_boilerplate_classification")

    checkable = eval_result.checks.get("checkable_count") or {}
    if not checkable.get("passed"):
        themes.append("unexpected_checkable_proposition")

    for match in eval_result.expected_matches:
        if match.matched:
            continue
        reason = str(match.suggested_failure_reason or "").lower()
        if "evidence" in reason:
            themes.append("missing_evidence_quote")
        if "subject" in reason or "action" in reason:
            themes.append("weak_subject_or_action")
        if "conditions" in reason or "exceptions" in reason:
            themes.append("missing_conditions_or_exceptions")

    compression = eval_result.checks.get("over_compression") or {}
    if compression.get("findings"):
        themes.append("over_compressed_proposition")

    for warning in eval_result.warnings:
        wl = warning.lower()
        if "table" in wl and "numeric" in wl:
            themes.append("table_evidence_salvage")
        if "extra actual" in wl or "warn-only" in wl:
            themes.append("fixture_or_eval_policy_warning")

    if row.extra_actual_count and eval_result.summary.get("allow_extra_actual"):
        themes.append("fixture_or_eval_policy_warning")

    if (
        row.extra_actual_count > 0
        and not eval_result.summary.get("allow_extra_actual")
        and all_expected_matched
        and not eval_result.passed
    ):
        themes.append("fixture_or_eval_policy_warning")

    # dedupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for theme in themes:
        if theme not in seen:
            seen.add(theme)
            ordered.append(theme)
    return ordered


def _row_status_from_eval(
    *,
    eval_result: PromptEvalResult,
    workbench_status: str | None,
) -> BatchRowStatus:
    if eval_result.eval_status == "error":
        return "error"
    if not eval_result.passed:
        return "fail"
    has_warnings = bool(eval_result.warnings)
    compression = eval_result.checks.get("over_compression") or {}
    if compression.get("findings") and compression.get("warn_only"):
        has_warnings = True
    extra = eval_result.checks.get("extra_actual") or {}
    if extra.get("status") == "extras_allowed" and extra.get("extra_count"):
        has_warnings = True
    if workbench_status and workbench_status not in {"success"}:
        has_warnings = True
    return "warn" if has_warnings else "pass"


def _build_row_from_eval(
    *,
    fixture_path: Path,
    fixture_data: dict[str, Any],
    run_dir: Path,
    eval_result: PromptEvalResult,
    workbench_result: FragmentWorkbenchResult | None,
    runtime_errors: list[str],
) -> PromptLabBatchRow:
    cfg = _evaluation_config(fixture_data)
    expected_checkable = cfg.get("expected_checkable_count")
    if expected_checkable is not None:
        expected_checkable = int(expected_checkable)

    checkable = eval_result.checks.get("checkable_count") or {}
    boilerplate = eval_result.checks.get("boilerplate_classification") or {}
    compression = eval_result.checks.get("over_compression") or {}

    row = PromptLabBatchRow(
        fixture_file=str(fixture_path),
        case_id=str(fixture_data.get("case_id") or fixture_path.stem),
        tier=infer_fixture_tier(fixture_path, fixture_data),
        label=str(fixture_data.get("label") or ""),
        evaluation_mode=str(cfg.get("mode") or "exhaustive"),
        status=_row_status_from_eval(
            eval_result=eval_result,
            workbench_status=workbench_result.workbench_status if workbench_result else None,
        ),
        expected_proposition_count=eval_result.expected_count,
        actual_proposition_count=eval_result.actual_count,
        matched_expected=f"{eval_result.matched_expected_count}/{eval_result.expected_count}",
        expected_checkable_count=expected_checkable,
        actual_checkable_count=int(checkable.get("checkable_count") or 0),
        extra_actual_count=len(eval_result.extra_actual),
        missing_legal_effects=list(eval_result.missing_effects),
        unexpected_legal_effects=_unexpected_legal_effects(eval_result),
        boilerplate_failures=len(boilerplate.get("findings") or []),
        over_compression_warnings=len(compression.get("findings") or []),
        evidence_failures=_count_evidence_failures(eval_result),
        runtime_extraction_errors=list(runtime_errors),
        run_directory=str(run_dir.resolve()),
        warnings=list(eval_result.warnings),
    )
    row.failure_themes = _classify_failure_themes(row=row, eval_result=eval_result)
    return row


def _error_row(
    *,
    fixture_path: Path,
    fixture_data: dict[str, Any] | None,
    run_dir: Path | None,
    message: str,
) -> PromptLabBatchRow:
    data = fixture_data or {}
    cfg = _evaluation_config(data) if fixture_data else {"mode": "unknown"}
    row = PromptLabBatchRow(
        fixture_file=str(fixture_path),
        case_id=str(data.get("case_id") or fixture_path.stem),
        tier=infer_fixture_tier(fixture_path, fixture_data),
        label=str(data.get("label") or ""),
        evaluation_mode=str(cfg.get("mode") or "unknown"),
        status="error",
        expected_proposition_count=len(data.get("expected_propositions") or []),
        runtime_extraction_errors=[message],
        run_directory=str(run_dir.resolve()) if run_dir else None,
    )
    row.failure_themes = _classify_failure_themes(row=row, eval_result=None)
    return row


def run_prompt_lab_batch(
    *,
    output_root: str | Path,
    extraction_mode: FragmentExtractionMode = "local",
    fixture_dir: Path | None = None,
    fixture_paths: list[Path] | None = None,
    fixture_glob: str | None = None,
    limit: int | None = None,
    run_eval: bool = True,
    eval_only: bool = False,
    reapply_normalisation: bool = False,
    overwrite: bool = True,
    fail_fast: bool = False,
    max_propositions: int = 8,
    retry_empty_extraction: bool = True,
    extraction_output_mode: str | None = None,
    allow_output_mode_fallback: bool = False,
) -> PromptLabBatchResult:
    """Run extract-fragment (+ optional eval) for each discovered fixture."""
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    fixtures = discover_prompt_lab_fixtures(
        fixture_dir,
        fixture_paths=fixture_paths,
        fixture_glob=fixture_glob,
        limit=limit,
    )

    rows: list[PromptLabBatchRow] = []
    batch_failed = False

    for fixture_path in fixtures:
        run_dir = root / fixture_path.stem
        fixture_data: dict[str, Any] | None = None
        runtime_errors: list[str] = []

        try:
            fixture_data = load_prompt_lab_fixture(fixture_path)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            rows.append(_error_row(fixture_path=fixture_path, fixture_data=None, run_dir=None, message=str(exc)))
            batch_failed = True
            if fail_fast:
                break
            continue

        if (
            extraction_mode == "dry"
            and not eval_only
            and not _fixture_has_dry_output(fixture_data)
        ):
            rows.append(
                PromptLabBatchRow(
                    fixture_file=str(fixture_path),
                    case_id=str(fixture_data.get("case_id") or fixture_path.stem),
                    tier=infer_fixture_tier(fixture_path, fixture_data),
                    label=str(fixture_data.get("label") or ""),
                    evaluation_mode=str(_evaluation_config(fixture_data).get("mode") or "exhaustive"),
                    status="skipped",
                    expected_proposition_count=len(fixture_data.get("expected_propositions") or []),
                    warnings=["dry mode skipped: fixture has no dry.raw_model_output"],
                    failure_themes=["fixture_or_eval_policy_warning"],
                )
            )
            continue

        if run_dir.exists() and not overwrite and not eval_only:
            rows.append(
                PromptLabBatchRow(
                    fixture_file=str(fixture_path),
                    case_id=str(fixture_data.get("case_id") or fixture_path.stem),
                    tier=infer_fixture_tier(fixture_path, fixture_data),
                    label=str(fixture_data.get("label") or ""),
                    evaluation_mode=str(_evaluation_config(fixture_data).get("mode") or "exhaustive"),
                    status="skipped",
                    expected_proposition_count=len(fixture_data.get("expected_propositions") or []),
                    run_directory=str(run_dir.resolve()),
                    warnings=["skipped: run directory exists and --no-overwrite set"],
                    failure_themes=["fixture_or_eval_policy_warning"],
                )
            )
            continue

        if eval_only:
            if not run_dir.is_dir():
                rows.append(
                    _error_row(
                        fixture_path=fixture_path,
                        fixture_data=fixture_data,
                        run_dir=None,
                        message=f"eval-only: missing run directory {run_dir}",
                    )
                )
                batch_failed = True
                if fail_fast:
                    break
                continue
            if run_eval:
                try:
                    eval_result, _, _ = evaluate_and_write_prompt_lab_run(
                        fixture=fixture_data,
                        run_dir=run_dir,
                        reapply_normalisation=reapply_normalisation,
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        _error_row(
                            fixture_path=fixture_path,
                            fixture_data=fixture_data,
                            run_dir=run_dir,
                            message=f"eval failed: {exc}",
                        )
                    )
                    batch_failed = True
                    if fail_fast:
                        break
                    continue
            else:
                eval_result = evaluate_prompt_lab_extraction(fixture=fixture_data, run_dir=run_dir)
            row = _build_row_from_eval(
                fixture_path=fixture_path,
                fixture_data=fixture_data,
                run_dir=run_dir,
                eval_result=eval_result,
                workbench_result=None,
                runtime_errors=[],
            )
            rows.append(row)
            if row.status == "fail":
                batch_failed = True
                if fail_fast:
                    break
            continue

        workbench_result: FragmentWorkbenchResult | None = None
        try:
            workbench_result = run_extract_fragment_workbench(
                fixture_path=fixture_path,
                extraction_mode=extraction_mode,
                max_propositions=max_propositions,
                retry_empty_extraction=retry_empty_extraction,
                extraction_output_mode=extraction_output_mode,  # type: ignore[arg-type]
                allow_output_mode_fallback=allow_output_mode_fallback,
            )
            write_extract_fragment_workbench_outputs(workbench_result, run_dir)
            if workbench_result.workbench_status != "success":
                runtime_errors.extend(workbench_result.empty_reasons)
            if workbench_result.extraction_trace.get("validation_errors"):
                runtime_errors.extend(
                    str(x)
                    for x in workbench_result.extraction_trace.get("validation_errors") or []
                    if str(x).strip()
                )
        except Exception as exc:  # noqa: BLE001 — batch must continue
            rows.append(
                _error_row(
                    fixture_path=fixture_path,
                    fixture_data=fixture_data,
                    run_dir=run_dir if run_dir.exists() else None,
                    message=str(exc),
                )
            )
            batch_failed = True
            if fail_fast:
                break
            continue

        if run_eval:
            try:
                eval_result, _, _ = evaluate_and_write_prompt_lab_run(
                    fixture=fixture_data,
                    run_dir=run_dir,
                    reapply_normalisation=reapply_normalisation,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    _error_row(
                        fixture_path=fixture_path,
                        fixture_data=fixture_data,
                        run_dir=run_dir,
                        message=f"eval failed: {exc}",
                    )
                )
                batch_failed = True
                if fail_fast:
                    break
                continue
        else:
            eval_result = evaluate_prompt_lab_extraction(fixture=fixture_data, run_dir=run_dir)

        row = _build_row_from_eval(
            fixture_path=fixture_path,
            fixture_data=fixture_data,
            run_dir=run_dir,
            eval_result=eval_result,
            workbench_result=workbench_result,
            runtime_errors=runtime_errors,
        )
        rows.append(row)
        if row.status in {"fail", "error"}:
            batch_failed = True
            if fail_fast:
                break

    failure_themes = aggregate_failure_themes(rows)
    verdict, verdict_detail = compute_batch_verdict(rows)

    result = PromptLabBatchResult(
        output_root=str(root),
        mode=extraction_mode,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        fixture_count=len(rows),
        rows=rows,
        failure_themes=failure_themes,
        verdict=verdict,
        verdict_detail=verdict_detail,
    )
    write_prompt_lab_batch_summary(result, root)
    return result


def aggregate_failure_themes(rows: list[PromptLabBatchRow]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {key: [] for key, _ in _FAILURE_THEMES}
    for row in rows:
        case = row.case_id or row.fixture_file
        for theme in row.failure_themes:
            grouped.setdefault(theme, []).append(case)
    return {key: grouped.get(key, []) for key, _ in _FAILURE_THEMES if grouped.get(key)}


def compute_batch_verdict(rows: list[PromptLabBatchRow]) -> tuple[str, str]:
    if not rows:
        return "no_fixtures", "No fixtures were discovered or run."

    statuses = {row.status for row in rows}
    if statuses <= {"pass"}:
        return "all_pass", "All fixtures passed evaluation."

    if statuses <= {"pass", "warn", "skipped"}:
        return (
            "pass_with_warnings",
            "All runnable fixtures passed; some rows have warnings or were skipped.",
        )

    infra_themes = {"extraction_or_runtime_error", "table_evidence_salvage"}
    eval_policy_themes = {"fixture_or_eval_policy_warning"}
    prompt_themes = {
        "missing_expected_legal_effect",
        "wrong_boilerplate_classification",
        "unexpected_checkable_proposition",
        "missing_evidence_quote",
        "weak_subject_or_action",
        "missing_conditions_or_exceptions",
        "over_compressed_proposition",
    }

    all_themes: set[str] = set()
    for row in rows:
        all_themes.update(row.failure_themes)

    fail_rows = [row for row in rows if row.status == "fail"]
    extras_only_fails = [row for row in fail_rows if _row_is_extras_only_failure(row)]
    prompt_worthy_fails = [row for row in fail_rows if _row_suggests_prompt_change(row)]

    has_infra = bool(all_themes & infra_themes) or any(row.status == "error" for row in rows)
    has_eval_policy = bool(all_themes & eval_policy_themes) or bool(extras_only_fails)
    has_prompt = bool(prompt_worthy_fails) or (
        bool(all_themes & prompt_themes)
        and not extras_only_fails
        and not has_eval_policy
    )

    if has_infra and not has_prompt and not has_eval_policy:
        return (
            "failures_suggest_infrastructure_issue",
            "Failures look like extraction, parsing, or evidence-validation infrastructure issues.",
        )

    if fail_rows and len(extras_only_fails) >= len(fail_rows) / 2:
        detail_parts = [
            f"{len(extras_only_fails)} of {len(fail_rows)} failures matched all expected gold rows "
            "but failed on exhaustive proposition count or disallowed extras; review evaluation.mode "
            "and expected_propositions scope.",
        ]
        if prompt_worthy_fails:
            ids = ", ".join(row.case_id or row.fixture_file for row in prompt_worthy_fails)
            detail_parts.append(
                f"Also review substantive gaps (not extras-only): {ids}.",
            )
        classifier_rows = [
            row
            for row in fail_rows
            if row not in extras_only_fails and row not in prompt_worthy_fails
        ]
        if classifier_rows:
            ids = ", ".join(row.case_id or row.fixture_file for row in classifier_rows)
            detail_parts.append(
                f"Classifier or gold legal_effect_type mismatch (content likely present): {ids}.",
            )
        return "fixture_policy_review_needed", " ".join(detail_parts)

    if has_eval_policy and not has_prompt:
        return (
            "failures_require_fixture_or_eval_update",
            "Failures are mostly fixture/eval policy mismatches (counts, extras, gold expectations).",
        )
    if has_prompt:
        return (
            "failures_suggest_prompt_change",
            "Failures include unmatched expected propositions from omissions, weak matches, "
            "or mis-extracted legal structure.",
        )
    return (
        "failures_require_fixture_or_eval_update",
        "Some fixtures failed evaluation; review per-row status and failure themes.",
    )


def build_prompt_lab_summary_markdown(result: PromptLabBatchResult) -> str:
    lines = [
        "# Prompt-lab batch summary",
        "",
        f"**Verdict:** {result.verdict}",
        "",
        result.verdict_detail,
        "",
        f"- **Output root:** `{result.output_root}`",
        f"- **Mode:** `{result.mode}`",
        f"- **Fixtures run:** {result.fixture_count}",
        f"- **Generated:** {result.generated_at}",
        "",
        "## Results",
        "",
        "| Fixture | Tier | Mode | Status | Matched | Actual/Expected | Extras | Run dir |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result.rows:
        run_dir = f"`{row.run_directory}`" if row.run_directory else "—"
        lines.append(
            f"| `{Path(row.fixture_file).name}` | {row.tier} | {row.evaluation_mode} | "
            f"{row.status} | {row.matched_expected} | {row.actual_proposition_count}/"
            f"{row.expected_proposition_count} | {row.extra_actual_count} | {run_dir} |"
        )

    lines.extend(["", "## Failure themes", ""])
    any_theme = False
    for key, label in _FAILURE_THEMES:
        cases = result.failure_themes.get(key) or []
        if not cases:
            continue
        any_theme = True
        lines.append(f"### {label}")
        for case in cases:
            lines.append(f"- `{case}`")
        lines.append("")
    if not any_theme:
        lines.append("_No failure themes recorded._")
        lines.append("")

    lines.extend(["## Per-fixture detail", ""])
    for row in result.rows:
        lines.append(f"### `{Path(row.fixture_file).name}` — {row.status}")
        lines.append(f"- **Case:** {row.case_id}")
        lines.append(f"- **Label:** {row.label}")
        if row.runtime_extraction_errors:
            lines.append(f"- **Errors:** {'; '.join(row.runtime_extraction_errors)}")
        if row.warnings:
            lines.append(f"- **Warnings:** {'; '.join(row.warnings)}")
        if row.failure_themes:
            lines.append(f"- **Themes:** {', '.join(row.failure_themes)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_prompt_lab_batch_summary(result: PromptLabBatchResult, output_root: str | Path) -> tuple[Path, Path]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / PROMPT_LAB_SUMMARY_JSON
    md_path = root / PROMPT_LAB_SUMMARY_MD
    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(build_prompt_lab_summary_markdown(result), encoding="utf-8")
    return json_path, md_path
