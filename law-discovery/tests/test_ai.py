from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from law_discovery.ai import (
    _CANDIDATE_TRIAGE_SYSTEM_PROMPT,
    _RELATED_SOURCE_ASSESSMENT_SYSTEM_PROMPT,
    AdaAIConfigurationError,
    AdaAISettings,
    AICheckResponse,
    CandidateRelevanceAssessment,
    CandidateTriageAssessment,
    CandidateTriageBatch,
    CategoryExpansion,
    RelatedSourceAssessment,
    RelatedSourceAssessmentBatch,
    SearchTermSuggestion,
    _candidate_triage_batch_prompt,
    _category_triage_context,
    assess_related_sources_with_ai,
    build_ai_check_agent,
    build_candidate_triage_agent,
    build_category_expansion_agent,
    build_litellm_model,
    build_related_source_assessment_agent,
    check_ai_connection,
    expand_category_with_ai,
    expand_keywords_deterministic,
    is_ai_configured,
    load_ai_settings,
    run_ai_connection_check,
    triage_candidates_with_ai,
)
from law_discovery.models import CandidateSource, CategoryBrief, SourceRelationship


@pytest.fixture(autouse=True)
def clear_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAW_DISCOVERY_LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LITELLM_MODEL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_AI_MODEL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_AI_PROVIDER", raising=False)


def test_load_ai_settings_from_explicit_args() -> None:
    settings = load_ai_settings(
        model_name="test-model",
        base_url="http://localhost:4000/v1",
        api_key="secret",
    )
    assert settings == AdaAISettings(
        provider="litellm",
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
        litellm_api_key="secret",
    )


def test_load_ai_settings_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAW_DISCOVERY_AI_MODEL", "env-model")
    monkeypatch.setenv("LAW_DISCOVERY_LITELLM_BASE_URL", "http://localhost:4000/v1/")
    monkeypatch.setenv("LAW_DISCOVERY_LITELLM_API_KEY", "env-key")
    settings = load_ai_settings()
    assert settings.model == "env-model"
    assert settings.litellm_base_url == "http://localhost:4000/v1"
    assert settings.litellm_api_key == "env-key"


def test_load_ai_settings_missing_model_raises() -> None:
    with pytest.raises(AdaAIConfigurationError, match="LAW_DISCOVERY_AI_MODEL"):
        load_ai_settings(base_url="http://localhost:4000/v1")


def test_load_ai_settings_missing_base_url_raises() -> None:
    with pytest.raises(AdaAIConfigurationError, match="LAW_DISCOVERY_LITELLM_BASE_URL"):
        load_ai_settings(model_name="test-model")


def test_load_ai_settings_unsupported_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAW_DISCOVERY_AI_PROVIDER", "openai")
    with pytest.raises(AdaAIConfigurationError, match="Unsupported AI provider"):
        load_ai_settings(model_name="test-model", base_url="http://localhost:4000/v1")


def test_search_term_suggestion_validates() -> None:
    suggestion = SearchTermSuggestion(
        term="central equine database",
        reason="Common UK traceability term",
        term_type="related_concept",
        confidence="medium",
    )
    assert suggestion.term_type == "related_concept"


def test_category_expansion_validates() -> None:
    expansion = CategoryExpansion(
        category_id="equine_identification",
        suggested_terms=[
            SearchTermSuggestion(
                term="equine passport",
                reason="Related search term",
                term_type="synonym",
                confidence="high",
            )
        ],
        suggested_exclusions=[
            SearchTermSuggestion(
                term="racecourse admission",
                reason="Out of scope",
                term_type="exclusion",
                confidence="medium",
            )
        ],
    )
    assert expansion.category_id == "equine_identification"
    assert len(expansion.suggested_terms) == 1


def test_candidate_relevance_assessment_validates() -> None:
    assessment = CandidateRelevanceAssessment(
        source_id="uksi/2018/123",
        relevance="medium",
        relationship_to_category="possibly_relevant",
        rationale="Title matches equine identification terminology but evidence is limited.",
        useful_evidence=["Title mentions equine identification"],
        false_positive_risks=["May be superseded or partially revoked"],
        recommended_review_status="needs_more_research",
    )
    assert assessment.recommended_review_status == "needs_more_research"


def test_is_ai_configured_false_by_default() -> None:
    assert is_ai_configured() is False


def test_is_ai_configured_true_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAW_DISCOVERY_LITELLM_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("LAW_DISCOVERY_AI_MODEL", "test-model")
    assert is_ai_configured() is True
    settings = load_ai_settings()
    model = build_litellm_model(settings)
    assert model.model_name == "test-model"


