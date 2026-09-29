from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from law_discovery.ai import (
    AdaAIConfigurationError,
    AITriageStats,
    CandidateRelevanceAssessment,
    CandidateTriageAssessment,
    _uncertain_triage_assessment,
    assess_candidate_with_ai,
    load_ai_settings,
    triage_candidates_with_ai,
)
from law_discovery.lex_adapter import LexAdapter, LexAdapterError, normalise_lex_result_to_candidate
from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    Confidence,
    DiscoveryRun,
    RelationshipToCategory,
    ReviewStatus,
    SourceRegister,
)
from law_discovery.progress import DiscoveryProgressEvent, ProgressCallback, emit_progress
from law_discovery.query_plan import build_query_plan
from law_discovery.scoring import deduplicate_candidates, score_candidates
from law_discovery.triage_helpers import normalize_triage_assessment, triage_metadata_from_assessment

_NETWORK_DISABLED_WARNING = "Network discovery was disabled."

_RELEVANCE_TO_CONFIDENCE: dict[str, Confidence] = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "not_relevant": "low",
    "uncertain": "unknown",
}


def _default_run_id() -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"law-discovery-run-{timestamp}"


def _append_note(existing: str | None, addition: str) -> str:
    if existing and existing.strip():
        return f"{existing.strip()}\n\n{addition}"
    return addition


def _format_ai_notes(assessment: CandidateRelevanceAssessment) -> str:
    sections = [f"AI rationale: {assessment.rationale}"]
    if assessment.useful_evidence:
        evidence_lines = "\n".join(f"- {item}" for item in assessment.useful_evidence)
        sections.append(f"Useful evidence:\n{evidence_lines}")
    if assessment.false_positive_risks:
        risk_lines = "\n".join(f"- {item}" for item in assessment.false_positive_risks)
        sections.append(f"False positive risks:\n{risk_lines}")
    return "\n\n".join(sections)


_RECOMMENDED_ACTION_TO_REVIEW: dict[str, ReviewStatus] = {
    "accept_candidate": "accepted",
    "reject_candidate": "rejected",
    "park": "parked",
    "needs_more_research": "needs_more_research",
}


def _format_triage_notes(assessment: CandidateTriageAssessment) -> str:
    sections = [
        f"AI triage rationale: {assessment.rationale}",
        f"AI triage relevance: {assessment.relevance}",
        f"AI triage review_priority: {assessment.review_priority}",
        f"AI triage recommended_action: {assessment.recommended_action}",
    ]
    if assessment.supporting_signals:
        signal_lines = "\n".join(f"- {item}" for item in assessment.supporting_signals)
        sections.append(f"Supporting signals:\n{signal_lines}")
    if assessment.false_positive_risks:
        risk_lines = "\n".join(f"- {item}" for item in assessment.false_positive_risks)
        sections.append(f"False positive risks:\n{risk_lines}")
    if assessment.evidence_limitations:
        limitation_lines = "\n".join(f"- {item}" for item in assessment.evidence_limitations)
        sections.append(f"Evidence limitations:\n{limitation_lines}")
    return "\n\n".join(sections)


def apply_triage_assessment_to_candidate(
    candidate: CandidateSource,
    assessment: CandidateTriageAssessment,
    apply_recommended_review_status: bool = False,
) -> CandidateSource:
    """Merge AI triage assessment into a candidate without auto-accepting by default."""
    assessment = normalize_triage_assessment(assessment)

    relationship: RelationshipToCategory = candidate.relationship_to_category
    if assessment.relationship_to_category != "unknown":
        relationship = assessment.relationship_to_category

    review_status: ReviewStatus = candidate.review_status
    if apply_recommended_review_status:
        review_status = _RECOMMENDED_ACTION_TO_REVIEW[assessment.recommended_action]

    confidence: Confidence = assessment.confidence_after_ai
    if assessment.relevance == "not_relevant":
        confidence = "low"
    if (
        assessment.review_priority == "likely_reject"
        and assessment.recommended_action == "reject_candidate"
        and assessment.relevance != "uncertain"
    ):
        confidence = "low"
    if confidence != assessment.confidence_after_ai:
        assessment = assessment.model_copy(update={"confidence_after_ai": confidence})

    return candidate.model_copy(
        update={
            "confidence": confidence,
            "relationship_to_category": relationship,
            "review_status": review_status,
            "ai_triage": triage_metadata_from_assessment(assessment),
            "notes": _append_note(candidate.notes, _format_triage_notes(assessment)),
        }
    )


