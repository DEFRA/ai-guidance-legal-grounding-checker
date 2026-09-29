"""Classify fidelity failures into model vs deterministic origins (evaluation-only)."""

from __future__ import annotations

from typing import Any

from law_proposition_extractor_pipeline.proposition_fidelity.results import PropositionFidelityCaseResult

from .models import FailureOrigin, FailureOriginFinding


def _origin_for_dimension(
    dimension: str,
    *,
    status: str,
    detail: str,
    parse_ok: bool,
    validation_errors: list[str],
    json_repair_applied: bool,
    raw_row_count: int,
    final_count: int,
) -> FailureOrigin:
    if not parse_ok:
        return "response_format_error"
    detail_l = detail.lower()
    if "heading" in dimension or "structural_context" in dimension:
        if "evidence" in detail_l or "quote" in detail_l:
            return "model_evidence_error"
        return "model_structure_error"
    if dimension == "coverage" and status == "fail":
        if raw_row_count < final_count:
            return "deterministic_reconciliation_error"
        return "model_omission"
    if dimension == "coverage" and "unexpected" in detail_l:
        if any(
            marker in detail_l
            for marker in (
                "measured from the edge",
                "is measured from",
                "distance is measured",
                "measurement of",
            )
        ):
            # Source-grounded measurement restatement / dependent qualification —
            # not an unsupported invented claim.
            return "model_false_split"
        return "model_invention"
    if dimension == "atomicity" or dimension == "no_false_merge":
        return "model_false_merge"
    if dimension == "no_false_split":
        return "model_false_split"
    if dimension == "evidence_fidelity":
        return "model_evidence_error"
    if dimension in {
        "actor_fidelity",
        "action_fidelity",
        "object_fidelity",
        "condition_fidelity",
        "exception_fidelity",
        "threshold_fidelity",
        "cross_reference_fidelity",
        "legal_effect_fidelity",
    }:
        if validation_errors and any("evidence" in e.lower() for e in validation_errors):
            return "deterministic_validation_error"
        # Synonym-style action wording (shall/must) often needs human/gold review.
        if dimension == "action_fidelity" and (
            "shall" in detail_l or "must" in detail_l or "not preserved" in detail_l
        ):
            return "gold_or_evaluator_ambiguity"
        return "model_structure_error"
    if dimension == "completeness_fidelity":
        return "human_review_required"
    if json_repair_applied and "json" in detail_l:
        return "response_format_error"
    if validation_errors:
        return "deterministic_validation_error"
    return "human_review_required"


def classify_failures(
    *,
    case_id: str,
    repetition: int,
    pf: PropositionFidelityCaseResult,
    parse_ok: bool,
    validation_errors: list[str],
    json_repair_applied: bool,
    raw_rows: list[dict[str, Any]],
    final_props: list[dict[str, Any]],
) -> list[FailureOriginFinding]:
    findings: list[FailureOriginFinding] = []
    raw_summary = (
        f"{len(raw_rows)} raw rows"
        if raw_rows
        else "no raw rows (omission or parse failure)"
    )
    final_summary = f"{len(final_props)} final propositions"

    def _add(
        *,
        dimension: str,
        role: str | None,
        detail: str,
        expected: str,
        actual: str,
        status: str,
        severity: str,
    ) -> None:
        origin = _origin_for_dimension(
            dimension,
            status=status,
            detail=detail,
            parse_ok=parse_ok,
            validation_errors=validation_errors,
            json_repair_applied=json_repair_applied,
            raw_row_count=len(raw_rows),
            final_count=len(final_props),
        )
        findings.append(
            FailureOriginFinding(
                case_id=case_id,
                repetition=repetition,
                dimension=dimension,
                role=role,
                expected_invariant=expected or detail,
                raw_model_row_or_omission=raw_summary if status != "pass" else "n/a",
                validator_result="; ".join(validation_errors[:4]) or "ok",
                final_proposition_result=f"{final_summary}; actual={actual or status}",
                likely_origin=origin,  # type: ignore[arg-type]
                severity=severity,  # type: ignore[arg-type]
                detail=detail,
            )
        )

    for role in pf.role_results:
        for dim in role.dimension_results:
            if dim.status == "fail":
                _add(
                    dimension=dim.dimension,
                    role=role.role,
                    detail=dim.detail,
                    expected=dim.expected,
                    actual=dim.actual,
                    status=dim.status,
                    severity="critical",
                )
            elif dim.status == "warning":
                _add(
                    dimension=dim.dimension,
                    role=role.role,
                    detail=dim.detail,
                    expected=dim.expected,
                    actual=dim.actual,
                    status=dim.status,
                    severity="warning",
                )

    for dim in pf.dimension_results:
        if dim.status == "fail":
            _add(
                dimension=dim.dimension,
                role=None,
                detail=dim.detail,
                expected=dim.expected,
                actual=dim.actual,
                status=dim.status,
                severity="critical",
            )
        elif dim.status == "warning":
            _add(
                dimension=dim.dimension,
                role=None,
                detail=dim.detail,
                expected=dim.expected,
                actual=dim.actual,
                status=dim.status,
                severity="warning",
            )

    if pf.unexpected_propositions:
        unexpected_blob = str(pf.unexpected_propositions).lower()
        dependent_qualification = any(
            marker in unexpected_blob
            for marker in (
                "measured from the edge",
                "is measured from",
                "distance is measured",
                "measurement of",
            )
        )
        findings.append(
            FailureOriginFinding(
                case_id=case_id,
                repetition=repetition,
                dimension="coverage",
                role=None,
                expected_invariant=(
                    "no unexpected dependent qualification propositions"
                    if dependent_qualification
                    else "no unexpected operative propositions"
                ),
                raw_model_row_or_omission=raw_summary,
                validator_result="; ".join(validation_errors[:4]) or "ok",
                final_proposition_result=str(pf.unexpected_propositions)[:400],
                likely_origin=(
                    "model_false_split" if dependent_qualification else "model_invention"
                ),
                severity="critical",
                detail=(
                    f"{len(pf.unexpected_propositions)} unexpected dependent "
                    "qualification proposition(s)"
                    if dependent_qualification
                    else f"{len(pf.unexpected_propositions)} unexpected proposition(s)"
                ),
            )
        )

    return findings