def test_expand_keywords_deterministic_without_ai() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test",
        description="Desc",
        synonyms=["equine"],
    )
    expansion = expand_keywords_deterministic(category)
    assert expansion.suggested_terms == []
    assert "not configured" in expansion.notes[0].lower()


def test_category_expansion_agent_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    test_model = TestModel(
        custom_output_args={
            "category_id": "equine_identification",
            "suggested_terms": [
                {
                    "term": "equine passport",
                    "reason": "Related UK term",
                    "term_type": "synonym",
                    "confidence": "high",
                }
            ],
            "suggested_exclusions": [],
            "notes": ["Example note"],
        }
    )
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        synonyms=["horse passport"],
    )
    expansion = expand_category_with_ai(
        category,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert expansion.suggested_terms[0].term == "equine passport"
    assert expansion.category_id == "equine_identification"


def test_build_ai_check_agent_uses_structured_output_type() -> None:
    settings = AdaAISettings(
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
    )
    agent = build_ai_check_agent(settings)
    assert agent.output_type is AICheckResponse


def test_run_ai_connection_check_with_test_model(monkeypatch: pytest.MonkeyPatch) -> None:
    test_model = TestModel(custom_output_args={"ok": True, "message": "hello"})
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    settings = AdaAISettings(
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
    )
    response = run_ai_connection_check(settings)
    assert response.ok is True
    assert response.message == "hello"


def test_check_ai_connection_loads_settings_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    test_model = TestModel(custom_output_args={"ok": True, "message": "hello"})
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    response = check_ai_connection(
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert response == AICheckResponse(ok=True, message="hello")


def test_build_category_expansion_agent_uses_structured_output_type() -> None:
    settings = AdaAISettings(
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
    )
    agent = build_category_expansion_agent(settings)
    assert agent.output_type is CategoryExpansion


def test_candidate_triage_assessment_validates() -> None:
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="medium",
        review_priority="needs_human_review",
        relationship_to_category="possibly_relevant",
        confidence_after_ai="medium",
        rationale="Title mentions slurry storage but evidence is thin.",
        supporting_signals=["Matched term: slurry"],
        false_positive_risks=["May be vehicle safety regulations"],
        recommended_action="needs_more_research",
        evidence_limitations=["No full text provided"],
    )
    assert assessment.recommended_action == "needs_more_research"


def test_candidate_triage_batch_validates() -> None:
    batch = CandidateTriageBatch(
        assessments=[
            CandidateTriageAssessment(
                source_id="lex-1",
                relevance="low",
                review_priority="likely_reject",
                relationship_to_category="possibly_relevant",
                confidence_after_ai="low",
                rationale="Local road act unrelated to manure.",
                recommended_action="reject_candidate",
            )
        ],
        batch_notes=["Batch reviewed conservatively"],
    )
    assert len(batch.assessments) == 1
    assert batch.batch_notes[0].startswith("Batch")


def test_triage_candidates_with_ai_failed_batch_returns_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenAgent:
        def run_sync(self, *_args: object, **_kwargs: object) -> None:
            msg = "simulated model failure"
            raise RuntimeError(msg)

    monkeypatch.setattr(
        "law_discovery.ai.build_candidate_triage_agent",
        lambda _settings: BrokenAgent(),
    )

    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage and spreading rules",
    )
    candidates = [
        CandidateSource(source_id="lex-1", title="Slurry Storage Regulations 2010"),
        CandidateSource(source_id="lex-2", title="M4 Junction Improvement Act 1991"),
    ]
    assessments, stats = triage_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
        batch_size=2,
    )
    assert len(assessments) == 2
    assert all(item.relevance == "uncertain" for item in assessments)
    assert all(item.review_priority == "needs_human_review" for item in assessments)
    assert all(item.evidence_limitations for item in assessments)
    assert stats.ai_triage_failed is True
    assert stats.ai_triage_partial is False
    assert stats.ai_triage_batch_count == 1
    assert stats.ai_triage_failed_batch_count == 1
    assert stats.ai_triage_fallback_candidate_count == 2
    assert stats.ai_triage_successful_candidate_count == 0
    assert stats.ai_triage_failure_reasons == ["AI triage batch failed: simulated model failure"]


