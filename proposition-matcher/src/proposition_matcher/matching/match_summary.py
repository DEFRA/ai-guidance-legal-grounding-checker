"""Proposition-level match assessment vs pair-level relationship.

``relationship`` on each match row is the outcome of one guidance–law pair.
It must never encode pipeline coverage such as "no law candidate".

Per guidance proposition we also record a ``GuidancePropositionMatchSummary``:
what happened across candidate discovery and all intended pair comparisons.
Absence of a comparison row is not proof that no candidate exists — only
explicit ``match_processing`` evidence can say whether retrieval ran, failed,
or found zero survivors.

``UNGROUNDED`` means a candidate pair was evaluated and rejected; it remains
available for audit but is not a reportable UI comparison.
"""

from __future__ import annotations

from typing import Any, Literal

# Execution state for one guidance proposition's match assessment.
AssessmentStatus = Literal["NOT_CHECKED", "COMPLETE", "PARTIAL", "FAILED"]

# Coverage among completed assessments only. Incomplete runs leave this null.
CoverageResult = Literal[
    "HAS_REPORTABLE_COMPARISON",
    "ONLY_UNGROUNDED_CANDIDATES",
    "NO_CANDIDATES_FOUND",
]

# Pair relationships that surface as reportable comparison rows (not audit-only).
# Mirrored in audit_assembler.match_summary — keep in sync via contract tests.
REPORTABLE_RELATIONSHIPS = frozenset({
    "GROUNDED",
    "GUIDANCE_BROADER",
    "GUIDANCE_INCOMPLETE",
    "CONFLICTS",
    "GUIDANCE_MISSING",
})

ClassificationOutcome = Literal["complete", "failed", "partial", "not_attempted"]


def normalise_relationship(raw: Any) -> str:
    """Canonical pair relationship label (CONFLICT → CONFLICTS)."""
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
    Winner = first occurrence in Matcher ``matches[]`` order (already ranked
    best-first by LABEL_PRIORITY). Returns ``(deduped, duplicates_dropped)``.
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


def classify_processing(
    *,
    candidate_count: int,
    classified_law_ids: set[str],
    survivor_law_ids: set[str],
    request_succeeded: bool,
    parse_succeeded: bool,
) -> tuple[ClassificationOutcome, str | None]:
    """Derive classification outcome from retrieval + group-rerank evidence.

    Retrieval with zero survivors needs no LLM call and is a successful
    complete assessment (coverage = NO_CANDIDATES_FOUND).
    """
    if candidate_count == 0:
        return "complete", None
    if not request_succeeded:
        return "failed", "group_rerank_request_failed"
    if not parse_succeeded:
        return "failed", "group_rerank_parse_failed"
    classified_survivors = classified_law_ids & survivor_law_ids
    if len(classified_survivors) < candidate_count:
        if classified_survivors:
            return "partial", "not_all_candidates_classified"
        return "partial", "no_candidates_classified"
    return "complete", None


def build_match_processing(
    *,
    candidate_count: int,
    classification: ClassificationOutcome,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Explicit pipeline evidence persisted on each results.json guidance row."""
    row: dict[str, Any] = {
        "candidate_count": candidate_count,
        "classification": classification,
    }
    if failure_reason:
        row["failure_reason"] = failure_reason
    return row


def summarise_guidance_proposition_match(
    *,
    guidance_proposition_id: str,
    match_processing: dict[str, Any] | None,
    matches: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build one proposition-level summary from explicit processing evidence + pairs.

    Without ``match_processing``, the assessment is ``NOT_CHECKED`` — empty
    ``matches`` alone must not become ``NO_CANDIDATES_FOUND``.
    """
    # Count distinct semantic pairs so summary agrees with assembled comparison output.
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

    # classification == complete
    if reportable_count > 0:
        coverage: CoverageResult | None = "HAS_REPORTABLE_COMPARISON"
    elif candidate_count > 0 and ungrounded_count > 0 and reportable_count == 0:
        # All evaluated pairs are UNGROUNDED (possibly with unknown labels normalised away).
        coverage = "ONLY_UNGROUNDED_CANDIDATES"
    elif candidate_count == 0:
        coverage = "NO_CANDIDATES_FOUND"
    elif ungrounded_count == 0 and reportable_count == 0:
        # Complete classification recorded zero rows — treat as inconclusive, not "no candidates".
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


def summarise_guidance_propositions(
    guidance_proposition_ids: list[str],
    entries_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Exactly one summary per guidance proposition in scope (order preserved)."""
    out: list[dict[str, Any]] = []
    for gp_id in guidance_proposition_ids:
        entry = entries_by_id.get(gp_id) or {}
        out.append(
            summarise_guidance_proposition_match(
                guidance_proposition_id=gp_id,
                match_processing=entry.get("match_processing"),
                matches=entry.get("matches"),
            )
        )
    return out


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