def apply_ai_assessment_to_candidate(
    candidate: CandidateSource,
    assessment: CandidateRelevanceAssessment,
    allow_ai_rejection: bool = False,
) -> CandidateSource:
    """Merge AI relevance assessment into a candidate without auto-accepting."""
    confidence = _RELEVANCE_TO_CONFIDENCE[assessment.relevance]
    relationship: RelationshipToCategory = candidate.relationship_to_category
    if assessment.relationship_to_category != "unknown":
        relationship = assessment.relationship_to_category

    review_status: ReviewStatus = candidate.review_status
    if allow_ai_rejection and assessment.relevance == "not_relevant":
        review_status = "rejected"

    return candidate.model_copy(
        update={
            "confidence": confidence,
            "relationship_to_category": relationship,
            "review_status": review_status,
            "notes": _append_note(candidate.notes, _format_ai_notes(assessment)),
        }
    )


def assess_candidates_with_ai(
    category: CategoryBrief,
    candidates: list[CandidateSource],
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    allow_ai_rejection: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> list[CandidateSource]:
    """Assess each candidate with AI and apply structured mapping."""
    total = len(candidates)
    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_assess_start",
            message="Starting AI assessment",
            total=total,
            extra={"candidate_count": total},
        ),
    )
    assessed: list[CandidateSource] = []
    for index, candidate in enumerate(candidates, start=1):
        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="ai_assess_candidate",
                message=candidate.title,
                current=index,
                total=total,
                extra={"title": candidate.title, "source_id": candidate.source_id},
            ),
        )
        try:
            assessment = assess_candidate_with_ai(
                category,
                candidate,
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
            )
            assessed.append(
                apply_ai_assessment_to_candidate(
                    candidate,
                    assessment,
                    allow_ai_rejection=allow_ai_rejection,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep candidate on individual AI failure
            warning_note = f"AI assessment failed: {exc}"
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(stage="warning", message=warning_note),
            )
            assessed.append(
                candidate.model_copy(
                    update={"notes": _append_note(candidate.notes, warning_note)},
                )
            )
    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_assess_complete",
            message=f"Assessed {total} candidates with AI",
            extra={"candidate_count": total},
        ),
    )
    return assessed


def triage_and_apply_candidates_with_ai(
    category: CategoryBrief,
    candidates: list[CandidateSource],
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = 15,
    apply_recommended_review_status: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[CandidateSource], AITriageStats]:
    """Batch-triage candidates with AI and apply structured mapping."""
    stats = AITriageStats(ai_triage_requested=True)
    if not candidates:
        return [], stats

    effective_batch_size = max(1, batch_size)
    batch_count = (len(candidates) + effective_batch_size - 1) // effective_batch_size
    candidate_count = len(candidates)
    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_triage_start",
            message="Starting AI triage",
            total=candidate_count,
            extra={
                "candidate_count": candidate_count,
                "batch_count": batch_count,
                "batch_size": effective_batch_size,
                "unit": "candidates",
            },
        ),
    )

    triaged: list[CandidateSource] = []
    for batch_index, offset in enumerate(range(0, len(candidates), effective_batch_size), start=1):
        batch_candidates = candidates[offset : offset + effective_batch_size]
        candidates_done = offset + len(batch_candidates)
        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="ai_triage_batch",
                message=f"Triage batch {batch_index}/{batch_count}",
                current=candidates_done,
                total=candidate_count,
                extra={
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "batch_size": len(batch_candidates),
                    "candidate_count": candidate_count,
                    "unit": "candidates",
                },
            ),
        )
        assessments, batch_stats = triage_candidates_with_ai(
            category,
            batch_candidates,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            batch_size=len(batch_candidates),
        )
        stats.merge(batch_stats)
        assessment_by_id = {item.source_id: item for item in assessments}
        for candidate in batch_candidates:
            assessment = assessment_by_id.get(candidate.source_id)
            if assessment is None:
                assessment = _uncertain_triage_assessment(
                    candidate,
                    limitation="Missing triage assessment after batch processing.",
                )
                stats.ai_triage_fallback_candidate_count += 1
            triaged.append(
                apply_triage_assessment_to_candidate(
                    candidate,
                    assessment,
                    apply_recommended_review_status=apply_recommended_review_status,
                )
            )

    if stats.ai_triage_failed:
        complete_message = (
            "AI triage failed for all batches (fallback assessments only)"
        )
    elif stats.ai_triage_partial:
        complete_message = (
            f"AI triage partially failed "
            f"({stats.ai_triage_failed_batch_count}/{stats.ai_triage_batch_count} "
            "batches failed)"
        )
    else:
        complete_message = f"Triaged {len(candidates)} candidates with AI"

    emit_progress(
        progress_callback,
        DiscoveryProgressEvent(
            stage="ai_triage_complete",
            message=complete_message,
            extra={
                "candidate_count": len(candidates),
                "batch_count": batch_count,
                "ai_triage_failed": stats.ai_triage_failed,
                "ai_triage_partial": stats.ai_triage_partial,
            },
        ),
    )
    return triaged, stats