def test_candidate_triage_agent_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    test_model = TestModel(
        custom_output_args={
            "assessments": [
                {
                    "source_id": "lex-1",
                    "relevance": "high",
                    "review_priority": "likely_accept",
                    "relationship_to_category": "directly_regulates",
                    "confidence_after_ai": "high",
                    "rationale": "Strong alignment with slurry storage category.",
                    "supporting_signals": ["Title matches slurry storage"],
                    "false_positive_risks": [],
                    "recommended_action": "accept_candidate",
                    "evidence_limitations": [],
                }
            ],
            "batch_notes": [],
        }
    )
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage rules",
    )
    candidates = [
        CandidateSource(source_id="lex-1", title="Slurry Storage Regulations 2010"),
    ]
    assessments, stats = triage_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert assessments[0].review_priority == "likely_accept"
    assert assessments[0].source_id == "lex-1"
    assert stats.ai_triage_failed is False
    assert stats.ai_triage_successful_candidate_count == 1
    assert stats.ai_triage_fallback_candidate_count == 0


def test_triage_candidates_with_ai_partial_batch_failure(
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
                },
                {
                    "source_id": "lex-4",
                    "relevance": "low",
                    "review_priority": "likely_reject",
                    "relationship_to_category": "possibly_relevant",
                    "confidence_after_ai": "low",
                    "rationale": "Unrelated.",
                    "supporting_signals": [],
                    "false_positive_risks": [],
                    "recommended_action": "reject_candidate",
                    "evidence_limitations": [],
                },
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
                msg = "first batch failed"
                raise RuntimeError(msg)
            return SimpleNamespace(output=success_batch)

    monkeypatch.setattr(
        "law_discovery.ai.build_candidate_triage_agent",
        lambda _settings: PartialFailureAgent(),
    )

    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage rules",
    )
    candidates = [
        CandidateSource(source_id="lex-1", title="First"),
        CandidateSource(source_id="lex-2", title="Second"),
        CandidateSource(source_id="lex-3", title="Third"),
        CandidateSource(source_id="lex-4", title="Fourth"),
    ]
    assessments, stats = triage_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
        batch_size=2,
    )
    assert len(assessments) == 4
    assert stats.ai_triage_partial is True
    assert stats.ai_triage_failed is False
    assert stats.ai_triage_batch_count == 2
    assert stats.ai_triage_failed_batch_count == 1
    assert stats.ai_triage_successful_batch_count == 1
    assert stats.ai_triage_fallback_candidate_count == 2
    assert stats.ai_triage_successful_candidate_count == 2


def test_build_candidate_triage_agent_uses_structured_output_type() -> None:
    settings = AdaAISettings(
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
    )
    agent = build_candidate_triage_agent(settings)
    assert agent.output_type is CandidateTriageBatch


def test_candidate_triage_system_prompt_mentions_triage_guidance() -> None:
    assert "category.metadata.triage_guidance" in _CANDIDATE_TRIAGE_SYSTEM_PROMPT
    assert "user-supplied domain guidance" in _CANDIDATE_TRIAGE_SYSTEM_PROMPT
    assert "not a legal conclusion" in _CANDIDATE_TRIAGE_SYSTEM_PROMPT


def test_category_triage_context_includes_full_metadata() -> None:
    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage rules",
        metadata={
            "source": "user_supplied_category_description",
            "triage_guidance": {
                "likely_accept": ["Slurry storage regulations"],
                "likely_reject": ["Road improvement acts"],
                "triage_rule": "Weak terms are supporting signals only.",
            },
        },
    )
    context = _category_triage_context(category)
    assert "metadata:" in context
    assert '"triage_guidance"' in context
    assert "Slurry storage regulations" in context
    assert "Weak terms are supporting signals only." in context


def test_candidate_triage_batch_prompt_includes_guidance_once_per_batch() -> None:
    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage rules",
        metadata={
            "triage_guidance": {
                "likely_accept": ["Slurry storage regulations"],
                "triage_rule": "Weak terms are supporting signals only.",
            }
        },
    )
    candidates = [
        CandidateSource(source_id="lex-1", title="Slurry Storage Regulations 2010"),
        CandidateSource(source_id="lex-2", title="M4 Junction Improvement Act 1991"),
    ]
    prompt = _candidate_triage_batch_prompt(category, candidates)
    assert prompt.count("triage_guidance") == 1
    assert prompt.count("Slurry storage regulations") == 1
    assert "source_id: lex-1" in prompt
    assert "source_id: lex-2" in prompt


