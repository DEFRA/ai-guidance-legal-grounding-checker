from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from law_discovery.ai import CandidateRelevanceAssessment, CandidateTriageAssessment, CandidateTriageBatch
from law_discovery.discovery_service import (
    DiscoveryService,
    apply_ai_assessment_to_candidate,
    apply_triage_assessment_to_candidate,
    triage_and_apply_candidates_with_ai,
)
from law_discovery.lex_adapter import LexAdapter, LexAdapterError
from law_discovery.models import CandidateSource, CategoryBrief


def _sample_category() -> CategoryBrief:
    return CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["horse passport"],
    )


def test_run_discovery_without_lex_config_fails_fast() -> None:
    service = DiscoveryService()
    with pytest.raises(LexAdapterError, match="LAW_DISCOVERY_LEX_BASE_URL"):
        service.run_discovery(_sample_category(), use_network=True)


def test_run_discovery_with_network_disabled_returns_empty_candidates_and_warning() -> None:
    service = DiscoveryService()
    run = service.run_discovery(_sample_category(), use_network=False)

    assert run.candidate_sources == []
    assert any("network discovery was disabled" in warning.lower() for warning in run.warnings)
    assert run.metadata["use_network"] is False
    assert run.metadata["candidate_count"] == 0
    assert len(run.query_plan) > 0


def test_apply_ai_assessment_maps_high_to_confidence_high() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Equine Identification (England) Regulations 2018",
        source_type="uksi",
        confidence="low",
    )
    assessment = CandidateRelevanceAssessment(
        source_id="lex-1",
        relevance="high",
        relationship_to_category="directly_regulates",
        rationale="Strong match to equine identification requirements.",
    )

    updated = apply_ai_assessment_to_candidate(candidate, assessment)

    assert updated.confidence == "high"
    assert updated.relationship_to_category == "directly_regulates"
    assert "AI rationale:" in (updated.notes or "")


def test_apply_ai_assessment_never_sets_accepted() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Example",
        review_status="unreviewed",
    )
    assessment = CandidateRelevanceAssessment(
        source_id="lex-1",
        relevance="high",
        relationship_to_category="directly_regulates",
        rationale="Looks relevant.",
        recommended_review_status="accepted",
    )

    updated = apply_ai_assessment_to_candidate(candidate, assessment)

    assert updated.review_status == "unreviewed"


def test_apply_ai_assessment_only_rejects_when_allowed() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Example",
        review_status="unreviewed",
    )
    assessment = CandidateRelevanceAssessment(
        source_id="lex-1",
        relevance="not_relevant",
        relationship_to_category="possibly_relevant",
        rationale="Out of scope.",
    )

    without_rejection = apply_ai_assessment_to_candidate(
        candidate,
        assessment,
        allow_ai_rejection=False,
    )
    with_rejection = apply_ai_assessment_to_candidate(
        candidate,
        assessment,
        allow_ai_rejection=True,
    )

    assert without_rejection.review_status == "unreviewed"
    assert with_rejection.review_status == "rejected"


def test_apply_triage_assessment_updates_confidence() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Slurry Storage Regulations 2010",
        confidence="low",
    )
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="high",
        review_priority="likely_accept",
        relationship_to_category="directly_regulates",
        confidence_after_ai="high",
        rationale="Strong category alignment.",
        recommended_action="accept_candidate",
    )

    updated = apply_triage_assessment_to_candidate(candidate, assessment)

    assert updated.confidence == "high"
    assert updated.relationship_to_category == "directly_regulates"
    assert updated.ai_triage is not None
    assert updated.ai_triage.review_priority == "likely_accept"
    assert "AI triage rationale:" in (updated.notes or "")


def test_apply_triage_assessment_does_not_accept_by_default() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Example",
        review_status="unreviewed",
    )
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="high",
        review_priority="likely_accept",
        relationship_to_category="directly_regulates",
        confidence_after_ai="high",
        rationale="Looks relevant.",
        recommended_action="accept_candidate",
    )

    updated = apply_triage_assessment_to_candidate(candidate, assessment)

    assert updated.review_status == "unreviewed"