class DiscoveryService:
    """Orchestrate query planning, Lex discovery, scoring, and optional AI assessment."""

    def __init__(self, lex_adapter: LexAdapter | None = None) -> None:
        self._lex_adapter = lex_adapter

    def run_discovery(
        self,
        category: CategoryBrief,
        run_id: str | None = None,
        limit_per_query: int = 10,
        use_network: bool = True,
        expansion: object | None = None,
        use_ai_assessment: bool = False,
        use_ai_triage: bool = False,
        ai_triage_batch_size: int = 15,
        apply_ai_review_status: bool = False,
        ai_model_name: str | None = None,
        litellm_base_url: str | None = None,
        litellm_api_key: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> DiscoveryRun:
        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(stage="build_query_plan", message="Building query plan..."),
        )
        query_plan = build_query_plan(category, expansion=expansion)
        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="build_query_plan",
                message=f"Built {len(query_plan)} queries",
                extra={
                    "query_count": len(query_plan),
                    "queries": [query.query for query in query_plan],
                },
            ),
        )
        warnings: list[str] = []
        candidate_sources: list[CandidateSource] = []
        successful_query_count = 0
        failed_query_count = 0

        if not use_network:
            warnings.append(_NETWORK_DISABLED_WARNING)
        else:
            adapter = self._lex_adapter or LexAdapter()
            adapter.require_base_url()
            raw_candidates: list[CandidateSource] = []
            total_queries = len(query_plan)
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="lex_search_start",
                    message="Searching Lex",
                    total=total_queries,
                ),
            )
            for index, query in enumerate(query_plan, start=1):
                emit_progress(
                    progress_callback,
                    DiscoveryProgressEvent(
                        stage="lex_search_query",
                        message=query.query,
                        current=index,
                        total=total_queries,
                        extra={"query": query.query},
                    ),
                )
                try:
                    lex_results = adapter.search(query.query, limit=limit_per_query)
                except LexAdapterError as exc:
                    failed_query_count += 1
                    warning = (
                        f"Lex search failed for query {query.query!r}: {exc}. "
                        "Discovery continued with remaining queries."
                    )
                    warnings.append(warning)
                    emit_progress(
                        progress_callback,
                        DiscoveryProgressEvent(stage="warning", message=warning),
                    )
                    emit_progress(
                        progress_callback,
                        DiscoveryProgressEvent(
                            stage="lex_search_result",
                            message=f"Collected {len(raw_candidates)} raw candidates",
                            current=index,
                            total=total_queries,
                            extra={
                                "raw_count": len(raw_candidates),
                                "query_results": 0,
                                "query": query.query,
                            },
                        ),
                    )
                    continue
                successful_query_count += 1
                for result in lex_results:
                    raw_candidates.append(
                        normalise_lex_result_to_candidate(result, category, query)
                    )
                emit_progress(
                    progress_callback,
                    DiscoveryProgressEvent(
                        stage="lex_search_result",
                        message=f"Collected {len(raw_candidates)} raw candidates",
                        current=index,
                        total=total_queries,
                        extra={
                            "raw_count": len(raw_candidates),
                            "query_results": len(lex_results),
                            "query": query.query,
                        },
                    ),
                )
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="lex_search_complete",
                    message="Lex search complete",
                    extra={"raw_count": len(raw_candidates)},
                ),
            )
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="normalise",
                    message=f"Normalised {len(raw_candidates)} candidates",
                    extra={"raw_count": len(raw_candidates)},
                ),
            )
            deduped = deduplicate_candidates(raw_candidates)
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="deduplicate",
                    message=f"Deduplicated to {len(deduped)} candidates",
                    extra={"before": len(raw_candidates), "after": len(deduped)},
                ),
            )
            candidate_sources = score_candidates(deduped, category)
            emit_progress(
                progress_callback,
                DiscoveryProgressEvent(
                    stage="score",
                    message=f"Scored {len(candidate_sources)} candidates",
                    extra={"candidate_count": len(candidate_sources)},
                ),
            )

        resolved_ai_model: str | None = None
        ai_triage_stats: AITriageStats | None = None
        if use_ai_assessment or use_ai_triage:
            try:
                ai_settings = load_ai_settings(
                    model_name=ai_model_name,
                    base_url=litellm_base_url,
                    api_key=litellm_api_key,
                )
                resolved_ai_model = ai_settings.model
            except AdaAIConfigurationError as exc:
                feature = "triage" if use_ai_triage else "assessment"
                msg = f"AI {feature} requested but configuration is invalid: {exc}"
                raise AdaAIConfigurationError(msg) from exc

        if use_ai_assessment:
            candidate_sources = assess_candidates_with_ai(
                category,
                candidate_sources,
                model_name=ai_model_name,
                base_url=litellm_base_url,
                api_key=litellm_api_key,
                progress_callback=progress_callback,
            )

        if use_ai_triage:
            candidate_sources, ai_triage_stats = triage_and_apply_candidates_with_ai(
                category,
                candidate_sources,
                model_name=ai_model_name,
                base_url=litellm_base_url,
                api_key=litellm_api_key,
                batch_size=ai_triage_batch_size,
                apply_recommended_review_status=apply_ai_review_status,
                progress_callback=progress_callback,
            )

        emit_progress(
            progress_callback,
            DiscoveryProgressEvent(
                stage="complete",
                message="Discovery complete",
                extra={"candidate_count": len(candidate_sources), "warning_count": len(warnings)},
            ),
        )

        metadata: dict[str, object] = {
                "use_network": use_network,
                "use_ai_assessment": use_ai_assessment,
                "use_ai_triage": use_ai_triage,
                "ai_triage_batch_size": ai_triage_batch_size if use_ai_triage else None,
                "ai_triage_model": resolved_ai_model if use_ai_triage else None,
                "apply_ai_review_status": apply_ai_review_status if use_ai_triage else None,
                "candidate_count": len(candidate_sources),
                "successful_query_count": successful_query_count if use_network else None,
                "failed_query_count": failed_query_count if use_network else None,
                "partial_results": failed_query_count > 0 if use_network else None,
            }
        if ai_triage_stats is not None:
            metadata.update(ai_triage_stats.to_metadata())

        return DiscoveryRun(
            run_id=run_id or _default_run_id(),
            created_at=datetime.now(tz=UTC),
            category=category,
            query_plan=query_plan,
            candidate_sources=candidate_sources,
            warnings=warnings,
            metadata=metadata,
        )


def discover_sources(
    category: CategoryBrief,
    *,
    lex_adapter: LexAdapter | None = None,
    run_id: str | None = None,
    search_limit: int = 10,
) -> DiscoveryRun:
    """Backwards-compatible wrapper around network discovery."""
    return DiscoveryService(lex_adapter=lex_adapter).run_discovery(
        category,
        run_id=run_id,
        limit_per_query=search_limit,
        use_network=True,
    )


def build_register(category: CategoryBrief, run: DiscoveryRun) -> SourceRegister:
    accepted = [source for source in run.candidate_sources if source.review_status == "accepted"]
    rejected = [source for source in run.candidate_sources if source.review_status == "rejected"]
    parked = [source for source in run.candidate_sources if source.review_status == "parked"]
    return SourceRegister(
        register_id=str(uuid4()),
        category_id=category.category_id,
        created_at=datetime.now(tz=UTC),
        accepted_sources=accepted,
        rejected_sources=rejected,
        parked_sources=parked,
    )