def test_triage_candidates_with_ai_passes_category_metadata_in_batch_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []

    class CapturingAgent:
        def run_sync(self, prompt: str, *_args: object, **_kwargs: object) -> object:
            captured_prompts.append(prompt)
            return SimpleNamespace(
                output=CandidateTriageBatch(
                    assessments=[
                        CandidateTriageAssessment(
                            source_id="lex-1",
                            relevance="high",
                            review_priority="likely_accept",
                            relationship_to_category="directly_regulates",
                            confidence_after_ai="high",
                            rationale="Relevant.",
                            recommended_action="accept_candidate",
                        )
                    ]
                )
            )

    monkeypatch.setattr(
        "law_discovery.ai.build_candidate_triage_agent",
        lambda _settings: CapturingAgent(),
    )

    category = CategoryBrief(
        category_id="slurry",
        label="Slurry and manure",
        description="Storage rules",
        metadata={
            "triage_guidance": {
                "likely_reject": ["Road improvement acts"],
            }
        },
    )
    candidates = [
        CandidateSource(source_id="lex-1", title="Slurry Storage Regulations 2010"),
    ]
    triage_candidates_with_ai(
        category,
        candidates,
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert len(captured_prompts) == 1
    assert "triage_guidance" in captured_prompts[0]
    assert "Road improvement acts" in captured_prompts[0]


def test_build_related_source_assessment_agent_uses_structured_output_type() -> None:
    settings = AdaAISettings(
        model="test-model",
        litellm_base_url="http://localhost:4000/v1",
    )
    agent = build_related_source_assessment_agent(settings)
    assert agent.output_type is RelatedSourceAssessmentBatch


def test_related_source_assessment_system_prompt_avoids_legal_effect() -> None:
    assert "Do not decide final legal effect" in _RELATED_SOURCE_ASSESSMENT_SYSTEM_PROMPT
    assert "appears to amend" in _RELATED_SOURCE_ASSESSMENT_SYSTEM_PROMPT


def test_assess_related_sources_with_ai_uses_test_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_model = TestModel(
        custom_output_args={
            "assessments": [
                {
                    "from_source_id": "seed",
                    "to_source_id": "related",
                    "relationship_type": "amended_by",
                    "relevance": "high",
                    "confidence": "medium",
                    "recommended_review_status": "accepted",
                    "rationale": "Title suggests amendment.",
                }
            ],
            "batch_notes": [],
        }
    )
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    category = CategoryBrief(
        category_id="equine",
        label="Equine",
        description="Test",
    )
    seed = CandidateSource(source_id="seed", title="Horse Passports Regulations 2009")
    related = CandidateSource(
        source_id="related",
        title="Horse Passports Regulations 2009 Amendment Regulations 2015",
    )
    relationship = SourceRelationship(
        relationship_id="rel:seed:related:amended_by",
        from_source_id="seed",
        to_source_id="related",
        relationship_type="amended_by",
    )
    assessments = assess_related_sources_with_ai(
        category,
        seed_sources=[seed],
        related_sources=[related],
        relationships=[relationship],
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert len(assessments) == 1
    assert isinstance(assessments[0], RelatedSourceAssessment)
    assert assessments[0].relationship_type == "amended_by"


def test_assess_related_sources_with_ai_batch_failure_returns_uncertain_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenAgent:
        def run_sync(self, *_args: object, **_kwargs: object) -> None:
            msg = "simulated batch failure"
            raise RuntimeError(msg)

    monkeypatch.setattr(
        "law_discovery.ai.build_related_source_assessment_agent",
        lambda _settings: BrokenAgent(),
    )

    relationship = SourceRelationship(
        relationship_id="rel:a:b:amended_by",
        from_source_id="a",
        to_source_id="b",
        relationship_type="amended_by",
    )
    assessments = assess_related_sources_with_ai(
        CategoryBrief(category_id="x", label="X", description="Y"),
        seed_sources=[CandidateSource(source_id="a", title="Seed")],
        related_sources=[CandidateSource(source_id="b", title="Amendment")],
        relationships=[relationship],
        model_name="test-model",
        base_url="http://localhost:4000/v1",
    )
    assert assessments[0].relevance == "uncertain"
    assert "AI relationship triage unavailable" in assessments[0].rationale


def test_invalid_search_term_confidence_fails_validation() -> None:
    with pytest.raises(ValidationError):
        SearchTermSuggestion.model_validate(
            {
                "term": "x",
                "reason": "y",
                "term_type": "synonym",
                "confidence": "maybe",
            }
        )
