"""Proposition-level match summaries for the content-audit frontend contract.

Canonical derivation rules live in ``proposition_matcher.matching.match_summary``.
This module re-derives from ``match_processing`` + current ``matches`` so Match
Adjudicator relationship edits stay reflected without trusting a possibly stale
``match_summary`` field on the matcher row.

Pair-level ``relationship`` stays on comparison records. Absence of a
comparison row is not proof of no candidates — only ``match_processing`` can say.
``UNGROUNDED`` is an evaluated-but-rejected pair, kept for audit, and is
intentionally absent from ``guidance-proposition-law-comparisons.json``.

``REPORTABLE_RELATIONSHIPS`` is mirrored from Proposition Matcher — contract-tested.
"""

from __future__ import annotations

from typing import Any, Literal

AssessmentStatus = Literal["NOT_CHECKED", "COMPLETE", "PARTIAL", "FAILED"]

CoverageResult = Literal[
    "HAS_REPORTABLE_COMPARISON",
    "ONLY_UNGROUNDED_CANDIDATES",
    "NO_CANDIDATES_FOUND",
]

# Mirrored from proposition_matcher.matching.match_summary.REPORTABLE_RELATIONSHIPS.
# Keep in sync via tests/test_reportable_contract.py.
REPORTABLE_RELATIONSHIPS = frozenset({
    "GROUNDED",
    "GUIDANCE_BROADER",
    "GUIDANCE_INCOMPLETE",
    "CONFLICTS",
    "GUIDANCE_MISSING",
})


def normalise_relationship(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    if value == "CONFLICT":
        return "CONFLICTS"
    return value


def is_reportable_relationship(raw: Any) -> bool:
    """Whether a pair relationship is a frontend-facing reportable comparison."""
    return normalise_relationship(raw) in REPORTABLE_RELATIONSHIPS


def law_proposition_id(match: dict[str, Any]) -> str | None:
    law_id = (match.get("law_proposition") or {}).get("id")
    return str(law_id) if law_id else None


def distinct_matches_by_law_id(
    matches: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate accidental repeat ``(guidance, law)`` rows.

    Semantic pair identity is ``(guidance_proposition_id, law_proposition_id)``.
    Winner = first occurrence in Matcher ``matches[]`` order (ranked best-first).
    Returns ``(deduped, duplicates_dropped)``.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates = 0
    for match in matches or []:
        law_id = law_proposition_id(match)
        if law_id is None:
            continue
        if law_id in seen:
            duplicates += 1
            continue
        seen.add(law_id)
        out.append(match)
    return out, duplicates


def summarise_guidance_proposition_match(
    *,
    guidance_proposition_id: str,
    match_processing: dict[str, Any] | None,
    matches: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    distinct, _ = distinct_matches_by_law_id(matches)
    relationships = [normalise_relationship(m.get("relationship")) for m in distinct]
    reportable_count = sum(1 for r in relationships if r in REPORTABLE_RELATIONSHIPS)
    ungrounded_count = sum(1 for r in relationships if r == "UNGROUNDED")

    if match_processing is None:
        return _summary(
            guidance_proposition_id,
            assessment_status="NOT_CHECKED",
            coverage_result=None,
            reportable_comparison_count=reportable_count,
            ungrounded_candidate_count=ungrounded_count,
            candidate_count=None,
        )

    candidate_count = int(match_processing.get("candidate_count", 0))
    classification = str(match_processing.get("classification") or "not_attempted")
    failure_reason = match_processing.get("failure_reason")

    if classification == "not_attempted":
        return _summary(
            guidance_proposition_id,
            assessment_status="NOT_CHECKED",
            coverage_result=None,
            reportable_comparison_count=reportable_count,
            ungrounded_candidate_count=ungrounded_count,
            candidate_count=candidate_count,
            failure_reason=failure_reason,
        )

    if classification == "failed":
        return _summary(
            guidance_proposition_id,
            assessment_status="FAILED",
            coverage_result=None,
            reportable_comparison_count=reportable_count,
            ungrounded_candidate_count=ungrounded_count,
            candidate_count=candidate_count,
            failure_reason=failure_reason,
        )

    if classification == "partial":
        return _summary(
            guidance_proposition_id,
            assessment_status="PARTIAL",
            coverage_result=None,
            reportable_comparison_count=reportable_count,
            ungrounded_candidate_count=ungrounded_count,
            candidate_count=candidate_count,
            failure_reason=failure_reason,
        )

    if reportable_count > 0:
        coverage: CoverageResult | None = "HAS_REPORTABLE_COMPARISON"
    elif candidate_count > 0 and ungrounded_count > 0 and reportable_count == 0:
        coverage = "ONLY_UNGROUNDED_CANDIDATES"
    elif candidate_count == 0:
        coverage = "NO_CANDIDATES_FOUND"
    elif ungrounded_count == 0 and reportable_count == 0:
        coverage = None
    else:
        coverage = "ONLY_UNGROUNDED_CANDIDATES"

    return _summary(
        guidance_proposition_id,
        assessment_status="COMPLETE",
        coverage_result=coverage,
        reportable_comparison_count=reportable_count,
        ungrounded_candidate_count=ungrounded_count,
        candidate_count=candidate_count,
        failure_reason=failure_reason,
    )


def build_guidance_proposition_match_summaries(
    matcher_output: list[dict],
    guidance_row_ids: list[str | None],
) -> list[dict[str, Any]]:
    """One summary per guidance proposition emitted to the frontend (stable id order)."""
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry, gp_id in zip(matcher_output, guidance_row_ids, strict=True):
        if gp_id is None or gp_id in seen:
            continue
        seen.add(gp_id)
        summaries.append(
            summarise_guidance_proposition_match(
                guidance_proposition_id=gp_id,
                match_processing=entry.get("match_processing"),
                matches=entry.get("matches"),
            )
        )
    return summaries


def _summary(
    guidance_proposition_id: str,
    *,
    assessment_status: AssessmentStatus,
    coverage_result: CoverageResult | None,
    reportable_comparison_count: int,
    ungrounded_candidate_count: int,
    candidate_count: int | None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "guidance_proposition_id": guidance_proposition_id,
        "assessment_status": assessment_status,
        "coverage_result": coverage_result,
        "reportable_comparison_count": reportable_comparison_count,
        "ungrounded_candidate_count": ungrounded_candidate_count,
        "candidate_count": candidate_count,
    }
    if failure_reason:
        row["failure_reason"] = failure_reason
    return row
