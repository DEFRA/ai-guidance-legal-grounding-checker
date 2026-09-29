"""Orchestrate live proposition calibration (evaluation-only; permits live model calls)."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from law_proposition_extractor_llm.client import JuditLLMClient
from law_proposition_extractor_pipeline.extract import EXTRACTION_PROMPT_VERSION
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import (
    load_proposition_fidelity_cases,
)
from law_proposition_extractor_pipeline.proposition_fidelity.results import (
    accumulate_dimension,
    empty_dimension_totals,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

from .artifacts import write_json
from .evaluate import evaluate_live_propositions
from .extract_live import (
    resolve_model_provenance,
    run_live_article_49a,
    run_live_dry_fragment,
)
from .failure_origins import classify_failures
from .gates import analyse_case_repeatability, props_fingerprint, raw_fingerprint
from .models import (
    FailureOriginFinding,
    LiveCalibrationRepetitionResult,
    LivePropositionCalibrationResult,
)
from .paths import (
    CALIBRATION_CASES,
    REPETITIONS,
    call_artifact_name,
    calls_dir,
    run_dir,
)
from .recording_client import RecordingJuditLLMClient
from .report import render_calibration_report, render_docs_page

_DEPENDENT_QUALIFICATION_MARKERS = (
    "measured from the edge",
    "is measured from",
    "distance is measured",
    "measurement of",
)


def _looks_like_dependent_qualification_unexpected(unexpected: list[Any]) -> bool:
    """True when unexpected rows look like source-grounded measurement restatements."""
    if not unexpected:
        return False
    for row in unexpected:
        if isinstance(row, dict):
            blob = " ".join(
                str(row.get(k) or "")
                for k in ("proposition_text", "legal_effect_type", "fragment_locator")
            ).lower()
        else:
            blob = str(row).lower()
        if any(marker in blob for marker in _DEPENDENT_QUALIFICATION_MARKERS):
            return True
        if "definition" in blob and "metre" in blob:
            return True
    return False


def _apply_repetition_gates(
    *,
    pf_status: str,
    parse_status: str,
    heading_boundary: dict[str, Any],
    unexpected: list[Any],
    failure_origins: list[Any],
) -> tuple[str, str, list[str]]:
    critical_failures: list[str] = []
    if parse_status != "ok":
        critical_failures.append("unparseable_or_missing_response")
    hb = heading_boundary or {}
    if hb.get("heading_only_proposition"):
        critical_failures.append("heading_only_proposition")
    if hb.get("heading_only_evidence"):
        critical_failures.append("heading_only_evidence")
    if hb.get("heading_material_expansion"):
        critical_failures.append("heading_material_expansion")
    if unexpected:
        if _looks_like_dependent_qualification_unexpected(unexpected):
            critical_failures.append(
                "unexpected_dependent_qualification_proposition"
            )
        else:
            critical_failures.append("invented_operative_proposition")
    for fo in failure_origins:
        if getattr(fo, "severity", None) == "critical" and fo.dimension == "threshold_fidelity":
            critical_failures.append("unsupported_numerical_threshold")
        if getattr(fo, "dimension", None) == "structural_context_boundary" and getattr(
            fo, "severity", None
        ) == "critical":
            critical_failures.append("cross_provision_heading_leakage")

    critical_gate = "fail" if critical_failures else "pass"
    case_fidelity = (
        "pass"
        if critical_gate == "pass" and pf_status in {"pass", "warning"} and not unexpected
        else "fail"
    )
    return critical_gate, case_fidelity, critical_failures


def _compact_props(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in props:
        meta = p.get("extraction_debug_meta") if isinstance(p.get("extraction_debug_meta"), dict) else {}
        out.append(
            {
                "id": p.get("id"),
                "fragment_locator": p.get("fragment_locator"),
                "legal_effect_type": p.get("legal_effect_type"),
                "proposition_text": p.get("proposition_text"),
                "legal_subject": p.get("legal_subject"),
                "action": p.get("action"),
                "conditions": p.get("conditions"),
                "label": p.get("label"),
                "evidence_quote": meta.get("evidence_quote"),
                "structured_list_path": meta.get("structured_list_path"),
                "completeness_status": meta.get("completeness_status") or p.get("completeness_status"),
                "display_label": meta.get("display_label"),
            }
        )
    return out


def _dimension_highlights(pf_dict: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for role in pf_dict.get("role_results") or []:
        for dim in role.get("dimension_results") or []:
            if dim.get("status") in {"fail", "warning"}:
                rows.append(
                    f"{role.get('role')}/{dim.get('dimension')}: {dim.get('status')} — {dim.get('detail')}"
                )
    for dim in pf_dict.get("dimension_results") or []:
        if dim.get("status") in {"fail", "warning"}:
            rows.append(
                f"case/{dim.get('dimension')}: {dim.get('status')} — {dim.get('detail')}"
            )
    return rows


def run_live_proposition_calibration(
    *,
    calibration_run_id: str | None = None,
    root: Path | None = None,
    llm_client: JuditLLMClient | RecordingJuditLLMClient | None = None,
    write_docs: bool = True,
    work_dir: Path | None = None,
) -> LivePropositionCalibrationResult:
    started = perf_counter()
    base_root = root or judit_root()
    run_id = calibration_run_id or datetime.now(UTC).strftime("live-pf-%Y%m%dT%H%M%SZ")
    out = run_dir(run_id, root=base_root)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calls").mkdir(parents=True, exist_ok=True)

    inner = llm_client if isinstance(llm_client, JuditLLMClient) else (llm_client.inner if isinstance(llm_client, RecordingJuditLLMClient) else JuditLLMClient())
    recorder = llm_client if isinstance(llm_client, RecordingJuditLLMClient) else RecordingJuditLLMClient(inner=inner)
    model_info = resolve_model_provenance(recorder)

    all_cases = load_proposition_fidelity_cases(root=base_root)
    by_id = {c.case_id: c for c in all_cases}
    missing = [c for c in CALIBRATION_CASES if c not in by_id]
    if missing:
        raise LookupError(f"calibration cases missing from PF manifest: {missing}")

    case_results = []
    critical_failures: list[str] = []
    warnings: list[str] = []
    dim_totals = empty_dimension_totals()
    call_summaries: list[dict[str, Any]] = []
    provider_calls = 0
    provider_retries = 0
    tmp_root = work_dir or Path(tempfile.mkdtemp(prefix="live-pf-work-"))

    for case_id in CALIBRATION_CASES:
        case = by_id[case_id]
        rep_results: list[LiveCalibrationRepetitionResult] = []
        raw_fps: list[str] = []
        prop_fps: list[str] = []

        for repetition in REPETITIONS:
            # Fresh recorder window per call artifact — keep global list for totals.
            call_offset = len(recorder.calls)
            if case.runner == "article_49a_pipeline":
                extract = run_live_article_49a(
                    case,
                    llm_client=recorder,
                    work_dir=tmp_root / f"{case_id}-r{repetition}",
                )
            else:
                # Isolate call list for dry fragment by using a nested recorder? Keep shared.
                # Reset isn't needed — we slice provider_calls from offset.
                nested = RecordingJuditLLMClient(inner=recorder.inner)
                extract = run_live_dry_fragment(case, llm_client=nested)
                # Merge nested calls into parent recorder for totals.
                recorder.calls.extend(nested.calls)
                extract.provider_calls = [c.to_dict() for c in nested.calls]

            pf = evaluate_live_propositions(
                case,
                extract.props,
                operative_text=extract.operative_text,
                heading_text=extract.heading_text or case.heading_text,
                diagnostics=extract.diagnostics,
                article_49a_bundle=extract.article_49a_bundle,
            )
            pf_dict = pf.to_dict()

            origins = classify_failures(
                case_id=case_id,
                repetition=repetition,
                pf=pf,
                parse_ok=extract.parse_status == "ok",
                validation_errors=extract.validation_errors,
                json_repair_applied=extract.json_repair_applied,
                raw_rows=extract.raw_rows,
                final_props=extract.props,
            )
            crit_gate, fidelity_gate, crit_msgs = _apply_repetition_gates(
                pf_status=pf.case_status,
                parse_status=extract.parse_status,
                heading_boundary=extract.heading_boundary,
                unexpected=pf.unexpected_propositions,
                failure_origins=origins,
            )
            for msg in crit_msgs:
                critical_failures.append(f"{case_id}/r{repetition}: {msg}")
            for role in pf.role_results:
                for dim in role.dimension_results:
                    accumulate_dimension(dim_totals, dim)
                    if dim.status == "warning":
                        warnings.append(
                            f"{case_id}/r{repetition}/{role.role}/{dim.dimension}: {dim.detail}"
                        )
                    elif dim.status == "fail":
                        critical_failures.append(
                            f"{case_id}/r{repetition}/{role.role}/{dim.dimension}: {dim.detail}"
                        )
            for dim in pf.dimension_results:
                accumulate_dimension(dim_totals, dim)
                if dim.status == "warning":
                    warnings.append(f"{case_id}/r{repetition}/case/{dim.dimension}: {dim.detail}")
                elif dim.status == "fail":
                    critical_failures.append(
                        f"{case_id}/r{repetition}/case/{dim.dimension}: {dim.detail}"
                    )

            # Article 49a downstream relationship invariants
            if extract.article_49a_detail:
                detail = extract.article_49a_detail
                if detail.get("triggered_by_count", 0) != 1:
                    critical_failures.append(
                        f"{case_id}/r{repetition}: triggered_by_count="
                        f"{detail.get('triggered_by_count')} (expected 1)"
                    )
                    fidelity_gate = "fail"
                    origins.append(
                        FailureOriginFinding(
                            case_id=case_id,
                            repetition=repetition,
                            dimension="legal_effect_fidelity",
                            role="inspection-trigger",
                            expected_invariant="triggered_by ×1",
                            raw_model_row_or_omission="see paragraph-3 raw rows",
                            validator_result="n/a",
                            final_proposition_result=(
                                f"triggered_by={detail.get('triggered_by_count')}"
                            ),
                            likely_origin="human_review_required",
                            severity="critical",
                            detail=(
                                "expected triggered_by relationship missing "
                                "after live extraction"
                            ),
                        )
                    )
                if detail.get("exception_to_count", 0) != 3:
                    critical_failures.append(
                        f"{case_id}/r{repetition}: exception_to_count="
                        f"{detail.get('exception_to_count')} (expected 3)"
                    )
                    fidelity_gate = "fail"
                if not detail.get("paragraph_1_group_ok") or not detail.get(
                    "paragraph_2_group_ok"
                ):
                    critical_failures.append(
                        f"{case_id}/r{repetition}: legal_rule_group invariant failed "
                        f"(p1={detail.get('paragraph_1_group_ok')} "
                        f"p2={detail.get('paragraph_2_group_ok')})"
                    )
                    fidelity_gate = "fail"

            # UK threshold grounding check
            if case_id == "uk_regulation_12_spread":
                op = extract.operative_text.lower()
                for prop in extract.props:
                    meta = (
                        prop.get("extraction_debug_meta")
                        if isinstance(prop.get("extraction_debug_meta"), dict)
                        else {}
                    )
                    blob = (
                        f"{prop.get('proposition_text')} {meta.get('evidence_quote')}".lower()
                    )
                    if "10" in blob and "10 metre" not in op and "10 metres" not in op:
                        critical_failures.append(
                            f"{case_id}/r{repetition}: "
                            "unsupported_numerical_threshold_from_non_operative"
                        )
                        crit_gate = "fail"
                        fidelity_gate = "fail"

            rep = LiveCalibrationRepetitionResult(
                repetition=repetition,
                raw_response_status=extract.raw_response_status,
                parse_status=extract.parse_status,
                validation_status=extract.validation_status,
                proposition_count=len(extract.props),
                benchmark_result=pf_dict,
                latency_seconds=extract.latency_seconds,
                token_usage=extract.token_usage,
                diagnostics=extract.diagnostics,
                provider_call_count=len(extract.provider_calls),
                provider_retry_count=extract.provider_retry_count,
                json_repair_applied=extract.json_repair_applied,
                heading_boundary=extract.heading_boundary,
                article_49a_detail=extract.article_49a_detail,
                failure_origins=origins,
                critical_gate=crit_gate,  # type: ignore[arg-type]
                case_fidelity_gate=fidelity_gate,  # type: ignore[arg-type]
            )
            rep_results.append(rep)
            raw_fps.append(raw_fingerprint(extract.raw_responses))
            prop_fps.append(props_fingerprint(extract.props))
            provider_calls += len(extract.provider_calls)
            provider_retries += extract.provider_retry_count

            call_payload = {
                "calibration_run_id": run_id,
                "case_id": case_id,
                "repetition": repetition,
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "prompt_template_identifier": model_info.get("prompt_template_identifier"),
                "model_alias": extract.model_alias or model_info.get("configured_model_alias"),
                "resolved_provider_model": extract.resolved_model
                or model_info.get("resolved_provider_model"),
                "request_parameters": extract.request_parameters,
                "source_snapshot_id": extract.source_snapshot_id,
                "source_fragment_ids": extract.source_fragment_ids,
                "required_locators": extract.required_locators,
                "focus_terms": extract.focus_terms,
                "started_at": extract.provider_calls[0]["started_at"]
                if extract.provider_calls
                else None,
                "ended_at": extract.provider_calls[-1]["ended_at"]
                if extract.provider_calls
                else None,
                "latency_seconds": extract.latency_seconds,
                "token_usage": extract.token_usage,
                "provider_request_ids": [
                    c.get("provider_request_id")
                    for c in extract.provider_calls
                    if c.get("provider_request_id")
                ],
                "provider_calls": extract.provider_calls,
                "raw_structured_response": extract.raw_responses,
                "json_repair_applied": extract.json_repair_applied,
                "json_repair_method": extract.json_repair_method,
                "parser_result": {
                    "parse_status": extract.parse_status,
                    "raw_row_count": len(extract.raw_rows),
                },
                "validation_diagnostics": extract.validation_errors,
                "validation_status": extract.validation_status,
                "raw_rows": extract.raw_rows,
                "validated_rows": extract.validated_rows,
                "rejected_rows": extract.rejected_rows,
                "final_propositions": _compact_props(extract.props),
                "benchmark_result": pf_dict,
                "heading_boundary": extract.heading_boundary,
                "article_49a_detail": extract.article_49a_detail,
                "failure_origins": [f.to_dict() for f in origins],
                "operative_source_excerpt": extract.operative_text[:2000],
                "legislative_heading": extract.heading_text or case.heading_text,
                "prompt_text": extract.prompt_text,
                "diagnostics": extract.diagnostics,
            }
            write_json(
                calls_dir(run_id, root=base_root) / call_artifact_name(case_id, repetition),
                call_payload,
            )
            call_summaries.append(
                {
                    "case_id": case_id,
                    "repetition": repetition,
                    "source_locator": case.source_locator,
                    "legislative_heading": case.heading_text,
                    "operative_source_excerpt": extract.operative_text[:1200],
                    "expected_roles": [g.role for g in case.gold],
                    "raw_model_rows_json": json.dumps(extract.raw_rows, sort_keys=True, indent=2)[:4000],
                    "retained_propositions_json": json.dumps(
                        _compact_props(extract.props), sort_keys=True, indent=2
                    )[:4000],
                    "rejected_rows": extract.rejected_rows,
                    "diagnostics": extract.diagnostics,
                    "case_status": pf.case_status,
                    "dimension_highlights": _dimension_highlights(pf_dict),
                }
            )
            _ = call_offset  # retained for potential future delta accounting

        case_result = analyse_case_repeatability(
            case_id,
            [g.role for g in case.gold],
            rep_results,
            raw_fingerprints=raw_fps,
            prop_fingerprints=prop_fps,
        )
        case_results.append(case_result)

    # Promotion candidates: one green rep per case if any
    promotion: list[dict[str, Any]] = []
    for case_result in case_results:
        for rep in case_result.repetitions:
            if (
                rep.critical_gate == "pass"
                and rep.case_fidelity_gate == "pass"
                and rep.parse_status == "ok"
                and (rep.benchmark_result or {}).get("case_status") in {"pass", "warning"}
                and not (rep.benchmark_result or {}).get("missing_roles")
                and not (rep.benchmark_result or {}).get("unexpected_propositions")
            ):
                promotion.append(
                    {
                        "case_id": case_result.case_id,
                        "repetition": rep.repetition,
                        "reason": (
                            "Fully green live prompt-v3 response suitable as a future "
                            "curated regression fixture (not promoted automatically)."
                        ),
                        "call_artifact": call_artifact_name(
                            case_result.case_id, rep.repetition
                        ),
                    }
                )
                break

    result = LivePropositionCalibrationResult(
        calibration_run_id=run_id,
        model=model_info,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        cases=case_results,
        totals={
            "cases": len(case_results),
            "case_repetitions": len(case_results) * len(REPETITIONS),
            "critical_gate_failures": sum(
                1
                for c in case_results
                for r in c.repetitions
                if r.critical_gate == "fail"
            ),
            "case_fidelity_failures": sum(
                1 for c in case_results if c.case_fidelity_gate == "fail"
            ),
            "repeatability_failures": sum(
                1 for c in case_results if c.repeatability_gate == "fail"
            ),
            "warnings": len(warnings),
        },
        repeatability={
            "cases": [
                {
                    "case_id": c.case_id,
                    "stability": c.stability,
                    "case_fidelity_gate": c.case_fidelity_gate,
                    "repeatability_gate": c.repeatability_gate,
                    "proposition_count_variance": c.proposition_count_variance,
                }
                for c in case_results
            ]
        },
        critical_failures=sorted(set(critical_failures)),
        warnings=warnings,
        dimension_totals=dim_totals,
        promotion_candidates=promotion,
        runtime_seconds=round(perf_counter() - started, 3),
        provider_call_count=provider_calls,
        provider_retry_count=provider_retries,
        estimated_cost_usd=None,
    )

    manifest = {
        "calibration_run_id": run_id,
        "calibration_timestamp": datetime.now(UTC).isoformat(),
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "prompt_template_identifier": model_info.get("prompt_template_identifier"),
        "model": model_info,
        "cases": list(CALIBRATION_CASES),
        "repetitions": list(REPETITIONS),
        "case_repetitions": len(CALIBRATION_CASES) * len(REPETITIONS),
        "provider_call_count": provider_calls,
        "provider_retry_count": provider_retries,
        "artifact_layout": {
            "manifest": "calibration_manifest.json",
            "calls": "calls/<case>-<repetition>.json",
            "result": "calibration_result.json",
            "report": "calibration_report.md",
        },
        "notes": [
            "Evaluation-only live calibration. Does not modify production prompts or curated fixtures.",
            "Article 49a issues three production required-locator LLM calls per case-repetition.",
            "No LLM judge. No chain-of-thought stored.",
        ],
    }
    write_json(out / "calibration_manifest.json", manifest)
    write_json(out / "calibration_result.json", result.to_dict())
    report = render_calibration_report(result, manifest=manifest, call_summaries=call_summaries)
    (out / "calibration_report.md").write_text(report, encoding="utf-8")

    if write_docs:
        docs_path = base_root / "docs/explainability/live-proposition-calibration.md"
        docs_path.write_text(
            render_docs_page(result, manifest=manifest), encoding="utf-8"
        )

    return result


def inspect_calibration_run(run_id: str, *, root: Path | None = None) -> str:
    from .artifacts import load_calibration_result, load_manifest

    result = load_calibration_result(run_id, root=root)
    manifest = load_manifest(run_id, root=root)
    return render_calibration_report(result, manifest=manifest)


def check_calibration_run(run_id: str, *, root: Path | None = None) -> list[str]:
    from .artifacts import validate_calibration_artifacts

    return validate_calibration_artifacts(run_id, root=root, expect_complete=True)