def test_apply_triage_assessment_applies_review_status_when_flag_set() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Example",
        review_status="unreviewed",
    )
    accept_assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="high",
        review_priority="likely_accept",
        relationship_to_category="directly_regulates",
        confidence_after_ai="high",
        rationale="Core instrument.",
        recommended_action="accept_candidate",
    )
    reject_assessment = CandidateTriageAssessment(
        source_id="lex-2",
        relevance="not_relevant",
        review_priority="likely_reject",
        relationship_to_category="possibly_relevant",
        confidence_after_ai="low",
        rationale="Unrelated local act.",
        recommended_action="reject_candidate",
    )

    accepted = apply_triage_assessment_to_candidate(
        candidate,
        accept_assessment,
        apply_recommended_review_status=True,
    )
    rejected = apply_triage_assessment_to_candidate(
        CandidateSource(source_id="lex-2", title="Local Act", review_status="unreviewed"),
        reject_assessment,
        apply_recommended_review_status=True,
    )

    assert accepted.review_status == "accepted"
    assert rejected.review_status == "rejected"


def _minimal_category() -> CategoryBrief:
    return CategoryBrief(
        category_id="test_category",
        label="Alpha",
        description="Beta",
    )


def test_run_discovery_continues_when_one_lex_query_fails() -> None:
    failing_query = "Alpha Beta"
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = request.content.decode("utf-8")
        if failing_query in body:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example Regulations 2010",
                        "uri": "https://www.legislation.gov.uk/uksi/2010/1",
                        "type": "uksi",
                    }
                ]
            },
        )

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        max_retries=0,
        sleep=lambda _duration: None,
    )
    service = DiscoveryService(lex_adapter=adapter)

    run = service.run_discovery(_minimal_category(), use_network=True)

    assert call_count == 2
    assert len(run.candidate_sources) > 0
    assert run.metadata["partial_results"] is True
    assert run.metadata["failed_query_count"] == 1
    assert run.metadata["successful_query_count"] == 1
    assert any("Lex search failed for query" in warning for warning in run.warnings)
    assert any("Discovery continued with remaining queries" in warning for warning in run.warnings)


def test_triage_and_apply_all_batches_failed_sets_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenAgent:
        def run_sync(self, *_args: object, **_kwargs: object) -> None:
            msg = "Connection error"
            raise RuntimeError(msg)

    monkeypatch.setattr(
        "law_discovery.ai.build_candidate_triage_agent",
        lambda _settings: BrokenAgent(),
    )

    category = _sample_category()
    candidates = [
        CandidateSource(source_id="lex-1", title="Example Regulations 2010"),
        CandidateSource(source_id="lex-2", title="Other Regulations 2011"),
    ]

    triaged, stats = triage_and_apply_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
        batch_size=2,
    )

    assert len(triaged) == 2
    assert stats.ai_triage_failed is True
    assert stats.ai_triage_partial is False
    assert stats.to_metadata()["ai_triage_failed"] is True
    assert all("AI triage unavailable" in (candidate.notes or "") for candidate in triaged)


def test_triage_and_apply_partial_batch_failure_sets_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    success_model = TestModel(
        custom_output_args={
            "assessments": [
                {
                    "source_id": "lex-3",
                    "relevance": "high",
                    "review_priority": "likely_accept",
                    "relationship_to_category": "directly_regulates",
                    "confidence_after_ai": "high",
                    "rationale": "Relevant.",
                    "supporting_signals": [],
                    "false_positive_risks": [],
                    "recommended_action": "accept_candidate",
                    "evidence_limitations": [],
                }
            ],
            "batch_notes": [],
        }
    )

    success_batch = CandidateTriageBatch.model_validate(success_model.custom_output_args)

    class PartialFailureAgent:
        def run_sync(self, *_args: object, **_kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "Connection error"
                raise RuntimeError(msg)
            return SimpleNamespace(output=success_batch)

    monkeypatch.setattr(
        "law_discovery.ai.build_candidate_triage_agent",
        lambda _settings: PartialFailureAgent(),
    )

    category = _sample_category()
    candidates = [
        CandidateSource(source_id="lex-1", title="First"),
        CandidateSource(source_id="lex-2", title="Second"),
        CandidateSource(source_id="lex-3", title="Third"),
    ]

    _triaged, stats = triage_and_apply_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
        batch_size=2,
    )

    assert stats.ai_triage_partial is True
    assert stats.ai_triage_failed is False
    assert stats.to_metadata()["ai_triage_partial"] is True
